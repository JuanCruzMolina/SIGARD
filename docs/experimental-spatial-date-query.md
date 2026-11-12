# Consulta privada A/B por fecha e inferencia del estimador existente

**Estado posterior a la migración PostgreSQL del 29/10/2026:** la inferencia
nueva A basada en Parquet está deshabilitada hasta verificar su contrato con
la base. El servicio informa `postgres_legacy_contract_unverified`. A/B conservan
sus resultados retrospectivos; el frontend no cambió. La implementación descrita
a continuación se conserva como antecedente y reproducción histórica explícita.
Ver [migración operativa de ML](database/postgres-ml-migration.md).

Los modelos nuevos [Option B](database/option-b-research.md) se consultan por
el CLI privado PostgreSQL. No se activan en esta API ni modifican el frontend.

Implementada en `entrenamiento-ML`. Conserva el calendario libre y los resultados
congelados y habilita **inferencia nueva A**, privada, experimental y t+1 desde
la semana actual. B no ejecuta inferencia nueva porque falta una fuente
epidemiológica reciente con disponibilidad verificable. No se entrenó, ajustó
ni seleccionó otro modelo; V1/V2/V3 permanecen independientes.

## Uso y fechas realmente habilitadas

Ejecutar `npm.cmd --prefix frontend run dev` y abrir
`http://127.0.0.1:5173/mapa`. Elegir fecha y pulsar **Consultar predicción**.
Se mantienen A, B, diferencia B − A, 263 radios, mapa e historial. Cambiar fecha
limpia inmediatamente los resultados y conserva el radio; las respuestas
reemplazadas se cancelan e ignoran. Gris: sin estimación; borde discontinuo:
error. La diferencia exige ambos scores del mismo radio y semana.

El calendario existente `ar-snvs-2020-2026-v1` admite **29/12/2019–02/01/2027**.
Se resuelve en Python, sin calendario JavaScript alternativo. El 10/04/2024 es
SE 15/2024, objetivo 07/04–13/04, origen 31/03–06/04.

- **Congelados:** objetivos 07/01–02/03, 10/03–04/05 y 12/05–08/06 de 2024,
  20 semanas por modelo. Se devuelve la colección original con sus versiones,
  particiones, metadatos y nulls, sin volver a predecir.
- **A nuevo:** la semana inmediatamente siguiente a la semana del reloj real
  del servidor en Argentina (UTC−03). En la comprobación del **27/10/2026 local**,
  cualquier fecha del **01/11/2026 al 07/11/2026**, con origen **25/10–31/10**.
  Todos esos días reconstruyen la misma matriz.
- **Histórico sin congelado:** bloqueado. Observar hoy contexto y estimador no
  acredita disponibilidad en un origen anterior. Incluye purgas y la semana
  actual, cuyo origen ya pasó.
- **Más lejano:** bloqueado. No se anticipa un origen futuro ni hay extrapolación
  recursiva. La ventana se desplaza con el reloj real, siempre t+1 y dentro del
  calendario soportado, sin aceptar un supuesto presente elegido por el cliente.
- **B nuevo:** bloqueado aunque A pueda calcularse. No se sustituye B por A,
  V3, persistencia ni una matriz de rezagos completamente fabricada.

## Fuentes y transformaciones exactas

Entrada directa de A:
`data/processed/official/spatial_assumed_2024_v1/predictors_A.private.parquet`,
vinculada por el manifiesto de escenario a la revisión del modelo A. Se proyectan
sólo sus siete columnas y claves; no se leen etiquetas para reconstruir A.
Orden conservado:

1. `superficie_km2`: área del maestro territorial, originalmente EPSG:32719 / 1e6.
2. `poblacion`: población del Censo 2022 del mismo maestro.
3. `densidad_poblacional`: población / superficie, ya conciliada en el maestro.
4. `cantidad_vecinos`: número de vecinos queen del mismo universo de 263 radios.
5. `semana_epidemiologica`: SE del **origen**, nunca del objetivo.
6. `estacionalidad_seno`: seno de `2π × (SE_origen − 1) / semanas_del_año`.
7. `estacionalidad_coseno`: coseno de esa fase; 52/53 semanas del calendario oficial.

Las cuatro primeras proceden de `territorial_master.parquet`, a través de
`spatial_ml_05a_v2/expanded/exploratory/predictors_retrospective.private.parquet`
y la selección del escenario. Se preservan exactamente, sin actualizar población
ni recalcular cartografía. `dataset.territorial_context` hizo sus verificaciones
originales; no se repiten auditorías geográficas. Las tres últimas reutilizan
`features.calendar_predictors`. No hay escalador, imputador o calibrador que
ajustar; el RF realiza su conversión interna habitual a float32. A no usa
meteorología, coordenadas como features ni historia epidemiológica reciente.

B añade `local_presencia_exp_rezago_1` a `_4` y luego sus cuatro indicadores
`_missing`: presencia provisional experimental de t−1…t−4, por fechas exactas,
sin saltar huecos. El entrenamiento convirtió la matriz a float64 y preservó
NaN para el tratamiento nativo del bosque; `_missing=1` significa desconocido.
No se transforma un desconocido en cero.

Su fuente existente es
`spatial_temporal_feasibility_05e_v1/weekly_history_sources.private.parquet`,
derivada por `temporal_history.source_history` de las semanas y etiquetas de
2024. La matriz candidata es `predictors_B_presence_candidate.private.parquet`;
la utilizada está en `spatial_rf_B_05f_v1/inference_matrix.private.parquet`.
No son fuentes recientes. La revisión existente no acredita disponibilidad
epidemiológica operativa en origen para esas filas.

Para B nuevo faltan presencias por radio de **27/09–03/10, 04/10–10/10,
11/10–17/10 y 18/10–24/10 de 2026**, para el origen 25/10. Debe existir un
producto privado autorizado compatible con los 263 radios y las mismas
definiciones, con conocidos/desconocidos, pendientes, versiones/revisiones y
fecha de disponibilidad por entrada anterior al corte. Un cero necesita respaldo.
Una fuente compatible puede tener nulls legítimos por radio; **no disponer de
ninguna fuente reciente verificable no se sustituye por cuatro NaN**. No se
incorporaron fuentes pendientes ni se reconstruyó esa historia en esta tarea.

## Procedencia temporal y autorización

La autorización expresa de esta tarea permite reutilizar los estimadores. Se
creó `data/interim/official/spatial_date_inference_v1/policy.private.json`,
separado de permisos, modelos y manifiestos históricos congelados.

La captura comprobó contexto y estimador disponibles localmente en
**28/10/2026 01:15:21 UTC = 27/10/2026 22:15:21 de Argentina**. Es observación
local desde ahora, no fecha institucional de publicación ni acreditación de
disponibilidad en 2024. No se utilizaron mtimes como evidencia.

Cada inferencia fija `information_cutoff` al instante real de consulta, dentro
del origen actual, y exige captura de contexto/modelo ≤ corte. El contexto
estático ya está disponible y el calendario es conocido de antemano: **A no
necesita esperar el cierre de observaciones de t**. No usa variables dinámicas
de t ni del objetivo. Esto respalda A prospectivo sin acreditar orígenes pasados.
El fin de origen es un límite de calendario distinto del corte informativo.

Se conserva el **contexto fijo censal 2022**, no población actual estimada.
Disponibilidad de entradas no acredita vigencia demográfica, generalización del
modelo, cobertura epidemiológica ni validación sanitaria fuera de 2024.

## Ejecutor y contrato privado

La API no deserializa joblib. `experimental_inference.LocalABInference` invoca
el entorno ML existente con Python `-I -B -m
sigard_ml.official.spatial_ml.date_inference`, sin shell, con timeout de 12 s y
máximo dos ejecuciones simultáneas. No hay proceso ML persistente ni escritura
de scores. No se accede a PostgreSQL/Docker ni se entrena o evalúa.

Antes de cargar el propio A se comprueban el registro autorizado y los hashes
de manifiesto, modelo, revisión, metadatos y matriz fuente fijados en la captura.
Calendario/features/protocolo deben seguir idénticos a los registrados durante
el entrenamiento. Se exige el entorno original: scikit-learn **1.9.0**, NumPy,
SciPy, pandas, joblib, threadpoolctl, PyArrow y Python 3.12.10. No se actualizaron dependencias.

Se validan tipo exacto RandomForestClassifier, siete columnas en orden, clases
[0,1], 400 árboles y parámetros originales. Se deserializan los mismos bytes
verificados, nunca una ruta/pickle del cliente. La confianza proviene del
artefacto propio autorizado y su cadena conocida; un hash aislado no autentica
un pickle externo. `fit` está bloqueado para bosque/árboles; se exige la misma
huella del estimador antes/después de `predict_proba` y el archivo intacto.

Las rutas privadas `/calendar` y `/query?date=...&model=A[&radio=...]` conservan
loopback, Host/Origin/cabecera exactos, sólo GET y `no-store`. La API pública
y `dev:demo` permanecen independientes. El catálogo añade `date_inference` con
la ventana real y el motivo de bloqueo de B.

El sobre `sigard-private-spatial-date-query/1` admite `frozen`, `unavailable` y
`experimental_inference`. Para inferencia, `information_cutoff` es ISO con zona
horaria y `result` usa **`sigard-experimental-spatial-inference/1`**, separado del
contrato congelado. Incluye modelo/versión inalterados, objetivo, origen, t+1,
scores y procedencia de la captura, sin rutas, hashes, features o etiquetas.
Retrospectividad, publicación y uso sanitario son falsos para el resultado nuevo.
El backend valida una lista cerrada de campos antes de enviarlo al cliente.

UI, detalle y tooltip identifican la inferencia nueva y su corte. Los scores
siguen en escala 0–1, sin porcentajes de riesgo. Si falta B no hay diferencia.
El historial sólo muestra congelados con fechas explícitas; no se insertan
inferencias nuevas ni se recalculan métricas.

Si falta la captura privada, se conserva el modo congelado. En otra instalación
autorizada puede observarse la disponibilidad una vez con:

```powershell
.\ml\venv\Scripts\python.exe -I -B -m sigard_ml.official.spatial_ml.date_inference --capture
```

Usa el reloj real, no acepta fecha manual y no sobrescribe una captura existente.
Si cambian archivos/captura tras iniciar, se bloquea la inferencia sin repinning
automático. No repetir la captura para eludir errores de integridad.

## Validación reproducible

```powershell
.\ml\venv\Scripts\python.exe -B -m pytest ml/tests/test_ab_date_inference.py -p no:cacheprovider --basetemp=<directorio-nuevo-dentro-del-proyecto>
.\backend\.venv\Scripts\python.exe -B backend/tests/publication_isolated.py --backend-regression
npm.cmd --prefix frontend run test:research
npm.cmd --prefix frontend run test:security
npm.cmd --prefix frontend run test:public-map
npm.cmd --prefix frontend run test:dev
npm.cmd --prefix frontend run test:demo
npm.cmd --prefix frontend run lint
npm.cmd --prefix frontend run build
.\backend\.venv\Scripts\python.exe -B tools/check_repository_security.py
git diff --check
```

Las pruebas nuevas usan entradas y dobles de estimador ficticios, sin fit ni
fuentes privadas. Cubren transformación exacta, reloj, backdating, entradas
futuras, horizonte, esquema/parámetros/clases, mutación, hashes, aislamiento,
rechazo de campos privados, independencia A/B y preservación de congelados.

La comprobación privada real ejecutó A para dos días de 01/11–07/11: 263 scores
idénticos, B bloqueado, congelados conservados y fecha más lejana bloqueada.
Sólo se guardó un resumen sin scores en `proof.private.json`, junto a la captura.
La prueba de navegador `frontend/scripts/research-panel.browser.mjs` comprueba
A real, retorno a congelados, escritorio/móvil, selección, respuestas tardías,
desconexión y exclusión en producción. Requiere el coordinador local y Puppeteer
ya disponible. Sólo guarda capturas de una fixture totalmente ficticia fuera de
`public/`. Son pruebas de implementación, no una nueva evaluación científica.

Resultado de esta entrega: **17 pruebas ML**, **222 backend** y **72 frontend**
aprobadas, más **12 comprobaciones de navegador** (incluida A real). Las seis
pruebas backend omitidas requieren PostgreSQL/PostGIS descartable y no se
ejecutaron. Lint, build, 189 controles estáticos de seguridad y diff check
aprobados; build conserva una advertencia de bundle mayor a 500 kB. Comparación
antes/después: **302 archivos congelados A/B y V1/V2/V3 intactos**. La captura y
el resumen privados están excluidos de Git; no hay nuevos scores en recursos
públicos ni inferencias persistidas por la API.
