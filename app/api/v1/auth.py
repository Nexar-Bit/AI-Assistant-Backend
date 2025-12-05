from datetime import timedelta

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from fastapi.security import OAuth2PasswordRequestForm
from jose import JWTError
from sqlalchemy.orm import Session

from app.api.dependencies import (
    enforce_login_attempt_limit,
    get_current_user,
    get_refresh_token_from_cookie,
    is_refresh_token_active,
    reset_login_attempts,
    revoke_refresh_token,
    store_refresh_token,
)
from app.core.config import settings
from app.core.database import get_db
from app.core.security import (
    create_access_token,
    create_refresh_token,
    decode_token,
    verify_password,
)
from app.models.user import User
from app.services.audit_service import log_auth_event
from app.workshops.crud import WorkshopCRUD


router = APIRouter(prefix="/auth", tags=["auth"])


def _set_refresh_cookie(response: Response, refresh_token: str) -> None:
    max_age = settings.REFRESH_TOKEN_EXPIRE_DAYS * 24 * 60 * 60
    # In development, allow insecure cookies (HTTP). In production, use secure=True (HTTPS)
    is_secure = settings.ENVIRONMENT.lower() not in ("development", "dev", "local")
    response.set_cookie(
        "refresh_token",
        refresh_token,
        httponly=True,
        secure=is_secure,
        samesite="lax",
        max_age=max_age,
    )


def _clear_refresh_cookie(response: Response) -> None:
    response.delete_cookie("refresh_token")


@router.post("/login")
def login(
    request: Request,
    response: Response,
    form_data: OAuth2PasswordRequestForm = Depends(),
    db: Session = Depends(get_db),
):
    enforce_login_attempt_limit(form_data.username)

    user = db.query(User).filter(User.username == form_data.username).first()
    if not user or not verify_password(form_data.password, user.password_hash):
        log_auth_event(
            db,
            user_id=str(user.id) if user else None,  # type: ignore[arg-type]
            action_type="AUTH_LOGIN",
            success=False,
            ip_address=request.client.host if request.client else None,
            user_agent=request.headers.get("user-agent"),
            details={"username": form_data.username},
        )
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect username or password",
        )

    if not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="User is inactive",
        )

    reset_login_attempts(form_data.username)

    access_token = create_access_token(subject=user.id)
    refresh_token = create_refresh_token(subject=user.id)

    # store refresh token jti in Redis for rotation
    refresh_payload = decode_token(refresh_token, expected_type="refresh")
    jti = refresh_payload["jti"]
    ttl_seconds = settings.REFRESH_TOKEN_EXPIRE_DAYS * 24 * 60 * 60
    store_refresh_token(str(user.id), jti, ttl_seconds)

    _set_refresh_cookie(response, refresh_token)

    log_auth_event(
        db,
        user_id=str(user.id),
        action_type="AUTH_LOGIN",
        success=True,
        ip_address=request.client.host if request.client else None,
        user_agent=request.headers.get("user-agent"),
        details={},
    )

    # Get user's workshops for multi-tenant support
    workshops = WorkshopCRUD.get_user_workshops(db, user.id)
    workshops_data = [
        {
            "id": str(w.id),
            "name": w.name,
            "slug": w.slug,
            "description": w.description,
            "role": "owner" if str(w.owner_id) == str(user.id) else "member",  # Simplified
        }
        for w in workshops
    ]

    return {
        "access_token": access_token,
        "refresh_token": refresh_token,
        "token_type": "bearer",
        "user": {
            "id": str(user.id),
            "username": user.username,
            "email": user.email,
            "role": user.role,
        },
        "workshops": workshops_data,  # Multi-tenant: user's available workshops
    }


@router.post("/refresh")
def refresh_token(
    request: Request,
    response: Response,
    refresh_token: str = Depends(get_refresh_token_from_cookie),
    db: Session = Depends(get_db),
):
    import logging
    logger = logging.getLogger("app.auth")
    
    # Log cookie presence for debugging
    cookies = request.cookies
    logger.debug(f"Refresh endpoint called. Cookies present: {list(cookies.keys())}")
    
    try:
        payload = decode_token(refresh_token, expected_type="refresh")
    except JWTError as e:
        logger.warning(f"Invalid refresh token: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid refresh token",
        )

    user_id: str | None = payload.get("sub")
    jti: str | None = payload.get("jti")
    if not user_id or not jti:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid refresh token payload",
        )

    if not is_refresh_token_active(user_id, jti):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Refresh token has been rotated or revoked",
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
    
    user = db.query(User).filter(User.id == user_uuid).first()
    if not user or not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User not found or inactive",
        )

    # rotate: revoke old and issue new
    revoke_refresh_token(user_id, jti)
    new_access = create_access_token(subject=user_id)
    new_refresh = create_refresh_token(subject=user_id)
    new_payload = decode_token(new_refresh, expected_type="refresh")
    new_jti = new_payload["jti"]
    ttl_seconds = settings.REFRESH_TOKEN_EXPIRE_DAYS * 24 * 60 * 60
    store_refresh_token(user_id, new_jti, ttl_seconds)

    _set_refresh_cookie(response, new_refresh)

    log_auth_event(
        db,
        user_id=user_id,
        action_type="AUTH_REFRESH",
        success=True,
        ip_address=request.client.host if request.client else None,
        user_agent=request.headers.get("user-agent"),
        details={},
    )

    return {
        "access_token": new_access,
        "refresh_token": new_refresh,
        "token_type": "bearer",
    }


@router.post("/logout")
def logout(
    request: Request,
    response: Response,
    refresh_token: str = Depends(get_refresh_token_from_cookie),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    try:
        payload = decode_token(refresh_token, expected_type="refresh")
        jti = payload.get("jti")
        if jti:
            revoke_refresh_token(str(current_user.id), jti)
    except JWTError:
        # ignore errors on logout
        pass

    _clear_refresh_cookie(response)

    log_auth_event(
        db,
        user_id=str(current_user.id),
        action_type="AUTH_LOGOUT",
        success=True,
        ip_address=request.client.host if request.client else None,
        user_agent=request.headers.get("user-agent"),
        details={},
    )

    return {"detail": "Logged out"}


