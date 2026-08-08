# Pipelines reproducibles de SIGARD

Esta etapa construye el maestro territorial de Capital, La Rioja, sin modificar
las fuentes locales. Requiere Python 3.11 o posterior.

## Instalación

Desde `ml/`, crear un entorno virtual e instalar las dependencias mínimas:

```powershell
python -m venv venv
venv\Scripts\python -m pip install --upgrade pip
venv\Scripts\python -m pip install -r requirements.txt
```

GeoPandas instala transitivamente Shapely, PyProj y el motor de lectura
geoespacial. PyArrow se declara de forma directa porque es necesario para la
salida Parquet; pytest sólo se usa para las pruebas.

## Ejecución

Desde la raíz del repositorio:

```powershell
ml\venv\Scripts\python -m sigard_ml.ingestion.territorial `
  --config ml/configs/territorial_master.json
```

Salidas locales, excluidas de Git:

- `data/processed/territorial_master.parquet`
- `data/processed/territorial_master.geojson`
- `data/processed/territorial_quality_report.json`

Para ejecutar las pruebas:

```powershell
ml\venv\Scripts\python -m pytest ml/tests
```

## Etapa temporal: dengue y clima semanal

Desde la raíz del repositorio, la segunda etapa se ejecuta con:

```powershell
ml\venv\Scripts\python -m sigard_ml.ingestion.temporal `
  --config ml/configs/temporal_weekly.json
```

La configuración declara rutas, codificaciones, delimitadores, nombres reales
de columnas y el calendario epidemiológico argentino usado por el Ministerio de
Salud (domingo a sábado). No se lo trata como equivalente a ISO-8601. Produce:

- `data/processed/dengue_weekly.parquet`
- `data/processed/climate_weekly.parquet`
- `data/processed/department_weekly.parquet`
- `data/processed/modeling_weekly.parquet`
- `data/processed/temporal_quality_report.json`

Las ausencias no se imputan. `dengue_record_available` distingue una semana sin
registro de una semana con cero observado (`dengue_zero_cases_observed`), y
`climate_data_available`/`climate_week_complete` documentan disponibilidad y
cobertura climática. El JSON conserva procedencia, versión, unidad temporal,
condición observada y controles de calidad.

`epidemiological_status` clasifica cada semana como `observed`,
`explicit_zero`, `missing_record` u `outside_source_coverage`. La salida de
modelado conserva solamente semanas `observed` o `explicit_zero` con siete días
climáticos; nunca convierte una ausencia epidemiológica en cero.

La correspondencia de fechas se valida contra los calendarios y boletines del
[Ministerio de Salud](https://www.argentina.gob.ar/salud/epidemiologia/herramientas):
en 2024 la SE1 abarcó 2023-12-31 a 2024-01-06 y la SE52, 2024-12-22 a
2024-12-28, según el [índice oficial de boletines 2024](https://www.argentina.gob.ar/salud/boletin-epidemiologico-nacional/boletines-2024).

## Etapa 3: asignación espacial sintética

Desde la raíz del repositorio:

```powershell
ml\venv\Scripts\python -m sigard_ml.simulation.pipeline `
  --config ml/configs/synthetic_allocation.json
```

Distribuye cada total semanal real y agregado de Capital entre los 263 radios
mediante dos escenarios separados: multinomial proporcional a `poblacion`, y
clusters reproducibles basados en población y `neighbor_ids`. La configuración
registra semilla, versión, variables y parámetros. No usa clima ni genera
coordenadas puntuales. Los resultados son asignaciones sintéticas, no
observaciones ni ubicaciones reales de casos.

Produce, sin sobrescribirlos por defecto:

- `data/processed/synthetic_radio_week_population.parquet`
- `data/processed/synthetic_radio_week_clusters.parquet`
- `data/processed/synthetic_allocation_quality_report.json`

## Etapa 4: panel radio-semana para modelado

Sin entrenar modelos ni dividir datos, se ejecuta desde la raíz con:

```powershell
ml\venv\Scripts\python -m sigard_ml.features.pipeline `
  --config ml/configs/modeling_panel.json
```

Produce `radio_week_panel.parquet` con las 263 filas de cada semana disponible,
`modeling_panel.parquet` sólo con filas que poseen tres semanas consecutivas de
historia y target consecutivo, y `modeling_panel_quality_report.json`. Los lags
se buscan por fecha exacta, sin imputación; la media vecinal usa exclusivamente
`neighbor_ids` y casos de semanas anteriores. El target sigue siendo una
asignación sintética espacial en `t+1`, no evidencia epidemiológica por radio.

Las salidas no se sobrescriben salvo que se indique deliberadamente
`--overwrite`, que sólo alcanza los tres productos configurados de esta etapa.

El reporte controla conservación semanal exacta, 263 radios por semana,
duplicados, nulos, negativos, ceros, concentración y radios con mayor
asignación. Reemplazar deliberadamente esas rutas requiere `--overwrite`.
