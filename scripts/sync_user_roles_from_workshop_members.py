#!/usr/bin/env python3
"""Sync global user roles from workshop_members roles.

Usage (from backend directory):
    python scripts/sync_user_roles_from_workshop_members.py

Logic:
    - For each user, look at all their workshop memberships.
    - Compute a "highest" role based on the following priority:
          owner > admin > technician > viewer > member
    - If the computed role differs from user.role, update user.role.

This is a one-time data fix to align the users table with workshop_members.
"""

import sys
from pathlib import Path

# Add parent directory to path so we can import app modules
sys.path.insert(0, str(Path(__file__).parent.parent))

from app.core.database import SessionLocal  # type: ignore
from app.models.user import User  # type: ignore
from app.workshops.models import WorkshopMember  # type: ignore


ROLE_PRIORITY = {
    "owner": 5,
    "admin": 4,
    "technician": 3,
    "viewer": 2,
    "member": 1,
}


def compute_highest_role(roles: list[str]) -> str | None:
    """Return the highest-priority role from a list of roles."""
    best_role = None
    best_priority = -1
    for r in roles:
        pr = ROLE_PRIORITY.get(r, 0)
        if pr > best_priority:
            best_priority = pr
            best_role = r
    return best_role


def sync_user_roles() -> None:
    db = SessionLocal()
    try:
        # Build map: user_id -> list of membership roles
        memberships = db.query(WorkshopMember).all()
        roles_by_user: dict[str, list[str]] = {}
        for m in memberships:
            user_id = str(m.user_id)
            roles_by_user.setdefault(user_id, []).append(m.role)

        print(f"Found memberships for {len(roles_by_user)} users.")

        updated = 0
        total_users = db.query(User).count()
        print(f"Total users: {total_users}")

        for user in db.query(User).all():
            key = str(user.id)
            member_roles = roles_by_user.get(key)
            if not member_roles:
                # No workshop memberships; skip
                continue

            highest = compute_highest_role(member_roles)
            if not highest:
                continue

            if user.role != highest:
                print(f"Updating user {user.username} ({user.id}) role {user.role!r} -> {highest!r}")
                user.role = highest
                db.add(user)
                updated += 1

        if updated:
            db.commit()
        print(f"Done. Updated {updated} users.")
    except Exception as e:
        db.rollback()
        print(f"❌ Error syncing user roles: {e}")
        import traceback

        traceback.print_exc()
        sys.exit(1)
    finally:
        db.close()


def main() -> None:
    sync_user_roles()


if __name__ == "__main__":
    main()


