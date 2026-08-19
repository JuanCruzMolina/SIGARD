from datetime import datetime, timedelta, timezone

from sqlalchemy import func, select

from app.models import User
from app.config import get_settings
from app.schemas import PRIVACY_NOTICE_VERSION
from app.retention import purge_expired
from app.security import hash_password


VALID_REPORT = {
    "category": "agua_acumulada",
    "description": "Hay varios recipientes con agua estancada junto a la vereda.",
    "latitude": -29.4135,
    "longitude": -66.8560,
    "address_reference": "Esquina cercana a la plaza",
    "neighborhood": "Centro",
    "privacy_notice_version": PRIVACY_NOTICE_VERSION,
    "privacy_accepted": True,
}


def test_anonymous_report_and_public_status_do_not_expose_location(client):
    response = client.post(
        "/api/v1/citizen-reports",
        json=VALID_REPORT,
        headers={"Idempotency-Key": "test-submission-1"},
    )
    assert response.status_code == 201
    tracking_code = response.json()["tracking_code"]
    assert tracking_code.startswith("SGD-RPT-")

    public = client.get(f"/api/v1/citizen-reports/status/{tracking_code}")
    assert public.status_code == 200
    assert set(public.json()) == {
        "tracking_code", "status", "created_at", "updated_at", "public_status_message"
    }


def test_idempotency_returns_the_same_tracking_code(client):
    first = client.post(
        "/api/v1/citizen-reports", json=VALID_REPORT, headers={"Idempotency-Key": "retry-key"}
    )
    second = client.post(
        "/api/v1/citizen-reports", json=VALID_REPORT, headers={"Idempotency-Key": "retry-key"}
    )
    assert first.json()["tracking_code"] == second.json()["tracking_code"]


def test_rejects_outside_city_and_direct_contact_data(client):
    outside = {**VALID_REPORT, "latitude": -30.0}
    assert client.post("/api/v1/citizen-reports", json=outside).status_code == 422

    with_email = {**VALID_REPORT, "description": "Hay agua acumulada. Escribirme a persona@example.com por favor."}
    assert client.post("/api/v1/citizen-reports", json=with_email).status_code == 422

    with_dni_in_reference = {**VALID_REPORT, "address_reference": "Domicilio asociado al DNI 12345678"}
    assert client.post("/api/v1/citizen-reports", json=with_dni_in_reference).status_code == 422


def test_admin_can_review_and_update_with_publicly_safe_result(client):
    with client.app.state.SessionLocal() as db:
        db.add(User(email="admin@test.local", password_hash=hash_password("secure-test-password"), rol="admin"))
        db.commit()

    token_response = client.post(
        "/api/v1/admin/session",
        json={"email": "admin@test.local", "password": "secure-test-password"},
    )
    token = token_response.json()["access_token"]
    headers = {"Authorization": f"Bearer {token}"}

    created = client.post("/api/v1/citizen-reports", json=VALID_REPORT).json()
    listing = client.get("/api/v1/admin/citizen-reports", headers=headers)
    assert listing.status_code == 200
    report_id = listing.json()["items"][0]["id"]

    detail = client.get(f"/api/v1/admin/citizen-reports/{report_id}", headers=headers)
    assert detail.json()["latitude"] == VALID_REPORT["latitude"]
    update = client.patch(
        f"/api/v1/admin/citizen-reports/{report_id}",
        headers=headers,
        json={"status": "en_revision", "public_status_message": "El equipo está revisando el reporte."},
    )
    assert update.status_code == 200

    public = client.get(f"/api/v1/citizen-reports/status/{created['tracking_code']}").json()
    assert public["status"] == "en_revision"
    assert "latitude" not in public and "description" not in public


def test_nearby_same_category_is_marked_as_possible_duplicate(client):
    client.post(
        "/api/v1/citizen-reports",
        json=VALID_REPORT,
        headers={"Idempotency-Key": "original-nearby-report"},
    )
    nearby = {**VALID_REPORT, "latitude": VALID_REPORT["latitude"] + 0.0003}
    client.post(
        "/api/v1/citizen-reports",
        json=nearby,
        headers={"Idempotency-Key": "second-nearby-report"},
    )
    with client.app.state.SessionLocal() as db:
        from sqlalchemy import select
        from app.models import CitizenReport
        reports = db.scalars(select(CitizenReport).order_by(CitizenReport.created_at)).all()
        assert reports[1].possible_duplicate_of == reports[0].id


def test_retention_removes_only_expired_reports(client):
    from app.models import CitizenReport

    now = datetime.now(timezone.utc)
    common = {
        "category": "agua_acumulada",
        "description": "Reporte de prueba para verificar la política de retención.",
        "latitude": -29.4135,
        "longitude": -66.8560,
        "status": "recibido",
        "privacy_notice_version": PRIVACY_NOTICE_VERSION,
        "created_at": now,
        "updated_at": now,
    }
    with client.app.state.SessionLocal() as db:
        db.add_all([
            CitizenReport(tracking_code="SGD-RPT-OLD001", retention_until=now - timedelta(days=1), **common),
            CitizenReport(tracking_code="SGD-RPT-KEEP01", retention_until=now + timedelta(days=1), **common),
        ])
        db.commit()

    assert purge_expired(str(client.app.state.engine.url)) == 1
    with client.app.state.SessionLocal() as db:
        assert db.scalar(select(func.count()).select_from(CitizenReport)) == 1


def test_geocoding_uses_server_proxy_and_rejects_direct_identifiers(client, monkeypatch):
    class FakeResponse:
        def raise_for_status(self):
            return None

        def json(self):
            return [{"lat": "-29.415", "lon": "-66.855", "display_name": "Plaza, La Rioja"}]

    class FakeClient:
        def __init__(self, *args, **kwargs):
            pass

        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

        def get(self, url, params):
            assert url == "https://nominatim.openstreetmap.org/search"
            assert "La Rioja Capital" in params["q"]
            return FakeResponse()

    monkeypatch.setattr("app.geocoding.httpx.Client", FakeClient)
    found = client.post("/api/v1/geocoding/address", json={"address_reference": "Plaza principal"})
    assert found.status_code == 200
    assert found.json()["latitude"] == -29.415
    rejected = client.post(
        "/api/v1/geocoding/address",
        json={"address_reference": "Domicilio de persona@example.com"},
    )
    assert rejected.status_code == 422


def test_admin_login_is_rate_limited(client):
    settings = get_settings()
    original_limit = settings.admin_login_rate_limit
    settings.admin_login_rate_limit = 2
    try:
        payload = {"email": "rate-limit@test.local", "password": "incorrect-password"}
        assert client.post("/api/v1/admin/session", json=payload).status_code == 401
        assert client.post("/api/v1/admin/session", json=payload).status_code == 401
        assert client.post("/api/v1/admin/session", json=payload).status_code == 429
    finally:
        settings.admin_login_rate_limit = original_limit


def test_csv_export_sanitizes_spreadsheet_formulas(client):
    with client.app.state.SessionLocal() as db:
        db.add(User(email="export@test.local", password_hash=hash_password("secure-export-password"), rol="admin"))
        db.commit()
    token = client.post(
        "/api/v1/admin/session",
        json={"email": "export@test.local", "password": "secure-export-password"},
    ).json()["access_token"]
    payload = {**VALID_REPORT, "description": "=2+2 posible fórmula en una planilla exportada"}
    assert client.post("/api/v1/citizen-reports", json=payload).status_code == 201
    exported = client.get(
        "/api/v1/admin/citizen-reports/export.csv",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert exported.status_code == 200
    assert "'=2+2" in exported.text
    assert exported.headers["cache-control"] == "no-store"
