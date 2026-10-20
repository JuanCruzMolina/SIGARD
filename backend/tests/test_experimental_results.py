"""All artifacts here are fictional; never open the local epidemiological files."""

import hashlib
import json
import shutil
import subprocess
from datetime import date, timedelta
from pathlib import Path

import httpx
import pytest

pa = pytest.importorskip("pyarrow", reason="Instalar requirements.research.txt para las pruebas locales A/B")
import pyarrow.parquet as pq

from app.experimental_api import create_research_app, PREFIX
from app.experimental_results import (
    ROOT, MODELS, MISSING, SCHEMA, TERRITORY, ArtifactBlocked, ExperimentalResults, NotAvailable,
    METRICS,
)
from app.main import create_app

TRUSTED = {"Origin": "http://127.0.0.1:5173", "X-Sigard-Research": "local-read"}
WEEK = "2024-01-07"


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def write_json(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value), encoding="utf-8")


@pytest.fixture
def artifacts(tmp_path):
    root = tmp_path / "fictional"
    geo = root / "frontend/public/data/territorial_context.geojson"
    write_json(geo, {"type": "FeatureCollection", "features": [{"properties": {"radio_id": f"000{i:03}"}} for i in range(263)]})
    write_json(root / "frontend/security/public-assets.json", {"assets": {"data/territorial_context.geojson": digest(geo)}})
    cal = root / "ml/src/sigard_ml/official/calendar_rules.py"
    cal.parent.mkdir(parents=True)
    shutil.copyfile(ROOT / "ml/src/sigard_ml/official/calendar_rules.py", cal)
    targets = [date(2024, 1, 7) + timedelta(weeks=i) for i in range(8)] + [date(2024, 3, 10) + timedelta(weeks=i) for i in range(8)] + [date(2024, 5, 12) + timedelta(weeks=i) for i in range(4)]
    registry_path = root / "data/interim/official/session/registry.private.json"
    registry = {"schema_version": SCHEMA, "local_read_authorized": True, "territory_version": TERRITORY, "models": {}}
    frames = {}
    for model, (experiment, version) in MODELS.items():
        folder = root / "data/processed/official" / experiment
        folder.mkdir(parents=True)
        rows, matrix = [], []
        for index, target in enumerate(targets):
            for i in range(263):
                key = {"radio_censal": f"000{i:03}", "fecha_inicio_semana": target - timedelta(days=7)}
                rows.append({**key, "fecha_inicio_semana_objetivo": target,
                    "partition": "train" if index < 8 else "validation" if index < 16 else "test",
                    f"random_forest_{model}_probability": None if i == 0 else (0.0 if i == 1 else .2 if model == "A" else .4),
                    "objetivo_semana_siguiente": "PRIVATE_FICTIONAL_LABEL",
                    "patient_name": "PRIVATE_FICTIONAL_PERSON", "latitude": 123.456})
                matrix.append({**key, **{k: (1 if i == 0 else 0 if i == 1 else j % 2) for j, k in enumerate(MISSING)},
                               "private_lag_value": "PRIVATE_FICTIONAL_LAG"})
        frames[model] = rows
        pq.write_table(pa.Table.from_pylist(rows), folder / "predictions_radio_week.private.parquet")
        if model == "B":
            pq.write_table(pa.Table.from_pylist(matrix), folder / "inference_matrix.private.parquet")
            metrics = [{"model": name, "partition": part, "threshold": .5,
                "grid_rows": 263 * count, "n": 263 * count - 10, "positive": 20,
                "negative": 263 * count - 30, "unknown_excluded": 10,
                **{metric: (.2 if name == "random_forest_A" else .4) for metric in METRICS},
                "patient_name": "PRIVATE_FICTIONAL_PERSON"}
                for name in ("random_forest_A", "random_forest_B", "training_prevalence")
                for part, count in (("train", 8), ("validation", 8), ("test", 4))]
            metrics[0]["precision"] = None
            pq.write_table(pa.Table.from_pylist(metrics), folder / "metrics.private.parquet")
        write_json(folder / "metadata.private.json", {"version": version, "calendar_version": "ar-snvs-2020-2026-v1"})
        write_json(folder / "review.private.json", {"version": version, "training_authorized": False,
            "research_training_authorized": True, "coverage_verified": False,
            "operational_model_enabled": False, "test_previously_examined": True})
        registry["models"][model] = {}

    def pin():
        for model, (experiment, version) in MODELS.items():
            folder = root / "data/processed/official" / experiment
            manifest = folder / "integrity_manifest.private.json"
            write_json(manifest, {"version": version, "outputs_sha256": {p.name: digest(p) for p in folder.iterdir() if p != manifest}})
            if model in registry["models"]:
                registry["models"][model] = {"manifest_sha256": digest(manifest)}
        write_json(registry_path, registry)
        return ExperimentalResults(registry_path, digest(registry_path), root=root)

    return root, frames, registry, pin


def test_readonly_projection_and_missing_status(artifacts, monkeypatch):
    root, _, _, pin = artifacts
    adapter = pin()
    before = {p: digest(p) for p in root.rglob("*") if p.is_file()}
    original = pq.ParquetFile.read
    projections = []

    def bounded_read(self, columns=None, **kwargs):
        projections.extend(columns)
        return original(self, columns=columns, **kwargs)

    monkeypatch.setattr(pq.ParquetFile, "read", bounded_read)
    catalog = adapter.list_experiments()
    assert [m["model_id"] for m in catalog["models"]] == ["A", "B"]
    assert [len(m["weeks"]) for m in catalog["models"]] == [20, 20]
    result = adapter.get_retrospective_scores("B", MODELS["B"][0], WEEK)
    missing, zero, partial = result["rows"][:3]
    assert missing["experimental_score"] is None and missing["score_status"] == "not_computed"
    assert missing["data_availability"]["known_lag_count"] == 0
    assert zero["experimental_score"] == 0 and zero["score_status"] == "available"
    assert zero["data_availability"]["known_lag_count"] == 4
    assert partial["data_availability"]["known_lag_count"] == 2
    assert result["target_epidemiological_week"] == 2
    assert "PRIVATE_FICTIONAL" not in json.dumps(result)
    assert "objetivo_semana_siguiente" not in projections and "private_lag_value" not in projections
    assert before == {p: digest(p) for p in root.rglob("*") if p.is_file()}


@pytest.mark.parametrize("model,experiment,target", [("C", "x", WEEK), ("A", "wrong", WEEK),
    ("A", MODELS["A"][0], "2024-03-03"), ("A", MODELS["A"][0], "2026-10-18")])
def test_unavailable_queries(artifacts, model, experiment, target):
    with pytest.raises(NotAvailable):
        artifacts[3]().get_retrospective_scores(model, experiment, target)


@pytest.mark.parametrize("filename", ["predictions_radio_week.private.parquet", "integrity_manifest.private.json", "review.private.json", "inference_matrix.private.parquet"])
def test_mutation_blocks_even_after_successful_query(artifacts, filename):
    root, _, _, pin = artifacts
    adapter = pin()
    adapter.list_experiments()
    p = root / "data/processed/official" / MODELS["B"][0] / filename
    p.write_bytes(p.read_bytes() + b"corrupt")
    with pytest.raises(ArtifactBlocked):
        adapter.list_experiments()


@pytest.mark.parametrize("mutation", ["duplicate", "missing_radio", "nan", "range", "date", "partition", "numeric_radio", "version", "authorization", "mask", "registry_extra"])
def test_invalid_artifacts_with_new_hash_still_blocked(artifacts, mutation):
    root, frames, registry, pin = artifacts
    folder = root / "data/processed/official" / MODELS["B"][0]
    rows = frames["B"]
    if mutation == "duplicate": rows[1] = rows[0]
    if mutation == "missing_radio": rows.pop()
    if mutation == "nan": rows[0]["random_forest_B_probability"] = float("nan")
    if mutation == "range": rows[0]["random_forest_B_probability"] = 1.1
    if mutation == "date": rows[0]["fecha_inicio_semana_objetivo"] += timedelta(days=1)
    if mutation == "partition": rows[0]["partition"] = "test"
    if mutation == "numeric_radio": rows[0]["radio_censal"] = "999999"
    pq.write_table(pa.Table.from_pylist(rows), folder / "predictions_radio_week.private.parquet")
    if mutation in {"version", "authorization"}:
        p = folder / "review.private.json"
        value = json.loads(p.read_text())
        value["version" if mutation == "version" else "training_authorized"] = "wrong" if mutation == "version" else True
        write_json(p, value)
    if mutation == "mask":
        p = folder / "inference_matrix.private.parquet"
        matrix = pq.read_table(p).to_pylist(); matrix[0][MISSING[0]] = 2
        pq.write_table(pa.Table.from_pylist(matrix), p)
    if mutation == "registry_extra": registry["arbitrary_path"] = "data/raw/patients"
    with pytest.raises(ArtifactBlocked): pin().list_experiments()


def test_comparison_and_one_model_missing(artifacts):
    _, _, registry, pin = artifacts
    adapter = pin()
    comparison = adapter.compare("000002", WEEK)
    assert comparison["comparable"] is True
    assert [c["rows"][0]["experimental_score"] for c in comparison["results"]] == [.2, .4]
    assert not adapter.compare("000000", WEEK)["comparable"]
    assert all(c["target_week_start"] == WEEK for c in comparison["results"])
    del registry["models"]["B"]
    one_model = pin()
    assert one_model.compare("000002", WEEK)["comparable"] is False
    with pytest.raises(NotAvailable): one_model.compare("bad", WEEK)


def test_backend_frontend_contract(artifacts):
    adapter = artifacts[3]()
    result = adapter.get_retrospective_scores("A", MODELS["A"][0], WEEK)
    script = """
import {validateCatalog,validateScores,joinExperimentalGeometry,experimentalColor} from './frontend/src/services/experimentalContract.mjs';
let text=''; for await (const chunk of process.stdin) text+=chunk;
const {catalog,scores}=JSON.parse(text); validateCatalog(catalog);
const radios=scores.rows.map(r=>r.radio_censal);
validateScores(scores,catalog.models[0],scores.target_week_start,radios);
const geometry={features:radios.map(r=>({properties:{radio_id:r},geometry:{type:'Polygon',coordinates:[]}}))};
if(joinExperimentalGeometry(geometry,scores).features[0].properties.experimental_score!==null) throw Error('null lost');
if(experimentalColor(null)===experimentalColor(0)) throw Error('missing equals zero');
scores.rows[0].experimental_score=0;
let blocked=false; try {validateScores(scores,catalog.models[0],scores.target_week_start,radios)} catch {blocked=true}
if(!blocked) throw Error('invalid null accepted');
"""
    run = subprocess.run([shutil.which("node"), "--input-type=module", "-e", script], cwd=ROOT,
        input=json.dumps({"catalog": adapter.list_experiments(), "scores": result}), text=True, capture_output=True)
    assert run.returncode == 0, run.stderr


def test_frozen_evaluation_and_history_project_only_allowed_aggregates(artifacts):
    root, _, _, pin = artifacts
    adapter = pin()
    before = {p: digest(p) for p in root.rglob("*") if p.is_file()}
    evaluation = adapter.get_evaluation()
    assert len(evaluation["partitions"]) == 3
    assert evaluation["partitions"][0]["models"][0]["metrics"]["precision"] is None
    for part in evaluation["partitions"]:
        assert [m["model_id"] for m in part["models"]] == ["A", "B"]
        assert all(set(m["metrics"]) == set(METRICS) for m in part["models"])
    history = adapter.history("000002")
    assert len(history["comparisons"]) == 20
    assert all(len(result["rows"]) == 1 for c in history["comparisons"] for result in c["results"])
    assert all(c["comparable"] for c in history["comparisons"])
    for forbidden in ("PRIVATE_FICTIONAL", "positive", "negative", str(root), "patient_name"):
        # Limitations include assumed_negatives by design; test exact private fields separately.
        if forbidden in ("positive", "negative"):
            assert f'"{forbidden}":' not in json.dumps(evaluation)
        else:
            assert forbidden not in json.dumps([evaluation, history])
    assert before == {p: digest(p) for p in root.rglob("*") if p.is_file()}


@pytest.mark.parametrize("problem", ["nan", "range", "threshold", "cohort", "duplicate"])
def test_invalid_metrics_block_even_with_a_new_manifest_hash(artifacts, problem):
    root, _, _, pin = artifacts
    path = root / "data/processed/official" / MODELS["B"][0] / "metrics.private.parquet"
    rows = pq.read_table(path).to_pylist()
    if problem == "nan": rows[1]["roc_auc"] = float("nan")
    if problem == "range": rows[1]["brier"] = 1.1
    if problem == "threshold": rows[1]["threshold"] = .7
    if problem == "cohort": rows[3]["positive"] += 1; rows[3]["negative"] -= 1
    if problem == "duplicate": rows[1] = rows[0]
    pq.write_table(pa.Table.from_pylist(rows), path)
    with pytest.raises(ArtifactBlocked): pin().get_evaluation()


def test_missing_metrics_do_not_disable_scores_and_tampering_blocks_evaluation(artifacts):
    root, _, registry, pin = artifacts
    path = root / "data/processed/official" / MODELS["B"][0] / "metrics.private.parquet"
    adapter = pin()
    path.write_bytes(b"FICTIONAL_TAMPER")
    with pytest.raises(ArtifactBlocked): adapter.get_evaluation()
    path.unlink()
    adapter = pin()
    with pytest.raises(NotAvailable): adapter.get_evaluation()
    assert adapter.get_retrospective_scores("A", MODELS["A"][0], WEEK)["rows"]
    del registry["models"]["B"]
    adapter = pin()
    with pytest.raises(NotAvailable): adapter.get_evaluation()
    assert not adapter.history("000002")["comparisons"][0]["comparable"]


def test_analysis_backend_frontend_contract(artifacts):
    adapter = artifacts[3]()
    script = """
import {validateEvaluation,validateHistory} from './frontend/src/services/experimentalAnalysis.mjs';
let data=''; for await (const chunk of process.stdin) data+=chunk;
const {catalog,evaluation,history}=JSON.parse(data);
validateEvaluation(evaluation,catalog); validateHistory(history,catalog,'000002');
"""
    result = subprocess.run([shutil.which("node"), "--input-type=module", "-e", script], cwd=ROOT,
        input=json.dumps({"catalog": adapter.list_experiments(), "evaluation": adapter.get_evaluation(), "history": adapter.history("000002")}),
        text=True, capture_output=True)
    assert result.returncode == 0, result.stderr


@pytest.mark.anyio
async def test_analysis_routes_keep_local_guards_and_read_only_contract(artifacts):
    app = create_research_app(artifacts[3]())
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app, client=("127.0.0.1", 2000)), base_url="http://127.0.0.1:8765") as c:
        for path in (PREFIX + "/evaluation", PREFIX + "/history/000002"):
            assert (await c.get(path)).status_code == 403
            response = await c.get(path, headers=TRUSTED)
            assert response.status_code == 200 and response.headers["cache-control"] == "no-store, private"
            assert "PRIVATE_FICTIONAL" not in response.text
            assert (await c.get(path + "?file=private", headers=TRUSTED)).status_code == 400
            assert (await c.post(path, headers=TRUSTED)).status_code == 405


def test_disabled_by_default(client, monkeypatch):
    monkeypatch.setenv("SIGARD_LOCAL_RESEARCH", "true")
    app = create_app(database_url="sqlite://")
    assert not any(route.path.startswith("/api/v1/research") for route in app.routes)
    app.state.engine.dispose()
    assert client.get(PREFIX + "/models").status_code == 404
    assert client.post(PREFIX + "/session/request", json={}, headers=TRUSTED).status_code == 404
    assert "/research/" not in json.dumps(client.get("/openapi.json").json())


@pytest.fixture
def anyio_backend():
    return "asyncio"


@pytest.mark.anyio
async def test_direct_readonly_api_without_authentication(artifacts):
    app = create_research_app(artifacts[3]())
    path = PREFIX + "/models"
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app, client=("127.0.0.1", 2000)), base_url="http://127.0.0.1:8765") as c:
        response = await c.get(path, headers=TRUSTED)
        assert response.status_code == 200
        catalog = response.json()
        assert [m["model_id"] for m in catalog["models"]] == ["A", "B"]
        assert not c.cookies
        for model in catalog["models"]:
            weeks = await c.get(path + f"/{model['model_id']}/weeks", headers=TRUSTED)
            assert weeks.json()["weeks"] == model["weeks"]
            for week in model["weeks"]:
                result = await c.get(path + f"/{model['model_id']}/scores/{week['target_week_start']}",
                                     params={"experiment_id": model["experiment_id"]}, headers=TRUSTED)
                assert result.status_code == 200
                assert len(result.json()["rows"]) == 263
                assert "PRIVATE_FICTIONAL" not in result.text and str(artifacts[0]) not in result.text
                for row in result.json()["rows"]:
                    assert set(row) == {"radio_censal", "experimental_score", "score_status", "score_unavailable_reason", "data_availability"}
                    assert set(row["data_availability"]) == {"historical_context", "epidemiological_history", "known_lag_count", "operational_availability", "prediction_as_of"}
                assert "set-cookie" not in result.headers and "www-authenticate" not in result.headers
                assert "access-control-allow-credentials" not in result.headers
        for radio, comparable in [("000002", True), ("000000", False)]:
            response = await c.get(PREFIX + f"/comparison/{WEEK}/{radio}", headers=TRUSTED)
            assert response.status_code == 200 and response.json()["comparable"] is comparable
            assert "PRIVATE_FICTIONAL" not in response.text
        assert (await c.get(path + "/C/weeks", headers=TRUSTED)).status_code == 404
        assert (await c.get(PREFIX + "/comparison/2024-03-03/000002", headers=TRUSTED)).status_code == 404
        for suffix in ("?path=secret", "?model=A&model=B"):
            assert (await c.get(path + suffix, headers=TRUSTED)).status_code == 400
        assert (await c.get("/health")).json() == {"status": "ok"}
        # No approval routes, private admin/report API, files or schema on this listener.
        for route in (PREFIX + "/session", PREFIX + "/session/request", PREFIX + "/session/claim", PREFIX + "/session/logout",
                      "/api/v1/admin/citizen-reports", "/api/v1/citizen-reports", "/docs", "/openapi.json",
                      "/data/processed/official/spatial_rf_05c_v1/predictions_radio_week.private.parquet",
                      "/.env", "/ml/models/model.joblib", "/data/datos%20oficiales/source.xlsx"):
            assert (await c.get(route, headers=TRUSTED)).status_code == 404
        for method in ("POST", "PUT", "PATCH", "DELETE"):
            assert (await c.request(method, path, headers=TRUSTED, json={})).status_code == 405
        assert not c.cookies


@pytest.mark.anyio
async def test_local_network_origin_and_browser_restrictions(artifacts):
    app = create_research_app(artifacts[3]())
    path = PREFIX + "/models"
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app, client=("127.0.0.1", 2000)), base_url="http://127.0.0.1:8765") as c:
        for headers in ({}, {"Origin": TRUSTED["Origin"]}, {**TRUSTED, "X-Sigard-Research": "wrong"},
                        {**TRUSTED, "Origin": "http://localhost:5173"}, {**TRUSTED, "Origin": "https://foreign.example"},
                        {**TRUSTED, "Origin": "http://127.0.0.1:9000"}, {**TRUSTED, "Host": "evil.example"},
                        {**TRUSTED, "Host": "127.0.0.1:9000"}, {**TRUSTED, "Sec-Fetch-Site": "cross-site"},
                        {**TRUSTED, "X-Forwarded-For": "127.0.0.1"}, {**TRUSTED, "Forwarded": "for=127.0.0.1"},
                        {**TRUSTED, "X-Real-IP": "127.0.0.1"}):
            response = await c.get(path, headers=headers)
            assert response.status_code == 403 and "no-store" in response.headers["cache-control"]
            assert "set-cookie" not in response.headers and "www-authenticate" not in response.headers
            assert "access-control-allow-credentials" not in response.headers
            if headers.get("Origin") != TRUSTED["Origin"]:
                assert "access-control-allow-origin" not in response.headers
        for duplicate in ("origin", "host", "x-sigard-research"):
            headers = list(TRUSTED.items()) + [(duplicate, TRUSTED.get(duplicate.title(), "127.0.0.1:8765"))]
            if duplicate == "host": headers.append(("Host", "127.0.0.1:8765"))
            assert (await c.get(path, headers=headers)).status_code == 403
        response = await c.options(path, headers={"Origin": TRUSTED["Origin"], "Access-Control-Request-Method": "GET", "Access-Control-Request-Headers": "X-Sigard-Research"})
        assert response.status_code == 200
        assert response.headers["access-control-allow-origin"] == TRUSTED["Origin"]
        assert "access-control-allow-credentials" not in response.headers
        response = await c.options(path, headers={"Origin": TRUSTED["Origin"], "Access-Control-Request-Method": "POST"})
        assert response.status_code == 400
        response = await c.get(path, headers={"Origin": TRUSTED["Origin"]})
        assert response.status_code == 403
        assert response.headers["access-control-allow-origin"] == TRUSTED["Origin"]
        assert "origin" in response.headers["vary"].lower()
    for peer in ("198.51.100.1", "192.168.1.2", "::1", "testclient"):
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app, client=(peer, 1234)), base_url="http://127.0.0.1:8765") as c:
            for endpoint in (path, "/health"):
                response = await c.get(endpoint, headers=TRUSTED)
                assert response.status_code == 403 and "access-control-allow-origin" not in response.headers


@pytest.mark.anyio
async def test_integrity_failure_has_no_private_details_or_fallback(artifacts):
    app = create_research_app(artifacts[3]())
    broken = artifacts[0] / "data/processed/official" / MODELS["A"][0] / "predictions_radio_week.private.parquet"
    broken.write_bytes(b"bad")
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app, client=("127.0.0.1", 2000)), base_url="http://127.0.0.1:8765") as c:
        for path in ("/models", f"/models/A/scores/{WEEK}?experiment_id={MODELS['A'][0]}", f"/comparison/{WEEK}/000002"):
            response = await c.get(PREFIX + path, headers=TRUSTED)
            assert response.status_code == 503
            assert response.json() == {"detail": "experimental_artifacts_blocked"}
            assert response.headers["access-control-allow-origin"] == TRUSTED["Origin"]
            assert "no-store" in response.headers["cache-control"]
            assert str(artifacts[0]) not in response.text


def test_launcher_fixed_socket_without_credentials(monkeypatch, artifacts):
    import app.research_local as launcher
    import uvicorn
    monkeypatch.delenv("SECRET_KEY", raising=False)
    monkeypatch.delenv("DATABASE_URL", raising=False)
    monkeypatch.setattr(launcher, "local_bytes", lambda *args: b"fictional registry")
    monkeypatch.setattr(launcher, "ExperimentalResults", lambda *args: artifacts[3]())
    captured = {}
    monkeypatch.setattr(uvicorn, "run", lambda app, **kwargs: captured.update(kwargs))
    launcher.main()
    assert captured["host"] == "127.0.0.1" and captured["port"] == 8765
    assert captured["proxy_headers"] is False and captured["access_log"] is False
    assert captured["server_header"] is False
    for environment in ("VERCEL", "RENDER", "RAILWAY_ENVIRONMENT", "WEBSITE_INSTANCE_ID", "K_SERVICE"):
        monkeypatch.setenv(environment, "1")
        with pytest.raises(SystemExit): launcher.main()
        monkeypatch.delenv(environment)
    monkeypatch.setattr(launcher, "Path", lambda path: type("Container", (), {"exists": lambda self: True})())
    with pytest.raises(SystemExit): launcher.main()
