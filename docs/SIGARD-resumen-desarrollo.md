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

**0:00–0:30 — Inicio y alcance.** Ejecutar `npm run dev:demo` desde `frontend`
y abrir `http://127.0.0.1:5173/`. Esperar **Listo**; conservar la cuenta de sesión
sólo en la terminal, fuera de capturas, grabaciones e informes. «SIGARD es un
prototipo académico. A/B consulta resultados retrospectivos congelados de
presencia provisional en t+1; no genera predicciones nuevas ni habilita decisiones
sanitarias. Los reportes y cuentas de esta sesión son inventados y temporales».

**0:30–2:00 — Mapa A/B y radio.** Elegir una semana objetivo, alternar **Modelo A**,
**Modelo B** y **Diferencia B − A**. Seleccionar un radio por polígono o selector;
conservar la misma semana/radio. «A usa territorio y calendario; B añade cuatro
antecedentes experimentales y sus indicadores de faltantes. Ambos aprendieron
de etiquetas provisionales. Violeta usa intervalos fijos del score [0,1], no
probabilidades clínicas calibradas. En la resta, azul indica B menor, ocre mayor,
blanco igualdad y gris ausencia, nunca cero ni ausencia de casos». Mostrar ambos
scores sin elegir ejemplos por supuesto riesgo ni guardar resultados privados.

**2:00–2:45 — Historial y métricas.** Abrir **Ver evolución temporal**, señalar
los huecos sin interpolación y consultar valores por semana. En **Análisis de
modelos**, recorrer entrenamiento, validación y prueba ya examinadas. «Brier
menor es mejor; las otras cinco métricas se interpretan en dirección mayor-mejor.
Son métricas guardadas, con umbral experimental 0,5 y sin ganador general cuando
hay compromisos. No acreditan evaluación futura ni epidemiología». Mantener
visibles límites de cobertura y disponibilidad histórica; no inventar baselines.

**2:45–3:15 — Separar dominios.** Mostrar **MVP sintético y contexto** y volver
a A/B. «El contexto censal describe el territorio; la simulación del MVP es
sintética y tiene otro objetivo. Los reportes ciudadanos que crearemos no son
casos de dengue, no alimentan modelos y no se publican en este mapa». FastAPI
lee resultados existentes; Python prepara/entrena offline. Vercel aloja sólo
frontend. La demo usa dos API independientes y SQLite, sin Docker/PostgreSQL.

**3:15–4:00 — Prevención y directorio.** Ir a **Prevención y ayuda**; explorar
recomendaciones, filtro/listado de centros y un marcador. «Son fuentes públicas
de contexto, no establecimientos inventados ni disponibilidad actual acreditada.
El aviso de vigencia permanece. El mapa no necesita teselas externas en demo».
No activar teléfonos ni enlaces remotos durante la exposición.

**4:00–5:00 — Reporte y seguimiento.** Usar **Crear reporte ficticio**, elegir
una categoría, inventar descripción/barrio y marcar un punto manual con clic o
Tab/flechas/Enter sobre el mapa. «No usamos datos personales ni hechos reales;
geocodificación externa y geolocalización están deshabilitadas». Aceptar el aviso,
enviar y usar el enlace al código de seguimiento. Consultarlo: sólo aparecen
estado, fechas y mensaje público; descripción, barrio y coordenadas quedan privados.
El código se usa en la sesión y no se incorpora a informes ni artefactos.

**5:00–6:15 — Administración existente.** Entrar por **Administración demo** con
la cuenta generada en terminal, sin proyectar ni registrar las credenciales.
Localizar el reporte, revisar el detalle, cambiar a **En revisión** y escribir
un mensaje público ficticio. Guardar y recargar para comprobar persistencia
durante esta sesión. Cerrar sesión; volver a seguimiento e ingresar el mismo
código. «El cambio público ya aparece; la nota interna y ubicación siguen
restringidas. Se conserva autenticación, permisos y revocación, sin acceso libre».

**6:15–7:00 — Cierre y evidencia.** Ctrl+C en la terminal cierra Vite y las API
propias y elimina la base inventada; una API A/B previa, verificada y reutilizada
queda activa. Reiniciar `npm run dev:demo` y comprobar que el código anterior ya
no existe; cuenta, contraseña y clave de tokens son nuevas. Cerrar nuevamente.
«Esta evidencia demuestra el circuito técnico con SQLite descartable, no
PostGIS actual ni capacidad epidemiológica acreditada. No se entrenó ni recalculó
ML». Próxima prioridad académica: ensayar la exposición completa con el equipo
de tesis y registrar sólo hallazgos de usabilidad, sin credenciales ni resultados
privados. El comando habitual `npm run dev` conserva únicamente frontend + A/B.

## 9. Lista de preparación de la demostración

- [ ] Confirmar rama `entrenamiento-ML`, dependencias ya instaladas y artefactos
  A/B autorizados íntegros. No regenerar faltantes ni reentrenar.
- [ ] Liberar 5173/8766 sin detener servicios desconocidos. Una API en 8765 sólo
  se reutiliza tras verificar contrato y restricción local. No abrir dos demos
  ni ejecutar pruebas de demo mientras la sesión está abierta.
- [ ] Ejecutar `npm run dev:demo` desde `frontend`; esperar **Listo** y abrir
  `http://127.0.0.1:5173/`. Los tres listeners usan sólo `127.0.0.1`; no abrir
  túneles ni cambiar hosts para proyectar. Docker permanece apagado, sin 5432.
- [ ] Comprobar aviso de demo y enlaces a reporte, seguimiento y administración.
  Reservar un medio local privado para copiar las credenciales al login; no
  grabar/fotografiar la terminal o formulario con credenciales.
- [ ] Ensayar A/B, misma semana/radio, diferencias, historial y seis métricas.
  Los límites científicos permanecen visibles. El MVP usa su respaldo estático
  aprobado, sin afirmar una publicación territorial PostGIS activa.
- [ ] Ensayar prevención/directorio sin conexión; las teselas/fuentes externas
  se omiten sólo en demo. Inventar todo el reporte y seleccionar ubicación
  manual. No usar geolocalización real, direcciones personales ni datos de salud.
- [ ] Crear, seguir y administrar el reporte ficticio contra la API SQLite de esta
  sesión; recargar para comprobar el cambio. No es necesario ejecutar el harness
  de navegador ni preparar manualmente una segunda API.
- [ ] Cerrar con Ctrl+C; comprobar que desaparece `backend/.tmp/sigard-demo-*`
  de esta sesión. Reiniciar y comprobar código anterior inexistente; cerrar.
  Una caída del sistema/terminación forzada puede dejar temporales ignorados;
  nunca se recuperan como sesión ni se publican.
- [ ] Ensayar teclado y escritorio/móvil. Las pruebas a 1440/390 px no acreditan
  lector de pantalla ni teléfono físico. La integración completa PostGIS y las
  decisiones científicas/institucionales siguen pendientes fuera de esta demo.
- [ ] Revisar la [evidencia integral](mvp-functional-status.md#entorno-integral-de-demostración-descartable--21102026)
  y cerrar todas las sesiones inventadas al terminar.

**Condiciones que limitan o impiden la exposición:** puertos ocupados,
dependencias ausentes o integridad inválida bloquean el inicio; no se eluden los
controles ni se detienen procesos ajenos. Sin resultados autorizados no mostrar
A/B como operativo. Sin PostGIS no afirmar integración persistente geoespacial.
El estado es **entorno integral de demostración académica con datos ciudadanos
ficticios**, sin validación para utilización epidemiológica real.
