"""Demostración sin archivos de entrada/salida ni modelos persistidos."""

import argparse
from datetime import date
import json

from sigard_ml.forecasting.fixtures import fictional_inputs
from sigard_ml.forecasting.prediction import forecast_next_week
from sigard_ml.forecasting.training import run_experiment


def main():
    parser = argparse.ArgumentParser(description="SIGARD conteos t+1: sólo simulación ficticia en memoria")
    parser.add_argument("--fictional-demo", action="store_true", required=True)
    parser.parse_args()
    inputs = fictional_inputs()
    result = run_experiment(inputs, start=date(2024, 1, 28), end=date(2024, 11, 3),
                            validation_start=date(2024, 5, 19), test_start=date(2024, 8, 11),
                            evaluation_as_of=date(2024, 11, 24))
    forecast = forecast_next_week(result.fitted, inputs, as_of=date(2024, 11, 17))
    # Sólo resumen ficticio, sin exportar matrices, modelos o filas de entrenamiento.
    print(json.dumps({"data_kind": "fictional", "scientific_performance": False,
                      "real_training_enabled": False, "model_id": result.fitted.model_id,
                      "selected": result.report["selected"], "rows": result.report["rows"],
                      "test": {name: {key: values[key] for key in ("territorial", "capital", "macro_radio_mae")}
                               for name, values in result.report["test"].items()},
                      "forecast": {key: forecast[key] for key in ("status", "target_week", "expected_capital_count", "uncertainty")}},
                     ensure_ascii=False, allow_nan=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
