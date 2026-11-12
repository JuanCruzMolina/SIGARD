# Lectura analítica para A, B y V3

El [nuevo contrato de investigación con política B](option-b-research.md)
implementa datasets, ajuste, evaluación, registro e inferencia desde PostgreSQL.
No exige equivalencia histórica para entrenar esos datasets nuevos. Este
documento conserva los contratos anteriores y sus comprobaciones estrictas.

La consolidación posterior del 29/10/2026 implementa un
[componente principal desde PostgreSQL](predictive-core.md), con otra definición
filtrada de conteo y unidad Capital. El candidato no superó el baseline. Este
documento conserva los contratos históricos A/B/V3, que no se activaron ni se
reentrenaron como productos de la consolidación.

Las vistas no entrenan, ejecutan ni registran modelos. Toda ejecución incluye
versión, fuentes seleccionadas, universo, calendario, políticas temporal y de
clasificación, cobertura, corte informativo, modo y procedencia del contexto.
`equivalencia_ml_verificada` queda en falso hasta una revisión explícita del
contrato completo; que coincidan siete features A no acredita equivalencia de
etiquetas ni de cobertura con los modelos congelados.

Las [resoluciones deterministas](resolution-guide.md) añaden revisiones
inmutables seleccionadas mediante `resolution_version`. Un candidato espacial
único se distingue de una ubicación suficientemente precisa. Los contratos de
features, horizontes y disponibilidad se conservan; los resultados se materializan
en otra versión analítica, sin sobrescribir las ejecuciones anteriores.

## Conteos y cobertura

`analytics.conteos_radio_semana` conserva la grilla de una ejecución. El conteo
observado incluido es un subtotal de registros, nunca episodios. La cantidad
completa es NULL si hay pendientes, fechas aproximadas o cobertura insuficiente.
Una presencia provisional puede ser 1 cuando existe algún registro incluido;
un negativo requiere cantidad conocida igual a cero bajo su definición.

- `verified`: revisión respaldada para todas las fuentes, intervalo y criterio.
- `experimental_assumed`: supuesto separado, autorizado y acotado a semanas
  explícitas; cero significa ausencia de registro bajo ese escenario.
- `unknown`: no hay evidencia suficiente; ausencia de filas no genera cero.
- `out_of_scope`: fuera del alcance explícito del escenario, no ausencia de
  vigilancia ni de enfermedad. Un rótulo anual del archivo no acredita cobertura.

La geografía y la identidad no se resuelven por declarar cobertura. Las
geocodificaciones con revisión requerida no pasan a asignación aprobada. Un
pendiente sin fecha puede afectar todas las semanas posibles; sin un radio
aceptable puede afectar todos los radios. Esta regla conservadora puede dejar
sin cantidades utilizables un conjunto importado íntegramente. No es permiso
para retirar máscaras o convertir desconocidos en ceros.

`analytics.registros_fuente_semana` permite conciliar todos los registros,
incluidos los sin fecha y los excluidos/pendientes. No presenta subtotales
territoriales como totales de ciudad. `candidatos_espaciales_pendientes` permite
revisar correspondencias sin marcarlas como etiquetas ML utilizables.

`analytics.conteos_con_procedencia` identifica la ejecución, políticas y universo;
`analytics.fuente_ejecucion` permite recorrer sus lotes hasta los hashes fuente.
Las vistas de revisión de candidatos individuales quedan
reservadas al importador; el lector analítico no recibe domicilios ni puntos.
El año epidemiológico 2022 permanece sin objetivo ML, incluso bajo cobertura
asumida, hasta contar con una política revisada para sus clasificaciones.

## A

`analytics.ml_a` selecciona el universo A/B y expone las columnas originales:
`superficie_km2`, `poblacion`, `densidad_poblacional`, `cantidad_vecinos`,
`semana_epidemiologica`, `estacionalidad_seno`, `estacionalidad_coseno`.
La fase usa semana **de origen**, número de semanas de su año y el calendario
argentino versionado; no `extract(week)` ISO. El objetivo es presencia en t+1.
Superficie y vecinos proceden del maestro existente; densidad se calcula.

## B

`analytics.ml_b` añade `local_presencia_exp_rezago_1` a `_4` y sus cuatro
`_missing`, en el orden del estimador original. Son presencias binarias locales
de t−1…t−4 por claves de fecha exactas. No son conteos, no saltan huecos y no
rellenan NULL con cero. No exigen conocer el objetivo futuro para construir X.

## V3

`analytics.ml_v3` selecciona el universo V3, con horizontes explícitos 1, 2 y 4:
`count_origin`, `cases_lag_1`, `cases_lag_2`, `recent_mean_3`, `recent_trend`,
`known_recent_count`, `neighbor_mean_origin`, `neighbor_known_fraction`,
`temperature_origin`, `humidity_origin`, `precipitation_origin`,
`temperature_mean_4_origin`, `precipitation_sum_4_origin`, `season_sin`,
`season_cos`, `population`, `population_density`. Media reciente requiere al
menos dos conteos conocidos; ventanas climáticas requieren cuatro semanas
completas. El objetivo es cantidad de registros t+h y permanece separado de
las presencias A/B. Las variables faltantes siguen NULL.

La vista es una preparación de contrato. El consumidor debe aplicar las reglas
congeladas de admisibilidad de horizonte/continuidad y comprobar procedencia,
features, máscaras y semántica antes de conectarla a un modelo existente.
No se afirma equivalencia con los artefactos V3 sólo por compartir nombres.

## Universos y tiempo

Los 263 radios A/B y los 256 V3 se representan mediante pertenencias explícitas
al maestro versionado. `analytics.correspondencia_universos` sólo une la misma
clave canónica de radio/geometría presente en ambos; no hay fuzzy matching ni
coincidencias por posición de fila. Los vecinos V3 se restringen a sus miembros.

En modo `as_of`, historia y clima se exponen sólo si su disponibilidad acreditada
precede al cierre del origen. El contexto estático sin fecha disponible queda
NULL, también para A. Síntomas o extracción final no sustituyen llegada. En modo
`retrospective` se declara reconstrucción de eventos, no un backtest operativo.
 La base importada no proporciona automáticamente antecedentes de 2025/2026.

## Consumidores PostgreSQL y equivalencia

La [migración de consumidores](postgres-ml-migration.md) implementa la lectura
compartida y los adaptadores offline A/B/V3, con bloqueo previo si falta
equivalencia completa. Los modelos históricos se conservan. La inferencia nueva
de A basada en Parquet deja de anunciarse como disponible; su reproducción
requiere una opción histórica explícita. No se modifica la API pública, el
frontend ni la demo. La importación no entrena ni habilita modelos.
