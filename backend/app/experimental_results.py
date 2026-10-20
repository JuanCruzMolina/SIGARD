"""Read-only projection of explicitly pinned, local research artifacts. No ML runtime."""

import hashlib
import importlib.util
import json
import math
import re
import sys
from datetime import date, timedelta
from io import BytesIO
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
SCHEMA = "sigard-retrospective-spatial-score/1"
CALENDAR = "ar-snvs-2020-2026-v1"
TERRITORY = "capital-census-2022-public-v1"
MODELS = {
    "A": ("spatial_rf_05c_v1", "official-spatial-rf-research-0.5c.0"),
    "B": ("spatial_rf_B_05f_v1", "official-spatial-rf-B-research-0.5f.0"),
}
KEYS = ["radio_censal", "fecha_inicio_semana"]
MISSING = [f"local_presencia_exp_rezago_{i}_missing" for i in range(1, 5)]
METRICS = ("precision", "recall", "f1", "average_precision_pr_auc", "roc_auc", "brier")
LIMITATIONS = [
    "experimental_assumed_negatives", "provisional_positive_labels", "coverage_not_verified",
    "historical_record_availability_not_accredited", "census_historical_availability_not_accredited",
    "date_classification_and_spatial_uncertainty", "spatial_and_temporal_dependence",
    "previously_examined_evaluation_period", "uncalibrated_score_not_validated_epidemiological_risk",
    "retrospective_only_no_operational_forecast",
]


class ArtifactBlocked(ValueError):
    pass


class NotAvailable(ValueError):
    pass


def require(condition):
    if not condition:
        raise ArtifactBlocked("Artefactos experimentales bloqueados")


def local_bytes(root, relative, expected=None, limit=16 * 1024 * 1024):
    """Hash and decode the SAME bounded bytes; reject links and traversal."""
    root = root.resolve()
    path = root / relative
    require(not Path(relative).is_absolute() and ".." not in Path(relative).parts)
    require(path.resolve().is_relative_to(root))
    require(not any(part.is_symlink() or part.is_junction() for part in [path, *path.parents] if part != root.parent))
    require(path.is_file() and path.stat().st_size <= limit)
    with path.open("rb") as source:
        value = source.read(limit + 1)
    require(len(value) <= limit)
    if expected is not None:
        require(isinstance(expected, str) and re.fullmatch(r"[a-f0-9]{64}", expected) is not None)
        require(hashlib.sha256(value).hexdigest() == expected)
    return value


def calendar(root):
    # Reuse the existing pure calendar module without importing pipelines or sklearn.
    name = "_sigard_research_calendar_rules"
    if name not in sys.modules:
        spec = importlib.util.spec_from_file_location(name, root / "ml/src/sigard_ml/official/calendar_rules.py")
        module = importlib.util.module_from_spec(spec)
        sys.modules[name] = module
        # Execute trusted repository code in memory, without creating bytecode on disk.
        source = local_bytes(root, "ml/src/sigard_ml/official/calendar_rules.py")
        exec(compile(source, spec.origin, "exec"), module.__dict__)
    return sys.modules[name].DEFAULT_CALENDAR


class ExperimentalResults:
    def __init__(self, registry_path, registry_sha256, *, root=ROOT):
        self.root = Path(root).resolve()
        self.registry_path = Path(registry_path)
        self.registry_sha256 = registry_sha256

    def _read(self, *, include_evaluation=False):
        """Revalidate every query; never silently serve a stale cached snapshot."""
        try:
            return self._validated(include_evaluation=include_evaluation)
        except ArtifactBlocked:
            raise
        except Exception:
            raise ArtifactBlocked("Artefactos experimentales bloqueados") from None

    def _validated(self, *, include_evaluation=False):
        import pyarrow.parquet as pq  # Optional dependency, local research only.

        relative = self.registry_path.relative_to(self.root) if self.registry_path.is_absolute() else self.registry_path
        require(relative.as_posix().startswith("data/interim/official/"))
        require(relative.name.endswith(".private.json"))
        registry = json.loads(local_bytes(self.root, relative, self.registry_sha256))
        require(set(registry) == {"schema_version", "local_read_authorized", "territory_version", "models"})
        require(registry["schema_version"] == SCHEMA and registry["local_read_authorized"] is True)
        require(registry["territory_version"] == TERRITORY)
        require(isinstance(registry["models"], dict) and 0 < len(registry["models"]) <= 2)
        require(set(registry["models"]) <= set(MODELS))
        approved = json.loads(local_bytes(self.root, "frontend/security/public-assets.json"))["assets"]
        geo = local_bytes(self.root, "frontend/public/data/territorial_context.geojson")
        require(hashlib.sha256(geo.replace(b"\r\n", b"\n")).hexdigest() == approved["data/territorial_context.geojson"])
        radios = [f["properties"]["radio_id"] for f in json.loads(geo)["features"]]
        require(len(radios) == len(set(radios)) == 263)
        require(all(isinstance(r, str) and re.fullmatch(r"[0-9]+", r) for r in radios))
        result, evaluation_rows = {}, None
        for model, entry in registry["models"].items():
            require(set(entry) == {"manifest_sha256"})
            experiment, version = MODELS[model]
            folder = Path("data/processed/official") / experiment
            manifest = json.loads(local_bytes(self.root, folder / "integrity_manifest.private.json", entry["manifest_sha256"]))
            require(manifest["version"] == version)
            hashes = manifest["outputs_sha256"]

            def read_json(name):
                return json.loads(local_bytes(self.root, folder / name, hashes[name]))

            def table(name, columns, expected_rows=5260):
                value = local_bytes(self.root, folder / name, hashes[name])
                parquet = pq.ParquetFile(BytesIO(value))
                require(parquet.metadata.num_rows == expected_rows)
                return parquet.read(columns=columns).to_pylist()

            review = read_json("review.private.json")
            require(review["version"] == version and review["training_authorized"] is False)
            require(review["research_training_authorized"] is True)
            if model == "A":
                meta = read_json("metadata.private.json")
                require(meta["version"] == version and meta["calendar_version"] == CALENDAR)
                require(review["coverage_verified"] is False)
            else:
                require(review["operational_model_enabled"] is False and review["test_previously_examined"] is True)
                if include_evaluation and "metrics.private.parquet" in hashes:
                    evaluation_rows = table("metrics.private.parquet", ["model", "partition", "n", "positive", "negative",
                        "grid_rows", "unknown_excluded", "threshold", *METRICS], expected_rows=9)
            score_key = f"random_forest_{model}_probability"
            rows = table("predictions_radio_week.private.parquet", KEYS + ["fecha_inicio_semana_objetivo", "partition", score_key])
            availability = {}
            if model == "B":
                for row in table("inference_matrix.private.parquet", KEYS + MISSING):
                    key = (row[KEYS[0]], row[KEYS[1]])
                    require(key not in availability)
                    require(all(type(row[k]) in (int, float) and row[k] in (0, 1) for k in MISSING))
                    availability[key] = 4 - sum(int(row[k]) for k in MISSING)
            weeks, identities = {}, set()
            for row in rows:
                radio, origin, target, partition = (row[k] for k in KEYS + ["fecha_inicio_semana_objetivo", "partition"])
                require(radio in radios and type(origin) is date and type(target) is date)
                require(origin.weekday() == 6 and target == origin + timedelta(days=7))
                ranges = {"train": (date(2024, 1, 7), date(2024, 2, 25)),
                          "validation": (date(2024, 3, 10), date(2024, 4, 28)),
                          "test": (date(2024, 5, 12), date(2024, 6, 2))}
                require(partition in ranges and ranges[partition][0] <= target <= ranges[partition][1])
                require((radio, origin) not in identities)
                identities.add((radio, origin))
                score = row[score_key]
                require(score is None or (type(score) in (float, int) and math.isfinite(score) and 0 <= score <= 1))
                count = availability.get((radio, origin)) if model == "B" else None
                require(model == "A" or count is not None)
                year, week = calendar(self.root).date_week(target)
                if target.isoformat() not in weeks:
                    weeks[target.isoformat()] = {"schema_version": SCHEMA, "model_id": model,
                        "experiment_id": experiment, "training_version": version, "territory_version": TERRITORY,
                        "data_kind": "official_experimental_retrospective",
                        "prediction_target": "binary_experimental_record_presence_next_week",
                        "score_semantics": "raw_class_1_score_uncalibrated", "calendar_version": CALENDAR,
                        "origin_week_start": origin.isoformat(), "origin_week_end": (origin + timedelta(days=6)).isoformat(),
                        "target_week_start": target.isoformat(), "target_week_end": (target + timedelta(days=6)).isoformat(),
                        "target_epidemiological_year": year, "target_epidemiological_week": week,
                        "coverage_scenario": "spatial_assumed_2024_v1", "coverage_verified": False,
                        "evaluation_partition": partition, "previously_examined": True, "retrospective": True,
                        "operational_use_authorized": False, "publication_authorized": False,
                        "interpretation_limitations": LIMITATIONS, "rows": []}
                collection = weeks[target.isoformat()]
                require(collection["evaluation_partition"] == partition)
                collection["rows"].append({"radio_censal": radio, "experimental_score": score,
                    "score_status": "not_computed" if score is None else "available",
                    "score_unavailable_reason": "frozen_score_missing" if score is None else None,
                    "data_availability": {"historical_context": "retrospective_unverified",
                        "epidemiological_history": "not_used_by_model" if model == "A" else (
                            "retrospective_complete" if count == 4 else "retrospective_partial" if count else "retrospective_unknown"),
                        "known_lag_count": count, "operational_availability": "not_accredited", "prediction_as_of": None}})
            require(len(weeks) == 20)
            require(all({r["radio_censal"] for r in w["rows"]} == set(radios) for w in weeks.values()))
            require(model == "A" or set(availability) == identities)
            for w in weeks.values():
                w["rows"].sort(key=lambda r: r["radio_censal"])
            result[model] = weeks
        if set(result) == {"A", "B"}:
            require(set(result["A"]) == set(result["B"]))
        return (result, evaluation_rows) if include_evaluation else result

    def get_evaluation(self):
        values, rows = self._read(include_evaluation=True)
        if set(values) != {"A", "B"} or rows is None:
            raise NotAvailable("not_available")
        indexed = {}
        for row in rows:
            require(isinstance(row["model"], str) and isinstance(row["partition"], str))
            key = row["model"], row["partition"]
            require(key not in indexed)
            indexed[key] = row
        require(set(indexed) == {(model, part) for model in ("random_forest_A", "random_forest_B", "training_prevalence")
                                 for part in ("train", "validation", "test")})
        partitions = []
        for part in ("train", "validation", "test"):
            weeks = sorted(w for w, collection in values["A"].items() if collection["evaluation_partition"] == part)
            models, cohort = [], None
            for model in ("A", "B"):
                row = indexed["random_forest_" + model, part]
                require(row["threshold"] == .5)
                for field in ("n", "positive", "negative", "grid_rows", "unknown_excluded"):
                    require(type(row[field]) is int and row[field] >= 0)
                require(row["grid_rows"] == 263 * len(weeks) and row["n"] > 0
                        and row["n"] + row["unknown_excluded"] == row["grid_rows"]
                        and row["positive"] + row["negative"] == row["n"])
                composition = tuple(row[field] for field in ("n", "positive", "negative", "unknown_excluded"))
                require(cohort is None or cohort == composition)
                cohort = composition
                metrics = {key: row[key] for key in METRICS}
                require(all(value is None or (type(value) in (float, int) and math.isfinite(value) and 0 <= value <= 1)
                            for value in metrics.values()))
                require(metrics["brier"] is not None)
                models.append({"model_id": model, "experiment_id": MODELS[model][0],
                               "training_version": MODELS[model][1], "metrics": metrics})
            partitions.append({"partition": part, "target_week_start": weeks[0],
                "target_week_end": values["A"][weeks[-1]]["target_week_end"], "week_count": len(weeks),
                "evaluated_radio_weeks": cohort[0], "models": models})
        return {"schema_version": "sigard-retrospective-spatial-evaluation/1", "calendar_version": CALENDAR,
                "coverage_scenario": "spatial_assumed_2024_v1", "coverage_verified": False,
                "retrospective": True, "previously_examined": True, "operational_use_authorized": False,
                "publication_authorized": False, "evaluation_source": "frozen_comparative_evaluation",
                "threshold": .5, "interpretation_limitations": LIMITATIONS, "partitions": partitions}

    def history(self, radio):
        values = self._read()
        if not re.fullmatch(r"[0-9]+", radio):
            raise NotAvailable("not_available")
        comparisons = []
        for target in sorted({week for model in values.values() for week in model}):
            results = []
            for model in ("A", "B"):
                collection = values.get(model, {}).get(target)
                row = next((r for r in collection["rows"] if r["radio_censal"] == radio), None) if collection else None
                if row is not None:
                    results.append({**{k: v for k, v in collection.items() if k != "rows"}, "rows": [row]})
            if results:
                comparisons.append({"schema_version": SCHEMA, "radio_censal": radio, "target_week_start": target,
                    "comparable": len(results) == 2 and all(c["rows"][0]["score_status"] == "available" for c in results), "results": results})
        if not comparisons:
            raise NotAvailable("not_available")
        return {"schema_version": SCHEMA, "radio_censal": radio, "comparisons": comparisons}

    def list_experiments(self):
        values = self._read()
        return {"schema_version": SCHEMA, "models": [{"model_id": m, "experiment_id": MODELS[m][0],
            "training_version": MODELS[m][1], "weeks": [{k: w[k] for k in (
                "target_week_start", "target_week_end", "target_epidemiological_year", "target_epidemiological_week",
                "evaluation_partition")} for _, w in sorted(weeks.items())]} for m, weeks in sorted(values.items())]}

    def get_retrospective_scores(self, model, experiment, target):
        values = self._read()
        if model not in values or MODELS[model][0] != experiment or target not in values[model]:
            raise NotAvailable("not_available")
        return values[model][target]

    def compare(self, radio, target):
        values = self._read()
        if not re.fullmatch(r"[0-9]+", radio):
            raise NotAvailable("not_available")
        output = []
        for model in ("A", "B"):
            collection = values.get(model, {}).get(target)
            if collection is None:
                continue
            row = next((r for r in collection["rows"] if r["radio_censal"] == radio), None)
            if row is not None:
                output.append({**{k: v for k, v in collection.items() if k != "rows"}, "rows": [row]})
        if not output:
            raise NotAvailable("not_available")
        return {"schema_version": SCHEMA, "radio_censal": radio, "target_week_start": target,
                "comparable": len(output) == 2 and all(c["rows"][0]["score_status"] == "available" for c in output),
                "results": output}
