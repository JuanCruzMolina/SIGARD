# SIGARD: consolidación técnica de las etapas 1 a 16

**Preparación de etapa 16 — 20/10/2026, `entrenamiento-ML`:** inicio nuevo con el
comando habitual, frontend 5173 y A/B 8765 exclusivamente en `127.0.0.1`.
La API pública persistente y administración siguen siendo independientes.
Se corrigió un defecto demostrado de tabulación: los tooltips hacían que Chromium
recorriera los 263 polígonos antes del selector. Las vistas con selector textual
retiran esos paths de Tab; conservan clic/hover y controles existentes. Se añadió
la comprobación al harness integral, sin nuevo módulo ni dependencia.

Regresión: **1.042 aprobadas, cero fallidas, una omitida PostgreSQL real**;
cuatro casos ML deseleccionados y ocho módulos excluidos, con entrenamiento/carga
de modelos bloqueados. Lint, build y 178 controles de seguridad aprobados.
11 grupos de navegador sobre API/SQLite ficticios, revisión visual a 1440/390 px
y prueba adicional de Tab/Enter, historial y reintento A/B; cero excepciones JS.
Se conciliaron nuevamente 10.520 filas, 36 métricas y 20 semanas congeladas.
Nombres accesibles y contraste de muestras comprobados mediante CDP; lector de
pantalla, móvil físico y auditoría integral pendientes.

No se accedió a las bases del servicio 5432 ni se inició PostgreSQL/Docker.
Migraciones PostgreSQL compiladas offline en ambos sentidos y reversión
administrativa SQLite comprobada; concurrencia/PostGIS real **no verificados**.
El [procedimiento aislado pendiente](../backend/README.md#ensayo-postgresqlpostgis-descartable--preparación-de-etapa-16)
define puertos 5434/5435, bases separadas y limpieza, sujeto a autorización.
El [guion de siete minutos](SIGARD-resumen-desarrollo.md#8-guion-académico-de-siete-minutos)
incluye servicios, checklist y condiciones que impiden cada recorrido.
Estado: preparado para demostración académica experimental, no validado para
utilización epidemiológica real. La matriz conserva **15 completas, 8 parciales
y 3 bloqueadas**. Sin commits, cambios de rama ni modificación de resultados.
Las actualizaciones siguientes conservan sus resultados históricos.

**Actualización de etapa 15 — 20/10/2026, `entrenamiento-ML`:** se estabilizaron
los recorridos de consulta pública, A/B y administración conservando los cambios
de etapas 13/14. Se corrigieron cinco defectos comprobados: transición de zoom
de Leaflet después del desmontaje, sesión local no cerrada ante rechazo de
reportes/exportación, ubicación ciudadana inaccesible con teclado, contraste de
distintivo/foco y un marcador privado sin acción presentado como botón sin nombre.
No se añadieron módulos, endpoints, frameworks ni archivos versionables nuevos
en esta etapa; tampoco se modificaron modelos, resultados o fuentes.

Resultado: **1.042 pruebas aprobadas**, cero fallidas; una prueba PostgreSQL
omitida y cuatro casos ML deseleccionados (además de ocho módulos excluidos).
Las 79 backend y 51 frontend mantienen la regresión de etapa 14; las 912 ML
coinciden con la selección segura de etapa 11, con `fit`/`joblib.load` bloqueados.
Lint, build, recursos públicos y 178 controles de seguridad aprobados. Inicio
real con el comando único, API en `127.0.0.1:8765` y Vite en `127.0.0.1:5173`.

Chromium: 11 grupos integrales sobre API/SQLite descartables y usuarios ficticios,
incluidos alta→seguimiento→revisión de reportes y ciclo de cuentas. A/B: 40
colecciones/10.520 filas, 36 métricas y 20 semanas conciliadas con resultados
congelados. Capturas a 1440/390 px; cero excepciones JavaScript/advertencias React
al cierre. CDP/contraste de muestras usados para accesibilidad; lector de pantalla,
dispositivo físico y auditoría integral permanecen pendientes.

PostgreSQL 18 nativo acepta conexiones en 5432, pero no se identificó como instancia
de pruebas ni se accedió a sus bases. Docker está detenido y 5433 no responde.
Cadena Alembic completa compilada a SQL PostgreSQL en ambos sentidos y migración
administrativa reversible probada en SQLite ficticio; **concurrencia PostgreSQL
real no verificada**. La prueba opcional exige un entorno descartable autorizado;
la integración geoespacial necesita además PostGIS. No se iniciaron esos servicios
ni se aplicaron migraciones a bases persistentes.

La [matriz funcional](mvp-functional-status.md#etapa-15--pruebas-integrales-y-estabilización)
detalla evidencia, límites y las ocho funcionalidades parciales: se conservan
15 completas, 8 parciales y 3 bloqueadas. No hubo staging/commit/push ni cambio de
rama; etapa 16 sin iniciar. El contenido siguiente conserva revisiones históricas
y sus cantidades/estado Git no describen el cierre actual.

**Actualización de etapa 13 — 20/10/2026:** se revisaron los módulos contra la
documentación disponible y se registró la [matriz funcional del MVP](mvp-functional-status.md).
Los documentos originales de línea base citados por el plan no están en este
checkout; la matriz usa referencias verificables del plan y alcance existentes.
La única mejora implementada completa la consulta pública de radios por teclado,
prevista por la etapa 7 del plan: `TerritorialMap` reutiliza el detalle agregado,
sincroniza selector/clic, enfoca y marca el radio y conserva su código al cambiar
semana o capa. Cambiaron el componente compartido, cuatro reglas CSS y el script
de prueba del frontend; se añadieron cinco pruebas focalizadas y se actualizó su
README. No se cambiaron API, datos, modelos ni unidades.

Validación de etapa 13: 443 pruebas seleccionadas aprobadas (0 fallidas/omitidas),
lint/build y 178 controles de seguridad aprobados. Chromium: 11 grupos de
comprobaciones, capturas a 1440/390 px, consulta pública y regresión A/B, sin
excepciones JavaScript ni advertencias React. Docker detenido: PostGIS y el
circuito ciudadano con base real siguen sin verificarse aquí. El detalle de
comandos, reintentos por permisos y límites está en la matriz. La revisión partió
de árbol limpio en `entrenamiento-ML` y deja siete archivos nuevos/modificados,
sin staging ni commit. El contenido siguiente conserva la evidencia histórica
de etapa 11; sus cantidades/estado Git no describen esta entrega.

Revisión local: **20/10/2026**, rama `entrenamiento-ML`, HEAD `b160601`.
Este documento actualiza la consolidación existente hasta Fase 5F. Describe el
working tree actual, incluidos cambios todavía sin commit. Es una base técnica
para un posterior resumen de tesis; no constituye aprobación epidemiológica,
autorización de publicación ni certificación de producción.

## 1. Arquitectura actual

SIGARD mantiene preparación/ML, persistencia, API y visualización separadas.
Conviven dos recorridos analíticos que no deben confundirse:

- **MVP v0.1:** observaciones agregadas de Capital, asignaciones sintéticas por
  radio y predicciones de conteos. La unidad es radio censal–semana; las
  coordenadas sintéticas sólo sirven para visualizar. Sus productos publicados
  se consultan mediante la API pública o el respaldo estático explícito.
- **Investigación A/B:** clasificación binaria de presencia experimental de
  registros en t+1. Usa positivos provisionales y negativos asumidos de un
  escenario retrospectivo; no estima casos confirmados ni riesgo clínico.
  Sus predicciones y métricas congeladas permanecen privadas y se proyectan
  exclusivamente mediante la API experimental local.

```text
Procesamiento oficial offline, con permisos por fuente y uso
  → normalización, calidad, fechas, cartografía y paneles privados
  → preparación espacial y experimentos retrospectivos A/B ya congelados
  → lector de resultados con hashes → FastAPI local :8765 → React/Leaflet :5173

Fixtures ficticias + autorización externa en memoria
  → validador → preflight → preparación controlada → informe, sin entrenamiento

Productos públicos aprobados del MVP
  → importador offline → PostgreSQL/PostGIS → API pública :8000 → React
  → respaldo estático explícito cuando la API pública no está disponible
```

Los reportes ciudadanos, geocodificación y administración constituyen un circuito
independiente. El backend no entrena, deduplica episodios ni reconstruye etiquetas
durante solicitudes. La demostración A/B no necesita base de datos ni Docker.
Vercel sigue previsto para el frontend; FastAPI y PostGIS requieren despliegue
separado. No se alteró esta arquitectura en la revisión.

## 2. Componentes desarrollados y estado

- **Procesamiento epidemiológico:** `ml/src/sigard_ml/official/` implementa
  acceso por fuente/uso, ingesta, normalización, calidad, calendario argentino,
  clasificación, fechas, episodios, cobertura, universo y preparación espacial.
  Los módulos funcionan bajo sus contratos; nuevas fuentes y nuevos usos reales
  requieren permisos y decisiones aplicables. No se ejecutó ingesta real aquí.
- **Cartografía censal:** construcción y validación territorial offline;
  geometría pública aprobada de 263 radios, unida a los scores por identificador
  textual canónico. El polígono no acredita residencia ni precisión sanitaria.
- **Random Forest A/B:** experimentos retrospectivos entrenados previamente y
  congelados, independientes del RF de conteos del MVP. A usa siete variables
  de contexto/calendario; B conserva esas variables y añade cuatro rezagos de
  presencia experimental y cuatro indicadores de faltantes. Se preservan NaN y
  estados desconocidos. No se entrenaron ni deserializaron modelos en esta revisión.
- **Validador, etapa 7:** funciones pequeñas de clasificación, fechas/semanas,
  identidad/estructura, cobertura y asignación espacial. Devuelve control,
  estado, motivo y campo: válido, advertencia, inválido o pendiente de acreditación.
  No deduplica episodios ni convierte ausencia de registros en negativos.
- **Preflight, etapa 8:** reutiliza el validador y separa consistencia técnica,
  investigación retrospectiva y criterios epidemiológicos acreditados. Comprueba
  respaldos/decisiones simulados enlazados al conjunto, uso y versión exactos.
  La integridad de una referencia no acredita su veracidad institucional.
- **Preparación controlada, etapa 9:** `official/preparation_pipeline.py`
  verifica autorización externa y llama una sola vez al preflight. Sólo admite
  fixtures ficticias en memoria y entrega informe agregado. No escribe matrices
  ni datos; entrenamiento, evaluación efectiva y publicación siguen bloqueados.
  Los ejecutores históricos A/B conservan sus permisos específicos; este adaptador
  no los invoca, sustituye ni otorga nuevas autorizaciones.
- **FastAPI público:** reportes anónimos, seguimiento, geocodificación,
  administración protegida y consultas del lote publicado del MVP. Las 49 pruebas
  del backend pasaron con bases SQLite ficticias. La instancia pública y PostGIS
  no estaban activos durante esta revisión; no se afirma validación operativa de
  esa conexión en esta entrega.
- **FastAPI experimental:** instancia separada en `127.0.0.1:8765`, sólo lectura,
  sin base de datos ni autenticación de usuario. Proyecta agregados permitidos,
  verifica registro/manifiestos/hashes y no carga modelos. Operativa en HTTP real.
- **React/Leaflet:** MVP, contexto territorial, reportes y vistas metodológicas;
  modalidad A/B sólo en desarrollo desde el origen local exacto. Mapa, scores,
  historial y panel de evaluación operativos en navegador.
- **PostgreSQL/PostGIS y Docker:** Compose, imágenes separadas, volumen de base,
  migraciones, importador, retención y ML offline implementados. Puertos publicados
  en loopback; trabajos bajo perfil `tools`. Configuración de los ocho servicios
  validada y SQL de las tres migraciones generado hasta `20260924_03` sin conexión.
  El daemon Docker está detenido: no se iniciaron contenedores, migraciones reales,
  importaciones ni retención; su funcionamiento en vivo queda sin verificar aquí.

## 3. Funcionalidades disponibles

El comando único inicia FastAPI experimental y Vite, comprueba disponibilidad e
integridad y conserva los servicios ajenos. Las pruebas del coordinador verifican
reutilización de API compatible, cancelación y cierre exclusivo de procesos propios.

La demostración permite seleccionar Modelo A/B, semana epidemiológica y radio,
mantener la selección al cambiar controles, comparar ambos scores y consultar
20 semanas de historial. El mapa conserva los 263 radios. Los huecos temporales
y scores no calculados no se interpolan ni se convierten en cero.

El panel compara seis métricas por entrenamiento, validación y prueba, con barras
0–1, explicaciones, identidad técnica secundaria y advertencias metodológicas.
La prueba y la validación se identifican como ya examinadas. La ausencia de una
métrica produce un estado explícito, sin fabricar un resultado ni ocultarlo con
el MVP. No se presenta un ganador por una única métrica.

Las seis rutas de la SPA revisadas responden correctamente: `/`, `/mapa`,
`/validacion`, `/metodologia`, `/prevencion` y `/admin/reportes`. La administración
conserva su autenticación. Sin la API pública, el MVP utiliza su respaldo aprobado;
la demostración A/B sigue consultando exclusivamente la API experimental.

## 4. Tecnologías utilizadas

- Python, pandas, NumPy, PyArrow y GeoPandas/Shapely para procesamiento tabular y
  geoespacial; scikit-learn para los experimentos offline existentes; Pytest para pruebas.
- FastAPI, Uvicorn, Pydantic, SQLAlchemy/GeoAlchemy2 y Alembic para API,
  contratos, persistencia y migraciones; PostgreSQL/PostGIS para almacenamiento.
- React, React Router, React-Leaflet/Leaflet y Vite; CSS y SVG para el panel,
  sin incorporar una librería gráfica adicional. ESLint y Node test runner.
- Docker Compose e imágenes separadas para base, backend, frontend y ML;
  Nginx sirve el build estático. Dependencias y entornos actuales conservados.

Los artefactos A/B se consumen como resultados congelados: no se presupone que
sus modelos serializados sean portables entre versiones de scikit-learn. No se
instalaron dependencias ni se requirió cargar un joblib para la demostración.

## 5. Resultados experimentales y consistencia comprobada

La comparación local expone precisión, sensibilidad, F1, Average Precision,
ROC-AUC y Brier. AP conserva la definición guardada y no se confunde con PR-AUC
trapezoidal. Precisión, sensibilidad y F1 conservan umbral 0,5. Las métricas
evalúan sólo etiquetas conocidas y mantienen el mismo denominador/composición
para A/B; los scores de inferencia conservan todos los radios.

Particiones de semanas **objetivo**, idénticas en ambos modelos:

- Entrenamiento: 07/01/2024–02/03/2024, ocho semanas.
- Validación ya examinada: 10/03/2024–04/05/2024, ocho semanas.
- Prueba ya examinada: 12/05/2024–08/06/2024, cuatro semanas.
- Semanas objetivo purgadas: comienzos 03/03/2024 y 05/05/2024.

Se comprobaron las 40 colecciones modelo–semana, 10.520 filas agregadas, sus
identidades y particiones. Los **36 valores de métricas** de la API coincidieron
exactamente con la proyección de la tabla comparativa congelada autorizada;
el navegador mostró su formato esperado para las tres particiones. Se conciliaron
20 semanas del historial de un radio con sus scores de las colecciones originales.
No se recalcularon métricas ni se generaron pronósticos fuera del catálogo.

Los valores sanitarios y scores concretos se conservan en la consulta local:
este documento versionable no reproduce resultados privados. No hay conclusión
de superioridad ni nueva validación independiente. Curvas de calibración,
baselines e intervalos de confianza no se exponen mediante estas consultas;
eso no implica que todos estén ausentes de los diagnósticos privados históricos.

## 6. Limitaciones epidemiológicas y seguridad

Permanecen pendientes las decisiones P1–P6 del contrato y dossier existentes:

1. Clasificación histórica y evidencia de confirmación.
2. Significado de identificadores, notificaciones y episodios, con resolución respaldada.
3. Cobertura y completitud por tiempo/territorio para acreditar negativos.
4. Evento temporal, inicio de síntomas frente a toma de muestra y aproximaciones.
5. Alcance espacial admisible y tratamiento de asignaciones ambiguas.
6. Disponibilidad histórica/maduración y alcance retrospectivo u operativo.

La ausencia de registros no prueba ausencia de casos. La literalidad de
«confirmado», una declaración de cobertura o un hash no constituyen aprobación
institucional. Positivos provisionales, negativos asumidos, fechas/ubicaciones
inciertas y pocos bloques temporales limitan los resultados. Existe dependencia
espacial y temporal; no se asume independencia de filas radio–semana.
Los scores no son riesgo clínico calibrado ni confirmaciones de casos.

La API experimental fija loopback, Host y Origin exactos, rechaza proxies y
exige marcador público de lectura. CORS no admite credenciales. No hay rutas de
archivos, administración, documentación/OpenAPI o registros individuales en esa
instancia; respuestas y errores son `no-store, private`. Sin autenticación,
cualquier proceso del propio equipo puede solicitar esos agregados con las
cabeceras esperadas: no equivale a control de identidad entre usuarios locales.
No habilitar túneles, exposición LAN o publicación de estos resultados.

Pasaron **178 controles** de seguridad de Git/Docker/recursos: cero candidatos
sensibles versionados detectados, diez recursos públicos aprobados con hashes
conservados y exclusiones de fuentes, derivados, modelos, secretos y cachés.
Las rutas experimentales no se registran en `app.main`; A/B no se incluyó en
`public/` ni en la distribución estática. La búsqueda de nombres sensibles del
historial (privados, Excel, modelos y Parquet) no encontró candidatos; las
coincidencias de `.env.*` fueron plantillas de ejemplo. El escaneo heurístico
no sustituye una auditoría
forense de todo el contenido del historial o de despliegues remotos.

El inventario de **706 archivos locales de datos/modelos/artefactos** conservó
tamaños y tiempos de modificación. Es una comprobación de metadatos, no un nuevo
hash integral de fuentes epidemiológicas. El adaptador verificó los hashes de
los resultados autorizados consumidos. No se incorporaron fuentes epidemiológicas
adicionales ni se modificaron datasets, etiquetas o predicciones.

## 7. Revisión técnica, correcciones y estado de Git

Se corrigió un defecto demostrado en `SigardComponents.jsx`: `PageIntro`
envolvía en `<p>` contenidos que ya eran párrafos, generando HTML inválido y
advertencias de React en varias rutas. Se eliminó sólo esa envoltura. La nueva
comprobación del navegador no detectó párrafos anidados, advertencias React ni
excepciones JavaScript en las seis rutas. No se añadieron funciones visuales,
servicios, permisos ni capas de validación.

La consolidación anterior todavía describía el adaptador y el selector A/B
como propuestas pendientes; se actualiza aquí al estado implementado y se remite
a los contratos especializados, sin duplicar documentación.

Resultado final: **1.007 pruebas automatizadas aprobadas**, sin fallos en la
selección segura final: 912 de procesamiento/ML, 49 backend, 13 cliente A/B,
15 recursos públicos y 18 coordinador local. Lint, build, comprobación de recursos,
Compose y compilación SQL offline aprobados; navegador en 1440 y 390 px, sin
desbordamiento horizontal de página. Los 178 controles de seguridad se informan
separadamente y no se suman otra vez a las pruebas.

La selección ML excluyó ocho módulos que entrenan o dependen de artefactos/fuentes
locales adicionales y cuatro casos concretos de ajuste/lectura real. Se aplicó
una barrera temporal contra `BaseForest.fit` y `joblib.load`, fuera del código
del producto. La primera selección no hizo coincidir cuatro exclusiones de rutas:
la barrera interceptó tres llamadas antes de ajustar y otra prueba leyó agregados
históricos existentes sin escribir datasets. Se corrigió la selección y la
ejecución final pasó. No se considera eso un defecto del producto ni una
ejecución global de todos los tests. El backend conserva cinco advertencias de
deprecación de dependencias; no afectan el resultado y no se cambian versiones.

Al cierre: **12 archivos tracked modificados y 31 nuevos sin seguimiento**, sin
staging. Antes de esta revisión eran 11 y 31. Los cambios nuevos versionables de
etapa 11 son este documento y la corrección puntual del componente ya modificado;
los scripts, recibos y SQL de revisión permanecen en `.tmp/`, excluidos.
No se detectaron archivos privados visibles o cambios accidentales que requieran
borrado; no se descartó ni reorganizó trabajo previo.

Pendiente de consolidar: validador/preflight/preparación y pruebas de etapas 7–9;
API/launcher local, inicio único y contratos; panel, servicios y pruebas React de
etapa 10; documentación relacionada. El plan antiguo `technical-commit-plan.json`
es un antecedente de Fases 1–5F, no una lista vigente para staging automático.

Hay cinco commits posteriores a la referencia local `origin/main`:
`5b78c96` (seguridad/contratos), `9f708cb` (procesamiento/calendario), `b4f72f3`
(preparación espacial), `8d0fd02` (experimentos retrospectivos) y `b160601`
(pruebas/documentación). La rama no tiene upstream configurado. No se hizo fetch,
por lo que no se certifica el estado remoto actual. Sin commit, merge, push,
cambio de rama ni modificación del índice en esta revisión.

## 8. Inicio local y pendientes para continuar

Con los entornos y dependencias existentes y los artefactos autorizados presentes,
ejecutar desde la raíz:

```powershell
npm.cmd --prefix frontend run dev
```

Abrir **http://127.0.0.1:5173/mapa** y seleccionar **Investigación local A/B**.
El coordinador inicia `app.research_local` en `127.0.0.1:8765` y Vite en
`127.0.0.1:5173`, sin entrenar, migrar, importar ni modificar artefactos. No hacen
falta Docker, PostgreSQL, tokens o credenciales para esta modalidad. Los puertos
son fijos; una ocupación incompatible bloquea el inicio sin detener procesos ajenos.
Ctrl+C cierra sólo los servicios iniciados por ese comando. Este inicio completo
se repitió correctamente durante la revisión.

Las rutas públicas y de reportes requieren su API/base propias; su ausencia puede
producir errores de red esperados y activar el respaldo explícito del MVP, no un
fallback de scores A/B. Procedimientos y requisitos completos:
[guía local](experimental-spatial-local.md), [backend](../backend/README.md),
[Docker](docker-development.md) y [contrato A/B](experimental-spatial-results-contract.md).

Para repetir comprobaciones focalizadas sin entrenar:

```powershell
.\backend\.venv\Scripts\python.exe -B -m pytest backend/tests -q -p no:cacheprovider --basetemp=backend/.tmp/review-backend-new
.\ml\venv\Scripts\python.exe -B -m pytest ml/tests/test_epidemiological_validator.py ml/tests/test_epidemiological_preflight.py ml/tests/test_official_preparation_pipeline.py -p no:cacheprovider --basetemp=ml/.tmp/review-preparation-new
.\ml\venv\Scripts\python.exe -B tools/check_repository_security.py
npm.cmd --prefix frontend run test:research
npm.cmd --prefix frontend run test:security
npm.cmd --prefix frontend run test:dev
npm.cmd --prefix frontend run lint
npm.cmd --prefix frontend run build
git diff --check
```

No ejecutar toda la suite ML sin seleccionar: contiene pruebas que ajustan RF o
leen artefactos locales. Los tests de cierre de procesos deben ejecutarse en un
entorno que permita terminar sus propios descendientes. Usar destinos temporales
nuevos; no ejecutar entrenadores, importadores, retención ni `--overwrite` como
parte de una verificación documental.

**SIGARD está preparado para una demostración académica experimental local** del
mapa y comparación retrospectiva A/B, conservando las advertencias. Antes de una
demostración completa basada en PostGIS debe iniciarse y verificar por separado
el stack público existente. Para procesar nuevos datos reales o entrenar hace
falta aprobar P1–P6 y evidencias/alcance, resolver su procedencia institucional y
acordar un protocolo temporal y período no examinado. La preparación de fixtures
no sustituye esos pasos. Cualquier publicación exige autorización independiente.

Referencias de alcance: [dossier de decisiones](official-epidemiology-review.md),
[auditoría](epidemiological-data-quality-audit.md), [contrato epidemiológico](epidemiological-labeling-and-coverage-contract.md)
y [controles de seguridad](repository-security.md). La revisión humana y la
consolidación posterior en Git quedan pendientes; no se avanza a otra etapa.
