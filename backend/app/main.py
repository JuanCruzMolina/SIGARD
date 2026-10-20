from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.exception_handlers import request_validation_exception_handler
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from sqlalchemy import select
from sqlalchemy.exc import SQLAlchemyError

from .admin import router as admin_router
from .admin_accounts import lock_account_changes, router as accounts_router
from .config import get_settings
from .database import Base, build_engine, build_session_factory
from .geocoding import router as geocoding_router
from .models import AdminAccountAudit, CitizenReport, User
from .public import router as public_router
from .reports import router as reports_router
from .security import hash_password
from .schemas import AdminLogin


def create_app(database_url: str | None = None, auto_create_schema: bool | None = None) -> FastAPI:
    settings = get_settings()
    engine = build_engine(database_url or settings.database_url)
    session_factory = build_session_factory(engine)
    should_create = settings.auto_create_schema if auto_create_schema is None else auto_create_schema

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        if should_create:
            Base.metadata.create_all(engine)
        if settings.admin_bootstrap_email and settings.admin_bootstrap_password:
            with session_factory() as db:
                lock_account_changes(db)
                # Bootstrap only an empty user store. Never recreate privileges
                # in a managed installation or reset a deactivated account.
                if db.scalar(select(User.id).limit(1)) is None:
                    try:
                        bootstrap = AdminLogin(email=settings.admin_bootstrap_email, password=settings.admin_bootstrap_password)
                    except ValueError:
                        raise RuntimeError("Configuración administrativa bootstrap inválida") from None
                    db.add(User(
                        email=bootstrap.email,
                        password_hash=hash_password(bootstrap.password.get_secret_value()),
                        rol="admin",
                    ))
                    db.commit()
        yield
        engine.dispose()

    application = FastAPI(
        title=settings.app_name,
        description="API de SIGARD para información territorial y reportes ciudadanos anónimos",
        version="0.2.0",
        lifespan=lifespan,
    )
    application.state.engine = engine
    application.state.SessionLocal = session_factory
    application.add_middleware(
        CORSMiddleware,
        allow_origins=settings.allowed_origins,
        allow_credentials=False,
        allow_methods=["GET", "POST", "PATCH", "OPTIONS"],
        allow_headers=["Authorization", "Content-Type", "Idempotency-Key"],
    )
    application.include_router(reports_router)
    application.include_router(geocoding_router)
    application.include_router(admin_router)
    application.include_router(accounts_router)
    application.include_router(public_router)

    @application.exception_handler(RequestValidationError)
    async def safe_admin_validation(request, exc):
        if request.url.path.startswith("/api/v1/admin/"):
            # FastAPI's default validation payload can echo passwords or tokens.
            return JSONResponse(status_code=422, content={"detail": "Datos administrativos inválidos. Revisá los campos y sus límites."})
        return await request_validation_exception_handler(request, exc)

    @application.middleware("http")
    async def protect_sensitive_responses(request, call_next):
        response = await call_next(request)
        response.headers["Referrer-Policy"] = "no-referrer"
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        if request.url.path.startswith("/api/v1/admin"):
            response.headers["Cache-Control"] = "no-store"
        return response

    @application.get("/")
    def root():
        return {"message": "SIGARD API funcionando", "version": "0.2.0"}

    @application.get("/health")
    def health():
        return {"status": "ok"}

    @application.get("/health/ready")
    def readiness():
        try:
            with application.state.engine.connect() as connection:
                connection.execute(select(User.id, User.token_version).limit(1)).first()
                connection.execute(select(AdminAccountAudit.id).limit(1)).first()
                connection.execute(select(CitizenReport.id).limit(1)).first()
        except SQLAlchemyError:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="Base de datos o esquema no disponible",
            ) from None
        return {"status": "ready"}

    return application


app = create_app()
