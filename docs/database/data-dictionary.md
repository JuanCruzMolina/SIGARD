# Diccionario estructural

Diccionario del esquema PostgreSQL implementado. No contiene nombres de hojas,
valores clínicos, direcciones ni distribuciones reales. El diccionario **real
por columna Excel**, con encabezados originales y destino propuesto, se guarda
privadamente en el inventario de la importación. Las columnas no reconocidas
conservan su posición, tipo Excel y valor en staging; no se eliminan.

`PK`: clave primaria; `FK`: clave foránea; `NULL`: ausencia permitida. Los tipos
de fecha no indican disponibilidad del registro; ésta tiene su campo separado.
Los identificadores externos y códigos son texto. `contenido_original` es el
archivo completo; `contenido` es una fila de celdas tipadas, no un caso validado.

## `analytics.clima_semana`

| Columna | Tipo PostgreSQL | Claves | NULL | Significado |
|---|---|---|---|---|
| `version` | text | PK | No | Identificación de versión del catálogo, fuente, regla o ejecución correspondiente. |
| `semana_id` | bigint | PK, FK | No | Referencia a analytics.semana_epidemiologica.id. |
| `temperatura` | double precision | — | Sí | Temperatura, correspondiente a esta entidad. |
| `humedad` | double precision | — | Sí | Humedad, correspondiente a esta entidad. |
| `precipitacion` | double precision | — | Sí | Precipitacion, correspondiente a esta entidad. |
| `disponible_desde` | timestamp with time zone | — | Sí | Momento acreditado de disponibilidad; NULL no se sustituye por fecha del evento. |
| `fuente_sha256` | character | — | No | Huella de la entrada de procedencia; no evidencia de validez epidemiológica. |
| `compatible` | boolean | — | No | Compatible, correspondiente a esta entidad. |

Restricciones:

- `PRIMARY KEY (version, semana_id)`
- `FOREIGN KEY (semana_id) REFERENCES analytics.semana_epidemiologica(id)`

## `analytics.conteos_radio_semana`

| Columna | Tipo PostgreSQL | Claves | NULL | Significado |
|---|---|---|---|---|
| `ejecucion_id` | bigint | PK, FK | No | Referencia a analytics.ejecucion.id. |
| `radio_id` | bigint | PK, FK | No | Referencia a territory.radio_censal.id. |
| `semana_id` | bigint | PK, FK | No | Referencia a analytics.semana_epidemiologica.id. |
| `registros_observados` | integer | — | No | Subtotal de registros incluidos bajo las reglas de la ejecución. |
| `cantidad_registros` | integer | — | Sí | Conteo completo bajo cobertura y calidad suficientes; NULL en caso contrario. |
| `episodios_acreditados` | integer | — | Sí | Sin acreditación de episodios; permanece NULL. |
| `presencia` | integer | — | Sí | Presencia binaria provisional o NULL; un negativo necesita respaldo de cero. |
| `pendientes_posibles` | integer | — | No | Menciones posibles de pendientes en la celda; no sumarlas como personas. |
| `fechas_aproximadas` | integer | — | No | Registros incluidos con referencia temporal alternativa. |
| `cobertura_estado` | text | — | No | Cobertura estado, correspondiente a esta entidad. |
| `estado_asignacion` | text | — | No | Estado asignacion, correspondiente a esta entidad. |
| `ultimo_disponible` | timestamp with time zone | — | Sí | Última disponibilidad requerida del agregado y su respaldo de cobertura. |
| `disponibilidad_verificada` | boolean | — | No | Indica si la disponibilidad permite aplicar el corte as-of. |
| `ventana_parcial` | boolean | — | No | Semana no contenida completamente en la ventana analítica; impide conteo completo. |

Restricciones:

- `CHECK ((cantidad_registros >= 0))`
- `CHECK (((cantidad_registros IS NULL) OR ((cobertura_estado = ANY (ARRAY['verified'::text, 'experimental_assumed'::text])) AND (pendientes_posibles = 0))))`
- `CHECK (((cantidad_registros IS NULL) OR (presencia = ((cantidad_registros > 0))::integer)))`
- `CHECK ((cobertura_estado = ANY (ARRAY['verified'::text, 'experimental_assumed'::text, 'unknown'::text, 'out_of_scope'::text])))`
- `FOREIGN KEY (ejecucion_id) REFERENCES analytics.ejecucion(id)`
- `CHECK ((episodios_acreditados IS NULL))`
- `CHECK ((fechas_aproximadas >= 0))`
- `CHECK ((pendientes_posibles >= 0))`
- `PRIMARY KEY (ejecucion_id, radio_id, semana_id)`
- `CHECK ((presencia = ANY (ARRAY[0, 1])))`
- `FOREIGN KEY (radio_id) REFERENCES territory.radio_censal(id)`
- `CHECK ((registros_observados >= 0))`
- `FOREIGN KEY (semana_id) REFERENCES analytics.semana_epidemiologica(id)`
- `CHECK (((cantidad_registros IS NULL) OR ((fechas_aproximadas = 0) AND (NOT ventana_parcial))))`
- `CHECK (((cantidad_registros IS NULL) OR ((cantidad_registros = registros_observados) AND (presencia IS NOT NULL))))`
- `CHECK (((presencia IS NULL) OR ((presencia = 1) AND (registros_observados > 0)) OR ((presencia = 0) AND (cantidad_registros IS NOT NULL) AND (cantidad_registros = 0))))`

## `analytics.contexto_radio`

| Columna | Tipo PostgreSQL | Claves | NULL | Significado |
|---|---|---|---|---|
| `universo_id` | bigint | PK, FK | No | Referencia a territory.miembro_universo.universo_id, territory.universo.id. |
| `radio_id` | bigint | PK, FK | No | Referencia a territory.miembro_universo.radio_id, territory.radio_censal.id. |
| `superficie_km2` | double precision | — | No | Superficie km2, correspondiente a esta entidad. |
| `poblacion` | integer | — | No | Poblacion, correspondiente a esta entidad. |
| `cantidad_vecinos` | integer | — | No | Cantidad vecinos, correspondiente a esta entidad. |
| `fuente_sha256` | character | — | No | Huella de la entrada de procedencia; no evidencia de validez epidemiológica. |
| `disponible_desde` | timestamp with time zone | — | Sí | Momento acreditado de disponibilidad; NULL no se sustituye por fecha del evento. |

Restricciones:

- `CHECK ((cantidad_vecinos >= 0))`
- `PRIMARY KEY (universo_id, radio_id)`
- `CHECK ((poblacion >= 0))`
- `FOREIGN KEY (radio_id) REFERENCES territory.radio_censal(id)`
- `CHECK ((superficie_km2 > (0)::double precision))`
- `FOREIGN KEY (universo_id) REFERENCES territory.universo(id)`
- `FOREIGN KEY (universo_id, radio_id) REFERENCES territory.miembro_universo(universo_id, radio_id)`

## `analytics.ejecucion`

| Columna | Tipo PostgreSQL | Claves | NULL | Significado |
|---|---|---|---|---|
| `id` | bigint | PK | No | Identificador interno de la entidad, sin semántica de caso. |
| `version` | text | — | No | Identificación de versión del catálogo, fuente, regla o ejecución correspondiente. |
| `universo_id` | bigint | FK | No | Referencia a territory.universo.id. |
| `politica_temporal_id` | bigint | FK | No | Referencia a epidemiology.politica_temporal.id. |
| `politica_clasificacion_id` | bigint | FK | No | Referencia a epidemiology.politica_clasificacion.id. |
| `criterio_cobertura_id` | bigint | FK | No | Referencia a epidemiology.criterio_cobertura.id. |
| `inicio` | date | — | No | Inicio, correspondiente a esta entidad. |
| `fin` | date | — | No | Fin, correspondiente a esta entidad. |
| `calendario_version` | text | — | No | Calendario version, correspondiente a esta entidad. |
| `escenario` | text | — | No | Escenario, correspondiente a esta entidad. |
| `aceptar_geografia_provisional` | boolean | — | No | Aceptar geografia provisional, correspondiente a esta entidad. |
| `corte_informacion` | timestamp with time zone | — | No | Corte informativo explícito con zona horaria. |
| `modo` | text | — | No | Reconstrucción retrospectiva o aplicación estricta de disponibilidad as-of. |
| `clima_version` | text | — | Sí | Clima version, correspondiente a esta entidad. |
| `equivalencia_ml_verificada` | boolean | — | No | No habilita modelos hasta verificar el contrato completo; falso inicialmente. |
| `creado_en` | timestamp with time zone | — | No | Creado en, correspondiente a esta entidad. |

Restricciones:

- `CHECK ((inicio <= fin))`
- `FOREIGN KEY (criterio_cobertura_id) REFERENCES epidemiology.criterio_cobertura(id)`
- `CHECK ((escenario = ANY (ARRAY['conservative'::text, 'experimental_assumed'::text])))`
- `CHECK ((modo = ANY (ARRAY['retrospective'::text, 'as_of'::text])))`
- `PRIMARY KEY (id)`
- `FOREIGN KEY (politica_clasificacion_id) REFERENCES epidemiology.politica_clasificacion(id)`
- `FOREIGN KEY (politica_temporal_id) REFERENCES epidemiology.politica_temporal(id)`
- `FOREIGN KEY (universo_id) REFERENCES territory.universo(id)`
- `UNIQUE (version)`

## `analytics.exclusion_registro`

| Columna | Tipo PostgreSQL | Claves | NULL | Significado |
|---|---|---|---|---|
| `ejecucion_id` | bigint | PK, FK | No | Referencia a analytics.ejecucion.id. |
| `registro_id` | bigint | PK, FK | No | Referencia a epidemiology.registro_epidemiologico.id. |
| `motivo` | text | PK | No | Motivo, correspondiente a esta entidad. |

Restricciones:

- `FOREIGN KEY (ejecucion_id) REFERENCES analytics.ejecucion(id)`
- `PRIMARY KEY (ejecucion_id, registro_id, motivo)`
- `FOREIGN KEY (registro_id) REFERENCES epidemiology.registro_epidemiologico(id)`

## `analytics.fuente_ejecucion`

| Columna | Tipo PostgreSQL | Claves | NULL | Significado |
|---|---|---|---|---|
| `ejecucion_id` | bigint | PK, FK | No | Referencia a analytics.ejecucion.id. |
| `lote_id` | bigint | PK, FK | No | Referencia a ingestion.lote_importacion.id. |

Restricciones:

- `FOREIGN KEY (ejecucion_id) REFERENCES analytics.ejecucion(id)`
- `FOREIGN KEY (lote_id) REFERENCES ingestion.lote_importacion(id)`
- `PRIMARY KEY (ejecucion_id, lote_id)`

## `analytics.semana_epidemiologica`

| Columna | Tipo PostgreSQL | Claves | NULL | Significado |
|---|---|---|---|---|
| `id` | bigint | PK | No | Identificador interno de la entidad, sin semántica de caso. |
| `calendario_version` | text | — | No | Calendario version, correspondiente a esta entidad. |
| `anio` | integer | — | No | Anio, correspondiente a esta entidad. |
| `numero` | integer | — | No | Numero, correspondiente a esta entidad. |
| `inicio` | date | — | No | Inicio, correspondiente a esta entidad. |
| `fin` | date | — | No | Fin, correspondiente a esta entidad. |
| `semanas_anio` | integer | — | No | Semanas anio, correspondiente a esta entidad. |

Restricciones:

- `UNIQUE (calendario_version, anio, numero)`
- `UNIQUE (calendario_version, inicio)`
- `CHECK ((fin = (inicio + 6)))`
- `CHECK (((numero >= 1) AND (numero <= 53)))`
- `PRIMARY KEY (id)`
- `CHECK ((semanas_anio = ANY (ARRAY[52, 53])))`

## `epidemiology.catalogo_clasificacion`

| Columna | Tipo PostgreSQL | Claves | NULL | Significado |
|---|---|---|---|---|
| `id` | bigint | PK | No | Identificador interno de la entidad, sin semántica de caso. |
| `codigo` | text | — | No | Código textual de catálogo o identificador canónico, sin perder ceros iniciales. |

Restricciones:

- `UNIQUE (codigo)`
- `PRIMARY KEY (id)`

## `epidemiology.clase_admitida`

| Columna | Tipo PostgreSQL | Claves | NULL | Significado |
|---|---|---|---|---|
| `politica_id` | bigint | PK, FK | No | Referencia a epidemiology.politica_clasificacion.id. |
| `catalogo_id` | bigint | PK, FK | No | Referencia a epidemiology.catalogo_clasificacion.id. |

Restricciones:

- `FOREIGN KEY (catalogo_id) REFERENCES epidemiology.catalogo_clasificacion(id)`
- `PRIMARY KEY (politica_id, catalogo_id)`
- `FOREIGN KEY (politica_id) REFERENCES epidemiology.politica_clasificacion(id)`

## `epidemiology.clasificacion_registro`

| Columna | Tipo PostgreSQL | Claves | NULL | Significado |
|---|---|---|---|---|
| `id` | bigint | PK | No | Identificador interno de la entidad, sin semántica de caso. |
| `registro_id` | bigint | FK | No | Referencia a epidemiology.registro_epidemiologico.id. |
| `columna_id` | bigint | FK | No | Referencia a ingestion.columna_fuente.id. |
| `valor_literal` | text | — | No | Clasificación original observada, sin reinterpretación clínica. |
| `fecha_revision` | date | — | Sí | Fecha revision, correspondiente a esta entidad. |

Restricciones:

- `FOREIGN KEY (columna_id) REFERENCES ingestion.columna_fuente(id)`
- `PRIMARY KEY (id)`
- `UNIQUE (registro_id, columna_id)`
- `FOREIGN KEY (registro_id) REFERENCES epidemiology.registro_epidemiologico(id)`

## `epidemiology.cobertura_fuente`

| Columna | Tipo PostgreSQL | Claves | NULL | Significado |
|---|---|---|---|---|
| `id` | bigint | PK | No | Identificador interno de la entidad, sin semántica de caso. |
| `archivo_id` | bigint | FK | No | Referencia a ingestion.archivo_fuente.id. |
| `universo_id` | bigint | FK | No | Referencia a territory.universo.id. |
| `criterio_id` | bigint | FK | No | Referencia a epidemiology.criterio_cobertura.id. |
| `inicio` | date | — | No | Inicio, correspondiente a esta entidad. |
| `fin` | date | — | No | Fin, correspondiente a esta entidad. |

Restricciones:

- `FOREIGN KEY (archivo_id) REFERENCES ingestion.archivo_fuente(id)`
- `UNIQUE (archivo_id, universo_id, criterio_id, inicio, fin)`
- `CHECK ((inicio <= fin))`
- `FOREIGN KEY (criterio_id) REFERENCES epidemiology.criterio_cobertura(id)`
- `PRIMARY KEY (id)`
- `FOREIGN KEY (universo_id) REFERENCES territory.universo(id)`

## `epidemiology.criterio_cobertura`

| Columna | Tipo PostgreSQL | Claves | NULL | Significado |
|---|---|---|---|---|
| `id` | bigint | PK | No | Identificador interno de la entidad, sin semántica de caso. |
| `version` | text | — | No | Identificación de versión del catálogo, fuente, regla o ejecución correspondiente. |
| `politica_clasificacion_id` | bigint | FK | No | Referencia a epidemiology.politica_clasificacion.id. |
| `definicion_poblacion` | text | — | No | Definicion poblacion, correspondiente a esta entidad. |
| `filtro_extraccion` | text | — | No | Filtro extraccion, correspondiente a esta entidad. |

Restricciones:

- `PRIMARY KEY (id)`
- `FOREIGN KEY (politica_clasificacion_id) REFERENCES epidemiology.politica_clasificacion(id)`
- `UNIQUE (version)`

## `epidemiology.fecha_registro`

| Columna | Tipo PostgreSQL | Claves | NULL | Significado |
|---|---|---|---|---|
| `id` | bigint | PK | No | Identificador interno de la entidad, sin semántica de caso. |
| `registro_id` | bigint | FK | No | Referencia a epidemiology.registro_epidemiologico.id. |
| `tipo_id` | bigint | FK | No | Referencia a epidemiology.tipo_fecha.id. |
| `columna_id` | bigint | FK | No | Referencia a ingestion.columna_fuente.id. |
| `valor` | date | — | Sí | Fecha interpretada o NULL con su estado, conservando el original en staging. |
| `estado` | text | — | No | Estado controlado por las restricciones enumeradas de esta entidad. |
| `parser_version` | text | — | No | Versión de interpretación de fechas, separada de las observaciones. |

Restricciones:

- `CHECK (((estado = 'valid'::text) = (valor IS NOT NULL)))`
- `FOREIGN KEY (columna_id) REFERENCES ingestion.columna_fuente(id)`
- `CHECK ((estado = ANY (ARRAY['valid'::text, 'missing'::text, 'invalid_format'::text, 'out_of_range'::text])))`
- `PRIMARY KEY (id)`
- `UNIQUE (registro_id, columna_id, parser_version)`
- `FOREIGN KEY (registro_id) REFERENCES epidemiology.registro_epidemiologico(id)`
- `FOREIGN KEY (tipo_id) REFERENCES epidemiology.tipo_fecha(id)`

## `epidemiology.grupo_etario`

| Columna | Tipo PostgreSQL | Claves | NULL | Significado |
|---|---|---|---|---|
| `id` | bigint | PK | No | Identificador interno de la entidad, sin semántica de caso. |
| `literal` | text | — | No | Literal, correspondiente a esta entidad. |

Restricciones:

- `UNIQUE (literal)`
- `PRIMARY KEY (id)`

## `epidemiology.incidencia_validacion`

| Columna | Tipo PostgreSQL | Claves | NULL | Significado |
|---|---|---|---|---|
| `id` | bigint | PK | No | Identificador interno de la entidad, sin semántica de caso. |
| `registro_id` | bigint | FK | No | Referencia a epidemiology.registro_epidemiologico.id. |
| `codigo` | text | — | No | Código textual de catálogo o identificador canónico, sin perder ceros iniciales. |
| `columna_id` | bigint | FK | Sí | Referencia a ingestion.columna_fuente.id. |

Restricciones:

- `FOREIGN KEY (columna_id) REFERENCES ingestion.columna_fuente(id)`
- `PRIMARY KEY (id)`
- `UNIQUE NULLS NOT DISTINCT (registro_id, codigo, columna_id)`
- `FOREIGN KEY (registro_id) REFERENCES epidemiology.registro_epidemiologico(id)`

## `epidemiology.normalizacion_clasificacion`

| Columna | Tipo PostgreSQL | Claves | NULL | Significado |
|---|---|---|---|---|
| `id` | bigint | PK | No | Identificador interno de la entidad, sin semántica de caso. |
| `observacion_id` | bigint | FK | No | Referencia a epidemiology.clasificacion_registro.id. |
| `regla_id` | bigint | FK | No | Referencia a epidemiology.regla_normalizacion_clasificacion.id. |
| `aplicada_en` | timestamp with time zone | — | No | Aplicada en, correspondiente a esta entidad. |

Restricciones:

- `FOREIGN KEY (observacion_id) REFERENCES epidemiology.clasificacion_registro(id)`
- `UNIQUE (observacion_id, regla_id)`
- `PRIMARY KEY (id)`
- `FOREIGN KEY (regla_id) REFERENCES epidemiology.regla_normalizacion_clasificacion(id)`

## `epidemiology.politica_clasificacion`

| Columna | Tipo PostgreSQL | Claves | NULL | Significado |
|---|---|---|---|---|
| `id` | bigint | PK | No | Identificador interno de la entidad, sin semántica de caso. |
| `version` | text | — | No | Identificación de versión del catálogo, fuente, regla o ejecución correspondiente. |
| `definicion` | text | — | No | Definicion, correspondiente a esta entidad. |

Restricciones:

- `PRIMARY KEY (id)`
- `UNIQUE (version)`

## `epidemiology.politica_temporal`

| Columna | Tipo PostgreSQL | Claves | NULL | Significado |
|---|---|---|---|---|
| `id` | bigint | PK | No | Identificador interno de la entidad, sin semántica de caso. |
| `version` | text | — | No | Identificación de versión del catálogo, fuente, regla o ejecución correspondiente. |
| `descripcion` | text | — | No | Descripcion, correspondiente a esta entidad. |

Restricciones:

- `PRIMARY KEY (id)`
- `UNIQUE (version)`

## `epidemiology.prioridad_fecha`

| Columna | Tipo PostgreSQL | Claves | NULL | Significado |
|---|---|---|---|---|
| `politica_id` | bigint | PK, FK | No | Referencia a epidemiology.politica_temporal.id. |
| `tipo_id` | bigint | PK, FK | No | Referencia a epidemiology.tipo_fecha.id. |
| `prioridad` | integer | — | No | Prioridad, correspondiente a esta entidad. |

Restricciones:

- `PRIMARY KEY (politica_id, tipo_id)`
- `FOREIGN KEY (politica_id) REFERENCES epidemiology.politica_temporal(id)`
- `UNIQUE (politica_id, prioridad)`
- `CHECK ((prioridad > 0))`
- `FOREIGN KEY (tipo_id) REFERENCES epidemiology.tipo_fecha(id)`

## `epidemiology.registro_epidemiologico`

| Columna | Tipo PostgreSQL | Claves | NULL | Significado |
|---|---|---|---|---|
| `id` | bigint | PK | No | Identificador interno de la entidad, sin semántica de caso. |
| `fila_id` | bigint | FK | No | Referencia a ingestion.fila_staging.id. |
| `identificador_externo` | text | — | Sí | Referencia original del evento; no identifica de forma única persona o episodio. |
| `grupo_etario_id` | bigint | FK | Sí | Referencia a epidemiology.grupo_etario.id. |
| `domicilio_id` | bigint | FK | Sí | Referencia a territory.domicilio.id. |
| `estado_normalizacion` | text | — | No | Estado normalizacion, correspondiente a esta entidad. |
| `disponible_desde` | timestamp with time zone | — | Sí | Momento acreditado de disponibilidad; NULL no se sustituye por fecha del evento. |

Restricciones:

- `FOREIGN KEY (domicilio_id) REFERENCES territory.domicilio(id)`
- `CHECK ((estado_normalizacion = ANY (ARRAY['complete'::text, 'partial'::text])))`
- `FOREIGN KEY (fila_id) REFERENCES ingestion.fila_staging(id)`
- `UNIQUE (fila_id)`
- `FOREIGN KEY (grupo_etario_id) REFERENCES epidemiology.grupo_etario(id)`
- `PRIMARY KEY (id)`

## `epidemiology.regla_normalizacion_clasificacion`

| Columna | Tipo PostgreSQL | Claves | NULL | Significado |
|---|---|---|---|---|
| `id` | bigint | PK | No | Identificador interno de la entidad, sin semántica de caso. |
| `version` | text | — | No | Identificación de versión del catálogo, fuente, regla o ejecución correspondiente. |
| `literal_canonico` | text | — | No | Clave literal normalizada bajo una versión de correspondencia. |
| `catalogo_id` | bigint | FK | No | Referencia a epidemiology.catalogo_clasificacion.id. |
| `estado_validacion` | text | — | No | Estado validacion, correspondiente a esta entidad. |

Restricciones:

- `FOREIGN KEY (catalogo_id) REFERENCES epidemiology.catalogo_clasificacion(id)`
- `CHECK ((estado_validacion = ANY (ARRAY['provisional'::text, 'validated'::text])))`
- `PRIMARY KEY (id)`
- `UNIQUE (version, literal_canonico)`

## `epidemiology.relacion_registro`

| Columna | Tipo PostgreSQL | Claves | NULL | Significado |
|---|---|---|---|---|
| `id` | bigint | PK | No | Identificador interno de la entidad, sin semántica de caso. |
| `registro_id` | bigint | FK | No | Referencia a epidemiology.registro_epidemiologico.id. |
| `otro_id` | bigint | FK | No | Referencia a epidemiology.registro_epidemiologico.id. |
| `tipo` | text | — | No | Tipo, correspondiente a esta entidad. |
| `evidencia` | text | — | No | Referencia de respaldo o justificación conservada para revisión. |
| `revision_estado` | text | — | No | Revision estado, correspondiente a esta entidad. |

Restricciones:

- `CHECK ((registro_id <> otro_id))`
- `FOREIGN KEY (otro_id) REFERENCES epidemiology.registro_epidemiologico(id)`
- `PRIMARY KEY (id)`
- `FOREIGN KEY (registro_id) REFERENCES epidemiology.registro_epidemiologico(id)`
- `UNIQUE (registro_id, otro_id, tipo)`
- `CHECK ((revision_estado = ANY (ARRAY['technical_exact'::text, 'pending'::text, 'accepted'::text, 'rejected'::text])))`
- `CHECK ((tipo = ANY (ARRAY['exact_duplicate'::text, 'possible_revision'::text, 'same_external_id'::text])))`

## `epidemiology.revision_cobertura`

| Columna | Tipo PostgreSQL | Claves | NULL | Significado |
|---|---|---|---|---|
| `id` | bigint | PK | No | Identificador interno de la entidad, sin semántica de caso. |
| `cobertura_id` | bigint | FK | No | Referencia a epidemiology.cobertura_fuente.id. |
| `estado` | text | — | No | Estado controlado por las restricciones enumeradas de esta entidad. |
| `evidencia` | text | — | No | Referencia de respaldo o justificación conservada para revisión. |
| `responsable` | text | — | No | Referencia del responsable de la declaración o revisión. |
| `revisada_en` | timestamp with time zone | — | No | Revisada en, correspondiente a esta entidad. |

Restricciones:

- `FOREIGN KEY (cobertura_id) REFERENCES epidemiology.cobertura_fuente(id)`
- `CHECK ((estado = ANY (ARRAY['verified'::text, 'experimental_assumed'::text, 'unknown'::text, 'out_of_scope'::text])))`
- `CHECK ((evidencia <> ''::text))`
- `PRIMARY KEY (id)`

## `epidemiology.tipo_fecha`

| Columna | Tipo PostgreSQL | Claves | NULL | Significado |
|---|---|---|---|---|
| `id` | bigint | PK | No | Identificador interno de la entidad, sin semántica de caso. |
| `codigo` | text | — | No | Código textual de catálogo o identificador canónico, sin perder ceros iniciales. |

Restricciones:

- `UNIQUE (codigo)`
- `PRIMARY KEY (id)`

## `ingestion.archivo_fuente`

| Columna | Tipo PostgreSQL | Claves | NULL | Significado |
|---|---|---|---|---|
| `id` | bigint | PK | No | Identificador interno de la entidad, sin semántica de caso. |
| `nombre_original` | text | — | No | Nombre original, correspondiente a esta entidad. |
| `sha256` | character | — | No | Huella de integridad del archivo o payload tipado según la entidad. |
| `bytes` | bigint | — | No | Bytes, correspondiente a esta entidad. |
| `periodo_declarado` | text | — | Sí | Periodo declarado, correspondiente a esta entidad. |
| `fecha_extraccion` | date | — | Sí | Fecha extraccion, correspondiente a esta entidad. |
| `procedencia` | text | — | No | Procedencia, correspondiente a esta entidad. |
| `entrega_version` | text | — | No | Entrega version, correspondiente a esta entidad. |
| `contenido_original` | bytea | — | No | Bytes íntegros del archivo fuente; almacenamiento privado. |

Restricciones:

- `CHECK ((bytes >= 0))`
- `CHECK ((octet_length(contenido_original) = bytes))`
- `PRIMARY KEY (id)`
- `CHECK ((sha256 ~ '^[a-f0-9]{64}$'::text))`
- `UNIQUE (sha256)`

## `ingestion.columna_fuente`

| Columna | Tipo PostgreSQL | Claves | NULL | Significado |
|---|---|---|---|---|
| `id` | bigint | PK | No | Identificador interno de la entidad, sin semántica de caso. |
| `hoja_id` | bigint | FK | No | Referencia a ingestion.hoja_fuente.id. |
| `ordinal` | integer | — | No | Posición física de hoja o columna, con numeración desde uno. |
| `nombre_original` | text | — | Sí | Nombre original, correspondiente a esta entidad. |
| `campo_propuesto` | text | — | Sí | Campo reconocido del importador; una ausencia no elimina la columna. |

Restricciones:

- `FOREIGN KEY (hoja_id) REFERENCES ingestion.hoja_fuente(id)`
- `UNIQUE (hoja_id, ordinal)`
- `CHECK ((ordinal > 0))`
- `PRIMARY KEY (id)`

## `ingestion.fila_staging`

| Columna | Tipo PostgreSQL | Claves | NULL | Significado |
|---|---|---|---|---|
| `id` | bigint | PK | No | Identificador interno de la entidad, sin semántica de caso. |
| `lote_id` | bigint | FK | No | Referencia a ingestion.lote_importacion.id. |
| `hoja_id` | bigint | FK | No | Referencia a ingestion.hoja_fuente.id. |
| `numero_fila` | integer | — | No | Fila física original en la hoja, con numeración desde uno. |
| `contenido` | jsonb | — | No | Array posicional de celdas originales tipadas, con formato Excel. |
| `sha256` | character | — | No | Huella de integridad del archivo o payload tipado según la entidad. |
| `estado` | text | — | No | Estado controlado por las restricciones enumeradas de esta entidad. |

Restricciones:

- `CHECK ((jsonb_typeof(contenido) = 'array'::text))`
- `CHECK ((estado = ANY (ARRAY['normalized'::text, 'partial'::text])))`
- `FOREIGN KEY (hoja_id) REFERENCES ingestion.hoja_fuente(id)`
- `FOREIGN KEY (lote_id) REFERENCES ingestion.lote_importacion(id)`
- `UNIQUE (lote_id, hoja_id, numero_fila)`
- `CHECK ((numero_fila > 0))`
- `PRIMARY KEY (id)`
- `CHECK ((sha256 ~ '^[a-f0-9]{64}$'::text))`

## `ingestion.hoja_fuente`

| Columna | Tipo PostgreSQL | Claves | NULL | Significado |
|---|---|---|---|---|
| `id` | bigint | PK | No | Identificador interno de la entidad, sin semántica de caso. |
| `archivo_id` | bigint | FK | No | Referencia a ingestion.archivo_fuente.id. |
| `ordinal` | integer | — | No | Posición física de hoja o columna, con numeración desde uno. |
| `nombre` | text | — | No | Nombre, correspondiente a esta entidad. |
| `fila_encabezado` | integer | — | No | Fila encabezado, correspondiente a esta entidad. |
| `layout_sha256` | character | — | Sí | Layout sha256, correspondiente a esta entidad. |
| `preambulo` | jsonb | — | No | Preambulo, correspondiente a esta entidad. |

Restricciones:

- `FOREIGN KEY (archivo_id) REFERENCES ingestion.archivo_fuente(id)`
- `UNIQUE (archivo_id, nombre)`
- `UNIQUE (archivo_id, ordinal)`
- `CHECK ((fila_encabezado >= 0))`
- `CHECK ((ordinal > 0))`
- `PRIMARY KEY (id)`

## `ingestion.lote_importacion`

| Columna | Tipo PostgreSQL | Claves | NULL | Significado |
|---|---|---|---|---|
| `id` | bigint | PK | No | Identificador interno de la entidad, sin semántica de caso. |
| `archivo_id` | bigint | FK | No | Referencia a ingestion.archivo_fuente.id. |
| `importador_version` | text | — | No | Importador version, correspondiente a esta entidad. |
| `creado_en` | timestamp with time zone | — | No | Creado en, correspondiente a esta entidad. |
| `estado` | text | — | No | Estado controlado por las restricciones enumeradas de esta entidad. |
| `filas_leidas` | integer | — | No | Filas leidas, correspondiente a esta entidad. |
| `filas_normalizadas` | integer | — | No | Filas normalizadas, correspondiente a esta entidad. |
| `filas_parciales` | integer | — | No | Filas parciales, correspondiente a esta entidad. |
| `validacion` | jsonb | — | No | Validacion, correspondiente a esta entidad. |

Restricciones:

- `FOREIGN KEY (archivo_id) REFERENCES ingestion.archivo_fuente(id)`
- `UNIQUE (archivo_id, importador_version)`
- `CHECK ((estado = ANY (ARRAY['loading'::text, 'complete'::text])))`
- `CHECK ((filas_leidas >= 0))`
- `CHECK ((filas_normalizadas >= 0))`
- `CHECK ((filas_parciales >= 0))`
- `PRIMARY KEY (id)`

## `ingestion.schema_version`

| Columna | Tipo PostgreSQL | Claves | NULL | Significado |
|---|---|---|---|---|
| `version_num` | character varying | PK | No | Version num, correspondiente a esta entidad. |

Restricciones:

- `PRIMARY KEY (version_num)`

## `territory.asignacion_radio`

| Columna | Tipo PostgreSQL | Claves | NULL | Significado |
|---|---|---|---|---|
| `id` | bigint | PK | No | Identificador interno de la entidad, sin semántica de caso. |
| `geocodificacion_id` | bigint | FK | No | Referencia a territory.geocodificacion.id. |
| `version_geometria_id` | bigint | FK | No | Referencia a territory.version_geometria.id. |
| `estado` | text | — | No | Estado controlado por las restricciones enumeradas de esta entidad. |
| `evidencia` | text | — | No | Referencia de respaldo o justificación conservada para revisión. |

Restricciones:

- `CHECK ((estado = ANY (ARRAY['unique_provisional'::text, 'verified'::text, 'ambiguous'::text, 'boundary'::text, 'outside'::text, 'invalid'::text, 'insufficient'::text])))`
- `FOREIGN KEY (geocodificacion_id) REFERENCES territory.geocodificacion(id)`
- `UNIQUE (geocodificacion_id, version_geometria_id)`
- `PRIMARY KEY (id)`
- `FOREIGN KEY (version_geometria_id) REFERENCES territory.version_geometria(id)`
- `TRIGGER DEFERRABLE INITIALLY DEFERRED`

## `territory.candidato_asignacion`

| Columna | Tipo PostgreSQL | Claves | NULL | Significado |
|---|---|---|---|---|
| `asignacion_id` | bigint | PK, FK | No | Referencia a territory.asignacion_radio.id. |
| `radio_id` | bigint | PK, FK | No | Referencia a territory.radio_censal.id. |
| `predicado` | text | — | No | Predicado, correspondiente a esta entidad. |
| `seleccionado` | boolean | — | No | Candidato elegido sólo si el estado permite una selección única. |

Restricciones:

- `TRIGGER DEFERRABLE INITIALLY DEFERRED`
- `FOREIGN KEY (asignacion_id) REFERENCES territory.asignacion_radio(id)`
- `PRIMARY KEY (asignacion_id, radio_id)`
- `FOREIGN KEY (radio_id) REFERENCES territory.radio_censal(id)`

## `territory.contexto_censal`

| Columna | Tipo PostgreSQL | Claves | NULL | Significado |
|---|---|---|---|---|
| `radio_id` | bigint | PK, FK | No | Referencia a territory.radio_censal.id. |
| `version` | text | PK, FK | No | Referencia a territory.version_contexto_censal.version. |
| `poblacion` | integer | — | No | Poblacion, correspondiente a esta entidad. |

Restricciones:

- `PRIMARY KEY (radio_id, version)`
- `CHECK ((poblacion >= 0))`
- `FOREIGN KEY (radio_id) REFERENCES territory.radio_censal(id)`
- `FOREIGN KEY (version) REFERENCES territory.version_contexto_censal(version)`

## `territory.departamento`

| Columna | Tipo PostgreSQL | Claves | NULL | Significado |
|---|---|---|---|---|
| `id` | bigint | PK | No | Identificador interno de la entidad, sin semántica de caso. |
| `provincia_id` | bigint | FK | No | Referencia a territory.provincia.id. |
| `nombre` | text | — | No | Nombre, correspondiente a esta entidad. |
| `codigo` | text | — | Sí | Código textual de catálogo o identificador canónico, sin perder ceros iniciales. |

Restricciones:

- `PRIMARY KEY (id)`
- `UNIQUE (provincia_id, codigo)`
- `FOREIGN KEY (provincia_id) REFERENCES territory.provincia(id)`
- `UNIQUE (provincia_id, nombre)`

## `territory.domicilio`

| Columna | Tipo PostgreSQL | Claves | NULL | Significado |
|---|---|---|---|---|
| `id` | bigint | PK | No | Identificador interno de la entidad, sin semántica de caso. |
| `localidad_id` | bigint | FK | Sí | Referencia a territory.localidad.id. |
| `calle_original` | text | — | Sí | Calle original, correspondiente a esta entidad. |
| `numero_original` | text | — | Sí | Numero original, correspondiente a esta entidad. |

Restricciones:

- `FOREIGN KEY (localidad_id) REFERENCES territory.localidad(id)`
- `PRIMARY KEY (id)`

## `territory.fraccion_censal`

| Columna | Tipo PostgreSQL | Claves | NULL | Significado |
|---|---|---|---|---|
| `id` | bigint | PK | No | Identificador interno de la entidad, sin semántica de caso. |
| `departamento_id` | bigint | FK | No | Referencia a territory.departamento.id. |
| `codigo` | text | — | No | Código textual de catálogo o identificador canónico, sin perder ceros iniciales. |

Restricciones:

- `CHECK ((codigo <> ''::text))`
- `UNIQUE (departamento_id, codigo)`
- `FOREIGN KEY (departamento_id) REFERENCES territory.departamento(id)`
- `PRIMARY KEY (id)`

## `territory.geocodificacion`

| Columna | Tipo PostgreSQL | Claves | NULL | Significado |
|---|---|---|---|---|
| `id` | bigint | PK | No | Identificador interno de la entidad, sin semántica de caso. |
| `registro_id` | bigint | FK | No | Referencia a epidemiology.registro_epidemiologico.id. |
| `proceso_id` | bigint | FK | No | Referencia a territory.proceso_geocodificacion.id. |
| `geom` | geometry | — | Sí | Geometría con SRID 4326; no acredita domicilio ni lugar de infección. |
| `estado` | text | — | No | Estado controlado por las restricciones enumeradas de esta entidad. |
| `precision_literal` | text | — | Sí | Descripción original de precisión; no validación de ubicación. |
| `confianza` | text | — | Sí | Valor literal informado por el geocodificador; no calibración de exactitud. |
| `requiere_revision` | boolean | — | No | Marca fuente de revisión geográfica, conservada sin levantarla automáticamente. |
| `crs_estado` | text | — | No | Crs estado, correspondiente a esta entidad. |
| `radio_declarado` | text | — | Sí | Radio declarado, correspondiente a esta entidad. |
| `fraccion_declarada` | text | — | Sí | Fraccion declarada, correspondiente a esta entidad. |

Restricciones:

- `CHECK ((crs_estado = ANY (ARRAY['declared'::text, 'assumed'::text, 'verified'::text])))`
- `CHECK (((geom IS NULL) OR (((st_x(geom) >= ('-180'::integer)::double precision) AND (st_x(geom) <= (180)::double precision)) AND ((st_y(geom) >= ('-90'::integer)::double precision) AND (st_y(geom) <= (90)::double precision)))))`
- `PRIMARY KEY (id)`
- `FOREIGN KEY (proceso_id) REFERENCES territory.proceso_geocodificacion(id)`
- `FOREIGN KEY (registro_id) REFERENCES epidemiology.registro_epidemiologico(id)`
- `UNIQUE (registro_id, proceso_id)`

## `territory.localidad`

| Columna | Tipo PostgreSQL | Claves | NULL | Significado |
|---|---|---|---|---|
| `id` | bigint | PK | No | Identificador interno de la entidad, sin semántica de caso. |
| `departamento_id` | bigint | FK | No | Referencia a territory.departamento.id. |
| `nombre` | text | — | No | Nombre, correspondiente a esta entidad. |
| `codigo` | text | — | Sí | Código textual de catálogo o identificador canónico, sin perder ceros iniciales. |

Restricciones:

- `UNIQUE (departamento_id, codigo)`
- `FOREIGN KEY (departamento_id) REFERENCES territory.departamento(id)`
- `UNIQUE (departamento_id, nombre)`
- `PRIMARY KEY (id)`

## `territory.miembro_universo`

| Columna | Tipo PostgreSQL | Claves | NULL | Significado |
|---|---|---|---|---|
| `universo_id` | bigint | PK, FK | No | Referencia a territory.universo.id. |
| `radio_id` | bigint | PK, FK | No | Referencia a territory.radio_censal.id. |

Restricciones:

- `PRIMARY KEY (universo_id, radio_id)`
- `FOREIGN KEY (radio_id) REFERENCES territory.radio_censal(id)`
- `FOREIGN KEY (universo_id) REFERENCES territory.universo(id)`

## `territory.normalizacion_domicilio`

| Columna | Tipo PostgreSQL | Claves | NULL | Significado |
|---|---|---|---|---|
| `id` | bigint | PK | No | Identificador interno de la entidad, sin semántica de caso. |
| `domicilio_id` | bigint | FK | No | Referencia a territory.domicilio.id. |
| `version` | text | — | No | Identificación de versión del catálogo, fuente, regla o ejecución correspondiente. |
| `direccion_normalizada` | text | — | Sí | Direccion normalizada, correspondiente a esta entidad. |
| `calle_oficial` | text | — | Sí | Calle oficial, correspondiente a esta entidad. |
| `calle_codigo` | text | — | Sí | Calle codigo, correspondiente a esta entidad. |
| `estado` | text | — | No | Estado controlado por las restricciones enumeradas de esta entidad. |

Restricciones:

- `FOREIGN KEY (domicilio_id) REFERENCES territory.domicilio(id)`
- `UNIQUE (domicilio_id, version)`
- `PRIMARY KEY (id)`

## `territory.pais`

| Columna | Tipo PostgreSQL | Claves | NULL | Significado |
|---|---|---|---|---|
| `id` | bigint | PK | No | Identificador interno de la entidad, sin semántica de caso. |
| `nombre` | text | — | No | Nombre, correspondiente a esta entidad. |
| `codigo` | text | — | Sí | Código textual de catálogo o identificador canónico, sin perder ceros iniciales. |

Restricciones:

- `UNIQUE (codigo)`
- `UNIQUE (nombre)`
- `PRIMARY KEY (id)`

## `territory.proceso_geocodificacion`

| Columna | Tipo PostgreSQL | Claves | NULL | Significado |
|---|---|---|---|---|
| `id` | bigint | PK | No | Identificador interno de la entidad, sin semántica de caso. |
| `proveedor` | text | — | No | Proveedor, correspondiente a esta entidad. |
| `metodo` | text | — | No | Metodo, correspondiente a esta entidad. |
| `version` | text | — | No | Identificación de versión del catálogo, fuente, regla o ejecución correspondiente. |

Restricciones:

- `PRIMARY KEY (id)`
- `UNIQUE (proveedor, metodo, version)`

## `territory.provincia`

| Columna | Tipo PostgreSQL | Claves | NULL | Significado |
|---|---|---|---|---|
| `id` | bigint | PK | No | Identificador interno de la entidad, sin semántica de caso. |
| `pais_id` | bigint | FK | No | Referencia a territory.pais.id. |
| `nombre` | text | — | No | Nombre, correspondiente a esta entidad. |
| `codigo` | text | — | Sí | Código textual de catálogo o identificador canónico, sin perder ceros iniciales. |

Restricciones:

- `UNIQUE (pais_id, codigo)`
- `FOREIGN KEY (pais_id) REFERENCES territory.pais(id)`
- `UNIQUE (pais_id, nombre)`
- `PRIMARY KEY (id)`

## `territory.radio_censal`

| Columna | Tipo PostgreSQL | Claves | NULL | Significado |
|---|---|---|---|---|
| `id` | bigint | PK | No | Identificador interno de la entidad, sin semántica de caso. |
| `fraccion_id` | bigint | FK | No | Referencia a territory.fraccion_censal.id. |
| `version_geometria_id` | bigint | FK | No | Referencia a territory.version_geometria.id. |
| `codigo` | text | — | No | Código textual de catálogo o identificador canónico, sin perder ceros iniciales. |
| `geom` | geometry | — | No | Geometría con SRID 4326; no acredita domicilio ni lugar de infección. |

Restricciones:

- `CHECK ((codigo <> ''::text))`
- `FOREIGN KEY (fraccion_id) REFERENCES territory.fraccion_censal(id)`
- `CHECK (st_isvalid(geom))`
- `CHECK ((NOT st_isempty(geom)))`
- `PRIMARY KEY (id)`
- `UNIQUE (version_geometria_id, codigo)`
- `FOREIGN KEY (version_geometria_id) REFERENCES territory.version_geometria(id)`

## `territory.universo`

| Columna | Tipo PostgreSQL | Claves | NULL | Significado |
|---|---|---|---|---|
| `id` | bigint | PK | No | Identificador interno de la entidad, sin semántica de caso. |
| `version` | text | — | No | Identificación de versión del catálogo, fuente, regla o ejecución correspondiente. |
| `descripcion` | text | — | No | Descripcion, correspondiente a esta entidad. |

Restricciones:

- `PRIMARY KEY (id)`
- `UNIQUE (version)`

## `territory.vecindad`

| Columna | Tipo PostgreSQL | Claves | NULL | Significado |
|---|---|---|---|---|
| `radio_id` | bigint | PK, FK | No | Referencia a territory.radio_censal.id. |
| `vecino_id` | bigint | PK, FK | No | Referencia a territory.radio_censal.id. |
| `regla_version` | text | PK | No | Regla version, correspondiente a esta entidad. |

Restricciones:

- `CHECK ((radio_id <> vecino_id))`
- `PRIMARY KEY (radio_id, vecino_id, regla_version)`
- `FOREIGN KEY (radio_id) REFERENCES territory.radio_censal(id)`
- `FOREIGN KEY (vecino_id) REFERENCES territory.radio_censal(id)`

## `territory.version_contexto_censal`

| Columna | Tipo PostgreSQL | Claves | NULL | Significado |
|---|---|---|---|---|
| `version` | text | PK | No | Identificación de versión del catálogo, fuente, regla o ejecución correspondiente. |
| `fuente_sha256` | character | — | No | Huella de la entrada de procedencia; no evidencia de validez epidemiológica. |

Restricciones:

- `PRIMARY KEY (version)`

## `territory.version_geometria`

| Columna | Tipo PostgreSQL | Claves | NULL | Significado |
|---|---|---|---|---|
| `id` | bigint | PK | No | Identificador interno de la entidad, sin semántica de caso. |
| `version` | text | — | No | Identificación de versión del catálogo, fuente, regla o ejecución correspondiente. |
| `fuente_sha256` | character | — | No | Huella de la entrada de procedencia; no evidencia de validez epidemiológica. |
| `crs` | text | — | No | Crs, correspondiente a esta entidad. |

Restricciones:

- `CHECK ((crs = 'EPSG:4326'::text))`
- `PRIMARY KEY (id)`
- `UNIQUE (version)`

## Semántica de las observaciones

La migración aditiva `epi08` incorpora `analytics.ejecucion.resolucion_version`
(texto nullable, FK a `epidemiology.version_resolucion.version`). Las ejecuciones
anteriores conservan NULL. Las entidades añadidas son:

- `epidemiology.version_resolucion`: PK `version`; `politica`, `entrada_sha256`,
  `evidencia` JSONB y `creada_en` timestamptz, todos obligatorios.
- `territory.revision_asignacion`: PK (`version`, `asignacion_id`), con FK a
  versión y asignación; `radio_id` nullable con FK, `estado`, `motivo` y
  `comprobaciones` JSONB. Sólo `point_only` y `unique_provisional` tienen candidato.
- `epidemiology.revision_fecha`: PK (`version`, `fecha_id`), ambas FK;
  `valor` date nullable, `estado` y `motivo`. Sólo `valid` admite fecha no NULL.
- `epidemiology.revision_clasificacion`: PK (`version`, `observacion_id`), ambas
  FK; `catalogo_id` nullable con FK y `motivo`. NULL conserva la falta de equivalencia.
- `epidemiology.revision_extraccion`: PK (`version`, `archivo_id`), ambas FK;
  `declaracion` JSONB obligatoria, con respaldo y limitaciones del alcance.

Estas tablas son anexos inmutables: UPDATE/DELETE se rechazan mediante trigger.
No se conceden al lector de analítica. El [contrato de revisión](resolution-guide.md)
describe su selección y la procedencia agregada añadida a las vistas.

- Clasificación literal: observación original; la normalizada es propuesta
  provisional y versionada, no acreditación clínica.
- Fecha válida: interpretable bajo el parser, no necesariamente fecha de
  notificación, disponibilidad o cierre epidemiológico.
- Geocodificación: resultado fuente, con CRS supuesto/declarado/verificado;
  un interior único puede ser candidato provisional. La marca de revisión no
  se borra ni se convierte automáticamente en una asignación aprobada.
- Cobertura: `verified`, `experimental_assumed`, `unknown` u `out_of_scope`;
  siempre ligada a fuente, intervalo, universo y criterio.
- Conteo: `registros_observados` es un subtotal incluido bajo las reglas de la
  ejecución; `cantidad_registros` necesita alcance suficiente y sin pendientes
  ni fechas aproximadas. `episodios_acreditados` permanece NULL. Presencia
  provisional puede ser 1 aun cuando la cantidad completa sea desconocida.
- `disponible_desde`/`ultimo_disponible`: evidencia de llegada; NULL permanece
  desconocido y no se sustituye por síntomas ni fecha de extracción.
# Contrato adicional de investigación Option B

La [política B](option-b-research.md) usa tablas separadas y de anexado inmutable:

- `escenario_investigacion.version`: contrato raíz, calendario, fuentes, revisión,
  corte explícito, autorización declarada, protocolo previo al ajuste y huella.
- `registro_escenario_ml`: una selección por escenario y registro fuente, con
  lote, referencia semanal, tipo de fecha, asignación, elegibilidad, exclusión y
  calidad geográfica. Acceso individual reservado al importador.
- `clima_escenario_ml`: semana y número de días; valores NULL cuando faltan días.
- `dataset_investigacion.version`: universo y política geográfica; una variante
  nunca cambia las etiquetas de otra ni las de los experimentos anteriores.
- `conteo_investigacion.cantidad`: registros elegibles asignados, no episodios;
  `cero_asumido` identifica los ceros experimentales. Las tres columnas de calidad
  suman la cantidad y conservan su condición aproximada/provisional/verificada.
- `modelo_investigacion`: familia A/B/V3, horizonte, versión de dataset, estado
  experimental o bloqueado, corte del ajuste, artefacto SQL y SHA-256, protocolo,
  variables, entorno, huellas de código y matriz de desarrollo.
- `evaluacion_investigacion`: métricas de desarrollo, evaluación posterior al
  ajuste y sensibilidad. La sensibilidad no autoriza publicación ni selección
  después de observar la prueba.
- `prediccion_investigacion`: versión de modelo, radio, origen y valor; el modelo
  fija horizonte, dataset, objetivo y política. Las respuestas privadas añaden
  semana objetivo, estado experimental, calidad y causas de indisponibilidad.

Las vistas para consumo nuevo son `metadatos_investigacion`, `base_investigacion`,
`investigacion_a`, `investigacion_b`, `investigacion_v3` y
`disponibilidad_investigacion`. No sustituyen los contratos históricos.
