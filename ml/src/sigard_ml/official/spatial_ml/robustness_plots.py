"""Render aggregate-only payload using the existing isolated Matplotlib environment."""

import json
import os
from pathlib import Path
import sys


def render(path):
    path = Path(path)
    os.environ.setdefault("MPLCONFIGDIR", str(Path.cwd() / "ml/.tmp/phase5d-mpl-cache"))
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from datetime import date
    import platform
    plt.rcParams.update({"svg.hashsalt": "SIGARD-robustness-v1", "font.size": 10})
    data = json.loads(path.read_text(encoding="utf-8"))
    models = ("random_forest_A", "random_forest_B", "training_prevalence")
    names, styles = ("A", "B", "Baseline"), ("o-", "s--", "^:")
    def finish(fig, name):
        fig.supxlabel("Fuente: artefactos congelados 5C/5F · objetivos enero–junio 2024 · etiquetas experimentales", fontsize=8)
        fig.savefig(path.parent / (name + ".private.png"), dpi=160)
        fig.savefig(path.parent / (name + ".private.svg"), metadata={"Date": None})
        plt.close(fig)
    def dates(rows):
        return [date.fromisoformat(r["target_week"][:10]) for r in rows]
    fig, axes = plt.subplots(2, 2, figsize=(13, 8), layout="constrained")
    for ax, key, title in zip(axes.flat, ("prevalence", "mean_probability", "average_precision_pr_auc", "brier"),
                              ("Proporción positiva conocida", "Score medio en etiquetas conocidas", "Average Precision", "Brier (menor es mejor)")):
        for model, name, style in zip(models, names, styles):
            for part in ("train", "validation", "test"):
                rows = [r for r in data["weekly_metrics"] if r["model"] == model and r["partition"] == part]
                # Separate lines preserve the two purged weeks and partition boundaries.
                ax.plot(dates(rows), [r[key] if r[key] is not None else float("nan") for r in rows], style,
                        color={"A": "tab:blue", "B": "tab:orange", "Baseline": "dimgray"}[name],
                        label=name if part == "train" else None, markersize=3)
        ax.set(title=title, xlabel="Semana objetivo (fecha)", ylabel="Fracción / score (0–1)", ylim=(-.02, 1.02))
        ax.tick_params(axis="x", rotation=30)
        ax.grid(alpha=.2)
        ax.legend(fontsize=8)
    finish(fig, "weekly")
    fig, axes = plt.subplots(1, 2, figsize=(12, 5), layout="constrained")
    for model, name, style in zip(models, names, styles):
        rows = [r for r in data["calibration_bins"] if r["model"] == model and r["partition"] == "test"]
        axes[0].plot([r["mean_probability"] for r in rows], [r["fraction_positive"] for r in rows], style, label=name)
        axes[1].plot([r["mean_probability"] for r in rows], [r["n"] for r in rows], style, label=name)
    axes[0].plot([0, 1], [0, 1], color="gray", linestyle="--", label="Identidad")
    axes[0].set(title="Fiabilidad descriptiva en prueba (10 bins fijos)", xlabel="Score medio del bin (0–1)",
                ylabel="Fracción positiva experimental (0–1)", xlim=(0, 1), ylim=(0, 1))
    axes[1].set(title="Soporte de cada bin en prueba", xlabel="Score medio del bin (0–1)", ylabel="Celdas conocidas (n)", xlim=(0, 1))
    for ax in axes:
        ax.legend()
        ax.grid(alpha=.2)
    finish(fig, "reliability")
    fig, axes = plt.subplots(1, 2, figsize=(12, 5), layout="constrained")
    for ax, model, name in zip(axes, models[:2], names):
        for part in ("train", "validation", "test"):
            rows = [r for r in data["score_distributions"] if r["model"] == model and r["partition"] == part and r["population"] == "all_radios"]
            x = dates(rows)
            ax.fill_between(x, [r["q10"] for r in rows], [r["q90"] for r in rows], alpha=.2, color="tab:blue",
                            label="Cuantiles 10–90 (no IC)" if part == "train" else None)
            ax.plot(x, [r["median"] for r in rows], "o-", color="tab:blue", label="Mediana" if part == "train" else None)
        ax.set(title=f"Modelo {name}: dispersión entre 263 radios", xlabel="Semana objetivo (fecha)", ylabel="Score bruto (0–1)", ylim=(0, 1))
        ax.tick_params(axis="x", rotation=30)
        ax.legend(fontsize=8)
        ax.grid(alpha=.2)
    finish(fig, "dispersion")
    (path.parent / "render_runtime.private.json").write_text(json.dumps({
        "python": platform.python_version(), "matplotlib": matplotlib.__version__, "backend": matplotlib.get_backend(),
        "source": "analysis.private.json (aggregates only)", "training_performed": False}, indent=2), encoding="utf-8")


if __name__ == "__main__":
    render(sys.argv[1])
