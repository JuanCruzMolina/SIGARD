"""P2: filas inventadas en memoria, sin pacientes, cartografía, IO o ajustes."""

from copy import deepcopy
from datetime import date

import pandas as pd
import pytest

from sigard_ml.official.episodes import (
    PRINCIPAL_EPISODE_POLICY, episode_count_summary, episode_decision_digest, principal_episode_review,
)
from sigard_ml.official.observed_settings import ROW_KEY

AS_OF = date(2024, 12, 31)


def records():
    return pd.DataFrame([dict(source_id="fictional_source", source_version="fictional_v1",
        sheet_ref="fictional_sheet", record_ref=f"fictional_record_{index}", event_ref="fictional_reused_id",
        classification="confirmado", classification_mapped=True, classification_rule_version="fictional_class_v1",
        analysis_eligibility="eligible_provisional", epidemiological_eligibility_validated=False,
        symptom_onset=date(2024, 1, 8), symptom_onset_status="valid", sample_on=None, sample_on_status="missing",
        coordinate_group_ref="fictional_position_a", geometry_status="unique_interior", assignment_state="unique_geometry",
        crs_confirmed=True, location_role="residence", uncertainty_reasons=[], geocoding_category="fictional_documented",
        spatial_assignment_version="fictional_spatial_v1", record_available_on=date(2024, 3, 1)) for index in range(2)])


def review(frame=None, **kwargs):
    return principal_episode_review(records() if frame is None else frame, period_start=date(2020, 1, 1),
                                    period_end=AS_OF, as_of=AS_OF, **kwargs)


def keys(frame):
    return frame[ROW_KEY].values.tolist()


def decision(frame, *, same=False):
    pending = review(frame)
    return dict(reference="fictional_authorized_decision", status="approved", reviewer_ref="fictional_reviewer",
        criterion_ref="fictional_approved_episode_criterion", policy_version=PRINCIPAL_EPISODE_POLICY,
        criterion_status="approved", criterion_version="fictional_criterion_v1", authorization_ref="fictional_authorization",
        basis="Entirely invented complete-group review for software tests",
        records_sha256=episode_decision_digest(pending, record_keys=keys(frame)),
        decided_on=date(2024, 3, 1), available_on=date(2024, 3, 2), resolutions=[
            dict(record_key=key, episode_ref="fictional_same" if same else f"fictional_episode_{index}",
                 countable=index == 1 if same else True, evidence_ref="fictional_authorized_decision")
            for index, key in enumerate(keys(frame))])


@pytest.mark.parametrize("different_date,different_position,category", [
    (False, False, "possible_duplicate"), (True, True, "possible_distinct"),
    (True, False, "indeterminate"), (False, True, "indeterminate"),
])
def test_spatiotemporal_hints_never_establish_identity(different_date, different_position, category):
    frame = records()
    if different_date:
        frame.loc[1, "symptom_onset"] = date(2024, 2, 8)
    if different_position:
        frame.loc[1, "coordinate_group_ref"] = "fictional_position_b"
    before = deepcopy(frame)
    result = review(frame)
    assert result.records.p2_category.tolist() == [category] * 2
    assert not result.records.identity_countable.any()
    summary = episode_count_summary(result, record_keys=keys(frame))
    assert summary["eligible_records"] == 2 and summary["exact_episode_count"] is None
    assert summary["independent_episodes"] == 0
    pd.testing.assert_frame_equal(frame, before)


def test_shared_address_is_not_read_or_returned():
    class ForbiddenAddress:
        def __str__(self):
            pytest.fail("No debe leer ni interpretar domicilios")
    frame = records()
    frame["address"] = [ForbiddenAddress()] * 2
    frame["longitude_candidate"] = [ForbiddenAddress()] * 2
    frame["latitude_candidate"] = [ForbiddenAddress()] * 2
    frame.loc[1, "symptom_onset"] = date(2021, 1, 8)
    frame.loc[1, "coordinate_group_ref"] = "fictional_position_b"
    result = review(frame)
    assert result.records.p2_category.eq("possible_distinct").all()
    assert not {"address", "longitude_candidate", "latitude_candidate"} & set(result.records)
    assert "fictional_reused_id" not in repr(result)


def test_missing_onset_uses_sample_and_keeps_reference_type():
    frame = records()
    frame["symptom_onset"], frame["symptom_onset_status"] = None, "missing"
    frame["sample_on"], frame["sample_on_status"] = date(2024, 1, 8), "valid"
    result = review(frame).records
    assert result.tipo_fecha_referencia.eq("toma_muestra").all() and result.fecha_aproximada.all()
    assert result.p2_category.eq("possible_duplicate").all()


@pytest.mark.parametrize("change", ["missing_date", "missing_position", "approximate", "unconfirmed_crs",
                                     "unknown_uncertainty", "different_date_types", "contradictory_dates",
                                     "conflicting_classification", "different_spatial_version", "known_missing_coordinates",
                                     "missing_position_with_availability_flag"])
def test_insufficient_or_conflicting_metadata_remain_indeterminate(change):
    frame = records()
    if change == "missing_date":
        frame.loc[0, ["symptom_onset", "symptom_onset_status"]] = [None, "missing"]
    elif change == "missing_position": frame.loc[0, "coordinate_group_ref"] = None
    elif change == "approximate":
        frame.loc[0, "assignment_state"] = "uncertain"
        frame.at[0, "uncertainty_reasons"] = ["approximate_geocoding"]
    elif change == "unconfirmed_crs": frame.loc[0, "crs_confirmed"] = False
    elif change == "unknown_uncertainty": frame.at[0, "uncertainty_reasons"] = None
    elif change == "different_date_types":
        frame.loc[0, ["symptom_onset", "symptom_onset_status", "sample_on", "sample_on_status"]] = [None, "missing", date(2024, 1, 8), "valid"]
    elif change == "contradictory_dates":
        frame.loc[0, ["sample_on", "sample_on_status"]] = [date(2024, 1, 1), "valid"]
    elif change == "conflicting_classification": frame.loc[0, "classification"] = "sospechoso"
    elif change == "known_missing_coordinates": frame["coordinates_available"] = False
    elif change == "missing_position_with_availability_flag":
        frame["coordinates_available"] = True
        frame.loc[0, "coordinate_group_ref"] = None
    else: frame.loc[0, "spatial_assignment_version"] = "fictional_other_v1"
    assert review(frame).records.p2_category.eq("indeterminate").all()


def test_suspected_2022_records_are_preserved_separately_from_recorded_confirmed():
    frame = records()
    frame.loc[0, ["source_id", "classification", "symptom_onset"]] = ["fictional_delivery_2022", "sospechoso", date(2022, 2, 1)]
    frame.loc[0, "coordinate_group_ref"] = "fictional_position_b"
    result = review(frame)
    assert result.records.classification.tolist() == ["sospechoso", "confirmado"]
    assert result.records.p2_category.eq("indeterminate").all()
    assert episode_count_summary(result, record_keys=keys(frame))["exact_episode_count"] is None


@pytest.mark.parametrize("same,expected,episodes", [(False, "reviewed_distinct", 2), (True, "reviewed_same_episode", 1)])
def test_only_scoped_approved_decisions_resolve_episodes(same, expected, episodes):
    frame = records()
    result = review(frame, decisions=[decision(frame, same=same)])
    assert result.records.p2_category.eq(expected).all()
    assert result.records.identity_resolved_by_review.all()
    summary = episode_count_summary(result, record_keys=keys(frame))
    assert summary["exact_episode_count"] == summary["independent_episodes"] == episodes
    assert summary["eligible_records"] == 2 and summary["review_available_on"] == "2024-03-02"


@pytest.mark.parametrize("change", ["draft", "missing_criterion", "other_hash", "future", "partial_group",
                                     "duplicate_decision", "no_representative", "two_representatives",
                                     "criterion_draft", "missing_authorization"])
def test_review_metadata_cannot_replace_authorized_complete_group_resolution(change):
    frame = records()
    doc = decision(frame, same=True)
    docs = [doc]
    if change == "draft": doc["status"] = "draft"
    elif change == "missing_criterion": doc.pop("criterion_ref")
    elif change == "criterion_draft": doc["criterion_status"] = "draft"
    elif change == "missing_authorization": doc.pop("authorization_ref")
    elif change == "other_hash": doc["records_sha256"] = "0" * 64
    elif change == "future": doc["available_on"] = date(2025, 1, 1)
    elif change == "partial_group":
        doc["resolutions"] = doc["resolutions"][1:]
        doc["records_sha256"] = episode_decision_digest(review(frame), record_keys=keys(frame)[1:])
    elif change == "duplicate_decision": docs.append(deepcopy(doc))
    else:
        for item in doc["resolutions"]: item["countable"] = change == "two_representatives"
    with pytest.raises(ValueError):
        review(frame, decisions=docs)


def test_later_metadata_revision_and_result_mutation_require_new_review():
    frame = records()
    doc = decision(frame)
    frame.loc[0, "classification"] = "sospechoso"
    with pytest.raises(ValueError, match="alcance exacto"):
        review(frame, decisions=[doc])
    result = review(frame)
    result.records.loc[0, "p2_category"] = "reviewed_distinct"
    with pytest.raises(ValueError, match="modificado"):
        episode_count_summary(result, record_keys=keys(frame))


def test_reviewed_episode_is_counted_only_at_its_explicit_representative():
    frame = records()
    result = review(frame, decisions=[decision(frame, same=True)])
    assert episode_count_summary(result, record_keys=keys(frame)[:1])["exact_episode_count"] == 0
    assert episode_count_summary(result, record_keys=keys(frame)[1:])["exact_episode_count"] == 1


def test_unreviewed_singletons_or_missing_ids_never_establish_exact_counts():
    frame = records()
    frame["event_ref"] = ["fictional_unique_id", None]
    result = review(frame)
    assert result.records.p2_category.eq("indeterminate").all()
    assert not result.records.identity_countable.any()
    assert episode_count_summary(result, record_keys=keys(frame))["unknown_identity_records"] == 2


def test_three_records_do_not_merge_transitively_and_input_order_cannot_change_decisions():
    frame = pd.concat([records(), records().iloc[:1]], ignore_index=True)
    frame.loc[2, ["record_ref", "symptom_onset", "coordinate_group_ref"]] = [
        "fictional_record_third", date(2021, 1, 1), "fictional_position_b"]
    result = review(frame)
    assert result.records.p2_category.tolist() == ["indeterminate", "indeterminate", "possible_distinct"]
    assert episode_count_summary(result, record_keys=keys(frame))["exact_episode_count"] is None
    doc = decision(frame)
    reordered = review(frame.iloc[::-1], decisions=[doc])
    assert reordered.records.p2_category.eq("reviewed_distinct").all()
    assert episode_count_summary(reordered, record_keys=keys(frame))["exact_episode_count"] == 3


def test_approved_criteria_cannot_resolve_missing_identifier_with_current_contract():
    frame = records()
    frame["event_ref"] = None
    with pytest.raises(ValueError, match="identidades ausentes"):
        review(frame, decisions=[decision(frame)])


@pytest.mark.parametrize("column", ["classification", "geometry_status", "assignment_state", "location_role"])
def test_nullable_metadata_are_indeterminate_without_guessing(column):
    frame = records()
    frame[column] = frame[column].astype(object)
    frame.at[1, column] = pd.NA
    assert review(frame).records.p2_category.eq("indeterminate").all()
