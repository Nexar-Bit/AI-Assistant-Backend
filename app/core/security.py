from datetime import datetime, timedelta, timezone
from typing import Any, Optional
import re
import uuid

from jose import JWTError, jwt

try:
    from passlib.context import CryptContext
    pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")
    USE_PASSLIB = True
except Exception:
    # Fallback to direct bcrypt if passlib has issues
    import bcrypt
    USE_PASSLIB = False

from .config import settings

PASSWORD_POLICY_REGEX = re.compile(
    r"^(?=.*[a-z])(?=.*[A-Z])(?=.*\d)(?=.*[^A-Za-z0-9]).{12,}$"
)


def verify_password(plain_password: str, hashed_password: str) -> bool:
    password_bytes = plain_password.encode('utf-8')
    hash_bytes = hashed_password.encode('utf-8')
    
    if USE_PASSLIB:
        try:
            return pwd_context.verify(plain_password, hashed_password)
        except Exception:
            # Fall back to direct bcrypt if passlib fails
            pass
    
    # Direct bcrypt fallback
    import bcrypt
    return bcrypt.checkpw(password_bytes, hash_bytes)


def get_password_hash(password: str) -> str:
    if not PASSWORD_POLICY_REGEX.match(password):
        raise ValueError(
            "Password must be at least 12 characters long and contain upper, "
            "lower, digit, and special character."
        )
    
    # bcrypt has a 72-byte limit, truncate if necessary
    password_bytes = password.encode('utf-8')
    if len(password_bytes) > 72:
        password_bytes = password_bytes[:72]
        password = password_bytes.decode('utf-8', errors='ignore')
    
    if USE_PASSLIB:
        try:
            return pwd_context.hash(password)
        except Exception:
            # Fall back to direct bcrypt if passlib fails
            pass
    
    # Direct bcrypt fallback
    import bcrypt
    salt = bcrypt.gensalt()
    hashed = bcrypt.hashpw(password_bytes, salt)
    return hashed.decode('utf-8')


def create_token(
    subject: str | Any,
    expires_delta: Optional[timedelta],
    token_type: str,
    jti: Optional[str] = None,
) -> str:
    if isinstance(subject, str):
        sub = subject
    else:
        sub = str(subject)

    now = datetime.now(timezone.utc)
    expire = now + (expires_delta or timedelta(minutes=15))
    payload: dict[str, Any] = {
        "sub": sub,
        "iat": int(now.timestamp()),
        "exp": int(expire.timestamp()),
        "type": token_type,
        "jti": jti or uuid.uuid4().hex,
    }
    return jwt.encode(payload, settings.SECRET_KEY, algorithm=settings.JWT_ALGORITHM)


def create_access_token(subject: str | Any) -> str:
    expires = timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)
    return create_token(subject, expires, token_type="access")


def create_refresh_token(subject: str | Any) -> str:
    expires = timedelta(days=settings.REFRESH_TOKEN_EXPIRE_DAYS)
    return create_token(subject, expires, token_type="refresh")


def decode_token(token: str, expected_type: str) -> dict[str, Any]:
    try:
        payload = jwt.decode(
            token,
            settings.SECRET_KEY,
            algorithms=[settings.JWT_ALGORITHM],
        )
        if payload.get("type") != expected_type:
            raise JWTError("Invalid token type")
        return payload
    except JWTError as exc:
        raise JWTError("Invalid or expired token") from exc


