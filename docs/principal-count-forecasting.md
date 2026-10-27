# Módulo principal de conteos

Esta documentación pública describe interfaces y metodología. Los informes de
ejecución, conteos, desgloses, métricas y figuras obtenidos con fuentes privadas
se conservan exclusivamente en almacenamiento local excluido de Git.

La unidad del prototipo es radio censal por semana epidemiológica. El objetivo
definitivo es estimar conteos de episodios elegibles en la semana siguiente;
las modalidades de registros provisionales tienen otra unidad y no acreditan
episodios, cobertura, incidencia ni ausencia epidemiológica.

## Versiones experimentales

- V1 implementa un experimento condicional sobre celdas observadas.
- V2 implementa un escenario de snapshot con desconocidos y máscaras explícitos.
- V3 compara Poisson directo, presencia/cantidad y corrección de persistencia.

Los horizontes directos admitidos son t+1, t+2 y t+4. La selección usa únicamente
walk-forward de desarrollo con purga temporal y compara baselines de persistencia.
Las features del origen cerrado se admiten sólo como reconstrucción retrospectiva;
se comparan con persistencia que disponga de la misma información.
No se incluyen aquí resultados ni decisiones estadísticas derivadas de fuentes
privadas. La publicación de código no autoriza ejecutar experimentos nuevos.

## Separación pública y privada

`python -B -m sigard_ml.forecasting --fictional-demo` usa fixtures generadas.
`npm run dev:demo` desde `frontend` ofrece el recorrido web ficticio completo.
Ninguno necesita paquetes epidemiológicos, modelos o informes privados.

La consulta privada tiene un [contrato independiente](predictive-experimental-demo.md).
Las fuentes, permisos y artefactos reales no se distribuyen con Git. Los
contratos del adaptador describen el formato sin reproducir valores sanitarios.
No se promueve ningún modelo ni se habilita inferencia productiva por publicar
el software. Las limitaciones P1–P6 del objetivo definitivo se mantienen.

## Contrato de entrada y ejecución ficticia

El contrato de entrada ficticia `Inputs` tiene tres tablas de snapshots:

La unidad declarada es `fictional_eligible_episode_count`; otras unidades como
registros, notificaciones o presencia se rechazan explícitamente.

- `counts`: radio, domingo fuente, `available_on`, conteo entero nullable,
  estado `complete/provisional/unknown`, cobertura completa, pendientes,
  madurez y referencia de procedencia.
- `climate`: domingo fuente, disponibilidad, temperatura media (°C), humedad
  relativa (%), precipitación semanal (mm), completitud y procedencia. Es
  contexto común a Capital; no se atribuye clima medido individual por radio.
- `territory`: radio, disponibilidad, población, superficie km² y procedencia;
  densidad se deriva sólo cuando ambas entradas están disponibles. Grafo
  simétrico, versión y disponibilidad independientes, sin geometrías.

Cada snapshot reemplaza al anterior completo de esa clave. `available_on` es
disponibilidad efectiva y acreditada para el uso, **no** fecha de síntomas,
muestra o notificación. La resolución es diaria, al cierre; una operación
intradiaria necesitaría timestamps y otro contrato. Las tablas no admiten campos
de pacientes ni coordenadas. `Inputs` exige condición y procedencia ficticia
antes de inspeccionar los datos; ninguna bandera activa el uso real.

La entrada derivada acreditada tiene un [contrato separado y exacto](principal-count-input-contract.md).
`adapter.adapt_derived` recibe bytes autorizados; `load_derived` sólo abre el JSON
derivado exacto autorizado bajo `data/interim/` o `data/processed/`. Ambos exigen
versión y SHA-256, permisos de inspección/procesamiento, procedencia por componente,
autorización de preparación y decisión P1–P6 documentada para el mismo alcance.
El registro documental se aporta en memoria: nunca abre las referencias ni el
dossier privado. Rechaza semanas parciales, grillas incompletas y etiquetas
completas sin cobertura/madurez; conserva provisionales/desconocidos con objetivo
null. P6 enlaza disponibilidad de cada snapshot y todas sus variables.

La salida usa `build_dataset` sin cambiar features ni reglas científicas, con
condición/unidad correctas y huellas/documentos en la procedencia. Un panel
preparado no autoriza ajustar un modelo. Entrenamiento e inferencia reales
permanecen bloqueados explícitamente; probar el adaptador no acredita fuentes,
firmas ni elegibilidad epidemiológica. El [procedimiento futuro](principal-count-input-contract.md#procedimiento-para-un-futuro-entrenamiento)
separa preparación autorizada, revisión científica y otro acto de entrenamiento.

## Recorrido implementado

1. `build_dataset`: una fila por radio y origen; objetivo exacto t+1, domingo
   a sábado, calendario `ar-snvs-2020-2026-v1`. Conserva identificadores,
   procedencia, condición de la entrada, estados provisionales/desconocidos,
   máscaras por feature y fecha de disponibilidad del desenlace.
2. Features: conteos exactos t−1…t−4, media de cuatro semanas, tendencia
   t−1 menos t−2 y media de vecinos en t−1. Ventanas/vecinos con cualquier
   desconocido permanecen null. No se salta una semana ausente. Se excluye t
   deliberadamente para no asumir que el conteo contemporáneo ya maduró.
3. Clima: temperatura/humedad/precipitación t−1, medias de temperatura/humedad
   y precipitación acumulada en t−1…t−4, sólo con semanas completas conocidas
   al corte. Contexto territorial conocido entonces, año/SE de origen y
   seno/coseno con 52 o 53 semanas según el calendario. No se usa clima futuro.
4. Desenlaces: snapshot congelado separado de features. Un conteo se conoce
   sólo con cobertura completa, madurez y ausencia de pendientes; de otro modo
   queda null, aun si contiene positivos. Cero requiere las mismas condiciones.
   La presencia derivada se conserva separada del conteo.
5. Partición: cortes dominicales comunes a todos los radios, con purga de
   transiciones que cruzan train/validación y validación/test. Los dos candidatos
   predefinidos son GLM Poisson regularizado y boosting con pérdida Poisson,
   capacidad limitada y sin early stopping aleatorio. Semilla explícita;
   versiones/hiperparámetros/huella del ajuste en metadatos.
6. Preprocesamiento: lista cerrada de features, imputación técnica de features
   con cero más indicadores de faltante aprendidos en entrenamiento; escalado
   sólo para GLM. Nunca se imputa el objetivo. Cada pipeline se ajusta sólo en
   su entrenamiento. Un entrenamiento todo cero usa un modelo nulo explícito;
   una falta de convergencia bloquea la evaluación del candidato.
7. Selección por MAE de validación, con desempate hacia GLM. Sólo usa desenlaces
   conocidos al corte de selección; luego reajusta sobre desarrollo elegible.
   Reconstruye las versiones de etiquetas conocidas al ajuste, sin utilizar
   retrospectivamente una revisión posterior. El test queda fuera de selección,
   preprocesamiento y ajuste; sus features son de origen móvil con modelo fijo.
8. Baselines: media histórica por radio ajustada en entrenamiento (fallback
   media global), y persistencia t−1 con fallback a esa media cuando falta
   historia. Modelo y baselines evalúan las mismas claves elegibles, tanto en
   validación como prueba. Se informan MAE/RMSE, sesgo, MAE en positivos,
   proporción de ceros y desviancia Poisson cuando la predicción es positiva;
   con medias cero la desviancia queda null, sin epsilon oculto.
9. Evaluación por radio, macro-MAE territorial y semana; MAE/RMSE del total de
   Capital únicamente en semanas con todos sus radios conocidos. Los subtotales
   elegibles se identifican aparte, sin presentarlos como Capital completo.
10. `forecast_next_week`: toma el último origen cerrado al `as_of` explícito,
    exige t−1 completo/maduro en todo el universo y construye sólo t+1. Si falta
    historia reciente, devuelve bloqueo y conteos null, sin retroceder a una
    fecha vieja. Conserva corte, objetivo, versión, modelo, disponibilidad y
    procedencia; ordena concentración por esperanza y suma las esperanzas sin
    redondeos para obtener el total coherente de Capital.

Los conteos pronosticados son esperanzas no negativas, posiblemente fraccionarias.
No representan notificaciones, incidencia, score binario ni riesgo de brote.
Las candidaturas y parámetros actuales comprueban el código; su adecuación al
estudio real y el soporte temporal/espacial deben revisarse antes de congelar
un protocolo científico. No se afirma superioridad sobre los baselines.

## Consulta por fecha en Python

`resolve_date_query(target_date, as_of=..., information_cutoff=...)` recibe una
fecha `date` o texto canónico `YYYY-MM-DD`, sin catálogo fijo. La fecha identifica
la semana **objetivo**, no la fecha de carga ni de corte. El calendario argentino
verificado abarca 29/12/2019–02/01/2027; además debe estar verificado el origen
anterior, por lo que el primer objetivo consultable empieza 05/01/2020.
Esto es dominio del calendario, no disponibilidad de datos o de pronósticos reales.

El último corte respaldado se aporta explícitamente como sábado al cierre,
no posterior a `as_of`. Si el objetivo ya cerró a `as_of`, el modo es
`historical_backtest`; en otro caso es `forecast`. En ambos, el corte de features
es el sábado inmediatamente anterior al objetivo. Para historia, se reconstruye
ese corte; para futuro, sólo se admite la semana siguiente al corte aportado.
Una exportación actual no demuestra que ese corte histórico esté acreditado.

`forecast_for_date(fitted, inputs, target_date=..., as_of=...,
information_cutoff=...)` reutiliza `forecast_next_week`, los snapshots y las
features existentes. Exige modelo t+1, universo/versión coincidentes y ajuste
anterior al corte, además de historia reciente completa/madura. Sin modelo,
historia, calendario o horizonte admisible lanza `ForecastError` comprensible.
Rechaza inferencia real, aun con entrada preparada. No ajusta modelos, encadena
predicciones ni simula multihorizonte: ese caso necesitará otro contrato/modelo.

El pronosticador usa `build_dataset(..., include_outcomes=False)`: todas las
etiquetas del objetivo quedan null y no se exige una etiqueta futura. El adaptador
sigue exigiendo historia t−4 y origen dentro del período autorizado y corte no
posterior a la revisión. Entrenamiento/evaluación conservan el valor predeterminado
`include_outcomes=True`, con t+1 dentro del alcance; no se amplían permisos de uso.
La salida añade fecha solicitada, modo y último corte, manteniendo el total de
Capital como suma de esperanzas sin redondeo. No acredita independencia del backtest.
No se modificaron frontend ni CLI: la CLI sigue siendo sólo la demostración ficticia.

## Probabilidad, incertidumbre y límites

Hay un diagnóstico opcional Poisson `1-exp(-mu)` con Brier para presencia.
La pérdida de conteos no acredita una distribución Poisson ni calibración;
sobredispersión y exceso de ceros requieren evaluación específica. La salida
de pronóstico mantiene `presence_probability=null` e intervalos null con motivo
explícito. No publica el diagnóstico como probabilidad validada, ni inventa
intervalos/independencia espacial a partir de la media.

La prueba ficticia tiene reserva técnica. El test histórico A/B ya fue examinado;
no se acredita otro período independiente por cambiar de modelo. No se
persisten modelos, matrices o predicciones. El único lector opcional del adaptador
acepta derivados expresamente autorizados; no se utilizó con datos reales.
Los validadores/preflight/preparación de etapas 7–9 conservan sus restricciones;
la simulación aquí autorizada no utiliza sus informes como permiso real.

Para habilitar el recorrido real todavía se necesita:

- Resolver en el dossier existente P1 (definición/clasificación histórica),
  P2 (episodios e identificadores), P3 (extracción, cobertura y madurez por
  radio/semana), P4 (fecha objetivo), P5 (atribución espacial y límites aceptados),
  P6 (snapshots y disponibilidad de registros/clima/contexto en cada corte).
  Cada resolución debe indicar respaldo, alcance, responsable, fecha y límites.
- Autorizar preparación sobre versiones/entradas exactas y después entrenamiento
  por separado. El adaptador de derivados ya está implementado; faltan los
  respaldos institucionales y entradas acreditadas que permitan utilizarlo.
  Los validadores/preflight simulados conservan sus límites. Sustituir
  `fictional` por `real` no concede permisos ni habilita ejecución del modelo.
- Congelar población, features, horizonte, manejo de desconocidos, protocolo y
  período de prueba verdaderamente reservado. Si no existe reserva histórica,
  acordar validación prospectiva sin iniciarla automáticamente. Calibración y
  intervalos requieren metodología y evidencia independientes.

## Ejecución y comprobación

Desde la raíz, sin Docker, PostgreSQL, frontend ni backend:

```powershell
.\ml\venv\Scripts\python.exe -B -m sigard_ml.forecasting --fictional-demo
.\ml\venv\Scripts\python.exe -B -m pytest ml/tests/test_principal_forecasting.py -p no:cacheprovider --basetemp=ml/.tmp/principal-counts-tests
```

El CLI sólo genera fixtures y un resumen JSON por stdout. No acepta rutas de
entrada, fechas arbitrarias de objetivo ni exportaciones. La API Python devuelve
panel, informe y estimador en memoria para inspección técnica. Las pruebas
cubren calendario, snapshots, madurez, desconocidos, contigüidad, clima pasado,
vecinos, particiones/purga, preprocesamiento, reproducibilidad, baselines,
no influencia de test en el modelo y contrato de salida. Sus métricas son
exclusivamente ficticias y no se incorporan a la tesis como desempeño científico.

Verificación original del 21/10: **73 pruebas nuevas y 55 regresiones** de
`test_official_calendar.py` y `test_baseline_evaluation.py`, todas aprobadas.
Demo ficticia completada y **178 controles de seguridad estática** aprobados,
sin modelos cargados ni contextos enviados a Docker. No se repitieron auditorías
científicas ni suites A/B. No corresponde lint/build frontend porque no cambió.

Verificación de integración del 22/10: **131 pruebas nuevas del adaptador y
128 regresiones**, todas aprobadas (**259** en total), exclusivamente con fixtures
ficticias. Incluyen permisos anteriores a la interpretación, integridad, cada
P1–P6 ausente/no aprobada/fuera de alcance, disponibilidad por variable,
revisiones tardías sin fuga a features ni etiquetas históricas, ceros acreditados,
provisionales y desconocidos, mutaciones posteriores y bloqueo de ejecución real.
Se comprobaron **178 controles de seguridad estática**, sin Docker ni PostgreSQL,
sin abrir originales o privados adicionales, ni ejecutar inferencias reales.
La solicitud ejecutiva al Ministerio queda en la
[sección 10 del plan vigente](next-ml-training-readiness.md#10-resumen-ejecutivo-para-solicitar-evidencia-al-ministerio).

Verificación de criterios y consulta por fecha del 22/10: **362 pruebas aprobadas**
de consulta, adaptador, conteos principales, fechas, registros y calendario;
**178 controles de seguridad estática** y `git diff --check` sin errores.
Las entradas fueron generadas y ajenas a fuentes reales. Las nuevas pruebas de
consulta usan dobles de estimador, sin ajuste; la regresión reutiliza el recorrido
ficticio ya existente. Sin entrenamiento real, nuevas auditorías, servicios,
cambios frontend ni ejecución de A/B.

Referencias técnicas: documentación oficial de
[PoissonRegressor](https://scikit-learn.org/stable/modules/generated/sklearn.linear_model.PoissonRegressor.html),
[HistGradientBoostingRegressor](https://scikit-learn.org/stable/modules/generated/sklearn.ensemble.HistGradientBoostingRegressor.html)
y [métricas de evaluación](https://scikit-learn.org/stable/modules/model_evaluation.html).
Se comprobó con scikit-learn 1.9.0 instalado; sin dependencias nuevas.
