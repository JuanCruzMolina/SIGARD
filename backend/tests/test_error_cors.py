"""Error responses keep the CORS headers of an allowed origin, so the page can show the
server's message instead of a silent network failure. Unknown origins never get them."""
from fastapi.testclient import TestClient

from app.config import get_settings
from app.database import Base
from app.main import create_app


class _Source:
    def preload(self):
        return None


def _app(tmp_path):
    app = create_app(database_url=f"sqlite:///{tmp_path / 'errors.db'}", auto_create_schema=True)
    Base.metadata.create_all(app.state.engine)

    def boom():
        raise RuntimeError("fallo ficticio no controlado")
    app.add_api_route("/api/v1/admin/prueba-error-no-controlado", boom, methods=["GET"])
    return app


def test_unhandled_error_keeps_cors_for_allowed_origin_only(tmp_path):
    origin = get_settings().allowed_origins[0]
    with TestClient(_app(tmp_path), raise_server_exceptions=False) as client:
        allowed = client.get("/api/v1/admin/prueba-error-no-controlado", headers={"Origin": origin})
        assert allowed.status_code == 500
        assert allowed.headers["access-control-allow-origin"] == origin
        assert allowed.json() == {"detail": "Error interno del servidor. Intentá nuevamente."}
        assert "fallo ficticio" not in allowed.text  # no internal detail leaks
        unknown = client.get("/api/v1/admin/prueba-error-no-controlado", headers={"Origin": "http://otro.example"})
        assert unknown.status_code == 500 and "access-control-allow-origin" not in unknown.headers
        without = client.get("/api/v1/admin/prueba-error-no-controlado")
        assert without.status_code == 500 and "access-control-allow-origin" not in without.headers


def test_handled_login_errors_keep_cors(tmp_path):
    origin = get_settings().allowed_origins[0]
    with TestClient(_app(tmp_path)) as client:
        response = client.post("/api/v1/admin/session", headers={"Origin": origin},
                               json={"email": "nadie@example.test", "password": "contraseña-ficticia-larga"})
        assert response.status_code == 401
        assert response.headers["access-control-allow-origin"] == origin


def test_local_api_geocoding_refusal_keeps_cors_for_the_local_origin(tmp_path):
    from app import alerts_local
    app = _app(tmp_path)
    alerts_local.attach(app, _Source(), "disposable-sqlite")
    with TestClient(app) as client:
        local = client.post("/api/v1/geocoding/address", headers={"Origin": alerts_local.ORIGIN}, json={"address_reference": "Lugar ficticio"})
        assert local.status_code == 503
        assert local.headers["access-control-allow-origin"] == alerts_local.ORIGIN
        assert local.json() == {"detail": "No disponible en el entorno local de alertas."}
        other = client.post("/api/v1/geocoding/address", headers={"Origin": "http://otro.example"}, json={"address_reference": "Lugar ficticio"})
        assert other.status_code == 503 and "access-control-allow-origin" not in other.headers
