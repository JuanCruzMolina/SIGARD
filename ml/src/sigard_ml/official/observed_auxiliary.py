"""Unión opcional de auxiliares ya documentadas; no genera variables ni etiquetas."""

import pandas as pd

from sigard_ml.official.contracts import FeatureValue


def attach_auxiliary_values(panel, values):
    """Tabla larga: radio_censal, fecha_inicio_semana, name, value y disponibilidad.

    Cada predictor debe estar observado y disponible al sábado de esa semana,
    corte para una eventual predicción de la semana siguiente. Sin evidencia
    de disponibilidad se rechaza la unión. No transforma ausencias en ceros.
    """
    required = {"radio_censal", "fecha_inicio_semana", "name", "value", "observed_through", "available_on", "source_ref"}
    if not required <= set(values) or values[list(required)].isna().any().any():
        raise ValueError("Auxiliares sin correspondencia o disponibilidad")
    keys = ["radio_censal", "fecha_inicio_semana", "name"]
    if values.duplicated(keys).any():
        raise ValueError("Auxiliar territorial-temporal repetida")
    cuts = panel.set_index(keys[:2]).fecha_fin_semana.to_dict()
    for _, row in values.iterrows():
        key = (row.radio_censal, row.fecha_inicio_semana)
        if key not in cuts or not isinstance(row.radio_censal, str):
            raise ValueError("Auxiliar ajena a la grilla territorial-temporal")
        feature = FeatureValue(row["name"], float(row["value"]), row.observed_through, row.available_on)
        if feature.available_on > cuts[key]:
            raise ValueError("Información auxiliar posterior al corte de predicción")
        if row["name"] in panel.columns:
            raise ValueError("La auxiliar sobrescribiría un campo existente")
    joined = panel.copy()
    for field, suffix in (("value", ""), ("observed_through", "_observed_through"),
                          ("available_on", "_available_on"), ("source_ref", "_source_ref")):
        wide = values.pivot(index=keys[:2], columns="name", values=field).add_suffix(suffix).reset_index()
        if any(column in joined for column in wide if column not in keys[:2]):
            raise ValueError("La auxiliar sobrescribiría procedencia o un campo existente")
        joined = joined.merge(wide, on=keys[:2], how="left", validate="one_to_one")
    return joined
