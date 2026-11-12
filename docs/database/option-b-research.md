# Investigación A/B/V3 desde PostgreSQL con política B

Este contrato nuevo implementa la decisión expresa del proyecto del 29/10/2026.
No modifica los datasets conservadores, las etiquetas históricas, los modelos
congelados ni el candidato principal anterior. No exige equivalencia con Parquet
para un ajuste nuevo. La reproducción histórica conserva sus comprobaciones.

## Política y unidad

`option_b_complete_years_assumed_zero_v1` incluye todas las semanas del calendario
argentino de los años epidemiológicos 2020–2024. Incluye semanas anteriores,
intermedias y posteriores a los registros del año. Un cero significa ausencia
de **registro fuente elegible en el escenario**, asumida experimentalmente.
No acredita vigilancia completa, ausencia de dengue ni episodios clínicos.

La elegibilidad conserva la clasificación confirmada explícita existente,
residencia declarada en Capital, referencia de síntomas o, si falta, muestra,
fechas válidas y exclusión de duplicados técnicos y relaciones de identidad
pendientes. Los registros excluidos se preservan y se trazan; no se distribuyen
los sin fecha ni se reinterpretan clasificaciones desconocidas. En particular,
2022 puede tener todos sus conteos confirmados en cero bajo esa definición sin
que ello sea evidencia epidemiológica de ausencia de dengue.

La inclusión opcional de 2025 requiere fechas clínicas válidas almacenadas;
incluye su año completo bajo el supuesto. Para 2026 se exige además un corte
explícito sustentado por fuente y se incluyen sólo semanas completas hasta el
menor de ese corte y la fecha actual. Se comprueban tanto síntomas como muestra,
sin interpretar el nombre de un archivo como evidencia temporal. Si no hay
fechas, o no hay corte respaldado para 2026, se registra la exclusión.

Cada escenario tiene dos universos existentes, A/B y V3, y dos variantes:

- `approximate_included`: acepta candidatos geométricos aproximados, provisionales
  de mayor confianza y verificados si existen. Son atribuciones experimentales.
- `provisional_verified`: retiene sólo las dos últimas categorías. Una asignación
  provisional no se transforma en una localización verificada.

Las asignaciones ambiguas, fuera del universo o sin radio utilizable no se
reparten artificialmente. La tabla de selección mantiene el registro, lote,
revisión, asignación, semana, exclusión y calidad. Los conteos representan ese
subconjunto espacial; no se presentan como totales completos de casos.

## Persistencia y acceso

La migración aditiva `20261029_epi13` usa la base existente. Las tablas nuevas
son necesarias para separar el contrato de los anteriores, cuyas restricciones
y máscaras son diferentes:

- `escenario_investigacion`: política, fuentes, calendario, alcance, protocolo
  previo al ajuste, autorización declarada y huella de entrada.
- `fuente_escenario_ml` y `registro_escenario_ml`: selección sin duplicación de
  versiones y procedencia individual restringida al importador.
- `clima_escenario_ml`: agregación semanal única desde el clima diario existente
  en PostgreSQL, compartida por las variantes. Una semana incompleta conserva
  NULL; no se convierte clima faltante en cero.
- `dataset_investigacion` y `conteo_investigacion`: universo y política geográfica
  versionados, grilla completa y ceros asumidos identificados.
- `modelo_investigacion`, `evaluacion_investigacion` y `prediccion_investigacion`:
  estimador serializado, SHA-256, versiones, métricas por partición y resultados.
  Las tablas rechazan UPDATE/DELETE; no se sobrescriben modelos o métricas.

`MLRepository.research_metadata` y `research_frame` consultan las vistas
`metadatos_investigacion`, `investigacion_a`, `investigacion_b` e
`investigacion_v3`. Comprobar vigencia de lotes, contexto censal, geometría y
vecindades no depende de archivos. La revisión clínica se valida por las
observaciones y asignaciones seleccionadas, vinculadas a la revisión inmutable;
una importación complementaria ajena no invalida por sí sola esas observaciones.
Un lote clínico nuevo sin revisar sí se bloquea. No se elimina el control de
equivalencia de las rutas históricas.

Las FK y triggers comprueban registro/lote/asignación, pertenencia territorial,
semana cubierta y ajuste anterior al origen. El lector analítico usa vistas
agregadas y modelos privados, sin acceso a la selección individual. No se crean
cuentas de API pública ni endpoints de publicación.

## Ajuste, evaluación y sensibilidad

`option_b_training.PROTOCOL` se registra antes del primer ajuste. Mantiene los
RF A/B iniciales, sus siete/quince variables, NaN nativos y umbral 0,5. V3 mantiene
sus diecisiete variables, tres candidatos, horizontes 1/2/4, semillas, parámetros,
calibración, selección walk-forward y criterios de promoción de desarrollo.

El protocolo inicial usa 2020–2022 para ajuste inicial, 2023 para validación y
2024 para evaluación posterior al ajuste. El refit de A/B usa desarrollo hasta
2023; V3 selecciona sólo dentro de desarrollo. En cada caso los desenlaces de
ajuste deben terminar estrictamente antes del primer origen evaluado, con purga
por horizonte. Las nuevas fechas opcionales no cambian automáticamente esos
cortes ni amplían la prueba después de verla.

A/B comparan Brier, AP, ROC cuando está definida y F1 con prevalencia de
entrenamiento; B añade presencia t−1 con respaldo del prior. V3 compara MAE/RMSE
y sus controles originales con persistencia y media histórica. No se comparan
numéricamente métricas de clasificación con métricas de conteos. Particiones
de una sola clase mantienen las métricas de ranking no definidas. Los mínimos
son controles computacionales de soporte, no garantías de potencia científica.

El modelo se registra antes de evaluar la prueba. La sensibilidad repite el
protocolo bajo cada definición geográfica cuando existe soporte y también
mantiene fijo el modelo para medir cambios al sustituir únicamente sus inputs
por la otra variante. Esta última comprobación no reentrena, no selecciona y no
inserta esas predicciones contrafactuales como resultados del dataset original.
Las etiquetas de ambas variantes difieren: el análisis no acredita exactitud
espacial ni permite elegir una como verdad clínica por obtener mejor métrica.

## Inferencia privada

`option_b_training.infer` recupera metadatos, artefacto y predictores únicamente
de PostgreSQL. Comprueba hashes, código de features, entorno, fuentes, horizonte,
cobertura y corte de ajuste. Nunca ajusta para suplir una entrada faltante ni
carga un joblib arbitrario. La matriz de inferencia omite la etiqueta futura.
Las consultas retrospectivas identifican modelo, versión, radio, objetivo,
resultado, dataset, política de ceros, calidad geográfica y motivo de
indisponibilidad. Los resultados quedan como `experimental_unvalidated`.

El mejor ML V3 se fija en desarrollo para consulta de investigación, incluso
si no obtuvo aprobación de promoción; se informa ese resultado por separado.
Esto no activa el candidato anterior `candidate_failed` ni cambia el producto.
La modalidad operativa conserva la deshabilitación por falta de autorización
operativa y disponibilidad temporal acreditada, además de la ausencia de
entradas actuales cuando corresponda. No se inventa historia de 2025/2026.

CLI único privado:

```powershell
.\ml\venv\Scripts\python.exe -B -m sigard_ml.forecasting.postgres_experiment prepare --connection CONNECTION_PRIVADA --config CONTRATO_PRIVADO --report NUEVO_INFORME_PRIVADO
.\ml\venv\Scripts\python.exe -B -m sigard_ml.forecasting.postgres_experiment train --connection CONNECTION_PRIVADA --config CONTRATO_PRIVADO --dataset-version DATASET --family A --model-version MODELO_NUEVO --report NUEVO_INFORME_PRIVADO
.\ml\venv\Scripts\python.exe -B -m sigard_ml.forecasting.postgres_experiment infer --connection CONNECTION_PRIVADA --config CONTRATO_PRIVADO --model-version MODELO --origin AAAA-MM-DD --report NUEVO_INFORME_PRIVADO
```

`prepare` no entrena. El contrato contiene autorización y selección explícitas
de lotes y revisión. `train` exige además permiso de ajuste. Los comandos A/B/V3
anteriores aceptan `--mode postgres_option_b` con configuración nueva; el modo
`historical_contract` y `--historical-reproduction` conservan sus controles.
Los lectores tabulares se bloquean también durante las ejecuciones nuevas.
No hay entrenamiento automático al importar, materializar o consultar.

## Límites y evidencia

La cronología computacional se prueba con fechas exactas y alterando sólo
desenlaces de evaluación en fixtures: el ajuste debe permanecer igual. Eso no
acredita disponibilidad histórica de censos, clima, revisiones o clasificación.
La reconstrucción utiliza el snapshot final y contexto censal fijo; no se
denomina prueba prospectiva. El historial de evaluación ya fue examinado en
trabajos anteriores y no equivale a validación externa independiente.

Los resultados reales, conteos, métricas, hashes, predicciones y comparación de
sensibilidad se conservan exclusivamente en
`data/interim/official/postgres-policy-b-20261029-v1/`, excluido de Git.
El informe privado distingue integración técnica, soporte y aprobación científica.
Los datos y modelos anteriores y el frontend se verifican sin cambios. No se
crea otra base, reimporta SISA, publica información, inicia Docker ni accede a 5432.
