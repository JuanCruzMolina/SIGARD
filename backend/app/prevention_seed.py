"""Idempotent initial import of the static preventive content as published version 1.

Run from ``backend/`` against an authorized database::

    python -m app.prevention_seed --source ../frontend/public/data/prevention_content.json

Sections are matched by ``slug``: existing ones are never overwritten, so a
repeated run cannot undo administrator edits. Keep the slugs and titles in sync
with ``frontend/src/services/preventionContent.mjs`` (static fallback).
"""

import argparse
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.orm import Session

from .models import PreventionSection
from .prevention import audit, clean_text, snapshot


DEFAULT_SOURCE = Path(__file__).resolve().parents[2] / "frontend/public/data/prevention_content.json"
NATION_PREVENTION = "https://www.argentina.gob.ar/como-prevenir-el-dengue"
NATION_SYMPTOMS = "https://www.argentina.gob.ar/sintomas-y-signos-de-alarma"
NATION_FUMIGATION = "https://www.argentina.gob.ar/node/371159"


def bullet_list(items) -> str:
    return "\n".join(f"- {item}" for item in items)


def legacy_sections(content: dict) -> list[dict]:
    """Map the legacy JSON layout to sections (same mapping as the static fallback)."""
    sources = {source["url"]: source for source in content.get("sources", [])}

    def source(url):
        item = sources.get(url)
        return (f"{item['title']} · {item['publisher']}", url) if item else (None, None)

    vector = content["vector_control"]
    rows = [
        ("prevencion", "Prevenir empieza por eliminar criaderos", bullet_list(content["prevention"]), 10, NATION_PREVENTION),
        ("control-vectorial", vector["title"], vector["body"], 20, NATION_FUMIGATION),
        ("sintomas", "Síntomas compatibles", bullet_list(content["symptoms"]), 30, NATION_SYMPTOMS),
        ("consejos-medicos", "Qué hacer ante síntomas", "\n\n".join(content["medical_advice"]), 40, NATION_SYMPTOMS),
        ("signos-alarma", "Signos de alarma", bullet_list(content["warning_signs"]), 50, NATION_SYMPTOMS),
    ]
    sections = []
    for slug, title, body, position, url in rows:
        label, source_url = source(url)
        sections.append({
            "slug": slug, "title": clean_text(title, "title", required=True),
            "body": clean_text(body, "body", required=True), "position": position,
            "source_label": label, "source_url": source_url,
        })
    return sections


def seed_prevention(db: Session, content: dict, source_hash: str) -> int:
    """Insert missing sections as published v1. Returns how many were created."""
    existing = set(db.scalars(select(PreventionSection.slug)))
    now = datetime.now(timezone.utc)
    created = 0
    for item in legacy_sections(content):
        if item["slug"] in existing:
            continue
        section = PreventionSection(**item, status="published", version=1, published_at=now, created_at=now, updated_at=now)
        section.published_json = {**item, "version": 1, "published_at": now.isoformat()}
        db.add(section)
        db.flush()
        audit(db, section, None, "seed_import", None, {
            **snapshot(section), "origin": "prevention_content.json",
            "schema_version": content.get("schema_version"), "source_sha256": source_hash,
        })
        created += 1
    db.commit()
    return created


def seed_from_file(db: Session, path: Path = DEFAULT_SOURCE) -> int:
    raw = Path(path).read_bytes()
    return seed_prevention(db, json.loads(raw.decode("utf-8")), hashlib.sha256(raw).hexdigest())


def main() -> None:
    parser = argparse.ArgumentParser(description="Carga inicial idempotente del contenido preventivo")
    parser.add_argument("--source", type=Path, default=DEFAULT_SOURCE)
    args = parser.parse_args()
    from .config import get_settings
    from .database import build_engine, build_session_factory

    engine = build_engine(get_settings().database_url)
    try:
        with build_session_factory(engine)() as db:
            created = seed_from_file(db, args.source)
    finally:
        engine.dispose()
    print(json.dumps({"created_sections": created}))


if __name__ == "__main__":
    main()
