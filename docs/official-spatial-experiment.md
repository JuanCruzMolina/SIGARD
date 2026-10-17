# SIGARD Fase 5B: selección y preparación del experimento espacial

Versión `official-spatial-experiment-preparation-0.5b.0`. Consume los derivados
privados de Fase 5A y la configuración preservada de Fase 4.3. No entrena,
no ajusta imputadores o calibradores, no evalúa modelos, no genera etiquetas
negativas y no reabre Excel ni repite geocodificación.

La unidad sigue siendo radio censal–semana de origen, con objetivo de presencia
de un registro elegible **provisional** en la semana exacta siguiente. Esta fase
no cambia los modelos temporal departamental y espacial sintético del MVP.

## Ejecución

```powershell
.\ml\venv\Scripts\python.exe -B -m sigard_ml.official.spatial_ml.experiment_pipeline --config ml/configs/official.spatial-experiment.example.json
.\ml\venv\Scripts\python.exe -B -m pytest ml/tests/test_official_spatial_experiment.py -p no:cacheprovider --basetemp=ml/.tmp/phase5b-check
```

Se exige `entrenamiento-ML`, autorizaciones de inspección/procesamiento vigentes,
manifiestos y fuentes intactos, `training_enabled=false` y
`materialize_assumed_zeros=false`. Sólo escribe en una carpeta nueva directamente
bajo `data/interim/official/`; rechaza destinos existentes, públicos o superpuestos
con entradas. El ejemplo usa `spatial_experiment_05b_v1`. Elegir otro nombre para
repetir sin sobrescribir. Las salidas están excluidas de Git y Docker.

## Auditoría de las 55 columnas

Para cada variante estricta/ampliada y conservadora/exploratoria heredada de
Fase 5A, `column_audit` informa cantidad/porcentaje de valores conocidos,
desconocidos, valores distintos y disponibilidad entre observaciones cuyo
**objetivo t+1 es positivo provisional**. `column_by_year` repite estos cálculos
por año epidemiológico de origen. Si un año no tiene objetivos positivos,
el porcentaje condicionado es null, no cero.

`column_policies` identifica rol, utilidad propuesta, dependencia de conteos
desconocidos, semanas fuente, uso de información futura y limitaciones de
disponibilidad histórica. La matriz debe coincidir exactamente con su catálogo,
sin objetivos, duplicados ni desalineación de claves; se rechazan offsets futuros.

Un indicador de disponibilidad puede estar completo aunque todos sus valores
sean falsos. Por eso se informan también su cantidad de valores verdaderos y
la disponibilidad de la variable subyacente. Los indicadores de semanas/vecinos
conocidos no son conteos epidemiológicos ni prueban cobertura de vigilancia.

Se excluyen inicialmente el radio/fecha como predictores, el año por su fuerte
dependencia de temporada, el conteo contemporáneo de origen por sus demoras no
resueltas y las banderas constantes de validación/disponibilidad. Se conservan
como claves o metadatos; podrían estudiarse luego en sensibilidades explícitas.
No se codifica el identificador censal como una magnitud numérica.

## Configuraciones A, B y C

El núcleo obligatorio común contiene siete variables: `superficie_km2`,
`poblacion`, `densidad_poblacional`, `cantidad_vecinos`,
`semana_epidemiologica`, `estacionalidad_seno` y `estacionalidad_coseno`.

- **A, básico:** sólo ese núcleo geográfico/estacional.
- **B, historia corta:** A más `registros_retro_rezago_1` a `_4`, opcionales.
- **C, completo candidato:** B más acumulados locales 4/8/12, rezagos vecinales
  1–4 y acumulados vecinales 4/8/12, todos opcionales.

La población, densidad, área y topología del universo censal 2022 son contexto
**retrospectivo**. Su presencia no acredita fecha de publicación ni disponibilidad
histórica de esos límites censales. No se imputan poblaciones, no se inventan
features y no se incorporan coordenadas, scores sintéticos o predicciones previas.

`set_comparison` separa disponibilidad del núcleo, disponibilidad conjunta de
todos los candidatos, disponibilidad entre positivos y filas con al menos una
variable histórica conocida. También se calcula por año. Exigir todos los
candidatos no es una regla de exclusión de filas; un C con cobertura conjunta
nula no elimina la grilla. La recomendación inicial es A, con B como sensibilidad
posterior y C como candidato exploratorio sujeto a soporte.

La elección de variables opcionales se deja preparada por corte cronológico:
se exige, como umbral de revisión editable, al menos veinte valores conocidos
por clase y una fracción conocida de entrenamiento de al menos 10%. No son
umbrales científicamente validados ni autorización de entrenamiento. El preview
usa sólo etiquetas retrospectivas conocidas de la partición de entrenamiento;
la selección futura exige además maduración/validación de esas etiquetas.
No se aplicó selección aprendida. Cambiar datos de validación/prueba no altera
ese diagnóstico de soporte en entrenamiento.

## Faltantes y disponibilidad temporal

La estrategia primaria es conservar `NaN` nativo en el RF y derivar indicadores
de faltantes para las variables opcionales admitidas. No se ejecuta imputación
ni se transforma null en cero. Los ceros respaldados heredados siguen siendo
ceros; un cero de seno/coseno o de disponibilidad no se interpreta como ausencia
epidemiológica.

La versión instalada y la capacidad `allow_nan` se comprueban construyendo un
estimador y consultando parámetros/tags, sin llamar `fit`, `predict` o `score`.
La [documentación oficial del RandomForestClassifier](https://scikit-learn.org/stable/modules/generated/sklearn.ensemble.RandomForestClassifier.html)
describe el soporte nativo de NaN y los pesos `balanced_subsample`.

`experiment_missing.numeric_view` ofrece una utilidad numérica sin ajuste:
conserva el original, identifica NaN, cero observado bajo política heredada,
contexto retrospectivo y disponibilidad temporal no acreditada. En modo
`point_in_time` enmascara valores sin evidencia explícita de disponibilidad en
el origen, aunque exista un valor retrospectivo. No infiere esa evidencia desde
inicio de síntomas, muestra o notificación. Esta fase no construye una matriz
operativa validada con los datos oficiales.

Una columna opcional totalmente desconocida en entrenamiento se descarta en ese
corte junto con su indicador; un núcleo obligatorio desconocido bloquea el ajuste.
Si una implementación futura necesitara imputación, deberá versionar una
estrategia como mediana más indicador y ajustar sus parámetros exclusivamente
con entrenamiento y etiquetas conocidas/maduras. Nunca se reescribirá el conteo
observado ni se llamará observación a una imputación. El fallback está deshabilitado.

## Elegibilidad y cobertura experimental

Se preservan las etiquetas `1/0/null` y los bloqueos de pendientes. Se verifica
la conciliación con Fase 4.3 y no se aplica una nueva correspondencia de etiquetas.
El inventario privado agrupa clasificación canónica y desenlace por fuente;
para considerar terminología de confirmado exige las banderas explícitas previas
de elegibilidad e identidad validadas, además de inclusión y clasificación.
La etiqueta literal `confirmado` no basta. La revisión de la fuente 2022 queda
separada, con su inventario y requisitos de definición histórica, evento, filtros,
universo anterior al filtrado, episodios y residencia.

Se reutiliza íntegramente `configuration.private.json` de Fase 4.3 y su plantilla
de declaración. Las envolventes candidatas previas son capacidad condicional,
no intervalos completos declarados ni negativos disponibles.

`declared_coverage_preview` valida responsable, fecha/referencia, intervalo,
justificación, procedencia, confianza, definición de casos, conciliación,
territorio, políticas de fechas y extracciones con filtros literales. Además
comprueba que el intervalo esté cubierto por los períodos de extracción
documentados. No completa períodos desde extremos observados ni nombres de
archivos. Sin declaraciones, no hay candidatos experimentales declarados.

La previsualización sólo permite celdas desconocidas sin pendientes, con semana
completa dentro del intervalo explícito y de la ventana existente. Conserva
positivos, ceros previos y desconocidos fuera del alcance. El objetivo candidato
consulta la semana exacta t+1; no salta huecos. Se guardan máscaras con condición
experimental propuesta, sin escribir conteos ni etiquetas negativas.

Incluso una declaración estructuralmente completa mantiene la materialización
bloqueada. Se necesita respaldo/reconciliación, revisión de elegibilidad y
autorización explícita separada del responsable. Un escenario asumido deberá
escribirse con versión propia y condición experimental, preservando el
conservador. El escenario `exploratory` heredado de Fase 5A no se reclasifica
automáticamente como un escenario de cobertura asumida.

## Protocolo del Random Forest, sin ejecución

Se preparan 400 árboles, profundidad máxima 10, mínimo 10 muestras por división,
5 por hoja, `max_features="sqrt"`, `criterion="gini"`, bootstrap,
`class_weight="balanced_subsample"`, semilla 20261016 y `n_jobs=1`.
No usa OOB como evaluación temporal. Las sensibilidades futuras tienen semillas
20261017 y 20261018 predefinidas. No se ejecutan búsqueda de parámetros,
reentrenamiento ni réplicas.

Se reutilizan los planes cronológicos purgados de Fase 5A, con los mismos cortes
para todos los radios y ambas políticas de fechas. Se cuentan clases en cada
partición; los desconocidos no son negativos. Deben existir ambas clases con
maduración y tamaño suficientes; tener dos clases no basta para validar un
experimento ni su independencia temporal. Los pesos sólo podrán calcularse
desde muestras de entrenamiento, sin SMOTE ni remuestreo de evaluación.

Baselines futuros: prevalencia calculada sólo en entrenamiento y persistencia de
la última semana disponible, con abstención si es desconocida/no disponible.
Métricas previstas: precisión promedio, ROC AUC con ambas clases, precisión,
recall, F1, matriz de confusión, Brier, log loss y curva de calibración. Informar
también cobertura de predicción y estabilidad por semana/radio/temporada.

El umbral descriptivo inicial es 0,5. Cualquier ajuste de umbral o calibración
sigmoide debe usar bloques cronológicos internos de entrenamiento y etiquetas
maduras de ambas clases; nunca test ni validación externa. Comparar fechas
estrictas/ampliadas con los mismos parámetros/semillas/cortes y reportar
desacuerdos de etiquetas. No escoger la política por resultados de test.

## Productos privados y pruebas

La raíz conserva `experiment_A/B/C.private.json`, protocolo, configuración,
configuración heredada de Fase 4.3, plantilla sin firmar, revisión, informe,
metadatos y manifiesto SHA-256. Cada variante contiene:

- `column_audit.private.parquet` y `column_by_year.private.parquet`.
- `column_policies.private.json`.
- `set_comparison.private.parquet`.
- `training_feature_support.private.parquet` y `partition_classes.private.parquet`.
- `eligibility_inventory.private.parquet`.
- `assumed_coverage_preview.private.parquet`, sin conteos o etiquetas negativos.

Los módulos nuevos `experiment_selection`, `experiment_missing`,
`experiment_coverage`, `experiment_protocol` y `experiment_pipeline` no alteran
la implementación de Fase 5A. Se conservan hashes de entradas, implementación,
salidas y archivos previamente protegidos, además de versión de scikit-learn.

Las pruebas ficticias verifican auditoría de 55 columnas/por año/entre positivos,
denominadores vacíos, indicadores falsos completos, conjuntos opcionales, nulos,
ceros respaldados, indisponibilidad temporal, rechazo de objetivos futuros,
invariancia ante cambios en evaluación, declaraciones incompletas, alcance,
pendientes/semanas parciales, no materialización, elegibilidad no validada,
reproducibilidad, manifiestos, permisos y conservación de fases previas.
La integración prohíbe explícitamente `fit` del clasificador/regresor/imputador
y la apertura de Excel. No ejecutar suites legacy que llamen entrenadores para
validar esta fase de preparación.
