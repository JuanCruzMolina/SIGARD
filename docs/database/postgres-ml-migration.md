# Migración operativa de ML a PostgreSQL/PostGIS

La entrega posterior [Option B](option-b-research.md) completa los ajustes nuevos
y el registro privado de A/B/V3 sin exigir sus etiquetas antiguas. Los bloqueos
de equivalencia descritos aquí corresponden a reproducción histórica y no se
suprimen ni se trasladan al contrato experimental nuevo.

La migración usa la base privada existente `sigard_epi_local_v1`, sin reconstruirla,
reimportar Excel ni modificar modelos congelados. El núcleo consolidado conserva
su registro como único candidato del producto. Los adaptadores A/B/V3 son rutas
offline de investigación, bloqueadas para los datasets cuya equivalencia no está
verificada. No se crean otros sistemas activos ni se promueve `candidate_failed`.

## Dependencias identificadas

- A: `official/spatial_ml/research_training.py` leía etiquetas, siete predictores,
  particiones y contexto de los Parquet del escenario 2024. La inferencia de
  `date_inference.py` proyectaba contexto estático desde `predictors_A.private.parquet`
  y deserializaba el estimador histórico fijado por manifiesto.
- B: `research_model_b.py` leía etiquetas, particiones, historia de presencia,
  predictores candidatos y resultados congelados de A. La matriz tenía las siete
  variables A, cuatro presencias t−1…t−4 y sus cuatro indicadores de faltante.
- V3: `forecasting/v3_run.py` adaptaba un bundle JSON, leía la grilla Parquet y
  los paneles/particiones V2; también leía resultados previos para comparación.
  Los kernels `v3.py`, `v2.py`, `dataset.py` y `training.py` ya eran operaciones
  en memoria: no se sustituyen sus algoritmos ni parámetros.
- `forecasting/local_query.py` lee predicciones V2/V3 ya calculadas. Es consulta
  de archivo retrospectivo, no generación de predicciones nuevas.
- Núcleo consolidado: `core_data.py`, `core_model.py` y `core_pipeline.py` ya
  reconstruían, entrenaban y consultaban PostgreSQL. La lectura semanal se
  delega ahora a la capa compartida, conservando la misma consulta y contrato.
- Preparación histórica: `spatial_ml/pipeline.py`, `experiment_pipeline.py` y
  `assumed_scenario_pipeline.py` leían contextos, etiquetas y cartografía locales.
  Sus comandos requieren ahora `--historical-reproduction`.
- Los experimentos anteriores de `features/pipeline.py` y `evaluation/` consumen
  paneles sintéticos o departamentales, con objetivos distintos. Se conservan
  como reproducción histórica explícita; no se conectan a las vistas A/B/V3
  mediante una sustitución silenciosa de sus objetivos.
- Los lectores Excel de `official/excel.py` e
  `ingestion/epidemiology/reader.py`, los adaptadores complementarios y los
  lectores de cartografía son importadores. Permanecen como frontera de ingesta.
  Los módulos de diagnóstico, robustez, inventario y presentación de resultados
  congelados son herramientas históricas; no son fuentes de un ajuste nuevo.

## Acceso compartido y consultas

`sigard_ml.data_access.MLRepository` recibe una conexión validada por
`ingestion.epidemiology.db.connect`. No carga `.env` ni abre fuentes tabulares.

- `records(...)` reutiliza la selección clínica revisada de `core_data.read_records`
  y `eligibility`: fechas por tipo, clasificación, identidad pendiente, residencia,
  versión de revisión y lotes vigentes. No crea otra definición de elegibilidad.
- `calendar()` consulta `analytics.semana_epidemiologica` por la versión argentina.
- `territory(...)` une pertenencia al universo, radio, versión geométrica y
  `analytics.contexto_radio`; puede devolver EWKB canónico para uso privado.
  La geometría y los identificadores nunca entran en la matriz de predictores.
- `run(...)` consulta `analytics.ejecuciones_ml` y `analytics.fuentes_ml` con
  versión explícita. Expone calendario, políticas, cobertura, corte, modo,
  revisión, lotes y hashes; rechaza lotes retirados y calendarios incompatibles.
- `weekly(...)` usa `analytics.conteos_con_procedencia`; `climate(...)` consulta
  `analytics.clima_semana` según la versión climática de la ejecución.
- `legacy_frame(...)` selecciona columnas cerradas de `analytics.ml_a`, `ml_b`
  o `ml_v3`, siempre por versión y, cuando corresponde, origen y horizonte.
  La consulta de inferencia omite la columna del desenlace.
- V3 consulta además `analytics.soporte_predictor_v3`: conserva la regla V2 de
  al menos 50 % de radios con conteo t−1 conocido, clima t−1 completo y continuidad
  de las semanas explícitas del escenario desde origen hasta objetivo.
- `core_series(...)` conserva la unión de `analytics.serie_predictiva_lectura`
  con `analytics.clima_predictivo`, por versión y semana, para la unidad Capital.
  El núcleo conserva sus consultas a `modelo_predictivo`, disponibilidad de lotes
  y registro de resultados. Los estimadores registrados se validan por SHA-256.

La migración `20261029_epi12` añade únicamente tres vistas de metadatos/soporte.
No añade tablas ni actualiza registros, conteos, geometrías o modelos existentes.
El lector analítico recibe las vistas agregadas sin acceso a staging, domicilio
o registros individuales. La consulta de territorio/registros individuales queda
reservada a credenciales con sus permisos previos.

## Contratos y bloqueos

A/B conservan presencia provisional experimental t+1, siete/quince predictores,
RF y umbral originales, 263 radios y el plan temporal 2024 con semanas de purga.
V3 conserva conteos de snapshot, 256 radios, horizontes 1/2/4, sus diecisiete
variables, candidatos, calibración y selección walk-forward de desarrollo. El
núcleo conserva la unidad Capital y su definición filtrada, distinta de V3.

`forecasting.database_pipeline` prepara matrices desde SQL y reutiliza
`fit_models`, `fit_model_b` y el kernel V3. La pequeña extracción
`validate_development_frame` permite usar el panel PostgreSQL sin volver a
construirlo desde un bundle. No se cambia el cuerpo de la evaluación V3.

Antes de ajustar o predecir se exige `equivalencia_ml_verificada=true`, universo
completo, claves únicas, calendario/horizonte correctos, entradas fundamentales
y lotes vigentes. Esta migración **no marca equivalencias como aprobadas**. Ni
una autorización de entrenamiento ni nombres de columnas coincidentes eliminan
ese bloqueo. Un lote nuevo genera una versión nueva con equivalencia falsa.

El ajuste A/B exige las mismas particiones originales, clases soportadas y
purga temporal. V3 recibe cortes temporales explícitos y conserva sus mínimos
de soporte. Una inferencia de investigación exige un estimador en memoria
ajustado antes del origen; no carga automáticamente modelos históricos. Para
V3 sólo se permite consultar la referencia temporal sin activar candidatos.
No hay registro A/B/V3 paralelo al núcleo ni endpoints de producción nuevos.

La anterior inferencia A basada en Parquet queda como `infer_historical` y exige
opción histórica en el CLI. El servicio privado deja de anunciar A como habilitado
y devuelve `postgres_legacy_contract_unverified` para inferencia nueva. Sus
resultados congelados continúan disponibles como archivo retrospectivo. B sigue
sin un flujo reciente acreditado. El frontend no se modifica.

## Comparación reproducible

`data_access.equivalence.compare_frames` compara claves y cantidad de filas,
radios/semanas, valores y faltantes por variable y etiqueta, y campos temporales.
Tolera únicamente redondeo de coma flotante de predictores, hasta 1e−12; etiquetas
y claves temporales deben coincidir exactamente. La comparación no imputa ni
altera la base, y no concede equivalencia a partir de filas parcialmente comunes.

La comprobación solicitada de los datos reales está bajo
`data/interim/official/ml-postgres-migration-20261029-v1/`, excluida de Git.
Se leen sólo derivados históricos ya existentes, vinculados por manifiesto,
para esta comparación. No se reabren los cinco Excel ni se entrenan modelos.
Los informes privados conservan las diferencias por columna y las huellas antes
y después de aplicar las vistas. La ejecución `check-20261029T220125` comparó
las seis versiones analíticas existentes: catorce comparaciones A/B/V3 sin
equivalencia completa, y equivalencia completa del panel del núcleo consolidado.

- A conserva las mismas claves radio/origen, semanas y siete variables; las
  máscaras de etiquetas no coinciden, tanto en las versiones iniciales como
  en las revisadas `r2`. No se detectaron discrepancias en etiquetas conocidas
  por ambas fuentes; sí en qué celdas pueden tener etiqueta conocida.
- B compara su matriz de inferencia congelada con la grilla SQL, que incluye
  semanas adicionales. En las claves comunes difieren las cuatro presencias
  históricas y sus cuatro indicadores de faltante, además de la máscara objetivo.
  Recortar sólo el alcance no resuelve esas diferencias.
- V3, para los tres horizontes y ambas versiones SQL, tiene semanas SQL
  adicionales. En las claves comunes difieren las máscaras de conteo, historial
  reciente y vecinal, y la máscara objetivo. Clima, estacionalidad y población
  coinciden en esas claves. No se usa esa coincidencia parcial para habilitarlo.
- El núcleo reproduce sus claves, variables, etiquetas, faltantes y campos
  temporales del panel histórico. Las tres respuestas de consulta archivadas
  coinciden exactamente con las almacenadas en PostgreSQL.

Las políticas SQL conservan pendientes, incertidumbre geográfica y cobertura
desconocida; los escenarios históricos tenían sus propios alcances exploratorios
y máscaras. No se quitan esos controles para reproducir un entrenamiento antiguo.
La comparación es computacional y no acredita disponibilidad ni precisión espacial.

Las huellas de fuentes archivadas, registros normalizados, ejecuciones, conteos,
serie del núcleo y modelo registrado coinciden antes y después de la migración.
También se verificaron los manifiestos de los artefactos congelados A/B/V1/V2/V3,
el estado `candidate_failed` y la conservación de los 263 radios oficiales.

## Operación e incorporación de lotes

Para inspeccionar A/B/V3 con configuración privada revisada:

```powershell
.\ml\venv\Scripts\python.exe -B -m sigard_ml.forecasting.database_pipeline --family A --connection RUTA_CONNECTION_PRIVADA --config RUTA_CONTRATO_PRIVADO --report NUEVO_INFORME_PRIVADO
```

El contrato contiene `status="approved"`, `authorization_ref`, `dataset_version`
y, para V3, `horizon`, `validation_start` y `test_start`. `--action train` exige
además `research_training_authorized=true` y todos los bloqueos anteriores.
No ejecutar ese ajuste para comprobar una presentación o resolver equivalencia.
Los comandos históricos A/B/V3 enrutan a este consumidor PostgreSQL por defecto;
la reproducción de sus archivos exige `--historical-reproduction` y sus permisos
históricos originales. Los ajustes nuevos no se ejecutaron con datos reales.

El componente principal conserva el CLI `sigard_ml.forecasting.core_pipeline`.
Su consulta por fecha recupera modelo, variables y procedencia desde PostgreSQL;
el estado `candidate_failed` sigue devolviendo cantidad NULL y predicción no
disponible. No se habilitan predicciones por el solo hecho de completar la conexión.

La nueva ingesta sigue su autorización/hash y su transacción de importación.
Después se ejecuta explícitamente `sigard_ml.ingestion.db_analytics` para una
versión nueva con lotes y políticas seleccionados. Las vistas leen esa versión;
no hay un trigger de entrenamiento. Se excluyen lotes retirados al materializar.
El núcleo usa `materialize` para un dataset nuevo con selección y cobertura
explícitas; no sobrescribe su candidato único ya registrado.

Los archivos originales sirven para ingesta; los derivados y modelos antiguos
para respaldo y reproducción histórica. No hay fallback operativo a un archivo
cuando PostgreSQL o las entradas válidas no están disponibles. No se implementa
el frontend de ingesta, no se hacen commits/push y no se usa PostgreSQL 5432.

## Validación ejecutada

- 58 pruebas PostgreSQL/PostGIS: consumidores nuevos, núcleo, ingesta y
  resoluciones; ninguna omitida. Los esquemas ficticios se recrean únicamente
  en la base de pruebas existente, nunca en la base real.
- 122 regresiones focalizadas en ML: A/B, consulta por fecha, V2/V3 y núcleo.
  Se ajustan únicamente estimadores de fixtures ficticias.
- 14 pruebas finales de comandos: rutas operativas PostgreSQL y opción histórica.
- Siete pruebas finales de consumidores, con ajuste e inferencia ficticios y
  lectores pandas, Arrow, GeoPandas y aperturas tabulares bloqueados. Comparan
  las diecisiete variables y etiquetas V3 con las transformaciones originales
  en los tres horizontes; V3 ejercita sus tres candidatos en desarrollo.
- Los tres comandos reales A/B/V3 se inspeccionaron sin permiso de ajuste:
  seleccionan PostgreSQL y devuelven el bloqueo de equivalencia esperado.
- Backend aislado: 222 aprobadas y 6 omitidas; SQLite en memoria, dotenv
  deshabilitado, conexiones no SQLite y Docker bloqueados. Las omisiones no
  son evidencia de integración backend/PostGIS.
- Auditoría estática de seguridad del repositorio: 189 comprobaciones aprobadas.
  No se construye imagen ni se inicia Docker. `git diff --check` sin errores.

Las advertencias observadas corresponden a NumPy/joblib, detección de núcleos
en Windows y deprecaciones de dependencias backend; no se actualizaron paquetes.
No se ejecutó entrenamiento ni inferencia nuevos sobre los datos reales.

Para un ajuste real posterior siguen haciendo falta la equivalencia revisada y
la autorización específica de ejecución. El núcleo conserva además la regla de
un único candidato registrado: no se modifica esa protección para permitir otro
ajuste durante esta migración. El siguiente paso es revisar las diferencias de
etiquetas/cobertura, sin levantar máscaras ni entrenar automáticamente.
