from __future__ import annotations

from typing import Annotated, Callable, List

from fastapi import Cookie, Depends, HTTPException, Request, status
from fastapi.security import OAuth2PasswordBearer
from jose import JWTError
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.redis import get_redis_client, is_redis_available
from app.core.security import decode_token
from app.models.user import User


oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/v1/auth/login")


def get_current_user(
    token: Annotated[str, Depends(oauth2_scheme)],
    db: Session = Depends(get_db),
) -> User:
    try:
        payload = decode_token(token, expected_type="access")
    except JWTError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Could not validate credentials",
        )

    user_id: str | None = payload.get("sub")
    if user_id is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid token payload",
        )

    # Convert user_id string to UUID for database query
    import uuid as uuid_lib
    try:
        user_uuid = uuid_lib.UUID(user_id)
    except (ValueError, TypeError):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid user ID format",
        )

    user: User | None = db.query(User).filter(User.id == user_uuid, User.is_active.is_(True)).first()
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User not found or inactive",
        )
    return user


def require_roles(allowed_roles: List[str]) -> Callable[[User], User]:
    def dependency(current_user: Annotated[User, Depends(get_current_user)]) -> User:
        if current_user.role not in allowed_roles:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Insufficient permissions",
            )
        return current_user

    return dependency


def require_superuser(current_user: Annotated[User, Depends(get_current_user)]) -> User:
    """Dependency to require platform-level superuser role.

    For compatibility, allow both global 'owner' and legacy 'admin' users.
    Frontend already restricts /admin UI to 'owner'; this just prevents 403s
    while old 'admin' records still exist in the database.
    """
    if current_user.role not in ("owner", "admin"):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only platform superusers can perform this action",
        )
    return current_user


def get_refresh_token_from_cookie(
    request: Request,
    refresh_token: str | None = Cookie(default=None, alias="refresh_token"),
) -> str:
    import logging
    logger = logging.getLogger("app.dependencies")
    
    if not refresh_token:
        # Log all cookies for debugging
        all_cookies = request.cookies
        logger.warning(f"Refresh token cookie missing. Available cookies: {list(all_cookies.keys())}")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing refresh token. Please log in again.",
        )
    return refresh_token


def enforce_login_attempt_limit(username: str) -> None:
    """Limit login attempts: 5 attempts over rolling 15 minutes."""
    if not is_redis_available():
        # Skip rate limiting if Redis is not available
        return
    r = get_redis_client()
    if r is None:
        return
    key = f"auth:login_attempts:{username}"
    attempts = r.incr(key)
    if attempts == 1:
        r.expire(key, 15 * 60)
    if attempts > 5:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Too many login attempts. Try again in 15 minutes.",
        )


def reset_login_attempts(username: str) -> None:
    if not is_redis_available():
        return
    r = get_redis_client()
    if r is None:
        return
    r.delete(f"auth:login_attempts:{username}")


def store_refresh_token(user_id: str, jti: str, ttl_seconds: int) -> None:
    """Store refresh token in Redis. No-op if Redis is unavailable."""
    if not is_redis_available():
        return
    r = get_redis_client()
    if r is None:
        return
    key = f"auth:refresh:{user_id}:{jti}"
    r.set(key, "1", ex=ttl_seconds)


def revoke_refresh_token(user_id: str, jti: str) -> None:
    """Revoke refresh token in Redis. No-op if Redis is unavailable."""
    if not is_redis_available():
        return
    r = get_redis_client()
    if r is None:
        return
    key = f"auth:refresh:{user_id}:{jti}"
    r.delete(key)


def is_refresh_token_active(user_id: str, jti: str) -> bool:
    """Check if refresh token is active. Returns True if Redis is unavailable (allow all)."""
    if not is_redis_available():
        return True  # Allow all if Redis is not available
    r = get_redis_client()
    if r is None:
        return True
    key = f"auth:refresh:{user_id}:{jti}"
    return r.exists(key) == 1


