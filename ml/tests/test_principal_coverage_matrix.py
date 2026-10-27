"""P3: sólo agregados ficticios; no pacientes, fuentes reales, modelos o servicios."""

from copy import deepcopy
from datetime import date, timedelta

import pandas as pd
import pytest

from sigard_ml.official.coverage_diagnostics import principal_eligibility_matrix
from sigard_ml.official.coverage_policy import decide_observation

FIRST = date(2024, 1, 7)
VERSIONS = {"fictional_a": "fictional_v1", "fictional_b": "fictional_v2"}


def panel():
    rows = []
    for index in range(3):
        for radio in ("fictional_radio_a", "fictional_radio_b"):
            count = 3 if index < 2 else 0
            observed, coverage, state, provisional = decide_observation(count, 1, "unknown", "unknown", "conservative")
            sources = (["fictional_a"] if radio.endswith("a") else ["fictional_b"]) if index == 0 else ["fictional_a", "fictional_b"]
            rows.append(dict(radio_censal=radio, fecha_inicio_semana=FIRST + timedelta(weeks=index),
                casos_observados=observed, estado_cobertura=coverage, estado_observacion=state,
                cobertura_declarada="unknown", cobertura_comprobada="unknown", cero_provisional=provisional,
                escenario="conservative", declaracion_cobertura_ref="fictional_unknown_declaration",
                verificacion_cobertura_ref=None, ventana_semanal_parcial=False,
                registros_pendientes_posibles=1, registros_asignacion_incierta=count,
                fuentes_con_registros=sources if count else []))
    result = pd.DataFrame(rows)
    result["casos_observados"] = result.casos_observados.astype("Int64")
    return result


def test_existing_coverage_and_p2_unknowns_are_retained_without_mutation():
    data = panel()
    before = deepcopy(data)
    result = principal_eligibility_matrix(data, source_versions=VERSIONS)
    assert result["selected_provisional_weeks"] == 2 and result["grid_weeks"] == 3
    assert result["other_grid_weeks_not_evidence_of_zero"] == 1
    assert result["coverage_sufficient_weeks"] == result["accredited_count_weeks"] == 0
    assert result["grid_weeks_with_any_backed_zero_cell"] == 0
    assert all(row["accredited_episode_count"] is None and row["maturity"] == "unknown" for row in result["weeks"])
    assert all(row["pending_may_modify_count"] and row["P2_status"] == "unknown_or_unresolved" for row in result["weeks"])
    assert all(row["identity_pending_records"] is None for row in result["weeks"])
    assert not result["adapter_bundle_ready"] and not result["training_authorized"]
    assert all("radio_id" not in row and "radio_censal" not in row for row in result["weeks"] + result["source_weeks"])
    pd.testing.assert_frame_equal(data, before)


def test_exact_source_counts_and_mixed_cells_are_separate_not_evenly_distributed():
    result = principal_eligibility_matrix(panel(), source_versions=VERSIONS)
    exact = [row for row in result["source_weeks"] if row["week_start"] == FIRST.isoformat()]
    mixed = [row for row in result["source_weeks"] if row["week_start"] != FIRST.isoformat()]
    assert [row["provisional_records"] for row in exact] == [3, 3]
    assert all(row["provisional_records"] is None for row in mixed)
    assert all(row["provisional_records_lower_bound"] == 0 and row["provisional_records_upper_bound"] == 6 for row in mixed)
    assert all(row["source_coverage"] == "unknown" for row in result["source_weeks"])


def test_partial_week_with_positive_counts_stays_provisional():
    data = panel()
    data.loc[data.fecha_inicio_semana.eq(FIRST), "ventana_semanal_parcial"] = True
    result = principal_eligibility_matrix(data, source_versions=VERSIONS)
    first = result["weeks"][0]
    assert first["partial_week"] and "partial_week" in first["block_reasons"]
    assert first["observation_status"] == "positive_provisional" and first["accredited_episode_count"] is None


def identity(exact=6):
    return dict(eligible_records=6, independent_episodes=exact or 0,
                possible_duplicate_records=0, unknown_identity_records=0 if exact is not None else 6,
                exact_episode_count=exact, review_refs=["fictional_P2_review"] if exact is not None else [],
                review_available_on="2024-01-20" if exact is not None else None)


@pytest.mark.parametrize("exact", [None, 6])
def test_p2_resolution_alone_does_not_accredit_counts_or_coverage(exact):
    result = principal_eligibility_matrix(panel(), source_versions=VERSIONS, identity_by_week={FIRST: identity(exact)})
    first = result["weeks"][0]
    assert first["P2_status"] == ("reviewed_identity_only" if exact is not None else "unknown_or_unresolved")
    assert first["accredited_episode_count"] is None and not first["training_eligible"]


@pytest.mark.parametrize("change", ["wrong_count", "foreign_week", "forged_exact"])
def test_p2_summary_must_match_weekly_scope_and_preserve_pending(change):
    summary = identity()
    start = FIRST
    if change == "wrong_count": summary["eligible_records"] = 7
    elif change == "foreign_week": start += timedelta(weeks=10)
    else: summary["unknown_identity_records"] = 1
    with pytest.raises(ValueError):
        principal_eligibility_matrix(panel(), source_versions=VERSIONS, identity_by_week={start: summary})


def test_coverage_declaration_cannot_override_missing_verification_or_maturity():
    data = panel()
    data["cobertura_declarada"] = "complete"
    result = principal_eligibility_matrix(data, source_versions=VERSIONS)
    assert result["coverage_sufficient_weeks"] == 0
    assert not result["weeks"][0]["positive_accredited"]


def test_existing_verified_zero_is_counted_only_as_coverage_evidence():
    data = panel()
    mask = data.fecha_inicio_semana.eq(FIRST + timedelta(weeks=2))
    data.loc[mask, ["casos_observados", "cobertura_comprobada", "estado_cobertura", "estado_observacion",
                    "registros_pendientes_posibles"]] = [0, "complete", "completa_comprobada", "cero_comprobado_bajo_reglas", 0]
    result = principal_eligibility_matrix(data, source_versions=VERSIONS)
    assert result["grid_weeks_with_any_backed_zero_cell"] == 1
    assert result["accredited_count_weeks"] == 0 and result["selected_provisional_weeks"] == 2


def test_version_or_duplicate_cell_errors_are_not_hidden_by_aggregation():
    with pytest.raises(ValueError, match="versión"):
        principal_eligibility_matrix(panel(), source_versions={})
    with pytest.raises(ValueError, match="duplicadas"):
        principal_eligibility_matrix(pd.concat([panel(), panel().iloc[:1]]), source_versions=VERSIONS)


def test_missing_source_or_fractional_counts_cannot_be_silently_truncated():
    data = panel()
    data.at[0, "fuentes_con_registros"] = []
    with pytest.raises(ValueError, match="fuentes"):
        principal_eligibility_matrix(data, source_versions=VERSIONS)
    data = panel()
    data["casos_observados"] = data.casos_observados.astype(float)
    data.loc[0, "casos_observados"] = 1.5
    with pytest.raises(ValueError, match="enteros"):
        principal_eligibility_matrix(data, source_versions=VERSIONS)


def test_missing_radio_cells_cannot_establish_complete_territorial_coverage():
    data = panel()
    data = data.loc[~(data.fecha_inicio_semana.eq(FIRST) & data.radio_censal.eq("fictional_radio_b"))].copy()
    data["cobertura_comprobada"] = "complete"
    data["registros_pendientes_posibles"] = 0
    result = principal_eligibility_matrix(data, source_versions=VERSIONS)
    assert not result["weeks"][0]["coverage_sufficient_for_whole_territory"]
    assert "incomplete_radio_grid" in result["weeks"][0]["block_reasons"]
