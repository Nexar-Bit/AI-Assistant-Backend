"""Chat-based conversation endpoints for multi-message threads."""

import uuid
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status, WebSocket, WebSocketDisconnect
from datetime import datetime
from sqlalchemy import desc
from sqlalchemy.orm import Session

from app.api.dependencies import get_current_user
from app.core.database import get_db
from app.models.user import User
from app.models.vehicle import Vehicle
from app.chat import ChatThread, ChatMessage, ChatSessionManager, MessageHandler, ChatContextBuilder, connection_manager
from app.chat.websocket import ChatWebSocketManager
from app.workshops import WorkshopMember
from app.workshops.crud import WorkshopMemberCRUD
from app.services.chat_ai_service import ChatAIProvider, ChatMessage as ChatMsg, ChatRequest
from app.services.openai_service import OpenAIProvider
from app.tokens import TokenAccountingService
from app.services.token_notifications import TokenNotificationService
from app.api.v1 import workshops
from app.core.security import decode_token
from jose import JWTError


router = APIRouter(prefix="/chat", tags=["chat"])


def get_ai_provider() -> OpenAIProvider:
    """Get OpenAI provider instance."""
    from app.core.config import settings
    if not settings.OPENAI_API_KEY:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="OpenAI API key is not configured",
        )
    return OpenAIProvider(api_key=settings.OPENAI_API_KEY, default_model="gpt-4o-mini")


def get_chat_provider() -> ChatAIProvider:
    """Get chat AI provider instance."""
    return ChatAIProvider(get_ai_provider())


@router.post("/threads", status_code=status.HTTP_201_CREATED)
async def create_thread(
    payload: dict,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Create a new chat thread for a vehicle consultation."""
    workshop_id_str = payload.get("workshop_id")
    license_plate = payload.get("license_plate")
    vehicle_km = payload.get("vehicle_km")
    error_codes = payload.get("error_codes")  # Comma-separated DTC codes
    vehicle_context = payload.get("vehicle_context")
    vehicle_id_str = payload.get("vehicle_id")
    
    if not workshop_id_str or not license_plate:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="workshop_id and license_plate are required",
        )
    
    try:
        workshop_id = uuid.UUID(workshop_id_str)
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid workshop_id",
        )
    
    # Ensure user is a member of the workshop
    workshops._ensure_workshop_member(db, current_user.id, workshop_id)
    
    # Get or create vehicle
    vehicle = None
    if vehicle_id_str:
        try:
            vehicle_id = uuid.UUID(vehicle_id_str)
            vehicle = db.query(Vehicle).filter(Vehicle.id == vehicle_id).first()
        except ValueError:
            pass
    
    if not vehicle:
        # Try to find by license plate
        vehicle = db.query(Vehicle).filter(Vehicle.license_plate == license_plate).first()
        if not vehicle:
            # Create new vehicle
            vehicle = Vehicle(
                license_plate=license_plate,
                current_km=vehicle_km,
                workshop_id=workshop_id,
                created_by_user_id=current_user.id,
                created_by=str(current_user.id),
            )
            db.add(vehicle)
            db.flush()
    
    # Build vehicle context string
    context_parts = [f"License Plate: {license_plate}"]
    if vehicle.make:
        context_parts.append(f"Make: {vehicle.make}")
    if vehicle.model:
        context_parts.append(f"Model: {vehicle.model}")
    if vehicle.year:
        context_parts.append(f"Year: {vehicle.year}")
    if vehicle_km:
        context_parts.append(f"Current KM: {vehicle_km}")
    if error_codes:
        context_parts.append(f"Error Codes (DTC): {error_codes}")
    if vehicle_context:
        context_parts.append(f"Additional Context: {vehicle_context}")
    
    vehicle_context_str = "\n".join(context_parts)
    
    # Create thread using ChatSessionManager
    thread = ChatSessionManager.create_session(
        db,
        workshop_id=workshop_id,
        user_id=current_user.id,
        license_plate=license_plate,
        vehicle_id=vehicle.id,
        vehicle_km=vehicle_km,
        error_codes=error_codes,
        vehicle_context=vehicle_context_str,
        created_by=current_user.id,
    )
    
    return thread


@router.get("/threads")
def list_threads(
    workshop_id: Optional[str] = None,
    license_plate: Optional[str] = None,
    is_resolved: Optional[bool] = None,
    is_archived: Optional[bool] = None,
    status: Optional[str] = None,
    search: Optional[str] = None,  # Search in title, license_plate, vehicle_context
    limit: int = Query(50, ge=1, le=100),
    offset: int = Query(0, ge=0),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """List chat threads with search and filtering."""
    try:
        workshop_uuid = uuid.UUID(workshop_id) if workshop_id else None
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid workshop_id",
        )
    
    # Use ChatSessionManager to list threads
    threads = ChatSessionManager.list_sessions(
        db,
        workshop_id=workshop_uuid,
        user_id=current_user.id,
        license_plate=license_plate,
        status=status,
        is_resolved=is_resolved,
        is_archived=is_archived,
        limit=limit,
        offset=offset,
    )
    
    # Apply search filter if provided
    if search:
        search_lower = search.lower()
        threads = [
            t for t in threads
            if (
                search_lower in (t.title or "").lower()
                or search_lower in t.license_plate.lower()
                or search_lower in (t.vehicle_context or "").lower()
            )
        ]
    
    return {"threads": threads, "total": len(threads)}


@router.get("/threads/{thread_id}")
def get_thread(
    thread_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Get a chat thread with all messages."""
    try:
        thread_uuid = uuid.UUID(thread_id)
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid thread_id",
        )
    
    # Get thread using ChatSessionManager
    thread = ChatSessionManager.get_session(db, thread_uuid, current_user.id)
    
    if not thread:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Thread not found",
        )
    
    # Get messages using MessageHandler
    messages = MessageHandler.get_thread_messages(db, thread_uuid)
    
    return {
        "thread": thread,
        "messages": messages,
    }


@router.put("/threads/{thread_id}")
def update_thread(
    thread_id: str,
    payload: dict,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Update a chat thread (e.g., mark as resolved, archive, etc.)."""
    try:
        thread_uuid = uuid.UUID(thread_id)
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid thread_id",
        )
    
    # Get thread using ChatSessionManager
    thread = ChatSessionManager.get_session(db, thread_uuid, current_user.id)
    
    if not thread:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Thread not found",
        )
    
    # Update fields if provided
    if "is_resolved" in payload:
        thread.is_resolved = bool(payload["is_resolved"])
    if "is_archived" in payload:
        thread.is_archived = bool(payload["is_archived"])
    if "status" in payload:
        thread.status = payload["status"]
    if "title" in payload:
        thread.title = payload["title"]
    
    db.add(thread)
    db.commit()
    db.refresh(thread)
    
    return thread


@router.post("/threads/{thread_id}/messages", status_code=status.HTTP_201_CREATED)
async def send_message(
    thread_id: str,
    payload: dict,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
    chat_provider: ChatAIProvider = Depends(get_chat_provider),
):
    """Send a message in a chat thread and get AI response."""
    content = payload.get("content")
    if not content:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Message content is required",
        )
    
    try:
        thread_uuid = uuid.UUID(thread_id)
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid thread_id",
        )
    
    # Get thread using ChatSessionManager
    thread = ChatSessionManager.get_session(db, thread_uuid, current_user.id)
    
    if not thread:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Thread not found",
        )
    
    # Ensure user is still a member of the workshop
    workshops._ensure_workshop_member(db, current_user.id, thread.workshop_id)
    
    # Get existing messages using MessageHandler
    existing_messages = MessageHandler.get_thread_messages(db, thread_uuid)
    
    # Create user message using MessageHandler
    attachments = payload.get("attachments", {})
    user_message = MessageHandler.create_message(
        db,
        thread_id=thread_uuid,
        user_id=current_user.id,
        content=content,
        role="user",
        sender_type="technician",
        attachments=attachments,
        created_by=current_user.id,
    )
    
    # Token validation and accounting
    accounting_service = TokenAccountingService(db)
    notification_service = TokenNotificationService(db)
    
    # Estimate tokens needed (rough estimate: 4 chars per token)
    estimated_tokens = len(content) // 4 + 800  # Content + max response
    
    # Check token limits before AI call
    if not accounting_service.check_workshop_limits(thread.workshop_id, estimated_tokens):
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail={
                "error": "Workshop monthly token limit exceeded",
                "remaining": accounting_service.get_user_remaining_tokens(current_user.id, thread.workshop_id),
            },
        )
    
    if not accounting_service.check_user_limits(current_user.id, thread.workshop_id, estimated_tokens):
        remaining = accounting_service.get_user_remaining_tokens(current_user.id, thread.workshop_id)
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail={
                "error": "User daily token limit exceeded",
                "remaining": remaining,
            },
        )
    
    # Reserve tokens (optimistic check)
    if not accounting_service.reserve_tokens(current_user.id, thread.workshop_id, estimated_tokens):
        remaining = accounting_service.get_user_remaining_tokens(current_user.id, thread.workshop_id)
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail={
                "error": "Insufficient tokens available",
                "remaining": remaining,
            },
        )
    
    # Check and get notifications
    notifications = notification_service.check_and_notify(current_user.id, thread.workshop_id)
    
    # Use ChatContextBuilder to build conversation history
    context_builder = ChatContextBuilder()
    formatted_messages = context_builder.build_context(thread, existing_messages + [user_message])
    
    # Convert to ChatRequest format
    chat_messages = [
        ChatMsg(role=msg["role"], content=msg["content"])
        for msg in formatted_messages[1:]  # Skip system message (handled by context manager)
    ]
    
    # Get AI response
    chat_request = ChatRequest(
        user_id=str(current_user.id),
        messages=chat_messages,
        vehicle_context=thread.vehicle_context,
        model="gpt-4o-mini",
        temperature=0.1,
        max_tokens=800,
    )
    
    ai_response, _ = await chat_provider.chat_completion(chat_request)
    
    # Record actual token usage
    accounting_service.record_token_usage(
        current_user.id,
        thread.workshop_id,
        ai_response.prompt_tokens,
        ai_response.completion_tokens,
        ai_response.model,
    )
    
    # Create assistant message using MessageHandler
    assistant_message = MessageHandler.create_ai_message(
        db,
        thread_id=thread_uuid,
        user_id=current_user.id,
        content=ai_response.content,
        ai_model=ai_response.model,
        prompt_tokens=ai_response.prompt_tokens,
        completion_tokens=ai_response.completion_tokens,
        total_tokens=ai_response.total_tokens,
        estimated_cost=float(ai_response.estimated_cost) if ai_response.estimated_cost else None,
        created_by=current_user.id,
    )
    
    # Refresh thread to get updated token totals (updated by MessageHandler)
    db.refresh(thread)
    
    # Broadcast to WebSocket connections
    await connection_manager.broadcast_to_thread(
        str(thread_uuid),
        {
            "type": "message",
            "user_message": {
                "id": str(user_message.id),
                "content": user_message.content,
                "role": user_message.role,
                "sender_type": user_message.sender_type,
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
            "timestamp": datetime.utcnow().isoformat(),
        },
    )
    
    return {
        "user_message": user_message,
        "assistant_message": assistant_message,
    }


@router.get("/stats")
def get_dashboard_stats(
    workshop_id: Optional[str] = Query(None),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Get dashboard statistics for the current user/workshop."""
    from sqlalchemy import func, and_
    from datetime import datetime, timedelta
    
    try:
        workshop_uuid = uuid.UUID(workshop_id) if workshop_id else None
    except (ValueError, TypeError):
        # If workshop_id is provided but invalid, return error. If None, continue.
        if workshop_id:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Invalid workshop_id",
            )
        workshop_uuid = None
    
    if workshop_uuid:
        # Ensure user is member of workshop
        workshops._ensure_workshop_member(db, current_user.id, workshop_uuid)
    
    # Get threads for the user/workshop
    query = db.query(ChatThread).filter(ChatThread.user_id == current_user.id)
    if workshop_uuid:
        query = query.filter(ChatThread.workshop_id == workshop_uuid)
    
    # Total consultations
    total_consultations = query.count()
    
    # Resolved count
    resolved_count = query.filter(ChatThread.is_resolved == True).count()
    
    # Pending count (active and not resolved)
    pending_count = query.filter(
        and_(ChatThread.is_resolved == False, ChatThread.is_archived == False)
    ).count()
    
    # Tokens used this month
    start_of_month = datetime.utcnow().replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    tokens_this_month = (
        db.query(func.sum(ChatThread.total_tokens))
        .filter(
            ChatThread.user_id == current_user.id,
            ChatThread.created_at >= start_of_month,
        )
        .scalar() or 0
    )
    
    if workshop_uuid:
        tokens_this_month = (
            db.query(func.sum(ChatThread.total_tokens))
            .filter(
                ChatThread.workshop_id == workshop_uuid,
                ChatThread.created_at >= start_of_month,
            )
            .scalar() or 0
        )
    
    # Recent activity (last 5 threads)
    recent_threads = (
        query.order_by(desc(ChatThread.created_at))
        .limit(5)
        .all()
    )
    
    recent_activity = [
        {
            "id": str(t.id),
            "license_plate": t.license_plate,
            "title": t.title or f"Consultation for {t.license_plate}",
            "status": t.status,
            "is_resolved": t.is_resolved,
            "created_at": t.created_at.isoformat() if t.created_at else None,
            "last_message_at": t.last_message_at.isoformat() if t.last_message_at else None,
        }
        for t in recent_threads
    ]
    
    return {
        "total_consultations": total_consultations,
        "tokens_used_this_month": int(tokens_this_month),
        "resolved_count": resolved_count,
        "pending_count": pending_count,
        "recent_activity": recent_activity,
    }

