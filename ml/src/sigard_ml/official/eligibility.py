"""Elegibilidad de análisis independiente de diagnóstico e identidad del episodio."""

import pandas as pd

from sigard_ml.official.observed_settings import CLASSIFICATIONS


def evaluate_eligibility(categories, *, exploratory=False, include=(), exclude=(), version):
    if type(exploratory) is not bool or not isinstance(version, str) or not version.strip():
        raise ValueError("Política de elegibilidad inválida")
    include, exclude = set(include), set(exclude)
    if not (include | exclude) <= CLASSIFICATIONS or include & exclude or "indeterminado" in include:
        raise ValueError("Categorías de elegibilidad incompatibles")
    rows = []
    for category in categories:
        if category not in CLASSIFICATIONS:
            raise ValueError("Clasificación no canónica")
        if category == "descartado":
            status, reason = "excluded", "classification_discarded"
        elif exploratory and category in include:
            status, reason = "eligible_provisional", "explicit_exploratory_definition"
        elif exploratory and category in exclude:
            status, reason = "excluded", "outside_exploratory_definition"
        else:
            status, reason = "review", "epidemiological_rules_not_validated"
        rows.append({"analysis_eligibility": status, "eligibility_reason": reason,
                     "eligibility_rule_version": version, "epidemiological_eligibility_validated": False})
    return pd.DataFrame(rows)
