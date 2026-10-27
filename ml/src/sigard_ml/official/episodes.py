"""Grupos de identidad privada; una fila con ID no repetido es sólo provisional."""

import hashlib
from dataclasses import dataclass, field
from datetime import date
from itertools import combinations

import pandas as pd
import numpy as np

from sigard_ml.official.normalization import normalize_text
from sigard_ml.official.observed_settings import ROW_KEY
from sigard_ml.official.observed_dates import PRINCIPAL_DATE_HIERARCHY, assign_record_weeks, parse_reference_date

PRINCIPAL_EPISODE_POLICY = "principal-episode-review-1"
REVIEWED = {"reviewed_distinct", "reviewed_same_episode"}
# Sólo referencias técnicas y metadatos derivados. Domicilios y coordenadas
# individuales no se leen, comparan ni copian a la salida de esta política.
PRINCIPAL_FIELDS = ROW_KEY + [
    "source_version", "event_ref", "classification", "classification_mapped",
    "classification_rule_version", "analysis_eligibility", "epidemiological_eligibility_validated",
    "symptom_onset", "symptom_onset_status", "sample_on", "sample_on_status",
    "coordinate_group_ref", "coordinates_available", "crs_confirmed", "geometry_status", "assignment_state",
    "geocoding_category", "uncertainty_reasons", "location_role", "spatial_assignment_version",
    "record_available_on",
]


def _text(value):
    return isinstance(value, str) and bool(value.strip())


def _digest(frame):
    return hashlib.sha256(frame.sort_values(ROW_KEY).to_json(
        orient="records", date_format="iso", force_ascii=True).encode("utf-8")).hexdigest()


@dataclass(frozen=True)
class PrincipalEpisodeReview:
    """Resultado privado en memoria; su representación no imprime registros."""

    records: pd.DataFrame = field(repr=False)
    sha256: str
    scope_columns: tuple[str, ...] = field(repr=False)


def episode_decision_digest(review, *, record_keys):
    """Huella del alcance que el revisor debe examinar, sin aprobarlo."""
    selected = _select_review_records(review, record_keys)
    return _digest(selected[list(review.scope_columns)])


def _select_review_records(review, record_keys):
    if not isinstance(review, PrincipalEpisodeReview) or _digest(review.records) != review.sha256:
        raise ValueError("Resultado P2 ausente o modificado después de revisar")
    keys = [tuple(key) for key in record_keys]
    lookup = {tuple(row): index for index, row in review.records[ROW_KEY].iterrows()}
    if len(set(keys)) != len(keys) or any(key not in lookup for key in keys):
        raise ValueError("Alcance elegible P2 ajeno o duplicado")
    return review.records.loc[[lookup[key] for key in keys]]


def principal_episode_review(frame, *, period_start, period_end, as_of, decisions=()):
    """Indicios por ID, sin umbrales clínicos ni resolución automática.

    El llamador debe tener permiso para los derivados en memoria. Las decisiones
    son documentos revisados/autorizados por un custodio externo: validar sus
    campos y huella no autentica una firma ni acredita P1/P3–P6. Sin IO.
    """
    required = ROW_KEY + ["event_ref", "classification"]
    if (not isinstance(frame, pd.DataFrame) or not set(required) <= set(frame)
            or not frame[ROW_KEY].map(_text).all().all() or frame.duplicated(ROW_KEY).any()):
        raise ValueError("Faltan claves técnicas únicas o clasificación de los registros")
    if any(type(value) is not date for value in (period_start, period_end, as_of)):
        raise ValueError("Se requieren fechas sin hora")
    records = frame.reindex(columns=PRINCIPAL_FIELDS).copy(deep=True).reset_index(drop=True)
    if not records.event_ref.dropna().map(_text).all():
        raise ValueError("Los identificadores deben ser referencias opacas o null")
    # Una ausencia de metadatos no equivale a coordenadas disponibles.
    if "coordinates_available" not in frame:
        records["coordinates_available"] = records.coordinate_group_ref.map(_text)
    for value in records.record_available_on.dropna():
        if type(value) is not date or value > as_of:
            raise ValueError("Registro posterior al corte o disponibilidad inválida")
    dates = assign_record_weeks(records, field="symptom_onset", hierarchy=PRINCIPAL_DATE_HIERARCHY,
        period_start=period_start, period_end=period_end, as_of=as_of, version=PRINCIPAL_EPISODE_POLICY)
    records = pd.concat([records, dates], axis=1)
    scope_columns = tuple(records.columns)
    resolutions = []
    available = {}
    review_metadata = {}
    covered = set()
    references = set()
    for decision in decisions:
        if not isinstance(decision, dict):
            raise ValueError("Decisión P2 inválida")
        refs = ("reference", "reviewer_ref", "criterion_ref", "criterion_version", "authorization_ref", "basis")
        if (decision.get("status") != "approved" or decision.get("policy_version") != PRINCIPAL_EPISODE_POLICY
                or decision.get("criterion_status") != "approved"
                or not all(_text(decision.get(key)) for key in refs)
                or type(decision.get("decided_on")) is not date or type(decision.get("available_on")) is not date
                or not decision["decided_on"] <= decision["available_on"] <= as_of):
            raise ValueError("Decisión P2 no autorizada, sin criterio o posterior al corte")
        if decision["reference"] in references:
            raise ValueError("Referencia de decisión P2 repetida")
        references.add(decision["reference"])
        items = decision.get("resolutions")
        if not isinstance(items, (list, tuple)) or not items:
            raise ValueError("Decisión P2 sin resoluciones")
        if any(not isinstance(item, dict) or set(item) != {"record_key", "episode_ref", "countable", "evidence_ref"}
               for item in items):
            raise ValueError("Resolución P2 incompleta")
        try:
            keys = [tuple(item["record_key"]) for item in items]
        except (KeyError, TypeError) as error:
            raise ValueError("Resolución P2 sin claves de registros") from error
        lookup = {tuple(row): index for index, row in records[ROW_KEY].iterrows()}
        if (len(set(keys)) != len(keys) or any(key not in lookup or key in covered for key in keys)
                or any(item.get("evidence_ref") != decision["reference"] for item in items)):
            raise ValueError("Decisión P2 con registros ajenos, repetidos o evidencia incompatible")
        subset = records.loc[[lookup[key] for key in keys]]
        if decision.get("records_sha256") != _digest(subset):
            raise ValueError("Decisión P2 fuera del alcance exacto de registros/metadatos")
        if any(type(value) is date and value > decision["available_on"]
               for value in subset.record_available_on.dropna()):
            raise ValueError("Decisión P2 anterior a la disponibilidad de sus registros")
        resolutions.extend(items)
        covered.update(keys)
        for key in keys:
            available[key] = decision["available_on"]
            review_metadata[key] = decision
    identities = review_episode_groups(records, version=PRINCIPAL_EPISODE_POLICY, resolutions=resolutions)
    for _, group in identities.loc[identities.identity_resolved_by_review].groupby("episode_ref"):
        if group.identity_evidence_ref.nunique() != 1:
            raise ValueError("Un episodio debe resolverse completo en una misma decisión P2")
    identities.loc[~identities.identity_resolved_by_review, "identity_countable"] = False
    records = pd.concat([records, identities.drop(columns=ROW_KEY + ["event_ref"])], axis=1)
    records["p2_category"] = "indeterminate"
    records["p2_reason"] = "missing_or_singleton_identifier_not_accredited"
    records["p2_policy_version"] = PRINCIPAL_EPISODE_POLICY
    records["p2_review_available_on"] = [available.get(tuple(row)) for _, row in records[ROW_KEY].iterrows()]
    for name in ("criterion_ref", "authorization_ref"):
        records["p2_" + name] = [review_metadata.get(tuple(row), {}).get(name) for _, row in records[ROW_KEY].iterrows()]
    for _, group in records.loc[records.event_ref.notna()].groupby("event_ref", sort=False):
        indications = {index: [] for index in group.index}
        for left, right in combinations(group.index, 2):
            indication = _pair_indication(records.loc[left], records.loc[right])
            indications[left].append(indication)
            indications[right].append(indication)
        for index, findings in indications.items():
            if findings:
                kinds = {kind for kind, _ in findings}
                category = kinds.pop() if len(kinds) == 1 else "indeterminate"
                reasons = sorted({reason for _, reason in findings})
                records.loc[index, ["p2_category", "p2_reason"]] = [category, ";".join(reasons)]
    for index, row in records.loc[records.identity_resolved_by_review].iterrows():
        same = records.episode_ref.eq(row.episode_ref).sum() > 1
        records.loc[index, ["p2_category", "p2_reason"]] = [
            "reviewed_same_episode" if same else "reviewed_distinct", "authorized_scoped_episode_decision"]
    return PrincipalEpisodeReview(records, _digest(records), scope_columns)


def _pair_indication(left, right):
    if (not _text(left.classification) or not _text(right.classification)
            or left.classification == "indeterminado" or left.classification != right.classification):
        return "indeterminate", "missing_or_conflicting_recorded_classification"
    for row in (left, right):
        onset, _ = parse_reference_date(row.symptom_onset)
        sample, _ = parse_reference_date(row.sample_on)
        reasons = row.uncertainty_reasons
        if (not row.reference_date_usable or (onset and sample and sample < onset)
                or not isinstance(row.coordinates_available, (bool, np.bool_)) or not row.coordinates_available
                or not _text(row.coordinate_group_ref)
                or not isinstance(row.crs_confirmed, (bool, np.bool_)) or not row.crs_confirmed
                or not all(_text(getattr(row, name)) for name in ("geometry_status", "assignment_state", "location_role"))
                or row.geometry_status != "unique_interior" or row.assignment_state != "unique_geometry"
                or row.location_role != "residence" or not isinstance(reasons, (list, tuple)) or len(reasons)
                or not _text(row.spatial_assignment_version)):
            return "indeterminate", "missing_uncertain_or_contradictory_time_space"
    if left.reference_date_field != right.reference_date_field or left.spatial_assignment_version != right.spatial_assignment_version:
        return "indeterminate", "incomparable_date_basis_or_spatial_version"
    same_date = left.reference_date == right.reference_date
    same_location = left.coordinate_group_ref == right.coordinate_group_ref
    if same_date and same_location:
        return "possible_duplicate", "same_recorded_date_and_position_reference_not_identity_proof"
    if not same_date and not same_location:
        return "possible_distinct", "different_recorded_date_and_position_reference_not_episode_proof"
    return "indeterminate", "mixed_temporal_and_spatial_indications"


def episode_count_summary(review, *, record_keys):
    """Conciliación P2 para un alcance elegible definido externamente por P1/P4/P5.

    record_keys debe incluir todos los registros que puedan afectar esa celda,
    incluidos pendientes. No declara cobertura ni selecciona casos/sospechosos.
    Un episodio revisado cuenta sólo en la celda de su representante explícito.
    """
    selected = _select_review_records(review, record_keys)
    duplicate = int(selected.p2_category.eq("possible_duplicate").sum())
    unknown = int((~selected.p2_category.isin(REVIEWED | {"possible_duplicate"})).sum())
    reviewed = selected.loc[selected.p2_category.isin(REVIEWED)]
    episodes = int(reviewed.identity_countable.sum())
    result = dict(eligible_records=len(selected), independent_episodes=episodes,
                  possible_duplicate_records=duplicate, unknown_identity_records=unknown,
                  exact_episode_count=None if duplicate + unknown else episodes,
                  review_refs=sorted(set(reviewed.identity_evidence_ref)),
                  review_available_on=max(reviewed.p2_review_available_on).isoformat() if len(reviewed) else None)
    validate_episode_summary(result)
    return result


def validate_episode_summary(summary):
    """Contrato agregado compartido con el adaptador; nunca recibe pacientes."""
    counts = ("eligible_records", "independent_episodes", "possible_duplicate_records", "unknown_identity_records")
    fields = {*counts, "exact_episode_count", "review_refs", "review_available_on"}
    if (not isinstance(summary, dict) or set(summary) != fields
            or any(type(summary.get(key)) is not int or summary[key] < 0 for key in counts)):
        raise ValueError("Conciliación agregada P2 inválida")
    pending = summary["possible_duplicate_records"] + summary["unknown_identity_records"]
    reviewed = summary["eligible_records"] - pending
    exact = summary["exact_episode_count"]
    if (reviewed < summary["independent_episodes"] or (pending and exact is not None)
            or (not pending and (type(exact) is not int or exact != summary["independent_episodes"]))):
        raise ValueError("P2 no respalda un conteo exacto con identidad pendiente")
    refs = summary["review_refs"]
    if (not isinstance(refs, list) or not all(_text(ref) for ref in refs) or len(set(refs)) != len(refs)
            or (reviewed > 0 and (not refs or not _text(summary["review_available_on"])))
            or (reviewed == 0 and (refs or summary["review_available_on"] is not None))):
        raise ValueError("Conciliación P2 sin referencias/disponibilidad de revisión")
    if reviewed:
        value = summary["review_available_on"]
        try:
            if date.fromisoformat(value).isoformat() != value:
                raise ValueError
        except (TypeError, ValueError) as error:
            raise ValueError("Disponibilidad de revisión P2 debe ser YYYY-MM-DD") from error


def event_reference(value):
    value = normalize_text(value)
    return hashlib.sha256(value.encode("utf-8")).hexdigest() if value else None


def review_episode_groups(frame, *, version, resolutions=()):
    """No deduplica por posición. Repeticiones se excluyen salvo revisión explícita.

    Una resolución debe cubrir todo el grupo y nombrar un representante por
    episodio. El representante es declarado; nunca se selecciona el primero.
    """
    if frame.duplicated(ROW_KEY).any() or not isinstance(version, str) or not version.strip():
        raise ValueError("Claves de filas o versión de episodios inválidas")
    sizes = frame.event_ref.value_counts()
    result = frame[ROW_KEY + ["event_ref"]].copy()
    result["identity_group_size"] = result.event_ref.map(sizes).fillna(0).astype(int)
    result["episode_status"] = "repeated_identifier_pending"
    result.loc[result.identity_group_size.eq(1), "episode_status"] = "singleton_provisional"
    result.loc[result.event_ref.isna(), "episode_status"] = "missing_identifier_pending"
    result["episode_ref"] = result.event_ref.map(lambda value: "provisional_" + value if pd.notna(value) else None)
    result["identity_countable"] = result.identity_group_size.eq(1)
    result["identity_resolved_by_review"] = False
    result["episode_rule_version"] = version
    result["identity_evidence_ref"] = None
    apply_episode_resolutions(result, resolutions)
    # Ningún grupo provisional repetido se contabiliza de forma automática.
    if result.loc[result.identity_countable].episode_ref.duplicated().any():
        raise ValueError("Más de una fila contable por episodio candidato")
    return result


def apply_episode_resolutions(result, resolutions):
    if not resolutions:
        return
    keys = {tuple(row): index for index, row in result[ROW_KEY].iterrows()}
    decisions = {}
    for resolution in resolutions:
        key = tuple(resolution["record_key"])
        if key not in keys or key in decisions or type(resolution["countable"]) is not bool:
            raise ValueError("Resolución de identidad ajena, repetida o incompleta")
        for field in ("episode_ref", "evidence_ref"):
            if not isinstance(resolution[field], str) or not resolution[field].strip():
                raise ValueError("Resolución sin episodio o evidencia")
        decisions[key] = resolution
    reviewed = result.loc[[keys[key] for key in decisions]]
    if reviewed.event_ref.isna().any():
        raise ValueError("Resolver identidades ausentes requiere un contrato adicional")
    for event_ref in reviewed.event_ref.unique():
        members = result[result.event_ref.eq(event_ref)]
        if any(tuple(row) not in decisions for _, row in members[ROW_KEY].iterrows()):
            raise ValueError("La revisión debe cubrir todo el grupo de identidad")
    representative_counts = {}
    for key, resolution in decisions.items():
        episode = "reviewed_" + resolution["episode_ref"]
        representative_counts[episode] = representative_counts.get(episode, 0) + int(resolution["countable"])
        index = keys[key]
        result.loc[index, ["episode_status", "episode_ref", "identity_countable",
                           "identity_resolved_by_review", "identity_evidence_ref"]] = [
            "resolved_by_review" if resolution["countable"] else "resolved_nonrepresentative",
            episode, resolution["countable"], True, resolution["evidence_ref"]]
    if any(count != 1 for count in representative_counts.values()):
        raise ValueError("Cada episodio revisado requiere exactamente un representante")
