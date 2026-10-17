# SIGARD Fase 5E: viabilidad de características epidemiológicas temporales

Versión `official-spatial-temporal-feasibility-0.5e.0`. Preparación privada y
diagnóstico retrospectivo; no entrena, cambia modelos, etiquetas, cobertura,
hiperparámetros, umbrales o calibración. El entrenamiento oficial y el candidato
B permanecen explícitamente bloqueados.

## Alcance y ejecución

```powershell
.\ml\venv\Scripts\python.exe -B -m sigard_ml.official.spatial_ml.temporal_feasibility --diagnose-failure
.\ml\venv\Scripts\python.exe -B -m pytest ml/tests/test_official_temporal_feasibility.py -p no:cacheprovider --basetemp=ml/.tmp/phase5e-check
```

Consume `data/processed/official/spatial_assumed_2024_v1/`, el Modelo A y su
procedencia congelada en `spatial_rf_05c_v1`, el contexto privado de Fase 5A y
el grafo territorial ya validado. La comparación agregada previa de fechas se
reutiliza con su alcance 2020–2024 explícito. No abre Excel ni incorpora fuentes
en revisión, geocodifica o recalcula geometrías.

La salida nueva es `data/processed/official/spatial_temporal_feasibility_05e_v1/`.
Se exige `entrenamiento-ML`, ruta privada ignorada por Git, destino inexistente,
manifiestos/hashes intactos y banderas oficiales bloqueadas. Repetir requiere
otro nombre mediante `--output-dir`; no se sobrescriben artefactos previos.
El Parquet de particiones contiene tres planes completos. Se consulta solamente
el plan literal aprobado `authorized_2024_only` mediante filtro de lectura,
conservando todas sus filas, sin muestreo ni truncamiento de semanas. El límite
general de lectura es 100.000 filas seleccionadas; ese archivo admite hasta
250.000 filas previas al filtro explícito de plan.

## Tres pistas de historia separadas

- `presencia_exp`: copia de la etiqueta binaria provisional/asumida de la
  semana fuente. Los ceros ya autorizados permanecen experimentales. Unknown
  permanece null.
- `registros_provisionales`: cantidad original de registros en
  `casos_observados`, sin rellenar sus null con ceros de etiquetas. Puede ser
  incompleta si coexisten pendientes; no son conteos clínicos verificados.
- `registros_sin_pendientes`: la misma cantidad, enmascarada cuando existen
  pendientes. No se convierte por ello en vigilancia completa ni cobertura
  comprobada.

La autorización previa materializó etiquetas, no conteos negativos. Esta fase
usa los ceros sólo en la pista binaria y no interpreta una etiqueta negativa
como un conteo observado igual a cero. Un acumulado binario cuenta semanas
positivas, no casos; su versión vecinal cuenta pares vecino–semana positivos.
Se conserva la procedencia real/provisional/asumida/desconocida.

## Tiempo, ventanas y vecinos

La semana de origen es `t`; se predice presencia en `t+1`. Rezagos 1–4 consultan
exactamente `t-1` a `t-4`. Acumulados 4/8 usan `[t-W,t-1]`, excluyendo incluso
la semana contemporánea de origen. La semana fuente se obtiene de
`fecha_inicio_semana_objetivo` de la etiqueta anterior, evitando desplazar la
historia al reutilizar su fecha de origen.

Sólo se usan semanas fuente completas del 07/01 al 08/06/2024. Los bordes no se
rellenan con historia previa. Una ventana con una semana desconocida queda
null; no se saltan huecos ni suman sólo las semanas conocidas. Los indicadores
de disponibilidad y de soporte cuentan valores/banderas, no infecciones.

La suma vecinal exige todos los vecinos conocidos para cada semana y todas
las semanas para acumular. Un radio sin vecinos produce desconocido. Se
comprueba identidad, simetría, ausencia de duplicados y grados contra el núcleo
A, usando sólo atributos del grafo congelado y sin leer coordenadas.

Los cortes heredados y sus purgas supervisadas se conservan. Una semana purgada
puede aportar historia a un origen posterior cuando ya es pasado; no se
reincorpora como objetivo de entrenamiento/evaluación. El protocolo es de
origen móvil, no un pronóstico multisemana desde un único origen fijo.

## Reconstrucción retrospectiva y disponibilidad operativa

La matriz retrospectiva usa lo que hoy se conoce de semanas pasadas. No se
acreditaron fechas de llegada/revisión, maduración, declaración de ausencias ni
disponibilidad histórica del Censo 2022. Síntomas o toma de muestra no prueban
que el registro estuviera disponible en ese origen, ni autorizan inventar una
demora. La matriz operativa enmascara toda historia epidemiológica y las cuatro
variables censales; conserva sólo calendario conocido de antemano y claves
técnicas, sin autorizar un modelo operativo.

Se reporta disponibilidad por variable/conjunto, partición, semana y clase del
objetivo, tanto sobre grilla completa como sobre etiquetas conocidas. También
se cuantifican pendientes, positivos pendientes, desconocidos y bordes fuera
del escenario. Las filas con variables faltantes se conservan; no se impone un
complete-case-only dataset.

Se prepara un candidato separado `B_presence_experimental`, con núcleo A,
rezagos binarios locales 1–4 e indicadores de faltantes. No cambia el B de
conteos preparado en Fase 5B. Las ventanas y variables vecinales quedan como
candidatos de diagnóstico. El soporte de entrenamiento usa la regla técnica
heredada, expresamente no validada científicamente, sin selección desde test.
No se recomienda un acumulado de ocho semanas sin soporte en entrenamiento.

## Auditoría de la meseta del Modelo A

El perfilado EDA tabular no carga modelos. Un módulo scikit-learn separado
inspecciona exclusivamente el RF propio de Fase 5C, tras verificar SHA-256,
tipo, columnas, parámetros y la misma versión instalada de scikit-learn. No se
cargan modelos externos ni se vuelve a serializar el original.

Se reproduce la inferencia guardada, se recalcula el calendario de origen, se
contrasta orden/identidad de la matriz, valores float64/float32, umbrales y hojas
de todos los árboles. Un recorrido manual independiente reconstruye hojas y
probabilidades de las cuatro semanas de prueba. Se compara el estado de los
árboles y el archivo de modelo antes/después.

Se examinan sensibilidades de una variable estacional por vez y un barrido de
calendarios coherentes, manteniendo los 263 contextos territoriales fijos. Es
diagnóstico computacional del bosque existente, no entrenamiento, validación
de pronósticos o elección de parámetros. Los contrafácticos de una sola
variable pueden formar tripletas calendáricas no físicas y se etiquetan así.

## Productos y pruebas

Informe privado Markdown/HTML, revisión de seis preguntas, historia semanal de
procedencia, matrices retrospectiva/operativa/candidata B, referencia intacta
de etiquetas/particiones, disponibilidad por partición/semana/clase, soporte de
entrenamiento, pendientes, auditoría del RF, catálogo, código copiado, versiones,
estado de Git y manifiesto SHA-256. No se publican datos, pacientes, domicilios
o coordenadas. No se modifica frontend/backend ni se realiza commit/push.

Las pruebas específicas usan datos ficticios sin ajustar modelos: unidades,
fechas fuente, null/ceros, pendientes, ventanas incompletas, vecinos, huecos,
ausencia de información futura, bordes, retención de filas, vista operativa
cerrada, JSON no finito/duplicado, hashes y recorrido manual float32. Las suites
de entrenamiento previas no se ejecutan en esta fase.

Se aplican las skills scikit-learn, exploratory-data-analysis,
statistical-analysis y scientific-critical-thinking; se conserva trazabilidad
del borrador conforme a scientific-writing. Se incluye su referencia
procedimental: Kassis, T., Agarwal, V., He, Y., Patel, D., & Brueckner, A. M.
(2026). [Scientific Agent Skills](https://doi.org/10.48550/arXiv.2609.00065).
Las referencias metodológicas del informe provienen de la documentación oficial
de [RandomForestClassifier](https://scikit-learn.org/stable/modules/generated/sklearn.ensemble.RandomForestClassifier.html),
[DecisionTreeClassifier](https://scikit-learn.org/stable/modules/generated/sklearn.tree.DecisionTreeClassifier.html)
y [persistencia](https://scikit-learn.org/stable/model_persistence.html).
