"""Diagnóstico privado del cambio de calendario. No genera ni modifica paneles."""

import argparse
from datetime import date, datetime, timedelta
import hashlib
import json
from pathlib import Path

import pandas as pd
import pyarrow.parquet as pq

from sigard_ml.official.calendar_rules import CalendarError, DEFAULT_CALENDAR, LEGACY_CALENDAR


def calendar_changes(start: date, end: date) -> dict:
    """Compara etiquetas e intervalos sin consultar registros epidemiológicos."""
    if type(start) is not date or type(end) is not date or start > end:
        raise ValueError("Período inválido")
    changed = []
    day = start
    while day <= end:
        old, new = LEGACY_CALENDAR.date_week(day), DEFAULT_CALENDAR.date_week(day)
        if old != new:
            changed.append(day)
        day += timedelta(days=1)
    return {"start": start.isoformat(), "end": end.isoformat(), "days_compared": (end - start).days + 1,
            "days_with_changed_labels": len(changed),
            "first_changed_date": changed[0].isoformat() if changed else None,
            "last_changed_date": changed[-1].isoformat() if changed else None}


def _date(value):
    return value.date() if isinstance(value, (pd.Timestamp, datetime)) else value


def compare_panel(panel: pd.DataFrame) -> dict:
    """Sólo agregados: no devuelve radios, identificadores ni conteos por celda."""
    columns = ["anio_epidemiologico", "semana_epidemiologica", "fecha_inicio_semana", "fecha_fin_semana"]
    if not set(columns) <= set(panel):
        raise ValueError("Faltan campos de calendario en el panel")
    cache, changed, moved = {}, 0, 0
    for year, number, start, end in panel[columns].itertuples(index=False, name=None):
        start, end = _date(start), _date(end)
        if start not in cache:
            label = DEFAULT_CALENDAR.date_week(start)
            cache[start] = label, DEFAULT_CALENDAR.week_bounds(*label)
        label, bounds = cache[start]
        changed += (int(year), int(number)) != label
        moved += (start, end) != bounds
    return {"rows_checked": len(panel), "weeks_checked": len(cache),
            "rows_with_changed_labels": int(changed), "rows_with_changed_intervals": int(moved),
            "year_week_keys_change": bool(changed),
            "count_migration_between_date_intervals_required": bool(moved), "panel_regenerated": False}


def _digest(path):
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def audit_artifacts(repo_root: Path, output_dir: Path) -> dict:
    """Lee las Fases 4/4.1/4.2, verifica preservación y escribe sólo diagnóstico nuevo.

    El destino es privado y debe ser nuevo; nunca escribe sobre una salida previa.
    """
    repo_root, output_dir = repo_root.resolve(), output_dir.resolve()
    interim = (repo_root / "data/interim").resolve()
    if not output_dir.is_relative_to(interim) or output_dir.exists():
        raise ValueError("El diagnóstico requiere un directorio nuevo dentro de data/interim")
    observed = repo_root / "data/interim/official/observed"
    panels = sorted(observed.rglob("panel.parquet"))
    audits = sorted(observed.rglob("records_audit.parquet"))
    if not panels or not audits:
        raise ValueError("Faltan paneles o auditorías anteriores")
    # Fuentes y artefactos anteriores: sólo hashes y lectura, nunca exportación.
    preserved = sorted(set((repo_root / "data").rglob("*.xlsx"))
                       | set((repo_root / "data").rglob("*.xls"))
                       | set(observed.rglob("*.*")))
    preserved = [path for path in preserved if path.is_file()]
    before = {path.relative_to(repo_root).as_posix(): _digest(path) for path in preserved}
    reports, record_reports = {}, {}
    for path in panels:
        columns = ["anio_epidemiologico", "semana_epidemiologica", "fecha_inicio_semana", "fecha_fin_semana"]
        reports[path.relative_to(observed).as_posix()] = compare_panel(pd.read_parquet(path, columns=columns))
    for path in audits:
        required = ["reference_date", "week_start", "epidemiological_year", "epidemiological_week"]
        if not set(required) <= set(pq.ParquetFile(path).schema.names):
            raise ValueError("Auditoría sin campos de calendario requeridos")
        frame = pd.read_parquet(path, columns=required)
        checked = changed = moved = outside = 0
        cache = {}
        for value, start, year, number in frame.itertuples(index=False, name=None):
            if pd.isna(value) or pd.isna(start):
                continue
            value, start = _date(value), _date(start)
            try:
                if value not in cache:
                    label = DEFAULT_CALENDAR.date_week(value)
                    cache[value] = label, DEFAULT_CALENDAR.week_bounds(*label)[0]
                label, new_start = cache[value]
            except CalendarError:
                outside += 1
                continue
            checked += 1
            changed += label != (int(year), int(number))
            moved += start != new_start
        record_reports[path.relative_to(observed).as_posix()] = {
            "assigned_dates_checked": checked, "changed_labels": int(changed),
            "changed_week_intervals": int(moved), "outside_verified_calendar": outside}
    after = {path.relative_to(repo_root).as_posix(): _digest(path) for path in preserved}
    if before != after:
        raise ValueError("Se alteraron archivos durante la auditoría de calendario")
    report = {"audit_version": "calendar-impact-v1",
              "calendar_version": DEFAULT_CALENDAR.version, "previous_calendar_version": LEGACY_CALENDAR.version,
              "current_analysis_period": calendar_changes(date(2020, 1, 1), date(2024, 12, 31)),
              "validated_calendar_period": calendar_changes(date(2020, 1, 1), date(2026, 12, 31)),
              "panels": reports, "record_audits": record_reports,
              "preserved_file_count": len(before), "sha256_unchanged": before == after,
              "coverage_extended": False, "panels_regenerated": False}
    output_dir.mkdir(parents=True, exist_ok=False)
    (output_dir / "impact.private.json").write_text(json.dumps(report, indent=2, sort_keys=True), encoding="utf-8")
    (output_dir / "preserved_files_sha256.private.json").write_text(json.dumps(before, indent=2, sort_keys=True), encoding="utf-8")
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[4]
    report = audit_artifacts(root, args.output_dir)
    print(json.dumps({"panels_checked": len(report["panels"]),
                      "record_audits_checked": len(report["record_audits"]),
                      "changed_panel_labels": sum(item["rows_with_changed_labels"] for item in report["panels"].values()),
                      "changed_assigned_dates": sum(item["changed_labels"] for item in report["record_audits"].values()),
                      "sha256_unchanged": report["sha256_unchanged"], "panels_regenerated": False}))


if __name__ == "__main__":
    main()
