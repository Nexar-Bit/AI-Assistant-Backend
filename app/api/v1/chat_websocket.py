"""WebSocket endpoints for real-time chat."""

import json
import logging
import uuid
from datetime import datetime

from fastapi import APIRouter, HTTPException, Query, WebSocket, WebSocketDisconnect, status
from sqlalchemy.orm import Session

from app.core.database import SessionLocal
from app.core.security import decode_token
from app.chat import ChatMessage, ChatThread, ChatSessionManager, MessageHandler, ChatContextBuilder, connection_manager
from app.models.user import User
from app.services.chat_ai_service import ChatAIProvider, ChatMessage as ChatMsg, ChatRequest
from app.services.openai_service import OpenAIProvider
from app.tokens.accounting import TokenAccountingService
from app.tokens.limits import TokenLimitsService
from app.api.v1 import workshops, chat
from jose import JWTError


logger = logging.getLogger("app.chat.websocket")

router = APIRouter()


async def get_current_user_ws(
    websocket: WebSocket,
    token: str,
    db: Session,
) -> User | None:
    """Authenticate WebSocket connection via query parameter token."""
    try:
        payload = decode_token(token, expected_type="access")
        user_id_str = payload.get("sub")
        if not user_id_str:
            await websocket.close(code=1008, reason="Invalid token payload")
            return None
        
        user_id = uuid.UUID(user_id_str)
        user = db.query(User).filter(User.id == user_id, User.is_active.is_(True)).first()
        
        if not user:
            await websocket.close(code=1008, reason="User not found or inactive")
            return None
        
        return user
    except (JWTError, ValueError) as e:
        logger.warning("WebSocket authentication failed: %s", e)
        await websocket.close(code=1008, reason="Invalid token")
        return None


@router.websocket("/ws/chat/{thread_id}")
async def chat_websocket(
    websocket: WebSocket,
    thread_id: str,
    token: str = Query(...),
):
    """
    WebSocket endpoint for real-time chat.
    
    Connection URL: ws://localhost:8000/api/v1/ws/chat/{thread_id}?token={access_token}
    
    Message Format (Client → Server):
    {
        "type": "message",
        "content": "User message text",
        "attachments": []
    }
    
    Message Format (Server → Client):
    {
        "type": "message" | "typing" | "error" | "status",
        "message": {...ChatMessage...},
        "thread": {...ChatThread...},
        "timestamp": "2025-01-XX..."
    }
    """
    # Authenticate user - create DB session manually
    from app.core.database import SessionLocal
    db = SessionLocal()
    user = None
    thread = None
    
    try:
        user = await get_current_user_ws(websocket, token, db)
        if not user:
            db.close()
            return  # Connection already closed
        
        try:
            thread_uuid = uuid.UUID(thread_id)
        except ValueError:
            await websocket.close(code=1008, reason="Invalid thread_id")
            db.close()
            return
        
        # Verify thread exists and user has access using ChatSessionManager
        thread = ChatSessionManager.get_session(db, thread_uuid, user.id)
        
        if not thread:
            await websocket.close(code=1008, reason="Thread not found")
            db.close()
            return
        
        # Ensure user is member of workshop and check role
        try:
            membership = workshops._ensure_workshop_member(db, user.id, thread.workshop_id)
            # Viewers cannot access chat (read-only, can only view history)
            if membership.role == "viewer":
                await websocket.close(code=1008, reason="Viewers cannot access chat. Read-only access available in history.")
                db.close()
                return
        except HTTPException:
            await websocket.close(code=1008, reason="Not a member of this workshop")
            db.close()
            return
        
        # Connect WebSocket
        await connection_manager.connect(websocket, thread_id, str(user.id))
        
        # Send connection confirmation
        await websocket.send_json({
            "type": "status",
            "status": "connected",
            "thread_id": thread_id,
            "timestamp": datetime.utcnow().isoformat(),
        })
        
        # Get AI provider assigned to this workshop
        try:
            chat_provider, model_name = chat.get_workshop_ai_provider(thread.workshop_id, db)
        except HTTPException as e:
            await websocket.send_json({
                "type": "error",
                "message": e.detail,
            })
            db.close()
            return
        except Exception as e:
            logger.error(f"Failed to get AI provider for workshop {thread.workshop_id}: {e}")
            await websocket.send_json({
                "type": "error",
                "message": "AI service is not available. Please contact your administrator.",
            })
            db.close()
            return
        
        context_builder = ChatContextBuilder()
        
        # Message loop - keep DB session open for entire connection
        while True:
                # Receive message from client
                data = await websocket.receive_text()
                
                try:
                    message_data = json.loads(data)
                except json.JSONDecodeError:
                    await websocket.send_json({
                        "type": "error",
                        "message": "Invalid JSON format",
                    })
                    continue
                
                if message_data.get("type") != "message":
                    await websocket.send_json({
                        "type": "error",
                        "message": "Only 'message' type is supported",
                    })
                    continue
                
                content = message_data.get("content", "").strip()
                if not content:
                    await websocket.send_json({
                        "type": "error",
                        "message": "Message content is required",
                    })
                    continue
                
                attachments = message_data.get("attachments", [])
                
                # Broadcast typing indicator
                await connection_manager.broadcast_to_thread(
                    thread_id,
                    {
                        "type": "typing",
                        "user_id": str(user.id),
                        "timestamp": datetime.utcnow().isoformat(),
                    },
                )
                
                # Get existing messages using MessageHandler
                existing_messages = MessageHandler.get_thread_messages(db, thread_uuid)
                
                # Create user message using MessageHandler
                user_message = MessageHandler.create_message(
                    db,
                    thread_id=thread_uuid,
                    user_id=user.id,
                    content=content,
                    role="user",
                    sender_type="technician",
                    attachments=attachments if attachments else {},
                    created_by=user.id,
                )
                
                # Build AI context
                formatted_messages = context_builder.build_context(thread, existing_messages + [user_message])
                chat_messages = [
                    ChatMsg(role=msg["role"], content=msg["content"])
                    for msg in formatted_messages[1:]  # Skip system message
                ]
                
                # Check token limits before AI call
                token_accounting = TokenAccountingService(db)
                estimated_tokens = sum(len(msg.get("content", "")) // 4 for msg in formatted_messages) + 200  # Buffer for response
                
                # Check limits
                if not token_accounting.check_workshop_limits(thread.workshop_id, estimated_tokens):
                    await websocket.send_json({
                        "type": "error",
                        "message": "Workshop token limit exceeded. Please contact your administrator.",
                    })
                    continue
                
                if not token_accounting.check_user_limits(user.id, thread.workshop_id, estimated_tokens):
                    await websocket.send_json({
                        "type": "error",
                        "message": "Your daily token limit has been reached. Please try again tomorrow.",
                    })
                    continue
                
                # Reserve tokens (optimistic)
                if not token_accounting.reserve_tokens(user.id, thread.workshop_id, estimated_tokens):
                    await websocket.send_json({
                        "type": "error",
                        "message": "Unable to reserve tokens. Please try again.",
                    })
                    continue
                
                # Get AI response
                chat_request = ChatRequest(
                    user_id=str(user.id),
                    messages=chat_messages,
                    vehicle_context=thread.vehicle_context,
                    model=model_name,
                    temperature=0.1,
                    max_tokens=800,
                )
                
                ai_response, _ = await chat_provider.chat_completion(chat_request)
                
                # Record actual token usage
                token_accounting.record_token_usage(
                    user_id=user.id,
                    workshop_id=thread.workshop_id,
                    input_tokens=ai_response.prompt_tokens,
                    output_tokens=ai_response.completion_tokens,
                    model=ai_response.model or "gpt-4o-mini",
                )
                
                # Get updated token info for real-time tracking
                remaining_tokens = token_accounting.get_user_remaining_tokens(user.id, thread.workshop_id)
                
                # Create assistant message using MessageHandler
                assistant_message = MessageHandler.create_ai_message(
                    db,
                    thread_id=thread_uuid,
                    user_id=user.id,
                    content=ai_response.content,
                    ai_model=ai_response.model,
                    prompt_tokens=ai_response.prompt_tokens,
                    completion_tokens=ai_response.completion_tokens,
                    total_tokens=ai_response.total_tokens,
                    estimated_cost=float(ai_response.estimated_cost) if ai_response.estimated_cost else None,
                    created_by=user.id,
                )
                
                # Refresh thread to get updated token totals
                db.refresh(thread)
                
                # Broadcast messages to all connected clients with token info
                await connection_manager.broadcast_to_thread(
                    thread_id,
                    {
                        "type": "message",
                        "user_message": {
                            "id": str(user_message.id),
                            "content": user_message.content,
                            "role": user_message.role,
                            "sender_type": user_message.sender_type,
                            "attachments": user_message.attachments,
                            "sequence_number": user_message.sequence_number,
                            "created_at": user_message.created_at.isoformat(),
                        },
                        "assistant_message": {
                            "id": str(assistant_message.id),
                            "content": assistant_message.content,
                            "role": assistant_message.role,
                            "sender_type": assistant_message.sender_type,
                            "sequence_number": assistant_message.sequence_number,
                            "total_tokens": assistant_message.total_tokens,
                            "created_at": assistant_message.created_at.isoformat(),
                        },
                        "thread": {
                            "id": str(thread.id),
                            "total_tokens": thread.total_tokens,
                            "last_message_at": thread.last_message_at.isoformat() if thread.last_message_at else None,
                        },
                        "token_usage": {
                            "user": remaining_tokens["user"],
                            "workshop": remaining_tokens["workshop"],
                        },
                        "timestamp": datetime.utcnow().isoformat(),
                    },
                )
    
    except WebSocketDisconnect:
        logger.info("WebSocket disconnected: thread_id=%s, user_id=%s", thread_id, user.id)
    except Exception as e:
        logger.error("WebSocket error: %s", e, exc_info=True)
        from app.core.messages import (
            ERROR_INTERNAL_SERVER,
            AI_SERVICE_CONFIG_ERROR,
            TOKEN_LIMIT_EXCEEDED,
            DB_CONNECTION_ERROR,
            ERROR_NOT_FOUND,
            ERROR_PERMISSION_DENIED,
            ERROR_TIMEOUT,
        )
        
        error_message = ERROR_INTERNAL_SERVER
        
        # Provide more specific error messages based on exception type
        error_type = type(e).__name__
        error_str = str(e)
        
        if "OPENAI_API_KEY" in error_str or "api key" in error_str.lower():
            error_message = AI_SERVICE_CONFIG_ERROR
        elif "token" in error_str.lower() and ("limit" in error_str.lower() or "exceeded" in error_str.lower()):
            error_message = TOKEN_LIMIT_EXCEEDED
        elif "database" in error_str.lower() or "connection" in error_str.lower() or "sql" in error_str.lower():
            error_message = DB_CONNECTION_ERROR
        elif "not found" in error_str.lower() or "404" in error_str:
            error_message = ERROR_NOT_FOUND
        elif "permission" in error_str.lower() or "forbidden" in error_str.lower() or "403" in error_str:
            error_message = ERROR_PERMISSION_DENIED
        elif "timeout" in error_str.lower():
            error_message = ERROR_TIMEOUT
        else:
            # For debugging, include error type in development
            import os
            if os.getenv("ENVIRONMENT", "production") == "development":
                error_message = f"Error: {error_type}: {error_str[:100]}"
        
        try:
            await websocket.send_json({
                "type": "error",
                "message": error_message,
                "error_type": error_type,
            })
        except:
            pass
    finally:
        await connection_manager.disconnect(websocket)
        db.close()

