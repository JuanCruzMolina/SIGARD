# Resoluciones deterministas sin reimportación

La revisión consume sólo los originales operacionales ya preservados en la
base privada y las declaraciones locales existentes. No geocodifica por red,
no consulta nuevos registros clínicos, no modifica Excel y no ejecuta modelos.
La migración aditiva `20261028_epi08` conserva las tablas fuente y las
ejecuciones analíticas anteriores.

## Evidencia espacial

`territory.revision_asignacion` distingue el punto almacenado de la calidad de
la ubicación. Repite `ST_Intersects` y `ST_Contains` contra la versión de
geometría de cada asignación, exige un único interior y contrasta la clave
canónica declarada por igualdad exacta. No utiliza coincidencias difusas ni
elimina ceros de los códigos. Un trigger comprueba la unicidad y la versión.

- `point_only`: candidato geométrico conservado, precisión insuficiente o
  incompatibilidad pendiente. No se utiliza su radio para acotar artificialmente
  el alcance de un pendiente cuya incertidumbre no está documentada.
- `unique_provisional`: altura interpolada fuente, confianza media/alta, método
  exacto/difuso, sin marca fuente pendiente y radio compatible. Sigue siendo una
  asignación provisional; no acredita residencia, exactitud ni lugar de infección.
- `ambiguous`, `boundary`, `outside`, `invalid`, `insufficient`: motivo explícito
  sin asignación seleccionada. Una posible inversión de ejes se diagnostica,
  nunca se corrige automáticamente.

La marca `requiere_revision` original se conserva. Se revisan también precisión,
confianza, método y topología: la bandera por sí sola no describe el problema.
Una precisión de calle/barrio no proporciona un radio de error en metros. Un
buffer arbitrario o la distancia al límite no permiten aprobar esos domicilios.
El CRS supuesto continúa supuesto; los predicados no lo certifican.

## Fechas, clasificación e identidad

`epidemiology.revision_fecha` conserva la observación y añade una interpretación
por versión. El literal explícito `*sin dato*` pasa de formato inválido a ausente,
sin generar una fecha. No se infieren años desde nombres de archivo ni se usan
fechas administrativas para reemplazar síntomas/muestra. La prioridad temporal
permanece síntomas y luego muestra, con aproximación conservada.

`revision_clasificacion` conserva las equivalencias explícitas previas. Un
literal sin equivalencia o con equivalencias contradictorias permanece pendiente;
una mención de laboratorio positivo no acredita por sí sola otra definición
clínica. No se reinterpretan las clasificaciones de 2022. Las relaciones de
identificadores repetidos se mantienen pendientes y no fusionan registros.

## Cobertura y semanas sin registros

`revision_extraccion` vincula la declaración original, su huella, alcance y
limitaciones a cada archivo y versión de resolución. Una declaración del
responsable sobre exportación completa respecto de filtros se conserva como
declaración del responsable. No se convierte en verificación independiente ni
en intervalos de síntomas que no haya documentado.

Los estados de la grilla conservan el contrato previo:

- `verified`: cobertura revisada bajo fuente, criterio, población, filtros,
  territorio y semanas completas explícitos. Un cero necesita además ausencia
  de pendientes posibles y fechas aproximadas.
- `experimental_assumed`: sólo las semanas explícitamente autorizadas del
  escenario. El cero es condicional al supuesto y a las mismas máscaras de
  calidad, nunca ausencia epidemiológica.
- `unknown`: información insuficiente. Una semana sin filas conserva NULL.
- `out_of_scope`: fuera del escenario explícito; tampoco produce cero.

La presencia de registros confirmados incorporados se expresa con
`registros_observados` y presencia positiva; puede coexistir con cantidad
completa NULL. La ausencia de observaciones incorporadas no acredita un cero.
Los pendientes sin fecha pueden afectar todas las semanas; sin una asignación
utilizable y sin cota espacial, todos los radios posibles. No se suman esas
menciones como personas. Las semanas respaldadas sin pendientes no se descartan.

## Reproducibilidad y uso

`version_resolucion` contiene política, evidencia y huella de los originales
operacionales. Las cinco tablas nuevas rechazan UPDATE y DELETE. Repetir una
resolución idéntica devuelve la versión existente; una entrada o evidencia
distinta exige una versión nueva. La analítica rechaza revisiones obsoletas.

Migrar con el procedimiento privado existente y cargar
`SIGARD_EPI_DATABASE_URL` desde el archivo ignorado, sin imprimirlo. Después:

```powershell
.\ml\venv\Scripts\python.exe -B -m sigard_ml.ingestion.db_resolution --config data/interim/official/NUEVA_REVISION/resolution-config.private.json --report data/interim/official/NUEVA_REVISION/resolution-result.private.json
```

El JSON incluye `status="approved"`, `authorization_ref`, `version`, `evidence`
y opcionalmente `extraction_declarations`, por ID de archivo, cada una con
`source_sha256` y evidencia. El informe siempre usa almacenamiento privado.

Las nuevas configuraciones de `db_analytics` añaden `resolution_version` y
seleccionan `batch_ids` explícitos. Cada proyección utiliza otro `version`,
sin sobrescribir datos previos. La vista `conteos_con_procedencia` añade
`version_resolucion_geografica`, `version_territorial`, `politica_cobertura` y
`fuentes_sha256`, conservando el orden y tipo de las columnas anteriores.
Las vistas A/B/V3 siguen seleccionando ejecuciones por versión; no cambian los
contratos de variables ni activan inferencia.

En modo `as_of`, la revisión debe existir antes del corte y su fecha de creación
participa en la disponibilidad del agregado. Una revisión hecha después del
origen no habilita retrospectivamente sus antecedentes. En modo `retrospective`
se mantiene la reconstrucción declarada, sin acreditar disponibilidad histórica.

Las pruebas ficticias usan la base de pruebas PostGIS ya existente, protegida
por nombre y marcador de clúster. Nunca se ejecutan en la base de registros.
Se comprueban originales, idempotencia, restricciones espaciales, fechas,
ceros/NULL, cuatro rezagos exactos, versiones, permisos y entradas obsoletas.
