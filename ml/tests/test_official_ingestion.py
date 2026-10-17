"""Fuentes Excel completamente ficticias, creadas sólo en tmp_path."""

from dataclasses import replace
from datetime import datetime
import hashlib
import json

from openpyxl import Workbook
import pytest

from sigard_ml.official.access import AccessDenied, AuthorizedUse, SourceAuthorization
from sigard_ml.official.excel import ExcelReadError, inspect_source, read_sheet
from sigard_ml.official.pipeline import load_configuration, inspect_delivery, require_expected_digest
from sigard_ml.official.reports import safe_count, write_report


@pytest.fixture
def source(tmp_path):
    path = tmp_path / "fictional.xlsx"
    workbook = Workbook()
    worksheet = workbook.active
    worksheet.title = "Fictional"
    worksheet.append(["Fictional preface"])
    worksheet.append(["Nombre", "DNI", "Fecha apertura", "Latitud", "Longitud", "ClinicallySensitiveUnknownHeader"])
    worksheet.append(["FICTIONAL_PERSON", "FICTIONAL_DOCUMENT", datetime(2024, 1, 7), -29.4, -66.8, "FICTIONAL_SECRET"])
    worksheet.append([None, None, "invalid-date", "invalid-lat", None, None])
    workbook.save(path)
    workbook.close()
    return SourceAuthorization("fixture", "fixture-v1", path, ("Fictional",), "fixture-extract",
                               approved_extract=True, enabled=True,
                               uses=frozenset({AuthorizedUse.INSPECTION, AuthorizedUse.PROCESSING}),
                               evidence_ref="fixture-permit", custodian_ref="fixture-custody",
                               confidentiality_ref="fixture-policy", storage_policy_ref="fixture-storage")


def test_fictional_reader_finds_header_preserves_types_and_source(source):
    before = hashlib.sha256(source.path.read_bytes()).hexdigest()
    frame, schema = read_sheet(source, "Fictional")
    assert schema["header_row"] == 2
    assert len(frame) == 2
    assert isinstance(frame.loc[3, schema["fields"]["opened_on"]], datetime)
    assert frame.loc[4, schema["fields"]["opened_on"]] == "invalid-date"
    assert before == hashlib.sha256(source.path.read_bytes()).hexdigest()


def test_missing_or_unauthorized_sheet(source):
    with pytest.raises(AccessDenied):
        read_sheet(source, "Pending")
    with pytest.raises(ExcelReadError):
        read_sheet(replace(source, all_sheets_approved=True), "Missing")


def test_disabled_source_is_denied_before_workbook_open(source, monkeypatch):
    def forbidden(*args, **kwargs):
        pytest.fail("No debe abrir fuentes deshabilitadas")
    monkeypatch.setattr("sigard_ml.official.excel.load_workbook", forbidden)
    with pytest.raises(AccessDenied):
        read_sheet(replace(source, enabled=False), "Fictional")


def test_safe_structure_does_not_contain_persons_headers_sheets_or_cells(source):
    report = json.dumps(inspect_source(source))
    for private in ("FICTIONAL_PERSON", "FICTIONAL_DOCUMENT", "FICTIONAL_SECRET",
                    "ClinicallySensitiveUnknownHeader", "Fictional", "-29.4", "-66.8"):
        assert private not in report
    assert "given_name" in report and "column_006" in report


def test_explicit_header_and_column_mapping(source):
    frame, schema = read_sheet(source, "Fictional", header_row=2, column_map={"event_id": 6})
    assert schema["fields"]["event_id"] == "column_006"
    assert len(frame) == 2
    with pytest.raises(ExcelReadError):
        read_sheet(source, "Fictional", column_map={"latitude": 999})
    with pytest.raises(ExcelReadError):
        read_sheet(source, "Fictional", column_map={"sensitive_custom_field": 1})
    with pytest.raises(ExcelReadError):
        read_sheet(source, "Fictional", column_map={"classification": 1})


def test_private_configuration_rejects_public_output_and_unapproved_uses(tmp_path):
    config = {"source_root": str(tmp_path), "output_dir": str(tmp_path / "frontend/public/data"), "sources": []}
    path = tmp_path / "config.json"
    path.write_text(json.dumps(config), encoding="utf-8")
    with pytest.raises(ValueError):
        load_configuration(path, repo_root=tmp_path)
    config["output_dir"] = str(tmp_path / "data/interim/official")
    path.write_text(json.dumps(config), encoding="utf-8")
    assert load_configuration(path, repo_root=tmp_path)[1].sources == ()


def test_safe_counts_and_atomic_report(tmp_path):
    assert [safe_count(value) for value in (0, 1, 4, 5)] == [0, "<5", "<5", 5]
    path = tmp_path / "report.json"
    write_report({"record_count": 10}, path)
    assert json.loads(path.read_text()) == {"record_count": 10}
    assert not path.with_suffix(".tmp").exists()


def test_explicit_whole_workbook_permission_is_required_for_new_sheets(source):
    whole = replace(source, sheets=(), all_sheets_approved=True)
    assert len(read_sheet(whole, "Fictional")[0]) == 2
    with pytest.raises(AccessDenied):
        read_sheet(source, "Another")


def test_version_change_is_rejected_before_ingestion(source, monkeypatch):
    from sigard_ml.official.access import SourceRegistry
    monkeypatch.setattr("sigard_ml.official.pipeline.inspect_source",
                        lambda *args, **kwargs: pytest.fail("No debe leer una versión cambiada"))
    with pytest.raises(ValueError):
        inspect_delivery({"sources": [{"source_id": "fixture", "expected_sha256": "changed"}]},
                         SourceRegistry((source,)))
    require_expected_digest({}, "any")


def test_configuration_rejects_training_permission_and_directory_escape(tmp_path):
    config = {"source_root": str(tmp_path), "output_dir": str(tmp_path / "data/interim/official"),
              "uses": ["training"], "sources": [{"source_id": "fixture", "filename": "fictional.xlsx"}]}
    path = tmp_path / "config.json"
    path.write_text(json.dumps(config), encoding="utf-8")
    with pytest.raises(ValueError):
        load_configuration(path, repo_root=tmp_path)
    config["uses"] = ["inspection"]
    config["sources"][0]["filename"] = "../pending.xlsx"
    path.write_text(json.dumps(config), encoding="utf-8")
    with pytest.raises(ValueError):
        load_configuration(path, repo_root=tmp_path)


def test_cli_failure_does_not_echo_exception_values(tmp_path, monkeypatch, capsys):
    from sigard_ml.official.pipeline import main
    monkeypatch.setattr("sys.argv", ["official", "--config", str(tmp_path / "config.json")])
    def fail(*args, **kwargs):
        raise ValueError("FICTIONAL_SENSITIVE_EXCEPTION_CONTENT")
    monkeypatch.setattr("sigard_ml.official.pipeline.load_configuration", fail)
    with pytest.raises(SystemExit):
        main()
    assert "FICTIONAL_SENSITIVE_EXCEPTION_CONTENT" not in capsys.readouterr().err


def test_delivery_only_reads_explicit_sources_and_exports_private_projection(source, tmp_path):
    from sigard_ml.official.pipeline import validate_delivery
    from sigard_ml.official.reports import write_quality_summary
    (tmp_path / "pending.xlsx").write_bytes(b"not-authorized-not-readable")
    output = tmp_path / "data/interim/official"
    config = {
        "data_kind": "fictional_fixture", "source_root": str(tmp_path), "output_dir": str(output),
        "as_of_date": "2024-12-31", "write_normalized": True,
        "uses": ["inspection", "processing"],
        "authorization": {"evidence_ref": "fixture-permit", "custodian_ref": "fixture-custody",
                          "confidentiality_ref": "fixture-policy", "storage_policy_ref": "fixture-storage"},
        "sources": [{"source_id": "fixture", "filename": "fictional.xlsx", "enabled": True,
                     "approved_extract": True, "sheets": ["Fictional"], "sheet_options": {
                         "sheet_01": {"column_map": {"event_id": 6}}}}],
    }
    path = tmp_path / "config.json"
    path.write_text(json.dumps(config), encoding="utf-8")
    loaded, registry = load_configuration(path, repo_root=tmp_path)
    before = hashlib.sha256(source.path.read_bytes()).hexdigest()
    report = validate_delivery(loaded, registry)
    assert report["source_count"] == 1 and report["data_kind"] == "fictional_fixture"
    assert report["summary"]["rows"] == "<5"
    encoded = json.dumps(report)
    for private in ("FICTIONAL_PERSON", "FICTIONAL_DOCUMENT", "FICTIONAL_SECRET", "-29.4", "-66.8"):
        assert private not in encoded
    assert (output / "normalized/fixture_sheet_01.parquet").exists()
    write_quality_summary(report, output / "quality_report.md")
    assert "FICTIONAL_PERSON" not in (output / "quality_report.md").read_text(encoding="utf-8")
    assert before == hashlib.sha256(source.path.read_bytes()).hexdigest()
