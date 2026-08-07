from __future__ import annotations

import json
from pathlib import Path

import pandas as pd
import pytest

from sigard_ml.simulation.allocation import ClusterParameters, population_proportional, spatial_clusters
from sigard_ml.simulation.pipeline import build_allocations, write_outputs
from sigard_ml.validation.synthetic import SyntheticValidationError, validate_allocation

COLUMNS = {"radio_id": "radio_id", "population": "poblacion", "neighbors": "neighbor_ids", "year": "epidemiological_year", "week": "epidemiological_week", "week_start": "week_start_date", "week_end": "week_end_date", "observed_cases": "dengue_cases_observed", "status": "epidemiological_status"}


def territorial() -> pd.DataFrame:
    return pd.DataFrame({"radio_id": ["1", "2", "3"], "poblacion": [10, 20, 30], "neighbor_ids": [[2], [1, 3], [2]]})


def weeks() -> pd.DataFrame:
    return pd.DataFrame({"epidemiological_year": [2024, 2024], "epidemiological_week": [1, 2], "week_start_date": pd.to_datetime(["2023-12-31", "2024-01-07"]), "week_end_date": pd.to_datetime(["2024-01-06", "2024-01-13"]), "dengue_cases_observed": [17, 0], "epidemiological_status": ["observed", "explicit_zero"]})


@pytest.mark.parametrize("scenario", ["population", "clusters"])
def test_scenarios_are_deterministic_and_conserve_totals(scenario: str) -> None:
    args = (territorial(), weeks(), COLUMNS, 1234, "test-v1")
    if scenario == "population":
        first, second = population_proportional(*args), population_proportional(*args)
    else:
        params = ClusterParameters(1, 4.0, 2.0, 0.5, 0.1)
        first, second = spatial_clusters(*args, params), spatial_clusters(*args, params)
    pd.testing.assert_frame_equal(first, second)
    assert validate_allocation(first, 3)["weekly_conservation_failures"] == 0
    assert len(first) == 6
    assert first["synthetic_cases_assigned"].dtype == "int64"


def test_validation_rejects_changed_department_total() -> None:
    frame = population_proportional(territorial(), weeks(), COLUMNS, 7, "test-v1")
    frame.loc[0, "department_cases_observed"] = 999
    with pytest.raises(SyntheticValidationError, match="Asignación inválida"):
        validate_allocation(frame, 3)


def test_pipeline_integration_and_no_overwrite(tmp_path: Path) -> None:
    input_dir = tmp_path / "inputs"; input_dir.mkdir()
    territorial().to_parquet(input_dir / "territorial.parquet", index=False)
    weeks().to_parquet(input_dir / "weekly.parquet", index=False)
    config = {
        "pipeline": {"name": "test", "version": "1"}, "simulation": {"version": "v1", "seed": 8},
        "inputs": {"territorial": "inputs/territorial.parquet", "weekly": "inputs/weekly.parquet"}, "columns": COLUMNS,
        "universe": {"expected_radio_count": 3}, "weekly_filter": {"allowed_statuses": ["observed", "explicit_zero"], "forbidden_statuses": ["missing_record", "outside_source_coverage"]},
        "scenarios": {"population_proportional": {"method": "multinomial", "parameters": {"weight_variable": "poblacion"}}, "spatial_clusters": {"method": "clusters", "parameters": {"focus_count": 1, "focus_intensity": 4.0, "neighbor_intensity": 2.0, "persistence_probability": 0.5, "noise_sigma": 0.1}}},
        "quality_report": {"top_radio_count": 2}, "outputs": {"population_proportional": "out/pop.parquet", "spatial_clusters": "out/clusters.parquet", "quality_report": "out/report.json"},
    }
    outputs, report = build_allocations(config, tmp_path)
    write_outputs(outputs, report, config, tmp_path)
    assert json.loads((tmp_path / "out/report.json").read_text(encoding="utf-8"))["results"]["population_proportional"]["weeks"] == 2
    with pytest.raises(FileExistsError):
        write_outputs(outputs, report, config, tmp_path)
