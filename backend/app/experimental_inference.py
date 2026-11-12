"""Host-local bridge to the existing ML venv. No estimator in the API process."""

from datetime import datetime, timedelta, timezone
import json
import os
from pathlib import Path
import subprocess
from threading import BoundedSemaphore

from .experimental_results import ArtifactBlocked, calendar, local_bytes, require

POLICY = Path("data/interim/official/spatial_date_inference_v1/policy.private.json")
SCHEMA = "sigard-experimental-spatial-inference/1"
LOCAL_ZONE = timezone(timedelta(hours=-3))


def instant(value):
    try:
        result = datetime.fromisoformat(value)
        require(result.tzinfo is not None)
        return result.astimezone(timezone.utc)
    except (TypeError, ValueError):
        raise ArtifactBlocked("Inferencia privada bloqueada") from None


class LocalABInference:
    def __init__(self, root, policy_sha256):
        self.root = Path(root).resolve()
        self.policy_sha256 = policy_sha256
        self.slots = BoundedSemaphore(2)

    def policy(self):
        try:
            value = json.loads(local_bytes(self.root, POLICY, self.policy_sha256))
            require(set(value) == {"schema_version", "authorization_ref", "authorized_models", "static_available_at",
                "model_available_at", "availability_basis", "historical_availability_accredited", "snapshot_id", "pins"})
            require(value["schema_version"] == "sigard-private-ab-inference-authorization/1")
            require(value["authorized_models"] == ["A"])
            require(value["authorization_ref"] == "project_owner_existing_AB_date_inference_20261027")
            require(value["availability_basis"] == "local_hash_verified_observation_now")
            require(value["historical_availability_accredited"] is False)
            instant(value["static_available_at"])
            instant(value["model_available_at"])
            return value
        except Exception:
            raise ArtifactBlocked("Inferencia privada bloqueada") from None

    def window(self, now=None):
        now = now or datetime.now(timezone.utc)
        rules = calendar(self.root)
        try:
            year, week = rules.date_week(now.astimezone(LOCAL_ZONE).date())
            origin, _ = rules.week_bounds(year, week)
            start = origin + timedelta(days=7)
            rules.date_week(start)
        except ValueError:
            return None
        return start.isoformat(), (start + timedelta(days=6)).isoformat()

    def capabilities(self):
        policy = self.policy()
        now = datetime.now(timezone.utc)
        window = self.window(now)
        return {"model_a_enabled": False, "model_b_enabled": False,
                "target_week_start": window[0] if window else None,
                "target_week_end": window[1] if window else None,
                "context_available_at": policy["static_available_at"],
                "scope": "prospective_next_week_fixed_2022_context",
                "model_a_blocker": "postgres_legacy_contract_unverified",
                "model_b_blocker": "recent_epidemiological_history_unavailable"}

    def query(self, temporal, model, radios):
        policy = self.policy()
        now = datetime.now(timezone.utc)
        window = self.window(now)
        target = temporal["target_week_start"]
        if not window:
            return None, ["outside_calendar_coverage"]
        if target < window[0]:
            return None, ["historical_input_availability_unverified"]
        if target != window[0]:
            return None, ["horizon_not_supported"]
        if model == "B":
            return None, ["recent_epidemiological_history_unavailable"]
        if max(instant(policy["static_available_at"]), instant(policy["model_available_at"])) > now:
            return None, ["inputs_not_available_at_cutoff"]
        if not self.slots.acquire(blocking=False):
            return None, ["inference_busy"]
        try:
            python = self.root / "ml/venv" / ("Scripts/python.exe" if os.name == "nt" else "bin/python")
            if not python.is_file():
                return None, ["inference_runtime_unavailable"]
            # -I ignores PYTHONPATH/PYTHONHOME and the cwd; uses the installed own ML package.
            response = subprocess.run([str(python), "-I", "-B", "-m", "sigard_ml.official.spatial_ml.date_inference"],
                input=json.dumps({"date": temporal["requested_date"], "policy_sha256": self.policy_sha256}),
                capture_output=True, text=True, cwd=self.root, timeout=12,
                creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0)
            require(len(response.stdout) <= 1024 * 1024)
            output = json.loads(response.stdout)
            if response.returncode:
                code = output.get("blocked")
                if code in {"postgres_legacy_contract_unverified", "historical_input_availability_unverified", "horizon_not_supported",
                            "inputs_not_available_at_cutoff", "inference_runtime_incompatible"}:
                    return None, [code]
                raise ArtifactBlocked("Inferencia privada bloqueada")
            self.validate(output, temporal, radios, policy)
            return output, []
        except subprocess.TimeoutExpired:
            return None, ["inference_timeout"]
        except ArtifactBlocked:
            raise
        except Exception:
            raise ArtifactBlocked("Inferencia privada bloqueada") from None
        finally:
            self.slots.release()

    @staticmethod
    def validate(value, temporal, radios, policy):
        import math

        require(set(value) == {"schema_version", "target_week_start", "target_week_end", "target_epidemiological_year",
            "target_epidemiological_week", "origin_week_start", "origin_week_end", "information_cutoff", "calendar_version",
            "model_id", "experiment_id", "training_version", "territory_version", "horizon_weeks", "data_kind",
            "score_semantics", "prediction_target", "retrospective", "operational_use_authorized", "publication_authorized",
            "provenance", "rows"})
        require(value["schema_version"] == SCHEMA and value["data_kind"] == "private_experimental_inference")
        require(value["model_id"] == "A" and value["experiment_id"] == "spatial_rf_05c_v1"
                and value["training_version"] == "official-spatial-rf-research-0.5c.0")
        require(value["territory_version"] == "capital-census-2022-public-v1" and value["horizon_weeks"] == 1)
        require(value["score_semantics"] == "raw_class_1_score_uncalibrated"
                and value["prediction_target"] == "binary_experimental_record_presence_next_week")
        require(value["retrospective"] is False and value["operational_use_authorized"] is False and value["publication_authorized"] is False)
        for key in ("target_week_start", "target_week_end", "target_epidemiological_year", "target_epidemiological_week",
                    "origin_week_start", "origin_week_end", "calendar_version"):
            require(value[key] == temporal[key])
        cutoff = instant(value["information_cutoff"])
        local_day = cutoff.astimezone(LOCAL_ZONE).date().isoformat()
        require(temporal["origin_week_start"] <= local_day <= temporal["origin_week_end"] and cutoff <= datetime.now(timezone.utc))
        provenance = value["provenance"]
        require(set(provenance) == {"source_snapshot_id", "context_available_at", "model_available_at", "availability_basis",
                                   "historical_availability_accredited", "model_fitted", "context_semantics"})
        require(provenance["source_snapshot_id"] == policy["snapshot_id"] and provenance["availability_basis"] == policy["availability_basis"])
        require(provenance["historical_availability_accredited"] is False and provenance["model_fitted"] is False)
        require(provenance["context_semantics"] == "fixed_2022_census_context_not_current_population")
        for field, source in (("context_available_at", "static_available_at"), ("model_available_at", "model_available_at")):
            require(provenance[field] == policy[source] and instant(provenance[field]) <= cutoff)
        require(len(value["rows"]) == len(radios) == 263)
        require({row["radio_censal"] for row in value["rows"]} == set(radios))
        for row in value["rows"]:
            require(set(row) == {"radio_censal", "experimental_score", "score_status", "score_unavailable_reason", "data_availability"})
            require(row["score_status"] == "available" and row["score_unavailable_reason"] is None)
            score = row["experimental_score"]
            require(type(score) in (int, float) and math.isfinite(score) and 0 <= score <= 1)
            require(row["data_availability"] == {"prediction_as_of": value["information_cutoff"],
                "historical_context": "locally_observed_fixed_2022_context", "epidemiological_history": "not_used_by_model",
                "known_lag_count": None, "operational_availability": "not_accredited"})
