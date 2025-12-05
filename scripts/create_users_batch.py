#!/usr/bin/env python3
"""Batch script to create multiple users and optionally assign them to workshops."""

import sys
import uuid
from pathlib import Path

# Add parent directory to path so we can import app modules
sys.path.insert(0, str(Path(__file__).parent.parent))

from app.core.database import SessionLocal
from app.core.security import get_password_hash
from app.models.user import User
from app.workshops.crud import WorkshopCRUD, WorkshopMemberCRUD
from app.workshops.models import Workshop


def create_user(
    username: str,
    email: str,
    password: str,
    role: str = "technician",
    is_active: bool = True,
) -> User:
    """Create a new user in the database."""
    db = SessionLocal()
    try:
        # Check if user already exists
        existing = db.query(User).filter(
            (User.username == username) | (User.email == email)
        ).first()
        if existing:
            print(f"⚠️  User '{username}' already exists, skipping...")
            return existing

        # Hash password
        try:
            password_hash = get_password_hash(password)
        except ValueError as e:
            print(f"❌ Password validation failed for {username}: {e}")
            return None

        # Create user
        user = User(
            id=uuid.uuid4(),
            username=username,
            email=email,
            password_hash=password_hash,
            role=role,
            is_active=is_active,
        )

        db.add(user)
        db.commit()
        db.refresh(user)

        print(f"✅ User created: {user.username} ({user.email}) - Role: {user.role}")
        return user
    except Exception as e:
        db.rollback()
        print(f"❌ Error creating user {username}: {e}")
        return None
    finally:
        db.close()


def create_workshop(name: str, slug: str, owner_id: uuid.UUID, monthly_token_limit: int = 100000) -> Workshop:
    """Create a new workshop."""
    db = SessionLocal()
    try:
        # Check if workshop already exists
        existing = WorkshopCRUD.get_by_slug(db, slug)
        if existing:
            print(f"⚠️  Workshop '{name}' already exists, skipping...")
            return existing

        workshop = WorkshopCRUD.create(
            db,
            name=name,
            slug=slug,
            owner_id=owner_id,
            description=f"Workshop: {name}",
            monthly_token_limit=monthly_token_limit,
        )

        print(f"✅ Workshop created: {workshop.name} (slug: {workshop.slug})")
        return workshop
    except Exception as e:
        db.rollback()
        print(f"❌ Error creating workshop {name}: {e}")
        return None
    finally:
        db.close()


def add_user_to_workshop(user_id: uuid.UUID, workshop_id: uuid.UUID, role: str = "technician"):
    """Add a user to a workshop."""
    db = SessionLocal()
    try:
        # Check if membership already exists
        existing = WorkshopMemberCRUD.get_membership(db, workshop_id, user_id)
        if existing:
            if existing.role != role:
                # Update role if different
                existing.role = role
                existing.is_active = True
                db.add(existing)
                db.commit()
                print(f"✅ Updated user membership role to: {role}")
            else:
                print(f"⚠️  User already a member with role: {role}")
            return existing

        membership = WorkshopMemberCRUD.add_member(
            db,
            workshop_id=workshop_id,
            user_id=user_id,
            role=role,
        )
        print(f"✅ Added user to workshop with role: {role}")
        return membership
    except Exception as e:
        db.rollback()
        # Check if it's a duplicate key error (membership already exists)
        if "duplicate key" in str(e).lower() or "unique constraint" in str(e).lower():
            print(f"⚠️  User already a member of this workshop")
            return None
        print(f"❌ Error adding user to workshop: {e}")
        return None
    finally:
        db.close()


def main():
    """Create default users and workshop for testing."""
    print("🚀 Creating default users and workshop...\n")

    # Create admin user
    admin = create_user(
        username="admin",
        email="admin@example.com",
        password="Admin1234!@#$",
        role="admin",
    )

    if not admin:
        print("❌ Failed to create admin user")
        sys.exit(1)

    # Create technician users
    technician1 = create_user(
        username="tech1",
        email="tech1@example.com",
        password="Tech1234!@#$",
        role="technician",
    )

    technician2 = create_user(
        username="tech2",
        email="tech2@example.com",
        password="Tech1234!@#$",
        role="technician",
    )

    # Create viewer user
    viewer = create_user(
        username="viewer1",
        email="viewer1@example.com",
        password="Viewer1234!@#$",
        role="viewer",
    )

    # Create a default workshop
    print("\n📦 Creating default workshop...")
    workshop = create_workshop(
        name="Main Workshop",
        slug="main-workshop",
        owner_id=admin.id,
        monthly_token_limit=100000,
    )

    if workshop:
        # Add users to workshop
        print("\n👥 Adding users to workshop...")
        add_user_to_workshop(admin.id, workshop.id, role="owner")
        if technician1:
            add_user_to_workshop(technician1.id, workshop.id, role="technician")
        if technician2:
            add_user_to_workshop(technician2.id, workshop.id, role="technician")
        if viewer:
            add_user_to_workshop(viewer.id, workshop.id, role="viewer")

    print("\n✅ Setup complete!")
    print("\n📋 Created Users:")
    print(f"   Admin:     admin / Admin1234!@#$")
    print(f"   Tech 1:    tech1 / Tech1234!@#$")
    print(f"   Tech 2:    tech2 / Tech1234!@#$")
    print(f"   Viewer:    viewer1 / Viewer1234!@#$")
    print(f"\n🏭 Workshop: Main Workshop (main-workshop)")


if __name__ == "__main__":
    main()

