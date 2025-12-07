"""Message handling for chat system."""

import logging
import uuid
from datetime import datetime
from typing import List, Optional

from sqlalchemy.orm import Session

from .models import ChatMessage, ChatThread


logger = logging.getLogger("app.chat.messages")


class MessageHandler:
    """Handles message creation and retrieval."""

    @staticmethod
    def create_message(
        db: Session,
        thread_id: uuid.UUID,
        user_id: uuid.UUID,
        content: str,
        role: str = "user",
        sender_type: str = "technician",
        attachments: Optional[dict] = None,
        is_markdown: bool = True,
        created_by: Optional[uuid.UUID] = None,
    ) -> ChatMessage:
        """Create a new message in a thread."""
        # Get next sequence number
        existing_messages = (
            db.query(ChatMessage)
            .filter(
                ChatMessage.thread_id == thread_id,
                ChatMessage.is_deleted.is_(False),
            )
            .order_by(ChatMessage.sequence_number)
            .all()
        )
        
        next_sequence = max([m.sequence_number for m in existing_messages], default=0) + 1
        
        message = ChatMessage(
            thread_id=thread_id,
            user_id=user_id,
            role=role,
            sender_type=sender_type,
            content=content,
            is_markdown=is_markdown,
            attachments=attachments or {},
            sequence_number=next_sequence,
            created_by=str(created_by) if created_by else str(user_id),
        )
        
        db.add(message)
        db.flush()
        
        # Update thread's last_message_at
        thread = db.query(ChatThread).filter(ChatThread.id == thread_id).first()
        if thread:
            thread.last_message_at = datetime.utcnow()
            if not thread.title and role == "user":
                thread.title = content[:200]
            db.add(thread)
        
        db.commit()
        db.refresh(message)
        
        logger.info(
            "Message created: message_id=%s, thread_id=%s, role=%s",
            message.id,
            thread_id,
            role,
        )
        
        return message

    @staticmethod
    def create_ai_message(
        db: Session,
        thread_id: uuid.UUID,
        user_id: uuid.UUID,
        content: str,
        ai_model: str,
        prompt_tokens: int,
        completion_tokens: int,
        total_tokens: int,
        estimated_cost: Optional[float] = None,
        created_by: Optional[uuid.UUID] = None,
    ) -> ChatMessage:
        """Create an AI assistant message."""
        # Get next sequence number
        existing_messages = (
            db.query(ChatMessage)
            .filter(
                ChatMessage.thread_id == thread_id,
                ChatMessage.is_deleted.is_(False),
            )
            .order_by(ChatMessage.sequence_number)
            .all()
        )
        
        next_sequence = max([m.sequence_number for m in existing_messages], default=0) + 1
        
        message = ChatMessage(
            thread_id=thread_id,
            user_id=user_id,
            role="assistant",
            sender_type="ai",
            content=content,
            is_markdown=True,
            ai_model_used=ai_model,
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
            total_tokens=total_tokens,
            estimated_cost=estimated_cost,
            sequence_number=next_sequence,
            created_by=str(created_by) if created_by else str(user_id),
        )
        
        db.add(message)
        
        # Update thread token totals
        from decimal import Decimal
        
        thread = db.query(ChatThread).filter(ChatThread.id == thread_id).first()
        if thread:
            thread.total_prompt_tokens += prompt_tokens
            thread.total_completion_tokens += completion_tokens
            thread.total_tokens += total_tokens
            if thread.estimated_cost is None:
                thread.estimated_cost = Decimal('0.0')
            if estimated_cost is not None:
                thread.estimated_cost += Decimal(str(estimated_cost))
            thread.last_message_at = datetime.utcnow()
            db.add(thread)
        
        db.commit()
        db.refresh(message)
        
        logger.info(
            "AI message created: message_id=%s, thread_id=%s, tokens=%d",
            message.id,
            thread_id,
            total_tokens,
        )
        
        return message

    @staticmethod
    def get_thread_messages(
        db: Session,
        thread_id: uuid.UUID,
        limit: Optional[int] = None,
    ) -> List[ChatMessage]:
        """Get all messages for a thread."""
        query = (
            db.query(ChatMessage)
            .filter(
                ChatMessage.thread_id == thread_id,
                ChatMessage.is_deleted.is_(False),
            )
            .order_by(ChatMessage.sequence_number)
        )
        
        if limit:
            query = query.limit(limit)
        
        return query.all()

    @staticmethod
    def edit_message(
        db: Session,
        message_id: uuid.UUID,
        new_content: str,
        updated_by: uuid.UUID,
    ) -> Optional[ChatMessage]:
        """Edit a message."""
        message = (
            db.query(ChatMessage)
            .filter(
                ChatMessage.id == message_id,
                ChatMessage.is_deleted.is_(False),
            )
            .first()
        )
        
        if not message:
            return None
        
        message.content = new_content
        message.is_edited = True
        message.edited_at = datetime.utcnow()
        message.updated_by = str(updated_by)
        
        db.add(message)
        db.commit()
        db.refresh(message)
        
        return message

