from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import select

from .admin import router as admin_router
from .config import get_settings
from .database import Base, build_engine, build_session_factory
from .geocoding import router as geocoding_router
from .models import User
from .reports import router as reports_router
from .security import hash_password


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
                user = db.scalar(select(User).where(User.email == settings.admin_bootstrap_email.lower()))
                if not user:
                    db.add(User(
                        email=settings.admin_bootstrap_email.lower(),
                        password_hash=hash_password(settings.admin_bootstrap_password),
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

    return application


app = create_app()
