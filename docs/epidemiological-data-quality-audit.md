# Auditoría de calidad y trazabilidad epidemiológica

Fecha: 19/10/2026. Rama comprobada: `entrenamiento-ML`.
Estado: diagnóstico técnico para revisión del responsable; no habilita cambios,
entrenamiento ni uso sanitario. Alcance: circuito oficial y modelos A/B congelados.

## Dictamen

**La evidencia revisada permite investigación retrospectiva bajo los supuestos
declarados, pero no acredita un conjunto de etiquetas epidemiológicas verificadas
para entrenar y evaluar predicción operativa.** Los positivos conservan condición
provisional; los negativos utilizados por A/B son `cero_asumido_experimental`.
Los desconocidos permanecen separados. Un buen resultado frente a estas etiquetas
no demuestra predicción de infecciones ni de cantidades de casos reales. [E2–E7]

El calendario y los controles de estructura, claves y cronología son utilizables
como infraestructura técnica. La completitud numérica de los predictores de A
no acredita su disponibilidad histórica. La geografía puede usarse como contexto
retrospectivo aproximado aceptado por el proyecto, sin afirmar ubicación real de
casos. Ninguno de estos controles sustituye confirmación y cobertura. [E3–E7]

## Alcance y controles realizados

Se inspeccionaron código, contratos, pruebas y once informes JSON agregados ya
generados. Diez informes de fases posteriores se contrastaron con sus manifiestos
heredados: los diez coinciden con las huellas registradas. Esto acredita
integridad de esos archivos, no verdad epidemiológica ni vigencia de todas sus
fuentes. No se revalidaron hashes de originales ni se abrieron Excel reales,
normalizados con filas individuales, auditorías de pacientes o modelos joblib.
No se ejecutaron pipelines reales ni se consultaron servicios con datos privados.

Los resultados sanitarios exactos y desgloses territoriales/semanales permanecen
en almacenamiento privado. Este informe comunica indicadores globales de
existencia/estado y dimensiones del protocolo, sin republicar conteos sanitarios,
etiquetas literales, identificadores ni hashes privados. Los informes de fases
distintas tienen ámbitos temporales y denominadores diferentes: no sumar sus
pendientes o comparar sus totales como si fueran una única cohorte. [E8–E10]

## Procesamiento y entradas vigentes

1. La ingestión autorizada normaliza campos identificados, fechas y coordenadas,
   y conserva señales de calidad; no valida casos ni elimina duplicados. La
   clasificación usa correspondencias literales completas de un campo explícito,
   no palabras encontradas en otras partes de la fila. [E1–E2]
2. Elegibilidad e identidad se evalúan separadamente. El modo exploratorio admite
   categorías configuradas como confirmadas provisionalmente; probable/sospechoso
   excluido por ese escenario no significa enfermedad descartada. Identificadores
   repetidos quedan pendientes salvo resolución completa con evidencia y un
   representante por episodio; compartir coordenadas no deduplica. [E2]
3. La fecha estricta es inicio de síntomas. La ampliada usa la primera referencia
   válida en el orden síntomas, consulta médica, muestra, notificación. Encabezados
   literales y formatos explícitos aportan trazabilidad; fechas administrativas,
   seriales y fechas conjeturadas no son respaldos clínicos. [E3]
4. La asignación reutiliza coordenadas existentes y polígonos de 263 radios.
   Interiores únicos pueden aportar candidato; límites/múltiples coincidencias
   no se resuelven arbitrariamente. La coincidencia geométrica conserva un estado
   de incertidumbre separado de la elegibilidad epidemiológica. [E4]
5. Se construye la grilla radio–semana y se busca la semana objetivo exacta
   `t+1 = t + 7 días`: positivo provisional, cero respaldado bajo su política o
   desconocido. Una semana ausente no se salta hacia la siguiente observada.
   El escenario asumido agrega negativos identificados como experimentales,
   sin rellenar los conteos originales desconocidos. [E5]

**Modelo A:** siete entradas: superficie, población, densidad poblacional,
cantidad de vecinos, semana epidemiológica de origen y su seno/coseno.
**Modelo B:** las mismas siete más cuatro presencias binarias experimentales del
radio en `t−1…t−4` y cuatro indicadores de faltante: quince entradas. B no usa
conteos de pacientes como rezagos. Los NaN se conservan; no hay imputación ni
selección de casos completos. El identificador territorial, las coordenadas,
el objetivo y los metadatos de cobertura no son predictores de A/B. El objetivo
de ambos es presencia provisional en `t+1`, separado del objetivo de conteos
sintéticos del MVP. [E6–E7]

## Hallazgos comprobados en los agregados

- **Fechas:** la comparación preservada reproduce el panel estricto, concilia
  desenlaces y no cambia las semanas de registros previamente incluidos.
  La recuperación efectiva registrada proviene de toma de muestra; no informa
  recuperaciones por consulta/notificación. Persisten fechas no utilizables,
  excluidos y pendientes. Existen pares síntomas–muestra en semanas diferentes
  y muestras anteriores al inicio consignado. Son señales para revisión; los
  agregados no permiten decidir su causa ni invalidarlos clínicamente. La semana
  real de síntomas de los recuperados sigue desconocida. [E8]
- **Identidad:** hay identificadores repetidos pendientes; el resumen revisado
  no informa resoluciones manuales de identidad. Esto es una señal de posible
  duplicación/actualización, no prueba de episodios duplicados. El informe inicial
  de calidad no marca filas exactamente duplicadas; no descarta duplicación de
  episodios o actualizaciones con otros valores. Un identificador
  no repetido tampoco acredita un caso único. Los motivos pueden solaparse. [E1,E2,E8]
- **Espacio:** el informe registra 263 identificadores únicos, geometrías válidas
  y ausencia de solapamientos de área positiva. No informa faltantes de coordenadas
  ni registros no asignables en ese diagnóstico, pero las asignaciones conservan
  incertidumbre: CRS sin confirmación, rol de ubicación desconocido y procedencia
  geográfica no documentada. La aceptación de aproximaciones no valida domicilio,
  residencia o lugar de infección. [E4,E9]
- **Cobertura previa:** hay declaraciones, pero ninguna verificación aceptada.
  Los cuatro escenarios de fechas/cobertura de Fase 4.2 informan desconocidos y
  ninguna semana con ceros generados o cobertura completa comprobada. Declarar
  un período o encontrar fechas extremas no demuestra vigilancia continua. [E9]
- **Predictores:** el agregado del escenario informa disponibilidad completa de
  las siete entradas de A; el informe B confirma rezagos faltantes conservados.
  La disponibilidad histórica censal y de registros no está acreditada. No se
  infiere completitud del universo a partir de una matriz sin NaN. [E10]

## Confiabilidad de etiquetas y ventana de 2024

**Positivos:** el dossier revisado no acredita criterio clínico verificado para
ninguna fuente. Las banderas de elegibilidad e identidad validadas están en falso;
el código las asigna conservadoramente. Su valor no demuestra que las etiquetas
registradas como confirmadas sean falsas. Falta documentar la definición histórica
del evento, la correspondencia de clasificaciones y la unidad de episodio, en
especial la revisión pendiente de la fuente 2022. No se exige laboratorio como
único criterio: debe acreditarse el criterio admisible en su contexto. No hay base
en esta auditoría para certificar un subconjunto de positivos como validado. [E2,E9]

**Negativos:** en el escenario usado por A/B, todos los negativos del intervalo
autorizado son asumidos y no hay negativos verificados. Proceden de una decisión
explícita de investigación para semanas completas objetivo entre **07/01/2024 y
08/06/2024**, política ampliada y universo listo congelado. Sólo califican celdas
con conteo desconocido y sin pendientes posibles. La autorización fija el alcance
del experimento; no acredita exhaustividad de notificación ni puede extenderse
a todo 2024. Los conteos originales permanecen intactos. [E5,E10]

**Desconocidos:** existen dentro de esa ventana y en la grilla completa. Los
pendientes siguen bloqueando negativos; sin fecha pueden afectar todo el período
posible de un radio y sin radio ampliar el alcance territorial. Fuera de la
ventana no se autorizan nuevas ausencias asumidas; una celda `t+1` faltante conserva
null. Los agregados de B confirman desconocidos excluidos de ajuste/métricas en
las tres particiones. No se listan celdas individuales ni se convierten aquí a cero.
La exclusión deja una población evaluada seleccionada por disponibilidad; las
métricas no representan automáticamente toda la grilla. [E5,E7,E9–E10]

## Consistencia temporal y riesgos

El código usa claves semanales exactas, rezagos anteriores al origen y objetivos
separados. Se conservan los cortes por fecha comunes a todos los radios, sin
partición aleatoria. Los informes B y el contrato A coinciden en estas semanas
**objetivo**: entrenamiento 07/01–02/03/2024 (8); validación 10/03–04/05 (8);
prueba 12/05–08/06 (4). Se purgan objetivos iniciados el 03/03 y 05/05 para que
no crucen fronteras. No se modificó ninguna división. [E6–E7,E10]

Los controles revisados no muestran uso directo de `t+1` como predictor, ajuste
con etiquetas desconocidas ni selección del umbral con evaluación. Se mantiene
el baseline de prevalencia ajustado en entrenamiento y el umbral congelado.
Esto es consistencia computacional, no prueba de disponibilidad punto en el tiempo:
faltan fechas de llegada, revisiones y maduración de etiquetas, además de versiones
censales disponibles en cada origen. Un hecho con fecha anterior pudo conocerse
después. El uso posterior de semanas de prueba ya pasadas como historia responde
a origen móvil retrospectivo, no a pronóstico multisemanal desde un único origen.
Las semanas purgadas pueden aportar historia anterior sin pertenecer al ajuste. [E6–E7]

**Riesgos acreditados:** etiquetas provisionales/asumidas, cobertura no verificada,
fechas y ubicación inciertas, faltantes históricos, prevalencias distintas entre
particiones y prueba ya examinada. Cuatro semanas de prueba y radios dependientes
no equivalen a una muestra grande de eventos independientes. Los scores sin
calibración no deben interpretarse como probabilidades verificadas de infección.
**Hipótesis pendiente:** B podría aprender patrones de observación/faltantes y
temporada además de señal epidemiológica. La sensibilidad descriptiva existente
no identifica causalmente esas contribuciones ni demuestra por sí sola fuga
temporal efectiva. [E7,E10]

## Acciones recomendadas, por prioridad

1. **P0 — Acreditar positivos y universo:** revisión del responsable epidemiológico
   de definiciones históricas, columnas/reglas de clasificación, episodios y
   procedimiento territorial. Conservar provisionalidad hasta documentarla.
   Reutilizar el dossier y la plantilla existentes; no reabrir la conciliación
   suspendida ni incorporar originales sin otra autorización. [E2,E9,E11]
2. **P0 — Justificar cobertura y negativos:** documentar extracción/corte, base
   temporal, filtros, completitud por intervalo y pendientes. Mantener separados
   desconocido, asumido y verificado. Una autorización experimental no sustituye
   esa evidencia; no resolver pendientes por conveniencia para obtener ceros.
3. **P1 — Resolver calidad con indicadores privados:** reutilizar diagnósticos de
   fechas, episodios y geografía. Si falta información agregada, generar en otra
   tarea autorizada: matriz de clasificación/criterio/evidencia por fuente;
   conciliación de episodios revisados/pendientes; disponibilidad por campo de
   fecha, demoras y cruces de semana; y cobertura respaldada/bloqueada por período.
   Aplicar supresión de celdas pequeñas y no exportar claves de pacientes.
4. **P1 — Acreditar disponibilidad temporal:** obtener agregados de llegada y
   cambios de clasificación por corte, maduración de etiquetas y versiones/fechas
   de disponibilidad del contexto censal. Sin ellos, conservar la interpretación
   retrospectiva y no afirmar un backtest operativo.
5. **P2 — Evaluación posterior independiente:** después de la revisión humana,
   acordar otro período no examinado y protocolo congelado, con suficientes
   semanas y dependencia espacial/temporal considerada. No reutilizar la prueba
   actual como confirmación independiente ni cambiar los cortes en esta etapa.

## Validación y límites de entrega

Resultado: **393 pruebas pasaron; 1 se excluyó expresamente**, en dos ejecuciones
sin solapamiento: 309 de calendario/fechas/cobertura/revisión epidemiológica/
preparación espacial/escenario asumido/historia/validadores A/B, y 84 de calidad,
geografía y panel observado. Usan datos ficticios y comprueban identidad,
faltantes, t+1, purga y conservación. La prueba excluida es
`test_evaluation_changes_cannot_affect_fit_prior_or_threshold`, que ajusta RF
ficticios. La prueba de ajuste de B utiliza un espía sin entrenamiento real.
No se reentrenó ningún modelo ni se ejecutó preparación sobre la entrega real.

Se usó `ml/venv/Scripts/python.exe -B -m pytest`, sin caché, con temporales bajo
`frontend/.tmp/epidemiological-audit-{pytest,spatial-pytest}` y el filtro
`-k 'not test_evaluation_changes_cannot_affect_fit_prior_or_threshold'` en la
primera ejecución. Los módulos son `ml/tests/test_official_` más
`calendar`, `date_recovery`, `coverage`, `epidemiology_review`, `spatial_ml`,
`assumed_scenario`, `temporal_feasibility`, `research_training`,
`research_model_b`, `quality`, `spatial` y `observed`, con extensión `.py`.

No cambian código, datasets, etiquetas, resultados, interfaz ni dependencias.
Único entregable persistente de esta etapa: este informe. Los archivos temporales
de pruebas contienen exclusivamente datos ficticios; no se incorporan al producto.
La revisión del responsable queda pendiente antes de cualquier paso posterior.

## Evidencia y referencias

- **E1:** [Ingestión y calidad](official-ingestion.md); `official/normalization.py`,
  `validation.py` y `reports.py`, bajo `ml/src/sigard_ml/`;
  agregado privado `data/interim/official/quality_report.json`.
- **E2:** [Panel observado](official-observed-panel.md);
  `official/classification.py`, `eligibility.py`, `episodes.py` y
  `observed_pipeline.py::prepare_records`.
- **E3:** [Recuperación temporal](official-date-recovery.md),
  `official/observed_dates.py` y `observed_reading.py`.
  [Calendario del proyecto](official-calendar.md), `calendar_rules.py` y
  [calendario nacional 2024, página 1](https://www.argentina.gob.ar/sites/default/files/bancos/2023-11/calendario-epidemiologico-2024.pdf),
  consultado el 19/10/2026: domingo–sábado; SE1 31/12/2023–06/01/2024.
  La versión vigente es `ar-snvs-2020-2026-v1`; la corrección documentada del
  límite 2025/2026 no cambia el intervalo experimental de 2024.
- **E4:** [Asignación geográfica](official-geography.md),
  `official/spatial_assignment.py` y `cartography.py`.
- **E5:** [Cobertura](official-coverage.md), [escenario asumido](official-assumed-scenario.md),
  `official/weekly_targets.py`, `coverage_policy.py` y
  `official/spatial_ml/assumed_scenario.py::materialize_labels`.
- **E6:** [Modelo A](official-spatial-research.md),
  `official/spatial_ml/research_training.py::validate_design`, `splits.py` y
  `experiment_selection.py::BASE`.
- **E7:** [Modelo B](official-spatial-model-b.md),
  `official/spatial_ml/research_model_b.py::validate_candidate` y `temporal_history.py`.
- **E8, agregados privados:** `data/interim/official/observed/date_recovery_041/`:
  `comparison.private.json` y `strict/exploratory/reconciliation.json`,
  `expanded/exploratory/reconciliation.json`.
- **E9, agregados privados:** `data/interim/official/geography/geographic_quality.json`,
  `observed/coverage_042/viability.private.json` y
  `epidemiology_review_05b1_v1/diagnostic.private.json` bajo el mismo interim.
  [Explicación del dossier](official-epidemiology-review.md).
- **E10, agregados privados:** `data/processed/official/`:
  `spatial_assumed_2024_v1/review.private.json`,
  `spatial_rf_05c_v1/metrics.private.json`,
  `spatial_temporal_feasibility_05e_v1/review.private.json` y
  `spatial_rf_B_05f_v1/review.private.json`; cada uno con su manifiesto.
- **E11:** [Conciliación suspendida y alcance autorizado](official-selection-reconciliation.md).
- **Asistencia metodológica:** skills locales `scientific-critical-thinking` y
  `scientific-writing`; contraste de evidencia, incertidumbre y trazabilidad.
  Kassis, T., Agarwal, V., He, Y., Patel, D., & Brueckner, A. M. (2026).
  [Scientific Agent Skills: A Library of Procedural Knowledge for Research Agents](https://doi.org/10.48550/arXiv.2609.00065).
  Referencia procedimental verificada en arXiv el 19/10/2026; no es evidencia
  epidemiológica ni sustituye la revisión humana de este informe.
