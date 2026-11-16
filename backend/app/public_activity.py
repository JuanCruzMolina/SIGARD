"""Public view of registered activity: protected levels by radio and city weekly series.

Disabled by default (404). It serves the private offline package only when ALL hold:
- a private authorization file exists (date, institutional officer, scope, document
  reference) bound to the SHA-256 of the package manifest;
- the manifest and every listed file verify;
- the re-identification report passed with 0 disclosures;
- the package content matches the public contract and the authorized scope.
``SIGARD_PUBLIC_ACTIVITY=fixture`` serves only a generated fictional package (tests and local
review). No environment value ever enables real data. Nothing here is written to the frontend.
"""

import hashlib
import json
import re
from datetime import date, timedelta
from pathlib import Path

from fastapi import APIRouter, HTTPException, Request, Response

ROOT = Path(__file__).resolve().parents[2]
DEFAULT_PACKAGE = ROOT / "data/processed/official/public-activity-v1"
DEFAULT_AUTHORIZATION = ROOT / "data/interim/official/public-activity-authorization.private.json"
SCHEMA = "sigard-public-activity/1"
MANIFEST_SCHEMA = "sigard-public-activity-manifest/1"
POLICY_VERSION = "sigard-public-activity-minimum5-blocks4-v1"
SCOPE_LEVEL = "radio_censal_bloque_4_semanas_y_ciudad_semanal"
LEVELS = {"protegido", "bajo", "medio", "alto"}
EXCLUDED_YEARS = {2022}
MINIMUM = 5
SOURCE_LABEL = "Ministerio de Salud de La Rioja"
DISABLED = "La vista de actividad registrada no está habilitada"

router = APIRouter(prefix="/api/v1/public", tags=["información pública"])


class ActivityUnavailable(Exception):
    """Stable internal reason; the public response never discloses it."""


def _sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _json(path: Path):
    try:
        return json.loads(path.read_bytes())
    except (OSError, ValueError):
        raise ActivityUnavailable(f"unreadable:{path.name}") from None


def check_authorization(document) -> dict:
    required = ("fecha", "responsable_institucional", "cargo", "alcance", "referencia_documental", "manifest_sha256")
    if not isinstance(document, dict) or any(not document.get(key) for key in required):
        raise ActivityUnavailable("authorization_incomplete")
    try:
        date.fromisoformat(document["fecha"])
    except (TypeError, ValueError):
        raise ActivityUnavailable("authorization_date_invalid") from None
    scope = document["alcance"]
    if (not isinstance(scope, dict) or scope.get("nivel") != SCOPE_LEVEL or not isinstance(scope.get("anios"), list)
            or not all(isinstance(y, int) for y in scope["anios"])):
        raise ActivityUnavailable("authorization_scope_invalid")
    if not re.fullmatch(r"[0-9a-f]{64}", str(document["manifest_sha256"])):
        raise ActivityUnavailable("authorization_manifest_hash_invalid")
    return document


def check_activity(activity, years_allowed) -> None:
    if not isinstance(activity, dict) or activity.get("schema") != SCHEMA:
        raise ActivityUnavailable("activity_schema")
    if activity.get("policy", {}).get("version") != POLICY_VERSION:
        raise ActivityUnavailable("activity_policy")
    blocks = activity.get("blocks")
    if not isinstance(blocks, list) or not blocks:
        raise ActivityUnavailable("activity_empty")
    outside = set(activity.get("outside_radios", []))
    seen = set()
    for block in blocks:
        year = block.get("year")
        if year in EXCLUDED_YEARS or year not in years_allowed:
            raise ActivityUnavailable("activity_year_out_of_scope")
        date.fromisoformat(block["start"]), date.fromisoformat(block["end"])
        weeks = {(year, w) for w in block["weeks"]}
        if weeks & seen:
            raise ActivityUnavailable("activity_overlapping_blocks")
        seen |= weeks
        radios = block.get("radios", {})
        if set(radios.values()) - LEVELS or outside & set(radios):
            raise ActivityUnavailable("activity_radio_values")
        for entry in block.get("city_weeks", []):
            value, display = entry.get("value"), entry.get("display")
            if value is None and display not in ("<5", "oculto") or value is not None and (not isinstance(value, int) or value < MINIMUM):
                raise ActivityUnavailable("activity_city_week")


def load_authorized_package(package_dir: Path, authorization_path: Path) -> dict:
    if not authorization_path.is_file():
        raise ActivityUnavailable("no_authorization")
    authorization = check_authorization(_json(authorization_path))
    try:
        manifest_bytes = (package_dir / "manifest.json").read_bytes()
    except OSError:
        raise ActivityUnavailable("no_manifest") from None
    manifest_sha = _sha(manifest_bytes)
    if manifest_sha != authorization["manifest_sha256"]:
        raise ActivityUnavailable("manifest_not_authorized")
    manifest = json.loads(manifest_bytes)
    if manifest.get("schema") != MANIFEST_SCHEMA or manifest.get("policy_version") != POLICY_VERSION:
        raise ActivityUnavailable("manifest_schema")
    files = manifest.get("files", {})
    if not {"activity.json", "risk-report.json"} <= set(files):
        raise ActivityUnavailable("manifest_files")
    contents = {}
    for name, digest in files.items():
        if "/" in name or "\\" in name or name.startswith("."):
            raise ActivityUnavailable("manifest_file_name")
        try:
            data = (package_dir / name).read_bytes()
        except OSError:
            raise ActivityUnavailable("file_missing") from None
        if _sha(data) != digest:
            raise ActivityUnavailable("file_hash_mismatch")
        contents[name] = data
    risk = json.loads(contents["risk-report.json"])
    if risk.get("status") != "passed" or risk.get("disclosures") != 0 or manifest.get("risk") != {"status": "passed", "disclosures": 0}:
        raise ActivityUnavailable("risk_report_not_passed")
    activity = json.loads(contents["activity.json"])
    if activity.get("source", {}).get("kind") != "real" or manifest.get("source", {}).get("kind") != "real":
        raise ActivityUnavailable("fixture_cannot_be_authorized")
    check_activity(activity, set(authorization["alcance"]["anios"]))
    return dict(activity, source=dict(kind="real", fictional=False, label=SOURCE_LABEL),
                geometry_source="territorial_context",
                package=dict(version=manifest.get("package_version"), manifest_sha256=manifest_sha,
                             generated_at=manifest.get("generated_at")),
                authorization=dict(date=authorization["fecha"]))


def _epi_weeks(year):
    def first_sunday(y):
        jan4 = date(y, 1, 4)
        return jan4 - timedelta(days=(jan4.weekday() + 1) % 7)
    start, end = first_sunday(year), first_sunday(year + 1)
    return [(n + 1, start + timedelta(weeks=n), start + timedelta(weeks=n, days=6)) for n in range((end - start).days // 7)]


def fixture_package() -> dict:
    """Generated fictional package: abstract square cells away from any real cartography."""
    codes = [f"FICT-{i:03d}" for i in range(1, 25)]
    features = [{"type": "Feature", "properties": {"radio_id": code},
                 "geometry": {"type": "Polygon", "coordinates": [[[x, y], [x + .01, y], [x + .01, y + .01], [x, y + .01], [x, y]]]}}
                for index, code in enumerate(codes + ["FICT-900"])
                for x, y in [((index % 5) * .011, (index // 5) * .011)]]
    pattern = ["protegido", "bajo", "medio", "alto", "protegido", "protegido"]
    blocks = []
    for year in (2020, 2021, 2023, 2024):
        weeks = _epi_weeks(year)
        last = 6 if year == 2024 else 13
        for number in range(1, last + 1):
            numbers = list(range(number * 4 - 3, number * 4 + 1)) + ([53] if number == 13 and len(weeks) == 53 else [])
            rows = [weeks[n - 1] for n in numbers]
            radios = {code: pattern[(i + number + year) % len(pattern)] for i, code in enumerate(codes)}
            city = []
            for n, start, end in rows:
                value = (n * 7 + year) % 41
                city.append(dict(year=year, week=n, start=start.isoformat(), end=end.isoformat(),
                                 value=value if value >= MINIMUM else None, display=None if value >= MINIMUM else "<5"))
            if number == 2 and year == 2021:
                for entry in city:
                    entry.update(value=None, display="oculto")
            blocks.append(dict(id=f"{year}-B{number:02d}", year=year, block=number, weeks=numbers,
                               start=rows[0][1].isoformat(), end=rows[-1][2].isoformat(), radios=radios, city_weeks=city))
    period = dict(first_block=blocks[0]["id"], last_block=blocks[-1]["id"], start=blocks[0]["start"], end=blocks[-1]["end"],
                  first_week=dict(year=2020, week=1), last_week=dict(year=2024, week=24))
    return dict(schema=SCHEMA, policy=dict(version=POLICY_VERSION, minimum_count=MINIMUM, min_population=100, block_weeks=4,
                                           levels=[dict(level="bajo", min=5, max=9), dict(level="medio", min=10, max=19),
                                                   dict(level="alto", min=20, max=None)],
                                           protected_label="Menos de 5 registros (protegido)",
                                           excluded_years=[dict(year=2022, reason="classification_differs_suspected_probable_discarded_counted")]),
                period=period, generated_at="2026-11-16", outside_radios=["FICT-900"], blocks=blocks,
                source=dict(kind="fixture", fictional=True, label="Datos ficticios de prueba"),
                geometry_source="inline", geometry={"type": "FeatureCollection", "features": features},
                package=dict(version="fictional-public-activity-v1", manifest_sha256=None, generated_at="2026-11-16"),
                authorization=None)


def resolve_activity(mode: str | None, package_dir: Path, authorization_path: Path) -> dict | None:
    if mode == "fixture":
        return fixture_package()
    try:
        return load_authorized_package(package_dir, authorization_path)
    except (ActivityUnavailable, KeyError, TypeError, ValueError):
        return None


@router.get("/activity")
def get_activity(request: Request, response: Response):
    config = request.app.state.public_activity
    payload = resolve_activity(config["mode"], config["package_dir"], config["authorization"])
    if payload is None:
        raise HTTPException(status_code=404, detail=DISABLED)
    response.headers["Cache-Control"] = "no-cache"
    return payload
