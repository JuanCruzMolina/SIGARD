"""Account lifecycle using existing users, password hashes and JWT authorization."""

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from sqlalchemy import func, select, text
from sqlalchemy.exc import IntegrityError, OperationalError
from sqlalchemy.orm import Session

from .database import get_db
from .config import Settings, get_settings
from .models import AdminAccountAudit, User
from .schemas import (
    AdminAccountConfirm, AdminAccountCreate, AdminAccountPage,
    AdminAccountSummary, AdminPasswordRotation,
)
from .security import get_current_admin, hash_password, rate_limiter, verify_password


router = APIRouter(prefix="/api/v1/admin/users", tags=["cuentas administrativas"])


def lock_account_changes(db: Session) -> None:
    """Serialize lifecycle mutations before counting admins or changing credentials.

    PostgreSQL locks across workers until commit/rollback. SQLite's write lock is
    the equivalent for isolated tests; neither lock relies on a Python mutex.
    """
    dialect = db.get_bind().dialect.name
    try:
        if dialect == "postgresql":
            db.execute(text("SELECT pg_advisory_xact_lock(1397311297)"))
        elif dialect == "sqlite":
            db.connection().exec_driver_sql("BEGIN IMMEDIATE")
        else:
            raise HTTPException(status_code=503, detail="Gestión de cuentas no disponible en esta base")
    except OperationalError:
        db.rollback()
        raise HTTPException(status_code=409, detail="Otra operación está en curso. Intentá nuevamente") from None


def authorize_change(db: Session, admin: User, password: str, request: Request, settings: Settings) -> None:
    rate_limiter.check(request, settings, scope="admin-account-change", limit=settings.admin_login_rate_limit, identity=str(admin.id))
    version = admin.token_version
    lock_account_changes(db)
    # The session may have waited behind a revocation. Recheck after the lock.
    db.refresh(admin)
    if not admin.active or admin.token_version != version:
        raise HTTPException(status_code=401, detail="La sesión administrativa ya no es válida")
    if admin.rol != "admin":
        raise HTTPException(status_code=403, detail="Rol administrador requerido")
    if not verify_password(password, admin.password_hash):
        raise HTTPException(status_code=403, detail="No se pudo confirmar la autorización")


def target_admin(db: Session, user_id: int) -> User:
    user = db.scalar(select(User).where(User.id == user_id, User.rol == "admin").execution_options(populate_existing=True))
    if not user:
        raise HTTPException(status_code=404, detail="Cuenta administrativa no encontrada")
    return user


def audit(db: Session, admin: User, target: User, action: str) -> None:
    db.add(AdminAccountAudit(actor_user_id=admin.id, target_user_id=target.id, action=action))
    db.commit()


@router.get("", response_model=AdminAccountPage)
def list_accounts(
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=25, ge=1, le=100),
    db: Session = Depends(get_db),
    admin: User = Depends(get_current_admin),
):
    base = select(User).where(User.rol == "admin")
    return AdminAccountPage(
        items=[AdminAccountSummary.model_validate(user) for user in db.scalars(
            base.order_by(User.id).offset((page - 1) * page_size).limit(page_size)
        )],
        total=db.scalar(select(func.count()).select_from(base.subquery())) or 0,
        page=page, page_size=page_size, current_user_id=admin.id,
        active_admin_count=db.scalar(select(func.count(User.id)).where(User.rol == "admin", User.active.is_(True))) or 0,
    )


@router.post("", response_model=AdminAccountSummary, status_code=201)
def create_account(
    payload: AdminAccountCreate,
    request: Request,
    db: Session = Depends(get_db),
    admin: User = Depends(get_current_admin),
    settings: Settings = Depends(get_settings),
):
    authorize_change(db, admin, payload.current_password.get_secret_value(), request, settings)
    if db.scalar(select(User.id).where(func.lower(func.trim(User.email)) == payload.email)) is not None:
        raise HTTPException(status_code=409, detail="Ya existe una cuenta con ese correo")
    user = User(email=payload.email, password_hash=hash_password(payload.password.get_secret_value()), rol="admin")
    db.add(user)
    try:
        db.flush()
        audit(db, admin, user, "created")
    except IntegrityError:
        db.rollback()
        raise HTTPException(status_code=409, detail="No se pudo crear la cuenta; revisá si ya existe") from None
    return AdminAccountSummary.model_validate(user)


@router.post("/{user_id}/deactivate", response_model=AdminAccountSummary)
def deactivate_account(
    user_id: int, payload: AdminAccountConfirm, request: Request,
    db: Session = Depends(get_db), admin: User = Depends(get_current_admin),
    settings: Settings = Depends(get_settings),
):
    authorize_change(db, admin, payload.current_password.get_secret_value(), request, settings)
    user = target_admin(db, user_id)
    if user.active:
        count = db.scalar(select(func.count(User.id)).where(User.rol == "admin", User.active.is_(True))) or 0
        if count <= 1:
            raise HTTPException(status_code=409, detail="No se puede desactivar la última cuenta administrativa activa")
        user.active = False
        user.token_version += 1
        audit(db, admin, user, "deactivated")
    return AdminAccountSummary.model_validate(user)


@router.post("/{user_id}/password", response_model=AdminAccountSummary)
def rotate_password(
    user_id: int, payload: AdminPasswordRotation, request: Request,
    db: Session = Depends(get_db), admin: User = Depends(get_current_admin),
    settings: Settings = Depends(get_settings),
):
    authorize_change(db, admin, payload.current_password.get_secret_value(), request, settings)
    user = target_admin(db, user_id)
    if not user.active:
        raise HTTPException(status_code=409, detail="La cuenta está inactiva")
    new_password = payload.new_password.get_secret_value()
    if verify_password(new_password, user.password_hash):
        raise HTTPException(status_code=422, detail="La nueva contraseña debe ser distinta de la anterior")
    user.password_hash = hash_password(new_password)
    user.token_version += 1
    audit(db, admin, user, "password_rotated")
    return AdminAccountSummary.model_validate(user)
