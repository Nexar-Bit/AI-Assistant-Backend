"""Chat session management."""

import logging
import uuid
from datetime import datetime
from typing import List, Optional

from sqlalchemy import desc
from sqlalchemy.orm import Session

from app.models.vehicle import Vehicle
from .models import ChatThread


logger = logging.getLogger("app.chat.sessions")


class ChatSessionManager:
    """Manages chat session lifecycle."""

    @staticmethod
    def create_session(
        db: Session,
        workshop_id: uuid.UUID,
        user_id: uuid.UUID,
        license_plate: str,
        vehicle_id: Optional[uuid.UUID] = None,
        vehicle_km: Optional[int] = None,
        error_codes: Optional[str] = None,
        vehicle_context: Optional[str] = None,
        created_by: Optional[uuid.UUID] = None,
    ) -> ChatThread:
        """Create a new chat session."""
        # Get or create vehicle
        vehicle = None
        if vehicle_id:
            vehicle = db.query(Vehicle).filter(Vehicle.id == vehicle_id).first()
        
        if not vehicle:
            vehicle = (
                db.query(Vehicle)
                .filter(Vehicle.license_plate == license_plate)
                .first()
            )
        
        # Build vehicle context string
        vehicle_context_str = ""
        if vehicle:
            vehicle_context_str = (
                f"License Plate: {vehicle.license_plate}\n"
                f"Make: {vehicle.make or 'N/A'}\n"
                f"Model: {vehicle.model or 'N/A'}\n"
                f"Year: {vehicle.year or 'N/A'}\n"
                f"VIN: {vehicle.vin or 'N/A'}\n"
                f"Current KM: {vehicle.current_km or 'N/A'}\n"
                f"Last Service KM: {vehicle.last_service_km or 'N/A'}\n"
                f"Last Service Date: {vehicle.last_service_date.isoformat() if vehicle.last_service_date else 'N/A'}\n"
                f"Engine Type: {vehicle.engine_type or 'N/A'}\n"
                f"Fuel Type: {vehicle.fuel_type or 'N/A'}"
            )
        
        thread = ChatThread(
            workshop_id=workshop_id,
            user_id=user_id,
            vehicle_id=vehicle.id if vehicle else None,
            license_plate=license_plate,
            vehicle_km=vehicle_km,
            error_codes=error_codes,
            vehicle_context=vehicle_context_str or vehicle_context,
            created_by=str(created_by) if created_by else str(user_id),
            last_message_at=datetime.utcnow(),
        )
        
        db.add(thread)
        db.commit()
        db.refresh(thread)
        
        logger.info(
            "Chat session created: thread_id=%s, workshop_id=%s, user_id=%s",
            thread.id,
            workshop_id,
            user_id,
        )
        
        return thread

    @staticmethod
    def get_session(
        db: Session,
        thread_id: uuid.UUID,
        user_id: Optional[uuid.UUID] = None,
    ) -> Optional[ChatThread]:
        """Get a chat session by ID."""
        query = db.query(ChatThread).filter(
            ChatThread.id == thread_id,
            ChatThread.is_deleted.is_(False),
        )
        
        if user_id:
            query = query.filter(ChatThread.user_id == user_id)
        
        return query.first()

    @staticmethod
    def list_sessions(
        db: Session,
        workshop_id: Optional[uuid.UUID] = None,
        user_id: Optional[uuid.UUID] = None,
        status: Optional[str] = None,
        license_plate: Optional[str] = None,
        is_resolved: Optional[bool] = None,
        is_archived: Optional[bool] = None,
        limit: int = 50,
        offset: int = 0,
    ) -> List[ChatThread]:
        """List chat sessions with optional filters."""
        query = db.query(ChatThread).filter(ChatThread.is_deleted.is_(False))
        
        if workshop_id:
            query = query.filter(ChatThread.workshop_id == workshop_id)
        
        if user_id:
            query = query.filter(ChatThread.user_id == user_id)
        
        if status == "active":
            query = query.filter(
                ChatThread.is_resolved.is_(False),
                ChatThread.is_archived.is_(False),
            )
        elif status == "resolved":
            query = query.filter(ChatThread.is_resolved.is_(True))
        elif status == "archived":
            query = query.filter(ChatThread.is_archived.is_(True))
        
        # Support direct boolean filters
        if is_resolved is not None:
            query = query.filter(ChatThread.is_resolved.is_(is_resolved))
        
        if is_archived is not None:
            query = query.filter(ChatThread.is_archived.is_(is_archived))
        
        if license_plate:
            query = query.filter(ChatThread.license_plate.ilike(f"%{license_plate}%"))
        
        return query.order_by(desc(ChatThread.last_message_at)).limit(limit).offset(offset).all()

    @staticmethod
    def update_session(
        db: Session,
        thread_id: uuid.UUID,
        **updates
    ) -> Optional[ChatThread]:
        """Update session metadata."""
        thread = ChatSessionManager.get_session(db, thread_id)
        if not thread:
            return None
        
        for key, value in updates.items():
            if hasattr(thread, key) and value is not None:
                setattr(thread, key, value)
        
        db.add(thread)
        db.commit()
        db.refresh(thread)
        return thread

    @staticmethod
    def archive_session(
        db: Session,
        thread_id: uuid.UUID,
        archived_by: uuid.UUID,
    ) -> bool:
        """Archive a chat session."""
        thread = ChatSessionManager.get_session(db, thread_id)
        if not thread:
            return False
        
        thread.is_archived = True
        thread.status = "archived"
        thread.updated_by = str(archived_by)
        db.add(thread)
        db.commit()
        return True

    @staticmethod
    def resolve_session(
        db: Session,
        thread_id: uuid.UUID,
        resolved_by: uuid.UUID,
    ) -> bool:
        """Mark session as resolved."""
        thread = ChatSessionManager.get_session(db, thread_id)
        if not thread:
            return False
        
        thread.is_resolved = True
        thread.status = "completed"
        thread.updated_by = str(resolved_by)
        db.add(thread)
        db.commit()
        return True

