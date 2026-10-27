"""Paired synthesis of frozen V3 predictions; no fitting or source ingestion.

All resampling units are target weeks, containing every eligible radio. Blocks
never cross calendar gaps or fitted-fold boundaries. Intervals are descriptive
after model selection, not selection-adjusted confirmatory evidence.
"""
import argparse
from datetime import timedelta
import hashlib
import json
from pathlib import Path

import numpy as np
import pandas as pd

from sigard_ml.forecasting.contracts import require
from sigard_ml.forecasting.evaluation import count_metrics
from sigard_ml.forecasting.v3 import BASELINES, CANDIDATES, FEATURES, VERSION

SEED = 20261026
RESAMPLES = 10000
METHODS = (*CANDIDATES, *BASELINES)
ROOT = Path(__file__).resolve().parents[4]
DEFAULT_ARTIFACT = ROOT / "ml/artifacts/official" / VERSION


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def read_json(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def write_json(path, value):
    with Path(path).open("x", encoding="utf-8") as stream:
        json.dump(value, stream, ensure_ascii=False, indent=2, sort_keys=True, allow_nan=False)


class FrozenArtifact:
    """Integrity checks before deserialization. Only trusted local joblib is allowed."""
    def __init__(self, directory):
        self.directory = Path(directory).resolve()
        self.manifest = read_json(self.directory / "manifest.private.json")
        require(self.manifest.get("artifact_version") == VERSION, "Versión V3 incompatible")
        self.inputs = {"manifest.private.json": digest(self.directory / "manifest.private.json")}

    def path(self, name):
        path = (self.directory / name).resolve()
        require(path.is_relative_to(self.directory), "Ruta fuera del artefacto")
        sha = digest(path)
        require(self.manifest["outputs_sha256"].get(name) == sha, "Integridad V3 inválida")
        self.inputs[name] = sha
        return path

    def json(self, name):
        return read_json(self.path(name))

    def frame(self, name):
        return pd.read_parquet(self.path(name))

    def unchanged(self):
        require(all(digest(self.directory / name) == sha for name, sha in self.inputs.items()),
                "Se modificó un artefacto congelado")


def paired_frame(frame, horizon, methods=METHODS):
    require(set(("radio_id", "origin_week", "target_week", "target_count", *methods)) <= set(frame),
            "Faltan columnas pareadas")
    require(len(frame) > 0 and not frame.duplicated(["radio_id", "target_week"]).any(),
            "Claves vacías o duplicadas")
    require(frame[["radio_id", "origin_week", "target_week"]].notna().all().all(), "Clave desconocida")
    require(all(t - o == timedelta(weeks=horizon) for t, o in zip(frame.target_week, frame.origin_week)),
            "Horizonte desalineado")
    require(all(t.weekday() == o.weekday() == 6 for t, o in zip(frame.target_week, frame.origin_week)),
            "Semana no dominical")
    result = frame.loc[frame.target_count.notna()].copy()
    require(len(result) > 0, "Sin etiquetas utilizables")
    # Missing predictions are an error, never an outcome-dependent row exclusion.
    for method in methods:
        count_metrics(result.target_count, result[method])
    return result.sort_values(["target_week", "radio_id"]).reset_index(drop=True)


def week_statistics(frame, method, baseline):
    rows = []
    for target, group in frame.groupby("target_week", sort=True):
        actual = group.target_count.to_numpy(float)
        ml, ref = group[method].to_numpy(float) - actual, group[baseline].to_numpy(float) - actual
        rows.append(dict(target_week=target, fold=int(group.fold.iloc[0]) if "fold" in group else -1,
                         n=len(group), actual_total=float(actual.sum()),
                         ml_ae=float(abs(ml).sum()), ref_ae=float(abs(ref).sum()),
                         ml_se=float((ml ** 2).sum()), ref_se=float((ref ** 2).sum()),
                         ml_error=float(ml.sum()), ref_error=float(ref.sum())))
    return pd.DataFrame(rows)


def block_interval(weekly, length, *, resamples=RESAMPLES, seed=SEED):
    """Paired moving blocks stratified by fitted fold, truncated at gaps.

    Every observed week can start a block; a gap or fold end shortens it.
    Resample blocks within each fold until its original number of weeks is
    reached. RMSE is recomputed from summed squared errors, never averaged.
    """
    require(length >= 1 and resamples >= 100, "Remuestreo inválido")
    weekly = weekly.sort_values("target_week").reset_index(drop=True)
    runs, current = [], []
    for i, row in weekly.iterrows():
        if current and (row.target_week - weekly.iloc[current[-1]].target_week != timedelta(weeks=1)
                        or row.fold != weekly.iloc[current[-1]].fold):
            runs.append(current)
            current = []
        current.append(i)
    runs.append(current)
    rng = np.random.default_rng(seed)
    indices = []
    for fold in weekly.fold.unique():
        fold_runs = [run for run in runs if weekly.iloc[run[0]].fold == fold]
        size = sum(len(run) for run in fold_runs)
        blocks = [run[start:start + length] for run in fold_runs for start in range(len(run))]
        padded = np.full((len(blocks), max(map(len, blocks))), -1, dtype=int)
        for i, block in enumerate(blocks):
            padded[i, :len(block)] = block
        draws = padded[rng.integers(0, len(blocks), size=(resamples, size))].reshape(resamples, -1)
        valid = draws >= 0
        retained = valid & (np.cumsum(valid, axis=1) <= size)
        indices.append(draws[retained].reshape(resamples, size))
    indices = np.concatenate(indices, axis=1)
    totals = {key: weekly[key].to_numpy()[indices].sum(axis=1)
              for key in ("n", "ml_ae", "ref_ae", "ml_se", "ref_se", "ml_error", "ref_error")}
    changes = dict(mae=(totals["ml_ae"] - totals["ref_ae"]) / totals["n"],
                   rmse=np.sqrt(totals["ml_se"] / totals["n"]) - np.sqrt(totals["ref_se"] / totals["n"]),
                   bias=(totals["ml_error"] - totals["ref_error"]) / totals["n"])
    return dict(block_weeks=length, resamples=resamples, seed=seed, run_weeks=[len(r) for r in runs],
                variable_resampling=bool(any(sum(weekly.fold == f) > 1 for f in weekly.fold.unique())),
                intervals={k: np.quantile(v, [.025, .975]).tolist() for k, v in changes.items()})


def compare(frame, method, baseline, *, high_threshold, horizon, resamples=RESAMPLES):
    weekly = week_statistics(frame, method, baseline)
    ml, ref = count_metrics(frame.target_count, frame[method]), count_metrics(frame.target_count, frame[baseline])
    delta = (weekly.ml_ae - weekly.ref_ae) / weekly.n
    thresholds = (frame.groupby("target_week").high_week_threshold.first().to_numpy()
                  if "high_week_threshold" in frame else high_threshold)
    high = weekly.actual_total >= thresholds
    high_frame = frame.loc[frame.target_week.isin(weekly.loc[high, "target_week"])]
    gain = (weekly.ref_ae - weekly.ml_ae).sort_values(ascending=False)
    remaining = weekly.drop(gain.index[:min(3, len(weekly) - 1)])
    years = {}
    for year in sorted({d.year for d in frame.target_week}):
        part = frame.loc[frame.target_week.map(lambda d: d.year == year)]
        years[str(year)] = dict(n=len(part), weeks=int(part.target_week.nunique()),
                               ml=count_metrics(part.target_count, part[method]),
                               persistence=count_metrics(part.target_count, part[baseline]))
    return dict(method=method, baseline=baseline, n=len(frame), weeks=len(weekly),
                ml=ml, persistence=ref, delta_mae=ml["mae"] - ref["mae"], delta_rmse=ml["rmse"] - ref["rmse"],
                mae_reduction_percent=100 * (1 - ml["mae"] / ref["mae"]) if ref["mae"] else None,
                bias_limit=abs(ref["mean_bias"]) + .05 * float(frame.target_count.mean()),
                bias_acceptable=abs(ml["mean_bias"]) <= abs(ref["mean_bias"]) + .05 * float(frame.target_count.mean()),
                wins_ml=int((delta < -1e-12).sum()), wins_persistence=int((delta > 1e-12).sum()),
                ties=int((abs(delta) <= 1e-12).sum()),
                high_week_threshold="fold_training_q80" if "high_week_threshold" in frame else high_threshold,
                high_weeks=int(high.sum()),
                high_week_cells=(dict(ml=count_metrics(high_frame.target_count, high_frame[method]),
                                      persistence=count_metrics(high_frame.target_count, high_frame[baseline])) if len(high_frame) else None),
                high_week_total_rmse=dict(ml=float(np.sqrt(np.mean(weekly.loc[high, "ml_error"] ** 2))),
                                          persistence=float(np.sqrt(np.mean(weekly.loc[high, "ref_error"] ** 2)))) if high.any() else None,
                delta_mae_without_best_3_weeks=float((remaining.ml_ae.sum() - remaining.ref_ae.sum()) / remaining.n.sum()),
                by_year=years,
                bootstrap=[block_interval(weekly, length, resamples=resamples)
                           for length in sorted({1, 3, max(4, horizon), 8})])


def validate_cached(frame, panel, horizon):
    paired = paired_frame(frame, horizon)
    eligible = panel.loc[panel.predictor_admissible & panel.target_count.notna()]
    joined = paired.merge(eligible[["radio_id", "origin_week", "target_week", "target_count"]],
                          on=["radio_id", "origin_week", "target_week"], suffixes=("", "_panel"),
                          how="left", validate="one_to_one")
    require(joined.target_count_panel.notna().all() and joined.target_count.eq(joined.target_count_panel).all(),
            "Etiquetas/claves diferentes al panel congelado")
    return paired


def synthesize(artifact):
    """Use original selection and thresholds. Never rank candidates on old test."""
    metrics = artifact.json("metrics.private.json")
    selection = artifact.json("selection.private.json")
    provenance = artifact.json("provenance.private.json")
    output = dict(protocol=dict(seed=SEED, resamples=RESAMPLES, primary_horizon=1,
                               differences="ML minus persistence", selection_adjusted=False,
                               independent_confirmation=False), horizons={},
                  independence=dict(source_covered_weeks=len(provenance["source_input_evidence"]["snapshot_scenario"]["covered_weeks"]),
                                    last_seen_week=max(provenance["source_input_evidence"]["snapshot_scenario"]["covered_weeks"]),
                                    reason="Development used for fitting/selection; 2024 comparison previously observed in V1/V2; missing/2022/gaps not eligible independent outcomes"))
    weekly_output = []
    for h in (1, 2, 4):
        panel = artifact.frame(f"horizon_{h}/modeling_panel.private.parquet")
        dev = panel.loc[panel.partition.isin(["train", "validation"]) & panel.predictor_admissible & panel.target_count.notna()]
        high_threshold = float(dev.groupby("target_week").target_count.sum().quantile(.8))
        original = metrics[str(h)]["development"]
        for fold in original["folds"]:
            require(fold["train_target_end"] < fold["validation_first_origin"], "Purga temporal inválida")
        horizon = dict(best_ml=selection["horizons"][str(h)]["best_ml"],
                       promotion_approved=selection["horizons"][str(h)]["promotion_approved"],
                       original_selection=selection["horizons"][str(h)], periods={})
        for period, filename in (("internal_oof", "development_predictions.private.parquet"),
                                 ("previously_observed", "comparison_predictions.private.parquet")):
            frame = validate_cached(artifact.frame(f"horizon_{h}/{filename}"), panel, h)
            if period == "previously_observed":
                expected = panel.loc[panel.partition.eq("test") & panel.predictor_admissible & panel.target_count.notna()]
                require(len(frame) == len(expected), "Cohorte test incompleta")
                require(max(dev.target_end) < min(frame.origin_week), "Ajuste final posterior al primer origen")
            else:
                require(len(frame) == original["validation_rows"] and frame.target_week.nunique() == original["validation_weeks"],
                        "Cohorte OOF diferente")
            frozen_metrics = original["validation"] if period == "internal_oof" else metrics[str(h)]["comparison_previously_observed"]
            for name in METHODS:
                calculated = count_metrics(frame.target_count, frame[name])
                require(all(np.isclose(calculated[k], frozen_metrics[name][k], rtol=1e-10, atol=1e-12)
                            for k in ("mae", "rmse", "mean_bias")), "Métricas diferentes a las originales")
            rows = []
            for method in CANDIDATES:
                for baseline in BASELINES[:2]:
                    row = compare(frame, method, baseline, high_threshold=high_threshold, horizon=h)
                    if period == "internal_oof":
                        # Fold-local high-week thresholds, fixed before each validation block.
                        row["original_high_week_metrics"] = original["validation"][method]["high_week_known_subset"]
                    rows.append(row)
                    w = week_statistics(frame, method, baseline)
                    w["method"], w["baseline"], w["horizon"], w["period"] = method, baseline, h, period
                    weekly_output.append(w)
            horizon["periods"][period] = dict(first_week=str(frame.target_week.min()), last_week=str(frame.target_week.max()),
                n=len(frame), weeks=int(frame.target_week.nunique()), radio_min=int(frame.groupby("target_week").size().min()),
                radio_max=int(frame.groupby("target_week").size().max()), comparisons=rows,
                all_methods={name: count_metrics(frame.target_count, frame[name]) for name in METHODS})
        output["horizons"][str(h)] = horizon
    artifact.unchanged()
    output["input_sha256"] = artifact.inputs
    return output, pd.concat(weekly_output, ignore_index=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--artifact", type=Path, default=DEFAULT_ARTIFACT)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    destination = args.output.resolve()
    require(destination.is_relative_to(ROOT / "data/interim"), "Salida privada sólo bajo data/interim")
    require(not destination.exists(), "No sobrescribir síntesis")
    result, weekly = synthesize(FrozenArtifact(args.artifact))
    destination.mkdir(parents=True)
    write_json(destination / "comparison.private.json", result)
    weekly.to_parquet(destination / "weekly.private.parquet", index=False)
    write_json(destination / "manifest.private.json", dict(
        implementation_sha256=digest(Path(__file__)),
        outputs_sha256={p.name: digest(p) for p in destination.iterdir()}))
    print(json.dumps(dict(completed=True, horizons=list(result["horizons"]), independent=False)))


if __name__ == "__main__":
    main()
