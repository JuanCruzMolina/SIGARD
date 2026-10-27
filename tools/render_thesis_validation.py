"""Export aggregate-only figures and tables from a private frozen-error synthesis.

Optional Matplotlib renderer; never loads trained models or epidemiological rows.
The input summary is intentionally not part of Git. Run from repository root.
"""
import argparse
import json
from pathlib import Path


def comparison(horizon, period, baseline, method=None):
    return next(row for row in horizon["periods"][period]["comparisons"]
                if row["method"] == (method or horizon["best_ml"]) and row["baseline"] == baseline)


def save_svg(figure, path):
    figure.savefig(path, metadata={"Date": None})
    # Matplotlib emits trailing spaces inside path attributes; newlines retain
    # their XML whitespace meaning while keeping generated files Git-clean.
    path.write_text("\n".join(line.rstrip() for line in path.read_text(encoding="utf-8").splitlines()) + "\n",
                    encoding="utf-8")


def figures(summary, output, preview):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from matplotlib.ticker import MaxNLocator
    matplotlib.rcParams.update({"font.size": 10, "svg.fonttype": "none", "axes.spines.top": False,
                               "axes.spines.right": False, "svg.hashsalt": "sigard-thesis-validation"})
    output.mkdir(parents=True, exist_ok=True)
    preview.mkdir(parents=True, exist_ok=True)
    fig, axes = plt.subplots(2, 3, figsize=(12, 7), layout="constrained")
    baselines = ["lag_1_or_training_mean", "latest_closed_or_training_mean"]
    colors = ["#246580", "#9a5834"]
    for col, (h, horizon) in enumerate(summary["horizons"].items()):
        for row_index, period in enumerate(("internal_oof", "previously_observed")):
            ax = axes[row_index, col]
            for y, (baseline, color) in enumerate(zip(baselines, colors)):
                row = comparison(horizon, period, baseline)
                low, high = next(b for b in row["bootstrap"] if b["block_weeks"] == 3)["intervals"]["mae"]
                ax.hlines(y, low, high, color=color, linewidth=2)
                ax.plot(row["delta_mae"], y, "o" if y == 0 else "s", color=color, markersize=6)
            ax.axvline(0, color="0.4", linestyle="--", linewidth=1)
            ax.set_yticks([0, 1], ["Persistencia t−1", "Último cierre t"])
            ax.set_ylim(-.6, 1.6)
            ax.set_xlabel("ΔMAE ML − persistencia\n(registros por radio-semana)")
            label = "OOF interno" if row_index == 0 else "Comparación 2024"
            ax.set_title(f"t+{h} · {label}\n{horizon['periods'][period]['weeks']} semanas")
            ax.grid(axis="x", alpha=.2)
            ax.xaxis.set_major_locator(MaxNLocator(nbins=3))
    fig.suptitle("Diferencias de error de candidatos designados en desarrollo", fontsize=12)
    fig.get_layout_engine().set(rect=(0, .06, 1, .86))
    fig.text(.5, .015, "IC95 descriptivo: 10 000 remuestreos pareados, bloques de hasta 3 semanas; sin confirmación externa.\n"
             "Fuente: predicciones V3 congeladas · OOF 2021–febrero 2024; comparación marzo–junio 2024.", ha="center", fontsize=9)
    save_svg(fig, output / "validacion-predictiva-intervalos.svg")
    fig.savefig(preview / "intervalos.png", dpi=130)
    plt.close(fig)

    fig, axes = plt.subplots(1, 3, figsize=(12, 5.2), layout="constrained")
    for ax, (h, horizon) in zip(axes, summary["horizons"].items()):
        for baseline, color, marker in zip(baselines, colors, ("o", "s")):
            row = comparison(horizon, "internal_oof", baseline)
            years = list(row["by_year"])
            differences = [v["ml"]["mae"] - v["persistence"]["mae"] for v in row["by_year"].values()]
            ax.plot(years, differences, color=color, marker=marker,
                    label="Persistencia t−1" if baseline == baselines[0] else "Último cierre t")
        ax.axhline(0, color="0.4", linestyle="--", linewidth=1)
        ax.set_title(f"t+{h} · {horizon['periods']['internal_oof']['weeks']} semanas OOF")
        ax.set_xlabel("Año del objetivo (semanas disponibles)")
        ax.set_ylabel("ΔMAE ML − persistencia\n(registros por radio-semana)")
        ax.grid(axis="y", alpha=.2)
    axes[0].legend(frameon=False, fontsize=9)
    fig.suptitle("Estabilidad por período de candidatos designados en desarrollo", fontsize=12)
    fig.get_layout_engine().set(rect=(0, .15, 1, .82))
    fig.text(.5, .025, "Valores bajo cero favorecen ML. Años con pocos registros y soporte desigual; las líneas sólo conectan resúmenes.\n"
             "Fuente: predicciones OOF V3 congeladas · 2021, 2023 y enero–febrero 2024; 2022 excluido.", ha="center", fontsize=9)
    save_svg(fig, output / "validacion-predictiva-estabilidad.svg")
    fig.savefig(preview / "estabilidad.png", dpi=130)
    plt.close(fig)


def tables(summary):
    names = dict(v3_direct_poisson="Poisson", v3_hurdle="Presencia/cantidad", v3_residual_boosting="Corrección")
    text = ["| Horizonte / período | n / semanas | Método | MAE | RMSE | Sesgo |", "|---|---:|---|---:|---:|---:|"]
    for h, horizon in summary["horizons"].items():
        for period, content in horizon["periods"].items():
            tag = "OOF" if period == "internal_oof" else "2024 observada"
            for method in (horizon["best_ml"], "lag_1_or_training_mean", "latest_closed_or_training_mean"):
                value = content["all_methods"][method]
                name = names.get(method, "Persistencia t−1" if method.startswith("lag") else "Último cierre t")
                text.append(f"| t+{h} / {tag} | {content['n']} / {content['weeks']} | {name} | {value['mae']:.5f} | {value['rmse']:.5f} | {value['mean_bias']:+.5f} |")
    text += ["", "| Horizonte / período | Candidato | ΔMAE | ΔRMSE | IC95 ΔMAE (bloques 3) | Gana ML / pers. |", "|---|---|---:|---:|---|---:|"]
    for h, horizon in summary["horizons"].items():
        for period, content in horizon["periods"].items():
            for row in content["comparisons"]:
                if row["baseline"] != "lag_1_or_training_mean":
                    continue
                low, high = next(b for b in row["bootstrap"] if b["block_weeks"] == 3)["intervals"]["mae"]
                text.append(f"| t+{h} / {'OOF' if period == 'internal_oof' else '2024 observada'} | {names[row['method']]} | {row['delta_mae']:+.5f} | {row['delta_rmse']:+.5f} | [{low:+.5f}; {high:+.5f}] | {row['wins_ml']} / {row['wins_persistence']} |")
    return "\n".join(text) + "\n"


def private_output(path, root):
    target = path.resolve()
    allowed = (root / "data/interim/official").resolve()
    if not target.is_relative_to(allowed):
        raise ValueError("Generated scientific reports must stay in private local storage")
    if target.exists():
        raise ValueError("Do not overwrite an existing private report")
    return target


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--summary", type=Path, required=True)
    base = Path("data/interim/official/thesis_figures")
    parser.add_argument("--output", type=Path, default=base / "svg")
    parser.add_argument("--preview", type=Path, default=base / "preview")
    parser.add_argument("--tables", type=Path, default=base / "tables.private.md")
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[1]
    args.output = private_output(args.output, root)
    args.preview = private_output(args.preview, root)
    args.tables = private_output(args.tables, root)
    summary = json.loads(args.summary.read_text(encoding="utf-8"))
    figures(summary, args.output, args.preview)
    args.tables.parent.mkdir(parents=True, exist_ok=True)
    args.tables.write_text(tables(summary), encoding="utf-8")
    print("Two aggregate SVG figures and reproducible tables exported; no individual observations.")


if __name__ == "__main__":
    main()
