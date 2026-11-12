# Consolidación histórica: etapa 1

La política `sigard-project-positive-2022-covered-2020-2024-v1` implementa la
decisión expresa del responsable del proyecto del 02/11/2026. Es una nueva
definición de registros positivos experimentales SIGARD, sin modificar la
clasificación clínica original, las revisiones, los experimentos A/B/V3 o sus
resultados. No acredita episodios, vigilancia completa ni incidencia.

La migración aditiva `20261102_epi14` añade cinco tablas pequeñas y cuatro
vistas de consumo. No duplica las grillas históricas,
reimporta originales, carga estimadores ni ejecuta entrenamiento o inferencia.

## Selección y referencia temporal

La configuración fija lotes, hashes, revisión, fecha de corte, alcance de la
excepción 2022 y referencia de autorización. Cada registro conserva:

- FK al registro y lote originales, fecha clínica y semana de referencia.
- Clasificaciones literales originales y equivalencias de la revisión anterior.
- Elegibilidad, positividad experimental y todos los fallos del filtro.
- Indicador de excepción 2022 y confirmación clínica original por separado.
- Asignación geográfica existente, calidad y disponibilidad conocida.

La excepción `delivery_2022` se aplica a la entrega 2022 fijada por hash. **No
cambia fechas:** un registro de esa entrega fechado en 2021 pertenece a su semana
clínica de 2021. El modo explícito alternativo `clinical_year_2022` permite una
decisión diferente en otra versión; no se cambia silenciosamente el contrato.
Fuera de la excepción se mantiene la clasificación confirmada inequívoca.

Se conservan los filtros de residencia declarada, fecha válida, duplicación
técnica e identidad/revisión pendiente; también se exige identificador fuente.
La fecha es inicio de síntomas o, si falta una fecha válida, muestra identificada
como proxy. Ningún nombre de archivo genera fechas clínicas o etiquetas.

## Cobertura y ceros

2020–2024 comprende 261 semanas del calendario argentino existente
`ar-snvs-2020-2026-v1`, de domingo a sábado, incluida la semana 53 de 2020.
La cobertura es una declaración metodológica del responsable, registrada como
`project_owner_declared_coverage_2020_2024`, nunca certificación institucional.

`analytics.consolidacion_departamento` calcula el total del subconjunto elegible
por residencia declarada, incluidos registros cuya geografía no se puede asignar.
Una semana cubierta sin registros de ese subconjunto vale cero; sin fecha válida
el registro se excluye y concilia, no se distribuye. Fuera de cobertura, cantidad
y presencia son NULL. Se conservan filas de calendario 2025/2026 con estado
`out_of_coverage`, sin etiquetas ni ceros.

En radio–semana se exponen `registros_asignados` y su composición por calidad.
`cantidad_sigard` es NULL si el radio está fuera de la máscara común o existen
registros elegibles de esa semana sin radio. En este último caso puede conocerse
una presencia positiva, pero no un cero ni el total exacto de cada radio.
`cantidad_mayor_confianza` queda NULL cuando hay asignaciones aproximadas en la
semana: no se convierten los registros descartados por precisión en negativos.

Los conteos con calidad aproximada son atribuciones experimentales respaldadas
por el candidato geométrico revisado, sin garantía de domicilio o infección real.
No se crean nuevos puntos ni se reparte un registro ambiguo.

## Territorio compartido

Se reutiliza el maestro de 263 radios y las geometrías originales PostGIS.
`consolidacion_territorio` conserva membresía A/B, membresía V3 y máscara común
de 256 radios con contexto disponible. Los siete restantes mantienen su fila y
el motivo documentado del filtro histórico de localidad: inclusión completa o
fracción interior al menos 0,9999. Se reutiliza la comparación territorial
congelada con SHA-256; no se recalcula ni modifica cartografía.

La comparación futura entre presencia y cantidad debe usar los mismos
radio–semana, máscara y calidad, sin rellenar valores desconocidos. La suma de
registros asignados dentro/fuera de la máscara y no asignados debe coincidir
con el total departamental. Una cantidad de filas de grilla no es un total de
registros ni personas independientes.

## Clima y censo

El clima diario importado de un punto Open-Meteo se comparte como contexto de
Capital. Se verifica el hash del archivo revisado y la igualdad de los valores
diarios con PostgreSQL, sin reimportar. Las agregaciones domingo–sábado usan
media de temperatura/humedad y suma de precipitación con siete días completos;
faltantes e intervalos parciales permanecen NULL. Las semanas previas a 2020
sólo tienen clima, sin inventar años/semanas epidemiológicos o etiquetas.

El historial desde 2015 permite rezagos y cuatro semanas hasta el cierre de
origen, además de medias históricas expansivas **estrictamente anteriores** al
origen. Una media histórica de precipitación se expresa como promedio de sumas
semanales completas. No se confunden observaciones de un punto con estaciones
independientes en cada radio.

La población censal 2022 queda como `poblacion_contexto_2022` en la vista de
datos. `poblacion_predictor_asof` requiere año no anterior a 2022 y disponibilidad
conocida anterior al cierre; en otro caso es NULL. La vista de predictores no
ofrece población retrospectiva, vecindad o superficie censal como sustitutos
automáticamente acreditados de información disponible en 2020/2021.

La cronología de las mediciones no prueba su disponibilidad operativa. Los
timestamps desconocidos permanecen NULL y la disponibilidad operativa se
identifica como no acreditada. El producto es investigación retrospectiva.

## Consultas y reconstrucción

Tablas: `consolidacion_dataset`, `consolidacion_fuente`,
`consolidacion_registro`, `consolidacion_territorio`, `consolidacion_clima`.
La selección individual sólo se concede al importador; el lector analítico
recibe metadatos y vistas agregadas. Los triggers conservan anexado inmutable,
vínculo fuente, clasificación original, fecha/semana y calidad de asignación.

Vistas en `analytics`:

- `consolidacion_departamento`: conciliación semanal del conjunto elegible.
- `consolidacion_radio_semana`: cantidad/presencia, máscaras, procedencia del
  cero, calidad, contexto censal y clima; no es una tabla materializada.
- `consolidacion_predictores`: sólo variables del origen y su pasado, sin join
  con desenlaces futuros. Es el contrato para construir matrices de inferencia.
- `consolidacion_entrenamiento`: añade cantidad y presencia de la semana
  siguiente en columnas de objetivo explícitas. No utilizar `SELECT *` como
  matriz predictora ni tratar `entrada_sha256` o IDs como features.

Todas las consultas deben filtrar una versión explícita. Ejemplo estructural:

```sql
SELECT anio, numero, inicio, fin, cantidad_sigard, cobertura_estado
FROM analytics.consolidacion_departamento
WHERE dataset_version = :version
ORDER BY inicio;
```

CLI exclusivo de preparación/inspección, sin subcomando de entrenamiento:

```powershell
.\ml\venv\Scripts\python.exe -B -m sigard_ml.forecasting.consolidation prepare --connection CONNECTION_PRIVADA --config CONFIG_PRIVADA --report INFORME_NUEVO_PRIVADO
.\ml\venv\Scripts\python.exe -B -m sigard_ml.forecasting.consolidation inspect --connection CONNECTION_PRIVADA --config CONFIG_PRIVADA --report CONCILIACION_NUEVA_PRIVADA
```

`prepare` migra aditivamente y reconstruye desde fuentes ya almacenadas. La misma
versión y entradas devuelve `already_materialized`; una entrada diferente bajo
la misma versión se rechaza. Para una reconstrucción independiente se utiliza
otra versión y se comparan proyecciones sin los identificadores de versión.
Se fija una huella de entradas y código, no se atribuye validez científica al hash.

Las credenciales y configuraciones sólo se admiten bajo almacenamiento privado
excluido de Git. Se conserva la guarda existente de clúster WSL propio/puerto
privado; no se conecta Supabase, 5432 ni el frontend.

## Validación y límites

`ml/tests/test_consolidation.py` cubre la excepción 2022 y el descartado, filtros,
fechas de otra entrega, calendario, clima incompleto, reproducción, máscaras,
conciliación, inmutabilidad, PostGIS y cambio de clima futuro sin cambio de
predictores anteriores. Usa fuentes generadas y polígonos abstractos.

Las pruebas PostGIS requieren una base **temporal propia** `sigard_epi_test_*`
en el clúster permitido; nunca configurar las fixtures destructivas sobre la
base original. La evidencia privada distingue pruebas puras, pruebas reales en
esa base temporal y verificaciones de lectura de la base original.

Los totales reales, auditoría individual de 2022, semanas 2024, versiones,
configuración, hashes, inventario climático y comprobación de conservación
están exclusivamente en la carpeta privada de la ejecución. Este cierre no
entrena, selecciona modelos, habilita producción o inicia la etapa 2.
