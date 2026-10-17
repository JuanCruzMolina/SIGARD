"""Contrato reproducible de un futuro RF; nunca llama fit/predict/evaluate."""

from sigard_ml.official.spatial_ml.experiment_selection import SETS, SUPPORT_RULE
from sigard_ml.official.spatial_ml.splits import evaluation_contract

VERSION = "official-spatial-experiment-preparation-0.5b.0"
RF_PARAMETERS = {"n_estimators": 400, "criterion": "gini", "max_depth": 10,
    "min_samples_split": 10, "min_samples_leaf": 5, "max_features": "sqrt",
    "bootstrap": True, "class_weight": "balanced_subsample", "random_state": 20261016,
    "n_jobs": 1, "oob_score": False, "warm_start": False}


def installed_capabilities():
    import sklearn
    from sklearn.ensemble import RandomForestClassifier
    from sklearn.utils import get_tags
    estimator = RandomForestClassifier(**RF_PARAMETERS)
    return {"scikit_learn_version": sklearn.__version__, "native_nan_supported": bool(get_tags(estimator).input_tags.allow_nan),
            "parameters_accepted": estimator.get_params() | RF_PARAMETERS, "estimator_fitted": hasattr(estimator, "estimators_")}


def experiment_protocol():
    capabilities = installed_capabilities()
    if not capabilities["native_nan_supported"] or capabilities["estimator_fitted"]:
        raise ValueError("El entorno no cumple el contrato sin entrenamiento y con NaN nativo")
    return {"version": VERSION, "training_enabled": False, "training_performed": False,
        "estimator": "sklearn.ensemble.RandomForestClassifier", "parameters": RF_PARAMETERS,
        "environment": capabilities, "feature_sets": SETS, "optional_selection_rule": SUPPORT_RULE,
        "selection": "predefined A/B/C; optional support uses known mature training labels only; no selection by test performance",
        "imputation": {"strategy": "none_preserve_NaN", "applied": False, "parameters_fitted": False,
            "optional_all_unknown_in_training": "drop column and its missing indicator within that training fold",
            "mandatory_all_unknown_in_training": "block experiment",
            "future_fallback": "disabled; if needed, version training-only median+indicator; never fit on validation/test/unknown labels",
            "imputed_value_is_observed_count": False},
        "imbalance": "balanced_subsample weights from training bootstrap only; no SMOTE, no unknown-label conversion, no evaluation resampling",
        "numeric_view": "retain epidemiologically supported zeros; NaN for unknown or unavailable; missingness indicators are not epidemiological counts",
        "census": "2022 retrospective context; publication and boundary availability require separate evidence",
        "evaluation": evaluation_contract(),
        "classification_metrics": ["average_precision", "ROC_AUC_if_both_classes", "precision", "recall", "F1", "confusion_matrix", "Brier", "log_loss"],
        "threshold": "0.5 descriptive default; any tuning on inner chronological training only; freeze before validation/test",
        "calibration": {"primary": "assess raw probabilities with Brier/log_loss and reliability diagram",
            "optional_fit": "sigmoid on chronological inner training calibration block with mature labels and both classes",
            "never_fit_on": ["outer_validation", "test"], "applied": False},
        "strict_vs_expanded": "same calendar splits, hyperparameters, seeds and source hashes; report label disagreement, date effects and availability separately; no policy selection by test scores",
        "future_replicate_seeds": [20261016, 20261017, 20261018],
        "gates": ["explicit authorization to train", "supported negatives or separately authorized assumed scenario",
            "mature labels and both classes in every partition", "clinical eligibility/universe reviewed",
            "point-in-time record/classification availability", "census publication/boundary evidence",
            "training-only optional selection and preprocessing", "sample size and temporal dependence reviewed"],
        "reference": "https://scikit-learn.org/stable/modules/generated/sklearn.ensemble.RandomForestClassifier.html"}
