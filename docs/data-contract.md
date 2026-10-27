# Contrato conceptual de datos de SIGARD v0.1

## Contrato del módulo principal de conteos

V2 agrega `snapshot_record_count` como unidad experimental privada separada:
ceros del snapshot filtrado sólo bajo su hipótesis explícita, desconocidos ante
pendientes/fechas no utilizables o fuera de alcance y 2022 aparte. Produce conteos
territoriales y puntaje de presencia experimental por horizonte directo t+1/t+2/t+4.
Las observaciones y predicciones se distinguen; el total observado de 256 radios
es null cuando alguna etiqueta es desconocida. La consulta local no habilita
producción, publicación ni probabilidades de infección. Ver
[extensión de entrada V2](principal-count-input-contract.md#extensión-v2-snapshot-filtrado-y-consulta-privada).

El [módulo principal t+1](principal-count-forecasting.md) agrega un contrato
interno independiente `principal-counts-0.1.0`:
snapshots radio–semana con conteo nullable, estado, cobertura, pendientes,
madurez, disponibilidad y procedencia. Un positivo parcial no acredita un
conteo completo; desconocidos nunca se imputan como cero. Predictores usan
versiones conocidas al cierre del origen y desenlaces congelados separados.
La salida conserva esperanza por radio, suma coherente de Capital, corte,
objetivo y modelo; probabilidades e intervalos permanecen null sin acreditación.
No cambia los contratos públicos, el MVP sintético, A/B ni sus etiquetas.

Desde el 26/10/2026, `provisional_aggregate_experiment` permite ajuste y evaluación
experimental local sobre agregados reales autorizados por la declaración expresa
del responsable de SIGARD. Conserva `provisional_record_count`, desenlaces
desconocidos null, disponibilidad histórica no acreditada y P1–P6 como límites.
Su evaluación es retrospectiva y condicional a celdas positivas observadas;
no estima aparición territorial, episodios independientes, ceros acreditados ni
totales completos de Capital. `training_authorized`/`evaluation_authorized`
se calculan desde permisos y evidencia de esa modalidad; no activan producción.
Modelo y resultados V1 se almacenan sólo en la versión privada
`ml/artifacts/official/sigard-principal-v1-experimental/`. Ver
[contrato de entrada experimental](principal-count-input-contract.md#modalidad-provisional_aggregate_experiment).

El contexto operativo del principal adopta desde el 23/10/2026 la versión
`la-rioja-46014010-256-v1`: 256 radios completos (245 interiores y 11 con
superficie interior ≥ 99,99% en localidad `46014010`), con grafo inducido cerrado.
Se preservan geometrías, población, superficie y densidad por unidad; no hay
reparto por fracción de área ni reasignación de pacientes. La preparación está
configurada en `ml/configs/principal_territory.json` y conectada al adaptador
mediante `territorial_components`, sin entrenamiento ni conteos reales nuevos.
Ver [adopción y límites](principal-city-boundary.md#adopción-operativa-del-23102026).
El maestro original, contratos públicos y artefactos A/B conservan 263 radios.

## Contratos internos del circuito oficial

La fase 1 agrega objetos validados en `sigard_ml.official` para procedencia,
registros privados, semanas, coordenadas, asignaciones, calidad, panel observado,
entrenamiento y predicciones. Distingue observaciones oficiales y fixtures;
excluye asignaciones sintéticas. Son interfaces internas: no alteran el contrato
público, no habilitan lectura de Excel y no autorizan entrenar ni divulgar.
Ver [campos, semántica y límites de implementación](official-pipeline.md).

La [fase 2](official-ingestion.md) agrega una proyección privada de filas bajo
unidad `unresolved_source_record`, con fechas y coordenadas candidatas, calidad,
hashes y trazabilidad. No equivale a episodios elegibles ni al panel observado
radio-semana. El objetivo futuro solicitado es probabilidad de aparición de
casos; no se genera aún su etiqueta ni se modifica el objetivo del MVP sintético.

La [fase 3](official-geography.md) agrega un diagnóstico privado por registro.
La clave es `source_id + sheet_ref + record_ref`. Se conservan por separado
`coordinate_status`, `geocoding_category`, `geometry_status`, `assignment_state`
y `eligibility`; ésta permanece sin resolver si no existía una decisión previa.
`radio_candidate` sólo existe en un interior único, incluyendo los resultados
inciertos. Bordes y múltiples coincidencias quedan sin candidato elegido.
Los grupos de coordenadas y radios alternativos son controles de diagnóstico,
no episodios deduplicados ni probabilidades de ubicación. No se generan casos
por radio, semanas, etiquetas ni panel observado. Este contrato de filas no
reemplaza el contrato de episodios resueltos de Fase 1 ni los productos del MVP.

La [fase 4](official-observed-panel.md) construye una grilla privada con
`radio_censal`, `fraccion_censal`, `anio_epidemiologico`, `semana_epidemiologica`,
límites de semana, `registros_elegibles_provisionales` nullable y
`estado_observacion`. Distingue registros observados, cero respaldado, información
insuficiente, cobertura parcial y fuera de cobertura. Conserva versiones, calidad
espacial, procedencia y pendientes; no equivale a casos únicos validados.
Las claves técnicas de filas y episodios quedan exclusivamente en auditoría
privada. `validado` y `apto_entrenamiento` son falsos; disponibilidad histórica
no reconstruida implica modo retrospectivo. No se crean etiquetas negativas ni
se usan null como cero. El contrato provisional no reemplaza `ObservedRadioWeek`
como observación epidemiológica validada ni los contratos públicos actuales.

La [fase 4.1](official-date-recovery.md) agrega una jerarquía temporal opcional:
inicio de síntomas, consulta médica, toma de muestra y notificación. La auditoría
privada conserva `fecha_inicio_sintomas_original`, `fecha_referencia`,
`tipo_fecha_referencia`, `fecha_aproximada` y `motivo_seleccion_fecha`, además de
rechazos y procedencia por columna. Las alternativas no confirman el inicio de
síntomas. Los escenarios estricto/ampliado tienen carpetas versionadas privadas;
conservan el panel previo, identidad, elegibilidad, incertidumbre espacial y null.

La [fase 4.2](official-coverage.md) deriva `casos_observados` nullable,
`estado_cobertura`, `objetivo_semana_siguiente` (0/1/null), `objetivo_valido`,
`escenario` y `calidad_geografica` sobre la misma unidad radio-semana. Los
conteos son registros elegibles provisionales, no casos únicos validados.
Separa cobertura declarada/comprobada; los ceros declarados del escenario
exploratorio son provisionales. La etiqueta usa exclusivamente la semana exacta
siguiente y no se incorpora como predictor. Una etiqueta conocida no valida
disponibilidad histórica ni habilita entrenamiento. No altera el objetivo del MVP.

La [Fase 5A](official-spatial-ml.md) prepara tablas privadas separadas de
predictores retrospectivos, calendario, etiquetas y contexto de auditoría, por
fechas estrictas/ampliadas y cobertura conservadora/exploratoria. Conserva
objetivos `1/0/null` heredados; no genera negativos. Los rezagos usan fechas
exactas y los acumulados `[t-W,t-1]` requieren ventanas completas conocidas,
también para todos los vecinos verificados con polígonos. Población/densidad
Censo 2022 son contexto retrospectivo sin disponibilidad histórica acreditada.
Ninguna variable utiliza t+1, pero las historias no están validadas para operación
sin reconstruir disponibilidad de registros/clasificaciones. Catálogo explícito,
hashes y particiones cronológicas purgadas quedan privados; entrenamiento bloqueado.

La [Fase 5B](official-spatial-experiment.md) audita las 55 columnas sin alterar
Fase 5A y prepara conjuntos A/B/C, protocolo de RF y previsualización de
cobertura explícitamente declarada. Separa disponibilidad retrospectiva e
histórica operativa; no imputa ni convierte null en cero. La historia es
opcional y su soporte se revisa sólo en entrenamiento. No se materializan
negativos, reclasifican registros ni entrenan modelos. Los diagnósticos,
configuraciones y máscaras permanecen privados y no habilitan entrenamiento.

La [Fase 5B.1](official-epidemiology-review.md) agrega evidencia y plantillas de
decisión privadas, sin modificar la unidad, features, etiquetas o configuración
del Modelo A. Distingue banderas conservadoras del software de confirmación
clínica documentada; propone intervalos sin declararlos completos y conserva
todos los bloqueos de pendientes. La geografía aproximada ya aceptada permanece
como limitación, sin exigir precisión absoluta. La generación del diagnóstico
no depende de documentación externa que aún no esté disponible.

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

La publicación persistente reutiliza `backend/app/publication_import.py` con
estos seis contratos y exactamente 263 radios. Las geometrías deben representar
longitud/latitud WGS84 (SRID 4326), sin reproyección implícita; se validan estructura,
campos, números finitos, rangos existentes y alineación antes de persistir, y
topología con PostGIS antes de publicar. Los metadatos/evaluación son objetos
JSON de esquema abierto; el contrato no impone nuevas claves de procedencia.
La [verificación ficticia aislada](../backend/README.md#verificación-ficticia-del-importador-territorial--sin-docker)
documenta el hash/versionado, los límites geométricos y las garantías verificadas
sin confundir este importador con la ingestión epidemiológica oficial.

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

El circuito oficial usa `ar-snvs-2020-2026-v1`: 53 semanas en 2020 y 2025,
52 en 2021–2024 y 2026. El 04/01/2026 es 2026-SE1. La
[validación del calendario](official-calendar.md) documenta la contradicción
publicada al cerrar 2025 y la reproducción explícita `sigard-iso-shift-v0`.
Conservar fecha de inicio y versión al interpretar una clave año-SE; validar
el calendario hasta 2026 no amplía la cobertura vigente hasta 31/12/2024.

La [Fase 4.3](official-universe.md) revisa el universo para el objetivo binario
experimental de registrar al menos un confirmado provisional en el radio la
semana siguiente. Sus agregados y capacidades negativas condicionadas no son
un panel nuevo ni sustituyen objetivos/modelos existentes. Distingue positivos
provisionales, ceros comprobados, ceros asumidos experimentales y desconocidos;
no materializa ceros sin declaración explícita y autorización posterior.

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

## Contrato del módulo de prevención y ayuda

### Directorio público de establecimientos

`frontend/public/data/health_facilities.geojson` contiene una
`FeatureCollection` EPSG:4326 con 24 CAPS públicos y 3 hospitales de referencia.
Cada `Point` posee `id`, `name`, `type`, `address`, `neighborhood`, teléfono y
horario publicados cuando existen, servicios, fuente, fecha de fuente, fecha de
revisión, estado de verificación y precisión cartográfica. `vigencia_por_confirmar`
impide interpretar la ficha como disponibilidad en tiempo real.

En la revisión `2026-08-19`, 23 de los 24 CAPS conservan
`vigencia_por_confirmar`; el restante está rotulado `publicado`. Ninguno de esos
estados constituye verificación operativa en vivo. Los 3 hospitales se mantienen
en una categoría separada.

`frontend/public/data/prevention_content.json` contiene acciones preventivas,
síntomas, signos de alarma, conducta recomendada, explicación de control
vectorial, teléfonos publicados y sus fuentes. Ambos artefactos usan
`schema_version: 1.0.0` y fueron revisados el `2026-08-19`.

### Reporte ciudadano anónimo

`citizen_reports` es una entidad operativa privada y separada. No representa un
caso, una observación, una asignación sintética ni una predicción. Sus campos
públicos se limitan a:

```text
tracking_code, status, created_at, updated_at, public_status_message
```

La creación acepta categoría, descripción, coordenada, referencia y barrio
opcionales, versión/aceptación del aviso. No acepta identificadores de contacto
y valida el rectángulo operativo de Ciudad de La Rioja. El encabezado
`Idempotency-Key` se transforma con HMAC y evita duplicados por reintento; la IP
no se persiste. Un segundo reporte de igual categoría, dentro de 150 metros y
durante los siete días anteriores, se marca como posible duplicado sin impedir
su alta. Ubicación, descripción, notas y duplicados sólo aparecen en
endpoints administrativos con JWT y rol `admin`.

La búsqueda opcional de dirección usa `POST /api/v1/geocoding/address` después
de un consentimiento específico. La API valida que el texto no contenga correo,
teléfono o DNI y consulta Nominatim desde el servidor. El proveedor recibe la
referencia y la IP del servidor, no la del ciudadano. El mapa administrativo
usa exclusivamente la cartografía censal local de SIGARD y no solicita teselas
externas con la coordenada privada.

El plazo inicial de retención es de 180 días. `python -m app.retention` elimina
reportes vencidos y debe ejecutarse como tarea externa al proceso web. Su
servicio está definido en `compose.yaml` como un trabajo temporal y se detalla
en `docker-development.md`. Esta política aplica únicamente a reportes
ciudadanos y no elimina observaciones epidemiológicas, asignaciones sintéticas
ni predicciones.
