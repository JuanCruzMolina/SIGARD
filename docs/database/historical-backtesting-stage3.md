# Backtesting histórico local · etapa 3

> Integración vigente: el panel se reutiliza como módulo principal y las rutas
> activas pasan a `/api/v1/research/predictive`, con divulgación protegida por
> defecto. Este documento conserva el contrato técnico de etapa 3. Ver
> [ejecución y arquitectura final](../predictive-module-final.md).

La funcionalidad compara resultados offline de la campaña seleccionada en la etapa 2
con registros elegibles del dataset PostgreSQL consolidado en la etapa 1. No ajusta
modelos durante las consultas, cambia etiquetas ni genera predicciones operativas.

## Versiones y métodos

- Dataset: `sigard-consolidated-history-20261102-v1`.
- Política: `sigard-project-positive-2022-covered-2020-2024-v1`.
- Campaña: `sigard-predictive-motor-h1-20261102-v1`.
- Contrato: `sigard-historical-backtest/1`.
- Presencia: `presence_seasonal`, referencia territorial y estacional seleccionada.
- Cantidad: `count_latest`, persistencia del último cierre, también baseline.

Son referencias estadísticas. Ningún candidato ML fue promovido en la etapa 2.
Esta funcionalidad conserva la selección y todos los resultados históricos A/B,
V1/V2/V3 y Poisson. No mezcla sus etiquetas ni recalcula sus inferencias.

El calendario argentino versionado conserva las semanas 53. Las opciones proceden
del calendario registrado, no de semanas ISO ni de nombres de archivos. Los años
fuera de cobertura aparecen expresamente como no disponibles. El período inicial
sin resultados de la etapa 2 conserva observaciones y devuelve falta de soporte.

## Compilación reproducible offline

`sigard_ml.forecasting.backtest_bundle` abre una transacción PostgreSQL de sólo
lectura con aislamiento `REPEATABLE READ`. Verifica la campaña, política, hashes
del código congelado, dataset, cierre experimental y métodos seleccionados.
Reproduce las referencias con los cortes originales de cada bloque y compara cada
resultado contra `analytics.motor_prediccion`, sin llamar a entrenamiento,
calibración o deserialización de estimadores. Rechaza resultados incompletos,
fechas incompatibles y ajustes sin la separación temporal de cuatro semanas.

Ejemplo desde la raíz, con el clúster privado autorizado en 55439:

```powershell
.\ml\venv\Scripts\python.exe -B -m sigard_ml.forecasting.backtest_bundle `
  --connection data/interim/official/database-normalized-20261028-v1/connection.private.json `
  --config data/interim/official/predictive-motor-stage2-20261102-v1/configuration.private.json `
  --output data/interim/official/historical-backtest-rebuild-v1
```

La salida debe ser nueva y estar dentro de la carpeta privada excluida de Git.
El compilador no imprime credenciales ni sobrescribe resultados anteriores. Genera
un manifiesto con SHA-256 de calendario, geometrías poligonales, metadatos y cada
semana. Sólo proyecta agregados y delimitaciones territoriales; no extrae personas,
clasificaciones individuales ni coordenadas clínicas. No modifica PostgreSQL.

El puntero privado de la sesión local es
`data/interim/official/historical-backtest-session-v1/registry.private.json`.
Contiene `local_read_authorized: true`, `manifest_path` relativo al repositorio y
`manifest_sha256`. El launcher fija su hash al iniciar. Reproducir un paquete en
otra carpeta no reemplaza automáticamente el puntero ni activa predicciones.
Para revisar otra copia, verificar sus hashes y actualizar explícitamente ese
puntero privado, conservando la evidencia anterior; reiniciar el servicio local.

## Consulta local e interfaz

`npm.cmd --prefix frontend run dev` inicia el coordinador local existente. En
`http://127.0.0.1:5173/mapa`, elegir **Backtesting histórico**. Se mantienen las
vistas anteriores. El servidor de resultados funciona con PostgreSQL apagado.

La vista ofrece año y semana, presencia/cantidad, selección de radio, dos mapas
sin proveedores externos con encuadre y escala sincronizados, tabla territorial,
intervalo temporal, gráfico con discontinuidades y errores por semana y año.
La tabla conserva precisión numérica para calcular métricas; el redondeo es sólo
de presentación. Los valores desconocidos nunca se convierten en cero.

La API de lectura usa el listener existente `127.0.0.1:8765`, con prefijo
`/api/v1/research/backtest`:

- `GET /calendar`: calendario, estados y unidades territoriales.
- `GET /geometry`: exclusivamente polígonos territoriales y máscara común.
- `GET /metadata`: métodos seleccionados, versiones y limitaciones.
- `GET /comparison?year=2024&week=12[&radio=...]`: predicción, registros, baseline,
  errores y métricas de la misma proyección.
- `GET /predicted`, `/observed`, `/metrics`: misma selección, proyecciones acotadas.
- `GET /history?start=YYYY-MM-DD&end=YYYY-MM-DD[&radio=...]`: evolución continua,
  huecos explícitos, métricas agregadas y por año.

`year`/`week` son epidemiológicos; `start`/`end` son inicios de semanas del catálogo.
Parámetros desconocidos o duplicados se rechazan. Semana inválida: 400; radio
inexistente: 404; paquete ausente, alterado o inconsistente: 503. Falta de soporte,
fuera de cobertura o máscara territorial: respuesta estructurada sin predicción,
nunca un error convertido en resultado cero. Para una selección territorial,
`period_availability_status` conserva el estado de la semana y
`availability_status` expresa el de esa unidad.

El proceso HTTP usa únicamente JSON acotado y verificado, con lista explícita de
campos permitidos. No importa PostgreSQL, sklearn, joblib ni pickle en el lector
de backtesting. La API pública de FastAPI no registra estas rutas. Se conservan
los controles de loopback, Host, Origin exacto, rechazo de proxies y cabecera
`X-Sigard-Research: local-read`, con `no-store`. No hay cookies ni enlaces públicos
a archivos privados. Si falta el paquete, el backtesting falla cerrado sin impedir
el uso de los resultados A/B existentes.

## Semántica de datos y métricas

Las respuestas distinguen `predicted`, `observed`, `baseline`,
`availability_status`, `origin_week`, `origin_end`, `target_week`, `target_end`,
`model_version`, `data_policy_version`, `territorial_quality` y `evaluation_type`.
Este último es `event_time_retrospective_reconstruction`: las fechas de eventos
permiten la reconstrucción temporal, pero no acreditan llegada ni revisión
histórica de todas las fuentes. Cada versión de método identifica campaña y
bloque; no implica que persistencia sea un modelo ML entrenado.

El conjunto comparable utiliza la máscara común versionada de 256 radios del
universo de 263. Los siete restantes se muestran como no comparables, conservando
sus agregados asignados sólo en la conciliación departamental. El total estimado
es del subconjunto comparable; no se acredita como predicción departamental.
La conciliación separa registros comunes, asignados fuera de máscara y sin radio.
Una suma de celdas no se presenta como cantidad de casos.

La positividad experimental SIGARD de registros elegibles de la entrega 2022
conserva las clasificaciones clínicas originales. Los ceros cubiertos proceden de
la declaración metodológica del responsable para 2020–2024, sin certificar
vigilancia institucional completa. No se reinterpretan fechas de 2021 de aquella
entrega como fechas de 2022. En 2024 se distinguen semanas con registros de las
posteriores con cero por cobertura declarada.

Las métricas usan exactamente las filas comparables del mapa: Brier, AP (agrupando
empates), ROC-AUC cuando hay dos clases, precisión, recall, F1, matriz TP/FP/FN/TN,
calibración descriptiva, MAE, RMSE, sesgo, errores en ceros y en actividad y baseline.
Una métrica sin denominador queda nula. Las probabilidades sanitarias calibradas
no están acreditadas. Las asignaciones pueden ser aproximadas; el conteo es de
registros elegibles de investigación. El clima de un punto no es una medición por
radio y los métodos seleccionados no lo utilizan. 2024 ya fue examinado y no es
validación externa ni prospectiva.

## Pruebas

Las pruebas de software generan datos y polígonos abstractos; no usan fuentes
clínicas ni aportan métricas al estudio:

```powershell
.\ml\venv\Scripts\python.exe -B -m pytest ml/tests/test_backtest_bundle.py -q -p no:cacheprovider
.\backend\.venv\Scripts\python.exe -B backend/tests/publication_isolated.py --backend-regression
npm.cmd --prefix frontend run test:backtest
npm.cmd --prefix frontend run test:research
npm.cmd --prefix frontend run lint
npm.cmd --prefix frontend run build
```

`frontend/scripts/backtest.browser.mjs` verifica controles, mapas sincronizados,
semana 53, semanas conocidas con cero, falta de soporte, fuera de cobertura,
selección territorial, intervalos, fallos/reintentos y respuestas obsoletas. Por
defecto intercepta con fixtures generadas en memoria. `--real` consulta únicamente
el paquete privado verificado y guarda capturas privadas. Requiere el Puppeteer
ya disponible en el entorno o `SIGARD_BROWSER_MODULE`, sin nuevas dependencias.
La comprobación de producción verifica que no se consulten estas rutas.

El informe, los snapshots de las tablas, los hashes, la verificación del paquete y
los recibos de navegador se guardan exclusivamente en
`data/interim/official/historical-backtest-stage3-20261102-v1/`, excluida de Git.
La evidencia de software ficticia se mantiene separada de la verificación real
contra PostgreSQL. No se inicia la etapa 4.
