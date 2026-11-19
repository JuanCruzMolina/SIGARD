"""Public activity endpoint: disabled by default, authorization bound to the manifest hash.

Packages here are generated in a temporary folder with fictional radio codes; they only
exercise the verification contract and never reach the frontend or Git.
"""

import hashlib
import json

import pytest
from fastapi.testclient import TestClient

from app.database import Base
from app.main import create_app
from app.public_activity import DISABLED, SCOPE_LEVEL


def _write(path, value):
    data = (json.dumps(value, ensure_ascii=False, sort_keys=True) + "\n").encode()
    path.write_bytes(data)
    return hashlib.sha256(data).hexdigest()


def activity(year=2021, value=7, kind="real"):
    return {
        "schema": "sigard-public-activity/1",
        "policy": {"version": "sigard-public-activity-minimum5-blocks4-v1"},
        "period": {"first_block": f"{year}-B01", "last_block": f"{year}-B01", "start": "2021-01-03", "end": "2021-01-30"},
        "generated_at": "2026-11-16",
        "source": {"kind": kind, "fictional": kind == "fixture"},
        "outside_radios": ["FICT-900"],
        "blocks": [{
            "id": f"{year}-B01", "year": year, "block": 1, "weeks": [1, 2, 3, 4], "start": "2021-01-03", "end": "2021-01-30",
            "radios": {"FICT-001": "bajo", "FICT-002": "protegido"},
            "city_weeks": [{"year": year, "week": 1, "start": "2021-01-03", "end": "2021-01-09", "value": value, "display": None},
                           {"year": year, "week": 2, "start": "2021-01-10", "end": "2021-01-16", "value": None, "display": "<5"}],
        }],
    }


def package(folder, *, content=None, risk=None, kind="real"):
    folder.mkdir(parents=True, exist_ok=True)
    files = {
        "activity.json": _write(folder / "activity.json", content or activity(kind=kind)),
        "risk-report.json": _write(folder / "risk-report.json", risk or {"status": "passed", "disclosures": 0}),
    }
    manifest = {"schema": "sigard-public-activity-manifest/1", "policy_version": "sigard-public-activity-minimum5-blocks4-v1",
                "package_version": "fictional-contract-v1", "generated_at": "2026-11-16", "source": {"kind": kind},
                "risk": {"status": "passed", "disclosures": 0}, "files": files}
    return _write(folder / "manifest.json", manifest)


def authorize(path, manifest_sha, **changes):
    document = {"fecha": "2026-11-20", "responsable_institucional": "Responsable ficticio de prueba", "cargo": "Cargo ficticio",
                "alcance": {"anios": [2020, 2021, 2023, 2024], "nivel": SCOPE_LEVEL},
                "referencia_documental": "Nota ficticia 0000", "manifest_sha256": manifest_sha}
    document.update(changes)
    path.write_text(json.dumps(document), encoding="utf-8")


@pytest.fixture
def configured(client, tmp_path):
    folder, auth = tmp_path / "pkg", tmp_path / "authorization.private.json"
    client.app.state.public_activity = {"mode": None, "package_dir": folder, "authorization": auth}
    return client, folder, auth


def test_disabled_by_default_without_authorization(configured):
    client, folder, _ = configured
    package(folder)
    response = client.get("/api/v1/public/activity")
    assert response.status_code == 404 and response.json() == {"detail": DISABLED}


@pytest.mark.parametrize("value", ["real", "1", "true", "on", "enabled", "FIXTURE"])
def test_environment_alone_never_enables_real_data(monkeypatch, tmp_path, value):
    from app.config import get_settings
    monkeypatch.setenv("SIGARD_PUBLIC_ACTIVITY", value)
    monkeypatch.setenv("PUBLIC_ACTIVITY_DIR", str(tmp_path / "pkg"))
    monkeypatch.setenv("PUBLIC_ACTIVITY_AUTHORIZATION", str(tmp_path / "missing.private.json"))
    package(tmp_path / "pkg")
    get_settings.cache_clear()
    try:
        app = create_app(database_url=f"sqlite:///{tmp_path / 'env.db'}", auto_create_schema=True)
        with TestClient(app) as client:
            assert app.state.public_activity["mode"] is None
            assert client.get("/api/v1/public/activity").status_code == 404
        Base.metadata.drop_all(app.state.engine)
    finally:
        get_settings.cache_clear()


def test_fixture_mode_serves_only_fictional_data(monkeypatch, tmp_path):
    from app.config import get_settings
    monkeypatch.setenv("SIGARD_PUBLIC_ACTIVITY", "fixture")
    get_settings.cache_clear()
    try:
        app = create_app(database_url=f"sqlite:///{tmp_path / 'fx.db'}", auto_create_schema=True)
        with TestClient(app) as client:
            body = client.get("/api/v1/public/activity").json()
        Base.metadata.drop_all(app.state.engine)
    finally:
        get_settings.cache_clear()
    assert body["source"]["fictional"] is True and body["geometry_source"] == "inline"
    ids = {r for b in body["blocks"] for r in b["radios"]} | {f["properties"]["radio_id"] for f in body["geometry"]["features"]}
    assert all(i.startswith("FICT-") for i in ids)
    assert not any(b["year"] == 2022 for b in body["blocks"])
    assert body["period"]["last_week"] == {"year": 2024, "week": 24}
    levels = {lvl for b in body["blocks"] for lvl in b["radios"].values()}
    assert levels == {"protegido", "bajo", "medio", "alto"}
    weeks = [e for b in body["blocks"] for e in b["city_weeks"]]
    assert all(e["value"] is None or e["value"] >= 5 for e in weeks)
    assert {e["display"] for e in weeks} >= {"<5", "oculto", None}


def test_authorized_verified_package_is_served_without_officer_identity(configured):
    client, folder, auth = configured
    authorize(auth, package(folder))
    response = client.get("/api/v1/public/activity")
    assert response.status_code == 200
    body = response.json()
    assert body["authorization"] == {"date": "2026-11-20"}
    assert body["source"]["label"] == "Ministerio de Salud de La Rioja" and body["geometry_source"] == "territorial_context"
    assert body["package"]["generated_at"] == "2026-11-16" and body["period"]["first_block"] == "2021-B01"
    assert "Responsable ficticio" not in response.text and "Nota ficticia" not in response.text
    assert response.headers["cache-control"] == "no-cache"


def test_authorization_is_bound_to_the_manifest_hash(configured):
    client, folder, auth = configured
    authorize(auth, "0" * 64)
    package(folder)
    assert client.get("/api/v1/public/activity").status_code == 404


def test_tampered_file_is_rejected(configured):
    client, folder, auth = configured
    authorize(auth, package(folder))
    content = activity()
    content["blocks"][0]["radios"]["FICT-002"] = "bajo"
    (folder / "activity.json").write_text(json.dumps(content), encoding="utf-8")
    assert client.get("/api/v1/public/activity").status_code == 404


@pytest.mark.parametrize("risk", [{"status": "failed", "disclosures": 1}, {"status": "passed", "disclosures": 2}])
def test_risk_report_must_pass_with_zero_disclosures(configured, risk):
    client, folder, auth = configured
    authorize(auth, package(folder, risk=risk))
    assert client.get("/api/v1/public/activity").status_code == 404


@pytest.mark.parametrize("content", [activity(year=2022), activity(year=2019), activity(value=3)])
def test_content_outside_contract_or_scope_is_rejected(configured, content):
    client, folder, auth = configured
    authorize(auth, package(folder, content=content))
    assert client.get("/api/v1/public/activity").status_code == 404


def test_fixture_package_cannot_be_authorized_as_real(configured):
    client, folder, auth = configured
    authorize(auth, package(folder, content=activity(kind="fixture"), kind="fixture"))
    assert client.get("/api/v1/public/activity").status_code == 404


@pytest.mark.parametrize("change", [{"fecha": "ayer"}, {"responsable_institucional": ""}, {"referencia_documental": None},
                                    {"alcance": {"anios": [2021], "nivel": "otro"}}, {"manifest_sha256": "abc"}])
def test_incomplete_authorization_is_rejected(configured, change):
    client, folder, auth = configured
    authorize(auth, package(folder), **change)
    assert client.get("/api/v1/public/activity").status_code == 404
