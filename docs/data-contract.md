# Contrato conceptual de datos de SIGARD v0.1

## Contrato frontend de Iteración 10

- `temporal_predictions.json`: predicciones departamentales publicables sólo
  para semanas alineadas con la simulación espacial.
- `available_weeks.json`: única fuente futura del selector temporal.
- `territorial_context.geojson`: contexto territorial real, estable y no
  epidemiológico.
- `experimental_spatial_history.geojson`: simulación sintética dinámica.
- `model_evaluation.json`: métricas y seis semanas completas del holdout.
- `mvp_metadata.json`: identidad metodológica y advertencias del MVP.

La alineación exige coincidencia exacta de cutoff, inicio y fin de semana, y 263
radios experimentales. Los artefactos legacy actuales se preservan hasta que
React migre al nuevo contrato.

## Productos territoriales de Iteración 9

`territorial_context` contiene una fila por radio y geometría censal real. Su
score combina en partes iguales el promedio de ranks de población, hogares y
viviendas, y el rank de densidad. Superficie queda como atributo descriptivo y
no participa del score. No contiene casos ni predicciones epidemiológicas.

`experimental_spatial_history` contiene una fila por radio y semana objetivo.
Su score reutiliza una predicción del escenario sintético `spatial_clusters`,
con percentil recalculado dentro de cada semana. Su condición es experimental y
sintética; nunca debe denominarse observación o caso real predicho por radio.

Los dos productos son independientes y sus scores no se suman. El Random Forest
temporal departamental responde cuántos casos se esperan en Capital, mientras
las capas territoriales sólo expresan posiciones relativas entre radios.

## Unidad analítica

La fila principal del dataset de modelado representa un único **radio censal en
una semana epidemiológica**. Su clave lógica es:

```text
(radio_id, anio_epidemiologico, semana_epidemiologica)
```

`radio_id` debe ser el identificador oficial estable de la cartografía. La
semana debe validarse según el calendario epidemiológico usado por la fuente;
no se asumirá que cada año contiene exactamente 52 semanas.

## Entidades conceptuales

### Radio censal

| Campo conceptual | Descripción |
| --- | --- |
| `radio_id` | Código oficial y estable del radio censal |
| `geometry` | Geometría oficial del radio y su CRS declarado |
| `poblacion` | Población censal del radio |
| `hogares` | Hogares censales del radio |
| `viviendas` | Viviendas censales del radio |
| `fuente_version` | Identificación de la fuente y edición cartográfica/censal |

### Observación agregada de Capital

| Campo conceptual | Descripción |
| --- | --- |
| `anio_epidemiologico` | Año informado por la fuente epidemiológica |
| `semana_epidemiologica` | Semana epidemiológica informada |
| `casos_observados_capital` | Total real agregado para Capital |
| `fuente_version` | Fuente, fecha de descarga o versión |

Esta entidad no contiene radio ni coordenadas individuales.

### Clima histórico

El clima conserva fecha, variables meteorológicas, unidad, ubicación o área de
representación y fuente. Su agregación semanal debe documentar ventanas y
funciones utilizadas. Sólo puede asociarse a una predicción si habría estado
disponible al momento de emitirla.

### Asignación sintética por radio

| Campo conceptual | Descripción |
| --- | --- |
| `radio_id` | Radio receptor de la asignación |
| `anio_epidemiologico` | Año del total observado de origen |
| `semana_epidemiologica` | Semana del total observado de origen |
| `casos_asignados_sinteticos` | Conteo entero asignado al radio |
| `metodo_asignacion_version` | Identificador del algoritmo y parámetros |
| `semilla` | Semilla determinista usada |
| `es_sintetico` | Siempre `true` |

La implementación de la etapa 3 usa los nombres físicos
`epidemiological_year`, `epidemiological_week`, `week_start_date`,
`week_end_date`, `radio_id`, `department_cases_observed`,
`synthetic_cases_assigned`, `synthetic_allocation_weight`,
`simulation_scenario`, `simulation_version` y `simulation_seed`. El total
departamental conserva su naturaleza observada; el conteo por radio es siempre
una asignación sintética y no una observación espacial.

Para cada año-semana debe cumplirse:

```text
sum(casos_asignados_sinteticos por radio) = casos_observados_capital
```

Los conteos deben ser enteros no negativos y todos los radios deben pertenecer
al universo cartográfico definido para Capital.

### Punto sintético de visualización

| Campo conceptual | Descripción |
| --- | --- |
| `punto_sintetico_id` | Identificador técnico, no identificador de persona |
| `radio_id` | Radio dentro del cual fue generado |
| `anio_epidemiologico` | Año de la asignación de origen |
| `semana_epidemiologica` | Semana de la asignación de origen |
| `geometry` | Coordenada generada dentro del radio |
| `semilla` | Semilla o derivación reproducible |
| `es_sintetico` | Siempre `true` |

La cantidad de puntos por radio-semana debe coincidir con
`casos_asignados_sinteticos`. Estos puntos sirven sólo para visualización y no
pueden usarse como features, labels observados ni evidencia de domicilios.

### Predicción del modelo

| Campo conceptual | Descripción |
| --- | --- |
| `radio_id` | Radio para el cual se predice |
| `anio_objetivo` | Año de la semana predicha |
| `semana_objetivo` | Semana epidemiológica siguiente |
| `casos_predichos` | Cantidad estimada por el modelo |
| `fecha_emision` | Momento lógico de generación |
| `modelo_version` | Versión del modelo y configuración |
| `datos_version` | Versión del panel usado para entrenar |
| `es_prediccion` | Siempre `true` |

`casos_predichos` nunca debe sobrescribir observaciones ni asignaciones
sintéticas.

## Dataset de modelado

### Dataset temporal departamental v0.2

`department_temporal_modeling.parquet` tiene unidad **departamento Capital -
semana epidemiológica**. Cada fila usa `cutoff_week`, features disponibles hasta
ese corte y el total oficial `target_cases_next_week` de la semana exactamente
siguiente. Excluye `missing_record`, `outside_source_coverage`, identificadores y
targets espaciales, geometrías y asignaciones sintéticas. Los lags y rolling no
atraviesan discontinuidades. Esta predicción temporal agregada no valida ninguna
distribución territorial.

La variable objetivo para una fila del radio en la semana `t` es
`casos_asignados_sinteticos` del mismo radio en `t + 1`. Las features sólo
pueden contener información conocida hasta `t`, por ejemplo atributos censales
estáticos, clima disponible y rezagos de asignaciones sintéticas.

Cada dataset derivado debe registrar como mínimo:

- fuente y versión de sus entradas;
- fecha o período de cobertura;
- versión de transformación;
- semilla cuando corresponda;
- condición observada, sintética o predicha;
- reglas de calidad aplicadas.

La etapa 4 materializa los nombres físicos `radio_week_panel.parquet` (todas
las semanas disponibles) y `modeling_panel.parquet` (sólo historia mínima y
target consecutivo disponibles). Los rezagos se resuelven por diferencias
exactas de siete días y no por posición de fila. `neighbor_cases_lag_1` y
`neighbor_cases_lag_2` son la media de asignaciones pasadas de los radios
declarados en `neighbor_ids`; no incorporan casos contemporáneos ni futuros.

## Zonas de almacenamiento

- `data/raw/`: copias originales e inmutables de las fuentes.
- `data/interim/`: salidas parciales y reemplazables de transformación.
- `data/processed/`: datasets validados y listos para consumo.

## Artefactos estáticos de presentación del MVP

La etapa 7 publica una FeatureCollection por semana con exactamente 263 radios
en EPSG:4326. `mvp_prediction.geojson` contiene geometría censal real y las
propiedades `radio_id`, `population`, `population_density`,
`prediction_week_start`, `prediction_week_end`, `predicted_cases`,
`predicted_cases_rounded`, `risk_level`, `simulation_scenario`, `model_name`,
`model_version` y `data_scope`. `predicted_cases` es una salida continua del
modelo; su versión redondeada se usa sólo para presentación.

`risk_level` (`very_low`, `low`, `medium`, `high`) se calcula con los cuantiles
25, 50 y 75 de la predicción dentro de cada semana. Es una clasificación visual
relativa y no un umbral sanitario oficial.

`mvp_prediction_summary.json` documenta semana, corte, modelo, variante, total,
top de radios, métricas, configuración y advertencia. `mvp_backtest.json`
contiene exclusivamente las cuatro semanas del test temporal, compara la suma
predicha por radio con el total oficial departamental conservado por el target
y no declara validación espacial. `mvp_backtest_predictions.geojson` reúne las
cuatro capas históricas opcionales. Los tres artefactos principales se copian a
`frontend/public/data/`; no contienen fuentes raw, secretos ni datos personales.

Los archivos de estas zonas no se versionan. Tampoco se versionan modelos
entrenados, secretos, credenciales ni archivos `.env`.
