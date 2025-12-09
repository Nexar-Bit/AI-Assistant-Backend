import uuid
from datetime import datetime
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import func, and_
from sqlalchemy.orm import Session

from app.api.dependencies import require_roles, require_superuser, get_db
from app.models.user import User
from app.models.vehicle import Vehicle
from app.workshops.models import Workshop, WorkshopMember
from app.chat.models import ChatThread
from pydantic import BaseModel


router = APIRouter(prefix="/admin", tags=["admin"])


@router.get("/health")
def admin_health(current_user: User = Depends(require_roles(["admin"]))):
    return {"status": "admin-ok", "user": str(current_user.id)}


class WorkshopStatsResponse(BaseModel):
    """Statistics for a workshop."""
    id: str
    name: str
    description: Optional[str]
    member_count: int
    technician_count: int
    tokens_used: int
    tokens_limit: int
    active_consultations: int
    total_consultations: int
    vehicles_count: int
    last_activity: Optional[str]
    created_at: str


class TechnicianStatsResponse(BaseModel):
    """Statistics for a technician in a workshop."""
    user_id: str
    username: str
    email: str
    consultations_count: int
    tokens_used: int
    vehicles_created: int
    last_activity: Optional[str]


class WorkshopDetailResponse(BaseModel):
    """Detailed information for a workshop."""
    workshop: WorkshopStatsResponse
    technicians: List[TechnicianStatsResponse]


@router.get("/workshops/stats", response_model=List[WorkshopStatsResponse])
def get_workshops_stats(
    db: Session = Depends(get_db),
    current_user: User = Depends(require_superuser),
):
    """Get statistics for all workshops (superuser only)."""
    workshops = db.query(Workshop).filter(Workshop.is_deleted == False).all()
    
    stats_list = []
    for workshop in workshops:
        # Count members
        member_count = db.query(WorkshopMember).filter(
            WorkshopMember.workshop_id == workshop.id,
            WorkshopMember.is_deleted == False,
        ).count()
        
        # Count technicians
        technician_count = db.query(WorkshopMember).filter(
            WorkshopMember.workshop_id == workshop.id,
            WorkshopMember.role == "technician",
            WorkshopMember.is_deleted == False,
        ).count()
        
        # Count vehicles
        vehicles_count = db.query(Vehicle).filter(
            Vehicle.workshop_id == workshop.id,
            Vehicle.is_deleted == False,
        ).count()
        
        # Count consultations
        total_consultations = db.query(ChatThread).filter(
            ChatThread.workshop_id == workshop.id,
        ).count()
        
        active_consultations = db.query(ChatThread).filter(
            ChatThread.workshop_id == workshop.id,
            ChatThread.is_resolved == False,
            ChatThread.is_archived == False,
        ).count()
        
        # Calculate tokens used this month
        start_of_month = datetime.utcnow().replace(day=1, hour=0, minute=0, second=0, microsecond=0)
        tokens_used = (
            db.query(func.sum(ChatThread.total_tokens))
            .filter(
                ChatThread.workshop_id == workshop.id,
                ChatThread.created_at >= start_of_month,
            )
            .scalar() or 0
        )
        
        # Get last activity (most recent thread)
        last_thread = (
            db.query(ChatThread)
            .filter(ChatThread.workshop_id == workshop.id)
            .order_by(ChatThread.created_at.desc())
            .first()
        )
        last_activity = last_thread.created_at.isoformat() if last_thread else None
        
        stats_list.append(WorkshopStatsResponse(
            id=str(workshop.id),
            name=workshop.name,
            description=workshop.description,
            member_count=member_count,
            technician_count=technician_count,
            tokens_used=int(tokens_used),
            tokens_limit=workshop.monthly_token_limit or 0,
            active_consultations=active_consultations,
            total_consultations=total_consultations,
            vehicles_count=vehicles_count,
            last_activity=last_activity,
            created_at=workshop.created_at.isoformat(),
        ))
    
    return stats_list


@router.get("/workshops/{workshop_id}/detail", response_model=WorkshopDetailResponse)
def get_workshop_detail(
    workshop_id: uuid.UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_superuser),
):
    """Get detailed information for a workshop with technician breakdown (superuser only)."""
    workshop = db.query(Workshop).filter(
        Workshop.id == workshop_id,
        Workshop.is_deleted == False,
    ).first()
    
    if not workshop:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Workshop not found",
        )
    
    # Get workshop stats (same as above)
    member_count = db.query(WorkshopMember).filter(
        WorkshopMember.workshop_id == workshop.id,
        WorkshopMember.is_deleted == False,
    ).count()
    
    technician_count = db.query(WorkshopMember).filter(
        WorkshopMember.workshop_id == workshop.id,
        WorkshopMember.role == "technician",
        WorkshopMember.is_deleted == False,
    ).count()
    
    vehicles_count = db.query(Vehicle).filter(
        Vehicle.workshop_id == workshop.id,
        Vehicle.is_deleted == False,
    ).count()
    
    total_consultations = db.query(ChatThread).filter(
        ChatThread.workshop_id == workshop.id,
    ).count()
    
    active_consultations = db.query(ChatThread).filter(
        ChatThread.workshop_id == workshop.id,
        ChatThread.is_resolved == False,
        ChatThread.is_archived == False,
    ).count()
    
    start_of_month = datetime.utcnow().replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    tokens_used = (
        db.query(func.sum(ChatThread.total_tokens))
        .filter(
            ChatThread.workshop_id == workshop.id,
            ChatThread.created_at >= start_of_month,
        )
        .scalar() or 0
    )
    
    last_thread = (
        db.query(ChatThread)
        .filter(ChatThread.workshop_id == workshop.id)
        .order_by(ChatThread.created_at.desc())
        .first()
    )
    last_activity = last_thread.created_at.isoformat() if last_thread else None
    
    workshop_stats = WorkshopStatsResponse(
        id=str(workshop.id),
        name=workshop.name,
        description=workshop.description,
        member_count=member_count,
        technician_count=technician_count,
        tokens_used=int(tokens_used),
        tokens_limit=workshop.monthly_token_limit or 0,
        active_consultations=active_consultations,
        total_consultations=total_consultations,
        vehicles_count=vehicles_count,
        last_activity=last_activity,
        created_at=workshop.created_at.isoformat(),
    )
    
    # Get technician statistics
    technicians = db.query(WorkshopMember).filter(
        WorkshopMember.workshop_id == workshop.id,
        WorkshopMember.role == "technician",
        WorkshopMember.is_deleted == False,
    ).all()
    
    technician_stats = []
    for tech_member in technicians:
        user = db.query(User).filter(User.id == tech_member.user_id).first()
        if not user:
            continue
        
        # Count consultations by this technician
        consultations_count = db.query(ChatThread).filter(
            ChatThread.workshop_id == workshop.id,
            ChatThread.user_id == tech_member.user_id,
        ).count()
        
        # Count tokens used by this technician this month
        tech_tokens_used = (
            db.query(func.sum(ChatThread.total_tokens))
            .filter(
                ChatThread.workshop_id == workshop.id,
                ChatThread.user_id == tech_member.user_id,
                ChatThread.created_at >= start_of_month,
            )
            .scalar() or 0
        )
        
        # Count vehicles created by this technician
        vehicles_created = db.query(Vehicle).filter(
            Vehicle.workshop_id == workshop.id,
            Vehicle.created_by == tech_member.user_id,
            Vehicle.is_deleted == False,
        ).count()
        
        # Get last activity
        tech_last_thread = (
            db.query(ChatThread)
            .filter(
                ChatThread.workshop_id == workshop.id,
                ChatThread.user_id == tech_member.user_id,
            )
            .order_by(ChatThread.created_at.desc())
            .first()
        )
        tech_last_activity = tech_last_thread.created_at.isoformat() if tech_last_thread else None
        
        technician_stats.append(TechnicianStatsResponse(
            user_id=str(tech_member.user_id),
            username=user.username,
            email=user.email,
            consultations_count=consultations_count,
            tokens_used=int(tech_tokens_used),
            vehicles_created=vehicles_created,
            last_activity=tech_last_activity,
        ))
    
    return WorkshopDetailResponse(
        workshop=workshop_stats,
        technicians=technician_stats,
    )


