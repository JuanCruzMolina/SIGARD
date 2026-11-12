# Dos candidatos ML experimentales — cierre por reutilización

Versión `sigard-two-candidates-reused-h1-20261103-v1`.

La auditoría ML 1 no encontró un defecto de aprendizaje o inferencia que exija
reentrenamiento. Se reutilizan `rf_A_epi_climate` y `residual_h1` de la campaña
`sigard-predictive-motor-h1-20261102-v1`, con el dataset consolidado y política de
2022 vigentes. Son dos familias y un horizonte de una semana; los 16 ajustes
temporales por candidato se conservan, no son una búsqueda de configuraciones.

`sigard_ml.forecasting.candidate_release` escribe un manifiesto privado aditivo
que referencia los artefactos, predicciones y métricas existentes mediante SHA-256.
No copia grillas a PostgreSQL, no deserializa modelos en consultas y no ajusta ni
infiere resultados nuevos. Rechaza alteraciones de fuentes, columnas incompatibles,
universos incompletos, horizonte incorrecto y ajustes posteriores al corte permitido.

Estados del contrato:

- `experimental_evaluated`: candidatos entrenados y evaluados reutilizables en
  investigación, aun cuando no superen las referencias.
- `reference_selected`: `presence_seasonal` y `count_latest`, sin afirmar que son ML.
  `count_training_mean` permanece como comparación adicional.
- `blocked`: falta de soporte, fuera de cobertura o incompatibilidad técnica;
  incompatibilidad de integridad lanza `DatasetBlocked`, sin devolver valores.
- `operational_approved`: estado reconocido pero no concedido por esta entrega.

`CandidateRelease(root, manifest_relative_path, expected_sha256).week(week_start,
capability)` permite lectura **offline privada**, con `presence` o `quantity`.
Entrega origen, objetivo, candidato, versión, hash, corte, referencia y observados.
Presencia conserva score/umbral separados de cantidad. Los faltantes no se convierten
en cero. No se instala esta clase en el backend ni se inicia integración frontend.

Hay 208 semanas retrospectivas de 2021–2024 y 256 radios comunes. 2020 carece de
soporte de campaña y 2025/2026 de cobertura. Se usa calendario argentino y se
conserva semana 53. 2024 es comparación exploratoria ya observada. La disponibilidad
real de llegada histórica no está acreditada: se reconstruye por fecha del evento.

Ambos candidatos reciben las mismas 37 columnas congeladas. Temperatura, humedad,
precipitación y sus antecedentes son de origen o anteriores. Población y densidad
no tienen disponibilidad as-of acreditada; no se eliminan columnas del modelo ni
se rellenan con valores futuros. No hay calibración sanitaria acreditada.

La ablación de presencia existente permite cuantificar aporte conjunto del clima,
con resultados distintos según métrica. En cantidad su aporte incremental permanece
no demostrado; una nueva ablación no es requisito de cierre. No se cambia la
selección original por resultados de 2024 ni se promueven modelos por mostrarlos.

El informe privado, respaldo recuperable verificado, métricas, intervalos por bloques
temporales y pruebas se guardan en
`data/interim/official/ml-closure-stage2-20261103-v1/`. El manifiesto referencia
resultados originales y conserva hashes. Los archivos contienen agregados privados:
no se publican ni se incorporan a `frontend/public`.

Pruebas ficticias: `python -B -m pytest ml/tests/test_candidate_release.py
-p no:cacheprovider`. La evidencia PostgreSQL real es independiente de esas fixtures.
