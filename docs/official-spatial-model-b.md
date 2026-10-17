# Fase 5F: Random Forest B retrospectivo

El módulo `sigard_ml.official.spatial_ml.research_model_b` reutiliza el protocolo
de 5B, los controles de diseño de 5C, las métricas auditadas de 5D y la matriz
congelada de 5E. No modifica sus módulos, datasets ni modelos.

B conserva las siete variables de A e incorpora presencia binaria experimental
en t−1, t−2, t−3 y t−4 y sus cuatro indicadores `_missing` (1=desconocido).
El origen es t; la etiqueta es presencia en t+1. No son cantidades de pacientes.
Se conserva IEEE NaN, sin imputación ni selección de casos completos.

La ejecución requiere configuración privada con autorización explícita propia de
B, hashes de los manifiestos del escenario/A/5E, características, parámetros y
umbral 0,5 congelados. `training_authorized` permanece en `false`; el permiso
`research_training_authorized` sólo cubre el experimento retrospectivo. La API,
frontend y modelos operativos no intervienen. El CLI no genera autorizaciones.

```powershell
.\ml\venv\Scripts\python.exe -m sigard_ml.official.spatial_ml.research_model_b --config data/interim/official/spatial_rf_B_05f_v1/configuration.private.json
```

Antes de ajustar se comprueban soporte NaN del entorno, procedencia de ceros,
identidad exacta de etiquetas/particiones y todos los rezagos por semana fuente.
La ruta de salida debe ser nueva, privada y excluida de Git. No se cambian
dependencias si falta soporte nativo. El ajuste usa exclusivamente etiquetas
conocidas de entrenamiento; conserva las semanas purgadas y las fechas de A.
No hay búsqueda, calibración ni selección de umbral. A y baseline se comparan
mediante sus predicciones congeladas, sin volver a ajustarlos.

Se generan métricas globales y semanales, calibración descriptiva, MDI, grupos de
faltantes y una sensibilidad con B fijo: permutación conjunta de valores de los
cuatro rezagos dentro de semana y máscara NA idénticas. No rompe disponibilidad,
no entrena otro modelo, no selecciona características ni identifica causalidad.
Se distinguen AP y PR-AUC trapezoidal, y Precision indefinida si no hay alertas.

Dos ajustes de B con la misma semilla deben reproducir todas las probabilidades
exactamente; también se verifica la recarga del único joblib recién creado.
El manifiesto conserva hashes de fuentes, artefactos anteriores y código de
trabajo. Los resultados por radio-semana permanecen privados, sin pacientes,
domicilios ni coordenadas. El informe HTML contiene sólo agregados y no carga
recursos externos. La documentación pública no incluye resultados sanitarios.

La prueba ya examinada sólo permite comparación exploratoria. Cuatro semanas,
dependencia espacial/temporal, negativos asumidos, positivos provisionales,
cobertura y disponibilidad histórica no acreditadas impiden validación
epidemiológica u operativa. Una evaluación independiente requiere otro período
no examinado y snapshots de disponibilidad real, con protocolo congelado.

Pruebas focalizadas: `ml/tests/test_official_research_model_b.py` junto con las
pruebas de research_training, research_diagnostics y temporal_feasibility.
