#!/usr/bin/env python3
"""Script to create users for every role combination."""

import sys
import uuid
from pathlib import Path

# Add parent directory to path so we can import app modules
sys.path.insert(0, str(Path(__file__).parent.parent))

from app.core.database import SessionLocal
from app.core.security import get_password_hash
from app.models.user import User
from app.workshops.crud import WorkshopCRUD, WorkshopMemberCRUD
from app.workshops.models import Workshop, WorkshopMember


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
            print(f"❌ Password validation failed: {e}")
            return None

        # Create user
        user = User(
            id=uuid.uuid4(),
            username=username,
            email=email,
            password_hash=password_hash,
            role=role,
            is_active=is_active,
            email_verified=True,
        )

        db.add(user)
        db.commit()
        db.refresh(user)

        print(f"✅ Created user: {user.username} ({user.email}) - Global Role: {user.role}")
        return user
    except Exception as e:
        db.rollback()
        print(f"❌ Error creating user {username}: {e}")
        return None
    finally:
        db.close()


def get_or_create_workshop(name: str = "Demo Workshop", slug: str = "demo-workshop") -> Workshop:
    """Get existing workshop or create a new one."""
    db = SessionLocal()
    try:
        # Try to find existing workshop
        workshop = WorkshopCRUD.get_by_slug(db, slug)
        if workshop:
            print(f"📦 Using existing workshop: {workshop.name} ({workshop.id})")
            return workshop
        
        # Create a demo admin user to be the owner
        owner = db.query(User).filter(User.role == "admin").first()
        if not owner:
            print("❌ No admin user found. Please create an admin user first.")
            sys.exit(1)
        
        # Create workshop
        workshop = WorkshopCRUD.create(
            db=db,
            name=name,
            slug=slug,
            owner_id=owner.id,
            description="Demo workshop for testing all roles",
            monthly_token_limit=100000,
        )
        
        print(f"✅ Created workshop: {workshop.name} ({workshop.id})")
        return workshop
    except Exception as e:
        db.rollback()
        print(f"❌ Error creating workshop: {e}")
        return None
    finally:
        db.close()


def add_user_to_workshop(user: User, workshop_id: uuid.UUID, role: str) -> bool:
    """Add user to workshop with specified role."""
    if not user:
        return False
    
    db = SessionLocal()
    try:
        # Check if already a member
        existing = WorkshopMemberCRUD.get_membership(db, workshop_id, user.id)
        if existing:
            if existing.role != role:
                existing.role = role
                existing.is_active = True
                db.add(existing)
                db.commit()
                print(f"   ✅ Updated workshop role: {role}")
            else:
                print(f"   ℹ️  Already has role: {role}")
            return True
        
        # Add member
        membership = WorkshopMemberCRUD.add_member(
            db,
            workshop_id=workshop_id,
            user_id=user.id,
            role=role,
        )
        
        print(f"   ✅ Added to workshop with role: {role}")
        return True
    except Exception as e:
        db.rollback()
        print(f"   ❌ Error adding to workshop: {e}")
        return False
    finally:
        db.close()


def main():
    """Create users for all role combinations."""
    print("=" * 60)
    print("Creating Users for All Role Combinations")
    print("=" * 60)
    print()
    
    # Default password for all demo users
    default_password = "DemoUser123!@"
    
    # Get or create workshop
    print("📦 Setting up workshop...")
    workshop = get_or_create_workshop()
    if not workshop:
        print("❌ Failed to get or create workshop")
        sys.exit(1)
    print()
    
    # Users to create: (username, email, global_role, workshop_role)
    users_to_create = [
        # Global Admin roles
        ("admin_global", "admin@demo.com", "admin", "owner"),  # Global admin as owner
        ("admin_workshop", "admin_workshop@demo.com", "admin", "admin"),  # Global admin as workshop admin
        ("admin_tech", "admin_tech@demo.com", "admin", "technician"),  # Global admin as technician
        ("admin_member", "admin_member@demo.com", "admin", "member"),  # Global admin as member
        ("admin_viewer", "admin_viewer@demo.com", "admin", "viewer"),  # Global admin as viewer
        
        # Global Technician roles
        ("tech_owner", "tech_owner@demo.com", "technician", "owner"),  # Technician as owner
        ("tech_admin", "tech_admin@demo.com", "technician", "admin"),  # Technician as admin
        ("tech_technician", "tech_technician@demo.com", "technician", "technician"),  # Technician as technician
        ("tech_member", "tech_member@demo.com", "technician", "member"),  # Technician as member
        ("tech_viewer", "tech_viewer@demo.com", "technician", "viewer"),  # Technician as viewer
        
        # Global Viewer roles
        ("viewer_owner", "viewer_owner@demo.com", "viewer", "owner"),  # Viewer as owner
        ("viewer_admin", "viewer_admin@demo.com", "viewer", "admin"),  # Viewer as admin
        ("viewer_technician", "viewer_technician@demo.com", "viewer", "technician"),  # Viewer as technician
        ("viewer_member", "viewer_member@demo.com", "viewer", "member"),  # Viewer as member
        ("viewer_viewer", "viewer_viewer@demo.com", "viewer", "viewer"),  # Viewer as viewer
    ]
    
    print("👥 Creating users...")
    print()
    
    created_users = []
    for username, email, global_role, workshop_role in users_to_create:
        print(f"Creating: {username}")
        user = create_user(
            username=username,
            email=email,
            password=default_password,
            role=global_role,
        )
        
        if user:
            # Add to workshop with specified role
            add_user_to_workshop(user, workshop.id, workshop_role)
            created_users.append((user, workshop_role))
        print()
    
    # Summary
    print("=" * 60)
    print("Summary")
    print("=" * 60)
    print(f"✅ Created/Updated {len(created_users)} users")
    print(f"📦 Workshop: {workshop.name} ({workshop.id})")
    print()
    print("All users have password: DemoUser123!@")
    print()
    print("User List:")
    print("-" * 60)
    for user, workshop_role in created_users:
        print(f"  • {user.username:20} | Global: {user.role:10} | Workshop: {workshop_role:10} | {user.email}")
    print()
    print("=" * 60)
    print("✅ All role users created successfully!")
    print("=" * 60)


if __name__ == "__main__":
    main()

