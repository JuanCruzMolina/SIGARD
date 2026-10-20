# SIGARD Fase 5B.1: decisiones epidemiológicas y cobertura

Versión `official-epidemiology-decision-review-0.5b.1`. Prepara un dossier y una
plantilla privada para el responsable a partir de las cinco fuentes autorizadas,
sus normalizados y los diagnósticos preservados de Fases 4.2, 4.3 y 5B. No
reingiere, abre Excel, geocodifica, calcula features, cambia el Modelo A, entrena,
modifica clasificaciones o materializa negativos.

## Ejecución y privacidad

```powershell
.\ml\venv\Scripts\python.exe -B -m sigard_ml.official.epidemiology_review_pipeline --config ml/configs/official.epidemiology-review.example.json
.\ml\venv\Scripts\python.exe -B -m pytest ml/tests/test_official_epidemiology_review.py -p no:cacheprovider --basetemp=ml/.tmp/phase5b1-check
```

Se exige `entrenamiento-ML`, autorización de inspección/procesamiento para todas
las fuentes, manifiestos válidos y destino nuevo privado directamente dentro
de `data/interim/official/`. El ejemplo usa `epidemiology_review_05b1_v1`.
Para repetir debe elegirse otro nombre; se rechazan sobrescrituras y rutas
públicas. Se comparan hashes de fuentes, paneles, datos y modelos antes/después.
No se requieren documentos externos para generar el diagnóstico: su ausencia
se informa como evidencia no disponible, sin completar decisiones en nombre del
responsable. Los informes, inventarios y plantillas permanecen fuera de Git/Docker.

## Evidencia epidemiológica y territorial

`epidemiology_review.py` cruza exclusivamente claves técnicas de las auditorías
preservadas con `classification_label` de los normalizados autorizados. No
reinterpreta etiquetas ni aplica una nueva correspondencia. Inventaría valores
literales completos, frecuencias, categorías y desenlaces por fuente; identifica
las columnas originales desde el informe de calidad y sus encabezados desde
la inspección estructural preservada. Los campos adicionales no proyectados
permanecen explícitamente desconocidos, sin reabrir los libros.

El diagnóstico distingue:

- Confirmación registrada, con criterio histórico todavía sin documentar.
- Categorías sospechoso/probable que no afirman confirmación, pero tampoco
  prueban ausencia de enfermedad.
- Descarte registrado para una fila, que no equivale a negativo radio-semana.
- Clasificación ausente/no mapeada, cuya confirmación permanece desconocida.

Se documenta el motivo mecánico de las banderas: `evaluate_eligibility` asigna
`epidemiological_eligibility_validated=False` y `prepare_records` asigna
`epidemiological_identity_validated=False`; la conjunción usada por Fase 5B no
puede validarse automáticamente con esas salidas. El diagnóstico localiza las
asignaciones mediante AST y conserva líneas/hashes. Cero banderas no es prueba
de que todos los registros rotulados confirmados sean incorrectos.

El responsable debe revisar la definición histórica de dengue, el diccionario de
evento, los valores literales del filtro y el criterio de confirmación aplicable.
No se impone laboratorio como única forma de confirmación: cualquier criterio
admitido, incluido nexo cuando corresponda, debe quedar documentado y referido
a su contexto histórico. La fuente 2022 se revisa por su identificador autorizado;
no se infiere confirmación ni año de observación desde nombres de archivo.

La revisión territorial reutiliza conteos de provincia/departamento de residencia
de Fase 4.3. Una concordancia total con La Rioja–Capital es compatible con el
filtro, pero no reconstruye qué columnas u operaciones se usaron manualmente.
Se requiere procedimiento, columnas/valores, fecha/operador, orden de filtros y
conciliación con la exportación previa. No se equipara establecimiento notificador
con residencia ni se decide residencia desde coordenadas.

## Cobertura y pendientes

Las propuestas reutilizan exactamente los intervalos candidatos por fuente,
política y tipo de fecha de Fase 4.3, con límites y observaciones de Fase 4.2.
Conservan `proposal_not_declaration`, confianza de completitud `none`, justificación
documental pendiente y materialización deshabilitada. Fuentes sin intervalo
elegible quedan sin propuesta fechada, con revisión de clasificación/universo
pendiente. Una ventana sin semana completa también queda identificada.

Para cada intervalo se detallan criterio temporal, criterio de confirmación por
validar, residencia propuesta, incertidumbres y celdas bloqueadas por pendientes.
Las capacidades se calculan sin asignar cero y no se suman sobre intervalos
superpuestos. El responsable puede aceptar/rechazar/corregir propuestas, pero
debe declarar fechas propias y documentar extracción, corte, filtros,
completitud, limitaciones y confianza. No se extiende ninguna ventana hasta
diciembre de 2024 por ser el límite configurado.

Un pendiente sin fecha conserva todo el período posible de su radio candidato;
si no tiene radio, mantiene alcance territorial amplio. Los pendientes por
identidad y elegibilidad se contabilizan con sus intersecciones y no se suman
entre celdas como registros únicos. Se concilian con Fase 4.3. No se eliminan
pendientes para habilitar ceros. Tampoco es obligatorio resolverlos todos si las
celdas afectadas permanecen desconocidas y fuera de los negativos autorizados.

La toma de muestra sigue siendo aproximación temporal, comparada con la política
estricta y la evidencia de demoras ya calculada; no se restan retrasos imputados.
La asignación geográfica aproximada ya fue aceptada por el proyecto. No se exige
certeza domiciliaria absoluta o nueva geocodificación: su incertidumbre se conserva
como limitación, sin presentar puntos de infección reales.

## Dossier, plantilla y habilitación futura

`decision_dossier.private.md` integra diagnóstico por fuente, clasificación 2022,
residencia, intervalos exactos candidatos, pendientes, decisiones y requisitos.
`decisions.template.private.json` deja sin completar responsable/firma, decisiones
por etiqueta, procedimiento territorial, fechas declaradas, evidencias, confianza
y autorizaciones. Los límites candidatos se incluyen únicamente como sugerencias:
`declared_start/end` permanecen null y `coverage_declarations` vacío.

Se distinguen dos rutas, sin modificar la configuración del Modelo A:

1. Experimento retrospectivo: decisiones epidemiológicas/territoriales documentadas,
   cobertura respaldada o escenario asumido expresamente autorizado, pendientes
   preservados, ambas clases suficientes en cortes cronológicos purgados,
   contexto censal retrospectivo reconocido y autorización posterior de entrenamiento.
2. Backtest operativo: además, disponibilidad histórica censal/territorial,
   maduración/disponibilidad de etiquetas en cada corte y respaldo punto en el
   tiempo para un baseline de persistencia; si no existe, abstenerse o usar el
   baseline de prevalencia del entrenamiento.

El Modelo A no usa rezagos: no se exige una historia de features epidemiológicas
que no forma parte de su entrada. Esto no elimina los requisitos de cobertura,
etiquetas y evaluación temporal ni valida automáticamente el contexto censal.
Una firma del documento no dispara procesamiento, negativos o entrenamiento.

Las salidas adicionales son inventario de clasificación agregado, revisión de
pendientes por claves opacas (sin nombres, documentos, domicilios o posiciones),
propuestas de cobertura, diagnóstico JSON, configuración, metadatos y manifiesto
SHA-256. El hash de la configuración del Modelo A demuestra su conservación.

Las pruebas ficticias cubren distinción de evidencia, banderas conservadoras,
alineación de registros, consistencia territorial, intersecciones de pendientes,
intervalos exactos y no autorizados, documentos externos ausentes, plantilla
sin firmar, reproducibilidad e integridad/permisos. La integración bloquea
explícitamente lectura de Excel, cálculo de features y entrenamiento.

## Etapa 7: validador independiente de consistencia

Versión `epidemiological-validator-0.7.0`, 20/10/2026. Se basa en la
[auditoría](epidemiological-data-quality-audit.md) y el
[contrato de clasificación/cobertura](epidemiological-labeling-and-coverage-contract.md).
La clasificación de reglas se incorpora como sección 8 del **mismo**
`decision_dossier.private.md` de 5B.1 y de su generador; no se crea otro dossier
ni se completan decisiones de la plantilla. La enmienda documental conserva
la huella anterior del dossier y actualiza sólo su entrada en el manifiesto
local, con un registro de la enmienda. No regenera diagnósticos ni datasets.

El paquete `ml/src/sigard_ml/official/epidemiological_validator/` ofrece:

- `validate_records(records)`: controles por fila de clasificación canónica y
  acreditación declarada, claves técnicas, repetición de IDs opacos, fechas,
  calendario y asignación espacial. No aplica correspondencias nuevas ni
  resuelve episodios; reutiliza vocabularios y parser/calendario existentes.
- `validate_week(cell)`: celda de cobertura de `coverage_panel`, cotejada con
  `coverage_policy.decide_observation`; comprueba procedencia, versión,
  parcialidad y pendientes sin materializar ceros.
- `validate_label(target)`: objetivo de `assumed_scenario` separado de la celda
  de origen; distingue positivo provisional, negativo experimental, cero
  heredado y desconocido, conservando los originales null.

Cada control devuelve `CheckResult(control_id, status, reason, field)`.
Los estados son `valido`, `advertencia`, `invalido` y
`pendiente_acreditacion`. **Válido significa consistencia técnica de ese control**:
un registro bien estructurado puede conservar advertencias y acreditaciones
pendientes. No existe una bandera global de aprobación sanitaria ni de aptitud
para entrenar. Las referencias se comprueban como metadatos; su contenido y
alcance no se acreditan automáticamente ni se abren archivos de respaldo.

### Ejecución sin datasets

Desde la raíz, con el entorno Python existente, este ejemplo completamente
ficticio permite ver el informe de un registro incompleto:

```powershell
'{"records":[{"source_id":"fictional_source","sheet_ref":"fictional_sheet","record_ref":"fictional_row"}]}' | .\ml\venv\Scripts\python.exe -B -m sigard_ml.official.epidemiological_validator
```

La CLI consume únicamente JSON por stdin y escribe JSON por stdout; no acepta
rutas ni guarda/modifica entradas. Admite las listas opcionales `records`,
`weeks` y `labels`. Conserva índices posicionales y no reproduce claves ni
valores de entrada en el informe. Códigos: 0 sin controles inválidos (puede
haber advertencias/pendientes), 1 con controles inválidos —como en el ejemplo—,
2 entrada JSON/esquema no utilizable. `training_authorized` siempre es falso.

Para usar la API, importar las tres funciones desde
`sigard_ml.official.epidemiological_validator`; reciben diccionarios con los
nombres de columnas de los módulos mencionados. Las fechas son objetos `date`
o cadenas en los formatos explícitos de `observed_dates.parse_reference_date`.
Las listas espaciales deben ser listas Python y los conteos/banderas deben
ser `int`/`bool`, con faltantes `None`; un adaptador posterior debe convertir
explícitamente `NaN`, `pd.NA`, escalares NumPy y arrays antes de invocar la API.

La entrada agrega `calendar_version` desde los metadatos del artefacto:
debe ser `ar-snvs-2020-2026-v1`, sin inferir ni migrar versiones históricas.
`validate_week` recibe además `registros_elegibles_provisionales` desde el panel
base, y `zero_policy` desde la configuración existente; no los deduce de
`casos_observados`. Para una clasificación declarada verificada, el adaptador
debe aportar `classification_evidence_ref` desde una decisión revisada. No se
infiere esa referencia desde el literal ni desde la inclusión exploratoria.

Se detectan inconsistencias de formato, claves, metadatos y calendario;
muestra anterior a síntomas es una señal de revisión. No se acredita el
significado clínico de fechas, el período autorizado, la jerarquía de selección
aplicable, las resoluciones del grupo completo ni el alcance de una autorización
experimental sólo por sus banderas. Esas comprobaciones requieren el contexto
y los validadores existentes en una futura integración autorizada.

### Pruebas y futura integración

```powershell
.\ml\venv\Scripts\python.exe -B -m pytest ml/tests/test_epidemiological_validator.py -p no:cacheprovider --basetemp=ml/.tmp/epidemiological-validator-unit
```

Los ejemplos de prueba son ficticios y cubren los ocho casos solicitados,
contradicciones de acreditación, trazabilidad, fechas alternativas, límites
anuales argentinos, cobertura declarada/comprobada y negativos experimentales.
Se cotejan entradas producidas en memoria por `classify_labels`,
`assign_record_weeks`, `review_episode_groups` y `decide_observation`.

Después de la aprobación correspondiente, un adaptador fuera del backend
podrá invocar estas funciones sobre las proyecciones autorizadas, conservar un
informe privado por índice/clave técnica y aplicar una política de bloqueo
expresamente aprobada. Para evidencia de cobertura se reutilizará
`coverage_policy.validate_evidence`; para resoluciones de identidad,
`episodes.apply_episode_resolutions` sobre el grupo completo; para negativos
experimentales, `assumed_scenario.validate_authorization` con su alcance exacto.
Ninguna llamada del validador cambia etiquetas o habilita entrenamiento.
La conexión al pipeline oficial queda pendiente de otra etapa.

Validación técnica de esta entrega: **64 pruebas nuevas y 301 de regresión,
365 aprobadas, sin fallos**. La regresión se ejecutó con:

```powershell
.\ml\venv\Scripts\python.exe -B -m pytest ml/tests/test_official_calendar.py ml/tests/test_official_contracts.py ml/tests/test_official_date_recovery.py ml/tests/test_official_coverage.py ml/tests/test_official_observed.py ml/tests/test_official_spatial.py ml/tests/test_official_epidemiology_review.py ml/tests/test_official_assumed_scenario.py -p no:cacheprovider --basetemp=ml/.tmp/epidemiological-validator-regression
```

No hubo entrenamiento ni pruebas de ajuste de Random Forest A/B. Todas las
fuentes y salidas utilizadas por las pruebas son ficticias y temporales.
`git diff --check` sobre los archivos versionados de esta entrega no informó
errores de espacios. La única lectura privada de esta etapa fue el dossier
preexistente y su manifiesto técnico, para la enmienda documental autorizada.

## Etapa 8: preflight de elegibilidad con datos ficticios

Versión `epidemiological-preflight-0.8.0`. El paquete
`ml/src/sigard_ml/official/epidemiological_preflight/` interpreta las salidas
de etapa 7 y los requisitos C1–C4/P1–P6 del contrato. Se consultaron también la
auditoría y la sección 8 del dossier existente. No se modificaron el dossier,
su plantilla, datasets, etiquetas, modelos ni pipelines oficiales.

El informe separa:

- **Consistencia técnica:** ausencia de controles inválidos de etapa 7 y
  coherencia entre claves de registros, semanas y objetivos. Reutiliza
  `validate_records`, `validate_week`, `validate_label` y `validate_targets`;
  no vuelve a definir clasificaciones, calendario, cobertura ni horizonte.
- **Investigación retrospectiva experimental:** requiere una decisión simulada
  explícita para ese uso y respaldos revisados P1–P6. P1/P2/P4/P5 pueden reconocer
  categorías, episodios, fechas y ubicaciones provisionales; P3 puede documentar
  el supuesto experimental, y P6 reconocer límites de disponibilidad histórica.
  No exige demostrar disponibilidad operativa para una interpretación retrospectiva.
- **Uso epidemiológico acreditado:** en la simulación exige además declaraciones
  de acreditación enlazadas a sus respaldos de clasificación, identidad y espacio,
  cobertura comprobada y evidencia de disponibilidad/maduración P6. Los negativos
  experimentales y la cobertura desconocida bloquean esta ruta.

Ambas rutas pueden devolver `eligible_simulation_only` o `blocked`.
`permitted_uses` contiene exclusivamente usos con prefijo `simulation_`.
**`training_authorized` y `evaluation_authorized` siempre son falsos**, incluso
si toda la evaluación ficticia resulta elegible. Una solicitud `train`,
`evaluate` u otra acción distinta de `inspect` bloquea ambas rutas sin ejecutarla.
Un código de salida cero tampoco es una autorización efectiva.

### Evidencias y decisiones simuladas

La API no abre archivos ni URLs. `SimulatedArtifact(content: bytes, sha256: str)`
contiene un documento JSON ficticio en memoria; el registro enlaza referencias
con esos objetos. Se verifica el SHA-256 de los bytes aportados y el contenido
estructural de la decisión, sin interpretar clínicamente los respaldos.
Un hash comprueba integridad, **no autenticidad institucional ni veracidad**.
Esta interfaz es un mecanismo de prueba; no reemplaza el dossier ni crea un
nuevo circuito institucional de aprobación.

`dataset_digest(bundle)` vincula la decisión con el contenido, orden y versiones
exactas del conjunto, incluidos territorio, fechas, etiquetas y referencias.
El conjunto contiene exactamente `data_kind="fictional"`, `dataset_id`,
`dataset_version` y listas no vacías de diccionarios `records`, `weeks`, `labels`,
con el contrato de etapa 7. `labels` agrega las claves de origen y objetivo
(`radio_censal`, `fecha_inicio_semana`, `fecha_inicio_semana_objetivo`) y
`apto_entrenamiento=False`, requeridas por `validate_targets`.
Se comprueba que etiquetas y bloqueos correspondan a sus celdas objetivo, sin
modificar sus valores. No se reconstruye exhaustividad ni se seleccionan filas.

Cada respaldo debe incluir `reference`, `simulation=True`, `dataset_sha256`,
`requirement` (P1–P6), `uses`, `review_state="reviewed"`, `reviewer_ref` y `basis`.
Cada decisión debe incluir `reference`, `simulation=True`, `dataset_sha256`,
`use` (`retrospective_experimental` o `epidemiological_accredited`),
`status="approved"`, `reviewer_ref`, `decided_on`, `rule_version`,
`validator_version`, `evidence_refs` (una referencia por P1–P6) y
`accepted_findings` (claves exactas `Finding.key` de los hallazgos revisados).
Son decisiones suministradas por el escenario ficticio, nunca generadas o
aprobadas por `run_preflight`. Un respaldo no revisado, una referencia suelta,
una huella diferente o una decisión para otro uso no bastan.

Las referencias de verificación declaradas deben resolver a los respaldos
revisados: `classification_evidence_ref` a P1, `identity_evidence_ref` a P2,
`verificacion_cobertura_ref` a P3 y `spatial_evidence_ref` a P5. El último campo
es metadato del adaptador ficticio; no se agrega a los datasets actuales.
Para un negativo experimental, `autorizacion_cobertura_ref` debe resolver a la
decisión experimental exacta. P3 documenta una asunción o una cobertura según
la ruta; aceptar la primera no acredita la segunda.

No se pueden exceptuar controles técnicos inválidos, clasificación/identidad
sin resolver, ausencia de fecha de referencia, radio ambiguo/no asignable u
objetivo desconocido. Las advertencias y pendientes revisables requieren una
aceptación explícita para cada hallazgo del conjunto exacto. La lista de
controles revisables está limitada a P1–P6; un control desconocido bloquea.
No se eliminan filas ni se imputan valores para obtener elegibilidad.
El informe conserva los resultados originales de etapa 7: `pending_evidence`
puede contener pendientes ya considerados por una **decisión simulada**.
Los bloqueos efectivos de cada ruta figuran en `eligibility[].blockers`.

### Ejecución y resultados

Desde Python, con el entorno existente:

```python
from sigard_ml.official.epidemiological_preflight import run_preflight

# fictional_bundle, simulated_artifacts y simulated_decision_refs son objetos
# ficticios construidos por el llamador con los contratos anteriores.
report = run_preflight(
    fictional_bundle,
    artifacts=simulated_artifacts,
    decision_refs=simulated_decision_refs,
    requested_action="inspect",
)
result = report.to_dict()
assert result["training_authorized"] is False
```

También existe una CLI JSON por stdin/stdout. Este ejemplo no usa datos y
devuelve bloqueo por conjunto incompleto (código 1):

```powershell
'{"bundle":{}}' | .\ml\venv\Scripts\python.exe -B -m sigard_ml.official.epidemiological_preflight
```

El objeto de entrada admite `bundle`, `artifacts`, `decision_refs` y
`requested_action`. En la CLI cada entrada de `artifacts` contiene `content`
(el documento JSON como cadena UTF-8) y `sha256`. No acepta rutas ni argumentos.
Salida: versión, consistencia técnica, controles superados, advertencias,
pendientes, bloqueos por uso y elegibilidades exclusivamente simuladas.
No reproduce registros, respaldos o identidades del revisor en el informe.
Códigos: 0 alguna ruta elegible sólo en simulación; 1 ninguna ruta elegible;
2 entrada JSON/esquema no interpretable.

Las nueve situaciones solicitadas se ejercitan con datos y evidencias
completamente ficticios en `ml/tests/test_epidemiological_preflight.py`:

```powershell
.\ml\venv\Scripts\python.exe -B -m pytest ml/tests/test_epidemiological_preflight.py ml/tests/test_epidemiological_validator.py -p no:cacheprovider --basetemp=ml/.tmp/epidemiological-preflight-focused
```

### Requisitos antes de una integración real

Falta la aprobación del responsable de los criterios P1–P6, el alcance y las
excepciones aplicables a cada ruta, más un adaptador autorizado que resuelva
decisiones reales del dossier y sus evidencias verificables. Debe autenticar
responsable/resolución y revisar el contenido; una bandera o huella no lo hace.
Se reutilizarán `coverage_policy.validate_evidence`, las resoluciones del grupo
completo de `episodes` y `assumed_scenario.validate_authorization` cuando
corresponda, con los permisos y alcances vigentes. También debe aprobarse el
protocolo de selección, cortes temporales, disponibilidad histórica y evaluación.
Este preflight no audita matrices de features ni ajusta/evalúa modelos.
La conexión a cualquier pipeline y la autorización efectiva de entrenamiento
siguen fuera de esta etapa. No se incorpora ningún respaldo epidemiológico nuevo.

Validación técnica de etapa 8: **423 pruebas aprobadas, sin fallos**: 58 nuevas
de preflight, 64 del validador de etapa 7 y 301 de regresión. Se repitieron los
ocho módulos de regresión detallados en etapa 7, con temporales ficticios bajo
`ml/.tmp/epidemiological-preflight-regression`. Se comprobó además la CLI como
proceso independiente: entrada vacía bloqueada, sin autorización efectiva.
No se ejecutó entrenamiento ni evaluación de Random Forest A/B. No se leyeron
datos oficiales ni se incorporaron respaldos epidemiológicos; sólo se consultó
el dossier existente y la documentación, junto con código y pruebas ficticias.

## Etapa 9: preparación controlada con fixtures

`sigard_ml.official.preparation_pipeline.run_preparation` conecta las etapas
7 y 8 con un adaptador en memoria. **Entrada → autorización externa → validación
→ preflight → decisión → informe agregado.** Versión
`controlled-epidemiological-preparation-0.9.0`.

Se revisaron los puntos de entrada existentes: la ingesta de `official.pipeline`,
`observed_pipeline.prepare_records`, cobertura/objetivos semanales y
`spatial_ml.pipeline.run_preparation`, además de los permisos de entrenamiento
y evaluación retrospectiva de A/B. El nuevo adaptador consume el bundle de
etapa 8 ya preparado; no reingiere, reclasifica ni reconstruye paneles/features.
La compatibilidad se comprueba con salidas ficticias de los componentes existentes.
Los puntos de entrada históricos y sus autorizaciones específicas no cambian.

### Autorización y ejecución

El llamador aporta un `SourceRegistry` externo al dataset. Se reutiliza su
control `AuthorizedUse.PROCESSING`, con una autorización del **extracto ficticio
en memoria**, no del libro epidemiológico original: `source_id=dataset_id`,
`source_version=dataset_version`, secciones virtuales `records`, `weeks`, `labels`
y `subset_ref=dataset_digest(bundle)`. Deben cumplirse las referencias y permisos
ya exigidos por `SourceAuthorization`. Su ruta absoluta es un localizador
ficticio que nunca se consulta; no se abre ni se verifica su existencia.
Esta correspondencia de secciones sirve sólo al contexto de fixtures.

Sin ese permiso o si cambia el conjunto, su versión o su huella, se devuelve
bloqueo antes de ejecutar validaciones epidemiológicas. No se construye el
registro desde banderas ni declaraciones del bundle. Autorizar procesamiento
no acredita clasificación, cobertura ni decisiones institucionales: esos
respaldos se comprueban por el preflight existente, exclusivamente en simulación.

```python
from sigard_ml.official.preparation_pipeline import run_preparation

result = run_preparation(
    fictional_bundle,
    registry=fixture_registry,
    artifacts=simulated_artifacts,
    decision_refs=simulated_decision_refs,
)
summary = result.to_dict()
assert summary["training_authorized"] is False
```

Los objetos del ejemplo siguen los contratos de etapa 8; la construcción
completa del contexto ficticio está en las pruebas de integración. El adaptador
toma una copia del bundle y llama **una sola vez** a `run_preflight`, que ya
ejecuta los validadores de etapa 7. No hay validadores duplicados ni parámetros
para suministrar resultados precalculados u omitir el preflight.

El uso solicitado por defecto es `epidemiological_accredited`, siempre limitado
a simulación. Elegir explícitamente `requested_use=EXPERIMENTAL` (constante del
preflight) permite comprobar una preparación retrospectiva ficticia sólo si
sus decisiones y respaldos la habilitan. No hay degradación automática del
uso acreditado al experimental cuando faltan evidencias.

### Decisión, bloqueos y límites

`prepared_simulation_only` significa que el contexto y la ruta elegida superaron
el control para esa fixture; `blocked` incluye los motivos concretos. El informe
agrupa controles superados, advertencias, pendientes y bloqueos por ID, estado,
motivo y campo, con su frecuencia. Conserva las advertencias/pendientes originales
del validador; los bloqueos efectivos corresponden al uso seleccionado. No
reproduce registros, claves individuales, referencias privadas ni contenido de
respaldos. El objeto Python conserva el informe de preflight para revisión.

Sólo se admite `operation=AuthorizedUse.PROCESSING`, que produce este informe
en memoria. Solicitudes de entrenamiento, evaluación o publicación se rechazan
antes del preflight, incluso si el registro de acceso declara esos usos.
`training_enabled`, `training_authorized`, `evaluation_authorized` y
`datasets_written` permanecen falsos. No se devuelve una matriz entrenable ni
se ofrece un callback o continuación hacia operaciones posteriores.

El procesamiento de datos reales permanece bloqueado. Antes de incorporarlo
deben aprobarse criterios y respaldos P1–P6, responsables/resoluciones y alcance
de acceso real, la correspondencia de procedencia entre fuentes y proyecciones,
y el protocolo temporal/experimental aplicable. El hash y el registro en memoria
no autentican decisiones institucionales. La futura conexión real deberá resolver
esas evidencias mediante los contratos existentes, sin sustituirlas por flags.
Esta etapa no altera las preparaciones ni los experimentos congelados A/B.

Pruebas del flujo completo, sin fuentes reales ni entrenamiento:

```powershell
.\ml\venv\Scripts\python.exe -B -m pytest ml/tests/test_official_preparation_pipeline.py ml/tests/test_epidemiological_preflight.py ml/tests/test_epidemiological_validator.py -p no:cacheprovider --basetemp=ml/.tmp/controlled-preparation-focused
```

Validación de etapa 9: **488 pruebas aprobadas, sin fallos**: 35 nuevas de
integración, 122 de etapas 7/8 y 331 de regresión. La regresión utilizó los ocho
módulos de etapa 7 más `ml/tests/test_official_spatial_ml.py`, con temporales
bajo `ml/.tmp/controlled-preparation-regression`. Se comprobaron autorización
previa, orden de ejecución sin validación duplicada, clasificación/cobertura
sin respaldo, conservación de desconocidos, bloqueo de operaciones, ausencia
de IO/modificaciones y compatibilidad con `attach_next_week_target`.
No se accedió a archivos epidemiológicos adicionales ni se entrenaron modelos.
