# Contrato de entrada derivada para conteos t+1

22/10/2026 · `principal-count-input-1` · revisión institucional pendiente.

Implementación: `ml/src/sigard_ml/forecasting/adapter.py`. El adaptador recibe
agregados previamente preparados; no clasifica pacientes, deduplica episodios,
geocodifica ni construye cobertura. No importa las etiquetas A/B. Reutiliza las
reglas de snapshots de `Inputs`, el calendario oficial, `SourceRegistry`,
`AuthorizedUse` y las constantes/serialización del preflight existente.
No convierte los informes simulados de etapas 7–9 en aprobaciones reales.

Su salida se conecta a `build_dataset` y a la reconstrucción de etiquetas por
corte existente. No cambia features, particiones, candidatos, selección,
baselines ni métricas. La ruta acreditada conserva `training_authorized=False` y
`run_experiment` la rechaza, aun cuando la preparación supere todos los controles.
`forecast_next_week` mantiene el bloqueo de inferencia real para todas las rutas.
La modalidad experimental siguiente tiene unidad, permisos y límites separados.

## Extensión V2: snapshot filtrado y consulta privada

La evaluación futura de modelos V3 congelados tiene un
[contrato separado de panel, disponibilidad y etiquetas](evaluacion-independiente-v3.md).
Recibe agregados preparados bajo autorización específica, conserva la semántica
del snapshot y sella predicciones antes de abrir desenlaces. No modifica este
adaptador ni concede autorización de entrenamiento para nuevas entregas.

La solicitud V3 del 26/10/2026 habilita un experimento nuevo sobre este mismo
derivado, sin modificar cobertura, ceros, desconocidos ni la política de 2022.
`forecasting.v3.feature_frame` conserva exactamente las etiquetas V2 y agrega
variables admisibles del origen cerrado y su pasado; indicadores de conteos y
vecinos disponibles acompañan las medias parciales. No rellena desenlaces null
ni inventa semanas para construir rezagos. No acredita disponibilidad real P6.
Las particiones existentes y los cortes purgados se reutilizan por horizonte.

La consulta admite además `--artifacts ml/artifacts/official/sigard-principal-v3-experimental`,
manteniendo V2 por defecto. Verifica hashes de predicciones y límites de calidad.
`--method selected|persistence` conserva la alternativa de referencia; La selección efectiva depende de la versión privada autorizada. El lector rechaza
candidatos ML en la presentación: su futura habilitación requeriría integración
y promoción explícitas. `--research-summary` lee sólo métricas agregadas V3
selladas, sin ejecutar modelos ni habilitar alertas. Los puntajes de presencia
siguen excluidos de respuestas territoriales y mapas. No hay publicación nueva.

El [cierre de presentación](predictive-experimental-demo.md) agrega a la respuesta
`selected_method`, `model_version`, `expected_eligible_total`, `eligible_radios`,
`radios_without_estimate`, `radios_with_incomplete_predictors` y `estimate_status`
por radio (`available`, `available_with_historical_mean_fallback`, `insufficient_data`).
Un conteo ausente sólo se admite con estado explícito de indisponibilidad; nunca
se reemplaza por cero. Infinitos y negativos se rechazan. El total completo es
null si falta alguna estimación; el subtotal elegible y los faltantes se informan
aparte. Se conserva el total del conjunto al filtrar un radio.
`probability_available=false` y el aviso “en evaluación” sustituyen los puntajes
en la consulta de presentación; los artefactos de investigación no se modifican.
`--map-output` genera sólo `.private.html` nuevos bajo `data/interim/official`,
desde la plantilla genérica local, sin red, modelos ejecutables ni publicación.

La instrucción expresa V2 del 26/10/2026 permite el escenario separado
`principal-snapshot-input-2`, dentro de `provisional_aggregate_experiment`:
`data_kind="epidemiological_snapshot_scenario"`, `count_unit="snapshot_record_count"`
y `target_definition="principal-confirmed-snapshot-2"`. No cambia el derivado V1.

`snapshot_scenario` forma parte del alcance y huella del paquete: identifica el
escenario, lista exacta de semanas cubiertas, significado de ceros, referencia
de la declaración, SHA-256 de máscaras de calidad y política separada de 2022.
Se usan sólo las semanas con registros confirmados ya representadas en la
extracción; no se deducen períodos solicitados ni cobertura continua entre sus
extremos. La declaración de exhaustividad respecto de filtros es una hipótesis
experimental, no acredita vigilancia ni disponibilidad histórica.

La grilla de esas semanas contiene los 256 radios. `provisional` con
`label_kind="snapshot_record_count"` admite enteros ≥0 sólo sin pendientes;
`unknown` conserva null. Todas las filas mantienen `coverage_complete=false`,
`mature=false` y disponibilidad desconocida. Las máscaras existentes excluyen
pendientes y fechas aproximadas del ajuste. El nuevo derivado conserva por
separado el conteo positivo registrado incluso si su etiqueta utilizable es null.
Ceros asumidos no son ausencia epidemiológica; 2022 no aporta confirmados ni ceros.

El documento de uso declara `conditional_on_observed_cells=false`,
`snapshot_zero_assumption_accepted=true` y `local_retrospective_query_authorized=true`,
además del fundamento del responsable y límites de uso existentes. La verificación
de integridad y permisos permanece activa; no se repiten auditorías históricas.
La ruta V1 rechaza este esquema para evitar mezclar métricas condicionales y grilla.

`build_dataset` admite horizontes directos t+1, t+2 y t+4, conservando predictores
exactos t−1…t−4 y sin encadenar predicciones. Los modelos se entrenan/evalúan por
horizonte. La admisibilidad exige origen, objetivo y semanas intermedias dentro
del conjunto explícito, clima rezagado y al menos la mitad de radios con conteo
t−1 disponible. El modelo puede estimar radios con rezagos faltantes mediante
su tratamiento de features, siempre con advertencia; no imputa sus desenlaces.

La consulta privada `python -B -m sigard_ml.forecasting.local_query` reutiliza el
planificador manual de fechas, lee predicciones V2 o V3 explícita selladas y no carga
modelos ejecutables. Ofrece `--list-dates`, `--date YYYY-MM-DD`, `--horizon 1|2|4`,
`--radio ID` y exportación JSON con `--output` sólo bajo directorios oficiales
privados. Una fecha sin origen suficiente devuelve estado de datos insuficientes.
No usa observaciones de 2026 ni transforma t+1 en un horizonte arbitrario.

La suma territorial es la suma de las 256 estimaciones sin ajustar con modelos
departamentales. Un total observado de 256 radios permanece null si hay etiquetas
desconocidas; se comparan por separado los subconjuntos conocidos y se conserva
el límite inferior de registros positivos. Presencia binaria se ajusta sólo con
etiquetas utilizables; la corrección sigmoide usa desarrollo cronológico. Su salida
se denomina puntaje experimental, sin acreditar probabilidad de infección o brote.

## Modalidad `provisional_aggregate_experiment`

24/10/2026. Modificación de software solicitada por el responsable. Se extienden
`AdapterRequest`, `adapt_derived`/`load_derived`, `build_dataset` y `run_experiment`
existentes; no se agrega otro pipeline, adaptador ni modelo. La llamada requiere
`AdapterRequest(..., mode="provisional_aggregate_experiment")`. El modo por defecto
sigue siendo `accredited_episode_preparation`, con todos sus requisitos P1–P6.

El experimento estima **conteos de registros observados, condicionados a celdas
positivas observadas**. No estima episodios independientes, ausencia de casos,
incidencia exhaustiva ni aparición en todos los radios. Puede conservar P1–P6
sin resolver porque no acredita el objetivo definitivo. No transforma esos
pendientes en aprobaciones ni modifica sus resultados.

Permisos obligatorios antes de leer el paquete: `SourceRegistry` debe autorizar
`inspection`, `processing`, **`training` y `evaluation`** para la fuente del paquete,
su versión y `sheet="derived_bundle"`, `subset_ref` exacto. Se comprueban los mismos
usos para cada entrada de `upstream_sources`. La procedencia de counts, clima,
territorio y grafo debe referir a fuentes/versiones incluidas en esa lista. Los
originales nunca se abren. No basta con habilitar el paquete omitiendo restricciones
aguas arriba; el custodio debe revisar la exhaustividad de la procedencia.

El uso real requiere autorización específica, integridad y revisión del
custodio. Un permiso experimental local no autoriza publicación ni producción.
Las decisiones, sus evidencias y sus resultados permanecen en archivos privados.

Se reutiliza el paquete JSON agregado, la verificación SHA-256, `EvidenceDocument`,
los esquemas `TABLE_COLUMNS` y las reglas comunes de snapshots. En esta modalidad:

- `schema_version="principal-provisional-input-1"`,
  `data_kind="epidemiological_provisional_records"`,
  `count_unit="provisional_record_count"`.
- Campos adicionales obligatorios: `territory_version="la-rioja-46014010-256-v1"`,
  `target_definition="principal-confirmed-records-1"`,
  `evaluation_mode="retrospective_event_time"` y `upstream_sources`, lista no vacía
  de objetos exactos `source_id,source_version,sheet,subset_ref`. `scope` incluye
  los campos originales y estos cuatro campos adicionales. El custodio verifica
  los 256 IDs contra su manifiesto; no se infieren desde la cardinalidad.
- `counts`: sólo positivos enteros, `state="provisional"`,
  `label_kind="provisional_record_count"`, `coverage_complete=false`, `mature=false`.
  `pending` conserva el estado aportado. No admite ceros, episodios acreditados,
  duplicados, campos individuales o coordenadas. Admite una tabla dispersa.
- Clima/contexto/grafo conservan sus esquemas, procedencia y reglas numéricas;
  el contexto incluye los 256 radios y el grafo debe ser cerrado y simétrico.
  Se admiten huecos climáticos explícitos sin descargar ni regenerar clima.
- `available_on` y la disponibilidad del grafo pueden ser null y se conservan
  así. Sólo una versión retrospectiva por clave; no se selecciona arbitrariamente
  entre revisiones. No se copia la extracción a disponibilidad histórica.

Se requieren los documentos existentes de procedencia por componente y dos roles
de uso, ligados a los bytes exactos y al alcance: `provisional_experiment_preparation`
(con `source_id,subset_ref`) y `provisional_experiment_use`. Este último exige
`experiment_mode="provisional_aggregate_experiment"`,
`conditional_on_observed_cells=true`, `production_inference_authorized=false`,
`historical_availability_accredited=false` y un fundamento de autorización:

- Ruta externa existente: `provider_permission_ref` no vacío, con
  `authorization_basis="external_provider_permission"` o ausente por compatibilidad.
- Declaración expresa del responsable: `authorization_basis="project_owner_declared_provision"`,
  `project_owner_declaration_ref` no vacío, `institutionally_signed=false` y
  `local_experimental_only=true`, sin atribuir `provider_permission_ref`.

Son evidencias de acceso/uso experimental; no reemplazan ni simulan documentos
P1–P6. Los campos comunes de documentos siguen siendo obligatorios. La nueva
decisión privada transcribe la autorización efectivamente aportada en esta tarea;
el software no inventa permisos ni autentica firmas.

Una vez aportados esos permisos auténticos y el paquete autorizado:

```python
inputs = load_derived(registry, request, documents=documents)
result = run_experiment(inputs, start=start, end=end,
    validation_start=validation_start, test_start=test_start,
    evaluation_as_of=review_as_of, seed=20261021)
```

La construcción del panel conserva desenlaces ausentes como null y usa semanas
exactas t−1…t−4 y objetivo t+1. Las exportaciones finales se reconstruyen por fecha
del evento: **no es una evaluación punto en el tiempo**, aunque no entren datos
de semanas futuras como features. El contexto censal es retrospectivo. La
imputación de features faltantes con indicadores permanece dentro del estimador
ajustado sólo en entrenamiento; nunca imputa etiquetas ni acredita un cero.

Se reutilizan candidatos, semilla, cortes/purga, selección por MAE de validación,
refit de desarrollo y baselines del principal. El test no elige configuración;
su independencia científica no queda acreditada automáticamente. El informe
incluye semanas/filas utilizadas, MAE/RMSE/sesgo, unidad y límites. No calcula
probabilidades de aparición ni totales completos de Capital, incluso si alguna
semana tuviera observaciones en todos los radios. `FittedCounts.data_kind` conserva
la condición real provisional y la inferencia de producción continúa denegada.

`training_authorized` y `evaluation_authorized` sólo resultan true en entradas de esta modalidad que superan
la autorización y la comprobación de integridad; no es un flag configurable.
Se vuelven a comprobar permisos, documentos y huellas al construir/ejecutar.
Las demás rutas no adquieren permisos. Modelos, configuración, predicciones e
informes de una ejecución autorizada deberán guardarse en una carpeta privada
nueva, sin sobrescribir versiones anteriores ni activar reentrenamiento automático.
`forecasting.artifacts.save_experiment` guarda el modelo, configuración, variables,
panel, partición, métricas, predicciones ya calculadas y manifiesto SHA-256 sólo
bajo una versión nueva de `ml/artifacts/official/`. No vuelve a ajustar/predecir
ni carga modelos externos. Los artefactos y permisos privados permanecen fuera
de Git. La versión solicitada es `sigard-principal-v1-experimental`.

## Proyección descriptiva provisional del 24/10/2026

`official.coverage_panel.principal_provisional_counts` reutiliza los agregados
históricos de cobertura y su inventario de clasificación. No es una nueva ruta
de ingestión ni otro adaptador. El llamador debe autorizar las fuentes y verificar
sus manifiestos antes de pasar las tablas en memoria. La proyección exige
conciliación exacta por fuente y clasificación homogénea `confirmado` entre los
incluidos. Rechaza fuentes mixtas por celda, versiones ausentes, conteos inválidos,
duplicados y semanas incompatibles con el calendario oficial. No distribuye
resúmenes marginales entre celdas.

Devuelve sólo celdas históricas con registros positivos, distinguiendo `included`
y `outside` para `la-rioja-46014010-256-v1`. El llamador debe verificar los 256 IDs
contra el manifiesto territorial; la función comprueba versión, cardinalidad,
unicidad y pertenencia al conjunto suministrado, sin autenticar su procedencia.
La salida privada conserva:

- Año/semana epidemiológicos, inicio/fin y versión del calendario.
- `radio_id`, versión territorial y condición interior/exterior.
- `provisional_positive_records`, clasificación registrada y definición de objetivo.
- Unidad `provisional_record_count`, `accredited_episode_count=null`, P2 sin resolver.
- P3 no acreditado, estados originales de cobertura y menciones de pendientes
  por celda, que no se suman como registros únicos.
- P5 provisional aproximado y cantidad de asignaciones inciertas preservada.
- Fuente/versión, extracción declarada, versión temporal histórica y transformación.
- Madurez desconocida, `available_on=null`, condición provisional y entrenamiento
  deshabilitado. La extracción no es disponibilidad histórica.

Es una **tabla descriptiva dispersa, no el paquete `principal-count-input-1`**.
No incluye la grilla completa, documentos P1–P6, snapshots disponibles ni episodios
elegibles. No se conecta directamente al adaptador ni se convierte su unidad
global a `eligible_episode_count`. Cuando exista respaldo, una preparación
autorizada deberá representar explícitamente desconocidos en el alcance íntegro,
sin sustituirlos por ceros. No se debilitó ninguna exigencia de este contrato.

`official.classification.provisional_record_positive` define dos objetivos
versionados y explícitos:

- `principal-confirmed-records-1`: registros clasificados como `confirmado`.
- `principal-operational-records-2022-1`: los anteriores y registros clasificados
  como `sospechoso` o `probable` cuyo **año epidemiológico sea 2022**. Es una
  decisión experimental del responsable, no confirmación oficial ni nueva
  clasificación clínica. Excluye descartados e indeterminados.

Los criterios se prueban con agregados ficticios. Su aplicación real exige
un derivado conjunto autorizado y no puede reconstruirse desde resúmenes
marginales. Un cero declarado no acredita ausencia epidemiológica; una celda
sin dato permanece desconocida.

## API y permiso antes de interpretar entradas

```python
from sigard_ml.forecasting.adapter import AdapterRequest, adapt_derived, load_derived
from sigard_ml.forecasting.dataset import build_dataset

# registry y documents deben provenir de una revisión humana autorizada.
# No se crean aquí permisos ni documentos de aprobación.
request = AdapterRequest(
    source_id=source_id, source_version=version, subset_ref=subset_ref,
    package_sha256=expected_sha256, preparation_ref=preparation_ref,
    decision_ref=decision_ref, review_as_of=review_date,
)
inputs = load_derived(registry, request, documents=documents)
# Alternativa sin IO: adapt_derived(authorized_bytes, registry, request, documents=documents)
panel = build_dataset(inputs, start=origin_start, end=origin_end,
                      evaluation_as_of=outcome_freeze)
```

Los nombres del ejemplo son parámetros que debe aportar el responsable; no
constituyen una configuración habilitada. `review_date` es un `datetime.date`.
No hay CLI real ni descubrimiento de archivos. La demo ficticia conserva su CLI.

El registro vacío deniega todo. La entrada `SourceAuthorization` debe estar
habilitada, ser un extracto aprobado y autorizar **inspection y processing**
para `sheet="derived_bundle"`, `subset_ref` exacto y la misma versión que la
solicitud. Debe incluir custodio, confidencialidad, política de almacenamiento
y `evidence_ref` igual a `preparation_ref`. Los permisos de entrenamiento,
evaluación y publicación son distintos; el adaptador no los concede.

`load_derived` resuelve sólo la ruta absoluta de esa autorización. Admite un
JSON bajo `data/interim/` o `data/processed/` del repositorio, con máximo 32 MiB;
rechaza originales, otros formatos y escapes de esos directorios por enlaces.
Comprueba el permiso antes de abrirlo y el SHA-256 esperado de **bytes exactos**
antes de interpretar JSON. No abre ningún documento o URL referenciado.
`adapt_derived` también verifica permisos antes de interpretar los bytes recibidos;
quien los cargó previamente es responsable de haber autorizado esa lectura.

## Esquema exacto del paquete JSON

Todos los campos siguientes son obligatorios; no se admiten campos adicionales.
Fechas: cadenas canónicas `YYYY-MM-DD`, sin hora; cortes al cierre diario.
No se admiten claves JSON repetidas, NaN ni Infinity. No incluye geometrías,
coordenadas, IDs de pacientes ni registros individuales.

- `schema_version`: `principal-count-input-1`.
- `data_kind`: `epidemiological_accredited`, o `fictional` para integración
  simulada; nunca mezclar condición de paquete y documentos. Las fixtures usan
  exclusivamente radios con prefijo `fictional_`. Probar la rama acreditada con
  bytes ficticios no acredita ningún dataset real.
- `dataset_version`: cadena no vacía, igual a `source_version` autorizada.
- `calendar_version`: `ar-snvs-2020-2026-v1`. Ampliar años requiere evidencia
  y una modificación explícita del contrato/calendario, no inferirlos por nombre.
- `count_unit`: exactamente `eligible_episode_count`; no notificaciones,
  registros, presencia, cantidades departamentales repartidas o asignación sintética.
- `period_start`, `period_end`: domingos iniciales de la primera/última semana,
  inclusivos. La última semana debe haber cerrado al `review_as_of` explícito.
- `radios`: lista no vacía de IDs opacos, únicos, del universo aprobado en P5.
  No se leen los 263 radios ni se supone que cualquier lista los representa.
- `sources`: objeto con exactamente `counts`, `climate`, `territory`, `graph`.
  Cada valor tiene exactamente `source_id`, `source_version`,
  `transformation_version`, `provenance_ref`, todas cadenas no vacías.
  La referencia resuelve a un documento de procedencia revisado. Las fuentes
  aguas arriba se documentan en su respaldo; el adaptador no las abre.
- `counts`, `climate`, `territory`: listas no vacías con los esquemas de abajo.
- `graph`: objeto con exactamente `edges` (lista de pares de radios),
  `available_on` y `source_ref`. Aristas únicas, simétricas y sin lazos; admite
  radios aislados y grafo sin aristas. Su disponibilidad es independiente.

`counts`, columnas exactas:

```text
radio_id, week_start, available_on, count, state, coverage_complete,
pending, mature, source_ref, label_kind, partial_week
```

`count`: número entero no negativo o null; booleanos/textos no son conteos.
`state`: `complete`, `provisional` o `unknown`. `coverage_complete`, `pending`,
`mature` y `partial_week` son booleanos explícitos. Correspondencias obligatorias:

- `complete` → `label_kind="accredited_episode_count"`, conteo no nulo,
  cobertura completa, madurez y ningún pendiente. P1–P6 deben respaldar el
  paquete exacto. Cero exige las mismas condiciones que un conteo positivo.
- `provisional` → `label_kind="provisional_record_count"`. Conserva el conteo
  de registros provisional aportado, incluso cero, sin usarlo como episodios
  elegibles, presencia acreditada, feature de conteos u objetivo de entrenamiento.
- `unknown` → `label_kind="unknown"`, `count=null`. Nunca se completa con cero.

Un conteo completo con banderas incompatibles se rechaza; no se degrada ni
acredita silenciosamente. Un positivo respaldado pero sin total exhaustivo debe
resolverse aguas arriba y conservar su incertidumbre; este contrato no deduce
un total ni presencia acreditada desde registros provisionales.

`climate`, columnas exactas:

```text
week_start, available_on, temperature, humidity, precipitation,
complete, source_ref, partial_week
```

Temperatura media en °C (finita), humedad relativa en % [0,100] y precipitación
semanal en mm no negativa. Exige `complete=true`, valores no nulos y
`partial_week=false`; rechaza semanas de borde parciales. Es contexto semanal
común de Capital, sin atribuir mediciones individuales por radio.

Para preparar esta tabla se reutilizan `aggregate_climate(daily,
calendar=DEFAULT_CALENDAR)` y `forecasting.adapter.climate_snapshots(weekly,
availability=..., source_ref=...)`. El segundo recibe un diccionario explícito
`date -> date` con disponibilidad efectiva por semana, sin estimarla desde el
cierre o una extracción epidemiológica. Requiere calendario oficial, límites
exactos y siete días con las cinco variables completas. Su salida conserva las
columnas anteriores; no autoriza uso ni reemplaza P6. Temperaturas mínima/máxima
(promedios diarios) permanecen en el derivado semanal, fuera de este esquema.
El cruce real 75/75 conserva disponibilidad desconocida: no constituye un paquete
real listo para este adaptador. Ver [comprobación climática](principal-count-forecasting.md#integración-climática-del-principal-22102026).

`territory`, columnas exactas:

```text
radio_id, available_on, population, area_km2, source_ref
```

Población no negativa, superficie km² positiva; null preserva desconocimiento.
Densidad hereda ambas entradas y no se recibe como variable independiente.
La adecuación histórica de los límites/cartografía y las revisiones de población
requieren P5/P6, además de la integridad del grafo. El adaptador no hace auditoría
geométrica ni acredita residencia o lugar de infección.

Desde el 23/10/2026, el universo operativo del principal es
`la-rioja-46014010-256-v1`, configurado en `ml/configs/principal_territory.json`.
Son 245 radios interiores y 11 con fracción de superficie interior ≥ 0,9999
en la localidad `46014010`, siempre como unidades completas. Su
[versión territorial y grafo inducido](principal-city-boundary.md#adopción-operativa-del-23102026)
son independientes del maestro de 263 y de A/B. `territorial_components`
prepara las columnas anteriores y el grafo, con disponibilidad y referencias
explícitas; no completa conteos ni decisiones P1–P6. La versión debe constar
en la procedencia de ambos componentes. La elegibilidad epidemiológica y las
geocodificaciones aproximadas permanecen sin cambios.

Cada tabla admite revisiones: clave de snapshot `radio_id,week_start,available_on`
en counts; `week_start,available_on` en clima; `radio_id,available_on` en territorio.
No admite duplicados. Cada `source_ref` debe coincidir con la `provenance_ref`
de su componente. Ningún snapshot puede ser posterior al corte de revisión.

Debe existir al menos un snapshot explícito para **cada radio y semana** del
período en counts, cada semana en clima y cada radio en territorio. Una celda
desconocida explícita satisface la integridad de la grilla, no la cobertura.
Se rechazan huecos, radios ajenos y toda semana marcada parcial; no se excluyen
filas para producir negativos. Provisionales/desconocidos permanecen en el panel
con objetivo null y no entran al ajuste mediante `training_labels`.

## Documentos P1–P6, procedencia y autorización

`documents` es un diccionario `referencia_opaca: EvidenceDocument(content, sha256)`.
Cada contenido es JSON UTF-8 de hasta 2 MiB, con integridad SHA-256. No contiene
registros nominales. Se exige en cada documento:

```text
reference, role, data_kind, package_sha256, scope, status,
reviewer_ref, basis, rule_version, limits, decided_on
```

`reference` debe ser la clave del registro; `status="approved"`;
`decided_on` no puede ser posterior a `review_as_of`. Responsable, fundamento,
versión de regla y límites deben estar documentados con texto no vacío.
Se permiten campos documentales adicionales para describir las decisiones.
`scope` debe igualar exactamente el objeto formado por los campos del paquete
`dataset_version,calendar_version,count_unit,period_start,period_end,radios`.
`package_sha256` vincula todos los registros, revisiones, territorio y versiones
a los bytes exactos aceptados. Un cambio del paquete exige nuevas vinculaciones
y revisión del alcance; no actualizar informes congelados para ocultarlo.

Roles y campos adicionales obligatorios:

- `count_preparation`: referencia `preparation_ref`, con `source_id` y
  `subset_ref` exactos. Representa preparación autorizada, no ejecución del modelo.
- `count_training_eligibility`: referencia `decision_ref`, con `evidence_refs`,
  objeto de exactamente P1…P6 y seis referencias distintas. Revisión de la
  aptitud documental de las etiquetas para el futuro estudio de conteos;
  **no autoriza iniciar entrenamiento**.
- `P1`…`P6`: un documento aprobado y aplicable por decisión, sin sustituir
  la matriz única del dossier. `basis` debe localizar el respaldo documental
  y explicar la resolución; `rule_version` identifica su implementación aguas
  arriba y `limits` registra excepciones/desconocidos y límites del alcance.
- `provenance`: un documento por componente, con `component` exacto y
  `source` igual al objeto correspondiente de `sources`. Su fundamento conserva
  procedencia, condición, versiones, período y transformación del derivado.

P2 exige además `identity_policy_version="principal-episode-review-1"` y
`identity_snapshots`: una entrada por snapshot de counts, incluidas revisiones.
Cada entrada contiene exactamente `key=[radio_id,week_start]`, `available_on`,
`basis_ref` y `summary`. No contiene IDs de pacientes, claves individuales o
coordenadas. `basis_ref` localiza la revisión privada del alcance y su conciliación.

`summary` tiene exactamente:

```text
eligible_records, independent_episodes, possible_duplicate_records,
unknown_identity_records, exact_episode_count, review_refs, review_available_on
```

Las cuatro primeras cantidades son enteros no negativos. `independent_episodes`
cuenta representantes de episodios con identidad revisada, sin acreditar su
clasificación clínica o cobertura. `unknown_identity_records` incluye
`possible_distinct`, `indeterminate` e identidades no revisadas. Los posibles
duplicados siguen separados. Si cualquiera está pendiente, el conteo exacto es
null; en otro caso iguala `independent_episodes`. La suma de pendientes y episodios
independientes no puede superar `eligible_records`; los demás registros pueden
ser no representantes revisados. Cada episodio cuenta sólo en la celda de su
representante autorizado, sin perder los otros registros.

`review_refs` conserva las referencias opacas de decisiones autorizadas;
`review_available_on` es su última disponibilidad ISO, no posterior al snapshot.
Ambos son obligatorios cuando hay registros revisados; sin ellos son `[]` y null.
Una etiqueta `complete` debe coincidir con el conteo exacto P2, sin pendientes.
Un conteo provisional no nulo debe coincidir con `eligible_records`; no se
convierte en episodio. Una conciliación vacía no acredita un cero: siguen siendo
obligatorios P1/P3–P6, cobertura, madurez y alcance íntegro.

Esta revisión añade requisitos documentales P2 al contrato de paquete existente;
los documentos anteriores sin conciliación se rechazan, sin aprobación implícita.
El adaptador reutiliza `episodes.validate_episode_summary`; no resuelve identidades,
abre decisiones privadas ni autentica instituciones. El custodio debe comprobar
las decisiones, el criterio aprobado y que el alcance incluya todos los pendientes
que podrían afectar cada radiosemana antes de preparar las atestaciones.

P6 añade `snapshots`: lista con una entrada por snapshot de cada tabla y una
por grafo. Cada entrada tiene exactamente:

```text
component, key, available_on, variables, observed_through, basis_ref
```

`key` es `[radio_id,week_start]` en counts, `[week_start]` en clima, `[radio_id]`
en territorio y `[]` en grafo. `variables` debe ser la lista exacta y ordenada:

```text
counts:    [count,state,coverage_complete,pending,mature]
climate:   [temperature,humidity,precipitation,complete]
territory: [population,area_km2]
graph:     [edges]
```

`available_on` debe coincidir con el snapshot y representar disponibilidad
efectiva para SIGARD de **todas** sus variables, incluidos estados y máscaras.
Si sus campos llegaron en momentos distintos, no anticipar el vector: preparar
snapshots completos según evidencia real. `observed_through` no puede superar
la disponibilidad y para counts/clima debe igualar el sábado de su semana.
Esto acredita referencia semanal cerrada; no convierte cobertura desconocida
en completa. `basis_ref` localiza el historial/publicación/recepción revisado
en P6; nunca se abre automáticamente. No sirve la fecha del hecho como prueba
de disponibilidad ni basta una exportación final reconstruida retrospectivamente.

La extracción común **26/08/2026**, declarada por el responsable para las cinco
entregas SISA, queda en `provenance_declaration` del derivado privado de metadatos,
vinculado por huella a P3 y a las versiones de fuente preservadas. No se añade un
campo a las tablas ni se cambia este esquema. Esa declaración no completa P3/P6,
no es la disponibilidad histórica del registro/revisión y no se copia automáticamente
a `available_on` de un agregado acreditado. La
[síntesis temporal](principal-count-forecasting.md#consolidación-temporal-extracción-declarada-del-26082026)
precisa alcance, versionado inmutable, protocolo y evidencia pendiente.

No se aceptan atestaciones sobrantes, faltantes o con variables/claves/fechas
distintas. El join as-of existente deja fuera de cada origen los snapshots
posteriores, incluso si están presentes en el paquete. Para construir un panel
de entrenamiento/evaluación, todo origen necesita estar dentro del alcance con
historia t−4 y objetivo t+1; el congelamiento no puede superar el corte revisado.
Para construir sólo features (`include_outcomes=False`), se exigen historia t−4
y origen dentro del alcance, sin exigir ni leer desenlaces de la semana siguiente.
Esta opción permite preparar features para t+1 futuro; no amplía el alcance de
etiquetas ni habilita inferencia real. La [consulta por fecha](principal-count-forecasting.md#consulta-por-fecha-en-python)
reutiliza esa ruta, con modelo de un paso y corte explícito.
Tras adaptar, una huella
en memoria detecta modificaciones de tablas/metadatos antes de construir paneles;
se vuelven a comprobar permisos y documentos, sin IO. La procedencia de cada
fila conserva huella del paquete, referencias P1–P6 y huellas documentales.

**Frontera de confianza:** un documento JSON aprobado no autentica una firma,
una institución ni la verdad epidemiológica. El custodio/revisor debe comprobar
los respaldos y cargar únicamente permisos/documentos auténticos y autorizados.
No hay integración con firma digital, servidor ministerial ni resolución automática
del dossier. Las pruebas sólo acreditan controles de software sobre fixtures.

## Procedimiento para un futuro entrenamiento de episodios acreditados

1. Resolver y registrar P1–P6 en la sección 9 del dossier único, con evidencia,
   alcance, responsable, fecha, reglas, límites y tratamiento de pendientes.
   Utilizar el [resumen para la solicitud al Ministerio](next-ml-training-readiness.md#10-resumen-ejecutivo-para-solicitar-evidencia-al-ministerio).
2. Obtener autorización independiente de acceso/procesamiento y preparación
   para versiones, subconjunto y derivados exactos. No abrir entradas suspendidas
   ni originales adicionales con el permiso de este desarrollo.
3. Preparar agregados nuevos privados bajo esas reglas, conservando fuentes
   inmutables. Registrar procedencia por componente y disponibilidad P6 de cada
   snapshot. Exportar el JSON anterior sin información identificable. No repartir
   totales departamentales ni convertir etiquetas A/B en episodios acreditados.
4. Fijar SHA-256 de bytes exactos. El responsable autentica y revisa los documentos
   de procedencia, P1–P6, aptitud de etiquetas y autorización de preparación para
   esa huella y alcance. Cargar el registro privado en memoria sin versionarlo.
5. Ejecutar el adaptador y `build_dataset` únicamente con autorización específica
   de esa nueva etapa; revisar nulos, versiones, cortes, cobertura y maduración.
   Un rechazo no se resuelve marcando banderas: corregir el derivado o documentar
   y revisar el alcance afectado, conservando desconocidos.
6. Revisar el producto preparado y congelar protocolo científico: población,
   objetivo de conteos, features, faltantes, semillas, baselines, cortes/purga,
   maduración y reserva temporal independiente. Acordar validación prospectiva
   si no existe reserva histórica, sin iniciarla automáticamente.
7. Obtener **otro acto explícito de autorización de entrenamiento**, vinculado
   a paquete, protocolo y revisión. En una futura tarea autorizada implementar
   su verificación en la entrada de ejecución; la ruta acreditada sigue rechazando
   entradas reales. El experimento provisional separado tiene los requisitos de
   uso descritos arriba. No basta añadir TRAINING al registro ni cambiar `data_kind`.
   No hay un comando real habilitado por defecto. Inferencia, evaluación
   real, calibración y publicación requieren sus decisiones propias.

## Verificación local permitida

```powershell
.\ml\venv\Scripts\python.exe -B -m pytest ml/tests/test_forecasting_adapter.py ml/tests/test_principal_forecasting.py ml/tests/test_official_calendar.py ml/tests/test_baseline_evaluation.py -p no:cacheprovider --basetemp=ml/.tmp/forecasting-adapter-regression
.\backend\.venv\Scripts\python.exe -B tools/check_repository_security.py
git diff --check
```

Todas las entradas del test de integración y sus decisiones son generadas,
completamente ficticias y en memoria. Se simula también la condición acreditada
para verificar la ruta y el bloqueo de ejecución. El lector se comprueba mediante
bytes simulados, sin crear ni abrir derivados reales. Las regresiones del módulo
principal pueden ajustar sus fixtures ficticias; no entrenan con datos reales.
