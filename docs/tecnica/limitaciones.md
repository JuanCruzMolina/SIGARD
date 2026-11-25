# Limitaciones conocidas y trabajo futuro (v1.0.0)

Documento único que consolida las limitaciones registradas durante la integración F0–F7
(noviembre de 2026). Cada una indica **qué pasa**, su **impacto** y una **posible solución**. El
detalle y la evidencia de cada fase están en `docs/diseno/admin-v2/inventario.md`,
`docs/tecnica/arquitectura.md` §6, `docs/predictive-module-final.md` y
`docs/verificacion-final.md`.

Ninguna de estas limitaciones expone datos personales ni valores protegidos. SIGARD sigue siendo
un **prototipo académico**: no es un sistema operativo de vigilancia.

## Resumen

| # | Limitación | Área | Impacto | Esfuerzo estimado de la solución |
|---|---|---|---|---|
| 1 | La auditoría no registra ingresos, intentos fallidos ni cierres de sesión | Auditoría | Medio | Medio |
| 2 | Las cuentas desactivadas no se pueden reactivar | Cuentas | Bajo | Bajo |
| 3 | El historial de un reporte se borra con el reporte al vencer la retención | Auditoría / reportes | Medio | Medio (requiere decisión) |
| 4 | Las fechas de la auditoría usan un desfase fijo UTC−3 | Auditoría | Bajo | Bajo |
| 5 | Alertas: sin conteo histórico en «Reglas activas» ni «próxima semana pendiente» | Alertas internas | Bajo | Bajo–medio |
| 6 | La auditoría no tiene pantalla en un despliegue | Auditoría | Medio | Medio |
| 7 | 6 pruebas PostGIS no se ejecutaron | Pruebas | Medio | Bajo (requiere autorización) |
| 8 | Aviso de seguridad de zod 3 por Puppeteer | Dependencias de desarrollo | Bajo | Bajo |
| 9 | Aviso de Vite: bloque principal > 500 kB | Rendimiento | Bajo | Medio |
| 10 | Carrera de Chromium con la interceptación en 12 suites de navegador | Pruebas | Bajo | Medio |
| 11 | Variabilidad de las mediciones de rendimiento | Rendimiento | Medio | Bajo |
| 12 | Clima de un único punto para toda la ciudad | Modelo / datos | Medio | Alto |
| 13 | Limitaciones conocidas del modelo predictivo | Modelo | Alto | Alto |

## Administración y auditoría

### 1. Sesiones no auditadas
- **Qué pasa:** no se registran los inicios de sesión, los intentos fallidos ni los cierres de
  sesión. Los intentos fallidos sólo se cuentan en memoria para el límite de 5 cada 15 minutos.
  Sí queda registrada la revocación de sesiones al rotar una contraseña o desactivar una cuenta.
- **Impacto:** ante un acceso indebido no se puede reconstruir quién ingresó y cuándo; la
  auditoría sólo muestra lo que se hizo después de ingresar.
- **Posible solución:** una tabla de eventos de sesión (ingreso, fallo, cierre, vencimiento) con
  la misma política de la auditoría actual: sin contraseñas ni datos libres, con listas cerradas,
  y una categoría «Sesiones» en la pantalla de Auditoría. Requiere un cambio de escritura en el
  ingreso y su prueba.

### 2. Sin reactivación de cuentas
- **Qué pasa:** la API no tiene un endpoint para reactivar una cuenta. En **Cuentas** una cuenta
  inactiva muestra «Sin acciones».
- **Impacto:** si se desactiva una cuenta por error, hay que crear otra con otro correo (el correo
  ya existe); el historial de la persona queda repartido en dos cuentas.
- **Posible solución:** un endpoint de reactivación con la misma protección que la desactivación
  (contraseña de quien autoriza, confirmación explícita, auditoría) que obligue a fijar una
  contraseña nueva al reactivar.

### 3. El historial de un reporte se borra con el reporte (dilema de la retención)
- **Qué pasa:** `citizen_report_audit` se borra en cascada con su reporte. Cuando la retención
  (180 días por defecto) elimina un reporte, desaparece su historial de auditoría.
- **El dilema:** conservar el historial completo retendría, más allá del plazo de retención, el
  texto libre de notas internas y mensajes públicos que guardan los cambios. Borrarlo pierde la
  trazabilidad de quién atendió el reporte.
- **Impacto:** después del vencimiento no se puede saber quién cambió el estado de un reporte ni
  cuándo.
- **Posible solución:** al vencer el plazo, conservar sólo metadatos (acción, actor, fecha y
  nombres de campos) y borrar los valores. Exige una decisión del responsable institucional sobre
  el plazo y el contenido que se conserva.

### 4. Desfase fijo UTC−3
- **Qué pasa:** los filtros de fecha de la auditoría usan un desfase fijo UTC−3. Argentina no
  tiene horario de verano desde 2009 y en Windows la biblioteca estándar de Python no trae base de
  zonas horarias (no se agregó `tzdata`).
- **Impacto:** ninguno hoy. Si volviera el horario de verano, los eventos cerca de la medianoche
  quedarían en el día equivocado durante ese período.
- **Posible solución:** agregar `tzdata` y usar `America/Argentina/Buenos_Aires` con `zoneinfo`.

### 5. Alertas: sin conteo histórico guardado ni «próxima semana pendiente»
- **Qué pasa:**
  - «Reglas activas» no muestra «Se habría activado N veces»: ese dato sólo existe al calcular la
    vista previa de una regla y no se guarda.
  - No hay botón «Evaluar la próxima semana pendiente»: la API no informa cuál es; se elige la
    semana con un selector.
- **Impacto:** quien revisa una regla tiene que volver a calcular su frecuencia para recordarla, y
  quien evalúa tiene que saber qué semana falta.
- **Posible solución:** guardar la frecuencia calculada con cada versión de la regla (con la
  versión de datos usada) y agregar a la API un campo con la última semana evaluada por regla.

### 6. La auditoría no tiene pantalla en un despliegue
- **Qué pasa:** la consulta (`GET /api/v1/admin/audit`) existe sólo en la API administrativa local
  (8767). En un despliegue de `app.main` las acciones se registran igual, pero `/admin/auditoria`
  muestra «La auditoría se consulta en el entorno local de administración (npm run dev).»
- **Impacto:** en un despliegue institucional sólo se puede revisar la auditoría con acceso directo
  a la base de datos.
- **Posible solución:** montar el mismo router de sólo lectura en `app.main`, con sus mismas listas
  cerradas y la consulta auditada, después de revisar CORS y el control de acceso del despliegue.

## Pruebas y dependencias

### 7. Pruebas PostGIS no ejecutadas
- **Qué pasa:** 6 pruebas se omiten en cada regresión del backend: 5 de
  `test_postgis_integration.py` (sin `SIGARD_POSTGIS_URL`) y 1 de `test_admin_accounts.py` (sin
  `SIGARD_TEST_POSTGRES_URL`). Usan un contenedor Docker descartable propio (PostGIS 17-3.5 en
  127.0.0.1:5435), y `AGENTS.md` prohíbe iniciar Docker.
- **Impacto:** la cadena de migraciones, el SRID, los índices, el bloqueo consultivo y la
  persistencia tras reinicio sólo están probados con SQLite y con evidencia histórica de PostGIS,
  no en la versión actual. El importador territorial tampoco recorrió PostGIS real.
- **Posible solución:** que el responsable autorice Docker para ese contenedor descartable, o
  adaptar las pruebas a la base de prueba del clúster WSL (`sigard_epi_test_v1`, puerto 55439).
  También pueden correr en un CI con servicio PostGIS.

### 8. zod 3 por Puppeteer
- **Qué pasa:** `npm audit` informa 4 avisos altos encadenados de zod 3.25.76, que llega por
  chromium-bidi → puppeteer-core → puppeteer 25.9.0. La corrección exige Puppeteer 25.18.1, y
  F7a fijó 25.9.0 exacto.
- **Impacto:** no alcanzable en la práctica: es una dependencia de desarrollo, no llega al sitio, y
  con Chrome Puppeteer usa CDP (no WebDriver BiDi) con mensajes del Chromium local.
- **Posible solución:** subir Puppeteer a ≥ 25.18.1 (con su Chrome), correr todas las suites de
  navegador y actualizar el manual de instalación.

### 9. Aviso de bundle > 500 kB
- **Qué pasa:** `vite build` avisa que el bloque principal supera 500 kB (unos 642 kB, 194 kB
  comprimido). No rompe el build.
- **Impacto:** la primera carga en conexiones lentas tarda más de lo necesario, porque baja el
  código de Administración y del visor aunque se visite sólo el sitio público.
- **Posible solución:** dividir por rutas con `React.lazy` (Administración y visor). Exige cambiar
  el contrato de `security/local-entry.test.mjs`, que renderiza `App` en forma síncrona, y Leaflet
  seguiría en el bloque principal porque lo usan el mapa público y Prevención.

### 10. Carrera de la interceptación en 12 suites de navegador
- **Qué pasa:** con la interceptación de peticiones de DevTools activa, Chromium a veces cancela
  un `POST` con preflight CORS justo cuando termina el preflight (medido: 3–6 ingresos fallidos de
  cada ~75–100; 0 de 60 sin interceptación). `test:predictive:browser --real` y
  `test:demo:browser` ya no interceptan. Otras 12 suites siguen interceptando porque inyectan
  errores o sirven fixtures.
- **Impacto:** no afecta a usuarios reales. Esas suites pueden fallar de forma intermitente; pasaron
  en todas las regresiones, pero un fallo aislado obliga a repetirlas.
- **Posible solución:** activar la interceptación sólo durante el estado que la necesita (como ya
  hacen las suites de contenido y cuentas), o servir las fixtures desde una API descartable en vez
  de interceptar.

### 11. Variabilidad de las mediciones de rendimiento
- **Qué pasa:** `performance.browser.mjs` mide en el mismo equipo de desarrollo. En el cierre de F6,
  de 3 corridas seguidas, la primera dio p95 7.601 ms en la carga del visor con 5 usuarios; las
  otras dos, 4.242 y 4.333 ms. Durante la corrida 2 había otra aplicación pesada abierta y el
  sistema llegó a memoria crítica. Las medianas de todas las operaciones quedaron bajo 5 s.
- **Impacto:** una sola corrida puede dar un resultado que no representa el sistema; el criterio
  (c) se apoya en medianas de varias corridas y en el entorno de producción.
- **Posible solución:** medir en una máquina dedicada o en un runner limpio, con varias corridas
  y su dispersión publicada, y repetir la medición antes de una aceptación formal.

Además, la prueba `test_local_launcher_process_serves_the_viewer_behind_login` de la regresión
backend se omite (sin fallar) si 8767 está ocupado; la regresión del backend debe correr con los
puertos libres, no en paralelo con las suites de navegador.

## Modelo y datos

### 12. Clima de un único punto
- **Qué pasa:** el clima es un export diario de Open-Meteo para un solo punto de la ciudad
  (2015–2024, sin faltantes), sin variación espacial y con procedencia no acreditada
  institucionalmente. El visor lo muestra como contexto de la semana previa.
- **Impacto:** las variables climáticas sólo explican variaciones en el tiempo, no diferencias entre
  radios; no se pueden atribuir diferencias territoriales al clima.
- **Posible solución:** estaciones meteorológicas institucionales o una grilla con varios puntos
  dentro de la ciudad, con su procedencia documentada, en un experimento nuevo y prerregistrado.

### 13. Limitaciones conocidas del modelo predictivo
- **Resultados:** ningún candidato ML está promovido.
  - ¿Cuántos?: *Corrección de la semana anterior v2* redujo el error medio (MAE) un 13,6 % frente
    a la persistencia en desarrollo 2021–2023, pero no cumplió todos los criterios prefijados
    (sesgo y error en semanas de mucha actividad).
  - ¿Dónde?: *Bosque aleatorio v2* empató con la persistencia (recall@10 0,160 contra 0,156, con un
    intervalo que incluye el cero).
  - El visor usa como referencia métodos estadísticos simples (persistencia, estacionalidad).
- **Datos:** registros no son episodios ni casos confirmados; la asignación a radio es mayormente
  aproximada (geocodificación); los ceros significan «semana cubierta sin registros», no ausencia
  de casos; 2022 incluye sospechosos, probables y descartados como positivos experimentales; el
  Censo 2022 aplicado a 2020–2021 es retrospectivo.
- **Evaluación:** 2021–2023 se usaron mucho en desarrollo y 2024 ya fue observado: no queda un
  tramo futuro intacto. Desbalance extremo (muy pocas radio-semanas con registros), una sola
  semilla y bootstrap descriptivo. Es una **reconstrucción retrospectiva**, no un pronóstico.
- **Impacto:** los resultados no sirven para decisiones sanitarias ni para alertas públicas; las
  alertas internas exigen aprobación humana y la publicación ciudadana está bloqueada.
- **Posible solución:** una evaluación prospectiva con entregas semanales nuevas (2025 en adelante)
  y un protocolo prerregistrado; resolver los criterios epidemiológicos pendientes (episodios,
  cobertura, llegada de los datos) con el Ministerio; mejorar la representación de las
  transiciones de cero a positivo y la señal espacial, sin búsqueda masiva de hiperparámetros.

## Pendientes institucionales relacionados

- Sesiones de aceptación con dos referentes del Ministerio (kit en `docs/aceptacion/`).
- Autorización institucional para publicar «Actividad registrada» con datos reales.
- Tarea programada de retención en un despliegue institucional.
