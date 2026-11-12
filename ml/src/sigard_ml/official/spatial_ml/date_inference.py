"""Private, prospective t+1 inference of the existing A. Never trains or evaluates.

Capture records availability NOW, not a historical publication date. Only the
fixed local artifacts linked by the existing research registry can be loaded.
B is deliberately blocked until an as-of epidemiological input feed exists.
"""

import argparse
from contextlib import ExitStack
from datetime import datetime, timedelta, timezone
import hashlib
from io import BytesIO
import json
from pathlib import Path
import platform
import sys
from unittest.mock import patch

from sigard_ml.official.calendar_rules import DEFAULT_CALENDAR

ROOT = Path(__file__).resolve().parents[5]
POLICY = "data/interim/official/spatial_date_inference_v1/policy.private.json"
REGISTRY = "data/interim/official/spatial_app_session_v1/registry.private.json"
FOLDER = "data/processed/official/spatial_rf_05c_v1"
SCENARIO = "data/processed/official/spatial_assumed_2024_v1"
MODEL = "random_forest_A.research.private.joblib"
VERSION = "official-spatial-rf-research-0.5c.0"
POLICY_SCHEMA = "sigard-private-ab-inference-authorization/1"
RESULT_SCHEMA = "sigard-experimental-spatial-inference/1"
LOCAL_ZONE = timezone(timedelta(hours=-3))
CODE = ["calendar_rules.py", "spatial_ml/features.py", "spatial_ml/experiment_selection.py",
        "spatial_ml/experiment_protocol.py"]


class InferenceBlocked(ValueError):
    def __init__(self, code="inference_integrity_blocked"):
        super().__init__(code)
        self.code = code


def require(value, code="inference_integrity_blocked"):
    if not value:
        raise InferenceBlocked(code)


def utc_now():
    return datetime.now(timezone.utc)


def timestamp(value):
    result = datetime.fromisoformat(value)
    require(result.tzinfo is not None)
    return result.astimezone(timezone.utc)


def content(root, name, expected=None, limit=64 * 1024 * 1024):
    root = Path(root).resolve()
    relative = Path(name)
    require(not relative.is_absolute() and ".." not in relative.parts)
    path = root / relative
    require(path.resolve().is_relative_to(root))
    require(not any(p.is_symlink() or p.is_junction() for p in [path, *path.parents] if p != root.parent))
    require(path.is_file() and path.stat().st_size <= limit)
    with path.open("rb") as source:
        value = source.read(limit + 1)
    require(len(value) <= limit)
    if expected is not None:
        require(hashlib.sha256(value).hexdigest() == expected)
    return value


def metadata(root, name, expected=None):
    return json.loads(content(root, name, expected))


def trusted_inputs(root):
    """Resolve only the own A linked to the already authorized local registry."""
    registry = metadata(root, REGISTRY)
    require(registry["local_read_authorized"] is True)
    manifest_name = FOLDER + "/integrity_manifest.private.json"
    manifest = metadata(root, manifest_name, registry["models"]["A"]["manifest_sha256"])
    require(manifest["version"] == VERSION)
    pins = {REGISTRY: hashlib.sha256(content(root, REGISTRY)).hexdigest(),
            manifest_name: registry["models"]["A"]["manifest_sha256"]}
    for name in (MODEL, "review.private.json", "metadata.private.json", "research_authorization.private.json"):
        pins[FOLDER + "/" + name] = manifest["outputs_sha256"][name]
        content(root, FOLDER + "/" + name, pins[FOLDER + "/" + name])
    review = metadata(root, FOLDER + "/review.private.json", pins[FOLDER + "/review.private.json"])
    meta = metadata(root, FOLDER + "/metadata.private.json", pins[FOLDER + "/metadata.private.json"])
    require(review["version"] == meta["version"] == VERSION and review["research_training_authorized"] is True)
    scenario_manifest = SCENARIO + "/integrity_manifest.private.json"
    pins[scenario_manifest] = review["scenario_manifest_sha256"]
    scenario = metadata(root, scenario_manifest, pins[scenario_manifest])
    source = SCENARIO + "/predictors_A.private.parquet"
    pins[source] = scenario["outputs_sha256"]["predictors_A.private.parquet"]
    content(root, source, pins[source])
    # Existing transformations must remain byte-identical to those used in A.
    for name in CODE:
        relative = "ml/src/sigard_ml/official/" + name
        old = meta["implementation_sha256"].get(relative, meta["implementation_sha256"].get(relative.replace("/", "\\")))
        require(old is not None)
        content(root, relative, old)
        pins[relative] = old
    return pins, review, meta


def static_context(root, pins):
    import numpy as np
    import pyarrow.parquet as pq
    from sigard_ml.official.spatial_ml.experiment_selection import BASE
    from sigard_ml.official.spatial_ml.features import KEYS

    raw = content(root, SCENARIO + "/predictors_A.private.parquet", pins[SCENARIO + "/predictors_A.private.parquet"])
    parquet = pq.ParquetFile(BytesIO(raw))
    require(parquet.metadata.num_rows <= 100_000)
    frame = parquet.read(columns=KEYS + BASE).to_pandas()
    require(not frame.duplicated(KEYS).any() and not frame[KEYS].isna().any().any())
    require(all(isinstance(r, str) for r in frame.radio_censal))
    require(np.isfinite(frame[BASE].to_numpy(float)).all())
    require(frame.groupby("radio_censal")[BASE[:4]].nunique(dropna=False).eq(1).all().all())
    static = frame[["radio_censal", *BASE[:4]]].drop_duplicates().sort_values("radio_censal").reset_index(drop=True)
    require(len(static) == static.radio_censal.nunique() == 263)
    return static


def capture(root=ROOT):
    """Explicit authorization from this task; no backdating or automatic repinning."""
    root = Path(root).resolve()
    destination = root / POLICY
    require(not destination.exists(), "inference_policy_already_exists")
    require(destination.resolve().is_relative_to(root))
    require(not any(p.is_symlink() or p.is_junction() for p in destination.parents if p != root.parent))
    pins, _, _ = trusted_inputs(root)
    static_context(root, pins)
    observed = utc_now().isoformat()
    policy = {"schema_version": POLICY_SCHEMA,
              "authorization_ref": "project_owner_existing_AB_date_inference_20261027",
              "authorized_models": ["A"], "static_available_at": observed,
              "model_available_at": observed, "availability_basis": "local_hash_verified_observation_now",
              "historical_availability_accredited": False,
              "snapshot_id": "ab-fixed-context-" + observed.replace(":", "").replace("+", "_"),
              "pins": pins}
    destination.parent.mkdir(parents=True, exist_ok=True)
    require(not destination.parent.is_symlink() and not destination.parent.is_junction())
    with destination.open("x", encoding="utf-8") as output:
        json.dump(policy, output, indent=2)
    return {k: policy[k] for k in ("schema_version", "authorized_models", "static_available_at", "availability_basis")}


def load_policy(root, expected):
    policy = metadata(root, POLICY, expected)
    require(policy["schema_version"] == POLICY_SCHEMA and policy["authorized_models"] == ["A"])
    require(policy["authorization_ref"] == "project_owner_existing_AB_date_inference_20261027")
    require(policy["availability_basis"] == "local_hash_verified_observation_now" and policy["historical_availability_accredited"] is False)
    pins, review, meta = trusted_inputs(root)
    require(pins == policy["pins"])
    return policy, review, meta


def plan(requested, policy, now):
    day = datetime.strptime(requested, "%Y-%m-%d").date()
    require(day.isoformat() == requested, "invalid_date")
    year, number = DEFAULT_CALENDAR.date_week(day)
    target, target_end = DEFAULT_CALENDAR.week_bounds(year, number)
    current_year, current_number = DEFAULT_CALENDAR.date_week(now.astimezone(LOCAL_ZONE).date())
    current, _ = DEFAULT_CALENDAR.week_bounds(current_year, current_number)
    require(target > current, "historical_input_availability_unverified")
    require(target == current + timedelta(days=7), "horizon_not_supported")
    require(timestamp(policy["static_available_at"]) <= now and timestamp(policy["model_available_at"]) <= now,
            "inputs_not_available_at_cutoff")
    # Static context and origin calendar do not depend on origin-week closure.
    return {"target_week_start": target.isoformat(), "target_week_end": target_end.isoformat(),
            "target_epidemiological_year": year, "target_epidemiological_week": number,
            "origin_week_start": current.isoformat(), "origin_week_end": (target - timedelta(days=1)).isoformat(),
            "information_cutoff": now.isoformat(), "calendar_version": DEFAULT_CALENDAR.version}


def feature_matrix(static, origin):
    """Exactly A's unscaled columns; reuse the original seasonal transformation."""
    from sigard_ml.official.spatial_ml.experiment_selection import BASE
    from sigard_ml.official.spatial_ml.features import calendar_predictors

    frame = static.copy()
    year, week = DEFAULT_CALENDAR.date_week(origin)
    frame["fecha_inicio_semana"] = origin
    frame["anio_epidemiologico"], frame["semana_epidemiologica"] = year, week
    seasonal = calendar_predictors(frame)
    for name in BASE[4:]:
        frame[name] = seasonal[name].to_numpy()
    return frame[BASE]


def predict_existing(model, matrix, parameters):
    import joblib
    import numpy as np
    from sklearn.ensemble import RandomForestClassifier
    from sigard_ml.official.spatial_ml.experiment_selection import BASE
    from sigard_ml.official.spatial_ml.experiment_protocol import RF_PARAMETERS

    require(type(model) is RandomForestClassifier and list(model.feature_names_in_) == BASE)
    require(parameters == RF_PARAMETERS and all(model.get_params()[k] == v for k, v in parameters.items()))
    require(len(model.estimators_) == 400 and model.n_features_in_ == 7 and list(model.classes_) == [0, 1])
    before = joblib.hash(model)
    probability = model.predict_proba(matrix)[:, 1]
    require(joblib.hash(model) == before, "estimator_mutated")
    require(len(probability) == len(matrix) and np.isfinite(probability).all() and ((probability >= 0) & (probability <= 1)).all())
    return probability


def infer_historical(requested, expected_policy, *, root=ROOT, now=None):
    """Explicit historical reproduction of the original file-based A service."""
    import importlib.metadata
    import joblib
    from sklearn.ensemble import RandomForestClassifier
    from sklearn.tree import DecisionTreeClassifier

    now = now or utc_now()
    policy, review, meta = load_policy(root, expected_policy)
    temporal = plan(requested, policy, now)
    require(platform.python_version() == meta["python"], "inference_runtime_incompatible")
    for package in ("scikit-learn", "numpy", "scipy", "pandas", "joblib", "threadpoolctl", "pyarrow"):
        require(importlib.metadata.version(package) == meta["runtime"][package], "inference_runtime_incompatible")
    static = static_context(root, policy["pins"])
    matrix = feature_matrix(static, datetime.fromisoformat(temporal["origin_week_start"]).date())
    # Hash and load the SAME bytes from the specifically authorized own estimator.
    model_bytes = content(root, FOLDER + "/" + MODEL, policy["pins"][FOLDER + "/" + MODEL], limit=32 * 1024 * 1024)
    def no_fit(*args, **kwargs):
        raise InferenceBlocked("training_forbidden")
    with ExitStack() as guards:
        for cls in (RandomForestClassifier, DecisionTreeClassifier):
            guards.enter_context(patch.object(cls, "fit", no_fit))
        model = joblib.load(BytesIO(model_bytes))
        probability = predict_existing(model, matrix, review["parameters"])
    content(root, FOLDER + "/" + MODEL, policy["pins"][FOLDER + "/" + MODEL])
    return {"schema_version": RESULT_SCHEMA, **temporal,
            "model_id": "A", "experiment_id": "spatial_rf_05c_v1", "training_version": VERSION,
            "territory_version": "capital-census-2022-public-v1", "horizon_weeks": 1,
            "data_kind": "private_experimental_inference", "score_semantics": "raw_class_1_score_uncalibrated",
            "prediction_target": "binary_experimental_record_presence_next_week",
            "retrospective": False, "operational_use_authorized": False, "publication_authorized": False,
            "provenance": {"source_snapshot_id": policy["snapshot_id"], "context_available_at": policy["static_available_at"],
                "model_available_at": policy["model_available_at"], "availability_basis": policy["availability_basis"],
                "historical_availability_accredited": False, "model_fitted": False,
                "context_semantics": "fixed_2022_census_context_not_current_population"},
            "rows": [{"radio_censal": radio, "experimental_score": float(score), "score_status": "available",
                "score_unavailable_reason": None, "data_availability": {"prediction_as_of": temporal["information_cutoff"],
                    "historical_context": "locally_observed_fixed_2022_context", "epidemiological_history": "not_used_by_model",
                    "known_lag_count": None, "operational_availability": "not_accredited"}}
                for radio, score in zip(static.radio_censal, probability)]}


def infer(requested, expected_policy, *, root=ROOT, now=None):
    # Frozen A is not in the principal PostgreSQL registry, and the database
    # reconstruction has not verified its full contract. Never fall back to
    # Parquet or deserialize the historical model as an operational substitute.
    raise InferenceBlocked('postgres_legacy_contract_unverified')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--capture", action="store_true")
    parser.add_argument('--historical-reproduction', action='store_true')
    args = parser.parse_args()
    try:
        if args.capture:
            require(args.historical_reproduction, 'historical_reproduction_required')
            result = capture()
        else:
            request = json.loads(sys.stdin.read(4097))
            require(set(request) == {"date", "policy_sha256"})
            function = infer_historical if args.historical_reproduction else infer
            result = function(request["date"], request["policy_sha256"])
        print(json.dumps(result, allow_nan=False))
    except Exception as error:
        code = error.code if isinstance(error, InferenceBlocked) else "inference_integrity_blocked"
        print(json.dumps({"blocked": code}))
        sys.exit(1)


if __name__ == "__main__":
    main()
