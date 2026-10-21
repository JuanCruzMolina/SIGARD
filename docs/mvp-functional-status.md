# Estado funcional del MVP

Consolidación del 21/10/2026: rama `entrenamiento-ML`. Alcance: prototipo académico,
no sistema sanitario operativo. Esta matriz contrasta documentación con código;
no toma los estados históricos del plan como prueba de implementación.

## Referencias y criterio

El plan cita `SIGARD_Requerimientos_LineaBase_v0.1.md` y
`Relevamiento_requerimientos_md.md`, pero ninguno está disponible en este
checkout. Se usan referencias verificables de [plan-proyecto.md](plan-proyecto.md),
[mvp-funcionalidades.md](mvp-funcionalidades.md),
[arquitectura](architecture.md), [consolidación](technical-consolidation.md),
`PRODUCT.md` y `moduloInformativo.md`. Los RF/RNF agrupados por el plan no
permiten reconstruir la definición individual de cada identificador: no se
inventa esa correspondencia. La matriz cubre los módulos documentados disponibles;
su cotejo literal con la línea base original queda pendiente de recuperar esos documentos.

**Completa:** recorrido implementado en el alcance de demostración y con evidencia.
**Parcial:** base implementada con aspectos concretos sin completar/verificar.
**Pendiente:** no se encontró implementación equivalente.
**Bloqueada:** requiere una decisión o respaldo externo antes de desarrollar/operar.
Una prueba con SQLite o una respuesta estática no acredita PostGIS en vivo.

**Evidencia nueva de etapa 17:** PostgreSQL 17.5/PostGIS 3.5.2 descartables en
5435; migraciones completas reversibles, cuentas con concurrencia real, reportes
y geometrías ficticias. 56 pruebas seleccionadas y nueve grupos de navegador
aprobados. Se corrigió únicamente el ID de duplicado vacío, normalizado a NULL
en el backend por su FK. [Procedimiento, resultados y límites](../backend/README.md#ensayo-postgresqlpostgis-descartable--etapa-17).
La integración de pruebas queda verificada; no equivale a operación persistente,
importación completa de cartografía oficial o despliegue. Se conservan las
categorías de la matriz: 15 completas, ocho parciales y tres bloqueadas.

Limpieza propia verificada, sin conexión a 5432. En la revisión posterior Docker
ya estaba apagado; no se pudo comprobar el estado individual de los dos
contenedores existentes. El usuario decidió mantenerlo apagado. No se afirma
restauración global ni queda autorización pendiente para iniciarlo.

El importador existente se verificó después con 263 polígonos totalmente
ficticios: validación, importación transaccional, rollback/idempotencia y consultas
en SQLite aislado. Su recorrido completo contra PostGIS real **sigue pendiente**.
Ver [procedimiento y límites](../backend/README.md#verificación-ficticia-del-importador-territorial--sin-docker).
Estas comprobaciones no cambian las categorías funcionales ni habilitan datos reales.

## Matriz de cumplimiento

| Requerimiento / referencia | Funcionalidad | Estado | Evidencia de implementación | Prioridad | Acción necesaria |
| --- | --- | --- | --- | --- | --- |
| Plan §6, etapa 4 (RF-01–05 agrupados) | Ingesta, normalización, calendario y trazabilidad offline | Completa | `ml/src/sigard_ml/official/`, contratos en `docs/official-*.md`, pruebas de calendario/validador/preflight/preparación | Alta | Mantener permisos por uso; no ejecutar nuevas ingestas en esta etapa. |
| Plan §3 y etapa 8; contrato epidemiológico P1–P6 | Target territorial epidemiológico acreditado y uso operativo | Bloqueada | `ml/src/sigard_ml/official/epidemiological_preflight.py`, `official/preparation_pipeline.py`, `docs/epidemiological-labeling-and-coverage-contract.md` | Alta | Obtener decisiones y evidencias institucionales; no convertir el escenario A/B en evidencia validada. |
| Plan etapas 4 y 8; MVP §3 | Asignación sintética y cartografía de 263 radios | Completa | `ml/src/sigard_ml/simulation/allocation.py`, `frontend/public/data/territorial_context.geojson`, `experimental_spatial_history.geojson`, validación en `services/sigardData.js` | Alta | Conservar datos/semillas y rotulación sintética. |
| Plan etapa 8 (RF-06–08 agrupados); MVP §1 y §4 | Predicción temporal departamental y baseline | Completa | Pipelines offline de `ml/src/sigard_ml/evaluation/`, artefactos públicos aprobados, `pages/Validacion.jsx` | Alta | Mantener límites del holdout exploratorio; no reentrenar. |
| Consolidación §2–5; contrato experimental | Consulta retrospectiva A/B: modelo, semana, 263 radios y scores | Completa | `components/ExperimentalSpatial.jsx`, `services/experimentalContract.mjs`, `backend/app/experimental_results.py`, pruebas backend/cliente | Alta | Conservar acceso sólo local y resultados congelados. |
| Consolidación §3–5 | Comparación A/B, historial y seis métricas por partición | Completa | `components/ExperimentalAnalysis.jsx`, `services/experimentalAnalysis.mjs`, rutas `/comparison`, `/history`, `/evaluation`, pruebas específicas | Alta | Mantener etiquetas retrospectivas y ausencia explícita de resultados. |
| Plan etapa 2 | Persistencia geoespacial y publicación versionada | Parcial | Etapa 17: cuatro migraciones aplicadas/revertidas/reaplicadas en PostgreSQL/PostGIS real; punto generado, polígono ficticio, SRID, FK/índices/GiST y GeoJSON | Alta | Integración descartable verificada; falta importador completo con lote territorial y operación persistente. No se utilizó 5432. |
| Plan etapas 3 y 6; MVP datos consumidos | API pública de semanas, predicciones, capas y evaluación | Parcial | `public.py`, regresión `test_public_api.py`; etapa 17 comprueba rutas espaciales/GeoJSON en PostGIS con geometrías ficticias, también desde navegador | Alta | Conserva evidencia previa de 263 radios por HTTP/SQLite y fallback; falta importación completa de esos datos en PostGIS y lote operativo. |
| MVP §1–5; consolidación §3 | Ingreso anónimo y navegación pública | Completa | `App.jsx`, seis rutas existentes y navegación compartida | Alta | Mantener separación de prevención/administración y datos analíticos. |
| MVP §1 | Resumen de la semana, estimación agregada y procedencia | Completa | `pages/Dashboard.jsx`, `StatCard`, `TopRadios`, `services/sigardData.js` | Alta | Mantener distinción entre total departamental y señal territorial. |
| MVP §2; plan etapa 7 | Cambio temporal alineado entre predicción y simulación | Completa | Estado compartido en `App.jsx`, `TemporalControls`, `getExperimentalCollection`, `assertCompleteData` | Alta | Mantener validación exacta de corte e inicio/fin de semana. |
| MVP §3; plan etapa 7 | Mapa público de contexto y simulación con detalle agregado | Completa | `pages/Mapa.jsx`, `TerritorialMap`, `RadioDetails`, geometrías públicas aprobadas | Alta | Conservar 263 radios y leyendas sin umbrales sanitarios. |
| Plan etapa 7: teclado y alternativa textual; PRODUCT accesibilidad | Consultar cualquier radio público sin pulsar un polígono | Completa | `TerritorialMap` incorpora selector nativo, detalle vivo, enfoque y contorno; `security/public-map.test.mjs` y recorrido real de teclado/clic en Chromium | Alta | **Resuelta en etapa 13.** Conservar selección por código y leer siempre los valores de la capa/semana vigente. |
| MVP §3 y §5; plan §3 y etapa 7 | Leyendas y distinción observado/sintético/predicho | Completa | `LevelLegend`, `MethodNotice`, `RadioDetails`, `Dashboard.jsx`, metadatos aprobados | Alta | No rotular percentiles o scores como riesgo epidemiológico validado. |
| MVP §4 | Validación temporal pública con métricas y tabla de seis semanas | Completa | `pages/Validacion.jsx`, `BacktestChart`, `model_evaluation.json` | Media | Conservar alcance departamental y limitaciones exploratorias. |
| MVP §5 | Metodología y advertencias | Completa | `pages/Metodologia.jsx`, avisos junto a mapas | Media | Mantener coherencia con contratos de cada circuito. |
| MVP §6; plan etapa 10 (RF-19–20 agrupados); módulo §4 | Prevención, síntomas, fuentes y teléfonos | Completa | `pages/Prevencion.jsx`, `PreventionGuide`, `SymptomsAlert`, `prevention_content.json`, `services/preventionData.js` | Alta | Mantener revisión editorial; no se incorpora ni modifica consejo médico aquí. |
| Módulo §5; MVP §6 | Directorio con búsqueda, filtros, mapa y listado de 24 CAPS/3 hospitales | Parcial | `HealthFacilitiesMap.jsx`, `health_facilities.geojson`; navegador: 27 marcadores, filtros 24 CAPS/3 hospitales y búsqueda vacía, con listado textual | Media | Funciona para demostración. Confirmar vigencia de 23 CAPS con organismo competente; no equivale a disponibilidad actual. |
| Módulo §6; MVP §6 | Alta anónima y ubicación manual/opcional con código | Parcial | Etapa 17: formulario real → FastAPI → PostgreSQL, punto PostGIS generado y persistencia tras nueva instancia API, con datos ficticios | Alta | Integración descartable verificada; falta operación persistente. Geocodificador externo/geolocalización personal no utilizados. |
| Módulo §6; MVP §6 | Seguimiento público sin texto ni ubicación | Parcial | Etapa 17: alta→código→estado→actualización mediante navegador/API/PostgreSQL; respuesta pública restringida | Alta | Recorrido con persistencia comprobado en entorno descartable; falta operación persistente, sin desarrollar otro módulo. |
| Módulo §7; plan etapa 5 | Administración protegida de reportes, auditoría, exportación y retención | Parcial | Etapa 17: revisión/CSV en navegador con PostgreSQL; auditoría/purga y permisos en pruebas reales; ID de duplicado vacío corregido a NULL por FK | Alta | Integración descartable verificada; faltan operador autorizado y programación/supervisión de purga operativa. |
| Plan etapa 5: ciclo de cuentas | Alta, desactivación y restablecimiento/rotación autorizada de administradores | Completa | Etapa 17: migración 04 reversible en PostgreSQL; JWT/roles/revocación, navegador y dos conexiones concurrentes; espera real del advisory lock observada | Media | Alcance académico con persistencia verificado. Operación/despliegue y recuperación del operador siguen fuera del ensayo; no hay recuperación por correo. |
| Plan etapa 9 (RF-12–14, RN-06, CA-08 agrupados) | Alertas candidatas→aprobadas/rechazadas→publicadas | Bloqueada | Existe tabla histórica `alertas` en `backend/database/schema.sql`, sin máquina de estados, modelo ORM, router ni bandeja vigente; el plan exige reglas institucionales | Alta | Acordar condiciones, responsable y reglas de publicación antes de implementar; nunca generar alertas sanitarias con scores A/B. |
| Plan etapa 10: gestión editorial | Editar, auditar y publicar contenido sanitario | Bloqueada | Lectura estática implementada; no hay modelo/editor/API editorial; responsable requerido por el plan | Media | Definir responsable editorial y política borrador/publicación; reutilizar contenido actual cuando se autorice ese alcance. |
| Plan etapa 11; RNF y PRODUCT accesibilidad | Seguridad, responsive y accesibilidad integral | Parcial | Auditoría de 178 controles; Chromium Accessibility/CDP y contraste de muestras; teclado y viewports 1440/390; cinco defectos corregidos en etapa 15 | Alta | Falta lector de pantalla, dispositivo físico y auditoría completa; la muestra automatizada no acredita conformidad WCAG integral ni despliegue seguro. |
| Plan etapa 0 y etapa 11 | Entorno reproducible, Docker y despliegue separado | Parcial | Etapa 17: ejecutor PostGIS con guardas/limpieza, 18 pruebas del coordinador; launcher habitual A/B intacto | Media | Entorno descartable verificado; pendientes despliegue y operación. Restitución de dos contenedores autoactivados por Docker pendiente de aprobación. |

## Selección de la única mejora de etapa 13

Se prioriza la consulta accesible del mapa público, respaldada expresamente por
el plan, etapa 7, y por `PRODUCT.md`. Antes de esta etapa el detalle agregado
dependía de un clic sobre un polígono. El selector completa el recorrido
mapa→radio→información utilizando la capa ya cargada, sin datos adicionales,
dependencias o endpoints. A/B ya resuelve esa selección y debe conservarla.

Alternativas: reportes tienen implementación sustancial y su comprobación real
depende de servicios detenidos; alertas y edición sanitaria necesitan definiciones
externas; el ciclo de cuentas tiene mayor alcance que este cierre puntual.

## Comportamiento implementado

`TerritorialMap`, dentro de `SigardComponents.jsx`, reutiliza `RadioDetails` y
la colección vigente. El selector nativo ordena los 263 códigos textuales,
conserva ceros iniciales y ofrece etiqueta, ayuda, foco visible y detalle con
`aria-live="polite"`. Tanto clic como teclado sincronizan código y detalle;
la selección enfoca el polígono y dibuja un contorno discontinuo sin depender
sólo del color. Cambiar semana/capa mantiene el código y consulta sus nuevas
propiedades: no conserva una copia de valores antiguos. Elegir la opción vacía
retira el detalle y contorno. La ausencia de capa mantiene el estado de error
existente; el estado de carga no muestra valores anteriores.

El selector sólo aparece en el mapa público completo. El mapa compacto del
resumen y los controles A/B conservan sus recorridos. No cambia ningún campo,
unidad, endpoint, dataset, modelo ni contrato epidemiológico. `App.css` adapta
el control a los estilos y cortes responsive existentes; `package.json` añade
únicamente `test:public-map`, sin dependencias.

## Validación y cierre de etapa 13 (histórico)

Resultado final: **443 pruebas aprobadas, 0 fallidas y 0 omitidas en las suites
seleccionadas**. No se ejecutó la suite global ni pruebas de entrenamiento.

| Selección ejecutada | Aprobadas |
| --- | ---: |
| `npm.cmd --prefix frontend run test:public-map` | 5 |
| `npm.cmd --prefix frontend run test:research` | 13 |
| `npm.cmd --prefix frontend run test:dev` | 18 |
| `npm.cmd --prefix frontend run test:security` | 15 |
| `.\backend\.venv\Scripts\python.exe -m pytest backend/tests -q` | 49 |
| ML: calendario, validador, preflight, preparación controlada y seguridad | 343 |

La selección ML corresponde a `test_official_calendar.py` (51),
`test_epidemiological_validator.py` (64), `test_epidemiological_preflight.py` (58),
`test_official_preparation_pipeline.py` (35) y `test_repository_security.py` (135).
Se ejecutó con `-B -q -p no:cacheprovider --basetemp=ml/.tmp/stage13-check`.
Usa fixtures ficticias; no entrena ni carga modelos reales.

Lint, build, `security:check` y `git diff --check`: aprobados. La auditoría
`tools/check_repository_security.py` aprobó **178 controles**, verificó diez
recursos públicos con hashes aprobados y no detectó candidatos sensibles
versionados; no envió contextos Docker ni cargó modelos. Estos controles no
se suman otra vez al total de pruebas. Backend conserva cinco advertencias
de deprecación de dependencias existentes.

El primer intento ML tuvo 34 errores de preparación por permisos del directorio
temporal de pytest; la prueba del árbol de procesos del coordinador también
falló dentro del sandbox. Las repeticiones con permisos adecuados y temporales
locales pasaron completas; no se modificó producto para sortear esos errores.

**Navegador:** inicio con `npm.cmd --prefix frontend run dev`; Chromium sin
interfaz visible mediante Puppeteer ya disponible, con autorización para abrir
el navegador fuera del sandbox. Se aprobaron 11 grupos de comprobaciones:
estado vacío y 263 radios; selección real por teclado y foco; clic sincronizado;
cambio de capa; cambio de semana y valores; responsive; limpieza de selección;
navegación por cinco secciones y acceso administrativo protegido; recorrido A/B
con modelos/semanas/comparación/20 semanas de historial/seis métricas por cada
partición; fallo A/B; fallo público sin API ni respaldo. Se revisaron capturas
de escritorio de 1440 px y viewport móvil de 390 px, incluidos mapa público,
selector/detalle, mapa A/B y error público. Cero excepciones JavaScript o
advertencias React; sin desbordamiento horizontal. Los rechazos de red de la
API pública ausente y los fallos inyectados son esperados, no errores JavaScript.
Las capturas, scripts y recibo de revisión quedan en `frontend/.tmp/stage13-*`,
excluidos de Git y Docker.

**Límites:** Docker detenido, sin iniciar servicios adicionales. No se verifican
PostGIS, migraciones/importación vivas ni alta→seguimiento→administración contra
base real; las pruebas backend usan SQLite y fixtures. El directorio sanitario
sí se cargó y se comprobó su estado sin resultados en navegador; no se verificaron
horarios actuales. No se hizo prueba con lector de pantalla ni móvil físico.

Resultado de la matriz al cierre de etapa 13: **14 completas, 8 parciales, 1 pendiente y 3 bloqueadas**
(26 filas; componentes de demostración, no certificación operativa). La revisión
partió de un árbol limpio y deja siete archivos versionables nuevos/modificados,
sin staging, commit, push ni cambios de rama. Los artefactos públicos y resultados
A/B mantienen sus verificaciones de integridad; no se reentrenó ni se incorporaron
archivos epidemiológicos.

## Etapa 14 — gestión de cuentas administrativas

El plan, etapa 5, y el pedido de esta etapa respaldan el alcance. Se conservaron
JWT, PBKDF2-SHA256, rol `admin`, tabla `usuarios` e interfaz `/admin/reportes`.
No se reconstruyeron los requerimientos originales ausentes.

Se implementaron listado paginado y estado, alta protegida sin duplicados,
desactivación y rotación/restablecimiento por un administrador autorizado. Las
mutaciones requieren su contraseña actual y confirmación visual. La última
cuenta activa está protegida bajo bloqueo transaccional, con revalidación del
actor después de la espera. `token_version` revoca tokens al desactivar o rotar,
y el rol se consulta en la base. Los cambios propios cierran la sesión. Auditoría
sin credenciales y errores que no reflejan payloads; limitador existente
reutilizado. Bootstrap sólo con tabla vacía. No hay registro público, recuperación
por correo, reactivación, cambio de roles ni integración externa.

La migración reversible `20261020_04_admin_accounts.py` está preparada y probada
en SQLite ficticio y SQL PostgreSQL offline, **sin aplicarla a bases persistentes**.
Los tokens antiguos sin versión requieren nuevo login. El contrato, campos,
bootstrap y procedimiento están en [backend/README.md](../backend/README.md#cuentas-administrativas-y-autenticación--etapa-14).

Validación final de etapa 14: **265 pruebas aprobadas, 0 fallidas, 0 omitidas**
en las suites seleccionadas: 79 backend (30 nuevas), 135 de seguridad del
repositorio, 13 cliente A/B, 5 mapa público, 15 recursos públicos y 18 coordinador.
Lint, build, `security:check` y auditoría de 178 controles aprobados. No se
ejecutaron entrenamientos ni suites ML que ajusten modelos.

**Extremo a extremo:** Chromium recorrió interfaz→HTTP→SQLite temporal con
usuarios ficticios: alta y rechazo por contraseña incorrecta, rotación ajena,
rotación propia con cierre de sesión, rechazo de credenciales anteriores,
desactivación propia y bloqueo de login, protección visual del último admin,
error/reintento y retorno a reportes. Ocho grupos de comprobaciones; mapa público
y A/B sin tokens, 263 radios, comparación, historial y métricas conservados.
Se revisaron capturas a 1440/390 px y el formulario móvil, sin excepciones
JavaScript ni advertencias React. Se corrigió el listado móvil para mostrar las
acciones sin desplazamiento horizontal. La primera inyección de error del
harness afectaba sólo uno de los efectos duplicados de React en desarrollo;
se ajustó el harness y la ejecución final pasó.

La prueba reproducible es `npm.cmd --prefix frontend run test:accounts:browser`,
con Vite activo y Puppeteer disponible (ruta opcional `SIGARD_BROWSER_MODULE`).
`backend/tests/browser_admin_fixture.py` crea y elimina su propia base y escucha
sólo en loopback; no usa `.env` ni cuentas reales. Capturas y recibo local en
`frontend/.tmp/stage14-*`, excluidos de Git y Docker.

**Pendiente de integración real:** Docker/PostGIS no se iniciaron. No se aplicaron
migraciones ni se verificó el bloqueo advisory entre workers PostgreSQL, ni se
operaron cuentas persistentes. La comprobación end-to-end fue completa en el
entorno descartable, no en una instalación operativa. Recuperación por correo
queda fuera del alcance solicitado. No se modificó la API experimental, modelos,
resultados ni datasets. Se conserva todo el trabajo sin commit de etapa 13.

Estado actual de la matriz: **15 completas, 8 parciales, 0 pendientes y 3 bloqueadas**.
La integración real sigue reflejada como parcial en persistencia/infraestructura.
La evidencia anterior corresponde al cierre de etapa 14; se amplía a continuación.

## Etapa 15 — pruebas integrales y estabilización

No se añadieron módulos ni dependencias. Se conservaron los cambios de etapas
13/14 y se extendieron sus pruebas y fixture existentes, sin archivos nuevos
versionables. La fixture integral copia sólo los artefactos públicos aprobados
a SQLite descartable, con geometrías como texto JSON: esto no valida PostGIS.

### Defectos comprobados y corregidos

1. **Leaflet al navegar durante un zoom:** el temporizador de transición intentaba
   acceder a `_leaflet_pos` después de desmontar el mapa. Se desactivó únicamente
   la animación CSS de zoom en `TerritorialMap`; se conservan zoom, selección,
   capas y los 263 radios. La navegación rápida dejó de generar la excepción.
2. **Sesión revocada en reportes:** detalle/guardado no cerraban la sesión local,
   y exportación no conservaba el status HTTP del error. Se unificó el tratamiento
   de 401/403 y se limpian listado, detalle y campos privados al salir. El servidor
   ya rechazaba esos accesos: no se modificó ni debilitó JWT/autorización.
3. **Ubicación manual sólo con ratón:** Enter no marcaba un punto en el mapa
   enfocado. Ahora el teclado selecciona su centro tras desplazarse con flechas,
   con nombre, instrucciones y foco visible. Se reutiliza el mismo estado de
   ubicación; geolocalización y consentimiento opcionales permanecen separados.
4. **Contraste insuficiente:** texto del distintivo territorial 4,01→5,60 y foco
   del selector 1,70→5,16. Se oscurecieron sólo texto/foco; no cambiaron colores de
   niveles, clasificación, scores ni datos.
5. **Marcador privado como botón sin nombre:** era un elemento sin acción. Se
   retiró su interacción/foco; la ubicación sigue disponible en el detalle
   textual privado. El marcador del formulario conserva un título accesible.

### Evidencia final y comparación

**1.042 pruebas aprobadas, 0 fallidas, 1 omitida (PostgreSQL real):** 79 backend,
912 procesamiento/ML y 51 frontend (5 mapa, 13 A/B, 15 recursos, 18 coordinador).
La selección ML reutilizó en memoria el harness seguro de revisión anterior:
ocho módulos excluidos y cuatro casos deseleccionados por entrenamiento/artefactos;
`BaseForest.fit` y `joblib.load` prohibidos por una fixture. No se suman dos veces
las pruebas de seguridad incluidas entre las 912. Lint, build, `security:check`
y 178 controles de seguridad aprobados; `git diff --check` correcto.

Las 79 pruebas backend y 51 frontend mantienen los resultados de etapa 14; las
912 ML coinciden con la selección segura histórica de etapa 11. Los defectos
detectados pertenecen a recorridos ampliados que esas verificaciones no cubrían.
Se conservan advertencias de deprecación de dependencias, sin cambiar versiones.

**Navegador:** 11 grupos integrales con API HTTP/SQLite temporal: mapa público
servido por API, navegación, radios por teclado, capas/semanas; prevención y
directorio; alta→seguimiento→revisión administrativa de un reporte ficticio;
exportación CSV sólo en memoria; filtros vacíos; rechazo anónimo y cierre ante
401/403 en detalle, guardado y exportación; gestión completa de cuentas con datos
ficticios. Se comprobaron errores/reintento y estados vacíos. La revisión A/B
adicional concilió 40 colecciones/10.520 filas, 36 métricas congeladas y 20 semanas
de historial, para las seis rutas, desde la API exclusivamente loopback.

Se revisaron capturas de escritorio 1440 px y viewport móvil 390 px, incluido
el foco del mapa ciudadano. Cero excepciones JavaScript o advertencias React al
cierre; sin desbordamientos horizontales de página en los recorridos revisados.
La herramienta disponible fue el árbol de accesibilidad de Chromium (CDP), con
comprobación de nombres de controles y contraste de muestras en nueve contextos.
No se encontró axe ya instalado y no se instalaron dependencias. No se realizaron
pruebas con lector de pantalla ni móvil físico, ni una auditoría WCAG completa.

El harness se ejecuta con `SIGARD_INTEGRAL_REVIEW=1`, `SIGARD_EXPECT_STABLE=1` y
el comando de navegador existente; ver `frontend/README.md`. Los recibos/capturas
están en `frontend/.tmp/stage15-*` y el JUnit ML en
`ml/.tmp/stage15-safe-tests.xml`, excluidos de Git/Docker. Los reintentos iniciales
del harness corrigieron limpieza de inputs y la inyección del error de exportación:
el rechazo debe afectar al GET, no al preflight CORS OPTIONS. No fueron cambios
de producto ni relajaciones de controles.

### PostgreSQL y condiciones externas

El servicio nativo PostgreSQL 18 está activo y `pg_isready` confirmó aceptación
en `127.0.0.1:5432`. No hay una conexión de pruebas identificada: no se autenticó,
consultó ni modificó ninguna de sus bases. El puerto Compose 5433 no respondió;
Docker permanece detenido. No se encontró PostGIS en la instalación nativa.

Se compiló la cadena Alembic completa a SQL PostgreSQL de subida y reversión
(30/24 sentencias). La migración administrativa se aplicó/revirtió/reaplicó en
SQLite ficticio, preservando usuarios y verificando unicidad normalizada/default.
**No se probó concurrencia real en PostgreSQL.** Se dejó preparada una prueba
opcional en `test_admin_accounts.py`, omitida sin `SIGARD_TEST_POSTGRES_URL`, que
exige host loopback, puerto distinto de 5432/5433, rol/base ficticios
`sigard_stage15_test` y base vacía. Comprueba migración, NOT NULL/FK/unicidad,
revocación y desactivaciones simultáneas propias/cruzadas con ambos actores
autenticados antes del bloqueo. Su preparación no es evidencia de ejecución.

Está pendiente autorización para iniciar un clúster nativo **separado y descartable**
en `backend/.tmp/`, puerto loopback libre, cuentas ficticias, y detenerlo al cerrar.
Eso permitiría comprobar la parte administrativa. La cadena completa, importador
y geometrías requieren además un entorno **PostGIS** descartable autorizado
(por ejemplo Docker, sin reutilizar el volumen persistente). No se ejecutó
ninguna de esas acciones ni una migración sobre datos persistentes. La reversión
está documentada en `backend/README.md`.

### Revisión de las ocho funcionalidades parciales

| Funcionalidad | Evidencia académica actual | Dependencia pendiente |
| --- | --- | --- |
| Persistencia geoespacial | SQL Alembic completo y pruebas administrativas SQLite reversibles | PostgreSQL/PostGIS real e importación geográfica |
| API pública | Navegador consume semanas, capas y evaluación desde HTTP/SQLite temporal; fallback también conservado | Lote y geometrías PostGIS operativos |
| Directorio sanitario | 27 marcadores, búsquedas, filtro de tipo y listado funcionan | Confirmación institucional de vigencia de 23 CAPS |
| Reporte anónimo | Alta HTTP ficticia con teclado/clic, código y privacidad | PostGIS persistente; geocodificador externo no consultado |
| Seguimiento | Código y cambio de estado visibles, sin ubicación/descripción pública | Integración persistente/PostGIS |
| Gestión de reportes | Filtros, revisión, CSV, cierre por revocación; auditoría/purga con fixtures | PostGIS, operador y programación/supervisión de retención |
| Seguridad/accesibilidad integral | Controles Git/Docker, CDP, contraste, teclado, responsive y regresión | Lector de pantalla, dispositivo físico, auditoría completa y despliegue |
| Infraestructura | Inicio automático local A/B real y pruebas del coordinador | Contenedores/PostGIS y despliegue separado verificados en vivo |

Se mantienen **15 completas, 8 parciales y 3 bloqueadas**. Ningún estado parcial
se convirtió en completo por una prueba SQLite. Las definiciones institucionales
de target acreditado, alertas y gestión editorial siguen bloqueadas.

Para una futura etapa 16: autorizar/resolver la prueba PostgreSQL/PostGIS aislada,
acordar el entorno y guion de demostración con datos ficticios, probar lector de
pantalla/dispositivo físico y conservar advertencias sintéticas/retrospectivas.
No se inició esa etapa ni se realizaron operaciones de Git de escritura.

## Etapa 16 — preparación académica

**Preparado para demostración académica experimental local**, con el alcance
condicionado del [guion de siete minutos y lista de preparación](SIGARD-resumen-desarrollo.md#8-guion-académico-de-siete-minutos).
No equivale a un sistema completo y validado para utilización epidemiológica real.
Se mantienen **15 completas, ocho parciales y tres bloqueadas**; no se promovieron
estados por documentación o pruebas SQLite.

Inicio nuevo comprobado mediante `npm.cmd --prefix frontend run dev`: Vite en
`127.0.0.1:5173` y API A/B en `127.0.0.1:8765`, sin base de datos. Un intento con
5173 ocupado se rechazó sin detener procesos ajenos; después se cerró el comando
propio de la etapa anterior y se inició de nuevo. La API habitual de reportes,
cuentas y publicación persistente **no forma parte de ese comando**. La navegación,
mapa público con respaldo estático, prevención y directorio funcionan localmente;
la API pública también se probó mediante HTTP/SQLite descartable con artefactos
aprobados. Reportes/seguimiento y administración se verificaron en el navegador
del harness, que redirige sólo sus propias solicitudes a una API temporal y limpia
SQLite al terminar. No habilita ese circuito en el navegador normal del expositor.

**Un defecto adicional demostrado y corregido:** Chromium tabulaba los 263 polígonos
por los listeners de foco de los tooltips antes de llegar al selector público.
`TerritorialMap` asigna `tabindex=-1` a esos paths al añadirlos, sólo en vistas con
selector textual (pública completa e investigación). El mapa compacto permanece
igual, y la selección por clic/hover se conserva. Se amplió el harness existente
para comprobar Tab desde el mapa hasta el selector en menos de 12 pasos, sin
detenerse en paths. La prueba adicional recorrió navegación, selector público,
selector A/B, historial y reintento de catálogo fallido con Tab/Enter a 1440/390 px.

**Cierre de pruebas:** 79 backend aprobadas/una omitida PostgreSQL; 912 ML seguras
aprobadas/cuatro deseleccionadas y ocho módulos excluidos; 51 frontend aprobadas.
Total **1.042 aprobadas, cero fallidas, una omitida**, sin contar repeticiones.
Lint/build/recursos públicos y 178 controles de seguridad aprobados. Se conservan
las advertencias de deprecación de etapa 15. Navegador: 11 grupos integrales,
sin excepciones JavaScript/advertencias React; A/B concilió nuevamente 40
colecciones, 10.520 filas, 36 métricas y 20 semanas con resultados congelados.
Capturas revisadas en escritorio y viewport móvil; sin desbordamientos de página.
CDP comprobó nombres accesibles y contraste de muestras en nueve contextos, con
foco visible. No hubo lector de pantalla ni dispositivo físico; no es una auditoría
WCAG completa. La herramienta visual integrada falló al inicializar; Chromium
existente se ejecutó fuera del sandbox para completar estas verificaciones.

Los primeros intentos del harness temporal corrigieron etiquetas de recibos y
la secuencia de apertura de un selector nativo; no se modificó el producto para
eludirlos. Los recibos/capturas nuevos están en `frontend/.tmp/stage16-*`, JUnit
en `ml/.tmp/stage16-safe-tests.xml`, excluidos de Git y recursos públicos.

**PostgreSQL/PostGIS sigue sin verificar en vivo.** No se conectó, consultó ni
modificó ninguna base de 5432, ni se inició clúster, contenedor o servicio.
La cadena Alembic volvió a compilar 30/24 sentencias PostgreSQL offline en ambos
sentidos; el ensayo administrativo SQLite reversible pasó. El
[procedimiento pendiente](../backend/README.md#ensayo-postgresqlpostgis-descartable--preparación-de-etapa-16)
define opción nativa 5434, PostGIS aislado 5435, bases de esquema y concurrencia
separadas, prueba del último administrador y limpieza. Requiere autorización
explícita; no se usará el volumen persistente de Compose. Sin ese ensayo, la
concurrencia PostgreSQL y las geometrías/importador permanecen pendientes.

Las ocho parciales mantienen las dependencias detalladas en etapa 15: PostGIS y
operación persistente; vigencia institucional del directorio; retención y operación;
accesibilidad integral y despliegue. Las tres bloqueadas conservan sus requisitos
externos, incluidos el target acreditado, alertas y gestión editorial. No se
obtuvieron fuentes adicionales ni se relajó el preflight. El inventario protegido
de 706 archivos conservó tamaños y fechas; los diez recursos públicos aprobaron
sus hashes y la consulta A/B coincidió con los resultados congelados. No se
entrenaron ni deserializaron modelos. Etapa posterior sin iniciar.
