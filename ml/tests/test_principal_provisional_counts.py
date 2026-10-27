"""Agregados enteramente ficticios; sin IO privado, modelos ni entrenamiento."""

from copy import deepcopy
from datetime import date

import pandas as pd
import pytest

from sigard_ml.official.classification import (
    CONFIRMED_RECORD_TARGET, EXPERIMENTAL_2022_TARGET, provisional_record_positive,
)
from sigard_ml.official.coverage_panel import principal_provisional_counts


IDS = [f"fictional_radio_{i}" for i in range(256)]


def inputs():
    rows = []
    for radio, count in [(IDS[0], 3), ("fictional_outside", 2), (IDS[1], None), (IDS[2], 0)]:
        rows.append(dict(radio_censal=radio, anio_epidemiologico=2024,
            semana_epidemiologica=2, fecha_inicio_semana=date(2024, 1, 7),
            fecha_fin_semana=date(2024, 1, 13), casos_observados=count,
            fuentes_con_registros=["fictional_source"] if count else [],
            ventana_semanal_parcial=False, estado_cobertura="desconocida",
            cobertura_declarada="unknown", cobertura_comprobada="unknown",
            registros_pendientes_posibles=4, registros_asignacion_incierta=count or 0,
            version_fecha="fictional_preserved_date_rule"))
    panel = pd.DataFrame(rows)
    panel["casos_observados"] = panel.casos_observados.astype("Int64")
    panel["registros_asignacion_incierta"] = panel.registros_asignacion_incierta.astype("int64")
    inventory = pd.DataFrame([dict(source_id="fictional_source", canonical_category="confirmado",
                                   included_provisional=5)])
    return panel, inventory


def project(panel, inventory, **changes):
    options = dict(territory_ids=IDS, territory_version="la-rioja-46014010-256-v1",
                   source_versions={"fictional_source": "fictional_v1"}, extraction_date=date(2024, 2, 1))
    options.update(changes)
    return principal_provisional_counts(panel, inventory, **options)


def test_sparse_projection_conserves_counts_exterior_and_all_unknowns_without_mutation():
    panel, inventory = inputs()
    before = deepcopy(panel)
    result = project(panel, inventory)
    assert len(result) == 2 and result.provisional_positive_records.sum() == 5
    assert result.groupby("territory_status").provisional_positive_records.sum().to_dict() == {"included": 3, "outside": 2}
    assert result.accredited_episode_count.isna().all() and result.available_on.isna().all()
    assert result.P2_status.eq("unknown_or_unresolved").all()
    assert result.P3_status.eq("not_accredited").all() and not result.training_eligible.any()
    assert result.uncertain_assignment_records.sum() == 5
    assert result.target_definition.eq(CONFIRMED_RECORD_TARGET).all()
    assert not {"record_ref", "event_ref", "latitude", "longitude", "objetivo_semana_siguiente"} & set(result)
    pd.testing.assert_frame_equal(panel, before)


@pytest.mark.parametrize("change", ["mixed_source", "missing_version", "wrong_total", "nonconfirmed",
                                    "calendar", "partial", "future", "duplicate", "negative", "uncertain"])
def test_reject_incompatible_aggregates_instead_of_inventing_a_join(change):
    panel, inventory = inputs()
    options = {}
    if change == "mixed_source": panel.at[0, "fuentes_con_registros"] = ["fictional_source", "fictional_other"]
    elif change == "missing_version": options["source_versions"] = {}
    elif change == "wrong_total": inventory.loc[0, "included_provisional"] = 6
    elif change == "nonconfirmed": inventory.loc[0, "canonical_category"] = "sospechoso"
    elif change == "calendar": panel.loc[0, "semana_epidemiologica"] = 3
    elif change == "partial": panel.loc[0, "ventana_semanal_parcial"] = True
    elif change == "future": options["extraction_date"] = date(2024, 1, 12)
    elif change == "duplicate": panel = pd.concat([panel, panel.iloc[:1]], ignore_index=True)
    elif change == "negative": panel.loc[0, "casos_observados"] = -1
    elif change == "uncertain": panel.loc[0, "registros_asignacion_incierta"] = 9
    with pytest.raises(ValueError):
        project(panel, inventory, **options)


@pytest.mark.parametrize("ids,version", [(IDS[:-1], "la-rioja-46014010-256-v1"),
                                         (IDS[:-1] + [IDS[0]], "la-rioja-46014010-256-v1"),
                                         (IDS, "fictional_wrong_version")])
def test_territory_version_and_unique_256_ids_required(ids, version):
    with pytest.raises(ValueError):
        project(*inputs(), territory_ids=ids, territory_version=version)


@pytest.mark.parametrize("category", ["sospechoso", "probable"])
@pytest.mark.parametrize("year", [2021, 2022, 2023])
def test_experimental_definition_separate_and_bound_to_epidemiological_year(category, year):
    assert not provisional_record_positive(category, year, target_definition=CONFIRMED_RECORD_TARGET)
    assert provisional_record_positive(category, year, target_definition=EXPERIMENTAL_2022_TARGET) == (year == 2022)


@pytest.mark.parametrize("target", [CONFIRMED_RECORD_TARGET, EXPERIMENTAL_2022_TARGET])
def test_confirmed_stays_recorded_confirmed_and_discarded_or_unknown_never_positive(target):
    assert provisional_record_positive("confirmado", 2022, target_definition=target)
    for category in ("descartado", "indeterminado"):
        assert not provisional_record_positive(category, 2022, target_definition=target)


def test_no_implicit_target_definition():
    with pytest.raises(ValueError):
        provisional_record_positive("confirmado", 2022, target_definition="unknown")
