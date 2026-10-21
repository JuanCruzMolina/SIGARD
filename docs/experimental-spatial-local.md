# Mapa experimental A/B sin autenticación

La rama `entrenamiento-ML` permite consultar directamente los resultados A/B
congelados desde React/Vite y FastAPI. No hay diálogo de Windows, tokens,
contraseñas, cookies, sesiones, caducidad ni confirmaciones para ver el mapa.
No se modifican modelos, datasets, geometrías ni calendario epidemiológico.

## Inicio local sin Docker

Requisitos: las dependencias de `frontend/` y el entorno `backend/.venv` con
`backend/requirements.research.txt` instalados. Si falta el entorno:

```powershell
python -m venv backend/.venv
.\backend\.venv\Scripts\python.exe -m pip install -r backend/requirements.research.txt
# Desde frontend/: npm.cmd install
```

Se reutiliza el registro privado existente en
`data/interim/official/spatial_app_session_v1/registry.private.json`, que autoriza
la proyección local y referencia los manifiestos A/B. Si falta o falla su
validación, se bloquea el arranque: no se reconstruyen datos ni se renuevan
manifiestos automáticamente para sortear errores.

Desde la raíz del repositorio, iniciar ambos servicios con un solo comando:

```powershell
npm.cmd --prefix frontend run dev
```

Desde `frontend/` también se puede ejecutar `npm.cmd run dev`.
El coordinador Node.js `frontend/scripts/dev.mjs` reutiliza el launcher
`app.research_local`, el entorno virtual existente y la configuración de Vite.
Espera a que la API esté lista antes de abrir el servidor de desarrollo.

Abrir **http://127.0.0.1:5173**: `/` redirige a `/mapa` y selecciona
**Investigación local A/B** automáticamente sólo en desarrollo con ese origen.
El catálogo y los primeros scores se consultan automáticamente. **Vista del mapa**
ofrece Modelo A, Modelo B y Diferencia B − A. Cambiar vista conserva semana y radio;
seleccionar un radio permite consultar ambos scores y su resta cuando existen.
**MVP sintético y contexto** conserva la vista original y sigue accesible con
el selector. **Situación actual** abre el dashboard original en `/dashboard`
durante el desarrollo local autorizado. En producción, `/` sigue mostrando
el dashboard y `/mapa` conserva la vista inicial del MVP, sin selector A/B.
Si la API experimental no está disponible, se muestra su error y se permite
reintentar; nunca se sustituyen sus scores por la simulación sintética.

No se necesita `SECRET_KEY`, `DATABASE_URL`, `VITE_LOCAL_RESEARCH` ni pasar hashes
por consola. El hash del registro se fija en memoria al iniciar y se verifica de
nuevo en cada consulta. Esto verifica artefactos, no autentica al investigador.

Si 8765 ya está ocupado, el coordinador sólo reutiliza la API después de
verificar salud, catálogo, versión de contrato y restricción de acceso local.
Esa API permanece activa al detener el comando. **Ctrl+C** cierra Vite y sólo
el árbol de procesos Python creado por el coordinador. La API también puede
iniciarse manualmente para reutilizarla:

```powershell
$env:PYTHONPATH = 'backend'
.\backend\.venv\Scripts\python.exe -B -m app.research_local
```

El puerto 5173 debe estar libre. Un servicio incompatible en 8765, un entorno
virtual ausente o un fallo de integridad bloquean el arranque con un mensaje;
no se detienen procesos ajenos, no se cambia de puerto ni se regeneran datos.
No se admiten argumentos para cambiar host/puerto. No hace falta iniciar Docker
ni PostgreSQL. Si un frontend previo ocupa 5173, detener únicamente ese servicio.
Build, preview, producción y la API habitual del puerto 8000 no cambian.

## Límites de red y privacidad

- El launcher fija **127.0.0.1:8765**, sin opciones de host/puerto, reload o
  workers; desactiva confianza en proxies y access logs, y rechaza Docker y
  entornos de despliegue conocidos. Vite usa **127.0.0.1:5173** por defecto.
- La API experimental es una instancia FastAPI separada dentro de la
  implementación existente. Sólo registra las seis consultas agregadas y
  `/health`. No necesita base de datos ni carga la configuración confidencial
  del backend público. No registra reportes ciudadanos, administración, archivos,
  documentación ni OpenAPI. `app.main:app` sigue sin rutas experimentales.
- Cada solicitud exige peer IPv4 loopback, Host exacto y ausencia de cabeceras
  de proxy. Las consultas experimentales requieren Origin exactamente
  `http://127.0.0.1:5173` y `X-Sigard-Research: local-read`. Este marcador es
  público y automático; no es un token. Orígenes ausentes, ajenos, `localhost`,
  otros puertos y peticiones cross-site se rechazan. No usar túneles ni proxies.
- CORS permite únicamente ese origen y consultas GET, sin credenciales. La API
  rechaza escrituras; el cliente usa `credentials: omit`. No hay estado de sesión.
  Como el acceso es sin autenticación, cualquier proceso del equipo puede leer
  los agregados con las cabeceras locales esperadas; no obtiene archivos fuente.
- Respuestas y errores llevan `no-store, private`, `no-cache`, `no-referrer`,
  `nosniff` y `DENY`. Los errores de integridad no revelan rutas privadas.
- La proyección usa exclusivamente campos permitidos de resultados ya autorizados
  para visualización local. No entrega Excel, registros individuales, direcciones,
  coordenadas individuales, etiquetas, valores de rezagos, configuraciones,
  datasets privados ni modelos serializados. No carga joblib ni ejecuta ML.
- Se conservan las exclusiones Git/Docker y la whitelist con hashes de los diez
  recursos públicos. A/B no se copia a `public/`, al bundle ni a tablas públicas.
  La administración de reportes del backend habitual conserva su JWT y rol admin.

Comprobaciones de disponibilidad y listeners:

```powershell
Invoke-RestMethod http://127.0.0.1:8765/health
Get-NetTCPConnection -State Listen -LocalPort 5173,8765
```

Ambos listeners deben mostrar `127.0.0.1`. El endpoint de salud sólo entrega
`status: ok`. Las consultas de investigación sin Origin/marcador son rechazadas.

## Consultas y contrato

Bajo `/api/v1/research/spatial`, sólo GET:

- `/models`: A/B, versiones y semanas disponibles.
- `/models/{A|B}/weeks`: semanas calculadas del modelo.
- `/models/{A|B}/scores/{target_week_start}?experiment_id=...`: 263 scores agregados.
- `/comparison/{target_week_start}/{radio_censal}`: ambos scores del mismo radio
  y semana; `comparable=true` sólo cuando existen ambos.
- `/evaluation`: seis métricas comparativas congeladas por modelo y partición,
  junto con el alcance temporal y cantidad de filas radio–semana evaluadas.
- `/history/{radio_censal}`: comparaciones A/B de ese radio en las 20 semanas
  objetivo calculadas; no agrega predicciones para otras fechas.

Las antiguas rutas `/session`, `/session/request`, `/session/claim` y
`/session/logout` ya no existen. No hay código de consentimiento ni identidad TCP.

Cada consulta valida registro, hashes, versiones, 20 semanas (8/8/4 sin las
purgadas), 263 radios, fechas t/t+1, particiones, duplicados y valores finitos.
Se conservan las máscaras descriptivas guardadas de B sin exponer sus valores
epidemiológicos. Consulta inexistente: 404; integridad incompatible: 503 genérico,
sin sustitución por otro modelo, simulación o cero.

El [contrato de resultados](experimental-spatial-results-contract.md) mantiene
la unidad radio censal y semana objetivo, el score bruto sin calibración y la
geometría censal aprobada unida por identificador canónico. Se conserva el mapa,
zoom urbano 13, colores, leyendas, comparación y encuadre al cambiar selectores.
Null es score no calculado; cero es disponible. Se mantienen las advertencias:

> Resultados experimentales retrospectivos. No representan predicciones epidemiológicas validadas ni deben utilizarse para decisiones sanitarias.

Positivos provisionales, negativos asumidos, cobertura y disponibilidad histórica
no acreditadas y prueba 2024 ya examinada siguen explícitos. La comparación no
establece superioridad de B. El acceso local no autoriza publicación ni uso sanitario.

## Panel de análisis de modelos

El panel comienza con una orientación desplegable y las variables de ambos
modelos: A usa territorio/calendario; B añade antecedentes experimentales de las
cuatro semanas previas. Ambos se entrenaron con etiquetas epidemiológicas
provisionales. La advertencia inicial resume negativos asumidos, cobertura no
acreditada, disponibilidad histórica incompleta y evaluación ya examinada.

El mapa reutilizable mantiene intervalos violetas idénticos para A/B. Diferencia
B − A usa azul para valores negativos, blanco para cero y ocre para positivos,
en escala fija [−1,1]; gris es ausencia de ambos scores comparables. El detalle
explica si falta un score o falló su consulta, sin tratar ninguno como cero.
La leyenda queda debajo del mapa para no taparlo en móvil. La resta se calcula
en memoria a partir de las colecciones validadas; no es predicción nueva,
incidencia, cantidad de casos ni aumento real del riesgo sanitario. No se guarda.

En **Investigación local A/B**, el panel **Análisis de modelos** aparece debajo
del mapa actual. Los nombres principales son **Modelo A** y **Modelo B**; sus
identificadores y versiones técnicos se consultan en un detalle secundario.

El selector de partición permite comparar entrenamiento, validación ya examinada
y prueba ya examinada. Presenta precisión, sensibilidad, F1, Average Precision,
ROC-AUC y Brier mediante valores y barras en escala fija de 0 a 1. Cada fila
explica la métrica y su dirección: menor Brier es mejor; las demás tienen
dirección mayor-mejor. Ninguna basta por sí sola para declarar superioridad.
La síntesis de la partición elegida se construye desde esas métricas, conserva
empates/faltantes y explicita los compromisos cuando favorecen modelos distintos.
Average Precision es el resumen guardado de precisión–sensibilidad, no un área
trapezoidal recalculada. Precisión, sensibilidad y F1 usan el umbral congelado 0,5.

Las métricas proceden de la tabla comparativa del experimento B ya incluida en
el manifiesto autorizado, que evalúa A/B sobre las mismas filas con etiquetas
conocidas. No se estiman métricas desde los scores del mapa. Un valor null se
muestra como no disponible. Si falta B o su tabla de métricas autorizada, la
consulta devuelve 404 y el mapa sigue disponible; un fallo de integridad bloquea
la consulta con 503. La [ampliación del contrato](experimental-spatial-results-contract.md#ampliación-local-de-etapa-10)
define la proyección mínima de ambas consultas nuevas.

Seleccionar un radio por mapa o selector permite comparar sus scores A/B para
la semana elegida. La selección se conserva al cambiar semana o modelo. Pulsar
**Ver evolución temporal** consulta las 20 semanas congeladas del radio y las
representa con líneas A/B y una tabla desplegable. La semana elegida queda
señalada; los saltos de semanas purgadas y los resultados faltantes interrumpen
la línea, sin interpolarse ni convertirse en cero. En móvil el gráfico permite
desplazamiento horizontal para conservar la legibilidad.

La explicación metodológica distingue scores experimentales, positivos
provisionales, negativos asumidos y evaluación retrospectiva. Un score elevado
no confirma un caso ni representa riesgo clínico validado. No están disponibles
curvas de calibración, métricas de baselines ni intervalos de confianza mediante
estas consultas; tampoco etiquetas observadas o registros individuales. No se
generan pronósticos fuera de las semanas ya calculadas ni se modifica el MVP.

## Verificación

Validación del inicio predeterminado (21/10/2026): `npm.cmd run dev` ejecutado
desde `frontend/` reutilizó la API experimental existente, tras verificarla.
En navegador se comprobó `/` → `/mapa`, A/B inicial, cambio de ambos modelos,
20 semanas, scores, comparación, historial, seis métricas y sus particiones,
acceso al MVP y al dashboard. Un fallo de conexión simulado mostró el error
experimental sin datos sintéticos y el reintento recuperó la consulta. El build
de producción conservó `/` en el dashboard y `/mapa` en el MVP sin selector A/B.
Sin errores JavaScript. Se aprobaron 53 pruebas frontend (18 del coordinador,
15 de investigación, 5 del mapa público y 15 de recursos públicos), lint, build,
178 controles estáticos de seguridad y `git diff --check`. La prueba del cierre
de procesos Windows requirió repetición fuera del sandbox y pasó. No se ejecutó
entrenamiento ni se modificaron datos, modelos o predicciones; sin Docker/PostgreSQL.

```powershell
.\backend\.venv\Scripts\python.exe -B -m pytest backend/tests -q -p no:cacheprovider --basetemp backend/.tmp/direct-access-pytest
# Focalizada en el contrato y la proyección experimental:
.\backend\.venv\Scripts\python.exe -B -m pytest backend/tests/test_experimental_results.py -q -p no:cacheprovider --basetemp backend/.tmp/analysis-pytest
.\ml\venv\Scripts\python.exe -B -m pytest ml/tests/test_repository_security.py -q -p no:cacheprovider --basetemp ml/.tmp/direct-access-security
.\ml\venv\Scripts\python.exe -B tools/check_repository_security.py
git diff --check
# Desde frontend/:
npm.cmd run test:dev
npm.cmd run test:research
npm.cmd run test:security
npm.cmd run lint
npm.cmd run build
```

Las pruebas usan artefactos ficticios con campos privados señuelo; cubren acceso
directo, todas las semanas, 263 filas, selectores, comparación, ausencia de
credenciales, rutas retiradas, bloqueos de red/origen, integridad, null/cero,
conservación del encuadre y MVP. No ejecutar suites que entrenan estimadores.

La comprobación visual de etapa 10 cubrió escritorio de 1440 px y móvil de
390 px: mapa de 263 radios, seis métricas, cambio de partición, selección de
radio y evolución temporal, sin errores de interacción reportados. Se verificó
la legibilidad móvil mediante ajuste de texto y desplazamiento del gráfico.

Validación de etapa 10 (20/10/2026): **82 pruebas aprobadas**: 36 del adaptador/API
experimental, 13 del cliente experimental, 15 de recursos públicos y 18 del
coordinador local. Lint, build y `security:check` aprobados. La prueba del cierre
del árbol de procesos se repitió fuera del sandbox por sus restricciones de
gestión de procesos; la ejecución final pasó. Sin entrenamiento, commit ni push.

Antecedente, validación del 19/10/2026: 40 pruebas backend, 135 de seguridad Python, 8 del
cliente experimental y 15 de recursos públicos aprobadas. Lint, build y 178
controles de seguridad del repositorio aprobados. HTTP real: 20 semanas por
modelo y 10.520 scores, comparación A/B, rutas privadas inaccesibles, ausencia
de cookies y listeners exclusivamente en 127.0.0.1. Se conservaron los SHA-256
de los 706 archivos existentes de datos/modelos/artefactos. Sin entrenamiento,
commit ni push. La herramienta de navegador no pudo inicializarse en dos intentos;
la interacción se verificó con pruebas de componentes, sin validación visual
manual en navegador.
