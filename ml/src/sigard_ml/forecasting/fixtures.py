"""Generador determinista ajeno a pacientes, cartografía y resultados SIGARD."""

from datetime import date, timedelta

import numpy as np
import pandas as pd

from sigard_ml.forecasting.contracts import Inputs


def fictional_inputs(seed=20261021, weeks=48):
    rng = np.random.default_rng(seed)
    radios = ("fictional_north", "fictional_south", "fictional_west")
    first = date(2023, 12, 31)
    counts, climate, territory = [], [], []
    for index, radio in enumerate(radios):
        territory.append(dict(radio_id=radio, available_on=first, population=500 + 200 * index,
                              area_km2=1.0 + index, source_ref="fictional_census_v1"))
    for index in range(weeks):
        source_week = first + timedelta(weeks=index)
        available_on = source_week + timedelta(days=7)
        temperature = 22 + 6 * np.sin(index / 8)
        for offset, radio in enumerate(radios):
            value = int(rng.poisson(max(0.05, (offset + 1) * (0.5 + 0.4 * np.sin(index / 7)))))
            counts.append(dict(radio_id=radio, week_start=source_week, available_on=available_on,
                               count=value, state="complete", coverage_complete=True, pending=False,
                               mature=True, source_ref="fictional_surveillance_v1"))
        climate.append(dict(week_start=source_week, available_on=available_on, temperature=temperature,
                            humidity=float(rng.uniform(30, 80)), precipitation=float(rng.uniform(0, 20)),
                            complete=True, source_ref="fictional_weather_v1"))
    return Inputs(radios, pd.DataFrame(counts), pd.DataFrame(climate), pd.DataFrame(territory),
                  ((radios[0], radios[1]), (radios[1], radios[0]), (radios[1], radios[2]), (radios[2], radios[1])),
                  first, "fictional_graph_v1", "fictional_counts_v1")
