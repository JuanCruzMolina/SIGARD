# Contrato interno propuesto: resultados espaciales retrospectivos A/B

Estado: **diseño para revisión**, sin adaptador, endpoint, migración, exportación
ni interfaz implementados. No habilita publicación ni entrenamiento oficial.
Unidad: radio censal y semana objetivo; objetivo binario de presencia experimental
de registros en t+1. Es distinto de los conteos y de la simulación sintética del MVP.

## Consulta y procedencia

Interfaz interna recomendada, todavía sin código:

```text
list_experiments() -> metadatos de A/B y semanas disponibles
get_retrospective_scores(model_id, experiment_id, target_week_start)
    -> metadatos comunes + hasta 263 filas agregadas por radio
```

`model_id` admite exclusivamente `A` o `B`; no seleccionar automáticamente el
modelo con mejores métricas. La versión de entrenamiento es inmutable y forma
parte de la identidad. `target_week_start` es un domingo ISO 8601. Las etiquetas
de año/semana se derivan de `ar-snvs-2020-2026-v1`, nunca del calendario ISO ni del
adaptador histórico `sigard-iso-shift-v0`.

Fuentes congeladas propuestas para el registro local de experimentos:

- A: `spatial_rf_05c_v1`, entrenamiento `official-spatial-rf-research-0.5c.0`,
  columna `random_forest_A_probability` de `predictions_radio_week.private.parquet`.
- B: `spatial_rf_B_05f_v1`, entrenamiento `official-spatial-rf-B-research-0.5f.0`,
  columna `random_forest_B_probability` del archivo homónimo de B.
- Ambos: escenario `spatial_assumed_2024_v1`; la geometría censal se consulta
  separadamente y se une por el identificador canónico conservado como texto.

Las rutas físicas, hashes de archivos y autorizaciones permanecen en un registro
privado del proceso offline. El cliente recibe referencias opacas y versiones,
no rutas locales ni configuración de acceso. Para B se obtiene disponibilidad
de rezagos de la matriz congelada de 5E o la matriz de inferencia guardada.
Para A esa disponibilidad no es aplicable: A no utiliza historia epidemiológica.

## Campos de la respuesta

Metadatos comunes obligatorios:

- `schema_version`: `sigard-retrospective-spatial-score/1`.
- `model_id`, `experiment_id`, `training_version` y `territory_version`.
- `data_kind`: `official_experimental_retrospective`.
- `prediction_target`: `binary_experimental_record_presence_next_week`.
- `score_semantics`: `raw_class_1_score_uncalibrated`.
- `calendar_version`: `ar-snvs-2020-2026-v1`.
- `origin_week_start`, `origin_week_end`, `target_week_start`, `target_week_end`,
  `target_epidemiological_year` y `target_epidemiological_week`.
- `coverage_scenario`: `spatial_assumed_2024_v1`; `coverage_verified`: `false`.
- `evaluation_partition`: `train`, `validation` o `test`; `previously_examined`:
  `true`. Ni prueba ni validación se presentan como evaluación independiente nueva.
- `retrospective`: `true`; `operational_use_authorized`: `false`;
  `publication_authorized`: `false` mientras no exista una decisión separada.
- `interpretation_limitations`: códigos obligatorios enumerados más abajo.

Cada fila contiene sólo:

- `radio_censal`: identificador canónico de texto, sin perder ceros iniciales.
- `experimental_score`: número finito en [0,1] leído de la predicción congelada.
- `score_status`: `available` o `not_computed`. Un resultado no calculado se
  representa con `experimental_score=null` y causa explícita; nunca con cero.
- `data_availability`: objeto descrito a continuación.

El modelo, versión, semana y cobertura de cada fila se heredan inequívocamente de
los metadatos comunes. Si las filas se serializan solas, estos campos se repiten
obligatoriamente. Identidad única: modelo + experimento + radio + semana objetivo.
No mezclar versiones, modelos o semanas dentro de una colección.

`data_availability` distingue:

- `historical_context`: `retrospective_unverified` (Censo/contexto disponible hoy;
  publicación y disponibilidad histórica no acreditadas).
- `epidemiological_history`: `not_used_by_model` para A;
  `retrospective_complete`, `retrospective_partial` o `retrospective_unknown` para B.
- `known_lag_count`: `null` para A; entero 0…4 para B, según las cuatro máscaras
  de faltantes, sin devolver valores de rezagos ni etiquetas observadas.
- `operational_availability`: `not_accredited`.
- `prediction_as_of`: `null` mientras no pueda acreditarse el instante real de
  disponibilidad/emisión. Una fecha de origen no sustituye esa evidencia.

Los flags `_missing` de 5E significan 1=sin información; convertirlos a cantidad
de rezagos conocidos es una proyección descriptiva, no una imputación. Una
predicción puede existir aunque su etiqueta objetivo sea desconocida. La
disponibilidad del score no acredita cobertura ni validez epidemiológica.

Limitaciones obligatorias, heredadas por todas las filas:

```text
experimental_assumed_negatives
provisional_positive_labels
coverage_not_verified
historical_record_availability_not_accredited
census_historical_availability_not_accredited
date_classification_and_spatial_uncertainty
spatial_and_temporal_dependence
previously_examined_evaluation_period
uncalibrated_score_not_validated_epidemiological_risk
retrospective_only_no_operational_forecast
```

## Invariantes y errores

1. Leer sólo proyecciones y metadatos incluidos en manifiestos privados conocidos;
   verificar hashes antes de usarlos. No aceptar rutas arbitrarias del cliente.
2. No cargar `joblib` en el backend ni en el navegador. A se carga actualmente
   sólo en auditoría offline, con hash, tipo y versión de scikit-learn comprobados;
   B se recarga offline para verificar su propio archivo recién creado.
   Los scores guardados permiten la demostración sin deserializar modelos ni
   reconstruir features. Un hash local identifica el archivo esperado; por sí
   solo no autentica un pickle proporcionado por un tercero.
3. Conservar las 263 predicciones de cada semana calculada, incluidas filas con
   etiqueta desconocida. No filtrar el mapa por conocimiento de la etiqueta.
   A/B tienen grillas de inferencia iguales; las métricas usan sólo etiquetas
   conocidas. No exportar etiquetas, conteos, pacientes o pendientes al cliente.
4. Exponer únicamente las 20 semanas objetivo calculadas (8/8/4 por partición).
   No inventar scores para las dos semanas purgadas ni para fechas nuevas.
   Experimento/semana inexistente: `not_available`; artefacto corrupto o claves
   incompatibles: bloquear la consulta. Sin fallback silencioso a simulación,
   otro modelo, otra versión, otra semana o cero.
5. `origin_week_end = origin_week_start + 6 días`;
   `target_week_start = origin_week_start + 7 días`;
   `target_week_end = target_week_start + 6 días`. Un futuro adaptador al selector
   actual puede mostrar fin de origen como corte de calendario, sin atribuirle
   disponibilidad operativa acreditada.
6. Usar una lista explícita de campos de salida; rechazar extras. El contrato no
   contiene nombres, documentos, domicilios, IDs de personas, textos libres,
   fechas individuales, coordenadas puntuales ni datos de reportes ciudadanos.
   Las únicas geometrías permitidas en una capa separada son polígonos censales
   aprobados y versionados; nunca unir residencias o puntos sanitarios individuales.

## Presentación relativa futura

El score no es cantidad de casos, incidencia, probabilidad calibrada de dengue
ni nivel de riesgo sanitario. Mantener visible el valor bruto y la advertencia
de retrospectividad. Si se añade un percentil de color, calcularlo exclusivamente
entre los 263 radios del mismo modelo, experimento y semana, con regla fija
documentada y empates por rango promedio; conservar el score original.
Los percentiles de semanas/modelos diferentes no miden el mismo nivel absoluto.
No aplicar umbrales sanitarios ni reutilizar categorías del MVP sin una
explicación nueva. No elegir umbral o calibración con la prueba ya examinada.

Los componentes existentes pueden reutilizarse con un adaptador futuro explícito.
El almacenamiento público actual tiene unicidad lote + corte + radio y no
incluye modelo; el importador y el cliente también requieren productos del MVP
que este contrato no promete. No insertar A/B allí mediante un cambio de nombre
de columnas. Empezar con una proyección privada de sólo lectura; una futura
publicación debe pasar el Control C de `official/interfaces.py` y una revisión
de privacidad, alcance y autorización independiente.

Referencia metodológica utilizada: Kassis, T., Agarwal, V., He, Y., Patel, D., &
Brueckner, A. M. (2026). *Scientific Agent Skills: A Library of Procedural
Knowledge for Research Agents*. https://doi.org/10.48550/arXiv.2609.00065.
La skill `scientific-critical-thinking` ayuda a mantener separados disponibilidad,
predicción e interpretación; no sustituye la revisión humana del contrato.
