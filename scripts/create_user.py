#!/usr/bin/env python3
"""Script to create users in the database."""

import sys
import uuid
from pathlib import Path

# Add parent directory to path so we can import app modules
sys.path.insert(0, str(Path(__file__).parent.parent))

from app.core.database import SessionLocal
from app.core.security import get_password_hash
from app.models.user import User


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
            print(f"❌ User with username '{username}' or email '{email}' already exists!")
            sys.exit(1)

        # Hash password
        try:
            password_hash = get_password_hash(password)
        except ValueError as e:
            print(f"❌ Password validation failed: {e}")
            sys.exit(1)

        # Create user (with email verified for script-created users)
        user = User(
            id=uuid.uuid4(),
            username=username,
            email=email,
            password_hash=password_hash,
            role=role,
            is_active=is_active,
            email_verified=True,  # Script-created users are pre-verified
        )

        db.add(user)
        db.commit()
        db.refresh(user)

        print(f"✅ User created successfully!")
        print(f"   Username: {user.username}")
        print(f"   Email: {user.email}")
        print(f"   Role: {user.role}")
        print(f"   Active: {user.is_active}")
        print(f"\n💡 Note: Token limits are managed at the workshop level.")
        print(f"   Add this user to a workshop to grant access.")

        return user
    except Exception as e:
        db.rollback()
        print(f"❌ Error creating user: {e}")
        sys.exit(1)
    finally:
        db.close()


def main():
    """Main entry point for the script."""
    if len(sys.argv) < 4:
        print("Usage: python create_user.py <username> <email> <password> [role]")
        print("\nExample:")
        print("  python create_user.py admin admin@example.com Admin1234!@ admin")
        print("  python create_user.py tech1 tech1@example.com Tech1234!@ technician")
        print("\nRoles: admin, technician, viewer")
        print("Password must be at least 12 chars with upper, lower, digit, and special char.")
        sys.exit(1)

    username = sys.argv[1]
    email = sys.argv[2]
    password = sys.argv[3]
    role = sys.argv[4] if len(sys.argv) > 4 else "technician"

    if role not in ["admin", "technician", "viewer"]:
        print(f"❌ Invalid role '{role}'. Must be: admin, technician, viewer")
        sys.exit(1)

    create_user(
        username=username,
        email=email,
        password=password,
        role=role,
    )


if __name__ == "__main__":
    main()

