# SIGARD

**Resumen del desarrollo hasta la etapa 11**  
Material de apoyo para comprender el proyecto y preparar la tesis.  
Síntesis documental: etapa 12 | 20 de octubre de 2026

**Preparación de etapa 16 — 20/10/2026:** el resumen histórico de las secciones
1–7 se conserva. El [guion de exposición](#8-guion-académico-de-siete-minutos)
y la lista de preparación al final describen la demostración actual. Consultar
la [matriz vigente](mvp-functional-status.md) para el estado de implementación.

## 1. Introducción a SIGARD

SIGARD es un prototipo informático para explorar información territorial y desarrollar modelos predictivos relacionados con el dengue en La Rioja Capital. Busca reunir preparación de información, análisis con Machine Learning y visualización en un mapa dentro de un flujo comprensible y reproducible.

El proyecto permite estudiar cómo construir esa herramienta y qué evidencia falta para utilizarla con fines epidemiológicos. Su objetivo general es apoyar el análisis por territorio y semana; su estado actual es experimental y no habilita decisiones sanitarias.

Hay dos recorridos distintos. El **MVP inicial** combina totales observados de Capital, distribuciones sintéticas por radio y predicciones de conteos. Los **modelos A/B** estudian presencia experimental de registros en la semana siguiente. No son el mismo objetivo ni deben interpretarse como ubicaciones reales de casos.

## 2. Arquitectura y tecnologías

La preparación y el entrenamiento se realizan fuera del servidor web. La API entrega resultados ya preparados y la interfaz permite explorarlos.

| Tecnología | Función dentro de SIGARD |
| --- | --- |
| Python y FastAPI | Preparar información y ofrecer servicios de consulta. |
| Scikit-learn | Construir y evaluar los modelos Random Forest offline. |
| React y Vite | Desarrollar y ejecutar la interfaz web. |
| Leaflet | Mostrar los radios censales y permitir su selección. |
| PostgreSQL/PostGIS | Persistir información y geometrías del circuito público. |
| Docker Compose | Definir entornos separados de base, API, interfaz y ML. |

### Demostración local actual

Con los entornos y resultados autorizados ya disponibles, ejecutar desde la raíz: `npm.cmd --prefix frontend run dev`. Luego abrir **http://127.0.0.1:5173/mapa** y elegir **Investigación local A/B**. El comando inicia Vite y la API experimental en el puerto 8765, sólo en el propio equipo. Esta modalidad no necesita Docker ni PostgreSQL y no entrena modelos.

> **Alcance:** la configuración Docker existe. En la etapa 11 se revisó su configuración y las migraciones sin conexión; su ejecución con PostGIS quedó sin verificar porque el daemon estaba detenido.

<!-- pagebreak -->

## 3. Procesamiento de información

La unidad de trabajo es el **radio censal y la semana epidemiológica**. Cada fila preparada debe conservar de dónde proviene, a qué período corresponde y si representa información observada, provisional, sintética o asumida para un experimento.

### Recorrido de preparación

1. **Acceso autorizado.** Se define qué fuente, versión y uso están permitidos. Los archivos originales se conservan sin modificaciones.
2. **Normalización y calidad.** Se ordenan nombres y formatos y se detectan campos faltantes, fechas inválidas o inconsistencias. Una corrección de formato no acredita un caso clínico.
3. **Clasificación e identidad.** Se distinguen registros, notificaciones y episodios. La palabra «confirmado» no basta para acreditar la confirmación; las posibles repeticiones requieren evidencia para resolverse.
4. **Referencia temporal.** Se conserva la diferencia entre inicio de síntomas, consulta, toma de muestra y notificación. Si se usa otra fecha como aproximación, queda identificada.
5. **Referencia espacial.** Se compara la ubicación disponible con la cartografía censal. Una coincidencia ambigua o sobre un límite conserva su incertidumbre; no se fuerza un radio.
6. **Variables y objetivo.** Se organizan características del territorio y del tiempo. El objetivo de la semana siguiente se busca en la fecha exacta, sin saltar huecos ni convertir faltantes en ceros.

### Calendario y cartografía

El procesamiento oficial utiliza el calendario epidemiológico argentino documentado para **2020 a 2026**, con semanas de domingo a sábado. No se asume que coincida con la numeración ISO. El perfil histórico del MVP se conserva por separado para no cambiar resultados anteriores.

La cartografía de La Rioja Capital contiene **263 radios censales**. Sus polígonos permiten organizar y comparar el territorio. Un radio es una unidad de análisis: no indica el domicilio de un paciente ni demuestra exactitud epidemiológica de una asignación.

| Tipo de información | Cómo debe interpretarse |
| --- | --- |
| Observada agregada | Total disponible para un territorio y período. |
| Sintética | Distribución generada para probar el flujo del MVP. |
| Provisional o asumida | Etiqueta de trabajo con evidencia o cobertura pendientes. |

> **Regla central:** desconocido no equivale a negativo. No encontrar registros en una semana no demuestra que no hayan existido casos.

<!-- pagebreak -->

## 4. Modelos predictivos

Los modelos A y B son **Random Forest de clasificación**: combinan muchos árboles de decisión para producir un score entre 0 y 1. En estos experimentos, ese valor se refiere a la presencia de registros con etiqueta experimental en la semana siguiente, no a la cantidad de pacientes ni al riesgo clínico de una persona.

### Qué aporta cada modelo

**Modelo A:** utiliza contexto territorial y calendario. Sus siete entradas son superficie, población, densidad poblacional, cantidad de radios vecinos, semana epidemiológica de origen y dos representaciones cíclicas de esa semana: seno y coseno.

**Modelo B:** conserva las siete entradas de A y agrega cuatro valores de presencia experimental de semanas anteriores, más cuatro indicadores que señalan si esos valores faltan. Tiene **15 entradas**. La información desconocida se conserva como faltante; no se imputa a cero.

| Grupo de variables | Modelo A | Modelo B |
| --- | --- | --- |
| Territorio: superficie, población, densidad y vecinos | 4 | 4 |
| Calendario: semana y representación cíclica | 3 | 3 |
| Historia local: semanas t-1, t-2, t-3 y t-4 | No utiliza | 4 |
| Indicadores de historia faltante | No utiliza | 4 |
| Total de entradas | 7 | 15 |

Los rezagos se cuentan desde la semana de origen t; el objetivo es t+1. Los identificadores de radio y las coordenadas de pacientes no se utilizan como predictores. El contexto censal es retrospectivo: su disponibilidad en cada fecha histórica todavía debe acreditarse.

### Cómo se entrenaron y evaluaron

Se realizaron experimentos autorizados y separados del entrenamiento oficial, con un protocolo fijo de 400 árboles y semilla reproducible. Los bloques se ordenaron en el tiempo, sin mezclar filas al azar. Se ajustó sólo con entrenamiento y no se volvió a entrenar incorporando validación antes de la prueba.

| Partición | Semanas objetivo completas | Cantidad |
| --- | --- | --- |
| Entrenamiento | 07/01/2024 al 02/03/2024 | 8 semanas |
| Validación ya examinada | 10/03/2024 al 04/05/2024 | 8 semanas |
| Prueba ya examinada | 12/05/2024 al 08/06/2024 | 4 semanas |

Se dejaron fuera las semanas iniciadas el 03/03 y el 05/05. Las etiquetas desconocidas se excluyeron del ajuste y de las métricas, pero se conservaron en la grilla de inferencia. También se utilizó una referencia simple basada en la proporción positiva del entrenamiento. Los modelos y sus resultados quedaron congelados; la demostración sólo los consulta.

<!-- pagebreak -->

### Métricas y resultados de la evaluación

Las métricas comparan las predicciones con **positivos provisionales y negativos asumidos**. Describen el acuerdo con esas etiquetas, cuya validez epidemiológica sigue pendiente.

| Métrica del panel | Explicación breve |
| --- | --- |
| Precisión | De las predicciones positivas, qué proporción tiene etiqueta positiva provisional. |
| Sensibilidad | Qué proporción de las etiquetas positivas provisionales fue detectada. |
| F1 | Resume el equilibrio entre precisión y sensibilidad. |
| Average Precision (AP) | Resume precisión y sensibilidad a distintos umbrales; no es el área trapezoidal. |
| ROC-AUC | Resume la capacidad de ordenar positivos por encima de negativos. |
| Brier | Mide la diferencia cuadrática entre score y etiqueta; menor es mejor. |

Precisión, sensibilidad y F1 usan el umbral fijo **0,5**. Los informes también documentan matriz de confusión, log loss y diagnósticos de calibración. Estos últimos no implican que se haya calibrado el modelo. No todas esas salidas están disponibles en el panel.

La etapa 11 comprobó **36 valores de métricas** frente a la evaluación congelada, además de las **20 semanas** de scores de cada modelo. Este resumen no reproduce valores privados ni proclama un ganador. La prueba ya fue examinada y sólo cubre cuatro semanas: no es una validación epidemiológica independiente. Una métrica aislada no establece superioridad.

## 5. Backend y frontend

El **backend** ofrece servicios de consulta, publicación aprobada del MVP y un circuito separado de reportes ciudadanos, seguimiento y administración protegida. La API experimental local lee únicamente proyecciones agregadas autorizadas, comprueba su integridad y no carga modelos ni expone archivos fuente.

La **interfaz React/Leaflet** permite:

- Explorar los 263 radios en el mapa y seleccionar uno.
- Cambiar entre Modelo A y Modelo B y elegir semana epidemiológica.
- Comparar los dos scores del mismo radio y semana.
- Consultar su evolución temporal en las semanas ya calculadas.
- Revisar métricas por partición y leer qué representa cada una.

Los huecos se conservan y los identificadores técnicos quedan en un detalle secundario. Las predicciones A/B no se incluyen en los recursos estáticos públicos. Si falta la API pública, el MVP puede usar su respaldo explícito; ese mecanismo no inventa resultados A/B.

<!-- pagebreak -->

## 6. Validación y controles

La revisión epidemiológica mostró que **una estructura técnicamente correcta no garantiza una interpretación epidemiológica válida**. Por eso se separaron controles de calidad, decisiones científicas y permisos de uso.

### Qué se implementó

| Componente | Función y límite |
| --- | --- |
| Auditoría de calidad | Identifica problemas y limita qué puede concluirse de los datos existentes. |
| Contrato de clasificación y cobertura | Distingue categorías verificadas, provisionales y desconocidas; define decisiones pendientes. |
| Validador epidemiológico | Revisa estructura, clasificación, fechas, identidad, cobertura y asignación espacial. No cambia etiquetas. |
| Preflight de elegibilidad | Separa consistencia técnica de usos experimental y acreditado. Exige respaldos aplicables; actualmente sólo los simula con datos ficticios. |
| Preparación controlada | Verifica autorización externa, reutiliza validador y preflight y entrega un informe. Sólo admite ejemplos ficticios y no habilita entrenar. |

Los controles informan **válido, advertencia, inválido o pendiente de acreditación**, con un motivo. No resuelven episodios sin evidencia ni aceptan como prueba una declaración del propio dataset.

El recorrido controlado es: **entrada autorizada, validación, preflight, decisión e informe**. Incluso con evidencias simuladas completas, el resultado no es una aprobación institucional real. El entrenamiento y la evaluación efectiva permanecen deshabilitados en este flujo.

### Evidencia técnica de la etapa 11

| Área de pruebas | Resultado documentado |
| --- | --- |
| Procesamiento y ML, selección segura | 912 aprobadas |
| Backend, con bases ficticias | 49 aprobadas |
| Cliente experimental, recursos e inicio local | 46 aprobadas |
| Total de la selección ejecutada | **1.007 aprobadas** |

También pasaron lint, build y 178 controles de seguridad, informados por separado. En navegador se verificaron los 263 polígonos, selectores, historial y panel en escritorio y móvil. Se corrigió un párrafo HTML anidado que producía advertencias de React.

Se excluyeron pruebas que entrenan o requieren otras entradas locales. No se reentrenaron modelos: la revisión comprueba software y contratos, no acredita casos ni capacidad predictiva sanitaria.

### Privacidad de la demostración

La API A/B escucha sólo en el equipo local y limita origen y solicitudes. No entrega registros individuales, domicilios, coordenadas de pacientes ni modelos serializados. La lectura local no usa autenticación de usuario; eso permite consultar los agregados desde procesos del propio equipo, sin autorizar exposición en red ni publicación.

<!-- pagebreak -->

## 7. Estado actual y próximos pasos

**SIGARD puede utilizarse para una demostración académica experimental local.** Permite explicar el recorrido técnico, explorar el mapa y comparar resultados retrospectivos A/B, manteniendo visibles sus límites.

| Estado | Qué comprende |
| --- | --- |
| Implementado y comprobado | Inicio único local, mapa de 263 radios, scores A/B, historial, métricas y controles técnicos. |
| Implementado con alcance ficticio | Validador, preflight y preparación controlada integrados para probar decisiones y bloqueos. |
| Experimental | Etiquetas provisionales/asumidas, contexto retrospectivo y comparación de modelos sobre períodos ya examinados. |
| Verificación adicional | Ejecución del stack público con PostgreSQL/PostGIS y Docker; auditoría de accesibilidad con lector de pantalla. |

### Qué falta para usar información acreditada

1. **Clasificación:** respaldar las definiciones y los criterios de confirmación aplicables a cada período.
2. **Episodios:** acreditar el significado de los identificadores y resolver notificaciones repetidas con evidencia.
3. **Cobertura:** demostrar cuándo y dónde puede interpretarse una ausencia como negativo verificado.
4. **Fechas:** aprobar el evento temporal y el tratamiento de referencias incompletas o aproximadas.
5. **Espacio:** definir el alcance admisible de las asignaciones y conservar las ambigüedades.
6. **Disponibilidad histórica:** demostrar qué información existía en cada origen y acordar un período no examinado para una evaluación independiente.

Cualquier nuevo procesamiento real, entrenamiento o publicación necesita una autorización específica. Tampoco se ha acreditado riesgo clínico calibrado. En la revisión de etapa 11, Docker estaba detenido: su validación histórica no demuestra que PostGIS estuviera funcionando en ese momento.

### Cómo se resolvieron diferencias entre documentos

Las guías anteriores reflejan su momento de elaboración; se tomó la etapa 11 como corte actual. La precisión sin predicciones positivas usa convenciones distintas en informes iniciales y diagnósticos posteriores (cero o indefinida). El panel conserva la comparación autorizada, sin rellenar faltantes.

### Fuentes documentales utilizadas

- **Estado y arquitectura:** `technical-consolidation.md`, `architecture.md` y `docker-development.md`.
- **Preparación:** `official-ingestion.md`, `official-geography.md` y `official-calendar.md`.
- **Modelos y evaluación:** `official-spatial-research.md`, `official-spatial-model-b.md`, `official-spatial-diagnostics.md` y `experimental-spatial-results-contract.md`.
- **Controles epidemiológicos:** `epidemiological-data-quality-audit.md`, `epidemiological-labeling-and-coverage-contract.md` y `official-epidemiology-review.md`.
- **Uso de la aplicación:** `experimental-spatial-local.md`, `backend/README.md` y `frontend/README.md`.

Salvo los README indicados, las fuentes están en `docs/`. Las variables de A/B y el límite ficticio de la preparación se contrastaron con el código correspondiente. Esta síntesis utiliza documentación, sin abrir datasets privados o registros individuales. Los resultados técnicos citados pertenecen a la etapa 11; en la etapa 12 no se ejecutaron entrenamientos ni se recalcularon evaluaciones.

## 8. Guion académico de siete minutos

**0:00–0:45 — Problema y objetivo.** Abrir la pantalla inicial.
«SIGARD estudia cómo integrar información temporal y territorial sobre dengue
en La Rioja Capital, organizarla de forma reproducible y explorar modelos para
la semana siguiente. Es un prototipo de tesis: distingue información observada,
simulación y resultados experimentales; no es una herramienta sanitaria validada».

**0:45–1:30 — Arquitectura y preparación.** Abrir **Cómo funciona**.
«Python realiza la preparación y scikit-learn los experimentos fuera del servidor.
FastAPI entrega resultados ya calculados; React/Vite y Leaflet permiten consultarlos.
PostgreSQL/PostGIS está previsto para persistencia y geometrías del circuito público.
La unidad de análisis es radio censal–semana epidemiológica. Se conservan fuentes,
procedencia, incertidumbre y calendario argentino; la cartografía comprende 263 radios.
Los validadores distinguen una estructura correcta de una etiqueta acreditada».

**1:30–2:30 — Consulta pública.** Ir a **Mapa público**, elegir un código con el
selector, cambiar semana y alternar contexto/simulación.
«El contexto censal describe el territorio. La simulación es una distribución
sintética para comprobar el flujo, no domicilios ni casos reales por radio. Los
colores son niveles relativos, no umbrales sanitarios». Señalar leyenda, detalle
agregado y fuente técnica del pie. El resumen temporal agregado y la clasificación
A/B son objetivos diferentes: no interpretar sus magnitudes como equivalentes.

**2:30–4:15 — Modelos A/B.** Elegir **Investigación local A/B**, Modelo A, una semana
y un radio. Cambiar a B conservando radio/semana; abrir **Ver evolución temporal**.
«Ambos son Random Forest de clasificación de presencia experimental en t+1.
A usa siete entradas de territorio y calendario: superficie, población, densidad,
vecinos, semana de origen y su seno/coseno. B conserva esas siete y añade cuatro
rezagos de presencia y cuatro indicadores de faltantes: 15 entradas. Desconocido
no se convierte en cero. La interfaz lee resultados congelados; no está entrenando
ni generando un pronóstico nuevo». Mostrar los dos scores, las 20 semanas y los
huecos, sin interpolarlos ni presentar un ganador.

**4:15–5:15 — Evaluación y límites científicos.** Mostrar **Análisis de modelos** y
cambiar partición. «Se evaluaron retrospectivamente con positivos provisionales
y negativos experimentales asumidos, con cortes temporales y semanas de separación.
Entrenamiento, validación y prueba ya fueron examinados. Precisión y sensibilidad
describen acuerdo con esas etiquetas; Brier menor representa menor error contra
ellas. Ni las métricas ni un score alto acreditan casos, riesgo clínico calibrado
o superioridad de B. Faltan cobertura negativa y disponibilidad histórica acreditadas,
definiciones institucionales y evaluación futura independiente». Mantener visibles
los avisos de uso no sanitario.

**5:15–6:15 — Prevención y circuito ciudadano/administrativo.** Ir a **Prevención
y ayuda**, mostrar contenidos, búsqueda y filtros del directorio. «Hay 24 CAPS y
tres hospitales; 23 CAPS requieren confirmar vigencia, por lo que no mostramos
disponibilidad de atención en tiempo real». Si está preparada la prueba aislada,
mostrar el recorrido automatizado con un reporte ficticio, su código, actualización
administrativa y cuentas ficticias. «La administración exige JWT, rol y confirmación
de contraseña; desactivar o rotar revoca tokens y se protege la última cuenta».
Si sólo está iniciado el comando habitual, mostrar formulario y login e indicar
que envío, seguimiento y administración necesitan la API independiente: no intentar
operaciones contra un servicio de finalidad desconocida ni usar credenciales reales.

**6:15–7:00 — Estado y trabajo pendiente.** Mostrar la matriz y su evidencia.
«Las pruebas actuales respaldan una demostración académica experimental local.
El ciclo HTTP y SQLite descartable está comprobado; PostgreSQL/PostGIS y su
concurrencia real siguen pendientes de un entorno autorizado. La matriz conserva
15 funcionalidades completas, ocho parciales y tres bloqueadas. Faltan también
confirmaciones institucionales y accesibilidad con lector de pantalla/dispositivo
físico. Estos límites forman parte de lo que la tesis permite concluir».

## 9. Lista de preparación de la demostración

- [ ] Confirmar rama `entrenamiento-ML`, entornos/dependencias existentes y
  artefactos autorizados íntegros. No regenerar faltantes ni reentrenar.
- [ ] Ejecutar desde la raíz `npm.cmd --prefix frontend run dev`; esperar **Listo**
  y abrir `http://127.0.0.1:5173/`. Vite 5173 y A/B 8765 deben escuchar sólo en
  `127.0.0.1`. No abrir túneles, exponer el equipo ni cambiar los hosts para proyectar.
- [ ] Ensayar mapa público, capas/semanas, selector, fuente y leyendas. El respaldo
  estático aprobado funciona sin API 8000; no equivale a una publicación PostGIS activa.
- [ ] Ensayar A/B, misma semana/radio, historial y métricas. La API local no precisa
  tokens ni PostgreSQL y no incluye servicios ciudadanos o administrativos.
- [ ] Ensayar prevención/directorio; preparar conectividad para teselas externas.
  Si no cargan, distinguir fondo cartográfico de polígonos/datos; evitar el
  geocodificador y cualquier ubicación personal durante la exposición.
- [ ] Para demostrar operaciones ciudadanas/cuentas, ejecutar con Vite activo el
  harness integral documentado en [frontend/README.md](../frontend/README.md).
  Inicia una API en puerto loopback libre y SQLite ficticio, redirige únicamente
  el navegador de prueba y limpia al cerrar. **No habilita esos servicios en un
  navegador común** ni deja una cuenta disponible después. Sin esa preparación,
  limitar la exposición al formulario/login y explicar la dependencia.
- [ ] Para una futura demostración manual persistente, autorizar y preparar por
  separado API habitual 8000, PostgreSQL/PostGIS descartable, migraciones, lote
  público aprobado y bootstrap ficticio. Esto sigue pendiente; no usar Compose
  ordinario con su volumen existente ni el PostgreSQL prohibido de 5432.
- [ ] Ensayar Tab/Enter, foco, escritorio y viewport móvil; no afirmar prueba con
  lector de pantalla o teléfono físico sin realizarla. Conservar los avisos científicos.
- [ ] Revisar [evidencia de etapa 16](mvp-functional-status.md#etapa-16--preparación-académica)
  y cerrar sesiones ficticias. Ctrl+C cierra los servicios que inició el coordinador;
  no detiene una API previamente reutilizada ni procesos ajenos.

**Condiciones que limitan o impiden la exposición:** puertos ocupados, dependencias
ausentes o integridad inválida impiden iniciar A/B; no se eluden los bloqueos.
Sin resultados autorizados, omitir ese recorrido. Sin API ciudadana preparada,
no demostrar envíos ni cuentas como operación real. Sin PostGIS no afirmar
integración geoespacial persistente. La falta de teselas afecta el fondo en línea.
El estado es **preparado para demostración académica experimental**, no sistema
completo y validado para utilización epidemiológica real.
