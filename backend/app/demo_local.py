"""Session-only citizen/admin API. Run only through frontend's dev:demo.

Reuses the same app, schema, validation, authentication and permissions as the
disposable browser fixture. Never imports its optional PostGIS/public seeding.
The coordinator owns the empty temporary directory and removes it after exit.
"""

import argparse
import asyncio
import json
from pathlib import Path
import secrets
import socket
import sys


BACKEND = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND))


def checked_directory(value):
    directory = Path(value)
    if (
        directory.is_symlink()
        or directory.resolve().parent != (BACKEND / ".tmp").resolve()
        or not directory.name.startswith("sigard-demo-")
        or not directory.is_dir()
        or any(directory.iterdir())
    ):
        raise ValueError("La demo exige un directorio temporal propio y vacío")
    return directory.resolve()


def create_demo_app(directory):
    from app import config, database
    from sqlalchemy import event
    from sqlalchemy.engine import Engine, make_url

    database_path = directory / "demo.sqlite3"
    database_url = f"sqlite:///{database_path.as_posix()}"

    # Reject other drivers/paths BEFORE SQLAlchemy can import a PostgreSQL driver.
    original_build_engine = database.build_engine

    def sqlite_engine(url):
        parsed = make_url(url)
        if parsed.drivername != "sqlite" or parsed.database != database_path.as_posix() or parsed.query:
            raise RuntimeError("La demo sólo admite su SQLite temporal")
        return original_build_engine(database_url)

    database.build_engine = sqlite_engine

    # A second guard applies even to an accidental direct create_engine call.
    @event.listens_for(Engine, "do_connect")
    def only_owned_sqlite(dialect, _record, args, _params):
        if dialect.name != "sqlite" or Path(args[0]).resolve() != database_path:
            raise RuntimeError("Conexión persistente o no SQLite prohibida en demo")

    class SessionSettings(config.Settings):
        @classmethod
        def settings_customise_sources(cls, settings_cls, init_settings, env_settings, dotenv_settings, file_secret_settings):
            # No inherited DATABASE_URL, .env, bootstrap, secrets dir or settings.
            return (init_settings,)

    email = f"demo-{secrets.token_hex(4)}@example.test"
    password = secrets.token_urlsafe(24)
    settings = SessionSettings(
        secret_key=secrets.token_urlsafe(48), database_url=database_url,
        auto_create_schema=True, cors_origins="http://127.0.0.1:5173",
        admin_bootstrap_email=None, admin_bootstrap_password=None,
    )
    # Same process-local configuration seam used by browser_admin_fixture.py.
    # Set BEFORE app.main and its dependencies resolve get_settings.
    config.get_settings = lambda: settings
    from app.main import app
    from app.models import User
    from app.security import hash_password
    from fastapi.responses import JSONResponse

    database.Base.metadata.create_all(app.state.engine)
    with app.state.SessionLocal() as db:
        db.add(User(email=email, password_hash=hash_password(password), rol="admin"))
        db.commit()

    @app.middleware("http")
    async def demo_boundary(request, call_next):
        # Also enforced server-side: manually calling the route cannot geocode.
        if request.url.path.startswith("/api/v1/geocoding/"):
            return JSONResponse(status_code=503, content={"detail": "Demo ficticia: elegí una ubicación manual en el mapa."})
        response = await call_next(request)
        response.headers["Cache-Control"] = "no-store"
        return response

    nonce = secrets.token_urlsafe(24)

    @app.get("/health/demo", include_in_schema=False)
    def demo_health():
        return {"demo": True, "session": nonce, "storage": "disposable-sqlite"}

    return app, {"email": email, "password": password, "session": nonce}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--directory", required=True)
    args = parser.parse_args()
    directory = checked_directory(args.directory)
    # Reserve loopback before constructing the DB, never attach to a busy port.
    with socket.socket() as listener:
        listener.bind(("127.0.0.1", 8766))
        listener.listen(128)
        listener.setblocking(False)
        app, session = create_demo_app(directory)
        import uvicorn

        server = uvicorn.Server(uvicorn.Config(
            app, host="127.0.0.1", port=8766, log_level="error",
            access_log=False, proxy_headers=False, server_header=False,
        ))

        async def run():
            async def stop_on_input():
                await asyncio.to_thread(sys.stdin.readline)
                server.should_exit = True

            # Private pipe to coordinator, never forwarded to logs or files.
            print(json.dumps(session), flush=True)
            await asyncio.gather(server.serve(sockets=[listener]), stop_on_input())

        try:
            asyncio.run(run())
        finally:
            app.state.engine.dispose()


if __name__ == "__main__":
    try:
        main()
    except Exception:
        # Never echo settings, database URLs or credentials on failure.
        print("La API demo no pudo iniciarse o cerrarse. Revisá requisitos y puerto 8766.", file=sys.stderr)
        raise SystemExit(1) from None
