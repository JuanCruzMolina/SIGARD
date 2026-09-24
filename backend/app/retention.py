"""Elimina reportes vencidos. Ejecutar diariamente fuera del proceso web."""

import argparse
from datetime import datetime, timezone

from sqlalchemy import delete, func, select

from .config import get_settings
from .database import build_engine, build_session_factory
from .models import CitizenReport


def count_expired(database_url: str | None = None, *, before: datetime | None = None) -> int:
    settings = get_settings()
    engine = build_engine(database_url or settings.database_url)
    session_factory = build_session_factory(engine)
    cutoff = before or datetime.now(timezone.utc)
    try:
        with session_factory() as db:
            return db.scalar(
                select(func.count()).select_from(CitizenReport).where(CitizenReport.retention_until < cutoff)
            ) or 0
    finally:
        engine.dispose()


def purge_expired(database_url: str | None = None, *, before: datetime | None = None) -> int:
    settings = get_settings()
    engine = build_engine(database_url or settings.database_url)
    session_factory = build_session_factory(engine)
    cutoff = before or datetime.now(timezone.utc)
    try:
        with session_factory() as db:
            result = db.execute(delete(CitizenReport).where(CitizenReport.retention_until < cutoff))
            db.commit()
            return result.rowcount or 0
    finally:
        engine.dispose()


def main() -> None:
    parser = argparse.ArgumentParser(description="Aplica la política de retención de reportes ciudadanos")
    parser.add_argument("--dry-run", action="store_true", help="Cuenta reportes vencidos sin eliminarlos")
    args = parser.parse_args()
    if args.dry_run:
        print(f"Reportes vencidos detectados: {count_expired()}")
        return
    print(f"Reportes eliminados por retención: {purge_expired()}")


if __name__ == "__main__":
    main()
