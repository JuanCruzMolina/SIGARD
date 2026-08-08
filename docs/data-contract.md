# Contrato conceptual de datos de SIGARD v0.1

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

Los archivos de estas zonas no se versionan. Tampoco se versionan modelos
entrenados, secretos, credenciales ni archivos `.env`.
