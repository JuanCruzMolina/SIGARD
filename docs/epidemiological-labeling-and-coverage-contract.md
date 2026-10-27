# Contrato de clasificación epidemiológica, episodios y cobertura

Etapa 6 · Versión documental 0.6.0 · 19/10/2026 · Rama `entrenamiento-ML`.
**Borrador para revisión del responsable. No autoriza preparación ni entrenamiento.**

Actualización técnica de etapa 7 (20/10/2026): el
[validador independiente](official-epidemiology-review.md#etapa-7-validador-independiente-de-consistencia)
comprueba consistencia de los estados ya existentes. No convierte las propuestas
P1–P6 en criterios epidemiológicos aprobados ni añade categorías a los datasets.
Los estados del informe de controles se distinguen de las clasificaciones y
etiquetas originales. La sección 8 del dossier 5B.1 clasifica reglas comprobables,
experimentales y pendientes; las decisiones institucionales siguen pendientes.

Etapa 8: el [preflight independiente](official-epidemiology-review.md#etapa-8-preflight-de-elegibilidad-con-datos-ficticios)
interpreta esos controles y decisiones **simuladas** por uso. Sus estados de
elegibilidad no acreditan los datos actuales ni autorizan entrenamientos o
evaluaciones reales; P1–P6 y su revisión institucional siguen pendientes.

Etapa 9: la [preparación controlada con fixtures](official-epidemiology-review.md#etapa-9-preparación-controlada-con-fixtures)
reutiliza autorización de acceso externa, validador y preflight para producir
un informe agregado. No convierte permisos de procesamiento ni elegibilidad
simulada en aprobación epidemiológica, y mantiene bloqueados los datos reales,
el entrenamiento y la evaluación efectiva.

Este contrato desarrolla la [auditoría de etapa 5](epidemiological-data-quality-audit.md).
Se contrastaron documentación y código local. No se abrieron originales, filas de
pacientes, derivados individuales, informes privados ni modelos; no se ejecutaron
pipelines. Los hallazgos sobre la entrega se atribuyen a esa auditoría, sin una
nueva verificación de datos. No se incorporan fuentes epidemiológicas adicionales.

Se usan tres estados: **comprobado en código/documentación**, **experimental** y
**propuesto, pendiente de validación**. Comprobar una regla informática no acredita
su validez epidemiológica. Las referencias R1–R9 permiten localizar el respaldo.

## 1. Definiciones epidemiológicas y alcance

- **Registro:** una fila de una fuente versionada. Puede representar una
  notificación, muestra o actualización; su significado requiere un diccionario.
- **Episodio epidemiológico:** unidad de enfermedad definida por el criterio
  histórico aplicable. Puede reunir varias notificaciones o muestras. Una fila,
  una persona y un episodio no son unidades intercambiables.
- **Clasificación registrada:** categoría obtenida del campo explícito de la
  fuente. El literal `confirmado` no demuestra confirmación clínica o de laboratorio.
- **Clasificación verificada:** categoría cuyo significado histórico y aplicación
  al registro están respaldados por evidencia revisada. No valida por sí sola
  identidad del episodio, ubicación, fecha ni cobertura.
- **Cobertura acreditada:** evidencia aceptada sobre qué evento, población,
  territorio, período, base temporal y circuito de vigilancia representa una
  extracción, con sus límites. No equivale a detección de todas las infecciones.
- **Etiqueta radio–semana:** resultado agregado bajo una definición de evento,
  episodio, fecha, territorio y cobertura explícitas; su valor y su grado de
  respaldo deben conservarse por separado.

La unidad analítica sigue siendo **radio censal–semana epidemiológica**. El MVP
`v0.1` estima cantidades asignadas sintéticamente para la semana siguiente. A/B
son experimentos separados de presencia provisional en `t+1`; no predicen cantidades
clínicamente verificadas. Se mantienen separadas observaciones agregadas de Capital,
asignaciones sintéticas y predicciones. Este documento no cambia esos objetivos. [R1,R8]

## 2. Reglas actuales comprobadas y reglas experimentales

### C1. Clasificación y elegibilidad

**Comprobado:** `classification.py::classify_labels` aplica correspondencias
literales completas sobre `classification_label`, normalizando Unicode, mayúsculas
y espacios. Las categorías son `confirmado`, `probable`, `sospechoso`, `descartado`
e `indeterminado`; un valor no mapeado queda indeterminado. No busca palabras en
otras columnas. Las correspondencias versionadas son reglas técnicas, sin
equivalencia clínica histórica acreditada. [R2]

**Experimental:** la política exploratoria inicial incluye `confirmado`
provisionalmente y excluye probable/sospechoso/descartado según el escenario.
La conservadora deja las categorías no descartadas para revisión. Excluir del
análisis no demuestra ausencia de enfermedad. `evaluate_eligibility` conserva
`epidemiological_eligibility_validated=False`; esa bandera no prueba que una
clasificación registrada sea falsa. [R2,R3]

### C2. Identificación de filas y episodios

**Comprobado:** la clave técnica es `source_id + sheet_ref + record_ref`; identifica
una fila en una versión, no un episodio estable. `event_ref` deriva del hash del
identificador normalizado, con alcance global de la entrega; sigue siendo privado.
Un identificador único queda `singleton_provisional`; repetidos o ausentes quedan
pendientes y no aportan al conteo principal sin resolución aplicable. [R2]

`episodes.py::apply_episode_resolutions` exige cubrir todo el grupo revisado,
`episode_ref`, `countable`, `evidence_ref` y un representante por episodio.
Permite separar episodios dentro de un grupo; conserva las filas no representantes.
No escoge automáticamente la primera, última o más favorable. Resolver IDs ausentes
requiere un contrato adicional. Compartir coordenadas no deduplica.
`prepare_records` mantiene `epidemiological_identity_validated=False`, incluso
cuando existe una resolución técnica de identidad. [R2,R3]

La auditoría informa repetidos pendientes y no informa resoluciones manuales en
el resumen revisado. La ausencia de filas exactamente duplicadas no descarta
varias notificaciones de un mismo episodio; un ID único tampoco lo acredita. [R1]

### C3. Tiempo, espacio y cobertura

**Comprobado:** existen política estricta de inicio de síntomas y política ampliada
con prioridad síntomas → consulta médica → muestra → notificación. Se conserva el
tipo de fecha, la aproximación y los rechazos. La asignación espacial conserva
candidatos e incertidumbre; bordes y múltiples coincidencias no eligen un radio
arbitrariamente. El objetivo se busca por radio y fecha exacta `t + 7 días`, sin
saltar huecos. Los pendientes bloquean ceros en las celdas que podrían afectar. [R4–R6]

El código separa declaraciones y verificaciones de cobertura. Puede representar
`cero_comprobado_bajo_reglas` o `cero_declarado_provisional`, según política y
respaldo. **La capacidad implementada no significa que existan ceros verificados
en la entrega:** la auditoría no acredita cobertura aceptada ni negativos
verificados en A/B. `objetivo_valido=true` significa etiqueta conocida, no
validación epidemiológica. [R1,R6]

### C4. Justificación y límite de la ventana de 2024

**Experimental:** la ventana de semanas objetivo completas **07/01/2024–08/06/2024**
proviene de una autorización de investigación sobre el universo listo congelado,
263 radios, política ampliada y fuente técnica `delivery_2024_2026`.
No procede de una demostración de vigilancia continua. [R1,R7]

`materialize_labels` sólo agrega `cero_asumido_experimental` donde la celda objetivo
existe, su conteo original es desconocido, no hay pendientes posibles y la semana
es completa y autorizada. Conserva los null de los conteos originales. La auditoría
informa que los negativos usados por A/B son asumidos. No se extiende el permiso
a todo 2024 ni a otras fuentes por su nombre. [R1,R7]

Las semanas objetivo de A/B permanecen: entrenamiento 07/01–02/03, validación
10/03–04/05 y prueba 12/05–08/06/2024; se purgan los objetivos iniciados el 03/03
y 05/05. Estas divisiones no justifican cobertura y no se modifican aquí. [R8]

## 3. Reglas propuestas pendientes de validación y evidencia necesaria

Las propuestas P1–P6 son especificaciones para revisión, **no instrucciones para
reclasificar los datos actuales ni aprobaciones institucionales**. La política
técnica optativa P2 descrita abajo implementa indicios y resoluciones controladas,
sin aplicarlos a datos reales en esta entrega. No se afirma
que los campos necesarios estén disponibles. Su existencia y significado deben
acreditarse mediante documentación o una revisión futura expresamente autorizada.

### P1. Clasificación respaldada por fuente y período

**Caso confirmado verificable — pendiente.** Requerir: evento identificado,
definición de caso vigente en el período, columna y clasificación original,
criterio de confirmación aplicado y referencia de evidencia que permita comprobar
su aplicación. Si el criterio admite laboratorio, documentar método, resultado,
fechas y vínculo con el episodio cuando corresponda. Si admite criterio clínico
o nexo epidemiológico, documentar los requisitos y el respaldo correspondiente.
No se exige laboratorio como única vía ni se acepta una palabra como prueba.
No se fija aquí ningún umbral clínico o de laboratorio. [R3]

**Caso sospechoso o probable respaldado — pendiente.** Mantener ambas categorías
separadas. Requerir definición histórica específica, campo explícito y evidencia
de los requisitos aplicables, con fecha/estado de clasificación. No promover
automáticamente un sospechoso a probable, ni probable a confirmado. Si sólo
consta el literal, informar «clasificación registrada sin criterio acreditado».

**Registro con confirmación provisional — justificable como estado de trabajo.**
El campo autorizado está mapeado a `confirmado`, pero falta verificar el criterio
o su aplicación. Conservar origen, versión de correspondencia y motivo pendiente.
Su inclusión exploratoria continúa siendo una decisión separada; no habilita
contarlo como episodio verificado ni presentarlo como confirmado clínicamente.

**Registro sin clasificación suficiente — justificable como estado de trabajo.**
Campo ausente, etiqueta no mapeada, evento incierto o información contradictoria
sin resolución. Conservar el motivo y dejar pendiente su uso como positivo.
No asignar descarte ni negativo por falta de información. Un descarte registrado
también requiere contexto para validarse y nunca demuestra un cero radio–semana.

**Evidencia para aprobar P1:** matriz privada por fuente/período con evento,
columna original, etiqueta completa, categoría propuesta, definición histórica
con localizador, criterio aplicable, evidencia disponible/faltante y decisión
del revisor. Cada equivalencia histórica debe justificarse por separado,
especialmente la fuente 2022 señalada por la auditoría. La matriz no debe inventar
equivalencias entre años ni inferir el evento desde el nombre de un archivo. [R1,R3]

### P2. Episodios frente a notificaciones y muestras

Implementación técnica optativa: `official/episodes.py::principal_episode_review`,
política `principal-episode-review-1`. Las categorías `possible_distinct`,
`possible_duplicate` e `indeterminate` no autorizan contar ni fusionar registros.
Compara únicamente fechas seleccionadas por síntomas → muestra y referencias
espaciales existentes, con calidad/comparabilidad explícitas; sin umbrales clínicos.
Compartir domicilio no se consulta y compartir posición no demuestra identidad.

Procedimiento: inspeccionar el resultado privado y obtener el alcance con
`episode_decision_digest(review, record_keys=...)`. El revisor autorizado documenta
`reference`, `reviewer_ref`, `authorization_ref`, `basis`, `criterion_ref`,
`criterion_version`, `criterion_status="approved"`, `status="approved"`,
`policy_version`, `records_sha256`, `decided_on`, `available_on` y `resolutions`.
Las resoluciones conservan `record_key`, `episode_ref`, `countable`, `evidence_ref`
del mecanismo existente, con la referencia de esa decisión. Deben cubrir el grupo
completo y cada episodio en una misma decisión, con un representante explícito.
La fecha de disponibilidad no puede anticipar la decisión o los registros conocidos.

Volver a invocar con `decisions=[...]` permite `reviewed_distinct` o
`reviewed_same_episode`; una revisión parcial, sin criterio aprobado, posterior
al corte o para otros metadatos se rechaza. Los cambios de clasificación, fechas
o calidad requieren revisar nuevamente el alcance. No se autentican firmas:
el llamador debe aportar exclusivamente decisiones y criterios reales cuya
autorización/evidencia haya comprobado el custodio. El software no los crea.
`episode_count_summary` exporta sólo conciliación agregada para el adaptador
principal; pendientes implican conteo exacto null. La selección del alcance
elegible y su asignación radiosemana dependen de P1/P4/P5, no de este indicio.
El recorrido histórico predeterminado y sus artefactos permanecen congelados.

**Pendiente:** acreditar si el identificador representa persona, evento,
notificación, muestra o actualización, su alcance entre fuentes y si puede
cambiar o reutilizarse. Identificadores distintos podrían pertenecer al mismo
episodio; uno repetido podría corresponder a episodios distintos.

Se necesitaría un diccionario de identificadores y relaciones entre notificaciones,
muestras y episodios, más el criterio epidemiológico para distinguir continuidad,
actualización y nuevo episodio. Las fechas pueden ayudar a revisar, pero no
autorizan una ventana automática de deduplicación. No se proponen cantidades de
días, reglas por domicilio/coordenadas ni agrupación por nombres/documentos.

**Evidencia para aprobar P2:** procedimiento revisado, alcance entre fuentes,
referencias privadas de decisiones y conciliación agregada de filas, grupos,
episodios resueltos y pendientes. El responsable deberá justificar el representante
y los conflictos de clasificación/fecha sin eliminar historia. Si no hay respaldo,
seguir informando registros provisionales y episodios no identificables. No se
revisarán identidades individuales en esta etapa. [R2,R3]

### P3. Cobertura epidemiológica por período y territorio

Se deben distinguir expresamente estos estados:

1. **Presencia registrada:** existen registros incluidos bajo una política.
   Puede coexistir con cobertura desconocida y pendientes; no garantiza un total
   completo ni casos verificados.
2. **Ausencia de registros:** no se encontraron registros incluidos en el alcance
   consultado. Es un resultado de observación; por sí solo deja la etiqueta
   epidemiológica desconocida.
3. **Ausencia verificada bajo vigilancia con cobertura acreditada — pendiente en
   los datos actuales:** no hay episodios elegibles registrados, la semana y el
   territorio están respaldados, las reglas fueron revisadas y ningún pendiente
   relevante puede cambiar la celda. El cero representa ausencia según ese sistema,
   evento y corte; no ausencia universal de infecciones.
4. **Información desconocida:** faltan cobertura, clasificación, identidad, fecha
   o ubicación suficientes para decidir. Mantener null; no equivale a negativo.

**Evidencia para aprobar P3:** documentar sistema y evento vigilado, población y
territorio representados, establecimientos/canales incluidos y omitidos, intervalo
exacto, campo temporal de extracción, filtros, fecha de corte y procedimiento de
selección. Aportar respaldo de continuidad de notificación, interrupciones,
demoras y maduración, completitud de la extracción y límites de subregistro.
La base territorial debe distinguir residencia del establecimiento notificador.
Conciliar lo extraído con un control de completitud documentado y autorizado,
sin presumir que ese control ya existe. [R3,R6]

El responsable debe justificar qué significa «suficientemente completo» para el
uso académico elegido y con qué controles lo acepta; no se inventa un porcentaje
mínimo. La resolución tendrá alcance por intervalo, radios y política de fechas.
Una extracción por notificación no acredita automáticamente cobertura por síntomas
o muestra. Fechas extremas, grilla completa, matriz sin NaN o presencia de ambas
clases no acreditan completitud.

Una semana parcial no habilita cero. Un pendiente sin fecha puede afectar todas
las semanas posibles de su radio; sin radio, todos los radios de su semana; sin
ambos, toda la grilla. No se suman esos indicadores como episodios únicos. Pueden
quedar pendientes si sus celdas siguen desconocidas y fuera de los negativos;
no se eliminan para obtener ceros. Los ceros declarados o asumidos conservan su
condición separada, aunque se apruebe continuar un experimento. [R6,R7]

### P4. Fechas epidemiológicas y faltantes

**Mantener las políticas comprobadas, con interpretación explícita:**

- `symptom_onset`: inicio consignado de síntomas; referencia estricta.
- `consultation_on`: atención médica; referencia alternativa, no inicio confirmado.
- `sample_on`: obtención de muestra; fecha de un procedimiento, no necesariamente
  del comienzo de enfermedad ni de confirmación.
- `notified_on`: notificación al sistema; no acredita cuándo el registro estuvo
  disponible para SIGARD ni la fecha de los síntomas.

La prioridad ampliada expresa selección técnica de una referencia utilizable;
no demuestra equivalencia epidemiológica de esas fechas. Una fecha anterior
rechazada por formato, corte o período deja motivo trazable. Sin referencia
válida, no imputar semana, fecha promedio, año del archivo ni retraso estimado.
Conservar el pendiente, salvo exclusión independiente ya justificada. Las fechas
administrativas no sustituyen a las clínicas. [R4]

**Evidencia para aprobar P4:** significado de columnas por fuente, regla temporal
elegida para el objetivo, diagnósticos agregados de faltantes, demoras y cambios
de semana. Las muestras anteriores a síntomas consignados requieren revisión;
no se corrigen ni invalidan clínicamente por automatismo. La auditoría informa
que la recuperación efectiva provino de muestra y no permite conocer el inicio
real de los recuperados. [R1]

Preservar `ar-snvs-2020-2026-v1`, semanas domingo–sábado, con fecha de inicio y
versión del calendario. SE1/2024 es 31/12/2023–06/01/2024. No sustituir por ISO ni
extrapolar años sin respaldo. El calendario no amplía el período de análisis
01/01/2020–31/12/2024; las semanas que lo intersectan parcialmente siguen parciales.
No reinterpretar las claves históricas sin su versión. [R4]

### P5. Confiabilidad espacial para radios

**Pendiente para atribución epidemiológica verificada:** documentar si la ubicación
es residencia, notificación u otro lugar; su vigencia respecto del episodio;
procedencia y método de geocodificación, CRS confirmado, precisión e incertidumbre;
versión y adecuación temporal de la cartografía y criterio territorial de selección.
Una coincidencia interior única es un control geométrico, no evidencia de domicilio
ni lugar de infección. [R5]

**Evidencia para aprobar P5:** procedimiento espacial revisado y diagnóstico
agregado que permita decidir si la incertidumbre puede cambiar el radio.
No fijar un margen en metros sin respaldo. Bordes, múltiples candidatos y ubicaciones
no asignables requieren decisión documentada o permanecen sin asignación validada.
El proyecto ya aceptó candidatos aproximados para investigación retrospectiva;
esa decisión se conserva con incertidumbre y no se eleva a precisión real.
No exige aquí nueva geocodificación ni certeza domiciliaria absoluta. [R3,R5]

### P6. Disponibilidad histórica para Machine Learning

**Pendiente:** para cada variable distinguir fecha del hecho, período observado,
fecha de llegada/publicación, revisiones y versión disponible al cierre del origen
`t`. Sólo podría entrar como predictor la información efectivamente disponible
entonces. Para etiquetas, definir por separado el corte de seguimiento y su
maduración: pueden conocerse después de `t`, pero no entrar en sus predictores.

A usa superficie, población, densidad, número de vecinos y tres variables de
calendario del origen. B agrega cuatro presencias binarias en `t−1…t−4` y cuatro
indicadores de faltante. Son presencias experimentales, no conteos de pacientes.
No usa coordenadas ni metadatos de cobertura como predictores. La reconstrucción
actual de fechas pasadas no acredita que sus registros se conocieran en `t`. [R8]

**Evidencia para aprobar P6:** versiones y fechas de disponibilidad de datos
censales/cartográficos y agregados autorizados de llegada/revisión de registros y
clasificaciones por corte. Si no existen, mantener uso retrospectivo declarado;
no inventar disponibilidad ni un retraso fijo. NaN permanece desconocido y las
coordenadas sintéticas quedan sólo para visualización. [R1,R8]

## 4. Registro de evidencia y aprobación

**Propuesto:** reutilizar el dossier y la plantilla privados existentes de Fase
5B.1; no generar otro circuito de aprobación ni completarlos automáticamente.
Cada decisión P1–P6 debería registrar:

- ID de criterio, fuente/versiones y período/territorio/política a los que aplica.
- Regla evaluada y referencia documental con sección o localizador preciso.
- Estado: pendiente, aprobada, rechazada o no aplicable con motivo; evidencia
  faltante y límites de la conclusión.
- Responsable de la revisión, fecha, resolución y versión de la regla aprobada.
- Referencias privadas a respaldos y sus huellas cuando corresponda, sin datos
  individuales en documentación pública. Un hash acredita integridad, no verdad.

Para P3 ya existe el mecanismo `coverage_verifications`: exige referencia de
resolución, residencia como base territorial, revisión de elegibilidad, identidad,
fechas, alcance territorial y asignación espacial, y archivos privados con huellas.
No reemplaza la revisión del contenido de esa evidencia. Una firma sola no
materializa etiquetas ni autoriza entrenar. [R3,R6]

## 5. Limitaciones de los datos actuales

Según la auditoría de etapa 5, siguen sin acreditarse un subconjunto de positivos
verificados, la unidad epidemiológica de todos los identificadores, la cobertura
necesaria para negativos y la disponibilidad histórica de predictores/etiquetas.
Persisten fechas no utilizables o aproximadas, grupos de identidad pendientes y
ubicaciones con CRS, significado o procedencia sin confirmar. No se puede resolver
su causa a partir de los agregados revisados. [R1]

El universo procesado es un universo de trabajo, no el universo epidemiológico
definitivo. La conciliación con originales continúa suspendida: este contrato
no la reactiva ni autoriza incorporar fuentes. El dossier puede documentar lo
desconocido sin reabrir esos archivos. [R9]

La exclusión de objetivos desconocidos selecciona la población evaluada. La
prueba de A/B ya examinada abarca pocas semanas y radios dependientes; sus métricas
no validan epidemiología ni constituyen confirmación independiente para el futuro.
Una puntuación no calibrada no es probabilidad verificada de infección. [R1,R8]

## 6. Decisiones pendientes del responsable del proyecto

1. Designar quién revisará los criterios epidemiológicos y su evidencia; aprobar,
   corregir o dejar pendiente cada correspondencia histórica P1, incluida 2022.
2. Acreditar el significado de los identificadores y el criterio de episodio P2;
   decidir qué puede resolverse y qué seguirá como registro provisional.
3. Precisar el evento, población, territorio y definición de completitud P3;
   aceptar únicamente intervalos y radios respaldados. Si se mantiene un escenario
   asumido, reconocerlo como experimento separado, sin acreditar negativos.
4. Elegir y justificar el objetivo temporal: síntomas estrictos o referencia
   ampliada con aproximación; aceptar sus límites y los pendientes P4.
5. Definir el alcance espacial admisible P5: aproximación retrospectiva o
   atribución epidemiológica respaldada, con manejo de ambigüedades.
6. Definir el alcance futuro P6: investigación retrospectiva o backtest operativo;
   identificar los respaldos faltantes y autorizar por separado cualquier acceso
   adicional necesario. Acordar otro período de evaluación aún no examinado.

**Estado de esta versión:** estas decisiones siguen pendientes. Redactar este
contrato no las resuelve ni renueva permisos experimentales anteriores.

## 7. Condiciones mínimas antes de avanzar

### Para autorizar otra preparación de etiquetas

- Revisión explícita de este contrato y registro de decisiones P1–P6, con alcance,
  responsable, evidencia y excepciones reconocidas. Lo no acreditado sigue pendiente.
- Definiciones versionadas de clasificación, episodio, fechas y geografía; criterio
  de cobertura respaldado para cualquier cero verificado. Las celdas afectadas
  por pendientes conservan desconocido cuando no haya resolución suficiente.
- Objetivo y unidad aprobados: no confundir presencia experimental, conteos de
  registros, episodios verificados y conteos sintéticos.
- Autorización específica de preparación con entradas ya autorizadas y versiones
  fijadas. Una necesidad de nuevas fuentes no permite leerlas automáticamente;
  la conciliación suspendida requiere otra indicación explícita. [R9]
- Plan de conservación: fuentes inmutables, destinos nuevos privados en
  `data/interim/` y, cuando estén listos para consumo, `data/processed/`, sin
  sobrescribir etiquetas/modelos previos. Procedencia, período, unidad, versiones,
  condición real/provisional/sintética/asumida y conciliación agregada trazables.

### Para autorizar un futuro entrenamiento

- Revisar primero el resultado de esa preparación; aprobar una autorización de
  entrenamiento independiente. No cambiar banderas de aptitud por conveniencia.
- Para afirmar validación epidemiológica, acreditar positivos, episodios y
  cobertura de negativos. Un nuevo experimento con etiquetas provisionales/asumidas
  requiere permiso propio y mantiene esos límites; no satisface esta acreditación.
- Para afirmar backtest operativo, acreditar disponibilidad en cada origen y
  maduración de etiquetas. Sin ese respaldo sólo cabe interpretación retrospectiva.
- Congelar protocolo temporal, reglas de faltantes, variables, baselines temporales
  simples y métricas antes de evaluar; transformaciones ajustadas sólo en
  entrenamiento, sin partición aleatoria ni información futura. Preservar semillas
  explícitas y ejecución de ML fuera del backend.
- Justificar soporte de clases y cantidad de semanas, considerando dependencia
  espacial/temporal. Acordar evaluación independiente en otro período no examinado;
  no reutilizar la prueba actual como confirmación independiente. [R1,R8]

**Siguiente etapa recomendada, sólo tras revisión:** completar la trazabilidad de
decisiones y un validador de su estructura con datos ficticios, aprovechando la
plantilla existente. Debe detectar falta de evidencia, alcance o versión sin leer
pacientes, generar etiquetas ni entrenar. Sólo después evaluar una preparación
nueva y expresamente autorizada. No se implementa ese validador en esta etapa.

## Referencias locales y alcance de la comprobación

- **R1:** [Auditoría de etapa 5](epidemiological-data-quality-audit.md), dictamen,
  hallazgos agregados, ventana 2024 y riesgos. Sus E8–E10 respaldan los hallazgos
  de datos citados aquí; esos informes privados no se reabrieron.
- **R2:** [Panel observado](official-observed-panel.md);
  [`classify_labels`](../ml/src/sigard_ml/official/classification.py),
  [`evaluate_eligibility`](../ml/src/sigard_ml/official/eligibility.py),
  [`review_episode_groups` / `apply_episode_resolutions`](../ml/src/sigard_ml/official/episodes.py),
  [políticas predeterminadas](../ml/src/sigard_ml/official/observed_settings.py) y
  [`prepare_records`](../ml/src/sigard_ml/official/observed_pipeline.py).
- **R3:** [Revisión epidemiológica y plantilla 5B.1](official-epidemiology-review.md),
  evidencia histórica, territorio y condiciones de habilitación.
- **R4:** [Fechas](official-date-recovery.md),
  [`select_reference_date` / `assign_record_weeks`](../ml/src/sigard_ml/official/observed_dates.py),
  [calendario argentino](official-calendar.md) y
  [`Calendar` / `VERIFIED_YEARS`](../ml/src/sigard_ml/official/calendar_rules.py).
- **R5:** [Geografía](official-geography.md) y
  [`assign_coordinates`](../ml/src/sigard_ml/official/spatial_assignment.py).
- **R6:** [Cobertura](official-coverage.md),
  [`validate_evidence` / `decide_observation`](../ml/src/sigard_ml/official/coverage_policy.py),
  [`pending_counts`](../ml/src/sigard_ml/official/observed_panel.py) y
  [`attach_next_week_target`](../ml/src/sigard_ml/official/weekly_targets.py).
- **R7:** [Escenario asumido](official-assumed-scenario.md) y
  [`materialize_labels`](../ml/src/sigard_ml/official/spatial_ml/assumed_scenario.py).
- **R8:** [Contrato de datos](data-contract.md), [Modelo A](official-spatial-research.md),
  [Modelo B](official-spatial-model-b.md),
  [disponibilidad temporal](official-temporal-feasibility.md),
  [`validate_design`](../ml/src/sigard_ml/official/spatial_ml/research_training.py) y
  [`validate_candidate`](../ml/src/sigard_ml/official/spatial_ml/research_model_b.py).
- **R9:** [Conciliación suspendida y alcance autorizado](official-selection-reconciliation.md).

La lectura de código comprueba comportamiento implementado; no se ejecutaron
pruebas nuevas ni se certificó evidencia clínica. La aprobación humana de las
propuestas y de su respaldo sigue pendiente. Los permisos históricos descritos
en documentos de fases anteriores no autorizan acciones en esta entrega.

Asistencia de redacción: skill local `scientific-writing`, aplicada a procedencia
y separación entre evidencia y propuesta. Referencia procedimental ya citada en
la auditoría: Kassis, T., Agarwal, V., He, Y., Patel, D., & Brueckner, A. M. (2026).
[Scientific Agent Skills: A Library of Procedural Knowledge for Research Agents](https://doi.org/10.48550/arXiv.2609.00065).
Se conserva como referencia de método, sin nueva consulta externa ni uso como
evidencia epidemiológica.
