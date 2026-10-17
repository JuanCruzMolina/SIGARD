"""Grupos de identidad privada; una fila con ID no repetido es sólo provisional."""

import hashlib

import pandas as pd

from sigard_ml.official.normalization import normalize_text
from sigard_ml.official.observed_settings import ROW_KEY


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
