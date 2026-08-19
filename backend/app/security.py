import hashlib
import hmac
import secrets
import time
from datetime import datetime, timedelta, timezone

from fastapi import Depends, HTTPException, Request, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jose import JWTError, jwt
from passlib.context import CryptContext
from sqlalchemy import select
from sqlalchemy.orm import Session

from .config import Settings, get_settings
from .database import get_db
from .models import User


password_context = CryptContext(schemes=["pbkdf2_sha256"], deprecated="auto")
bearer = HTTPBearer(auto_error=False)


def hash_password(password: str) -> str:
    return password_context.hash(password)


def verify_password(password: str, password_hash: str) -> bool:
    return password_context.verify(password, password_hash)


def create_access_token(user: User, settings: Settings) -> str:
    expires = datetime.now(timezone.utc) + timedelta(minutes=settings.access_token_expire_minutes)
    return jwt.encode(
        {"sub": str(user.id), "role": user.rol, "exp": expires},
        settings.secret_key,
        algorithm=settings.algorithm,
    )


def get_current_admin(
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer),
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> User:
    unauthorized = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Autenticación administrativa requerida",
        headers={"WWW-Authenticate": "Bearer"},
    )
    if credentials is None:
        raise unauthorized
    try:
        payload = jwt.decode(credentials.credentials, settings.secret_key, algorithms=[settings.algorithm])
        user_id = int(payload.get("sub", ""))
    except (JWTError, ValueError):
        raise unauthorized from None
    user = db.scalar(select(User).where(User.id == user_id, User.active.is_(True)))
    if not user or user.rol != "admin":
        raise HTTPException(status_code=403, detail="Rol administrador requerido")
    return user


class EphemeralRateLimiter:
    """Límite en memoria con HMAC rotativo; nunca persiste la IP del ciudadano."""

    def __init__(self):
        self._buckets: dict[str, tuple[int, int]] = {}

    def check(
        self,
        request: Request,
        settings: Settings,
        *,
        scope: str,
        limit: int,
        identity: str = "",
    ) -> None:
        interval = 15 * 60
        bucket = int(time.time() // interval)
        host = request.client.host if request.client else "unknown"
        digest = hmac.new(
            settings.secret_key.encode(), f"{scope}:{bucket}:{host}:{identity}".encode(), hashlib.sha256
        ).hexdigest()
        count, stored_bucket = self._buckets.get(digest, (0, bucket))
        if stored_bucket != bucket:
            count = 0
        if count >= limit:
            raise HTTPException(status_code=429, detail="Demasiados envíos. Intentá nuevamente más tarde")
        self._buckets[digest] = (count + 1, bucket)
        if len(self._buckets) > 5000:
            self._buckets = {key: value for key, value in self._buckets.items() if value[1] >= bucket - 1}


rate_limiter = EphemeralRateLimiter()


def opaque_hash(value: str, secret_key: str) -> str:
    return hmac.new(secret_key.encode(), value.encode(), hashlib.sha256).hexdigest()


def generate_tracking_code() -> str:
    alphabet = "23456789ABCDEFGHJKLMNPQRSTUVWXYZ"
    return "SGD-RPT-" + "".join(secrets.choice(alphabet) for _ in range(6))
