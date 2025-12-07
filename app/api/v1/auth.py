from datetime import timedelta, datetime, timezone
import uuid

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from fastapi.security import OAuth2PasswordRequestForm
from jose import JWTError
from sqlalchemy.orm import Session
from pydantic import BaseModel, EmailStr, field_validator

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
    create_token,
    decode_token,
    verify_password,
    get_password_hash,
)
from app.models.user import User
from app.services.audit_service import log_auth_event
from app.services.email_service import email_service
from app.workshops.crud import WorkshopCRUD


router = APIRouter(prefix="/auth", tags=["auth"])


# Pydantic models for registration
class RegisterRequest(BaseModel):
    username: str
    email: EmailStr
    password: str

    @field_validator("username")
    @classmethod
    def validate_username(cls, v: str) -> str:
        if len(v) < 3:
            raise ValueError("Username must be at least 3 characters long")
        if len(v) > 50:
            raise ValueError("Username must be less than 50 characters")
        if not v.isalnum() and "_" not in v and "-" not in v:
            raise ValueError("Username can only contain letters, numbers, underscores, and hyphens")
        return v

    @field_validator("password")
    @classmethod
    def validate_password(cls, v: str) -> str:
        if len(v) < 12:
            raise ValueError("Password must be at least 12 characters long")
        return v


class VerifyEmailRequest(BaseModel):
    token: str


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
        # Log failed login attempt
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
    
    # Check if email is verified
    if not user.email_verified:
        log_auth_event(
            db,
            user_id=str(user.id),
            action_type="AUTH_LOGIN",
            success=False,
            ip_address=request.client.host if request.client else None,
            user_agent=request.headers.get("user-agent"),
            details={"username": form_data.username, "reason": "email_not_verified"},
        )
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Please verify your email address before logging in. Check your inbox for the verification link.",
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


@router.post("/register", status_code=status.HTTP_201_CREATED)
def register(
    request: Request,
    register_data: RegisterRequest,
    db: Session = Depends(get_db),
):
    """Register a new user account."""
    # Check if user already exists
    existing_user = db.query(User).filter(
        (User.username == register_data.username) | (User.email == register_data.email)
    ).first()
    
    if existing_user:
        if existing_user.username == register_data.username:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Username already taken",
            )
        if existing_user.email == register_data.email:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Email already registered",
            )
    
    # Hash password
    try:
        password_hash = get_password_hash(register_data.password)
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
        )
    
    # Generate email verification token
    verification_token = uuid.uuid4().hex
    verification_expires = datetime.now(timezone.utc) + timedelta(hours=24)
    
    # Create user (inactive until email is verified)
    user = User(
        id=uuid.uuid4(),
        username=register_data.username,
        email=register_data.email,
        password_hash=password_hash,
        role="technician",  # Default role
        is_active=False,  # Inactive until email verified
        email_verified=False,
        email_verification_token=verification_token,
        email_verification_expires_at=verification_expires,
    )
    
    db.add(user)
    db.commit()
    db.refresh(user)
    
    # Send verification email
    if email_service.is_available():
        email_sent = email_service.send_verification_email(
            to_email=register_data.email,
            verification_token=verification_token,
            username=register_data.username,
        )
        if not email_sent:
            logger.warning("Failed to send verification email to %s", register_data.email)
    else:
        logger.warning("Email service not configured. Verification email not sent to %s", register_data.email)
    
    # Log registration event
    log_auth_event(
        db,
        user_id=str(user.id),
        action_type="AUTH_REGISTER",
        success=True,
        ip_address=request.client.host if request.client else None,
        user_agent=request.headers.get("user-agent"),
        details={"email": register_data.email},
    )
    
    return {
        "message": "Registration successful. Please check your email to verify your account.",
        "user_id": str(user.id),
        "email": user.email,
        "email_verification_required": True,
    }


@router.post("/verify-email")
def verify_email(
    request: Request,
    verify_data: VerifyEmailRequest,
    db: Session = Depends(get_db),
):
    """Verify user email address using verification token."""
    # Find user by verification token
    user = db.query(User).filter(
        User.email_verification_token == verify_data.token,
        User.email_verified == False,
    ).first()
    
    if not user:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid or expired verification token",
        )
    
    # Check if token has expired
    if user.email_verification_expires_at and user.email_verification_expires_at < datetime.now(timezone.utc):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Verification token has expired. Please request a new one.",
        )
    
    # Verify email and activate account
    user.email_verified = True
    user.is_active = True
    user.email_verification_token = None
    user.email_verification_expires_at = None
    
    db.add(user)
    db.commit()
    
    # Log verification event
    log_auth_event(
        db,
        user_id=str(user.id),
        action_type="AUTH_EMAIL_VERIFIED",
        success=True,
        ip_address=request.client.host if request.client else None,
        user_agent=request.headers.get("user-agent"),
        details={},
    )
    
    return {
        "message": "Email verified successfully. Your account is now active.",
        "user_id": str(user.id),
        "email": user.email,
    }


@router.post("/resend-verification")
def resend_verification(
    request: Request,
    payload: dict,
    db: Session = Depends(get_db),
):
    """Resend email verification link."""
    email = payload.get("email")
    if not email:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Email is required",
        )
    
    user = db.query(User).filter(User.email == email).first()
    if not user:
        # Don't reveal if email exists or not (security best practice)
        return {
            "message": "If an account exists with this email, a verification link has been sent.",
        }
    
    if user.email_verified:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Email is already verified",
        )
    
    # Generate new verification token
    verification_token = uuid.uuid4().hex
    verification_expires = datetime.now(timezone.utc) + timedelta(hours=24)
    
    user.email_verification_token = verification_token
    user.email_verification_expires_at = verification_expires
    
    db.add(user)
    db.commit()
    
    # Send verification email
    if email_service.is_available():
        email_service.send_verification_email(
            to_email=user.email,
            verification_token=verification_token,
            username=user.username,
        )
    
    return {
        "message": "If an account exists with this email, a verification link has been sent.",
    }


