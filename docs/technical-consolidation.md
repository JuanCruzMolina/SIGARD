# Consolidación técnica hasta Fase 5F

Actualización posterior de seguridad: las brechas históricas descritas abajo se
abordaron mediante exclusiones y comprobaciones en la tarea autorizada siguiente.
Ver [controles y límites actuales](repository-security.md). Las ocho skills y su
lock quedan locales por instrucción del usuario; ya no se propone versionarlas.

Revisión local: 17/10/2026. Rama `entrenamiento-ML`. Documento de preparación;
sin integración implementada ni autorización de publicación. No se cambiaron
archivos preexistentes para reorganizar o simplificar el proyecto.

## Estado del desarrollo

Al inicio: 166 archivos tracked, 224 untracked y 11 tracked modificados, sin
staging. Las modificaciones previas se conservaron. El desarrollo oficial nuevo
incluye 68 módulos Python, 13 configuraciones de ejemplo, 18 módulos de pruebas y
17 documentos `official-*`. Este inventario es del working tree, no una atribución
histórica por commits: las fases todavía no están separadas en el historial.

- Fases 1–2: contratos, autorización específica por fuente/uso, lectura Excel,
  normalización y calidad. Los ejemplos no contienen autorizaciones efectivas.
- Fases 3–4.3: cartografía, asignación territorial, calendario oficial y adaptación
  histórica explícita, paneles observados, revisión de fechas/cobertura/universo y
  conciliación. Desconocido, provisional y verificado permanecen separados.
- Fase 5A: matriz radio-semana, catálogo de predictores y cortes temporales.
- Fase 5B: elegibilidad experimental, faltantes, protocolo RF y escenario
  diferenciado de negativos asumidos.
- Fases 5C–5F: A entrenado, diagnóstico, historia candidata y B entrenado en
  carpetas privadas independientes; comparación retrospectiva exploratoria.

Preparación/ML corre offline. FastAPI/PostGIS sirven actualmente un lote publicado
del MVP; React/Leaflet consume ese contrato con fallback estático explícito. El
circuito ciudadano es independiente. No corresponde conectar automáticamente los
resultados oficiales experimentales con la simulación sintética ni con reportes
ciudadanos. `training_authorized=false` sigue bloqueando el flujo oficial.

## Seguridad de Git y Docker

La revisión verificó reglas reales de Git con sondas de rutas, inventario de
archivos visibles, esquemas de artefactos públicos y lectura de Compose/Dockerfiles.
El escaneo heurístico de secretos revisó 388 archivos de texto (3.654.749 bytes)
y no halló coincidencias de las reglas comprobadas. Una imagen binaria quedó
fuera del escaneo textual; el GeoJSON sintético grande se revisó por estructura,
sin imprimir coordenadas. No se inspeccionó el historial completo ni se garantiza
detección exhaustiva de datos personales por contenido.

Protecciones comprobadas:

- `data/datos oficiales/`, `data/interim/official/`,
  `data/processed/official/` y `ml/artifacts/` están excluidos de Git. Las
  excepciones genéricas para `.gitkeep` no reabren los directorios oficiales.
- Excel `.xls`/`.xlsx` están excluidos. Los modelos actuales de A/B y las
  configuraciones privadas permanecen dentro de los directorios protegidos.
- Compose usa contextos separados `backend/`, `frontend/` y `ml/`, no todo el
  repositorio. Las cuatro reglas `.dockerignore` excluyen las rutas oficiales
  declaradas y `.xls`/`.xlsx`. No se encontraron nombres de archivos sensibles
  candidatos en los contextos reales examinados, fuera de las exclusiones.
- Los Dockerfiles usan fuentes explícitas de `COPY`; no usan `COPY . .`.
  Sin embargo, `COPY public/`, `COPY app/`, `COPY src/` y `COPY configs/`
  son copias recursivas amplias dentro de esas carpetas.

Brechas de defensa comprobadas con sondas, **sin evidencia de filtración actual**:

1. Git ignora `.env`, pero no `.env.local` o `.env.production`. Las dos
   `.env.example` versionadas contienen ejemplos, no credenciales efectivas.
2. Sólo `ml/configs/official.private.json` tiene exclusión específica: variantes
   como `official.research.private.json` no están cubiertas. Un archivo privado
   en `ml/configs/` también podría entrar por `COPY configs/` del contenedor ML.
3. `ml/models/*.joblib` no cubre subdirectorios. Tampoco hay exclusión general para
   modelos o Parquet privados fuera de las rutas previstas, claves `.pem`,
   `credentials.json` o Excel `.xlsm`.
4. `frontend/public/data/*.private.json` y nuevos GeoJSON no se bloquean por nombre.
   Un archivo colocado allí podría entrar a Git y al build estático. El importador
   actual rechaza algunas claves privadas, pero una lista negativa no reemplaza
   una proyección de salida con campos permitidos explícitos.
5. `.dockerignore` no usa reglas Git. Las sondas estáticas muestran que las reglas
   raíz `.env.*` no cubren todos los secretos anidados y que modelos/variantes
   privadas podrían entrar por rutas no previstas. No se ejecutó build ni se
   envió contexto a ningún builder; el daemon local no estaba disponible. La
   evaluación estática sólo implementa el subconjunto de patrones presente,
   no es una certificación del motor Moby/BuildKit.
6. El servicio ML monta `./data` y salidas del proyecto como volúmenes locales.
   `.dockerignore` controla el contexto de build, no esos montajes. No iniciar
   servicios ni importar/publicar lotes como parte de esta consolidación.

Antes de una integración o publicación, ampliar las exclusiones con excepciones
explícitas para ejemplos y pruebas de regresión de nombres/rutas. Mantener los
datos privados en sus rutas actuales hasta entonces. No se modificaron reglas
existentes ni se creó un supuesto permiso para mover/exportar información.

La semántica de contextos y exclusiones se contrastó con la
[documentación oficial de Docker](https://docs.docker.com/build/concepts/context/#dockerignore-files).
No se enviaron archivos del proyecto a servicios externos.

## Qué conservar en Git y qué mantener privado

Versionables en la propuesta: código fuente, fixtures ficticios, pruebas,
documentación técnica sin filas sanitarias y `official*.example.json` con valores
de autorización vacíos/bloqueados. Los cambios previos de calendario conservan el
MVP histórico explícitamente; no recalculan sus resultados.

Fuera de los commits: fuentes Excel, normalizados y paneles, coordenadas y datos
identificables, etiquetas y proyecciones sanitarias por radio, predicciones A/B,
modelos `joblib`, autorizaciones/configuraciones privadas, reportes científicos
con resultados privados, manifiestos privados, credenciales y entornos/cachés.
No mover nada a `frontend/public`, `docs` o fixtures para facilitar su consumo.

`.agents/skills/` contiene ocho herramientas externas: `exploratory-data-analysis`,
`geopandas`, `matplotlib`, `networkx`, `scientific-critical-thinking`,
`scientific-writing`, `scikit-learn` y `statistical-analysis`. `skills-lock.json`
registra su procedencia `K-Dense-AI/scientific-agent-skills`. No son parte del
runtime ni del entrenamiento por importación automática. La instrucción posterior
es conservarlas locales, excluidas de Git/Docker, sin un commit de herramientas;
el hash de un `SKILL.md` no se equipara al hash agregado del instalador.

## Organización propuesta de commits

El [manifiesto de commits](technical-commit-plan.json) enumera **cada archivo**,
sin globs ni comandos de staging. Cubre todos los cambios existentes y los
documentos de esta consolidación; la propuesta no modifica el índice.

1. Infraestructura, controles de acceso y contratos: reglas Git/Docker existentes,
   paquete oficial, tipos y calendario base requerido por los contratos.
2. Procesamiento oficial y calendario: lectura/calidad, geografía base, paneles,
   fechas, cobertura, universo/conciliación y adaptadores del calendario legado.
3. Ingeniería espacial y preparación: matriz/catálogos/particiones 5A, protocolo
   y faltantes 5B, escenario asumido y construcción pura de historia 5E. Incluye
   el orquestador de revisión epidemiológica que importa utilidades de 5A;
   su lógica base permanece en el segundo commit.
4. Experimentos retrospectivos A/B y soporte de evaluación: entrenadores, métricas,
   diagnósticos y auditoría temporal reutilizados por B. Los módulos de métricas y
   viabilidad deben acompañar a los entrenadores porque B los importa; separarlos
   después dejaría un commit intermedio sin dependencias necesarias.
5. Verificación y documentación: pruebas focalizadas de las fases restantes,
   informes técnicos públicos, arquitectura/contratos y propuesta de integración.

Las skills externas y su lock se excluyen de la propuesta actual y se conservan
sin modificaciones. Las comprobaciones nuevas de seguridad acompañan al primer
commit en el manifiesto actualizado.

Las pruebas de contratos acompañan al primer commit; las restantes se agrupan en
el quinto para la revisión solicitada. Antes de ejecutar estos commits, comprobar
importaciones/pruebas relevantes de cada estado intermedio. La revisión estática
de dependencias del manifiesto no sustituye esa ejecución. Las exclusiones y
comprobaciones que en esta revisión estaban pendientes se incluyen ahora en el
primer commit propuesto; ver `repository-security.md`.

## Interfaz de resultados e integración futura

Se definió un [contrato interno recomendado](experimental-spatial-results-contract.md)
con modelo/versión, radio, semana objetivo, score bruto, escenario de cobertura,
disponibilidad y limitaciones. Propone leer Parquet congelados y verificar hashes;
no carga ni evalúa modelos dentro de solicitudes. El inventario confirmó que
las claves de los 263 radios coinciden con la cartografía pública existente.

Actualmente A se deserializa sólo para auditoría offline con hash, tipo y versión
comprobados. B se recarga para verificar su serialización local. Ambos se
entrenaron con scikit-learn 1.9.0; `ml/requirements.runtime.txt` fija 1.9.1 para
Docker. No se garantiza portabilidad de sus joblib entre esos entornos. No se
cambiaron dependencias: consumir scores guardados evita esa deserialización en
la demostración. A/B no son modelos operativos ni se vuelven a entrenar.

Frontend reutilizable:

- `Mapa.jsx`: estado de selección y composición de la vista.
- `TemporalControls`: selector y presentación de intervalo; requiere un adaptador
  explícito de semana objetivo/calendario oficial.
- `TerritorialMap`, `GeoJSON`, bounds y selección de radio: geometrías poligonales.
- `MethodNotice`, leyenda y panel de detalle: avisos permanentes de alcance.
- `sigardData.js`: patrón de cliente/validación, con contrato separado. Su fallback
  actual a simulación no debe ocultar la ausencia de un resultado A/B.

Todavía no existe selector A/B. La clave de refresco del mapa actual no incluye
modelo ni versión, y el tooltip/panel esperan `synthetic_scenario`, `percentile`
y `relative_level`: requieren adaptación posterior, no sólo renombrar columnas.

Backend reutilizable: separación entre importador offline, lote versionado,
geometría censal, validaciones y respuestas de sólo lectura. No reutilizar
directamente el router público, la tabla `ExperimentalSpatialResult` o el
importador del MVP: su clave no distingue A/B, espera otros productos y publica
exclusivamente un lote aprobado. Una primera demostración privada puede leer una
proyección versionada sin migración nueva; la persistencia se decide sólo cuando
sea necesaria. Reportes ciudadanos y coordenadas puntuales permanecen separados.

## Validación y próximos pasos mínimos

Se ejecutaron 153 pruebas focalizadas de contratos/calendario/permisos/integridad,
con métodos `fit` bloqueados, sin reentrenar. No se ejecutó suite global, build,
frontend ni servicios del backend; no cambiaron. A y B conservan los hashes de
sus modelos, predicciones y salidas de manifiestos (79 salidas de A, 27 del
experimento B y su entrega final adicional). `git diff --check` y la revisión de
espacios de los tres documentos nuevos quedaron aprobados; la evidencia final
registra los comandos, códigos de salida y advertencias de finales de línea.

Secuencia mínima posterior, sujeta a revisión del diseño:

1. Resolver brechas de exclusiones y aprobar la lista exacta de archivos para
   commits; revisar procedencia/licencias de las skills opcionales.
2. Revisar el contrato y el alcance privado de la demo; conservar la distinción
   retrospectivo/operativo y score/riesgo. No prometer una publicación pública.
3. Implementar después un adaptador offline pequeño de sólo lectura que verifique
   hashes, claves, fechas y lista permitida de campos, sin cargar modelos.
4. Añadir posteriormente el selector A/B y la capa experimental separada, sin
   fallback silencioso al MVP. Mostrar score bruto y, si se decide, escala relativa
   documentada; sin alertas o umbrales sanitarios.
5. Probar fixtures ficticios y una revisión local privada: alineación de semanas,
   263 radios, estados faltantes, aislamiento de modelos/versiones y ausencia de
   campos individuales. Una eventual publicación exige Control C separado.

La evidencia detallada y los hashes se guardan localmente en
`data/interim/official/technical_consolidation_v1/`, excluido de Git. No hubo
`git add`, commit, push, merge, cambios de rama, entrenamiento, modificaciones de
A/B, frontend/backend ni publicación. La revisión humana queda pendiente.
