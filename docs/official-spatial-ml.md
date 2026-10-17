# SIGARD Fase 5A: preparación espacial para Machine Learning

Versión: `official-spatial-ml-preparation-0.5a.0`. El paquete independiente
`sigard_ml.official.spatial_ml` prepara un dataset privado para revisión. No
contiene entrenamiento, imputación, generación de negativos ni evaluación de
modelos. Reutiliza las salidas preservadas de Fases 4/4.1/4.2/4.3; no abre Excel,
no repite ingestión, recuperación de fechas o geocodificación.

El objetivo oficial es la presencia de al menos un **registro elegible provisional**
en un radio durante la semana epidemiológica siguiente. La clasificación clínica,
el universo de selección, la identidad epidemiológica y la localización real
permanecen sujetos a revisión. Este circuito no cambia el objetivo de conteo ni
los modelos temporal departamental y espacial sintético del MVP.

## Ejecución y conservación

Desde la raíz, en `entrenamiento-ML`:

```powershell
.\ml\venv\Scripts\python.exe -B -m sigard_ml.official.spatial_ml.pipeline --config ml/configs/official.spatial-ml.example.json
.\ml\venv\Scripts\python.exe -B -m pytest ml/tests/test_official_spatial_ml.py -p no:cacheprovider --basetemp=ml/.tmp/phase5a-check
```

La configuración completa debe conservar `training_enabled=false` y
`generate_zeros=false`. El destino debe ser una carpeta nueva inmediatamente
dentro de `data/processed/official/`. Una reejecución usa otro nombre: el programa
rechaza cualquier carpeta existente. Todas las salidas están excluidas de Git y
de las imágenes Docker por las reglas privadas existentes. No publicar Parquet,
JSON, informes, metadatos ni hashes privados en documentación versionada.

El pipeline verifica autorizaciones de procesamiento/inspección, manifiestos de
fases anteriores, hashes de las fuentes, procedencia de auditorías y revisión del
universo, cartografía y fuentes censales. Compara hashes de los datos y artefactos
científicos antes/después. No transforma ni sobrescribe fuentes o fases previas.

## Ingeniería de características

La clave es `radio_censal + fecha_inicio_semana`, donde `t` representa la semana
de origen domingo–sábado. Se conserva la grilla completa de 263 radios y todas
las semanas que intersectan el período existente, incluidos sus bordes parciales.
Se comprueban los límites con `ar-snvs-2020-2026-v1`, sin reglas ISO implícitas.

- `registros_retro_origen`: conteo nullable en `t`.
- `registros_retro_rezago_1` a `_4`: conteos en la fecha exacta `t-k`.
- `registros_retro_acumulado_4`, `_8`, `_12`: suma de las semanas
  `[t-W,t-1]`, excluyendo `t`; exige todas las semanas conocidas.
- `vecinos_retro_rezago_1` a `_4`: suma histórica de todos los vecinos queen.
- `vecinos_retro_acumulado_4`, `_8`, `_12`: suma de los totales vecinales
  completos en `[t-W,t-1]`. Un vecino desconocido invalida su total semanal;
  una semana vecinal desconocida invalida todo el acumulado.
- Indicadores `*_valor_disponible`, `*_semanas_conocidas_W`,
  `vecinos_retro_conocidos_rezago_k` y `cantidad_vecinos`.
- Año y semana epidemiológica; seno/coseno con fase `(SE-1)/semanas_del_año`,
  usando 52 o 53 según el calendario corregido.
- Código del radio, superficie en km², población y densidad del Censo 2022,
  únicamente desde el maestro territorial validado uno a uno.

Los vecinos se contrastan contra `touches` de los polígonos preservados:
simetría, ausencia de autorrelaciones/duplicados, radios válidos y todas las
aristas presentes/ausentes. Se rechaza un grafo inconsistente; no se reparan
geometrías. Un radio sin vecinos conserva sumas vecinales null.

No se convierte ningún conteo null en cero. Cero en un indicador de disponibilidad
significa que no se conoce ningún valor, no ausencia epidemiológica. Una suma
de conteos positivos conocidos sigue siendo una suma de registros provisionales,
no un total de casos completo si su cobertura no está acreditada.

Población/densidad se comprueban como valores finitos no negativos; población
entera, superficie positiva, densidad consistente con población/área y superficie
con la geometría métrica. El maestro se vincula a las fuentes censales y su
reporte de calidad preservados. No se inventan poblaciones ni se extrapolan
entre años. No se incorporan coordenadas de pacientes, puntos sintéticos,
predicciones previas ni scores de susceptibilidad.

## Disponibilidad histórica y separación de tablas

El conteo en una semana pasada no demuestra que estuviera disponible al final
de ella. Inicio de síntomas, consulta, muestra y notificación son eventos
distintos de la incorporación al sistema y de revisiones posteriores de su
clasificación. No se reconstruyen snapshots ni se restan demoras supuestas.
El prefijo `retro` y `historia_disponible_en_origen_validada=false` hacen explícita
esta limitación. El Censo 2022 y las geometrías actuales también son contexto
retrospectivo; `contexto_censal_disponible_en_origen_validado=false` impide
presentarlos como disponibles operativamente en 2020 o en cualquier fecha sin
respaldo de publicación y versión territorial.

Cada combinación `{strict,expanded}/{conservative,exploratory}` tiene:

- `predictors_retrospective.private.parquet`: características e indicadores.
- `predictors_calendar.private.parquet`: proyección separada sólo de calendario
  y código territorial de la grilla. Tampoco habilita un modelo por sí sola.
- `labels.private.parquet`: objetivo `1/0/null`, fecha exacta `t+1`, validez de
  conocimiento, provisionalidad y presencia de fechas aproximadas.
- `context.private.parquet`: panel previo preservado, estados y calidad para
  auditoría. No debe incorporarse automáticamente a los predictores.
- `splits.private.parquet`: membresía por plan cronológico, filas purgadas y
  estado conocido/desconocido; ninguna fila habilitada para entrenar.
- `by_year`, `by_target_year`, `by_radio`, `feature_availability` y
  `classification_by_source`, todos `.private.parquet`.

Los escenarios conservador/exploratorio califican **cobertura**, conservando la
elegibilidad provisional exploratoria heredada de Fase 4.1. No equivalen a
elegibilidad clínica conservadora. Se mantienen ambos paneles de fechas para
medir el efecto de las referencias aproximadas sin sustituir las originales.

El objetivo se verifica nuevamente contra la semana exacta siguiente: `1` para
conteo positivo provisional; `0` sólo para un cero respaldado ya existente en
Fase 4.2; null para desconocido o semana posterior ausente. Nunca se crea un
negativo desde una ausencia. `objetivo_valido` significa etiqueta conocida;
`apto_entrenamiento` permanece falso.

## Diagnóstico y evaluación futura

Los agregados separan año de origen y de objetivo, conteos y clases, fechas
aproximadas, asignación incierta, celdas afectadas por pendientes, disponibilidad
por variable/año/radio y clasificaciones canónicas por fuente/desenlace. Los
pendientes potenciales no se suman entre celdas como registros únicos. Se
concilian registros incluidos y referencias aproximadas con la auditoría previa.
Los detalles por radio y cantidades pequeñas quedan en almacenamiento privado;
el informe de texto suprime cantidades positivas menores de cinco.

Se reutiliza la evidencia de demoras y sensibilidad geográfica de Fase 4.3.
En especial, los problemas de clasificación de la fuente 2022 permanecen
pendientes: una etiqueta literal no acredita confirmación clínica, laboratorio,
evento o pertenencia al universo. Esta fase no reclasifica registros.

Se proponen dos planes diagnósticos, sin elegir cortes por rendimiento:

1. Estaciones: entrenamiento anterior a validación desde 2023-SE1;
   prueba desde 2024-SE1.
2. Dentro de 2024: validación desde 03/03/2024 y prueba desde 05/05/2024.

El fin exclusivo es 29/12/2024 para evitar el borde parcial 2025-SE1. En cada
límite se exige `fin_semana_objetivo < inicio_siguiente_partición`; se purga el
origen cuya etiqueta cruza el corte. Todos los radios comparten fechas. Se
conservan las observaciones desconocidas para diagnosticar cobertura, excluidas
de futuro ajuste y métricas. Se cuentan ambas clases y semanas objetivo que las
aportan. Tener ambas clases es necesario pero no suficiente; sin tamaño muestral
y disponibilidad validados los planes siguen no aptos.

`evaluation_contract.private.json` define prevalencia estimada sólo en training
y persistencia de la última semana disponible, con abstención ante desconocidos;
preprocesamiento/encoders/imputación/calibración ajustados exclusivamente con
entrenamiento, maduración de etiquetas, Brier/log loss, precisión promedio,
discriminación sólo con ambas clases, calibración y cobertura de predicción.
No se calculan métricas ni se entrenan baselines. Debe informarse concentración
en 2024 y estabilidad por temporada, semana y radio.

La raíz conserva catálogo explícito de características, configuración,
metadatos/procedencia/versiones/reglas de selección, informe de implementación,
diagnóstico, evidencia de calidad heredada y manifiesto SHA-256 de entradas,
implementación y salidas. La aritmética y el orden son deterministas; no hay
generación aleatoria ni entrenamiento estocástico.

## Módulos y pruebas

`features.py`, `dataset.py`, `validation.py`, `diagnostics.py`, `splits.py` y
`pipeline.py` separan cálculo, estructura, validación, diagnóstico, particiones
y coordinación privada. No importan entrenadores ni dependen de API/frontend.

Las pruebas ficticias cubren rezagos/acumulados, nulos y ceros respaldados,
vecinos completos/incompletos/ausentes, grafo contrastado con polígonos,
valores censales inválidos, cambio de año corregido, huecos semanales, objetivos
0/1/null, cambios futuros que no alteran predictores previos, purga cronológica,
reproducibilidad binaria, permisos, manifiestos alterados, conservación de entradas
y rechazo de sobrescrituras. La integración ficticia impide abrir Excel.
