"""Render offline de agregados de Fase 5D, en un entorno sólo de gráficos."""

import argparse
from datetime import date
import json
import os
from pathlib import Path
import platform

os.environ.setdefault("MPLCONFIGDIR", str(Path.cwd() / "ml/.tmp/phase5d-mpl-cache"))

import matplotlib
matplotlib.use("Agg")
import matplotlib.dates as mdates
import matplotlib.pyplot as plt
from matplotlib.ticker import PercentFormatter
import numpy as np

PARTS = ("train", "validation", "test")
LABELS = {"train": "Entrenamiento (ajuste)", "validation": "Validación", "test": "Prueba"}
RF, BASELINE = "random_forest_A", "training_prevalence"
TEAL, ORANGE, GREY = "#007C83", "#C46628", "#68737D"
FEATURES = {"superficie_km2": "Superficie", "poblacion": "Población", "densidad_poblacional": "Densidad",
    "cantidad_vecinos": "Vecinos", "estacionalidad_coseno": "Coseno", "estacionalidad_seno": "Seno",
    "semana_epidemiologica": "Semana"}


def render(data, output):
    output.mkdir(parents=True, exist_ok=False)
    plt.rcParams.update({"font.family": "DejaVu Sans", "font.size": 10,
        "axes.spines.top": False, "axes.spines.right": False, "axes.titleweight": "semibold",
        "svg.hashsalt": "SIGARD-5D-v1", "savefig.facecolor": "white"})
    files = []
    source = "Privado · Fase 5C congelada · radio–semana · positivos provisionales y negativos asumidos · sin inferencia IID"

    def save(fig, name, caption):
        fig.supxlabel(caption + "\n" + source, fontsize=8)
        for extension in ("png", "svg"):
            path = output / f"{name}.{extension}"
            fig.savefig(path, dpi=180, metadata={"Date": None} if extension == "svg" else {"Software": "SIGARD Fase 5D"})
            files.append(path.name)
        plt.close(fig)

    fig, axes = plt.subplots(2, 1, figsize=(11.5, 7.5), layout="constrained", sharex=True)
    for i, part in enumerate(PARTS):
        rows = sorted([r for r in data["weekly"] if r["model"] == RF and r["partition"] == part], key=lambda r: r["target_week"])
        x = [date.fromisoformat(r["target_week"]) for r in rows]
        axes[0].plot(x, [r["prevalence"] for r in rows], "o-", color=TEAL, label="Prevalencia conocida" if i == 0 else None)
        axes[0].plot(x, [r["mean_probability"] for r in rows], "s--", color=ORANGE, label="Probabilidad RF, etiquetas conocidas" if i == 0 else None)
        axes[0].plot(x, [r["mean_probability_all_radios"] for r in rows], ":", color=GREY, label="Probabilidad RF, 263 radios" if i == 0 else None)
        axes[1].plot(x, [r["known_label_coverage"] for r in rows], "o-", color=TEAL)
        axes[0].text(x[len(x) // 2], 1.01, LABELS[part], ha="center", fontsize=9)
    prior = next(r["mean_probability"] for r in data["summary"] if r["model"] == BASELINE)
    axes[0].axhline(prior, color=GREY, linestyle="--", label="Baseline: prevalencia de entrenamiento")
    axes[0].set(title="Probabilidades y presencia registrada durante ascenso, pico y descenso", ylabel="Probabilidad / fracción positiva", ylim=(0, 1.08))
    axes[0].yaxis.set_major_formatter(PercentFormatter(1))
    axes[0].legend(loc="upper left", bbox_to_anchor=(0, .90), fontsize=8)
    axes[1].set(ylabel="Fracción con etiqueta conocida", xlabel="Inicio de semana objetivo (2024)", ylim=(.7, 1.02))
    axes[1].yaxis.set_major_formatter(PercentFormatter(1))
    axes[1].xaxis.set_major_formatter(mdates.DateFormatter("%d/%m"))
    for ax in axes:
        ax.grid(axis="y", alpha=.2)
    save(fig, "01_temporal_probability", "07/01–08/06/2024. Líneas interrumpidas en las semanas purgadas; desconocidos excluidos de prevalencia.")

    fig, axes = plt.subplots(2, 3, figsize=(13, 8), layout="constrained")
    for column, part in enumerate(PARTS):
        n = next(r["n"] for r in data["summary"] if r["model"] == RF and r["partition"] == part)
        for model, color, marker, label in ((RF, TEAL, "o", "RF A"), (BASELINE, ORANGE, "s", "Baseline")):
            bins = sorted([r for r in data["calibration"] if r["model"] == model and r["partition"] == part], key=lambda r: r["bin"])
            axes[0, column].plot([r["mean_probability"] for r in bins], [r["fraction_positive"] for r in bins],
                marker=marker, color=color, label=label, linestyle="-" if model == RF else "None")
            axes[1, column].bar([(r["lower"] + r["upper"]) / 2 for r in bins], [r["n"] for r in bins],
                width=.08 if model == RF else .035, color=color, alpha=.65, label=label)
        axes[0, column].plot([0, 1], [0, 1], "--", color=GREY, label="Referencia ideal")
        axes[0, column].set(title=f"{LABELS[part]} · n={n}", xlabel="Probabilidad media por bin", ylabel="Fracción positiva experimental", xlim=(0, 1), ylim=(0, 1))
        axes[0, column].legend(fontsize=8)
        axes[1, column].set(xlabel="Probabilidad estimada (bins de 0,1)", ylabel="Celdas con etiqueta conocida", xlim=(0, 1))
    fig.suptitle("Calibración descriptiva de probabilidades sin reajuste", fontsize=15)
    save(fig, "02_calibration", "Tres bloques cronológicos de 2024. Diez bins uniformes fijos; sólo bins ocupados; sin intervalos de independencia.")

    rows = sorted([r for r in data["weekly"] if r["model"] == RF and r["partition"] == "test"], key=lambda r: r["target_week"])
    fig, axes = plt.subplots(1, 2, figsize=(11.5, 5), layout="constrained")
    x = np.arange(4)
    for ax, bottom, top, title, first, second in (
        (axes[0], "tp", "fp", "Predicciones positivas del RF", "Verdaderos positivos", "Falsos positivos"),
        (axes[1], "tn", "fn", "Predicciones negativas del RF", "Verdaderos negativos", "Falsos negativos")):
        ax.bar(x, [r[bottom] for r in rows], color=TEAL, label=first)
        ax.bar(x, [r[top] for r in rows], bottom=[r[bottom] for r in rows], color=ORANGE, hatch="//", label=second)
        for index, row in enumerate(rows):
            ax.text(index, row[bottom] + row[top] + 3, str(row[bottom] + row[top]), ha="center")
        ax.set(title=title, ylabel="Celdas radio–semana con etiqueta conocida", xlabel="Inicio de semana objetivo (2024)", ylim=(0, 210))
        ax.set_xticks(x, [date.fromisoformat(r["target_week"]).strftime("%d/%m") for r in rows])
        ax.legend(fontsize=9)
    save(fig, "03_test_weekly_errors", "12/05–08/06/2024. Umbral congelado 0,5; 861 celdas conocidas; 191 desconocidas excluidas.")

    fig, axes = plt.subplots(1, 3, figsize=(12, 5.5), layout="constrained")
    for ax, feature in zip(axes, ("semana_epidemiologica", "estacionalidad_seno", "estacionalidad_coseno")):
        summaries = [next(r for r in data["distributions"] if r["feature"] == feature and r["partition"] == part
                         and r["population"] == "known_labels_only") for part in PARTS]
        stats = [{"label": label, "med": r["median"], "q1": r["q25"], "q3": r["q75"],
            "whislo": r["minimum"], "whishi": r["maximum"], "fliers": []} for r, label in zip(summaries, ("Entr.", "Val.", "Prueba"))]
        ax.axhspan(summaries[0]["minimum"], summaries[0]["maximum"], color=TEAL, alpha=.12, label="Rango de entrenamiento")
        ax.bxp(stats, showfliers=False)
        ax.set(title=FEATURES[feature], ylabel="Semana de origen" if feature == "semana_epidemiologica" else "Valor adimensional", xlabel="Partición cronológica")
        ax.legend(fontsize=8)
    fig.suptitle("Soporte de las variables estacionales en cada bloque", fontsize=15)
    save(fig, "04_temporal_feature_support", "Distribuciones de celdas con etiqueta conocida, 2024. Caja: Q25–Q75; mediana; bigotes: mínimo–máximo.")

    fig, axes = plt.subplots(1, 3, figsize=(15, 5.7), layout="constrained", gridspec_kw={"width_ratios": [1, 1, 1.4]})
    static = ["superficie_km2", "poblacion", "densidad_poblacional", "cantidad_vecinos"]
    for ax, method in zip(axes[:2], ("pearson", "spearman")):
        matrix = [[next(r["correlation"] for r in data["correlations"] if r["method"] == method
                        and r["feature_one"] == one and r["feature_two"] == two) for two in static] for one in static]
        im = ax.imshow(matrix, cmap="RdBu_r", vmin=-1, vmax=1)
        ax.set_xticks(range(4), [FEATURES[s] for s in static], rotation=45, ha="right")
        ax.set_yticks(range(4), [FEATURES[s] for s in static])
        ax.set(title=method.capitalize(), xlabel="Variable estructural", ylabel="Variable estructural")
        for row in range(4):
            for col in range(4):
                ax.text(col, row, f"{matrix[row][col]:.2f}", ha="center", va="center", color="white" if abs(matrix[row][col]) > .6 else "black", fontsize=9)
    fig.colorbar(im, ax=list(axes[:2]), shrink=.65, label="Correlación descriptiva (sin p-valores)")
    importance = sorted(data["importance"], key=lambda r: r["importance_mdi"])
    axes[2].barh([FEATURES[r["feature"]] for r in importance], [r["importance_mdi"] for r in importance], color=TEAL)
    axes[2].xaxis.set_major_formatter(PercentFormatter(1))
    axes[2].set(title="Importancia MDI guardada", xlabel="Fracción de disminución de impureza", ylabel="Predictor del Modelo A", xlim=(0, .28))
    save(fig, "05_redundancy_and_mdi", "Correlaciones: 263 radios únicos, sin duplicarlos por semana. MDI: sólo ajuste de Fase 5C; no contribución causal.")

    fig, axes = plt.subplots(2, 3, figsize=(13, 8), layout="constrained")
    for col, part in enumerate(PARTS):
        for model, color, label in ((RF, TEAL, "RF A"), (BASELINE, ORANGE, "Baseline")):
            curve = next(r for r in data["curves"] if r["partition"] == part and r["model"] == model)
            axes[0, col].plot(curve["fpr"], curve["tpr"], color=color, label=f"{label}: AUC {curve['roc_auc']:.3f}")
            axes[1, col].step(curve["recall"], curve["precision"], where="post", color=color, label=f"{label}: AP {curve['ap']:.3f}")
        axes[0, col].plot([0, 1], [0, 1], "--", color=GREY)
        axes[0, col].set(title=LABELS[part], xlabel="Tasa de falsos positivos", ylabel="Recall / sensibilidad", xlim=(0, 1), ylim=(0, 1.03))
        axes[1, col].set(xlabel="Recall", ylabel="Precision", xlim=(0, 1), ylim=(0, 1.03))
        axes[0, col].legend(fontsize=8)
        axes[1, col].legend(fontsize=8)
    fig.suptitle("Discriminación y precision–recall por partición", fontsize=15)
    save(fig, "06_ranking_curves", "Bloques de 2024; sin elegir umbrales. AP es la métrica primaria, sin interpolación trapezoidal.")
    (output / "render_runtime.private.json").write_text(json.dumps({"python": platform.python_version(),
        "matplotlib": matplotlib.__version__, "numpy": np.__version__, "backend": matplotlib.get_backend(),
        "figures": files, "training_performed": False}, indent=2), encoding="utf-8")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    render(json.loads(args.input.read_text(encoding="utf-8")), args.output)


if __name__ == "__main__":
    main()
