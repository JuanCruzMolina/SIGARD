# Pipelines reproducibles de SIGARD

## Iteración 10: contrato frontend

```powershell
ml\venv\Scripts\python -m sigard_ml.export.frontend_mvp `
  --config ml/configs/frontend_mvp_export.json
```

El export sólo lee artefactos aprobados, valida la intersección temporal y copia
capas GeoJSON sin recalcular scores ni entrenar modelos. Los tres exports legacy
se conservan para que el frontend actual siga funcionando hasta Iteración 11.

## Iteración 9: análisis territorial

La auditoría 9.1 evalúa correlaciones, redundancia, contribución y sensibilidad
leave-one-out del índice estructural sin utilizar epidemiología. Produce
`structural_susceptibility_audit.json`; sus alternativas A/B/C/D son diagnósticas
y no reemplazan automáticamente la fórmula vigente.

```powershell
ml\venv\Scripts\python -m sigard_ml.territorial.analysis `
  --config ml/configs/territorial_analysis.json
```

Genera dos familias separadas: contexto territorial relativo con atributos
censales reales y una historia espacial experimental que reutiliza, sin
reentrenamiento, el escenario sintético existente. Ambas calculan ranks
deterministas independientes; no se combinan con el total temporal ni se
interpretan como probabilidad, incidencia o localización real de casos.

Desde Iteración 9.2 el artefacto vigente es `territorial_context.*`. Su score
pondera 50% magnitud demográfico-residencial y 50% densidad. Los artefactos
`structural_susceptibility.*` quedan congelados sólo como referencia histórica
de la auditoría 9.1 y ya no son sobrescritos por el pipeline.

## Iteración temporal departamental v0.2

La Iteración 8.1 compara sobre el mismo holdout congelado persistencia, RF con
22 features, RF reducido y RF reducido con target `log1p`. La selección de
hiperparámetros ocurre únicamente mediante walk-forward de development y se
publica en `department_temporal_variants_report.json`. La auditoría de los CSV
originales no permite interpretar registros ausentes como ceros: son tablas de
estratos positivos y no enumeran todas las jurisdicciones por semana.

La Iteración 8.2 añade dos Random Forest que predicen el cambio
`log1p(t+1)-log1p(t)`, usando sets minimal y minimal con clima. La reconstrucción
se realiza con `expm1` sin calibración ni clipping, y conserva exactamente los
hashes de development y holdout de 8.1.

La etapa independiente `department_temporal_random_forest` predice el total
oficial de Capital de la semana siguiente, sin usar radios ni simulación espacial:

```powershell
ml\venv\Scripts\python -m sigard_ml.evaluation.department_temporal_pipeline `
  --config ml/configs/department_temporal_random_forest.json
```

Usa walk-forward expansivo, selecciona una variante regularizada sólo en
development y conserva seis semanas finales como holdout. Debido a la cantidad
limitada y las discontinuidades de semanas oficiales, la evaluación se considera
exploratoria. Los ausentes nunca se rellenan con cero y el clima de la semana
objetivo no se utiliza.

## Etapa 7: artefactos estáticos del MVP

Esta etapa no entrena ni carga el modelo: filtra las predicciones ya generadas
de la variante seleccionada `rf_reduced_features`, conserva las cuatro semanas
de test y publica una vista territorial de la última semana objetivo. Ejecutar:

```powershell
ml\venv\Scripts\python -m sigard_ml.presentation.mvp_export `
  --config ml/configs/mvp_export.json
```

Produce `mvp_prediction.geojson`, `mvp_prediction_summary.json`,
`mvp_backtest.json` y el histórico opcional
`mvp_backtest_predictions.geojson` en `data/processed/`. Los tres primeros se
copian a `frontend/public/data/` como artefactos pequeños versionables de demo.
Una ejecución posterior requiere `--overwrite`, que sólo reemplaza estas
salidas de etapa 7.

`risk_level` usa cuantiles 25/50/75 de `predicted_cases` dentro de cada semana.
Es una categoría visual relativa, no un umbral sanitario oficial. El corte es
el sábado anterior a la semana objetivo y el backtest sólo usa las cuatro
semanas del test existente. El total oficial se obtiene sumando
`target_cases_next_week`, que conserva el total departamental, pero los targets
por radio son asignaciones sintéticas: no existe validación espacial real.

## Etapa 6.1: ajuste controlado del Random Forest

Esta etapa conserva literalmente el `evaluation_split.parquet` de etapa 5 y
evalúa las mismas 1.052 filas de test. Se ejecuta con:

```powershell
ml\venv\Scripts\python -m sigard_ml.evaluation.random_forest_variants_pipeline `
  --config ml/configs/random_forest_variants.json
```

El modelo original usa 300 árboles, profundidad máxima 12, hoja mínima 2 y las
18 features declaradas en `random_forest.json`. Las tres únicas alternativas
son `rf_regularized` (menor profundidad y hojas mayores), `rf_log_target`
(`log1p` al entrenar y `expm1` al predecir) y `rf_reduced_features` (11 señales
temporales, vecinales y meteorológicas, sin `population`, `households` ni
`dwellings`). Todas son `RandomForestRegressor`, usan semilla 20260807 y generan
predicciones continuas recortadas a cero.

La selección no minimiza ciegamente el MAE global. Primero exige guardas de
MAE/RMSE global y MAE sobre targets positivos; entre candidatas prioriza el
error absoluto semanal medio, luego el bias absoluto, el MAE en positivos y el
MAE global. Se comparan siempre PersistenceBaseline y el Random Forest original.

Las salidas nuevas son `random_forest_variants_metrics.json`,
`random_forest_variants_predictions.parquet`,
`random_forest_mvp_comparison.json`, `random_forest_mvp.joblib` y
`random_forest_mvp.json`. El target espacial por radio continúa siendo una
asignación sintética: los resultados no son evidencia epidemiológica, precisión
espacial real ni ubicaciones observadas de casos.

## Etapa 6: Random Forest de regresión

Con las salidas inmutables de la etapa 5 ya disponibles, ejecutar desde la raíz:

```powershell
ml\venv\Scripts\python -m sigard_ml.evaluation.random_forest_pipeline `
  --config ml/configs/random_forest.json
```

El proceso usa directamente `evaluation_split.parquet`: entrena con sus semanas
`train` y evalúa sólo las cuatro semanas `test` (1.052 filas), sin crear otra
partición. Las 18 features permitidas están enumeradas en la configuración; no
incluyen identificadores, fechas, coordenadas ni el target. No se imputan ni se
escalan variables, y los nulos o infinitos detienen la ejecución.

Produce, sin sobrescribirlos por defecto:

- `data/processed/random_forest_predictions.parquet`
- `data/processed/random_forest_metrics.json`
- `data/processed/model_comparison.json`
- `data/processed/random_forest_feature_importance.parquet`
- `ml/artifacts/random_forest.joblib`

Las predicciones continuas no negativas se usan sin redondear para las métricas;
la columna redondeada es sólo auxiliar para visualización futura. El baseline de
persistencia se informa únicamente como referencia de control. Tanto el target
por radio como las importancias corresponden a un escenario espacial sintético:
no son evidencia epidemiológica, localizaciones reales ni evidencia causal. En
esta etapa no se realiza tuning exhaustivo ni se utiliza SHAP.

## Etapa 5: evaluación temporal del baseline

Sin entrenar Random Forest, la referencia de persistencia se ejecuta desde la
raíz con:

```powershell
ml\venv\Scripts\python -m sigard_ml.evaluation.pipeline `
  --config ml/configs/baseline_evaluation.json
```

El corte usa semanas completas: reserva las últimas cuatro semanas consecutivas
del bloque temporal final como test y considera las anteriores como
desarrollo/train. No completa el salto entre bloques. `PersistenceBaseline`
predice los casos sintéticos asignados de `t+1` copiando exclusivamente los
casos disponibles en `t`; el target nunca se entrega al modelo.

Produce, sin sobrescribirlos por defecto:

- `data/processed/evaluation_split.parquet`
- `data/processed/baseline_predictions.parquet`
- `data/processed/baseline_metrics.json`

El JSON informa MAE, RMSE, mediana del error absoluto, MAE para targets
positivos, bias, porcentajes de ceros y errores de totales semanales. Los
targets por radio siguen siendo sintéticos y las predicciones no constituyen
evidencia epidemiológica ni ubicaciones reales.

Esta etapa construye el maestro territorial de Capital, La Rioja, sin modificar
las fuentes locales. Requiere Python 3.11 o posterior.

## Instalación

Desde `ml/`, crear un entorno virtual e instalar las dependencias mínimas:

```powershell
python -m venv venv
venv\Scripts\python -m pip install --upgrade pip
venv\Scripts\python -m pip install -r requirements.txt
```

GeoPandas instala transitivamente Shapely, PyProj y el motor de lectura
geoespacial. PyArrow se declara de forma directa porque es necesario para la
salida Parquet; pytest sólo se usa para las pruebas.

## Ejecución

Desde la raíz del repositorio:

```powershell
ml\venv\Scripts\python -m sigard_ml.ingestion.territorial `
  --config ml/configs/territorial_master.json
```

Salidas locales, excluidas de Git:

- `data/processed/territorial_master.parquet`
- `data/processed/territorial_master.geojson`
- `data/processed/territorial_quality_report.json`

Para ejecutar las pruebas:

```powershell
ml\venv\Scripts\python -m pytest ml/tests
```

## Etapa temporal: dengue y clima semanal

Desde la raíz del repositorio, la segunda etapa se ejecuta con:

```powershell
ml\venv\Scripts\python -m sigard_ml.ingestion.temporal `
  --config ml/configs/temporal_weekly.json
```

La configuración declara rutas, codificaciones, delimitadores, nombres reales
de columnas y el calendario epidemiológico argentino usado por el Ministerio de
Salud (domingo a sábado). No se lo trata como equivalente a ISO-8601. Produce:

- `data/processed/dengue_weekly.parquet`
- `data/processed/climate_weekly.parquet`
- `data/processed/department_weekly.parquet`
- `data/processed/modeling_weekly.parquet`
- `data/processed/temporal_quality_report.json`

Las ausencias no se imputan. `dengue_record_available` distingue una semana sin
registro de una semana con cero observado (`dengue_zero_cases_observed`), y
`climate_data_available`/`climate_week_complete` documentan disponibilidad y
cobertura climática. El JSON conserva procedencia, versión, unidad temporal,
condición observada y controles de calidad.

`epidemiological_status` clasifica cada semana como `observed`,
`explicit_zero`, `missing_record` u `outside_source_coverage`. La salida de
modelado conserva solamente semanas `observed` o `explicit_zero` con siete días
climáticos; nunca convierte una ausencia epidemiológica en cero.

La correspondencia de fechas se valida contra los calendarios y boletines del
[Ministerio de Salud](https://www.argentina.gob.ar/salud/epidemiologia/herramientas):
en 2024 la SE1 abarcó 2023-12-31 a 2024-01-06 y la SE52, 2024-12-22 a
2024-12-28, según el [índice oficial de boletines 2024](https://www.argentina.gob.ar/salud/boletin-epidemiologico-nacional/boletines-2024).

## Etapa 3: asignación espacial sintética

Desde la raíz del repositorio:

```powershell
ml\venv\Scripts\python -m sigard_ml.simulation.pipeline `
  --config ml/configs/synthetic_allocation.json
```

Distribuye cada total semanal real y agregado de Capital entre los 263 radios
mediante dos escenarios separados: multinomial proporcional a `poblacion`, y
clusters reproducibles basados en población y `neighbor_ids`. La configuración
registra semilla, versión, variables y parámetros. No usa clima ni genera
coordenadas puntuales. Los resultados son asignaciones sintéticas, no
observaciones ni ubicaciones reales de casos.

Produce, sin sobrescribirlos por defecto:

- `data/processed/synthetic_radio_week_population.parquet`
- `data/processed/synthetic_radio_week_clusters.parquet`
- `data/processed/synthetic_allocation_quality_report.json`

## Etapa 4: panel radio-semana para modelado

Sin entrenar modelos ni dividir datos, se ejecuta desde la raíz con:

```powershell
ml\venv\Scripts\python -m sigard_ml.features.pipeline `
  --config ml/configs/modeling_panel.json
```

Produce `radio_week_panel.parquet` con las 263 filas de cada semana disponible,
`modeling_panel.parquet` sólo con filas que poseen tres semanas consecutivas de
historia y target consecutivo, y `modeling_panel_quality_report.json`. Los lags
se buscan por fecha exacta, sin imputación; la media vecinal usa exclusivamente
`neighbor_ids` y casos de semanas anteriores. El target sigue siendo una
asignación sintética espacial en `t+1`, no evidencia epidemiológica por radio.

Las salidas no se sobrescriben salvo que se indique deliberadamente
`--overwrite`, que sólo alcanza los tres productos configurados de esta etapa.

El reporte controla conservación semanal exacta, 263 radios por semana,
duplicados, nulos, negativos, ceros, concentración y radios con mayor
asignación. Reemplazar deliberadamente esas rutas requiere `--overwrite`.
