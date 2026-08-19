"""Elimina reportes vencidos. Ejecutar diariamente fuera del proceso web."""

from datetime import datetime, timezone

from sqlalchemy import delete

from .config import get_settings
from .database import build_engine, build_session_factory
from .models import CitizenReport


def purge_expired(database_url: str | None = None) -> int:
    settings = get_settings()
    session_factory = build_session_factory(build_engine(database_url or settings.database_url))
    with session_factory() as db:
        result = db.execute(delete(CitizenReport).where(CitizenReport.retention_until < datetime.now(timezone.utc)))
        db.commit()
        return result.rowcount or 0


if __name__ == "__main__":
    print(f"Reportes eliminados por retención: {purge_expired()}")
