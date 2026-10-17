# SIGARD Fase 4.3: universo epidemiológico y cobertura asumida

Versión: `official-universe-review-0.4.3`. Esta fase revisa fuentes y derivados
privados para preparar un futuro clasificador Random Forest de ocurrencia en
radio censal–semana epidemiológica. No entrena, no genera paneles ni modifica
los escenarios conservadores de elegibilidad o cobertura de fases anteriores.

## Objetivo y condición de las etiquetas

El objetivo experimental es registrar al menos un caso de dengue confirmado
en la semana siguiente, una vez validado el universo de confirmación. Los
positivos disponibles actualmente son registros elegibles **provisionales**,
no episodios clínicamente validados ni ubicaciones reales de infección.
No sustituye los objetivos de conteo ni los modelos del MVP sintético.

Para cada radio y semana objetivo se distinguen cuatro condiciones:

- Positivo observado provisional: hay registros incluidos bajo las reglas
  actuales; su etiqueta es 1, con incertidumbre clínica, temporal y geográfica.
- Cero comprobado bajo reglas: requiere respaldo de completitud, ausencia de
  pendientes y semana completa; etiqueta 0 con procedencia verificable.
- Cero asumido experimental: sólo tras declaración explícita y autorización,
  con intervalo, territorio, política de fechas, justificación, procedencia y
  confianza; no adquiere condición epidemiológica comprobada.
- Desconocido: sin respaldo suficiente, con pendientes o ventana parcial;
  etiqueta nula. Ausencia de filas y celdas de una grilla no producen negativos.

## Revisión del universo

`universe_pipeline` lee los libros mediante las autorizaciones existentes y
concilia sus cantidades con la auditoría preservada de Fase 4.1. Sólo exporta
agregados. No escribe identificadores personales, domicilios ni coordenadas.
Inspecciona los campos reconocidos de provincia/departamento de residencia,
clasificación y evento, conservando las limitaciones semánticas del mapeo.

La coincidencia con etiquetas de residencia La Rioja–Capital no demuestra
qué columna se usó en el filtro manual. Tampoco prueba que las coordenadas
aproximadas representen residencia: ese rol sigue separado del filtro
territorial. Una cabecera de evento o una etiqueta genérica confirmada no
sustituye un catálogo de eventos ni el criterio diagnóstico histórico.

La clasificación literal y la evidencia diagnóstica son dimensiones distintas.
Como contexto histórico, la
[circular de vigilancia de febrero de 2024](https://www.argentina.gob.ar/sites/default/files/2024/05/circular-de-vigilancia-febrero-2024.pdf)
contempla criterios clínico-epidemiológicos en brote. La
[guía de noviembre de 2024](https://www.argentina.gob.ar/sites/default/files/2019/10/guia-vigilancia-dengue-otros-arbovirus-11-2024_0.pdf)
distingue categorías de laboratorio y nexo. Se necesita la definición aplicable
a la fecha de cada extracción; estas publicaciones no reclasifican automáticamente
los registros históricos ni sustituyen resultados de laboratorio individuales.

Sin exportación anterior al filtro manual o conciliación documentada, la
cantidad de registros omitidos es **desconocida**, no cero. La declaración previa
de entrega de la totalidad de registros disponibles no demuestra que el universo
seleccionado represente vigilancia completa de todos los radios y semanas.

## Fuentes, períodos y candidatos a declaración

Se reutilizan informes de Fases 4.1/4.2 y de la auditoría del período 2020–2026.
De esta última se usan sus hallazgos sobre las fuentes; su diagnóstico del
calendario precede a la corrección posterior y no se vuelve a ejecutar aquí.
No se utiliza el nombre del archivo para decidir un año observado.

Los límites configurados hasta 31/12/2024 sólo delimitan la grilla de análisis.
Los extremos de fechas presentes y las semanas activas tampoco prueban
continuidad. No se consideran 2025 o 2026 períodos observados. La semana
parcial etiquetada 2025-SE1 es un borde de la grilla, no cobertura de 2025.

Para dimensionar una propuesta sin inventar cobertura se calculan envolventes
por fuente, año civil de la fecha de referencia y tipo de fecha. Sus límites
candidatos incluyen únicamente semanas completas interiores a los extremos
observados. Se registran como `proposal_not_declaration`, confianza de
completitud `none`, justificación y procedencia. Los intervalos superpuestos
se unen como máscaras y no se suman dos veces.

Estas propuestas pueden ser más estrechas que una extracción completa real;
su amplitud no pretende estimar el período solicitado. El responsable debe
declarar fechas exactas a partir de su documentación y puede rechazarlas.
No se extienden automáticamente hasta diciembre ni se rellenan huecos entre
entregas. Un año sin confirmados elegibles no se convierte en año negativo.

## Capacidad condicional y análisis de incertidumbre

La máscara `potential_negative_if_interval_declared_complete` representa
capacidad, **no una etiqueta negativa**. Requiere celda actualmente desconocida,
sin pendientes posibles, semana completa y pertenencia íntegra a una propuesta.
La capacidad t+1 busca la semana exacta siguiente dentro del panel preservado;
no salta huecos ni prolonga su cobertura. Ninguna máscara rellena valores nulos.

Los pendientes sin fecha conservan como período posible toda la ventana actual,
sin asignarles año por archivo. Afectan las semanas de su radio candidato; si
no hay radio, conservan el bloqueo territorial amplio de las fases anteriores.
Una declaración de completitud no anula esos bloqueos. Se informan las
intersecciones de problemas de identidad y elegibilidad, evitando sumarlas
como registros independientes.

Se concilian políticas estricta/ampliada por clave opaca de fila, se contabilizan
las recuperaciones y se reutiliza la evidencia de demora de Fase 4.1. Muestra
es una fecha aproximada de síntomas: no se restan días para imputar el inicio
real, ni se valida la semana de síntomas de registros que carecen de ella.

Se mantienen las marcas de asignación incierta y se reutilizan los sondeos
geográficos previos sin geocodificar. Las distancias de sondeo no son radios
de error calibrados ni probabilidades. Aceptar candidatos aproximados para
exploración no prueba precisión espacial real.

## Estadísticas y separación cronológica

Los informes privados contienen, por política de fechas, agregados por año
epidemiológico de observación y del objetivo, por radio y por semana. Incluyen
positivos provisionales, ceros comprobados/asumidos, desconocidos, registros,
capacidad negativa condicional, proporción de clases y bloqueos por pendientes.
También separan los ejemplos que requieren un conteo conocido en el origen.

Los cortes de evaluación son domingos explícitos de la configuración. Entrenamiento
diagnóstico requiere que termine la semana objetivo antes del corte; evaluación,
que la semana de origen comience desde ese corte. Se excluye la transición
que cruza el límite. Se muestran los desconocidos de ambas particiones, sin
tratarlos como negativos. Los cortes se analizan sin entrenar ni seleccionar
por métricas. Su existencia no reconstruye disponibilidad histórica de
notificaciones o clasificaciones.

Antes de un Random Forest deben resolverse el universo, la cobertura y ambas
clases; definir features disponibles en el origen, ajustar transformaciones
sólo en entrenamiento y comparar con baselines temporales. La concentración
en una temporada exige evaluar cambio temporal y calibración de probabilidades
sin partición aleatoria de filas. Ningún resultado de esta fase habilita
automáticamente entrenamiento.

## Ejecución y salidas privadas

```powershell
.\ml\venv\Scripts\python.exe -m sigard_ml.official.universe_pipeline --config ml/configs/official.universe.example.json
```

La configuración sólo permite `generate_assumed_zeros=false` y
`training_enabled=false`. El destino debe ser nuevo y estar separado de los
directorios previos. Se verifican manifiestos, procedencia normalizada y
SHA-256 de fuentes y artefactos protegidos antes/después. No se reejecutan
ingestión, calendario, geocodificación o construcción de paneles.

Salidas ignoradas por Git bajo `data/interim/official/observed/universe_043_v1/`:

- `review.private.json` y `review.private.md`: revisión y estadísticas.
- `{strict,expanded}.by_observation_year.private.parquet`,
  `.by_target_year.private.parquet`, `.by_radio.private.parquet`,
  `.by_week.private.parquet` y `.chronological_splits.private.parquet`:
  agregados, no paneles de entrenamiento ni filas individuales.
- `configuration.private.json`, `declaration.template.private.json` y
  `integrity_manifest.private.json`: configuración, declaración sin firmar y huellas.

El destino de ejemplo queda ocupado tras una ejecución; una nueva revisión
debe elegir otro directorio para conservar el anterior.

## Información pendiente y punto de detención

La plantilla no firma ni rellena una declaración en nombre del usuario.
Requiere responsable y fecha, referencias privadas, intervalos y fuentes,
fechas/campo temporal/corte de cada extracción, columna y valores de ambos
filtros, definición de confirmación histórica, conciliación con el universo
anterior al filtro, territorio, política temporal y confianza.
`pending_policy=preserve_blockers` es obligatorio. La aproximación temporal y
geográfica requiere aceptación experimental explícita.

Una declaración de confianza alta sigue siendo una declaración, no una
verificación. Para ceros comprobados siguen vigentes los respaldos y reglas
de Fase 4.2. Aun con un borrador completo, Fase 4.3 sólo informa preparación
para revisión y no autoriza materialización. Se detiene sin ceros asumidos,
sin entrenamiento y a la espera de declaración/evidencia y autorización.

## Pruebas

`ml/tests/test_official_universe.py` usa fixtures ficticios para comprobar
conservación de nulos, bloqueos, ventanas parciales, contigüidad, cruce de
año objetivo, separación cronológica, incertidumbres, declaraciones inválidas,
rechazo de 2025/2026, encabezados enmascarados y protección de directorios.
Suite conjunta con cobertura y recuperación de fechas: **95 aprobadas**.
