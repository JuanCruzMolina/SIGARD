# SIGARD Fase 5D: diagnóstico privado del primer RF espacial

Versión `official-spatial-rf-diagnostics-0.5d.0`. Consume exclusivamente
artefactos privados congelados de Fase 5C y derivados anteriores referenciados
por ellos. No entrena, no carga modelos serializados, no ajusta calibración ni
cambia hiperparámetros, umbrales, etiquetas, cobertura o permisos oficiales.

## Ejecución y entorno

```powershell
.\ml\venv\Scripts\python.exe -B -m sigard_ml.official.spatial_ml.research_diagnostics --plot-python ml/.tmp/phase5d-venv/Scripts/python.exe --diagnose-failure
.\ml\venv\Scripts\python.exe -B -m pytest ml/tests/test_official_research_diagnostics.py -p no:cacheprovider --basetemp=ml/.tmp/phase5d-check
```

La entrada predeterminada es `data/processed/official/spatial_rf_05c_v1/` y el
destino nuevo es `data/processed/official/spatial_rf_diagnostics_05d_v1/`.
La entrega con revisión visual y descomposición temporal de AUC usa
`data/processed/official/spatial_rf_diagnostics_05d_v2/`; la primera ejecución se
conserva como evidencia técnica, sin sobrescribirla. Añadir `--output-dir` con
esa ruta para esa versión, o elegir un nombre nuevo para futuras repeticiones.
Se exige `entrenamiento-ML`, entrada/salida ignoradas por Git y destino nuevo
sin superposición. Para repetir, indicar otra ruta con `--output-dir`; nunca
sobrescribir resultados ni modelos. Los errores detienen el diagnóstico y
conservan cualquier producto parcial privado para inspección.

El cómputo usa el entorno original de Fase 5C; los gráficos usan un entorno
aislado en `ml/.tmp/phase5d-venv/` con Matplotlib 3.11.2 y backend Agg. La caché
de fuentes se mantiene en `ml/.tmp/phase5d-mpl-cache/`. Las versiones numéricas
del análisis y del render se registran por separado. No se modifica el entorno
original para incorporar dependencias gráficas.

## Controles y métricas

Se verifican el manifiesto SHA-256 de Fase 5C, los archivos que protegía, la
matriz/etiquetas/particiones del escenario y las banderas oficiales bloqueadas.
Las probabilidades y clases guardadas deben coincidir con el umbral congelado
0,5. Las etiquetas desconocidas se excluyen del denominador supervisado; se
conservan en la grilla y cobertura. No se interpreta un negativo asumido como
ausencia comprobada.

Se recalculan precision, recall, F1, confusión y Brier con fórmulas, AP con
acumulaciones que respetan empates y ROC-AUC con rangos medios. Se contrastan
con scikit-learn, los productos de Fase 5C y las identidades de agregación
semanal. Brier, log loss y probabilidad media se ponderan por cantidad de
etiquetas conocidas; F1/AP/ROC-AUC agrupados no son promedios simples de semanas.

PR-AUC primaria significa average precision, sin interpolación trapezoidal.
La PR-AUC trapezoidal guardada se verifica como secundaria, con advertencia
sobre scores constantes. Precision sin predicciones positivas se declara no
definida en el diagnóstico; se conserva y verifica el cero convencional usado
por Fase 5C. No se cambian los artefactos originales.

Se conserva el baseline de prevalencia calculada sólo en entrenamiento. Se
comparan diferencias de AP/ROC-AUC/Brier/log loss y habilidad Brier respecto de
ese baseline fijo, sin construir un baseline usando prevalencia futura.

## Diagnósticos

- Las cuatro semanas de prueba conservan positivos/negativos experimentales,
  desconocidos, cobertura, probabilidades, TP/FP/TN/FN y métricas de ambos modelos.
  Se descompone ROC-AUC por pares positivo–negativo dentro de la misma semana y
  entre semanas; no se confunde AUC agrupado con discriminación contemporánea.
- La calibración usa diez bins uniformes fijos, sus tamaños, ECE descriptivo,
  sesgo medio y contribuciones al Brier por clase. No ajusta pendiente,
  intercepto o calibrador. Brier no se trata como calibración aislada.
- Se comparan probabilidades sobre etiquetas conocidas, todos los 263 radios
  y una cohorte fija con etiqueta conocida en las cuatro semanas de prueba.
  La cohorte fija es una sensibilidad descriptiva, no un nuevo experimento.
- Se calculan distribuciones por bloque para grilla completa y etiquetas
  conocidas, distancias descriptivas ECDF/Wasserstein sin p-valores IID y
  fracción fuera del rango de entrenamiento.
- Las correlaciones estructurales se calculan con una fila por radio. Se
  verifica la identidad densidad=población/superficie y se examina la MDI
  guardada sin modificar variables ni afirmar contribuciones causales.
- Las banderas de fecha aproximada de los objetivos se agregan por partición.
  La comparación previa global de síntomas/muestra conserva su período y no
  se convierte en una demora específica del test de 2024.

El análisis reconoce ocho/ocho/cuatro semanas de una temporada, radios vecinos
dependientes y radios repetidos en todos los bloques. No trata las celdas conocidas
de prueba como eventos independientes ni calcula intervalos/p-valores IID.
La etiqueta es presencia provisional en t+1, separada del objetivo de conteos
sintéticos de `v0.1`; no modifica el MVP.

## Productos y límites

Informe científico privado Markdown/HTML, seis figuras PNG/SVG, tablas
agregadas CSV/Parquet, recomendaciones priorizadas, payload gráfico sin IDs de
pacientes, registro de evidencias con revisión humana pendiente, código copiado,
metadatos, estado de Git y manifiesto. No se generan mapas ni se publican
pacientes, domicilios o coordenadas. El HTML es un archivo local estático,
sin llamadas de red ni cambios en frontend/backend.

La CLI bloquea `fit` de RF/regresor RF/dummy/calibrador/logística/Pipeline y
`joblib.load` durante la revisión. Las pruebas específicas usan datos ficticios
sin ajustar modelos. No ejecutar las suites de entrenamiento de Fase 5C para
validar esta fase, porque algunas ajustan modelos ficticios.

Las propuestas distinguen datos adicionales, auditorías posibles con el dataset
actual, ingeniería de características, calibración y evaluación/selección
temporal. No se eligen hiperparámetros desde prueba ni se ajusta un calibrador
con ella. El test ya examinado conserva carácter exploratorio para cualquier
selección futura; una nueva validación final exige un bloque no examinado.

Referencias metodológicas: [AP](https://scikit-learn.org/stable/modules/generated/sklearn.metrics.average_precision_score.html),
[calibración](https://scikit-learn.org/stable/modules/calibration.html) e
[importancia MDI](https://scikit-learn.org/stable/auto_examples/inspection/plot_permutation_importance.html).
Se aplicaron las skills solicitadas y scientific-writing para trazabilidad;
su referencia procedimental se incluyó en el informe: Kassis, T., Agarwal, V.,
He, Y., Patel, D., & Brueckner, A. M. (2026).
[Scientific Agent Skills: A Library of Procedural Knowledge for Research Agents](https://doi.org/10.48550/arXiv.2609.00065).
No se presume revisión humana, aprobación epidemiológica ni autorización de publicación.
