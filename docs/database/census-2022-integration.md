# Vinculación local del Censo 2022

La preparación `sigard_ml.ingestion.census_2022` reutiliza los tres CSV locales,
la configuración territorial, el maestro existente y la membresía histórica
congelada. No descarga fuentes, reconstruye geometrías, duplica tablas, entrena
modelos ni modifica los artefactos de `rf_A_epi_climate` o `residual_h1`.

## Fuentes y significado

Los tres archivos tienen las dimensiones `codigo`, `cod_prov`, `cod_dep`,
`fraccion`, `radio`, `cod_variable`, `cod_categoria`, `categoria` y `cantidad`.
Su unidad es un conteo por radio, variable y categoría, no una fila por persona.
Los códigos se leen como texto y se normalizan a anchos 2/3/2/2; `codigo` debe
coincidir exactamente con su concatenación de nueve caracteres. Capital se
selecciona con provincia `46` y departamento `014`.

Se conserva la definición de los totales de `ml/configs/territorial_master.json`:

- Población: suma de categorías de `PERSONA_P02`. Las etiquetas locales son
  `Mujer / Femenino` y `Varón / Masculino`.
- Hogares: suma de categorías de `HOGAR_TIPHOGAR`, con tipos de hogar descritos
  literalmente en el CSV.
- Viviendas: suma de categorías de `VIVIENDA_TIPOVIVG`; en estos archivos de
  Capital la categoría observada es `Particular`. No se acredita un universo
  adicional de viviendas colectivas.

No se suman diferentes variables entre sí. La inspección local no encontró un
diccionario independiente. `category_inventory.csv` conserva códigos, etiquetas
literales y cobertura por categoría para revisar otras características
demográficas; **no reemplaza un diccionario oficial**, no establece denominadores
de subpoblaciones ni interpreta códigos ambiguos. Categorías ausentes no se
convierten automáticamente en cero.

## Vinculación y reproducibilidad

`link_context` agrega categorías antes de unir por código con cardinalidad uno a
uno. Rechaza claves repetidas, componentes incompatibles, membresías externas y
totales distintos de los ya presentes en el maestro. Conserva faltantes como
NULL e informa códigos sin correspondencia en ambas direcciones. Nunca usa
posición de fila, centroides ni proximidad geográfica.

La versión cartográfica declarada por la configuración existente es
`RADIOS_2022_v1_0`. Se comprueba el hash del maestro y del subconjunto contra su
manifiesto congelado. Esto verifica la continuidad del soporte territorial local;
no representa una nueva certificación externa de cartografía o diccionario.

El dataset derivado conserva 263 filas y `common_evaluation` para las 256
históricas. Los siete excluidos se identifican en el manifiesto y en las filas,
con `outside_frozen_common_membership`. El motivo histórico detallado sigue en
el manifiesto del subconjunto original. No se calcula una nueva máscara.

Ejecución local, siempre hacia un directorio nuevo:

```powershell
.\ml\venv\Scripts\python.exe -B -m sigard_ml.ingestion.census_2022 --output data/processed/census_2022_VERSION_NUEVA
```

Salidas privadas excluidas de Git: `context.parquet`, `category_inventory.csv`
y `manifest.json`, con hashes, fuentes, año de referencia, versión de
transformación y condición de contexto censal observado. Se verifican de nuevo
los hashes de entrada antes de escribir. Nunca se sobrescribe un resultado.

## PostgreSQL/PostGIS existente

Se reutilizan `territory.radio_censal`, `version_geometria`, `miembro_universo`,
`variable_censal`, `categoria_censal`, `observacion_censal` y los lotes vigentes
de `ingestion`. El importador `CensusCSV` ahora valida componentes, categorías
duplicadas y etiquetas contradictorias. Mantiene su identificador de adaptador
para conservar la idempotencia y las configuraciones anteriores; las nuevas
importaciones registran `validation_version=census-components-2`. Los lotes
anteriores no se reescriben ni se consideran revalidados automáticamente.

Para comprobar la base existente, agregar `--connection RUTA_PRIVADA_JSON` al
comando. Usa el conector ya existente: clúster propio `sigard-epi-*`, base
`sigard_epi_*`, puerto explícito distinto de 5432 y sesión de solo lectura.
No inicia servicios ni ejecuta migraciones. Comprueba:

- IDs internos y códigos únicos del universo `ab-263-master-v1`.
- Provincia, departamento, fracción, hash de la versión geométrica y membresía
  `v3-256-subset-v1` frente a los archivos congelados.
- Lotes censales vigentes por hash exacto de cada archivo y todas sus
  observaciones: ID interno, código, variable, categoría, descripción y cantidad.

Genera `postgres_linkage.csv` sólo si la consulta termina correctamente. Los
lotes ausentes se informan como no verificados; no se importan automáticamente.
Múltiples lotes se verifican separadamente y nunca se suman entre versiones.
El importador existente registra además radios faltantes y fuera del universo,
sin ocultar los descartes como simples totales de filas.

## Uso predictivo y disponibilidad temporal

`attach_asof` prepara columnas `poblacion_2022_asof`, `hogares_2022_asof` y
`viviendas_2022_asof` para paneles con códigos censales y `origin_end`. La fecha
de disponibilidad debe estar documentada y no puede preceder a 2022. Si falta,
o es posterior al cierre de origen, las columnas predictoras permanecen NULL.
Las columnas sin sufijo `_asof` son contexto descriptivo, no una matriz de
entrenamiento. No usar `SELECT *` ni todas las columnas como features.

Los protocolos y listas de features congeladas de los dos modelos permanecen
intactos. Este trabajo entrega el enlace y la preparación de contexto; **no
incorpora hogares/viviendas a los estimadores entrenados ni demuestra mejora
predictiva**. Esa incorporación exige una versión experimental nueva, definición
verificada de variables y disponibilidad temporal, y evaluación walk-forward
dentro de desarrollo, sin seleccionar por el período ya observado.

## Comprobación del 05/11/2026 y límites

La ejecución local en `data/processed/census_2022_linkage_20261105_v1` comprobó
coincidencia de los tres totales con el maestro, cobertura de sus 263 códigos y
conservación de los 256 comunes y siete excluidos, sin faltantes de vinculación.
Los archivos contienen 160813 filas de persona, 58098 de hogar y 16503 de
vivienda; se inspeccionaron completos, filtrando Capital para la preparación.

La conexión de solo lectura al clúster privado falló con `OperationalError`,
también fuera del sandbox. No se inició PostgreSQL ni Docker. Por ello el
manifiesto declara `database_status=not_checked`: los IDs y lotes reales siguen
pendientes de comprobación. Las pruebas automatizadas de SQL usan respuestas
ficticias; no equivalen a una prueba actual de PostGIS.

Pruebas focalizadas: `ml/tests/test_census_2022.py` y
`ml/tests/test_predictive_core.py`. No leen fuentes privadas ni entrenan modelos.
Los cambios previos del árbol de trabajo se conservan.

## Continuación autorizada: comparación censal controlada

La solicitud posterior del responsable autoriza iniciar exclusivamente el clúster
WSL existente `sigard-epi-local-v1`, puerto 55439 y base `sigard_epi_local_v1`,
comprobar la correspondencia y ejecutar una campaña nueva, sin modificar
artefactos anteriores. Esta autorización supera para esta tarea la restricción
general de no iniciar servicios; el clúster iniciado se apaga al finalizar.

La comprobación real del 05/11/2026 reutilizó `verify_database` y los derivados
ya preparados, sin ejecutar otra vez `prepare`. Verificó 263 IDs, 256 miembros
comunes, los hashes y todas las observaciones de los tres lotes censales. La
evidencia privada está en `data/interim/official/census-campaign-20261105-v1`.
El registro real contiene **64 artefactos**, todos preservados, aunque la
solicitud mencionaba 32. Se comparan identificador, SHA-256 declarado y MD5 del
contenido binario antes y después; no se carga ni se modifica ningún estimador
histórico. MD5 se usa aquí sólo como control adicional de igualdad de bytes.

`sigard_ml.forecasting.census_campaign` crea derivados privados nuevos desde
la vista consolidada, la política y el calendario existentes. No modifica SQL,
geometrías, coordenadas, geocodificaciones ni el dataset original. Conserva
2020–2024 y los 256 radios comunes; los 263 se mantienen en el contexto.
No amplía etiquetas ni entrenamiento a 2025/2026.

Los escenarios se guardan en archivos distintos:

- A: conserva `poblacion_predictor_asof` y su densidad. Si la disponibilidad
  desconocida deja las matrices censales nulas, no se entrena una comparación
  que pretenda medir el aporte de esas variables.
- B: reemplaza sólo población y densidad por su referencia censal fija 2022.
  Es una reconstrucción retrospectiva con información posterior para parte
  del período, nunca una predicción ex ante.

La campaña registra protocolo, hashes, versiones y auditoría de las matrices
de cada fold **antes del primer ajuste**. Reutiliza los cortes de 13 semanas,
la purga de cuatro semanas, la calibración interna y los hiperparámetros del
motor existente. Compara `rf_A_epi_climate` y `residual_h1`, cada uno con y sin
población/densidad, sobre exactamente los mismos radio–semana. Superficie,
historia epidemiológica, clima y calendario permanecen iguales. Hogares y
viviendas son contexto; no entran a las matrices de estos estimadores.

Las versiones sin censo se reajustan de forma pareada: no se mezclan métricas
de artefactos antiguos con otra muestra. El cambio opcional `features` en
`motor_models` permite únicamente subconjuntos de las listas autorizadas; el
comportamiento predeterminado y las listas originales se conservan. La
serialización de cada artefacto nuevo debe reproducir exactamente sus scores.

Los resultados separan desarrollo 2021–2023, cada año y 2024 exploratorio ya
observado. Se informan Brier, discriminación y errores de presencia; MAE, RMSE,
sesgo, positivos, ceros, colas y totales semanales para cantidad, junto con los
baselines existentes e intervalos descriptivos de diferencias pareadas por
bloques semanales. No hay búsqueda abierta, selección por 2024, ajuste final,
promoción automática, escritura en la base ni modificación del frontend.
