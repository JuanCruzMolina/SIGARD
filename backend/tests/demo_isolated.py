"""Fictitious checks in a fresh process; demo configuration never reaches pytest."""
import os
from pathlib import Path
import sys
from tempfile import TemporaryDirectory

BACKEND = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND))
from app.demo_local import checked_directory, create_demo_app


def main():
    temporary_root = BACKEND / ".tmp"
    temporary_root.mkdir(exist_ok=True)
    with TemporaryDirectory(prefix="sigard-demo-", dir=temporary_root) as name:
        directory = checked_directory(name)
        os.chdir(directory)
        # Poison all alternative configuration paths, using only invented values.
        os.environ.update(DATABASE_URL="postgresql://forbidden.invalid/persistent", SECRET_KEY="short",
                          AUTO_CREATE_SCHEMA="false", CORS_ORIGINS="https://forbidden.invalid",
                          ADMIN_BOOTSTRAP_EMAIL="unexpected@example.test", ADMIN_BOOTSTRAP_PASSWORD="short",
                          REPORT_RATE_LIMIT="9999")
        (directory / ".env").write_text("DATABASE_URL=postgresql://forbidden.invalid/dotenv\nSECRET_KEY=short\n")
        app, credentials = create_demo_app(directory)
        from app import config, database, geocoding
        from fastapi.testclient import TestClient
        from sqlalchemy import create_engine, func, select
        from app.models import User

        settings = config.get_settings()
        assert settings.allowed_origins == ["http://127.0.0.1:5173"]
        assert settings.auto_create_schema is True and settings.report_rate_limit == 5
        assert settings.admin_bootstrap_email is None and settings.admin_bootstrap_password is None
        assert app.state.engine.url.get_backend_name() == "sqlite"
        assert Path(app.state.engine.url.database) == directory / "demo.sqlite3"
        for url in ("postgresql://forbidden.invalid/nope", "sqlite:///:memory:", f"sqlite:///{directory / 'other.db'}"):
            try:
                database.build_engine(url)
            except RuntimeError:
                pass
            else:
                raise AssertionError("Alternate DB was accepted")
        try:
            create_engine("sqlite:///:memory:").connect()
        except RuntimeError:
            pass
        else:
            raise AssertionError("Direct SQLAlchemy bypass was accepted")

        def forbidden_client(*_args, **_kwargs):
            raise AssertionError("External geocoder was called")
        geocoding.httpx.Client = forbidden_client
        with TestClient(app) as client:
            assert client.get("/health/ready").status_code == 200
            assert client.post("/api/v1/geocoding/address", json={"address_reference": "Fictitious place"}).status_code == 503
            assert client.get("/api/v1/admin/citizen-reports").status_code == 401
            assert client.post("/api/v1/admin/session", json={"email": credentials["email"], "password": "wrong-password"}).status_code == 401
            with app.state.SessionLocal() as db:
                assert db.scalar(select(func.count()).select_from(User)) == 1
                assert db.scalar(select(User.email)) == credentials["email"]
        os.chdir(BACKEND)
    assert not directory.exists()
    print("Demo isolation: init-only settings, owned SQLite guards, auth and disabled geocoder passed")


if __name__ == "__main__":
    main()
