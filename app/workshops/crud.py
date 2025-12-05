"""CRUD operations for workshops and workshop members."""

import logging
import uuid
from typing import List, Optional

from sqlalchemy.orm import Session

from app.models.user import User
from .models import Workshop, WorkshopMember


logger = logging.getLogger("app.workshops.crud")


class WorkshopCRUD:
    """CRUD operations for workshops."""

    @staticmethod
    def get_by_id(db: Session, workshop_id: uuid.UUID) -> Optional[Workshop]:
        """Get workshop by ID."""
        return (
            db.query(Workshop)
            .filter(
                Workshop.id == workshop_id,
                Workshop.is_deleted.is_(False),
            )
            .first()
        )

    @staticmethod
    def get_by_slug(db: Session, slug: str) -> Optional[Workshop]:
        """Get workshop by slug."""
        return (
            db.query(Workshop)
            .filter(
                Workshop.slug == slug,
                Workshop.is_deleted.is_(False),
            )
            .first()
        )

    @staticmethod
    def get_user_workshops(db: Session, user_id: uuid.UUID) -> List[Workshop]:
        """Get all workshops where user is a member."""
        memberships = (
            db.query(WorkshopMember)
            .filter(
                WorkshopMember.user_id == user_id,
                WorkshopMember.is_active.is_(True),
                Workshop.is_active.is_(True),
                Workshop.is_deleted.is_(False),
            )
            .join(Workshop, WorkshopMember.workshop_id == Workshop.id)
            .all()
        )
        workshop_ids = [m.workshop_id for m in memberships]
        return db.query(Workshop).filter(Workshop.id.in_(workshop_ids)).all()

    @staticmethod
    def create(
        db: Session,
        name: str,
        slug: str,
        owner_id: uuid.UUID,
        description: Optional[str] = None,
        monthly_token_limit: int = 100000,
    ) -> Workshop:
        """Create a new workshop."""
        workshop = Workshop(
            name=name,
            slug=slug,
            description=description,
            owner_id=str(owner_id),
            monthly_token_limit=monthly_token_limit,
            created_by=str(owner_id),
        )
        db.add(workshop)
        db.flush()

        # Add owner as workshop member
        owner_membership = WorkshopMember(
            workshop_id=workshop.id,
            user_id=owner_id,
            role="owner",
            created_by=str(owner_id),
        )
        db.add(owner_membership)
        db.commit()
        db.refresh(workshop)
        return workshop

    @staticmethod
    def update(
        db: Session,
        workshop_id: uuid.UUID,
        **updates
    ) -> Optional[Workshop]:
        """Update workshop."""
        workshop = WorkshopCRUD.get_by_id(db, workshop_id)
        if not workshop:
            return None

        for key, value in updates.items():
            if hasattr(workshop, key) and value is not None:
                setattr(workshop, key, value)

        db.add(workshop)
        db.commit()
        db.refresh(workshop)
        return workshop

    @staticmethod
    def delete(db: Session, workshop_id: uuid.UUID, deleted_by: uuid.UUID) -> bool:
        """Soft delete workshop."""
        workshop = WorkshopCRUD.get_by_id(db, workshop_id)
        if not workshop:
            return False

        workshop.is_deleted = True
        workshop.deleted_by = str(deleted_by)
        db.add(workshop)
        db.commit()
        return True


class WorkshopMemberCRUD:
    """CRUD operations for workshop members."""

    @staticmethod
    def get_membership(
        db: Session,
        workshop_id: uuid.UUID,
        user_id: uuid.UUID,
    ) -> Optional[WorkshopMember]:
        """Get user's membership in a workshop."""
        return (
            db.query(WorkshopMember)
            .filter(
                WorkshopMember.workshop_id == workshop_id,
                WorkshopMember.user_id == user_id,
                WorkshopMember.is_deleted.is_(False),
            )
            .first()
        )

    @staticmethod
    def get_workshop_members(
        db: Session,
        workshop_id: uuid.UUID,
        active_only: bool = True,
    ) -> List[WorkshopMember]:
        """Get all members of a workshop."""
        query = (
            db.query(WorkshopMember)
            .filter(
                WorkshopMember.workshop_id == workshop_id,
                WorkshopMember.is_deleted.is_(False),
            )
        )
        if active_only:
            query = query.filter(WorkshopMember.is_active.is_(True))
        return query.all()

    @staticmethod
    def add_member(
        db: Session,
        workshop_id: uuid.UUID,
        user_id: uuid.UUID,
        role: str = "member",
        invited_by: Optional[uuid.UUID] = None,
        created_by: Optional[uuid.UUID] = None,
    ) -> WorkshopMember:
        """Add a user to a workshop."""
        membership = WorkshopMember(
            workshop_id=workshop_id,
            user_id=user_id,
            role=role,
            invited_by=invited_by,
            created_by=str(created_by) if created_by else str(user_id),
        )
        db.add(membership)
        db.commit()
        db.refresh(membership)
        return membership

    @staticmethod
    def update_role(
        db: Session,
        workshop_id: uuid.UUID,
        user_id: uuid.UUID,
        new_role: str,
        updated_by: uuid.UUID,
    ) -> Optional[WorkshopMember]:
        """Update member's role."""
        membership = WorkshopMemberCRUD.get_membership(db, workshop_id, user_id)
        if not membership:
            return None

        membership.role = new_role
        membership.updated_by = str(updated_by)
        db.add(membership)
        db.commit()
        db.refresh(membership)
        return membership

    @staticmethod
    def remove_member(
        db: Session,
        workshop_id: uuid.UUID,
        user_id: uuid.UUID,
        deleted_by: uuid.UUID,
    ) -> bool:
        """Remove a user from a workshop (soft delete)."""
        membership = WorkshopMemberCRUD.get_membership(db, workshop_id, user_id)
        if not membership:
            return False

        membership.is_deleted = True
        membership.deleted_by = str(deleted_by)
        db.add(membership)
        db.commit()
        return True

