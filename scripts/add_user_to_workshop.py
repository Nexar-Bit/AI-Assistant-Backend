#!/usr/bin/env python3
"""Script to add a user to a workshop."""

import sys
import uuid
from pathlib import Path

# Add parent directory to path so we can import app modules
sys.path.insert(0, str(Path(__file__).parent.parent))

from app.core.database import SessionLocal
from app.models.user import User
from app.workshops.crud import WorkshopMemberCRUD, WorkshopCRUD
from app.workshops.models import Workshop


def add_user_to_workshop(
    username_or_email: str,
    workshop_id: str,
    role: str = "member",
):
    """Add a user to a workshop."""
    db = SessionLocal()
    try:
        # Parse workshop ID
        try:
            workshop_uuid = uuid.UUID(workshop_id)
        except ValueError:
            print(f"❌ Invalid workshop ID: {workshop_id}")
            sys.exit(1)
        
        # Verify workshop exists
        workshop = db.query(Workshop).filter(Workshop.id == workshop_uuid).first()
        if not workshop:
            print(f"❌ Workshop not found: {workshop_id}")
            sys.exit(1)
        
        print(f"📦 Workshop: {workshop.name} ({workshop.slug})")
        
        # Find user by username or email
        user = db.query(User).filter(
            (User.username == username_or_email) | (User.email == username_or_email)
        ).first()
        
        if not user:
            print(f"❌ User not found: {username_or_email}")
            sys.exit(1)
        
        print(f"👤 User: {user.username} ({user.email})")
        
        # Check if user is already a member
        existing = WorkshopMemberCRUD.get_membership(db, workshop_uuid, user.id)
        if existing:
            if existing.is_active:
                print(f"⚠️  User is already a member with role: {existing.role}")
                if existing.role != role:
                    print(f"   Updating role from {existing.role} to {role}...")
                    existing.role = role
                    db.add(existing)
                    db.commit()
                    print(f"✅ Role updated successfully!")
                else:
                    print(f"   Role is already {role}")
            else:
                print(f"⚠️  User has inactive membership. Activating...")
                existing.is_active = True
                existing.role = role
                db.add(existing)
                db.commit()
                print(f"✅ Membership activated with role: {role}")
            return existing
        
        # Add member
        if role not in ["owner", "admin", "technician", "member", "viewer"]:
            print(f"❌ Invalid role: {role}. Must be: owner, admin, technician, member, or viewer")
            sys.exit(1)
        
        membership = WorkshopMemberCRUD.add_member(
            db,
            workshop_id=workshop_uuid,
            user_id=user.id,
            role=role,
        )
        
        print(f"✅ User added to workshop successfully!")
        print(f"   Role: {membership.role}")
        print(f"   Active: {membership.is_active}")
        
        return membership
    except Exception as e:
        db.rollback()
        print(f"❌ Error adding user to workshop: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
    finally:
        db.close()


def list_workshop_members(workshop_id: str):
    """List all members of a workshop."""
    db = SessionLocal()
    try:
        try:
            workshop_uuid = uuid.UUID(workshop_id)
        except ValueError:
            print(f"❌ Invalid workshop ID: {workshop_id}")
            sys.exit(1)
        
        workshop = db.query(Workshop).filter(Workshop.id == workshop_uuid).first()
        if not workshop:
            print(f"❌ Workshop not found: {workshop_id}")
            sys.exit(1)
        
        members = WorkshopMemberCRUD.get_workshop_members(db, workshop_uuid, active_only=True)
        
        print(f"\n📦 Workshop: {workshop.name} ({workshop.slug})")
        print(f"👥 Members ({len(members)}):\n")
        
        for member in members:
            user = db.query(User).filter(User.id == member.user_id).first()
            if user:
                print(f"   • {user.username} ({user.email}) - Role: {member.role} - Active: {member.is_active}")
        
        return members
    except Exception as e:
        print(f"❌ Error listing members: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
    finally:
        db.close()


def main():
    """Main entry point for the script."""
    if len(sys.argv) < 3:
        print("Usage:")
        print("  Add user to workshop:")
        print("    python add_user_to_workshop.py <username_or_email> <workshop_id> [role]")
        print("  List workshop members:")
        print("    python add_user_to_workshop.py --list <workshop_id>")
        print("\nExamples:")
        print("  python add_user_to_workshop.py tech2 94d6ec7f-83d9-4c79-8519-786748fecaec technician")
        print("  python add_user_to_workshop.py viewer1@example.com 94d6ec7f-83d9-4c79-8519-786748fecaec viewer")
        print("  python add_user_to_workshop.py --list 94d6ec7f-83d9-4c79-8519-786748fecaec")
        print("\nRoles: owner, admin, technician, member, viewer")
        sys.exit(1)
    
    if sys.argv[1] == "--list":
        workshop_id = sys.argv[2]
        list_workshop_members(workshop_id)
    else:
        username_or_email = sys.argv[1]
        workshop_id = sys.argv[2]
        role = sys.argv[3] if len(sys.argv) > 3 else "member"
        add_user_to_workshop(username_or_email, workshop_id, role)


if __name__ == "__main__":
    main()

