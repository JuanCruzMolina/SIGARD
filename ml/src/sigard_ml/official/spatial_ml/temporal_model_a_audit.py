"""Auditoría scikit-learn del RF propio congelado; inferencia sin ajuste."""

import hashlib
from pathlib import Path

import joblib
import numpy as np
import pandas as pd
import sklearn
from sklearn.ensemble import RandomForestClassifier
from sklearn.utils import get_tags

from sigard_ml.official.calendar_rules import DEFAULT_CALENDAR
from sigard_ml.official.spatial_ml.features import KEYS
from sigard_ml.official.spatial_ml.experiment_selection import BASE
from sigard_ml.official.spatial_ml.features import calendar_predictors
from sigard_ml.official.spatial_pipeline import digest_path

CALENDAR = BASE[4:]


def forest_fingerprint(model):
    digest = hashlib.sha256()
    for tree in model.estimators_:
        for array in (tree.tree_.children_left, tree.tree_.children_right, tree.tree_.feature,
                      tree.tree_.threshold, tree.tree_.value):
            digest.update(array.tobytes())
    return digest.hexdigest()


def manual_tree_leaves(tree, x):
    """Reproduce el recorrido <= umbral sobre float32, sin fit o mutación."""
    x = np.asarray(x, dtype=np.float32)
    node = np.zeros(len(x), dtype=int)
    while True:
        active = tree.children_left[node] != tree.children_right[node]
        if not active.any():
            break
        positions = np.flatnonzero(active)
        current = node[active]
        left = x[positions, tree.feature[current]] <= tree.threshold[current]
        node[positions] = np.where(left, tree.children_left[current], tree.children_right[current])
    return node


def audit_model_a(model_path, expected_sha256, metadata, review, features, predictions):
    """Sólo el joblib propio, firmado por hash de 5C y versión instalada idéntica.

    La deserialización pertenece a esta auditoría scikit-learn explícita del
    modelo confiable, separada del perfilado EDA de datos tabulares.
    """
    model_path = Path(model_path)
    if (model_path.is_symlink() or not model_path.is_file() or model_path.stat().st_size > 32 * 1024 * 1024
            or digest_path(model_path) != expected_sha256
            or metadata["runtime"]["scikit-learn"] != sklearn.__version__):
        raise ValueError("Modelo o versión no confiables para inspección")
    model = joblib.load(model_path)
    if (type(model) is not RandomForestClassifier or list(model.feature_names_in_) != BASE
            or any(model.get_params()[key] != value for key, value in review["parameters"].items())
            or len(model.estimators_) != 400):
        raise ValueError("El objeto no coincide con el RF A congelado")
    before = forest_fingerprint(model)
    joined = predictions.merge(features, on=KEYS, validate="one_to_one", how="left")
    if len(joined) != len(predictions) or joined[BASE].isna().any().any():
        raise ValueError("Matriz de inferencia sin correspondencia exacta")
    calendar = features[KEYS].copy()
    yw = calendar.fecha_inicio_semana.map(DEFAULT_CALENDAR.date_week)
    calendar["anio_epidemiologico"] = yw.map(lambda x: x[0])
    calendar["semana_epidemiologica"] = yw.map(lambda x: x[1])
    expected_calendar = calendar_predictors(calendar)
    for name in CALENDAR:
        if not np.allclose(features[name], expected_calendar[name], rtol=0, atol=1e-12):
            raise ValueError("Calendario de inferencia incorrecto")
    probabilities = model.predict_proba(joined[BASE])[:, list(model.classes_).index(1)]
    if not np.array_equal(probabilities, predictions.random_forest_A_probability.to_numpy()):
        raise ValueError("La inferencia original no reproduce las probabilidades guardadas")
    train = joined[joined.partition.eq("train") & joined.objetivo_semana_siguiente.notna()]
    thresholds = {}
    threshold_rows = []
    for i, name in enumerate(BASE):
        values = np.concatenate([tree.tree_.threshold[tree.tree_.feature == i] for tree in model.estimators_])
        thresholds[name] = values
        threshold_rows.append({"feature": name, "split_nodes": len(values),
            "minimum_threshold": float(values.min()) if len(values) else None,
            "maximum_threshold": float(values.max()) if len(values) else None,
            "minimum_training_value": float(train[name].min()), "maximum_training_value": float(train[name].max()),
            "trees_using_feature": sum(bool(np.any(tree.tree_.feature == i)) for tree in model.estimators_)})
    test = joined[joined.partition.eq("test")].sort_values(KEYS)
    weeks = sorted(test.fecha_inicio_semana_objetivo.unique())
    weekly_inputs, pair_rows, sensitivity, leaf_audit = [], [], [], []
    matrices = {}
    for week in weeks:
        group = test[test.fecha_inicio_semana_objetivo.eq(week)].sort_values("radio_censal").reset_index(drop=True)
        if len(group) != 263 or any(group[name].nunique() != 1 for name in CALENDAR):
            raise ValueError("Matriz de prueba semanal inesperada")
        x = group[BASE].copy()
        matrices[week] = (group, x, model.apply(x), model.predict_proba(x)[:, 1])
        manual_probability = np.zeros(len(x))
        leaves_manual_equal = True
        for number, tree in enumerate(model.estimators_):
            leaves = manual_tree_leaves(tree.tree_, x)
            leaves_manual_equal &= np.array_equal(leaves, matrices[week][2][:, number])
            weights = tree.tree_.value[leaves, 0, :]
            manual_probability += weights[:, 1] / weights.sum(axis=1)
        manual_probability /= len(model.estimators_)
        if not leaves_manual_equal or not np.allclose(manual_probability, matrices[week][3], rtol=0, atol=1e-15):
            raise ValueError("El recorrido manual del bosque no concilia con scikit-learn")
        leaf_audit.append({"target_week": str(week), "radios": len(group), "trees": len(model.estimators_),
            "manual_leaf_traversal_matches": bool(leaves_manual_equal),
            "manual_probability_max_error": float(np.max(np.abs(manual_probability - matrices[week][3])))})
        for name in CALENDAR:
            weekly_inputs.append({"target_week": str(week), "origin_week": str(group.fecha_inicio_semana.iloc[0]),
                "feature": name, "value_float64": float(x[name].iloc[0]),
                "value_float32_used_by_trees": float(np.float32(x[name].iloc[0]))})
    for first, second in zip(weeks[:-1], weeks[1:]):
        one, x1, leaves1, p1 = matrices[first]
        two, x2, leaves2, p2 = matrices[second]
        if not one.radio_censal.equals(two.radio_censal):
            raise ValueError("Radios desalineados entre semanas")
        changes = leaves1 != leaves2
        static_equal = np.array_equal(x1[BASE[:4]], x2[BASE[:4]])
        pair_rows.append({"first_target_week": str(first), "second_target_week": str(second),
            "radios": len(one), "static_features_equal": bool(static_equal),
            "radios_with_different_input_rows": int((x1.to_numpy() != x2.to_numpy()).any(axis=1).sum()),
            "same_leaf_radio_tree_pairs": int((~changes).sum()), "total_radio_tree_pairs": int(changes.size),
            "radios_with_any_changed_leaf": int(changes.any(axis=1).sum()),
            "identical_probability_radios": int((p1 == p2).sum()),
            "maximum_probability_difference": float(np.abs(p2 - p1).max())})
        for name in CALENDAR:
            value1, value2 = np.float32(x1[name].iloc[0]), np.float32(x2[name].iloc[0])
            branches = (value1 <= thresholds[name]) != (value2 <= thresholds[name])
            counterfactual = x1.copy()
            counterfactual[name] = x2[name].to_numpy()
            pcf = model.predict_proba(counterfactual)[:, 1]
            cf_leaves = model.apply(counterfactual)
            sensitivity.append({"first_target_week": str(first), "second_target_week": str(second),
                "feature": name, "first_value_float64": float(x1[name].iloc[0]),
                "second_value_float64": float(x2[name].iloc[0]),
                "global_split_nodes_whose_branch_changes": int(branches.sum()),
                "total_feature_split_nodes": len(thresholds[name]),
                "single_feature_changed_leaf_radio_tree_pairs": int((cf_leaves != leaves1).sum()),
                "single_feature_max_probability_difference": float(np.abs(pcf - p1).max()),
                "single_feature_radios_probability_changed": int((pcf != p1).sum()),
                "interpretation": "computational sensitivity only; one-feature substitution may not be a coherent calendar triple"})
    sweep = []
    base = matrices[weeks[0]][1].copy()
    for week_number in range(1, 23):
        origin, _ = DEFAULT_CALENDAR.week_bounds(2024, week_number)
        c = pd.DataFrame({"radio_censal": ["audit"], "fecha_inicio_semana": [origin],
            "anio_epidemiologico": [2024], "semana_epidemiologica": [week_number]})
        seasonal = calendar_predictors(c)
        x = base.copy()
        for name in CALENDAR:
            x[name] = seasonal[name].iloc[0]
        p = model.predict_proba(x)[:, 1]
        sweep.append({"origin_epidemiological_week": week_number, "origin_week_start": str(origin),
            "mean_probability_fixed_263_radios": float(p.mean()), "minimum_probability": float(p.min()),
            "maximum_probability": float(p.max()), "diagnostic_only_not_a_forecast_or_model_selection": True})
    if forest_fingerprint(model) != before or digest_path(model_path) != expected_sha256:
        raise ValueError("El modelo se alteró durante la auditoría")
    first_pair = pair_rows[0]
    first_sensitivity = sensitivity[:3]
    expected_tree_plateau = (first_pair["radios_with_different_input_rows"] == 263
        and first_pair["same_leaf_radio_tree_pairs"] == 263 * 400
        and first_pair["identical_probability_radios"] == 263
        and all(row["global_split_nodes_whose_branch_changes"] == 0 for row in first_sensitivity))
    if not expected_tree_plateau:
        raise ValueError("La meseta no se explica completamente; revisar implementación antes de concluir")
    result = {"model_loaded_for_readonly_scikit_audit": True, "new_model_fitted": False,
        "model_file_sha256": expected_sha256, "tree_state_sha256_before_and_after": before,
        "saved_predictions_bitwise_reproduced": True, "inference_rows_replayed": len(joined),
        "features_order": BASE, "estimator": "RandomForestClassifier_without_preprocessing_pipeline",
        "learned_transformations_applied": False, "tree_internal_input_dtype": "float32",
        "origin_calendar_recomputed_matches": True, "native_nan_supported": bool(get_tags(model).input_tags.allow_nan),
        "plateau_explained_by_same_tree_paths": bool(expected_tree_plateau),
        "implementation_error_detected": False,
        "scope_of_negative_finding": "audited frozen model, matrix/calendar/keys and replay only; not an epidemiological validation",
        "no_hyperparameters_or_thresholds_selected": True}
    return result, {"model_A_thresholds": threshold_rows, "model_A_weekly_inputs": weekly_inputs,
        "model_A_leaf_pairs": pair_rows, "model_A_seasonal_sensitivity": sensitivity,
        "model_A_manual_tree_audit": leaf_audit, "model_A_coherent_calendar_sweep": sweep}
