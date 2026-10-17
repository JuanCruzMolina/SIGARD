"""Correspondencias literales de un único campo; sin interpretación clínica."""

import unicodedata

import pandas as pd

from sigard_ml.official.observed_settings import CLASSIFICATIONS
from sigard_ml.official.normalization import normalize_text


def classification_key(value):
    text = normalize_text(value)
    return unicodedata.normalize("NFKC", text).casefold() if text else None


def prepare_classification_map(mapping):
    result = {}
    for label, category in mapping.items():
        key = classification_key(label)
        if not key or category not in CLASSIFICATIONS:
            raise ValueError("Correspondencia de clasificación inválida")
        if key in result and result[key] != category:
            raise ValueError("Correspondencias de clasificación contradictorias")
        result[key] = category
    return result


def classify_labels(labels, mapping, version):
    if not isinstance(version, str) or not version.strip():
        raise ValueError("Falta versión de clasificación")
    mapping = prepare_classification_map(mapping)
    keys = [classification_key(value) for value in labels]
    return pd.DataFrame({"classification": [mapping.get(key, "indeterminado") for key in keys],
                         "classification_mapped": [key in mapping for key in keys],
                         "classification_rule_version": version})
