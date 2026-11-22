# SIGARD · módulo predictivo experimental integrado

Estado: integración ML 3 sobre el cierre de etapa 4, horizonte de una semana. El módulo es de
investigación retrospectiva local. No se habilitan predicciones sanitarias
operativas, alertas oficiales, nuevas fuentes ni entrenamientos.

## Para explicar ante un tribunal

SIGARD permite elegir una semana epidemiológica anterior y preguntar **dónde**
se preveía al menos un registro elegible y **cuántos** registros se estimaban.
La aplicación compara esas estimaciones con los registros seleccionados por una
política explícita, preservando la incertidumbre territorial y la procedencia
de los ceros. También muestra evolución, errores, métodos y versiones.

La campaña de la etapa 2 evaluó Random Forest para presencia y corrección residual
de persistencia para cantidad. Ningún candidato cumplió los criterios congelados
de promoción con estabilidad suficiente. El resultado técnico final conserva dos
referencias estadísticas: territorial/estacional para presencia y persistencia
del último cierre para cantidad. ML 3 incorpora además las predicciones guardadas
de RF con clima y residual h1 como experimentos evaluados, sin cambiar esa decisión. Presentar persistencia como ML entrenado o como
un resultado superior a sí mismo sería incorrecto.

El aporte demostrado es la integración reproducible y temporalmente controlada
de fuentes, consulta, comparación territorial y límites metodológicos. No acredita
capacidad sanitaria operativa ni validación externa independiente.

## Arquitectura y versiones

1. PostgreSQL 16/PostGIS 3.4 privado conserva fuentes originales, revisiones,
   calendario, clima, geometrías, selección y registro experimental.
2. La etapa 1 genera el dataset lógico versionado
   `sigard-consolidated-history-20261102-v1`, política
   `sigard-project-positive-2022-covered-2020-2024-v1`.
3. La campaña congelada `sigard-predictive-motor-h1-20261102-v1` contiene cortes,
   resultados, artefactos y decisiones. No se ejecuta al navegar.
4. El compilador offline de etapa 3 proyecta agregados y polígonos en un paquete
   privado verificado por SHA-256. La etapa 4 añade un contexto climático separado
   de sólo lectura. No altera tablas ni paquetes anteriores.
5. `backend/app/predictive_service.py` unifica disponibilidad, métodos, privacidad,
   semana/origen, métricas y contexto. El snapshot de integridad dura una petición;
   no hay caché persistente que oculte alteraciones de archivos.
6. Desde F2 (22/11/2026), `predictive_admin.mount` instala el módulo final sólo en la
   API administrativa local (`alerts_local`, loopback 8767), detrás del guard local y de
   una sesión de administrador; el antiguo lanzador sin autenticación de 8765
   (`app.research_local`) fue retirado. React/Vite en loopback 5173 reutiliza el panel
   histórico, ambos mapas y el gráfico. La API pública y la demo ficticia siguen separadas.

Contrato de módulo: `sigard-predictive-experimental/2` desde el 14/11/2026 (las
capas ML se indexan por candidato; ver «Integración de candidatos v2»). La versión
`/1` indexaba ML por capacidad. Compatible con los campos
de `sigard-historical-backtest/1`. Los resultados identifican `result_type`,
`predicted` (presencia/score/cantidad separados), `observed`, `baseline`, unidad,
origen/objetivo, método y versión, política, calidad territorial, disponibilidad,
tipo de evaluación, divulgación y limitaciones. Un faltante conserva null.

## Fuentes, cobertura y criterio epidemiológico

Las fuentes epidemiológicas son las entregas SISA ya normalizadas. La positividad
experimental de registros elegibles de la entrega 2022 no exige clasificación
clínica confirmada. Se mantienen sus clasificaciones originales, fechas,
exclusiones verificables y la conciliación específica del registro descartado.
El año de entrega no reemplaza el año de la fecha clínica.

La cobertura 2020–2024 procede de una declaración metodológica del responsable,
no de una certificación institucional de vigilancia completa. Una semana cubierta
sin registros elegibles tiene cero experimental; fuera de cobertura o con
atribución insuficiente conserva desconocido. En 2024 se distinguen las semanas
con registros de las posteriores con cero por dicha declaración.

El calendario argentino usa domingo a sábado, con semanas 53. Hay 208 semanas
evaluables de 2021–2024; 2020 conserva observaciones sin soporte de predicción de
la campaña. 2025/2026 aparecen fuera de cobertura: no se generan etiquetas ni
predicciones actuales por el nombre de un archivo. La consulta usa el cierre de
N−1 como origen de N, con ajustes anteriores y purga de cuatro semanas. No se
mezclan radios de una misma semana aleatoriamente entre entrenamiento y prueba.

El universo oficial tiene 263 radios y una máscara común de 256; se conservan
los siete excluidos con su razón y sin imputarlos como ceros. La comparación
común no se presenta como predicción departamental completa. Se distingue
asignación aproximada/provisional/verificada, sin publicar puntos clínicos.

## Clima integrado y uso real

El historial Open-Meteo disponible desde 2015 hasta 2024 representa un punto de
referencia de La Rioja Capital. Temperatura media, humedad relativa media y
precipitación acumulada, con sus rezagos y antecedentes, están integrados en el
dataset de etapa 1 y fueron parte del contraste de etapa 2. Los métodos finalmente
de referencia **no utilizan variables climáticas como predictores**. Los dos
candidatos ML integrados sí reciben temperatura, humedad y precipitación de origen,
rezagos, medias/acumulados recientes y antecedentes históricos. El panel muestra
las 37 entradas efectivas del artefacto por bloque. Población y densidad siguen
sin disponibilidad temporal acreditada; no se interpretan como valores reales cero.
La ablación de presencia mejoró Brier frente al RF sin clima, pero no acreditó
mejora global frente a seasonal; AP/F1 empeoraron. En cantidad no se demostró el
aporte climático incremental. No se realizaron nuevas ablaciones ni ajustes.

La interfaz muestra temperatura (°C), humedad (%) y precipitación (mm) de la
semana de origen como contexto, con fechas y días completos. El compilador
`predictive_context.py` exige siete días y valores completos; los faltantes no
se reemplazan por cero. Cada período debe finalizar antes de la semana objetivo.
No se repite el dato de un punto como mediciones independientes por radio.
La llegada histórica de las fuentes no está acreditada: el ejercicio se identifica
como reconstrucción por fechas de eventos, no simulación perfecta de disponibilidad.

## Privacidad y acceso

El módulo final no es público. Sólo responde en la API administrativa local
127.0.0.1:8767 al origen exacto 127.0.0.1:5173, con cabecera de lectura, controles de
Host/cliente, rechazo de proxies, sólo GET y respuestas `no-store, private` (guard local),
**y además** con un JWT de administrador verificado contra la base administrativa (F2).
No se instala en `app.main`, no hay uploads ni montajes de archivos, cookies o rutas de
entrenamiento. Build/preview
y producción no consultan el paquete. Un clonado del código no incluye datos ni
autorizaciones privadas transferibles.

El modo de divulgación predeterminado, **Protegido** (en «Opciones avanzadas»), usa la política técnica
`sigard-local-presentation-minimum5-v1`: protege valores menores de cinco,
incluidos ceros, para no distinguir una celda pequeña positiva de una vacía.
También protege persistencia, scores/presencia, diferencias y subcuentas que
podrían reconstruir esos valores. Oculta totales departamentales complementarios.
Los mapas, tabla y métricas proceden de la misma proyección del servidor; no se
envían valores exactos para ocultarlos sólo con CSS.

Las sumas y métricas de presentación describen únicamente el subconjunto
divulgable, que cambia por semana. No reemplazan las métricas científicas completas
ni permiten comparar directamente su rendimiento con el estudio original. Una
semana sin celdas divulgables queda sin valor; no se convierte en cero.

La opción **Investigación privada · valores exactos** conserva la consulta local
autorizada del responsable. No debe proyectarse ni compartirse con conteos pequeños;
la interfaz lo recuerda con un aviso visible mientras ese modo está activo.
El filtro de cinco es una salvaguarda del prototipo, no una certificación de
anonimización ni una autorización de publicación. No se ofrece exportación pública
del paquete. Un despliegue futuro exigiría control institucional de divulgación,
autenticación/roles y auditoría propios del alcance sanitario.

### Decisión F2: el visor exige un administrador autenticado (22/11/2026)

Opción aprobada por el responsable: montar las rutas predictivas dentro de la API
administrativa local en lugar de mantener una API separada.

- **Quién abre los artefactos.** La API administrativa local (`backend/app/alerts_local.py`,
  modos `serve` y `session`) construye el `PredictiveService` con los mismos registros
  fijados que el antiguo lanzador (`predictive_admin.build_service`) y monta
  `/api/v1/research/predictive/*` con `predictive_admin.mount`. **`app.main` y cualquier
  despliegue nunca lo hacen**: no importan `predictive_admin` ni `predictive_service`, no
  contienen esas rutas (con o sin autenticación) y no abren los artefactos. La API demo
  (8766) tampoco. Pruebas: `backend/tests/test_predictive_access.py`.
- **No hay otra forma de servirlas.** `app.research_local` (8765, sin autenticación) fue
  retirado; `experimental_api.create_research_app` queda sólo para las pruebas de regresión
  de los flujos A/B y de backtest archivados y nunca instala el módulo final.
- **Acceso.** Orden de controles: guard local (cliente loopback, Host `127.0.0.1:8767`,
  `Origin` exacto `http://127.0.0.1:5173`, `Sec-Fetch-Site` local, sin cabeceras
  `Forwarded`/`X-Forwarded-*`/`X-Real-IP`, sólo GET/OPTIONS, `X-Sigard-Research: local-read`)
  → JWT de administrador (`security.get_current_admin`: rol, cuenta activa y
  `token_version`). Sin token o inválido/vencido: 401; rol distinto: 403; sesión revocada
  (rotación de contraseña, desactivación): 401. CORS: sólo `http://127.0.0.1:5173`, método
  GET y cabeceras `Authorization` y `X-Sigard-Research`; sin comodines ni credenciales.
- **Auditoría.** Cada consulta autenticada en modo privado (`disclosure=private`, valores
  exactos) inserta una fila en `predictive_view_audit` (tabla local del SQLite
  administrativo, metadatos propios como `demo_workspace`; fuera de `app.main` y de la cadena
  Alembic gestionada) con usuario, fecha, ruta (`comparison`, `history`, …), semana o período
  consultado y radio, **nunca los valores devueltos**. Si la fila no puede escribirse, la
  consulta falla (cerrada). Las consultas en modo protegido no se auditan.
- **Sin cambios de contrato.** Mismas respuestas `sigard-predictive-experimental/2`, misma
  protección de celdas < 5, misma verificación de integridad por petición y caché por
  proceso del servicio.
- **Alertas internas.** Leen el mismo servicio dentro del proceso (`LocalResearchSource`,
  sin HTTP ni token); no se expone nada nuevo al navegador.
- **Frontend.** Sólo cambió la capa de servicios (`backtestResults.js`, `adminSession.mjs`):
  envía el token que `/admin/reportes` guarda en `sessionStorage`; sin sesión o con el token
  vencido no envía la consulta; ante 401 borra la sesión y explica cómo volver a ingresar.
  La mudanza del visor a `/admin/predictivo` es F3 (el prefijo de la API no cambia; ver abajo).
- **`dev:demo`** no cambia: no inicia ni consulta el módulo predictivo.
- **Proceso compartido.** El guard (`predictive_admin.PredictiveGate`, ASGI puro) despacha el
  prefijo a una subaplicación propia, sin atravesar los demás middlewares administrativos, y admite
  a lo sumo 6 consultas simultáneas del visor (`VIEWER_CONCURRENCY`): las restantes esperan sin
  ocupar hilos, así login, reportes y alertas no quedan detrás del trabajo del visor (sin el límite,
  la primera apertura del panel de alertas tras 5 visores cargados llegaba a ~20 s).
  `/health/alerts` informa `warm` cuando terminó la precarga de alertas (~25–30 s tras iniciar).
- **Rendimiento (22/11/2026, producción, p95, `performance.browser.mjs --target production`).**
  Todas las operaciones < 5 s con 1 y 5 usuarios. Carga del visor con 5 usuarios: F0 2,95 s
  (16/11) y 2,56 s (mismo código F0 medido el 22/11); F2 2,54 s en la misma sesión de esa medición
  y 3,30–3,83 s en dos corridas posteriores, en las que las páginas públicas no modificadas también
  fueron ~35 % más lentas (variación del equipo). Arranque de `dev` 2,1–2,6 s (antes 3,5–4,0 s);
  memoria de 8767 tras la precarga ≈152 MB, igual que antes, sin el proceso 8765 (≈57 MB en
  reposo, ≈103 MB tras usar el visor).

## Registro de componentes activos y archivados

- Referencias seleccionadas: `presence_seasonal` y `count_latest`, h=1.
- Experimentales evaluados: `rf_A_epi_climate` y `residual_h1`, h=1, disponibles
  para comparación local. Sus salidas no se fusionan ni se multiplican.
- Experimentales no promovidos (campaña correctiva v2, 14/11/2026):
  `rf_v2_city_propensity` con regla top-10 y `residual_v2`, h=1. Son los modelos
  ML por defecto del visor, no la referencia seleccionada; P1–P3 y Q2 del
  protocolo prerregistrado no se cumplieron. `logit_v2_factors` es interpretativo
  y no se integra.
- Dataset y lector histórico verificados; clima de origen; sin entrenamiento
  ni inferencia de estimadores desde HTTP.
- No promocionados: `rf_A_reference`, `rf_A_epi_climate`, `rf_A_epi_no_climate`,
  `residual_h1`. Sus evaluaciones y artefactos siguen congelados.
- Archivados: A/B originales, Poisson V1/V2/núcleo previo, V3 h=2 y h=4 y variantes
  descartadas. No se importan estimadores A/B en el arranque final ni aparecen
  sus selectores en el panel principal. No se borran archivos/tablas/migraciones.
- Bloqueados: predicción sanitaria actual 2025/2026, alertas oficiales y promoción
  automática. No hay conexión a Supabase ni despliegue de datos clínicos.

`sigard_ml.forecasting.lifecycle` expone el estado sin conectarse a la base.
Los comandos A/B/V3 archivados bloquean su recorrido por defecto antes de acceder
a fuentes. Las reproducciones históricas conservan módulos y autorizaciones
originales, con opción explícita `--historical-reproduction`. El núcleo Poisson
exige esa opción para train/infer; los adaptadores anteriores la exigen para
train. No se ejecutó ninguna reproducción ni entrenamiento en esta etapa.
Los alias de entrenamiento anteriores se retiraron de `pyproject.toml`; el
registro de estado y la compilación de backtesting son las entradas finales.

## Endpoints y ejecución local

Con los paquetes privados previamente autorizados y las dependencias existentes:

```powershell
npm.cmd --prefix frontend run dev
```

Abrir `http://127.0.0.1:5173/admin/predictivo` (F3; `/` redirige ahí en desarrollo local) e
iniciar sesión con una cuenta de administrador en ese mismo formulario. El módulo es la entrada
local por defecto, sin cargar primero el dataset de demostración ni estimadores A/B. PostgreSQL
puede permanecer apagado. Sin sesión (o con la sesión vencida o revocada) no se muestra el visor
ni se envían consultas: aparece el ingreso de Administración y, al ingresar, el visor se abre en
la misma URL. El coordinador sólo cierra los procesos propios.

### Visor en Administración (F3)

- **Ruta.** `/admin/predictivo` (`pages/AdminPredictivo.jsx`) muestra el mismo
  `HistoricalBacktest`, sin cambios de aspecto (capturas antes/después idénticas salvo las
  pantallas de sesión). El menú público ya no ofrece «Módulo predictivo»; el acceso está en la
  bandeja de Administración. `/mapa` es siempre el mapa público, también en `dev`.
- **Sesión.** Sólo un token vigente con rol `admin` muestra el visor (compuerta de interfaz; la
  API sigue validando cada consulta). Al vencer (60 min) un temporizador vuelve al ingreso sin
  enviar consultas; un 401 del servidor hace lo mismo. El ingreso es el mismo formulario de
  `/admin/reportes` (`components/AdminLoginForm.jsx`), con la misma clave de `sessionStorage`.
- **Estado en la URL.** `anio`, `se`, `vista`, `metodo`, `capa`, `radio` y `modelo` se conservan
  bajo la nueva ruta; el modo de divulgación nunca va en la URL. `/mapa?…` con alguno de esos
  parámetros redirige (replace) a `/admin/predictivo?…` sólo con sesión de administrador; si no,
  muestra el mapa público con el enlace «El módulo predictivo está en Administración».
- **Sin cambios** en la API, su prefijo `/api/v1/research/predictive`, `SIGARD_PRIVATE_VIEW`
  ni el modo protegido por defecto.

Prefijo único activo, en 127.0.0.1:8767 (F2): `/api/v1/research/predictive`:

- `GET /calendar`, `/geometry`, `/metadata`.
- `GET /comparison?year=2024&week=12` y proyecciones `/predicted`, `/observed`,
  `/metrics`, con `radio` opcional.
- `GET /history?start=2023-12-31&end=2024-12-22`, con `radio` opcional.
- `disclosure=presentation` es el valor predeterminado; `disclosure=private`
  solicita la consulta exacta local. No amplía acceso fuera del listener guardado.

Las antiguas rutas `/research/spatial` y `/research/backtest` no se montan en el
launcher final, evitando un camino alternativo sin protección de divulgación.
Sus fábricas y pruebas siguen disponibles para reproducción técnica histórica.
Parámetros desconocidos/duplicados y períodos inválidos se rechazan; artefactos
alterados bloquean sin fallback ni reentrenamiento.

La reconstrucción del paquete fuente conserva el procedimiento de
[etapa 3](database/historical-backtesting-stage3.md). El contexto climático se
compila aparte con `compile_context`, transacción `readonly, REPEATABLE READ`,
destino privado nuevo y puntero SHA-256 en
`data/interim/official/predictive-context-session-v1/registry.private.json`.
Las credenciales se leen del archivo privado existente, nunca de documentación
ni argumentos con contraseñas. Iniciar sólo el clúster privado 55439 cuando sea
necesario y apagarlo si se inició para esa operación. Docker y 5432 no se usan.

### Historia anual precalculada (P6.1)

La serie anual de todo el territorio (`/history` con el rango completo de un año del
catálogo y sin `radio`) era la respuesta más lenta: proyecta y protege cada semana del año
(unos 3–6,5 s por año) y, con 5 usuarios a la vez, las solicitudes se serializaban en el
proceso local. Ahora se precalcula offline con el mismo código del servicio:

```powershell
cd backend
.\.venv\Scripts\python.exe -B -m app.predictive_history build    # crea el paquete (no sobrescribe)
.\.venv\Scripts\python.exe -B -m app.predictive_history verify   # almacenada == calculada, todos los años y modos
```

- Paquete privado `data/interim/official/predictive-history-v1/`: un archivo por año del
  catálogo y modo de divulgación (`presentation`, `private`), 14 en total, cada uno listado
  en `manifest.private.json` con su SHA-256; `registry.private.json` fija el manifiesto.
- El manifiesto queda **ligado a sus entradas**: SHA-256 del registro del backtest, de cada
  registro de candidatos ML y del código que produce la historia (`predictive_service.py`,
  `backtest_results.py`, `predictive_ml.py`, `predictive_history.py`). Si cualquiera cambia,
  la historia anual responde 503 hasta reconstruir el paquete.
- La API administrativa local (`predictive_admin.build_service`, antes `app.research_local`) instala el paquete si existe. Con el paquete instalado la API **sólo lee
  y verifica** la historia anual, con el mismo mecanismo de verificación y caché por proceso
  (`local_bytes`): nunca la recalcula. Un archivo, manifiesto o registro alterado bloquea (503);
  un año del catálogo ausente del manifiesto también bloquea.
- Otros rangos y la historia de un radio (panel del radio) se siguen proyectando por solicitud
  (alrededor de 1,2 s por radio y año); precalcularlas requeriría unos 3 700 archivos.
- Sin entrenamiento, inferencia, SQL ni lectura de fuentes: sólo proyecta los paquetes ya fijados.
- Pruebas: `backend/tests/test_predictive_history.py` (fixtures ficticias con candidatos v1 y v2).
  Con los paquetes reales, `verify` confirmó 14/14 historias idénticas (16/11/2026).

## Validación, rendimiento y límites pendientes

Las pruebas ficticias verifican privacidad, consistencia, contratos, calendario,
purga temporal, ceros, faltantes, clima y archivo de comandos sin entrenar.
La verificación real separada contrasta PostgreSQL/PostGIS, polígonos y hashes
de tablas de sólo lectura. Navegador Chromium comprueba desktop/móvil, mapas,
modo protegido/privado, errores/reintentos, carreras de solicitudes y ausencia
de consultas privadas en producción. La simulación de viewport no acredita
pruebas en dispositivos físicos ni todos los navegadores.

Comandos pertinentes:

```powershell
.\backend\.venv\Scripts\python.exe -B backend/tests/publication_isolated.py --backend-regression
.\ml\venv\Scripts\python.exe -B -m pytest ml/tests/test_predictive_integration.py ml/tests/test_backtest_bundle.py ml/tests/test_ml_postgres_entrypoints.py -p no:cacheprovider
npm.cmd --prefix frontend run test:backtest
npm.cmd --prefix frontend run test:research
npm.cmd --prefix frontend run test:public-map
npm.cmd --prefix frontend run test:security
npm.cmd --prefix frontend run test:dev
npm.cmd --prefix frontend run lint
npm.cmd --prefix frontend run build
```

`test:predictive:browser` utiliza fixtures generadas en memoria; `-- --real`
consulta agregados privados locales. Requiere el Puppeteer existente o
`SIGARD_BROWSER_MODULE`, sin dependencias nuevas. Las mediciones incluyen fetch
y decodificación JSON, cinco muestras por operación y el primer render. Se
reportan resultados reales por alcance; no se infiere cumplimiento para cualquier
equipo, carga o red a partir de una prueba local.

El informe privado de cierre, pruebas, rendimiento antes/después, hashes y
capturas se guarda en
`data/interim/official/predictive-integration-stage4-20261102-v1/`, excluida de Git.
Las métricas científicas completas permanecen en la evidencia de etapa 2 y en la
consulta privada, sin reescrituras.

Continúan pendientes validación externa con datos nuevos no examinados,
disponibilidad histórica acreditada, evaluación prospectiva autorizada,
validación de asignaciones, control de cambios/revisiones, gobierno institucional
de datos, roles/auditoría y autorización de operación. 2024 no es un test externo.
El cierre técnico no sustituye esos requisitos.


## Integración ML 3: contrato aditivo y reproducción

Se reutiliza el release `sigard-two-candidates-reused-h1-20261103-v1` de ML 2.
Son 32 artefactos ya entrenados (dos componentes por 16 bloques temporales),
53.248 pares radio/semana y **208 semanas válidas para cada candidato** de
2021–2024. Esta disponibilidad se verificó desde los resultados y artefactos;
no se dedujo de las 208 semanas de referencias. 2020 no tiene ML retrospectivo
compatible, incluidas sus semanas 53; 2025/2026 permanecen fuera de cobertura.

`sigard_ml.forecasting.predictive_ml_bundle.compile_bundle(root, release_pin,
reference_reader, new_private_destination)` valida el release completo, hashes,
37 variables, purga, universo común y coincidencia exacta de observaciones y
referencias, y escribe únicamente una proyección JSON nueva. No carga joblib,
no predice nuevamente, no entrena y no requiere PostgreSQL encendido. El destino
debe ser nuevo dentro de `data/interim/official`; se rechaza sobrescritura.
El `reference_reader` es el lector existente `SnapshotReader`; `release_pin`
contiene la ruta relativa y SHA del release de ML 2. El valor retornado es el
puntero `{path, sha256}` al manifiesto generado.

El arranque local lee ese puntero de
`data/interim/official/ml-integration-stage3-20261103-v1/registry.private.json`.
`predictive_ml.py` verifica manifiesto, archivos semanales y bytes de los modelos
referenciados sin deserializarlos. La verificación no persiste entre peticiones.
Los modelos temporales deben respetar último objetivo ajustado < origen −28 días.
La compilación completa y su recibo están en el informe privado de ML 3; fuentes,
modelos, release y paquetes anteriores permanecen inalterados.

El contrato conserva `predicted` y `metrics` como referencias por compatibilidad.
Añade `ml` (metadatos por capacidad), `rows[].ml` (score, decisión, cantidad,
umbral, confusión y errores), `rows[].ml_availability`, `ml_metrics` y, en historia,
`ml_predicted` y `ml_by_year`. `model_version` anterior identifica referencias;
`ml.presence.model_version` y `ml.quantity.model_version` identifican candidatos.
El calendario incorpora `ml_availability` por capacidad, derivado de archivos
semanales verificados. La falta de resultado ML mantiene null y conserva la
referencia. Una incompatibilidad o alteración del archivo semanal/modelo bloquea
la capa ML con motivo explícito, sin sustituirla silenciosamente por persistencia.
Una alteración del manifiesto raíz o del paquete de referencia bloquea la consulta.

La interfaz de `/mapa` se describe en «Interfaz del módulo predictivo». La
evolución mantiene tres series: ML, persistencia y registro. Los huecos ML no se
interpolan. La privacidad se aplica antes de calcular
las métricas visibles: cualquier celda pequeña del registro, origen persistente
o cantidad estimada suprime también ML, scores, confusiones y diferencias. Los
totales de presentación son subconjuntos variables, nunca totales del estudio.

Los experimentos conservan `experimental_evaluated`, las referencias
`reference_selected`; ninguno es `operational_approved`. El endpoint de metadatos
y las limitaciones describen estas diferencias. No se crean rutas públicas,
selectores de algoritmos adicionales ni nuevas familias.

## Integración de candidatos v2 (campaña correctiva)

Campaña `sigard-two-capabilities-h1-corrective-20261112-v1`; informe privado
`data/interim/official/corrective-v2-20261112-v1/informe.private.md`. Decisión
científica **sin cambios**: ningún candidato promovido. Sin entrenamiento,
inferencia ni deserialización de estimadores.

**Bundle offline.** `sigard_ml.forecasting.predictive_ml_bundle_v2.compile_bundle(root,
campaign_folder, reference_reader, new_private_destination)`:

- verifica el hash canónico del protocolo congelado (`a7dc47f9…`, igual al código
  `motor_protocol_v2.PROTOCOL` y a `protocol-before-fit`), el pin de la matriz v2
  (`2c09895c…`) en `matrix-before-fit` y en el manifiesto previo al ajuste, los
  **48 artefactos** del registro (16 bloques × rf_v2, logit_v2, residual_v2; sólo
  hash) y las 53.248 predicciones guardadas;
- comprueba universo de 256 radios, h=1, purga (último objetivo < primer origen −28
  días) y pareo exacto con observación y persistencia del paquete de referencia;
- resuelve offline la regla **top-10** con el desempate prerregistrado
  (`motor_features_v2.topk_select`, permutación semillada por semana sobre radios
  ordenados) y guarda por fila `topk_rank` (1–256); en/fuera del top-10 se deriva
  como `rank <= k`;
- antes de escribir exige reproducir exactamente los aciertos y onset congelados de
  `metrics.private.json` (desarrollo por año y 2024) y el MAE de residual_v2;
- escribe sólo en un destino nuevo bajo `data/interim/official`: manifiesto
  `sigard-predictive-ml-overlay/2` con candidatos, regla (`top_k`, k=10, o
  `count_estimate`), estado `experimental_not_promoted`, evidencias con SHA y un
  JSON por semana.

Compilado el 14/11/2026 en
`data/interim/official/ml-integration-v2-20261114-v1/` (`bundle-v2/`, 208 semanas,
manifiesto `e9752119…`; `registry.private.json` es el puntero que lee el arranque).

**Backend.** `predictive_admin.build_service` (antes `app.research_local`) fija al iniciar los punteros v1 y v2 instalados;
cada petición vuelve a verificar manifiestos, semanas y bytes de artefactos.
`predictive_ml.MLProjection` lee ambos esquemas y expone candidatos desde cada
manifiesto (varios por capacidad). Contrato `/2`:

- `ml[candidato]`: capacidad, estado, regla de decisión, campaña, decisión de
  promoción (`not_promoted`), disponibilidad, versión, ajuste, variables y SHA.
- `rows[].ml[candidato]`: `presence_score`, `presence`, `presence_threshold` (v1) o
  `topk_rank` y `onset_eligible` (v2), `quantity`, `confusion`, `difference`,
  `absolute_error`; `rows[].ml_availability[candidato]`.
- `ml_metrics[candidato]` por semana; en historia, `ml_predicted[candidato]`,
  `ml_metrics` y `ml_by_year[año][candidato]`, calculados en el servidor.
- Candidatos top-k: `ml_metrics[...].topk` con recall@10, onset@10 y precisión@10
  **sólo en modo privado** (todos los radios comparables). En modo protegido se
  devuelve `status: private_only_selection_bias` con valores null: la misma regla
  ya aplicada a precisión y falsas alarmas, porque el subconjunto visible (≥5
  registros) excluye todas las falsas alarmas y todos los onset (origen 0).
- `/calendar` y `/metadata`: `experimental_candidates`, `default_candidates`
  (`rf_v2_city_propensity`, `residual_v2` si están instalados) y
  `weeks[].ml_availability[candidato]`, derivada del manifiesto verificado.
- Una alteración de una semana o artefacto bloquea sólo esa proyección
  (`ml_integrity_or_compatibility_blocked`); v1 y la referencia se conservan. Un
  manifiesto que declare promoción, calibración o una regla inválida bloquea el
  módulo (503).
- Los artefactos sólo se hashean (una vez por proceso, ver caché abajo); su límite es 64 MiB (los RF v2 de 2024-q3/q4
  pesan ~20 MB y superaban el límite de 16 MiB de los JSON).

Las métricas por año del servidor reproducen las congeladas: recall@10 2021
75/513, 2022 7/47, 2023 32/152 (desarrollo 114/712 = 0,160), 2024 124/1.771;
onset 7/345, 3/43, 14/127; MAE de residual_v2 0,0673 / 0,0058 / 0,0186 y 2024 0,3525.

**Frontend.** El selector «Modelo ML» se arma con `experimental_candidates` de la
metadata (filtrado por pregunta) y se guarda en la URL como `modelo`; por defecto
`rf_v2_city_propensity` en ¿Dónde? y `residual_v2` en ¿Cuántos?. El contrato valida
estados permitidos, `not_promoted`, regla por capacidad, presencia = `rank <= k`,
nunca más de k radios y exactamente k cuando los 256 radios son visibles, y la
retención de recall@k en modo protegido. Ayuda en lenguaje simple: «Marca los 10
radios con mayor prioridad cada semana». Veredictos fijos (`GLOBAL_VERDICTS`):

- rf_v2: «Resultado similar al método de repetir la semana anterior (recall@10
  0,160 frente a 0,156; diferencia no significativa). Mejor que los modelos
  anteriores.»
- residual_v2: «Error promedio 13,6 % menor que repetir la semana anterior en
  2021–2023 (diferencia con intervalo de confianza que excluye 0). Subestima
  semanas de muchos casos.» 13,6 % = (0,035357 − 0,030535) / 0,035357 con los MAE
  sin redondear; con los redondeados (0,0305/0,0354) se obtendría 13,8 %.
- Ambos: «2024 es una comparación ya observada; ningún modelo está aprobado para
  uso operativo.»

**Verificación de integridad con caché por proceso** (14/11/2026,
`backend/app/experimental_results.py`). Cambio de garantía:

- Antes: cada solicitud recalculaba el SHA-256 completo de cada JSON y artefacto que
  leía (los artefactos, una vez por solicitud).
- Ahora: el SHA-256 completo se calcula la primera vez que el proceso usa un archivo
  y se recuerda por ruta resuelta, tamaño, `st_mtime_ns` y hash esperado. Mientras
  esos cuatro valores coincidan, no se vuelve a hashear (los artefactos tampoco se
  vuelven a leer: `verify_local`). Si cambia la ruta, el tamaño, la fecha de
  modificación o el hash fijado, se verifica de nuevo y se bloquea si no coincide;
  una verificación fallida nunca se guarda. Las comprobaciones de ruta, enlaces,
  traversal y límite de tamaño se siguen haciendo en cada lectura.
- Límite: una modificación local que conserve exactamente tamaño y `st_mtime_ns`
  (p. ej., restaurar la fecha con `os.utime`) no se detecta hasta reiniciar la API.
  Es aceptable porque la API es local, de sólo lectura y los archivos privados están
  bajo control del responsable; reiniciar el proceso fuerza la verificación completa.
- Pruebas: `backend/tests/test_integrity_cache.py` (sin cambios no re-hashea; mismo
  tamaño con otra fecha bloquea; otro tamaño u otro hash esperado bloquea; límites y
  traversal se mantienen) y
  `test_unchanged_artifacts_are_not_rehashed_across_requests_but_same_size_edits_block`.

**Rendimiento** (14/11/2026, local, `test:predictive:browser`, API reiniciada en cada
corrida, sin verificación de producción):

| Medición | Real (3 corridas válidas) | Ficticio (3 corridas) |
|---|---|---|
| Arranque en frío hasta la semana por defecto | 3,87 / 3,98 / 4,02 s | 1,42 / 1,47 / 1,57 s |
| Semana siguiente | 0,46–0,50 s | 0,23–0,25 s |
| Semana anterior (en caché del cliente) | 0,19–0,21 s | 0,15–0,17 s |
| Cambio de año | 0,35–0,40 s | 0,09–0,14 s |

Una corrida real adicional, la primera tras reiniciar Vite, tardó 6,11 s y no superó
el umbral de 5 s del script (compilación inicial de Vite); se descartó y se repitió.
Antes del caché: 4,02–4,38 s. El arranque en frío casi no cambia por diseño: la
primera solicitud de un proceso verifica todo. En proceso, la semana protegida
tarda 0,12 s en frío y 0,09 s después; la historia anual protegida tarda
~1,8–2,1 s con o sin caché (2,2–3,6 s por HTTP), dominada por las comprobaciones
de rutas y enlaces (~0,75 s) y la lectura/decodificación de los JSON semanales, no
por el hash. El caché evita re-hashear los artefactos RF v2 (~20 MB) entre
solicitudes. El calendario sigue en ~0,13 s.

### Interfaz del módulo predictivo

La vista local de `/mapa` («Predicción semanal de dengue por radio censal») está
orientada a usuarios no técnicos y se rotula como prototipo experimental de
reconstrucción histórica, sin uso operativo. Sólo presenta valores ya protegidos
por la API; las reglas de redacción están centralizadas en
`frontend/src/services/predictiveView.mjs` y no calculan métricas nuevas.

- **Controles**: línea de tiempo semanal (`WeekTimeline`) con años evaluables,
  pregunta **¿Dónde?** / **¿Cuántos?**, método **Modelo ML** / **Método de
  referencia** / **Comparar**, selector **Modelo ML** con los candidatos de la
  pregunta (v2 por defecto) y, en ¿Cuántos?, capa **Esperados** / **Observados**.
  Sin capa ML disponible sólo se ofrece la referencia. Se indica la fecha hasta la
  que se usaron datos y el clima de la semana previa (un único punto urbano).
- **Opciones avanzadas**: modo de divulgación, selección de un radio por código y
  versiones de dataset/política. El detalle de un radio se abre en `RadioPanel`.
- **Secciones plegables**: «¿Qué tan bien funciona el modelo?» (`ModelPerformance`:
  veredicto documentado del cierre de candidatos, cifras por año y métricas
  técnicas con su nomenclatura TP/FP/FN/TN), «Ver datos en tabla» (`DataTable`) y
  «Cómo leer esta pantalla y limitaciones».
- **Semana por defecto**: si la URL no indica una semana, se abre la semana con
  más radios divulgables en el modo activo dentro del último año evaluable
  (desempates: más registros, luego la semana más reciente). Al cambiar de año
  se aplica el mismo criterio. El criterio depende de actividad divulgable, no del
  desempeño de ningún método. Un botón lleva a la semana más activa entre los
  años ya cargados.
- **Estado en URL**: `anio`, `se`, `vista` (`donde`/`cuantos`), `metodo`
  (`ml`/`referencia`/`comparar`), `capa=observados` y `radio` (nueve dígitos) se
  leen y escriben con `replace`. Valores inválidos vuelven al predeterminado. El
  modo de divulgación nunca se lee ni se escribe en la URL: un enlace compartido
  siempre abre en modo protegido.
- **Carga**: calendario, geometría y metadatos se piden juntos; la semana nombrada
  en la URL se anticipa. El historial de otros años se carga de a uno después del
  primer mapa. Las respuestas se guardan sólo en memoria de la página, con clave
  que incluye el modo de divulgación; no se usa almacenamiento del navegador y
  «Reintentar» vacía esa caché.
- **Modo privado**: al elegir «Investigación privada · valores exactos» se muestra
  el aviso permanente «Modo privado: no proyectar ni compartir capturas», la
  leyenda completa (incluidas falsas alarmas y radios correctamente sin alerta)
  y las cifras por año. Al volver a protegido, el aviso desaparece.
- **Sesgo de selección en modo protegido**: el modo protegido sólo muestra radios
  con cinco o más registros, por lo que el subconjunto visible excluye por
  construcción falsas alarmas y radios sin registros. Por eso, en ese modo las
  tarjetas hablan de «radios visibles» y no presentan precisión, falsas alarmas,
  aciertos ni anticipación como desempeño; la leyenda omite categorías y rangos
  imposibles; las cifras por año sólo aparecen en modo privado, y una semana sin
  radios divulgables se resume con una sola explicación. «Protegido» nunca
  significa cero.
- **Mapa base de calles**: `BacktestMaps` agrega la capa de OpenStreetMap ya usada
  por los otros mapas (misma URL y atribución, ya permitida por la CSP), atenuada
  en gris sólo en el panel de mosaicos de este mapa, con zoom 11–17 y límites
  alrededor del universo común. «Mostrar calles» (casilla, activada por defecto)
  la oculta; en Comparar ambos mapas comparten capa y encuadre. Las peticiones de
  mosaicos se envían sin referrer y sólo contienen `z/x/y` del área de la ciudad;
  ningún dato de radios, registros, predicciones ni parámetros de la aplicación.
  Sin conexión el mapa sigue con el fondo liso y el aviso «Mapa de calles no
  disponible sin conexión». El visor privado autocontenido se construye con la
  capa desactivada (`VITE_SIGARD_BASEMAP=off`) y su build rechaza cualquier URL
  de mosaicos.
- **Codificación de zona**: los rellenos son semitransparentes sobre las calles;
  los radios con registros se marcan con trama diagonal sobre todo el polígono
  (nunca puntos ni marcadores) y los protegidos sólo con contorno fino punteado y
  trama suave. Los colores indican radios censales completos; no representan
  domicilios ni ubicaciones exactas.

La prueba `frontend/security/predictive-view.test.mjs` (incluida en
`test:backtest`) verifica estas reglas con fixtures ficticias, y
`frontend/scripts/predictive.browser.mjs` recorre la interfaz en Chromium local;
sus capturas se guardan como archivos privados ignorados por Git. Por defecto
bloquea los mosaicos (modo sin conexión, sin depender de internet); con `--tiles`
deja pasar sólo mosaicos de OpenStreetMap tras verificar coordenadas, área,
ausencia de parámetros y de referrer.

La verificación ML 3 usa fixtures exclusivamente ficticias, la regresión existente
y navegación Chromium local desktop/móvil. PostgreSQL/PostGIS no se inició ni se
modificó: la compatibilidad territorial procede del paquete verificado y la
evidencia anterior, no de una nueva prueba SQL. El rendimiento del calendario
completo puede superar cinco segundos; las medidas reales por operación y los
límites de dispositivo/navegador están en el cierre privado ML 3.
