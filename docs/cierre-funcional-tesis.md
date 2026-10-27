# Cierre funcional del prototipo SIGARD para la tesis

26/10/2026 · rama `entrenamiento-ML` · base `e606979`, diagnósticos conservados
en `8758346`. Responsable de la revisión científica y aceptación: pendiente de
actuación humana; este documento registra comprobaciones técnicas del agente.

El prototipo ofrece los seis recorridos funcionales en una demostración local
con datos ficticios o recursos públicos aprobados. **No acredita superioridad
ML frente a persistencia ni habilita operación sanitaria.** La predicción directa
por radio se conserva; no se incorporó un modelo de ciudad y reparto territorial.

## Matriz de requisitos y módulos

Se contrastaron los seis módulos del pedido con `PRODUCT.md`,
`docs/plan-proyecto.md`, contratos de datos, implementación y pruebas. El archivo
original del anteproyecto citado por `PRODUCT.md` pertenece a una ruta de otro
equipo que no existe aquí; no se afirma haber revisado literalmente ese original.
La aceptación formal respecto del anteproyecto queda a cargo de sus responsables.

| Módulo | Estado inicial comprobado | Estado final del prototipo | Evidencia y límite |
| --- | --- | --- | --- |
| 1. Ingestión/procesamiento | Parcial en el recorrido web; pipelines offline e importador existentes | Completo para el lote ficticio local; parcial para operación institucional | CSV de 48 claves, fechas/códigos acotados, validación atómica, preservación de desconocidos y auditoría SQLite. Importador público: regresión SQLite aprobada; PostGIS real actual pendiente. |
| 2. Predicción ML | Parcial: V1/V2/V3 y A/B congelados, consulta principal privada separada del sitio | Parcial científicamente; consulta web demostrable | Fecha, radio y t+1/t+2/t+4; persistencia predeterminada; V3 ilustrativo en demo. Lector privado V2/V3 de 256 radios verificado sin inferencia. Superioridad ML y validación independiente pendientes. |
| 3. Geolocalización/mapas | Completo para el alcance local existente | Completo para demostración | Leaflet, 263 radios públicos aprobados, selección textual/polígono, reinicio de vista; seis rectángulos enteramente ficticios en análisis admin. Ubicación manual de reportes ficticios. Geocodificación externa deshabilitada en demo. |
| 4. Alertas configurables | Pendiente: avisos preventivos existentes no eran reglas de alerta | Completo experimental local | Crear/editar reglas, umbral de cantidad, radio/horizonte, habilitar/deshabilitar, evaluar manualmente, revisar candidatas, persistir/auditar. Sin alerta epidemiológica oficial, correo, SMS ni publicación automática. |
| 5. Autenticación/roles | Completo en la API y bandeja local; acceso poco visible en navegación | Completo para el prototipo | Administración visible, login existente, permisos comprobados en servidor en cada ruta, cuentas y revocación existentes; ciudadanía pública/anónima conforme al plan. Un token inventado o usuario no administrador no obtiene datos admin. |
| 6. Información preventiva | Completo para consulta; edición institucional parcial | Completo para consulta; edición institucional parcial | Prevención, medidas y signos de alarma existentes, 27 centros públicos, directorio, reportes y seguimiento. No se implementó ni se acredita una aprobación/editorial sanitaria institucional. |

«Completo para demostración» no significa despliegue productivo ni validación
epidemiológica. No se cuentan controles decorativos como funcionalidades.

## Funcionalidades completadas

- Espacio administrativo **Análisis y alertas demo**, conectado a FastAPI real.
- Consulta histórica directa por radio/horizonte con fecha de origen y corte,
  selección de método, estimación y estado de disponibilidad. Los resultados
  anteriores desaparecen al cambiar selección o fallar la red.
- Lote CSV ficticio editable: 48 filas, ocho semanas y seis códigos inventados;
  el ejemplo inicial tiene 36 conteos conocidos y 12 desconocidos. Cambiar un
  conteo y cargarlo cambia la referencia ficticia consultada, con persistencia
  en la sesión. No es una animación ni una tabla desconectada del servidor.
- Reglas de alerta experimental persistentes, evaluación manual, revisión y
  auditoría. Una fecha sin datos no genera candidatas; reglas deshabilitadas y
  radios sin estimación no disparan alertas.
- Separación de demo y entorno privado: `dev:demo` no inicia ni consulta A/B.
  Los archivos A/B y V1/V2/V3 se conservan fuera del sitio y del bundle público.
- Leyenda del mapa de conteos corregida en móvil; selección textual, foco y
  detalle disponibles sin depender exclusivamente del color.
- Página de validación aclara que sus métricas del MVP departamental anterior
  no validan V3 ni una probabilidad territorial. No se alteraron métricas.

## Arquitectura efectivamente implementada

1. **Frontend React/Vite/Leaflet**, 127.0.0.1:5173. Vista ciudadana usa los diez
   recursos públicos aprobados por SHA y sus contratos existentes. No se añadió
   ninguna fixture ni predicción privada a `frontend/public`.
2. **FastAPI de demostración**, 127.0.0.1:8766, creada exclusivamente por
   `app/demo_local.py`. Reutiliza autenticación, cuentas, reportes y seguimiento.
   `app/demo_workspace.py` se adjunta sólo a esa factory y agrega
   `/api/v1/admin/demo/{catalog,query,ingestion,alerts,audit}` y operaciones de
   evaluación/revisión. La aplicación productiva no registra esas rutas: 404.
3. **SQLite descartable por sesión**, bajo `backend/.tmp/sigard-demo-*`.
   Usuarios, reportes y auditoría existentes; dos tablas adicionales de estado
   y auditoría ficticios. Tokens, reglas, candidatas y CSV no dependen de
   `localStorage`. El token de UI es transitorio en `sessionStorage`; el límite
   de autorización es la API, que vuelve a comprobar usuario, rol y versión.
4. **Procesos offline científicos congelados**, separados del backend. `dev`
   conserva el lector privado A/B en 8765. La consulta privada V2/V3 reutiliza
   predicciones selladas y no carga estimadores ejecutables. Vercel aloja sólo
   el frontend; no se supone que ejecute FastAPI, SQLite o PostgreSQL.

No se cargaron fuentes epidemiológicas originales. No se entrenó, ajustó ni
ejecutó ningún modelo V1/V2/V3/A/B. Se comprobaron intactas por hash **615 entradas protegidas** de
artefactos, derivados oficiales y recursos públicos. No se inició Docker ni se
accedió a PostgreSQL. La factory demo ignora `.env` y configuración persistente,
rechaza otros drivers/archivos y liga el servicio a loopback.

## Pruebas ejecutadas y resultados

| Comprobación | Resultado actual |
| --- | --- |
| Diagnósticos pendientes: fixtures y evaluador congelado | 33 pruebas aprobadas; sin ejecutar scripts de entrenamiento/diagnóstico privados |
| Regresión backend aislada | 177 aprobadas, 6 omitidas por requerir PostgreSQL; 65 avisos de deprecación existentes |
| Contratos/seguridad del nuevo espacio ficticio | 45 aserciones aprobadas: 401/403, token inválido/revocado, horizontes/fechas/radios inválidos, CSV, nulos, reglas/revisión y exclusión productiva |
| Lector privado V2/V3 | 34 aserciones de sólo lectura aprobadas; 256 radios, tres horizontes, selección individual, 2026 sin datos, entradas inválidas; sin exportar registros |
| Investigación/presentación frontend | 18 aprobadas, con fixtures ficticias y métricas conservadas |
| Recursos públicos/Vite | 15 aprobadas, incluidas denegación de privados y comprobación real de middleware dev/preview |
| Mapa público | 5 aprobadas |
| Cliente ciudadano | 4 aprobadas |
| Coordinador de desarrollo | 18 aprobadas; cierre sólo de procesos propios |
| Demo descartable | 13 aprobadas; incluyen las aserciones del espacio ficticio anterior, aislamiento y reinicio vacío |
| Navegador integral | 11 comprobaciones de recorrido aprobadas, con HTTP/SQLite reales y sin respuestas simuladas |
| Lint / build | Aprobados; sin dependencias nuevas |
| Seguridad estática del repositorio / espacios Git | 178 controles aprobados; diff de espacios sin errores |

Las 45 aserciones se incluyen dentro de una prueba de la suite demo: no se
suman como 45 tests pytest independientes. Las comprobaciones del lector privado
no son validación científica nueva. No se ejecutó una suite extensa de ML.

Se corrigieron dos problemas de herramientas encontrados: ESLint recorría
temporales ignorados con ACL restringidas; ahora excluye `.tmp`. El runner
backend intentaba reutilizar un `basetemp` histórico sin permisos; ahora crea
una ruta nueva por ejecución, sin limpiar carpetas previas. Se corrigió además
la coerción de horizonte en la nueva ruta y la conservación del CSV editado.
Los intentos fallidos no se consideran pruebas aprobadas.

## Rendimiento observado

| Acción | n | Mediana (ms) | Máximo (ms) |
| --- | ---: | ---: | ---: |
| Primera navegación al mapa público de 263 radios | 1 | 1678.01 | 1678.01 |
| Selección de radio en mapa público | 5 | 38.44 | 61.21 |
| Carga del espacio administrativo ficticio | 1 | 89.44 | 89.44 |
| Cambio de horizonte de consulta ficticia | 3 | 43.01 | 47.25 |
| Cambio de radio de consulta ficticia | 3 | 43.83 | 46.53 |
| Consulta 2026 sin datos | 1 | 31.38 | 31.38 |
| Validación y guardado del CSV ficticio | 1 | 27.61 | 27.61 |
| Evaluación manual de alertas ficticias | 1 | 61.46 | 61.46 |

Equipo: AMD Ryzen 5 5500, 12 procesadores lógicos, 15.9 GiB RAM; Windows win32 10.0.26300; Node v24.15.0; Chromium Chrome/152.0.7977.54 headless. Resolución 1440×1000 y comprobación adaptable a 390×1000. Vite en desarrollo, SQLite local y red loopback; sin limitación artificial de CPU/red ni peticiones externas. Navegador nuevo para el primer mapa y aplicación caliente para las acciones siguientes. Las 16 mediciones del recorrido final quedaron por debajo de 5000 ms.

El criterio de menos de cinco segundos se comprobó **en este entorno y con
este volumen de prueba**, desde la acción hasta detectar la respuesta en la UI
(polígonos/selector o resultado de la nueva consulta). No incluye el arranque
de servicios; no es una prueba de carga, concurrencia, red móvil, teléfono
físico, nube ni PostGIS. Las consultas web de seis radios ficticios no acreditan
el rendimiento de una futura API sanitaria de 256 radios. El mapa público sí
utiliza sus 263 geometrías aprobadas existentes.

## Evidencia visual y reproducción

Las capturas están en `frontend/.tmp/thesis-closure-ui/`, ignoradas por Git:
`empty-demo-1440.png`, `empty-demo-390.png`, `fictional-analysis-1440.png`,
`fictional-analysis-390.png`, `fictional-alerts-1440.png` y
`fictional-alerts-390.png`. Sólo contienen contexto público o fixtures, sin
credenciales. `checks.json` registra comprobaciones, equipo y mediciones; no
contiene códigos de seguimiento ni cuerpos de respuestas sanitarias.
Se revisaron capturas de escritorio/móvil y se confirmó que la leyenda no
superpone el selector, sin desbordamiento horizontal.

Desde la raíz, con las dependencias ya instaladas:

```powershell
npm.cmd --prefix frontend run dev:demo
```

Abrir **http://127.0.0.1:5173/**. No iniciar `dev` y `dev:demo` juntos. No abrir
Docker/PostgreSQL. La terminal muestra una cuenta admin temporal generada por
sesión; no guardar, fotografiar ni incluir sus credenciales en la tesis.

Guion: mapa público → prevención/directorio → reporte inventado y seguimiento
→ Administración/login → Análisis y alertas demo → consulta por fecha,
t+1/t+2/t+4 y D01/D05/D06 → 2026 sin datos → ingestión inválida/válida → regla
experimental y revisión → deshabilitar → volver a reportes/revisar → logout.
**Ctrl+C** cierra los procesos propios y elimina SQLite. Una segunda sesión
empieza vacía y rechaza reportes/tokens anteriores. Una terminación forzada del
sistema puede dejar temporales ignorados; nunca se reutilizan como otra sesión.

La vista real de investigación queda en `npm.cmd --prefix frontend run dev`,
exclusivamente para personas autorizadas en el equipo local. V3 continúa
congelada en su lector/visor privado; no abrir ni capturar esos resultados en
una demostración pública. La demo web no sustituye esa evaluación científica.

Comandos de comprobación (por separado, con puertos libres):

```powershell
npm.cmd --prefix frontend run lint
npm.cmd --prefix frontend run build
npm.cmd --prefix frontend run test:security
npm.cmd --prefix frontend run test:research
npm.cmd --prefix frontend run test:public-map
npm.cmd --prefix frontend run test:citizen
npm.cmd --prefix frontend run test:dev
npm.cmd --prefix frontend run test:demo
npm.cmd --prefix frontend run test:demo:browser
.\backend\.venv\Scripts\python.exe -B backend/tests/publication_isolated.py --backend-regression
.\backend\.venv\Scripts\python.exe -B tools/check_repository_security.py
git diff --check
```

El ensayo de navegador requiere Puppeteer/Chromium ya disponible; puede
indicarse el módulo existente mediante `SIGARD_BROWSER_MODULE`. No se instaló
una dependencia nueva para este cierre. No ejecutar pruebas demo junto a una
sesión demo abierta.

## Protocolo propuesto de aceptación con dos referentes del Ministerio

**Pendiente de ejecución. No hay participantes confirmados, firmas ni aceptación
obtenida.** Dos referentes designados por el Ministerio realizarían el recorrido
por separado; perfil sugerido: uno de vigilancia/análisis y otro de operación
territorial/comunicación. La designación y sus datos los completa la institución.

1. Registrar fecha, versión/commit, equipo/navegador, alcance ficticio y el
   consentimiento para observar la prueba. No utilizar datos personales reales.
2. Cada referente, sin intervención técnica durante la tarea, identifica qué
   información es pública, ficticia o privada y explica los límites del modelo.
3. Recorrer prevención y mapa; elegir radio/semana; comprobar que no puede abrir
   el panel administrativo sin credenciales. Acceder con cuenta temporal.
4. Consultar los tres horizontes, un radio disponible, otro sin estimación y una
   fecha de 2026. Verificar que un desconocido no aparezca como cero.
5. Cargar el ejemplo CSV y rechazar una entrada inválida. Crear regla, evaluar,
   revisar candidata, deshabilitarla y comprobar la persistencia tras recargar.
6. Crear/revisar un reporte ficticio y consultar su seguimiento como ciudadano:
   no deben aparecer coordenadas exactas, descripción ni notas internas.
7. Medir acciones de mapa/consulta con el mismo criterio de UI y registrar
   incidencias, ayuda requerida y comprensión de avisos. Criterio técnico
   propuesto: tareas esenciales completadas y cada respuesta observada <5 s
   bajo condiciones documentadas; ninguna exposición de información privada.
8. Registrar por referente y tarea: aprobado / observado / no aprobado,
   comentario y evidencia sanitizada. Si hay una filtración o se interpreta una
   alerta ficticia como oficial, no aceptar el cierre hasta corregirla.

Plantilla a completar: referente 1 — designación/fecha/resultados **pendientes**;
referente 2 — designación/fecha/resultados **pendientes**. No se sustituyen sus
opiniones por resultados automatizados ni se inventan firmas.

## Requisitos académicos e institucionales pendientes

- Superioridad del ML frente al baseline, conforme a
  [validación predictiva](validacion-predictiva-tesis.md), permanece no acreditada.
  No cambian métricas, selección, permisos ni embargo de nuevas entregas.
- Validación independiente compatible, cobertura/madurez y disponibilidad
  histórica; alcance epidemiológico definitivo y exactitud espacial reales.
- Aceptación de los dos referentes y contraste final con el anteproyecto original.
- Integración actual completa con PostGIS y despliegue persistente, sin reutilizar
  como evidencia actual los ensayos históricos de PostGIS.
- Política institucional de alertas reales, canales/receptores, umbrales aprobados,
  gestión editorial sanitaria y vigencia de contenidos/contactos.
- Accesibilidad integral con lector de pantalla y dispositivos físicos, carga
  concurrente y evaluación en infraestructura final.

No se inicia ninguno de esos trabajos como parte del cierre. La entrega es un
prototipo funcional local con límites explícitos, listo para revisión.
