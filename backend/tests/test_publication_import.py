"""Real importer and SQL transactions, with a deliberately narrow SQLite adapter.

The four spatial UDFs ONLY admit the generated fixture's known geometries.
They are transport/verdict stubs, not PostGIS or a topology implementation.
"""

from copy import deepcopy
from datetime import date
import json

from fastapi import FastAPI
from fastapi.testclient import TestClient
import pytest
from sqlalchemy import create_engine, event, func, select, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app import publication_import as importer
from app.database import Base, get_db
from app.models import (
    ExperimentalSpatialResult, PublicationBatch, PublicationWeek,
    TemporalPrediction, TerritorialRadio,
)
from app.public import router
from publication_fixture import CUTOFF, publication_documents, write_publication


@pytest.fixture
def documents():
    return publication_documents()


@pytest.fixture
def source(tmp_path, documents):
    return write_publication(tmp_path / "contracts", documents)


def change(document, path, value):
    for key in path[:-1]:
        document = document[key]
    if value is DELETE:
        del document[path[-1]]
    else:
        document[path[-1]] = value


DELETE = object()
TERRITORIAL = "territorial_context.geojson"
EXPERIMENTAL = "experimental_spatial_history.geojson"


def test_smallest_complete_fixture_is_deterministic_and_preserves_contract(tmp_path, source, documents):
    payload = importer.load_and_validate(source)
    repeated = importer.load_and_validate(write_publication(tmp_path / "repeat", publication_documents()))
    assert payload == repeated
    assert len(payload.weeks) == len(payload.predictions) == 1
    assert len(payload.territorial_features) == len(payload.experimental_features) == 263
    assert payload.metadata == documents["mvp_metadata.json"]
    assert payload.territorial_features == documents[TERRITORIAL]["features"]
    assert payload.experimental_features == documents[EXPERIMENTAL]["features"]
    assert {f["properties"]["radio_id"] for f in payload.territorial_features} == {f"TEST-{i:04d}" for i in range(263)}
    assert {f["geometry"]["type"] for f in payload.territorial_features} == {"Polygon", "MultiPolygon"}


@pytest.mark.parametrize("filename", importer.CONTRACT_FILES)
def test_missing_contract_is_rejected(source, filename):
    (source / filename).unlink()
    with pytest.raises(ValueError, match="Falta el contrato requerido"):
        importer.load_and_validate(source)


@pytest.mark.parametrize("content", [b"{", b"\xff", b'{"x": NaN}', b'{"x": Infinity}', b'{"x": 1e999}', b'{"x": 1, "x": 2}'])
def test_corrupt_json_is_rejected(source, content):
    (source / "model_evaluation.json").write_bytes(content)
    with pytest.raises(ValueError, match="JSON inválido"):
        importer.load_and_validate(source)


@pytest.mark.parametrize("filename,path,value,message", [
    (TERRITORIAL, ["features"], [], "263 radios"),
    (TERRITORIAL, ["features", 1, "properties", "radio_id"], "TEST-0000", "duplicado"),
    (TERRITORIAL, ["features", 0, "properties", "radio_id"], 123, "radio_id"),
    (TERRITORIAL, ["features", 0, "properties", "radio_id"], " " , "radio_id"),
    (TERRITORIAL, ["features", 0, "properties", "radio_id"], "x" * 33, "radio_id"),
    (TERRITORIAL, ["features", 0, "type"], "Other", "Feature"),
    (TERRITORIAL, ["features", 0], None, "Feature"),
    (TERRITORIAL, ["features", 0, "geometry"], None, "Feature"),
    (TERRITORIAL, ["features", 0, "geometry", "type"], "Point", "no poligonal"),
    (TERRITORIAL, ["features", 0, "geometry", "type"], [], "no poligonal"),
    (TERRITORIAL, ["features", 0, "geometry", "coordinates"], [], "Coordenadas"),
    (TERRITORIAL, ["features", 0, "geometry", "coordinates"], [[[0, 0], [1, 0], [1, 1], [0, 1]]], "anillo"),
    (TERRITORIAL, ["features", 0, "geometry", "coordinates"], [[[181, 0], [182, 0], [182, 1], [181, 0]]], "4326"),
    (TERRITORIAL, ["crs", "properties", "name"], "EPSG:3857", "CRS"),
    (TERRITORIAL, ["crs", "properties", "name"], [], "CRS"),
    (EXPERIMENTAL, ["crs", "properties", "name"], "EPSG:32719", "CRS"),
    (TERRITORIAL, ["features", 0, "geometry", "crs"], {"type": "name", "properties": {"name": "EPSG:3857"}}, "CRS"),
    (TERRITORIAL, ["features", 0, "properties", "population"], DELETE, "population"),
    (TERRITORIAL, ["features", 0, "properties", "population"], -1, "population"),
    (TERRITORIAL, ["features", 0, "properties", "population"], 1.5, "population"),
    (TERRITORIAL, ["features", 0, "properties", "population"], True, "population"),
    (TERRITORIAL, ["features", 0, "properties", "area_km2"], 0, "area_km2"),
    (TERRITORIAL, ["features", 0, "properties", "percentile"], 101, "percentile"),
    (TERRITORIAL, ["features", 0, "properties", "relative_level"], "critical", "Nivel"),
    (TERRITORIAL, ["features", 0, "properties", "relative_level"], [], "Nivel"),
    ("available_weeks.json", ["weeks", 0, "cutoff_label"], DELETE, "cutoff_label"),
    ("available_weeks.json", ["weeks", 0, "target_week_end"], "2030-01-11", "Intervalo"),
    ("available_weeks.json", ["weeks", 0, "cutoff_date"], "not-a-date", "Fecha"),
    ("available_weeks.json", ["weeks", 0], [], "weeks"),
    ("available_weeks.json", ["default_cutoff_date"], "2030-01-04", "predeterminado"),
    ("available_weeks.json", ["weeks", 0, "has_experimental_spatial"], False, "ambos productos"),
    ("temporal_predictions.json", ["predictions"], [], "cubren exactamente"),
    ("temporal_predictions.json", ["predictions", 0, "predicted_cases"], -1, "negativa"),
    ("temporal_predictions.json", ["predictions", 0, "predicted_cases"], "nan", "predicted_cases"),
    ("temporal_predictions.json", ["predictions", 0, "predicted_cases"], "inf", "predicted_cases"),
    ("temporal_predictions.json", ["predictions", 0, "predicted_cases_rounded"], DELETE, "predicted_cases_rounded"),
    ("temporal_predictions.json", ["predictions", 0, "target_week_start"], "2030-01-07", "desalineada"),
    ("temporal_predictions.json", ["predictions", 0, "cutoff_date"], "2030-01-04", "sin semana"),
    (EXPERIMENTAL, ["features"], [], "263 radios"),
    (EXPERIMENTAL, ["features", 0, "properties", "radio_id"], "UNKNOWN", "desconocido"),
    (EXPERIMENTAL, ["features", 0, "properties", "synthetic_scenario"], DELETE, "synthetic_scenario"),
    (EXPERIMENTAL, ["features", 0, "properties", "experimental_spatial_score"], -0.1, "negativo"),
    (EXPERIMENTAL, ["features", 0, "properties", "percentile"], -1, "percentile"),
    (EXPERIMENTAL, ["features", 0, "properties", "relative_level"], {}, "Nivel"),
    (EXPERIMENTAL, ["features", 0, "properties", "target_week_end"], "2030-01-11", "desalineado"),
    ("mvp_metadata.json", [], [], "mvp_metadata"),
    ("model_evaluation.json", [], None, "model_evaluation"),
    ("mvp_metadata.json", ["nested"], {"EMAIL": "fictitious@example.test"}, "Campo privado"),
])
def test_invalid_contract_rejected_before_engine(source, documents, monkeypatch, filename, path, value, message):
    if path:
        change(documents[filename], path, value)
    else:
        documents[filename] = value
    write_publication(source, documents)
    def forbidden_engine(_url):
        pytest.fail("Invalid contract must fail before opening a database")
    monkeypatch.setattr(importer, "build_engine", forbidden_engine)
    with pytest.raises(ValueError, match=message):
        importer.import_publication("sqlite://", source)


@pytest.mark.parametrize("filename,key", [("available_weeks.json", "weeks"), ("temporal_predictions.json", "predictions"), (EXPERIMENTAL, "features")])
def test_duplicate_temporal_keys_rejected(source, documents, filename, key):
    documents[filename][key].append(deepcopy(documents[filename][key][0]))
    write_publication(source, documents)
    with pytest.raises(ValueError, match="duplicad"):
        importer.load_and_validate(source)


def test_experimental_geometry_must_match_territory(source, documents):
    documents[EXPERIMENTAL]["features"][0]["geometry"] = deepcopy(documents[TERRITORIAL]["features"][1]["geometry"])
    write_publication(source, documents)
    with pytest.raises(ValueError, match="Geometría experimental distinta"):
        importer.load_and_validate(source)


def test_geojson_default_crs_is_still_accepted(source, documents):
    for filename in (TERRITORIAL, EXPERIMENTAL):
        del documents[filename]["crs"]
    write_publication(source, documents)
    assert len(importer.load_and_validate(source).territorial_features) == 263


@pytest.mark.parametrize("name", ["EPSG:4326", "urn:ogc:def:crs:EPSG::4326", "urn:ogc:def:crs:OGC:1.3:CRS84"])
def test_explicit_compatible_crs_is_accepted(source, documents, name):
    for filename in (TERRITORIAL, EXPERIMENTAL):
        documents[filename]["crs"]["properties"]["name"] = name
    write_publication(source, documents)
    assert len(importer.load_and_validate(source).territorial_features) == 263


@pytest.mark.parametrize("version", [" " , "v" * 81])
def test_invalid_version_is_rejected_before_engine(source, monkeypatch, version):
    def forbidden_engine(_url):
        pytest.fail("Invalid version must fail before opening a database")
    monkeypatch.setattr(importer, "build_engine", forbidden_engine)
    with pytest.raises(ValueError, match="version"):
        importer.import_publication("sqlite://", source, version=version)


def test_open_metadata_contract_does_not_invent_required_provenance_fields(source, documents):
    documents["mvp_metadata.json"] = {}
    documents["model_evaluation.json"] = {}
    write_publication(source, documents)
    payload = importer.load_and_validate(source)
    assert payload.metadata == payload.model_evaluation == {}


def test_topological_validity_remains_a_postgis_responsibility(source, documents):
    bowtie = {"type": "Polygon", "coordinates": [[[10, 10], [11, 11], [11, 10], [10, 11], [10, 10]]]}
    for filename in (TERRITORIAL, EXPERIMENTAL):
        documents[filename]["features"][0]["geometry"] = deepcopy(bowtie)
    write_publication(source, documents)
    # Structural validation cannot certify topology. Real ST_IsValid is pending.
    assert importer.load_and_validate(source).territorial_features[0]["geometry"] == bowtie


@pytest.fixture
def store(tmp_path, documents, monkeypatch):
    path = tmp_path / "owned-import-test.sqlite"
    url = f"sqlite:///{path.as_posix()}"
    engine = create_engine(url, connect_args={"check_same_thread": False})
    known = {json.dumps(f["geometry"], sort_keys=True) for f in documents[TERRITORIAL]["features"]}
    control = {"reject_geometry": False, "validity_calls": 0}
    def canonical(value):
        normalized = json.dumps(json.loads(value), sort_keys=True)
        if normalized not in known:
            raise ValueError("SQLite adapter only accepts the known generated fixture geometries")
        return normalized
    def set_srid(value, srid):
        assert srid == 4326
        return canonical(value)
    def validity(value):
        canonical(value)
        control["validity_calls"] += 1
        return int(not control["reject_geometry"])
    @event.listens_for(engine, "connect")
    def spatial_transport(dbapi, _record):
        dbapi.execute("PRAGMA foreign_keys=ON")
        dbapi.create_function("ST_GeomFromGeoJSON", 1, canonical)
        dbapi.create_function("ST_SetSRID", 2, set_srid)
        dbapi.create_function("ST_IsValid", 1, validity)
        dbapi.create_function("ST_SRID", 1, lambda value: 4326 if canonical(value) else None)
    Base.metadata.create_all(engine)
    # This index exists in the PostgreSQL migration, not in Base.metadata.
    with engine.begin() as db:
        db.execute(text("CREATE UNIQUE INDEX one_published_test ON publication_batches(status) WHERE status='published'"))
    def owned_engine(candidate):
        assert candidate == url, "Only this test's disposable SQLite URL is allowed"
        return engine
    monkeypatch.setattr(importer, "build_engine", owned_engine)
    try:
        yield engine, url, control
    finally:
        engine.dispose()
        path.unlink(missing_ok=True)


TABLES = (PublicationBatch, PublicationWeek, TemporalPrediction, TerritorialRadio, ExperimentalSpatialResult)


def counts(engine):
    with Session(engine) as db:
        return tuple(db.scalar(select(func.count()).select_from(table)) for table in TABLES)


def published(engine):
    with Session(engine) as db:
        return db.scalar(select(PublicationBatch.id).where(PublicationBatch.status == "published"))


def test_import_persist_idempotence_and_public_queries(store, source, documents):
    engine, url, control = store
    batch_id, created = importer.import_publication(url, source, version="fictitious-import-v1")
    assert created and counts(engine) == (1, 1, 1, 263, 263)
    assert control["validity_calls"] == 263
    assert importer.import_publication(url, source, version="ignored-on-same-hash") == (batch_id, False)
    assert counts(engine) == (1, 1, 1, 263, 263)
    with Session(engine) as db:
        batch = db.get(PublicationBatch, batch_id)
        assert batch.metadata_json == {"mvp": documents["mvp_metadata.json"], "temporal_model": documents["temporal_predictions.json"]["model"]}
        assert batch.model_evaluation_json == documents["model_evaluation.json"]
        assert batch.published_at is not None and batch.status == "published"
    app = FastAPI()
    app.include_router(router)
    def session_dependency():
        with Session(engine) as db:
            yield db
    app.dependency_overrides[get_db] = session_dependency
    with TestClient(app) as client:
        for endpoint, filename in (("territorial-context", TERRITORIAL), (f"experimental-spatial-history/{CUTOFF}", EXPERIMENTAL)):
            response = client.get("/api/v1/public/" + endpoint)
            assert response.status_code == 200
            assert response.json()["features"] == documents[filename]["features"]
            assert response.json()["publication"]["version"] == "fictitious-import-v1"
            assert response.headers["x-sigard-publication-version"] == "fictitious-import-v1"
            assert not (importer.PRIVATE_KEYS & set(response.text.split('"')))
        metadata = client.get("/api/v1/public/metadata").json()
        assert metadata["data_type"] == "synthetic"
        assert metadata["fixture_version"] == "territorial-import-v1"
        evaluation = client.get("/api/v1/public/model-evaluation").json()
        assert evaluation["metrics"] == {}
        weeks = client.get("/api/v1/public/weeks").json()
        assert weeks["default_cutoff_date"] == CUTOFF
        prediction = client.get(f"/api/v1/public/predictions/{CUTOFF}").json()
        assert prediction["predicted_cases"] == 2.5 and prediction["official_cases"] is None
        assert client.get("/api/v1/public/experimental-spatial-history/2030-01-04").status_code == 404
        assert client.get("/api/v1/public/predictions/2030-01-04").status_code == 404
        assert client.get("/api/v1/public/predictions/no-date").status_code == 422


def test_changed_batch_retires_previous_and_retired_hash_is_not_republished(store, source, documents):
    engine, url, _control = store
    old, _ = importer.import_publication(url, source)
    documents["mvp_metadata.json"]["fixture_version"] = "territorial-import-v2"
    write_publication(source, documents)
    new, created = importer.import_publication(url, source)
    assert created and new != old and counts(engine) == (2, 2, 2, 526, 526)
    assert published(engine) == new
    with Session(engine) as db:
        assert db.get(PublicationBatch, old).status == "retired"
    write_publication(source, publication_documents())
    with pytest.raises(RuntimeError, match="no está publicado"):
        importer.import_publication(url, source)
    assert published(engine) == new


@pytest.mark.parametrize("failure", ["duplicate-version", "after-radio-insert", "postgis-verdict"])
def test_transaction_rolls_back_and_keeps_previous_publication(store, source, documents, failure):
    engine, url, control = store
    old, _ = importer.import_publication(url, source, version="first")
    documents["mvp_metadata.json"]["fixture_version"] = "second"
    write_publication(source, documents)
    def interrupt(_connection, _cursor, statement, _parameters, _context, _many):
        if statement.lstrip().startswith("INSERT INTO experimental_spatial_results"):
            raise RuntimeError("controlled failure after territorial insert")
    if failure == "after-radio-insert":
        event.listen(engine, "before_cursor_execute", interrupt)
    if failure == "postgis-verdict":
        control["reject_geometry"] = True
    try:
        error = IntegrityError if failure == "duplicate-version" else RuntimeError if failure == "after-radio-insert" else ValueError
        with pytest.raises(error):
            importer.import_publication(url, source, version="first" if failure == "duplicate-version" else "second")
    finally:
        if failure == "after-radio-insert":
            event.remove(engine, "before_cursor_execute", interrupt)
        control["reject_geometry"] = False
    assert published(engine) == old
    assert counts(engine) == (1, 1, 1, 263, 263)


def test_invalid_batch_does_not_retire_previous(store, source, documents):
    engine, url, _control = store
    old, _ = importer.import_publication(url, source)
    documents[TERRITORIAL]["features"][1] = deepcopy(documents[TERRITORIAL]["features"][0])
    write_publication(source, documents)
    with pytest.raises(ValueError, match="duplicado"):
        importer.import_publication(url, source)
    assert published(engine) == old and counts(engine) == (1, 1, 1, 263, 263)


def test_staged_batch_is_not_reused_or_exposed(store, source):
    engine, url, _control = store
    batch_id, _ = importer.import_publication(url, source)
    with Session(engine) as db, db.begin():
        db.get(PublicationBatch, batch_id).status = "staged"
    with pytest.raises(RuntimeError, match="no está publicado"):
        importer.import_publication(url, source)
    from app.public import get_territorial_context
    from fastapi import HTTPException, Response
    with Session(engine) as db, pytest.raises(HTTPException) as caught:
        get_territorial_context(Response(), db)
    assert caught.value.status_code == 503


def test_rejected_first_batch_leaves_no_partial_rows(store, source):
    engine, url, control = store
    control["reject_geometry"] = True
    with pytest.raises(ValueError, match="PostGIS rechazó"):
        importer.import_publication(url, source)
    assert counts(engine) == (0, 0, 0, 0, 0)


def test_queries_exclude_retired_and_staged_batches(store, source, documents):
    engine, url, _control = store
    old, _ = importer.import_publication(url, source, version="retired-test")
    documents["mvp_metadata.json"]["fixture_version"] = "published-test"
    write_publication(source, documents)
    current, _ = importer.import_publication(url, source, version="published-test")
    with Session(engine) as db, db.begin():
        db.get(TerritorialRadio, (old, "TEST-0000")).population = 999999
        db.get(ExperimentalSpatialResult, (old, date.fromisoformat(CUTOFF), "TEST-0000")).experimental_spatial_score = 999999
        db.add(PublicationBatch(version="staged-test", input_hash="s" * 64, status="staged",
            default_cutoff_date=date.fromisoformat(CUTOFF), metadata_json={"private_marker": "unpublished"}, model_evaluation_json={}))
    from app.public import get_territorial_context, get_experimental_spatial_history, get_metadata
    from fastapi import Response
    with Session(engine) as db:
        territory = get_territorial_context(Response(), db)
        experimental = get_experimental_spatial_history(date.fromisoformat(CUTOFF), Response(), db)
        metadata = get_metadata(Response(), db)
        assert territory["features"][0]["properties"]["population"] == 100
        assert experimental["features"][0]["properties"]["experimental_spatial_score"] == 0.25
        assert territory["publication"]["version"] == "published-test"
        assert "private_marker" not in metadata
        assert published(engine) == current
