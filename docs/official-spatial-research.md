# SIGARD Fase 5C: primer RF espacial de investigación

Versión `official-spatial-rf-research-0.5c.0`. Ejecutor aislado:
`sigard_ml.official.spatial_ml.research_training`. La autorización explícita
del usuario permite ajustar y evaluar retrospectivamente el Modelo A sobre el
escenario privado congelado de cobertura asumida. No autoriza entrenamiento
oficial, publicación, despliegue ni reclasificación epidemiológica.

## Contrato de autorización

`training_authorized=false` permanece tanto en las opciones del ejecutor como
en su autorización y productos. El permiso nuevo exige
`research_training_authorized=true`, referencia de decisión/responsable,
SHA-256 del manifiesto exacto del escenario, Modelo A, plan
`authorized_2024_only`, tipo `cero_asumido_experimental` y fechas objetivo
2024-01-07 a 2024-06-08. Reconoce explícitamente las limitaciones pendientes.
El ejemplo público contiene `research_authorization=null` y no puede entrenar.
No se modifica `access.private.json`, `apto_entrenamiento`, permisos de fuentes,
configuraciones ni gates de fases previas.

La excepción admite contexto censal retrospectivo, positivos provisionales,
negativos asumidos y disponibilidad/maduración no reconstruidas exclusivamente
en investigación. No declara que esos controles científicos estén satisfechos.
El ejecutor falla antes de `fit` si no existe ese permiso específico.

## Integridad y tiempo

Se exige la rama `entrenamiento-ML`, almacenamiento privado ignorado por Git y
destino nuevo directamente en `data/processed/official/`. Se verifican
manifiestos de Fases 5A/5B/escenario, hashes congelados, fuentes autorizadas,
parámetros preparados, igualdad de matriz A con su proyección original e
igualdad de etiquetas con su materialización autorizada. No se abren libros,
ingieren registros, geocodifican ubicaciones ni regeneran features.

Los objetivos son semanas completas y exactas t+1. Las fechas indicadas abajo
son del **objetivo**, no de origen:

- Entrenamiento: 2024-01-07 a 2024-03-02, ocho semanas; primer origen 2023-12-31.
- Validación: 2024-03-10 a 2024-05-04, ocho semanas.
- Prueba: 2024-05-12 a 2024-06-08, cuatro semanas.

Se comparan las particiones con el plan heredado y su reconstrucción exacta.
Se conservan las semanas objetivo purgadas 2024-03-03 y 2024-05-05.
Desconocidos excluidos de ajuste y métricas, conservados en denominadores de
cobertura; ninguna etiqueta o historia desconocida se imputa a cero.
Una violación de integridad detiene el experimento; no se reparan datos para
forzar su ejecución.

Las siete variables son área, población, densidad, número de vecinos, semana
epidemiológica de origen y su seno/coseno. Se verifica el calendario contra el
calendario oficial de origen, constancia temporal de las variables estáticas y
catálogo sin dependencia de historia desconocida ni offsets futuros. No entran
objetivos, radio como número, coordenadas, pendientes o banderas de cobertura.
Esto acredita integridad temporal computacional, no disponibilidad histórica
del Censo 2022 ni maduración de etiquetas. No se afirma validación operativa.

## Ajuste y evaluación predefinidos

Se preserva exactamente el protocolo RF A: 400 árboles, profundidad 10,
`min_samples_split=10`, `min_samples_leaf=5`, `max_features="sqrt"`,
`class_weight="balanced_subsample"`, semilla 20261016, `n_jobs=1`, bootstrap,
gini, sin OOB ni warm start. Sin optimización, imputación ni calibrador.
Los pesos usan únicamente bootstraps de entrenamiento.

El baseline `DummyClassifier(strategy="prior")` se ajusta sólo con etiquetas
conocidas de entrenamiento y conserva esa probabilidad en los otros bloques.
No se usa persistencia porque la disponibilidad histórica no está acreditada.
El umbral 0,5 ya estaba fijado en Fase 5B. Las pocas semanas y el cambio de
prevalencia no ofrecen una base robusta para ajustarlo; no se elige con
validación o prueba. No se reentrena incorporando validación antes del test.

Se guardan precision, recall, F1, average precision como PR-AUC primaria,
PR-AUC trapezoidal secundaria, ROC-AUC cuando existen ambas clases, Brier,
log loss y matriz `[[TN, FP], [FN, TP]]`. La precisión se informa como cero si
no hay predicciones positivas, documentando que es una convención. Los AUC no
definidos por una sola clase se guardan como null.

La calibración conserva diez bins uniformes predefinidos no vacíos, frecuencias
observadas, probabilidades medias, ECE descriptivo, Brier y log loss. Se compara
probabilidad media con prevalencia por partición y semana. No se ajustan
probabilidades con etiquetas de evaluación. Importancia MDI desde entrenamiento,
con sesgo por cardinalidad/correlación y dispersión entre árboles explícitos;
no es causal ni se utiliza para cambiar el conjunto de variables.

El diagnóstico semanal registra cobertura de etiquetas, prevalencia, métricas,
predicciones positivas y suma de probabilidades de todos los radios. Esa suma
se refiere a radios con etiqueta positiva esperada, no a cantidad de casos.
El pico se identifica retrospectivamente por radios con etiqueta positiva, sin
intervenir en selección. Se documenta el descenso y el rango de predictores
fuera del soporte de entrenamiento. No se prueban hipótesis ni construyen
intervalos suponiendo independientes radios vecinos o semanas de una temporada.

## Productos privados y reproducción

La ejecución autorizada usa `data/processed/official/spatial_rf_05c_v1/`.
Para repetir se exige otro destino nuevo; no sobrescribir. Conserva:

- Configuración y autorización de investigación vinculada al manifiesto.
- Informe Markdown, revisión y métricas JSON.
- Modelos RF/baseline `.research.private.joblib`, aislados de modelos existentes.
- Predicciones privadas agregadas radio–semana y agregados semanales CSV.
- Diagnósticos temporales, calibración, importancia y rangos, en Parquet/CSV.
- Claves de entrenamiento, versiones instaladas, `pip freeze`, copia del código
  y manifiesto SHA-256 de entradas protegidas, implementación y salidas.

El ejecutor repite el ajuste con la misma semilla y exige igualdad exacta de
probabilidades; además reabre sus propios modelos y exige predicción idéntica.
Verifica que fuentes, derivados, modelos e interfaz/API previos conserven sus
hashes. No exporta pacientes, domicilios o coordenadas. Los productos privados
no se versionan en Git ni se publican. Los archivos de código/configuración
ejemplo/pruebas/documentación no contienen datos del experimento.

```powershell
.\ml\venv\Scripts\python.exe -B -m sigard_ml.official.spatial_ml.research_training --config <configuracion-privada>
.\ml\venv\Scripts\python.exe -B -m pytest ml/tests/test_official_research_training.py -p no:cacheprovider --basetemp=ml/.tmp/phase5c-check
```

La matriz de pruebas usa datos ficticios: permiso diferenciado, bloqueo previo
al ajuste, destinos aislados, hashes alterados, t+1/calendario/purga, predictores
prohibidos o incompletos, desconocidos, clases degeneradas, calibración e
invariancia del modelo/baseline ante cambios en datos de evaluación.

## Interpretación y referencias

El acuerdo con etiquetas experimentales no valida epidemiología: ceros asumidos,
cobertura no verificada, positivos provisionales, fechas/ubicaciones aproximadas,
Censo 2022 sin disponibilidad histórica acreditada, maduración no reconstruida,
radios vecinos dependientes y pocas semanas limitan cualquier interpretación.
La clasificación de presencia aquí autorizada es un experimento separado del
objetivo de conteos sintéticos de `v0.1`; no lo reemplaza ni modifica el MVP.

Se aplicaron las skills solicitadas y se añadió su referencia procedimental:
Kassis, T., Agarwal, V., He, Y., Patel, D., & Brueckner, A. M. (2026).
[Scientific Agent Skills: A Library of Procedural Knowledge for Research Agents](https://doi.org/10.48550/arXiv.2609.00065).
No se incorporaron datos privados a consultas externas. La implementación sigue
la documentación de [RandomForestClassifier](https://scikit-learn.org/stable/modules/generated/sklearn.ensemble.RandomForestClassifier.html)
y [calibración de probabilidades](https://scikit-learn.org/stable/modules/calibration.html).
