# Preparación epidemiológica del próximo entrenamiento

20/10/2026 · Rama `entrenamiento-ML` · Propuesta para revisión humana.
**No autoriza accesos, nuevas etiquetas, procesamiento real ni entrenamiento.**

Actualización 26/10/2026: este dossier conserva los requisitos del objetivo
epidemiológico acreditado. No bloquea la modalidad separada
`provisional_aggregate_experiment`, autorizada por la declaración expresa del
responsable para agregados de las cinco entregas SISA y uso experimental local.
V1 se ejecutó bajo ese alcance, sin resolver ni acreditar P1–P6, sin ceros nuevos
y sin habilitar producción. No se requieren nuevas respuestas del responsable
para esa ejecución. Ver [estado y límites del principal V1](principal-count-forecasting.md#principal-v1-experimental-autorización-del-26102026).

## Decisión que necesitamos tomar

Antes de otro entrenamiento hay que acordar qué evento y episodio representa
un positivo, y qué extracción permite interpretar una celda vacía como negativo
bajo vigilancia. Hoy no está acreditado ninguno de esos dos extremos. El primer
paso es designar al responsable de los registros y solicitar documentación de
definiciones y extracción; no volver a ejecutar las auditorías. [E1–E4,E6,E9]

La matriz de resolución se incorporó como **sección 9 del dossier existente**
`data/interim/official/epidemiology_review_05b1_v1/decision_dossier.private.md`.
Ese es el registro único de P1–P6. Este plan organiza acciones y condiciones;
no sustituye el dossier ni completa `decisions.template.private.json`.
Los responsables propuestos abajo son funciones a designar, no aprobaciones
institucionales existentes. Las seis decisiones siguen pendientes.

## 1. Condiciones actuales y evidencia utilizable

- **Ámbito operativo aprobado el 23/10/2026:** el principal adopta los 256 radios
  de `la-rioja-46014010-256-v1`, con grafo inducido y configuración propia.
  Ver [adopción territorial](principal-city-boundary.md#adopción-operativa-del-23102026).
  Esta decisión no completa P5 epidemiológico ni disponibilidad P6; el maestro
  original y A/B permanecen en 263, sin reasignar geocodificaciones aproximadas.
- **Comprobado técnicamente:** cartografía de 263 radios, calendario
  `ar-snvs-2020-2026-v1` domingo–sábado, trazabilidad de campos, tratamiento
  explícito de desconocidos y objetivos exactos t+1. La cartografía validada
  geométricamente no acredita residencia ni lugar de infección. [E1,E5,E8]
- **Documentado como experimental:** positivos provisionales, negativos
  `cero_asumido_experimental`, fechas alternativas y ubicación aproximada.
  La ventana objetivo 07/01/2024–08/06/2024 fue autorizada sobre un universo
  listo congelado; no demuestra vigilancia continua ni abarca todo 2024. [E2,E7]
- **Evidencia insuficiente:** significado clínico de las equivalencias históricas,
  unidad de episodio, verificación de cobertura, rol/CRS/procedencia espacial y
  disponibilidad histórica de registros y contexto censal. No se puede acreditar
  un subconjunto clínico ni negativos verificados desde los agregados. [E1,E3–E9]
- **Decisiones pendientes:** P1–P6, responsables y resoluciones por fuente,
  período, territorio, política y uso. La plantilla sigue sin completar;
  aprobación técnica, permiso de acceso y aprobación epidemiológica son actos
  distintos. Validador, preflight y preparación controlada de etapas 7–9
  trabajan con fixtures y no habilitan datos reales por aprobar pruebas. [E2,E3]
- **Resultados existentes:** A/B y robustez son retrospectivos, exploratorios
  y con prueba ya consultada. B mejora discriminación, con más falsos positivos
  y peor error probabilístico de prueba; no justifica resolver etiquetas,
  elegir criterios ni acreditar cobertura por su rendimiento. [E10,E11]

El objetivo del próximo estudio debe aprobarse explícitamente: presencia de
episodios bajo vigilancia, presencia de registros o conteos. A/B clasifican
presencia provisional en t+1; el MVP estima cantidades asignadas sintéticamente.
No son objetivos intercambiables ni se cambia ninguno en esta fase. [E2]

## 2. Evidencia necesaria y orden de acciones

1. **Designar interlocutores y fijar alcance (P1/P3).** El responsable del
   proyecto identifica quién custodia los registros y quién puede confirmar
   criterios epidemiológicos y extracción. Solicitar, sin registros nominales,
   diccionario de eventos/campos, definiciones históricas y descripción de
   extracción. Producto esperado: referencias documentales por fuente/período
   y designación del revisor; si no existen, registrar esa ausencia en el dossier.
2. **Cerrar la semántica de clasificación (P1) y episodios (P2).** Completar
   en el dossier las equivalencias de cada literal, contexto histórico y
   evidencia de aplicación; priorizar la discrepancia documentada de 2022.
   Acreditar si la fila es notificación, muestra o actualización y el alcance
   de sus identificadores. Producto: criterios aprobados y excepciones,
   incluyendo qué seguirá provisional/desconocido. No implementar deduplicación.
3. **Acordar tiempo y territorio (P4/P5).** El referente epidemiológico y los
   custodios de campos/geografía documentan referencia temporal del objetivo,
   significado de las ubicaciones, cartografía y límites admisibles. Producto:
   políticas versionadas con manejo de contradicciones/ambigüedades; conservar
   las aproximaciones aceptadas sólo para el uso que efectivamente respalden.
4. **Delimitar cobertura y negativos (P3).** Con las definiciones anteriores,
   el responsable de extracción identifica establecimientos/canales incluidos
   y omitidos, población/residencia, períodos, cortes y filtros. Aporta controles
   de completitud, interrupciones, revisión de atrasos y pendientes. Producto:
   resolución por territorio/intervalo/base temporal, con evidencia y límites;
   no basta firmar los extremos observados o aceptar la ventana experimental.
5. **Reconstruir disponibilidad (P6).** El custodio del sistema y de los datos
   territoriales identifica publicaciones, snapshots, llegada/actualización y
   maduración. Producto: inventario por variable y corte que separe disponible,
   reconstruida retrospectivamente y desconocida. Si no puede acreditarse,
   limitar explícitamente la interpretación a retrospectiva.
6. **Revisar preparación y evaluación propuestas.** El responsable científico
   acuerda población, objetivo, desconocidos, período reservado y comparabilidad
   con A/B. Sólo después se solicita autorización específica de preparación
   sobre entradas y versiones definidas; entrenamiento requiere otro acto.

Las solicitudes documentales de P1–P6 pueden avanzar juntas. La aceptación de
cobertura/negativos depende de conocer previamente el evento, episodio, fechas
y territorio; el entrenamiento no es una forma de resolver esas decisiones.
No se exige resolver todos los pendientes: sí delimitar y conservar desconocidas
las celdas afectadas, sin quitarlas para producir ceros. [E2,E3,E6]

## 3. Clasificación, episodios y etiquetas: criterios a aprobar

**Clasificación por fuente y período (P1).** Para confirmado verificable se
necesitan evento, definición histórica, columna/valor original, criterio
admitido y respaldo de su aplicación al episodio. Cuando corresponda laboratorio,
documentar método, resultado, fecha y vínculo; cuando se admita criterio clínico
o nexo, documentar sus requisitos. No imponer laboratorio como vía única ni
equiparar todos los literales que contienen «confirmado». Probable y sospechoso
requieren sus propias definiciones y deben permanecer separados. Si sólo existe
la correspondencia literal, la clasificación sigue registrada/provisional;
ausencia, contradicción o valor no mapeado dejan información insuficiente.
Ninguna categoría excluida o descarte individual demuestra un negativo semanal.
La matriz histórica detallada permanece privada en el dossier. [E2 §P1,E3]

**Episodios (P2).** `source_id + sheet_ref + record_ref` identifica una fila;
`event_ref` no acredita un episodio. Acreditar qué identificadores representan
persona, notificación, muestra, episodio o actualización, si cambian/reutilizan
valores y si enlazan fuentes. Varios IDs podrían ser un episodio y un ID repetido
podría abarcar varios episodios. No proponer una ventana de días sin criterio
epidemiológico. Reutilizar la resolución documentada del grupo completo y un
representante por episodio de `episodes.py`, conservando historia y conflictos.
Sin respaldo, identidad pendiente; no escoger primera/última fila, ni unir por
coordenadas. La identidad ausente no se resuelve con la clave técnica. [E2 §P2]

**Etiquetas futuras propuestas, sin materialización actual (P1–P5):**

- **Positiva respaldada:** existe al menos un episodio que cumple la definición
  aprobada, con identidad, fecha y atribución territorial justificadas. Puede
  demostrar presencia bajo ese sistema sin acreditar el total de episodios ni
  cobertura completa. Si sólo hay registros provisionales, conservar ese grado
  de evidencia y limitar el uso experimental; no promoverlos automáticamente.
- **Sin registros con cobertura acreditada:** sólo candidata a negativa bajo
  las reglas aprobadas si cubre semana completa, evento/población/radios y base
  temporal correctos, extracción y maduración respaldadas, sin pendientes que
  puedan cambiarla. Significa ausencia registrada bajo ese sistema/corte,
  nunca ausencia universal de dengue o de infección.
- **Sin registros con cobertura desconocida:** desconocida/null. Grilla completa,
  ninguna notificación o buen desempeño predictivo no sustituyen evidencia.
- **Información incompleta/pendiente:** conservar el motivo y alcance afectado;
  bloquear negativos y totales completos. Un positivo ya respaldado puede
  conservar evidencia de presencia, sin afirmar exhaustividad. Semana parcial,
  sin referencia válida o asignación irresoluble no se completa por conveniencia.

La ausencia de fecha amplía el alcance temporal posible; la ausencia de radio
amplía el territorial. Los pendientes no son sumables como episodios únicos.
No se convierten ceros asumidos/declarados en comprobados ni null de conteos en
ceros. Los estados y códigos actuales siguen intactos. [E2 §P3–P5,E6,E7]

## 4. Disponibilidad de las variables y fugas temporales

- **Calendario del origen:** semana y seno/coseno son calculables de antemano
  bajo la versión documentada. Mantener t+1 exacto y el calendario nacional;
  disponer del calendario no acredita el resto de las features. [E2 §P4,E8]
- **Superficie y cantidad de vecinos:** derivan de cartografía/topología; se
  necesitan versión, CRS, fecha de disponibilidad y adecuación territorial al
  momento de predicción. Pueden describir contexto retrospectivo estable,
  pero no asumir que esos límites ya estaban disponibles históricamente. [E2 §P5–P6]
- **Población y densidad:** acreditar versión censal/publicación y disponibilidad
  al corte. Densidad hereda población y superficie; matriz completa no demuestra
  conocimiento histórico. El contexto 2022 utilizado por A/B continúa siendo
  retrospectivo mientras falte esa evidencia. [E1,E9]
- **B: presencias t−1…t−4 y cuatro máscaras de faltantes:** acreditar qué se
  conocía al cierre de t, no sólo la fecha del hecho. Se requieren snapshots
  o historial verificable de llegada, clasificación y correcciones. Las máscaras
  también deben reflejar conocimiento en t; calcularlas con una exportación
  final puede introducir información retrospectiva. No son conteos de pacientes.
  La fecha de notificación tampoco prueba disponibilidad para SIGARD. [E2 §P6,E9]

Separar fecha del hecho, período al que corresponde, notificación, ingreso al
sistema, actualización, extracción y disponibilidad efectiva para SIGARD.
Para entrenar en un corte, usar sólo etiquetas ya conocidas/maduras entonces;
para evaluar un objetivo futuro puede definirse un seguimiento posterior,
congelado y separado de los predictores. No inventar retraso fijo, fecha de
publicación ni equivalencia entre muestra y síntomas. Cronología correcta por
fecha del hecho no descarta fuga por conocimiento posterior. [E2 §P4/P6]

## 5. Condiciones mínimas para otra preparación y otro entrenamiento

**Para solicitar preparación, todavía no autorizada:**

1. P1–P6 documentadas en el dossier con fuente/versión, período, territorio,
   regla, evidencia/localizador, responsable designado, resolución/fecha y
   límites. Pendientes explícitos con consecuencia para el alcance elegido;
   ninguna bandera automática reemplaza la revisión del contenido.
2. Objetivo y criterios de positivos/negativos/desconocidos aprobados; episodios,
   fechas y territorio versionados. Cobertura respaldada para cualquier negativo
   acreditado; ambigüedades preservadas o resueltas con evidencia, sin eliminación
   para conseguir ambas clases. Un escenario asumido requeriría permiso propio
   y no satisface esta acreditación.
3. Autorización específica de acceso/procesamiento y preparación para las entradas
   exactas. Fuentes en revisión y conciliación suspendida siguen excluidas;
   cualquier acceso adicional requiere una nueva autorización, sin buscarlo aquí.
4. Salida futura nueva, privada, reproducible y con procedencia/condición de cada
   derivado en `data/interim/` o `data/processed/`; fuentes inmutables y A/B intactos.
   Reutilizar validador, preflight y preparación controlada existentes. Su conexión
   a decisiones reales sigue pendiente; no suponerla resuelta por fixtures ni
   pedir otro validador. [E2 §7,E3 etapas 7–9]

**Antes de solicitar entrenamiento, en otra etapa:** revisar primero el producto
de esa preparación y su autorización independiente. Congelar features, faltantes,
protocolo temporal, transformaciones sólo ajustadas en entrenamiento, semillas,
baselines y métricas. Justificar clases y semanas efectivas considerando radios
vecinos/repetidos y temporada; no inventar mínimos ni dividir filas al azar.
Para afirmar operación, acreditar P6 en cada corte. Acordar quién aprobará
preparación y quién entrenamiento; no asignarles nombres o resoluciones ficticias.

## 6. Evaluación independiente y comparación con A/B

**No hay un nuevo período independiente acreditado en la evidencia revisada.**
El test A/B y sus semanas examinadas por robustez no vuelven a ser independientes
por cambiar etiquetas, nombre de partición o modelo. El nombre de una fuente
con años posteriores no acredita existencia, cobertura, autorización ni reserva
de esos años. [E1–E3,E10,E11]

Para reservar un período: identificar primero alcance autorizado y cobertura;
registrar quién examinó qué datos/resultados, fechas y usos; justificar suficientes
semanas y clases; congelar protocolo antes de consultar resultados; separar
desarrollo, calibración/umbrales y prueba final. Si no puede acreditarse reserva
histórica, proponer recolección prospectiva con snapshots y protocolo aprobado,
sin comenzarla automáticamente. Mantener separación temporal, t+1, purga según
horizonte y maduración, y dependencia espacial/temporal explícita.

El baseline mínimo futuro es la prevalencia calculada sólo con entrenamiento
del conjunto nuevo, sin actualizarla con prueba. Persistencia sólo si existe
historia disponible acreditada. Comparar Precision, Recall, F1, AP, ROC-AUC,
Brier, confusión, prevalencia y resultados semanales, sin escoger ganador sólo
por AUC/recall ni optimizar umbrales con prueba. Esta fase no calcula baselines.

**Comparabilidad con A/B:** conservar sus resultados como referencia histórica
del escenario antiguo. Una comparación numérica directa requiere mismas claves,
período/población, definición y versión de etiquetas, exclusiones, horizonte y
reglas métricas/umbral. Si cambian etiquetas o cobertura, las métricas publicadas
en los informes privados anteriores no son equivalentes. Una eventual evaluación
pareada de scores congelados contra nuevas etiquetas comunes requerirá autorización
separada; sería un puente descriptivo sobre un período ya examinado, no nueva
validación independiente. No requeriría reentrenar A/B. En otro período no hay
predicciones A/B acreditadas disponibles: no inventar comparación ni generarlas
ahora. Documentar exactamente las incompatibilidades y conservar ambas versiones.

## 7. Si no se consigue evidencia institucional

La alternativa académica es presentar un estudio de factibilidad computacional
y sensibilidad retrospectiva sobre registros provisionales y cobertura asumida,
con alcance y permiso propios; también puede estudiarse el MVP sintético
separadamente. No describirlo como aprendizaje de incidencia real, episodios
verificados, negativos acreditados o pronóstico operativo validado. Si faltan
negativos respaldados, no entrenar un clasificador supervisado acreditado como
si existieran. Si falta reserva temporal, no afirmar validación independiente.
Es válido concluir que la evidencia disponible no permite ese estudio y
documentar una propuesta prospectiva. No ejecutar automáticamente otro modelo.

## 8. Preguntas para el responsable de los registros

1. **P1:** ¿Qué evento y definición de caso regían por fuente/período, qué columna
   se exportó y qué evidencia respalda cada criterio de confirmado/probable/
   sospechoso? ¿Cómo se explica la discrepancia de clasificación de 2022?
2. **P2:** ¿Qué representa una fila y cada ID, qué IDs enlazan muestras y
   notificaciones de un episodio, y cómo se distingue un nuevo episodio?
3. **P3:** ¿Qué establecimientos/canales y residentes están incluidos/omitidos,
   con qué filtros, campo temporal, intervalo exacto y fecha de extracción/corte?
   ¿Quién puede respaldar continuidad, interrupciones y completitud de ese extracto?
4. **P3/P4:** ¿Cómo se notifican períodos sin registros, qué pendientes y atrasos
   pueden cambiar una semana y qué evidencia permite considerar madura una celda?
5. **P4:** ¿Qué significan síntomas, consulta, muestra y notificación en cada
   fuente, y qué referencia temporal consideran defendible para el objetivo?
6. **P5:** ¿Las ubicaciones representan residencia u otro lugar, con qué CRS,
   procedencia, fecha y precisión, y quién puede confirmar los límites de uso?
7. **P6:** ¿Se conservan ingreso, actualización y snapshots por corte? ¿Qué
   versiones censales/cartográficas podían consultarse en cada fecha?
8. **P1–P6:** ¿Quién revisará cada respaldo y resolución, qué documentación no
   existe y puede reservarse un período aún no examinado bajo alcance autorizado?

Preparadas para una consulta posterior; no se envió ninguna comunicación.
Solicitar documentos/metadatos y agregados revisados, sin datos identificatorios.

## 9. Referencias comprobadas y límites de verificación

- **E1:** [Auditoría existente](epidemiological-data-quality-audit.md), dictamen,
  hallazgos, confiabilidad de etiquetas y consistencia temporal.
- **E2:** [Contrato vigente](epidemiological-labeling-and-coverage-contract.md),
  C1–C4, P1–P6 y condiciones mínimas; sus identificadores/definiciones se conservan.
- **E3:** [Dossier y etapas 7–9](official-epidemiology-review.md) y dossier privado
  existente, secciones 1–8 (evidencia anterior) y 9 (matriz de resolución actual).
  `diagnostic.private.json`, plantilla y manifiesto bajo
  `data/interim/official/epidemiology_review_05b1_v1/`.
- **E4:** `data/interim/official/quality_report.json`: informe agregado existente.
  Se comprobó presencia/lectura, sin nueva acreditación contra originales ni
  coincidencia hallada en un manifiesto propio durante esta revisión.
- **E5:** [Geografía](official-geography.md) y
  `data/interim/official/geography/geographic_quality.json`.
- **E6:** [Cobertura](official-coverage.md) y
  `data/interim/official/observed/coverage_042/viability.private.json`.
- **E7:** [Escenario asumido](official-assumed-scenario.md) y
  `data/processed/official/spatial_assumed_2024_v1/review.private.json`.
- **E8:** [Fechas](official-date-recovery.md), [calendario](official-calendar.md)
  y `data/interim/official/observed/date_recovery_041/`: `comparison.private.json`,
  `strict/exploratory/reconciliation.json` y `expanded/exploratory/reconciliation.json`.
- **E9:** [Disponibilidad temporal](official-temporal-feasibility.md) y
  `data/processed/official/spatial_temporal_feasibility_05e_v1/review.private.json`.
- **E10:** [A](official-spatial-research.md), [B](official-spatial-model-b.md) y
  `data/processed/official/spatial_rf_B_05f_v1/review.private.json`.
- **E11:** [Robustez](official-spatial-robustness.md) y
  `data/processed/official/spatial_robustness_v2/`: `summary.private.md`,
  `report.private.html` y `manifest.private.json`; sin recalcular métricas.
- **E12:** [Conciliación suspendida](official-selection-reconciliation.md),
  alcance que esta propuesta no reactiva.

Se comprobaron las rutas y la integridad de los nueve informes JSON agregados
posteriores a calidad contra sus entradas en manifiestos existentes; esto
verifica archivos, no autenticidad institucional ni verdad epidemiológica.
La robustez se consultó por sus informes/manifiesto. No se leyeron tablas de
registros, etiquetas, predicciones o matrices para ampliar el análisis, ni Excel,
originales pendientes o modelos serializados. La comprobación de conservación
de A/B/robustez usa sólo huellas de bytes, sin interpretar sus datasets.
No se publica contenido privado, literales históricos detallados ni cifras
sanitarias nuevas. Revisión científica y aprobación institucional pendientes.

La enmienda del dossier se registra en su manifiesto local conservando huella y
longitud anteriores. Los manifiestos congelados que referían a su versión previa
conservan sus referencias históricas: no se alteran A/B ni se presentan esas
huellas como validación de la nueva enmienda. Una futura ejecución deberá resolver
explícitamente la versión documental; no actualizar resultados congelados para
ocultar la diferencia.

Apoyo procedimental: skills `scientific-critical-thinking` y `scientific-writing`.
Kassis, T., Agarwal, V., He, Y., Patel, D., & Brueckner, A. M. (2026).
[Scientific Agent Skills: A Library of Procedural Knowledge for Research Agents](https://doi.org/10.48550/arXiv.2609.00065).
Referencia ya verificada en la fase anterior; no es evidencia epidemiológica.
Documento elaborado con asistencia de Codex, pendiente de revisión humana.

## 10. Resumen ejecutivo para solicitar evidencia al Ministerio

22/10/2026 · Solicitud preparada, no enviada. Destinatarios: custodio de registros,
referente epidemiológico y responsables de extracción y contexto territorial,
todos pendientes de designación. Se necesitan documentos/metadatos y agregados
revisados, sin registros identificables. Este resumen reutiliza la matriz P1–P6
de la sección 9 del dossier único, según su descripción ya documentada arriba;
no reabre ese archivo privado ni repite las auditorías completadas.

La decisión solicitada es si puede prepararse un derivado de **conteos de
episodios elegibles por radio y semana**, con referencia temporal y cobertura
definidas. No se solicita acreditar el MVP sintético ni convertir el resultado
retrospectivo A/B en incidencia, conteos completos o nueva prueba independiente.

- **P1 — Evento y clasificación:** diccionario y definiciones históricas por
  fuente/período; correspondencias y evidencia de aplicación de criterios
  admitidos a episodios, con resolución de la discrepancia documentada de 2022.
  Entrega esperada: política versionada de elegibilidad y excepciones; sin ella,
  los registros continúan provisionales y no son etiquetas de conteos reales.
- **P2 — Episodio e identificadores:** significado de fila e IDs, relaciones
  entre notificación/muestra/actualización, reutilizaciones y criterio de nuevo
  episodio. Entrega esperada: resolución documentada de identidad y conciliación;
  sin ella no se puede contar filas como episodios ni deduplicar por conveniencia.
- **P3 — Extracción, cobertura y madurez:** canales/establecimientos incluidos
  y omitidos, población/residencia, filtros, fechas de corte, interrupciones,
  notificación de semanas sin registros, atrasos y pendientes que puedan cambiar
  cada celda. Entrega esperada: cobertura por radio/semana y criterio de madurez;
  sin ella no se acreditan ceros ni totales exhaustivos, aunque haya positivos.
- **P4 — Referencia temporal:** significado y calidad de síntomas, consulta,
  muestra y notificación; fecha defendible del objetivo y reglas para faltantes
  y contradicciones. Entrega esperada: política versionada compatible con semanas
  domingo–sábado; no sustituir fechas ni asignar años por nombre del archivo.
- **P5 — Atribución territorial:** significado de ubicaciones, residencia u
  otro rol, procedencia, CRS, cartografía vigente, precisión y ambigüedades.
  Entrega esperada: universo y política espacial aprobados con límites de uso;
  la validez geométrica de los 263 radios no acredita ubicación de episodios.
- **P6 — Disponibilidad histórica:** snapshots, historial de llegada y cambios,
  publicaciones/recepciones del clima y versiones censales/cartográficas.
  Entrega esperada: inventario de disponibilidad efectiva por snapshot y variable,
  incluidos estados, máscaras y grafo; sin ello una exportación retrospectiva
  no demuestra que esos predictores se conocían en cada origen.

Cada respuesta debe indicar fuente/versión, período, territorio, regla y versión,
localizador de respaldo, responsable/revisor, resolución, fecha y límites.
Registrar también documentos inexistentes y su consecuencia; una firma genérica
no resuelve cobertura, identidad o disponibilidad que no puedan respaldarse.
Las resoluciones permanecen en el dossier único, sin duplicar ni inventar
aprobaciones en este resumen.

**Actos separados que se necesitan:** designación y revisión P1–P6; autorización
de acceso/procesamiento y preparación sobre entradas exactas; revisión del
derivado y protocolo/reserva temporal; autorización posterior de entrenamiento.
No hay evidencia nueva que habilite 2025–2026 ni una reserva independiente; no
se deducen del nombre de las entregas o del éxito de pruebas técnicas.

El [adaptador y contrato exacto](principal-count-input-contract.md) ya comprueban
versiones, permisos, integridad, alcance, estados y disponibilidad en software.
Su ejecución real sigue pendiente de esos actos institucionales. No autentica
firmas ni reemplaza criterio epidemiológico; el entrenamiento e inferencia reales
continúan deshabilitados. El próximo hito útil es obtener las respuestas y
registrarlas en el dossier, sin iniciar otra preparación o estudio automáticamente.
