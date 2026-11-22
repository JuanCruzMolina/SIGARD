"""Local administrative API (login, reports, content, accounts, alerts) on 127.0.0.1:8767.
Never deployment.

  serve         persistent private SQLite (data/interim/official/internal-alerts-v1/,
                ignored by Git) + predictions read from the local predictive API
                (127.0.0.1:8765). Started by `npm run dev` (`dev:alerts` is an alias).
                Starts even without an account; readiness reports "admin": false.
  create-admin  interactive, one-time account creation; the password is never printed.
  session       disposable SQLite in backend/.tmp/sigard-alerts-*; a generated
                session-only admin is written to the coordinator pipe. For browser
                checks only (`--source fictional` or `--source local-research`).

Schema: the ORM metadata (same as the demo); the Alembic chain needs PostGIS and
remains the path for managed installations (migration 20261114_06).
"""
import argparse
import asyncio
import getpass
import json
import os
from pathlib import Path
import secrets
import socket
import sys
import threading

BACKEND = Path(__file__).resolve().parents[1]
ROOT = BACKEND.parent
sys.path.insert(0, str(BACKEND))
PORT = 8767
PERSISTENT = ROOT / "data/interim/official/internal-alerts-v1/alerts.private.sqlite3"
ORIGIN = "http://127.0.0.1:5173"


def refuse_deployment():
    if any(os.environ.get(k) for k in ("VERCEL", "RENDER", "RAILWAY_ENVIRONMENT", "WEBSITE_INSTANCE_ID", "K_SERVICE")) \
            or Path("/.dockerenv").exists():
        raise SystemExit("Las alertas internas sólo se inician en el host local, fuera de despliegues y Docker")


def persistent_path():
    folder = PERSISTENT.parent
    official = (ROOT / "data/interim/official").resolve()
    if any(p.is_symlink() for p in (folder, PERSISTENT) if p.exists()) or not folder.resolve().is_relative_to(official):
        raise SystemExit("Ruta privada de alertas inválida")
    folder.mkdir(parents=True, exist_ok=True)
    return PERSISTENT.resolve()


def session_path(value):
    directory = Path(value)
    if directory.is_symlink() or directory.resolve().parent != (BACKEND / ".tmp").resolve() \
            or not directory.name.startswith("sigard-alerts-") or not directory.is_dir() or any(directory.iterdir()):
        raise ValueError("La sesión exige un directorio temporal propio y vacío")
    return directory.resolve() / "alerts.sqlite3"


def build_app(database_path):
    from app import config, database
    from sqlalchemy import event
    from sqlalchemy.engine import Engine

    database_url = f"sqlite:///{database_path.as_posix()}"

    @event.listens_for(Engine, "do_connect")
    def only_owned_sqlite(dialect, _record, args, _params):
        if dialect.name != "sqlite" or Path(args[0]).resolve() != database_path:
            raise RuntimeError("Sólo se admite el SQLite propio de alertas")

    class LocalSettings(config.Settings):
        @classmethod
        def settings_customise_sources(cls, settings_cls, init_settings, env_settings, dotenv_settings, file_secret_settings):
            return (init_settings,)  # no inherited DATABASE_URL, .env, bootstrap or secrets

    # A new secret per process: sessions end when the local API stops. The only inherited
    # option is the explicit opt-in to the generated fictional "Actividad registrada" package.
    activity = "fixture" if os.environ.get("SIGARD_PUBLIC_ACTIVITY") == "fixture" else None
    settings = LocalSettings(secret_key=secrets.token_urlsafe(48), database_url=database_url, auto_create_schema=True,
                             cors_origins=ORIGIN, admin_bootstrap_email=None, admin_bootstrap_password=None,
                             sigard_public_activity=activity)
    config.get_settings = lambda: settings
    from app.main import app  # built with the settings above

    database.Base.metadata.create_all(app.state.engine)
    return app


def create_admin():
    refuse_deployment()
    app = build_app(persistent_path())
    from app.models import User
    from app.schemas import AdminLogin
    from app.security import hash_password
    from sqlalchemy import func, select

    email = input("Correo del administrador local: ").strip()
    password = getpass.getpass("Contraseña (no se muestra): ")
    if password != getpass.getpass("Repetí la contraseña: "):
        raise SystemExit("Las contraseñas no coinciden")
    try:
        login = AdminLogin(email=email, password=password)
    except ValueError:
        raise SystemExit("Correo o contraseña inválidos (revisá la longitud mínima)") from None
    with app.state.SessionLocal() as db:
        if db.scalar(select(User.id).where(func.lower(User.email) == login.email.lower())):
            raise SystemExit("Ya existe una cuenta con ese correo")
        db.add(User(email=login.email, password_hash=hash_password(login.password.get_secret_value()), rol="admin"))
        db.commit()
    app.state.engine.dispose()
    print("Cuenta de administrador creada en el almacenamiento privado de alertas.")


def serve(app, readiness):
    with socket.socket() as listener:
        listener.bind(("127.0.0.1", PORT))
        listener.listen(128)
        listener.setblocking(False)
        import uvicorn

        server = uvicorn.Server(uvicorn.Config(app, host="127.0.0.1", port=PORT, log_level="error",
                                               access_log=False, proxy_headers=False, server_header=False))

        async def run():
            async def stop_on_input():
                await asyncio.to_thread(sys.stdin.readline)
                server.should_exit = True
            print(json.dumps(readiness), flush=True)  # private pipe to the coordinator
            await asyncio.gather(server.serve(sockets=[listener]), stop_on_input())

        try:
            asyncio.run(run())
        finally:
            app.state.engine.dispose()


def attach(app, source, storage):
    from fastapi.responses import JSONResponse

    app.state.alert_source = source
    nonce = secrets.token_urlsafe(24)

    @app.middleware("http")
    async def local_boundary(request, call_next):
        if request.url.path.startswith("/api/v1/geocoding/"):
            return JSONResponse(status_code=503, content={"detail": "No disponible en el entorno local de alertas."})
        response = await call_next(request)
        response.headers["Cache-Control"] = "no-store"
        return response

    @app.get("/health/alerts", include_in_schema=False)
    def health():
        return {"alerts": True, "session": nonce, "storage": storage}

    # Warm the compact prediction cache so the first retrospective preview is fast.
    def warm():
        try:
            source.preload()
        except Exception:
            pass  # unavailable source is reported by the API itself
    threading.Thread(target=warm, daemon=True).start()
    return nonce


def main():
    refuse_deployment()
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("serve")
    sub.add_parser("create-admin")
    session = sub.add_parser("session")
    session.add_argument("--directory", required=True)
    session.add_argument("--source", choices=("fictional", "local-research"), required=True)
    args = parser.parse_args()
    if args.command == "create-admin":
        return create_admin()
    from app.alert_source import FictionalSource, LocalResearchSource
    if args.command == "serve":
        app = build_app(persistent_path())
        from app.models import User
        from sqlalchemy import select
        # Without an account the API still serves (login is simply refused) so `npm run dev`
        # starts; the coordinator prints the create-admin command. Never creates one.
        with app.state.SessionLocal() as db:
            admin = db.scalar(select(User.id).where(User.rol == "admin", User.active.is_(True)).limit(1)) is not None
        nonce = attach(app, LocalResearchSource(), "persistent-private-sqlite")
        return serve(app, {"session": nonce, "storage": "persistent-private-sqlite", "admin": admin})
    app = build_app(session_path(args.directory))
    from app.models import User
    from app.security import hash_password
    email, password = f"alerts-{secrets.token_hex(4)}@example.test", secrets.token_urlsafe(24)
    with app.state.SessionLocal() as db:
        db.add(User(email=email, password_hash=hash_password(password), rol="admin"))
        db.commit()
    source = FictionalSource() if args.source == "fictional" else LocalResearchSource()
    nonce = attach(app, source, "disposable-sqlite")
    serve(app, {"session": nonce, "storage": "disposable-sqlite", "email": email, "password": password})


if __name__ == "__main__":
    try:
        main()
    except SystemExit:
        raise
    except Exception:
        # Never echo settings, database URLs or credentials.
        print("La API local de alertas no pudo iniciarse o cerrarse. Revisá requisitos y el puerto 8767.", file=sys.stderr)
        raise SystemExit(1) from None
