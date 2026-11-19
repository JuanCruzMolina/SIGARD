# Registro de decisiones técnicas (ADR)

Formato breve: **contexto → decisión → alternativas descartadas → consecuencias**. Estado de
todas las decisiones: *aceptada*, vigente en `v0.9.1-aceptacion` (noviembre de 2026).

| N.º | Decisión | Área |
|---|---|---|
| [ADR-01](#adr-01--fastapi-para-las-apis) | FastAPI para las APIs | Backend |
| [ADR-02](#adr-02--leaflet-con-openstreetmap) | Leaflet con OpenStreetMap | Frontend |
| [ADR-03](#adr-03--scikit-learn-para-los-modelos) | scikit-learn para los modelos | ML |
| [ADR-04](#adr-04--postgresql-con-postgis) | PostgreSQL con PostGIS | Datos |
| [ADR-05](#adr-05--regla-top-k-en-dónde) | Regla top-k en ¿Dónde? | ML / producto |
| [ADR-06](#adr-06--protección-de-celdas-menores-a-5-y-bloques-fijos) | Protección de celdas menores a 5 y bloques fijos | Privacidad |
| [ADR-07](#adr-07--prerregistro-del-protocolo-v2) | Prerregistro del protocolo v2 | ML / método |
| [ADR-08](#adr-08--alertas-sólo-internas-con-aprobación-humana) | Alertas sólo internas con aprobación humana | Producto |
| [ADR-09](#adr-09--historia-anual-precalculada) | Historia anual precalculada | Rendimiento |

---

## ADR-01 · FastAPI para las APIs

**Contexto.** Hacía falta una API para reportes ciudadanos, administración y lectura de
resultados, mantenida por un equipo chico que ya trabaja en Python para la preparación de datos
y el ML.

**Decisión.** FastAPI 0.115 con Pydantic, SQLAlchemy 2 y Alembic, servida por uvicorn.

**Alternativas descartadas.**
- Django: más estructura de la necesaria, y su ORM y su administración no aportaban al caso.
- Node/Express: hubiera exigido un segundo lenguaje en el servidor y duplicar validaciones que
  ya existían en Python.

**Consecuencias.**
- Validación declarativa de entrada (longitudes, enums, `SecretStr`) y dependencias reutilizables
  para la autorización (`get_current_admin` en las 27 rutas administrativas).
- Mismo lenguaje que `ml/`. Aun así, el entrenamiento **nunca** se ejecuta dentro del backend:
  sólo se leen paquetes congelados.
- Un proceso uvicorn serializa el trabajo intensivo de CPU (GIL). Se mitigó con paquetes
  precalculados (ADR-09).

## ADR-02 · Leaflet con OpenStreetMap

**Contexto.** Los mapas muestran polígonos de radios censales y puntos de centros de salud. El
proyecto no tiene presupuesto para servicios cartográficos pagos, y los datos no deben salir
hacia terceros.

**Decisión.** Leaflet 1.9 con react-leaflet. Los polígonos son GeoJSON propios. Las teselas de
calles de OpenStreetMap son **opcionales**: sin conexión, el mapa sigue funcionando con la
geometría local y un fondo atenuado.

**Alternativas descartadas.**
- Google Maps o Mapbox: requieren licencia o clave y envían datos de uso a terceros.
- MapLibre con teselas vectoriales: más capacidad de la necesaria y mayor peso del bundle.

**Consecuencias.**
- Se mantiene la atribución de OpenStreetMap.
- Ningún dato epidemiológico ni ubicación de reportes viaja al proveedor de teselas: sólo se
  piden imágenes de calles.
- Las pruebas de navegador bloquean las teselas para medir sin depender de Internet.

## ADR-03 · scikit-learn para los modelos

**Contexto.** Hay datos tabulares por radio y semana, con pocas filas positivas y fuerte
desbalance. La evaluación tiene que ser reproducible y la ejecución offline en un equipo común.

**Decisión.** scikit-learn 1.9:
- `RandomForestClassifier` para presencia (400 árboles, semillas fijas; v1 con
  `balanced_subsample`, v2 sin ponderación de clases y `max_features=0.5`);
- `HistGradientBoostingRegressor` sobre el residuo de la persistencia en cantidad (v2 con
  pérdida absoluta: estimado = máx(0, persistencia + 0,5 · residuo));
- baselines simples (persistencia, estacionalidad) como referencia obligatoria.

**Alternativas descartadas.**
- Redes neuronales o modelos espacio-temporales profundos: con este volumen de datos tienen alto
  riesgo de sobreajuste y menor interpretabilidad.
- XGBoost o LightGBM: sin una ventaja demostrada que justificara una dependencia más.

**Consecuencias.**
- Entrenamiento determinista con semillas declaradas y artefactos versionados por hash fuera de
  Git.
- Los puntajes del RF **no están calibrados**: no se presentan como probabilidades (ADR-05).

## ADR-04 · PostgreSQL con PostGIS

**Contexto.** El sistema maneja geometrías oficiales de 263 radios y puntos de reportes, y
necesita integridad referencial, restricciones y auditoría transaccional.

**Decisión.** PostgreSQL con PostGIS en **dos bases separadas**:
- **API pública**: reportes con columna `geom` generada, índices espaciales, restricciones
  `CHECK` y bloqueos advisory para las cuentas;
- **Investigación**: clúster propio en `127.0.0.1:55439`, PostgreSQL 16 / PostGIS 3.4, con 4
  esquemas y 91 tablas.

**Alternativas descartadas.**
- Una única base: mezclaría datos sanitarios privados con la operación pública.
- SQLite en producción: sin tipos espaciales nativos ni concurrencia adecuada. Se usa sólo en
  demos y pruebas.

**Consecuencias.**
- Migraciones Alembic separadas. La cadena pública se verificó en PostGIS real (11/11 pasos).
- Las pruebas corren aisladas en SQLite. Las 6 pruebas PostGIS que exigen Docker quedan como
  límite documentado.

## ADR-05 · Regla top-k en ¿Dónde?

**Contexto.** Los puntajes de presencia no están calibrados. En el diagnóstico, los umbrales
fijos quedaban por encima de casi todos los positivos en algunos años y generaban declaraciones
masivas en otros. Un umbral único no era estable.

**Decisión.** Cada semana se priorizan los **k = 10 radios** con mayor puntaje
(`rf_v2_city_propensity`). Los empates se resuelven con una permutación semillada por semana. La
regla se fijó **antes** de ver los resultados de evaluación (ADR-07) y se resuelve offline: el
paquete guarda el puesto de cada radio.

**Alternativas descartadas.**
- Umbral de probabilidad: los puntajes no son probabilidades.
- Calibración posterior: requería datos fuera de muestra que no estaban disponibles sin
  reabrir la evaluación.

**Consecuencias.**
- Carga de trabajo predecible: 10 radios por semana.
- Se evalúa con recall@10 y onset@10. En **modo protegido** esas métricas no se muestran: el
  subconjunto visible (≥ 5 registros) excluye falsas alarmas e inicios de brote, y daría una
  cifra sesgada.

## ADR-06 · Protección de celdas menores a 5 y bloques fijos

**Contexto.** Con pocos casos por zona, publicar conteos exactos (incluido el cero) permite
inferir situaciones individuales. Además, cualquier total complementario permite deducir
celdas ocultas por resta.

**Decisión.**
- **Mínimo 5** en toda salida derivada de datos epidemiológicos: visor
  (`sigard-local-presentation-minimum5-v1`), alertas, exportaciones y mapa público. El cero
  también se protege.
- En «Actividad registrada»:
  - **bloques fijos de 4 semanas que no se solapan** (la SE53 se une al último bloque), porque
    ventanas móviles permitirían deducir valores por diferencia;
  - población mínima de 100 por radio;
  - supresión complementaria calculada contra un **atacante del peor caso**;
  - informe de riesgo que exige 0 revelaciones;
  - 2022 excluido por no ser comparable.

**Alternativas descartadas.**
- Ruido diferencial: con conteos tan bajos destruye la utilidad y es difícil de explicar.
- Mapa de calor kernel: permite inferir ubicaciones en zonas con pocos casos.

**Consecuencias.** Con datos reales, el 96,5 % de las celdas queda protegido: la vista informa
sobre todo en el brote de 2024. Es una pérdida de detalle aceptada a cambio de que ninguna celda
se pueda deducir.

## ADR-07 · Prerregistro del protocolo v2

**Contexto.** La primera campaña no superó a los baselines. Una segunda campaña corría el riesgo
de ajustar decisiones después de ver resultados (bifurcaciones del análisis), sobre todo con
2021–2023 ya muy usados.

**Decisión.** El protocolo v2 (`sigard-two-capabilities-h1-corrective-20261112-v1`) se
**versionó antes del ajuste** (commit `947f71c`) y se ejecutó después (commit `497af4e`). El
protocolo fija:
- candidatos, variables y la regla top-10;
- criterios de éxito P1–P3 (presencia) y Q1–Q2 (cantidad);
- walk-forward con purga de 28 días;
- semillas y hash canónico.

**Alternativas descartadas.** Explorar hiperparámetros y elegir el mejor: hubiera invalidado la
comparación con la persistencia.

**Consecuencias.**
- El resultado es creíble: `residual_v2` reduce el MAE un 13,6 % frente a `count_latest`, con
  IC95 de ΔMAE [−0,00823; −0,00195].
- También quedó registrado lo que **no** se cumplió (Q2 y P1–P3), y por eso ningún candidato se
  promovió.
- Una verificación independiente reprodujo las 28 cifras.

## ADR-08 · Alertas sólo internas con aprobación humana

**Contexto.** Los modelos son experimentales, no están promovidos y se evaluaron en
reconstrucción retrospectiva. Una alerta pública mal calibrada puede generar alarma o
estigmatizar barrios.

**Decisión.**
- Las reglas generan **candidatas** que un administrador aprueba, con comentario obligatorio, o
  descarta, con un motivo.
- Los avisos aprobados son **internos**: no hay correo, SMS ni publicación.
- La publicación ciudadana está bloqueada en el código (ruta que responde 409 y queda auditada)
  y en el esquema (`CHECK` sin estado «publicada»).
- La evaluación semanal es manual.

**Alternativas descartadas.**
- Alertas automáticas a la población: fuera del alcance ético y técnico del prototipo.
- Notificaciones por correo: exponen datos fuera del sistema.

**Consecuencias.** Toda alerta tiene una persona responsable y queda auditada. Mitigan las
falsas alarmas la regla de semanas consecutivas (1–4) y la frecuencia histórica que se muestra
antes de guardar una regla.

## ADR-09 · Historia anual precalculada

**Contexto.** Con 5 usuarios simultáneos, la carga del visor superaba los 5 s
(p95 33,5 s en P6). `/history` recalculaba y volvía a verificar la serie anual en cada pedido
(≈ 6,5 s por año), y las solicitudes se serializaban en un único proceso.

**Decisión.**
- La serie anual de todo el territorio se precalcula **offline con el mismo código del servicio**,
  un archivo por año y modo de divulgación.
- Los archivos quedan en un manifiesto con su SHA-256, verificado con el mecanismo existente.
- El manifiesto queda **ligado a sus entradas**: registro del backtest, registros ML y hash del
  código. Cualquier cambio bloquea la historia (503) hasta reconstruirla.
- La API sólo lee y verifica.

**Alternativas descartadas.**
- Caché en memoria por proceso: servía un resultado calculado sin un vínculo explícito con sus
  entradas y no sobrevivía a reinicios.
- Precalcular también la historia por radio: unos 3 700 archivos, por una consulta que ya cumple.

**Consecuencias.**
- `/history` pasó de ≈ 6,5 s a 0,08 s.
- En producción, las 6 operaciones cumplen p95 < 5 s con 1 y con 5 usuarios.
- Las pruebas exigen que la historia almacenada sea idéntica a la calculada para todos los años,
  modos y candidatos, y que un archivo alterado bloquee.
- Hay que reconstruir el paquete al cambiar cualquiera de sus entradas.
