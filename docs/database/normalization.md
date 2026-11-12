# Dependencias funcionales y normalización

La revisión se aplica al significado declarado de las relaciones operacionales,
no sólo a que existan IDs. Las observaciones son filas fuente, nunca personas
o episodios acreditados. La preservación original en JSONB/bytea y las
proyecciones analíticas constituyen excepciones explícitas, no tablas que se
presenten como 3FN. El historial Alembic es infraestructura.

## 1FN

Las entidades operacionales tienen PK y atributos atómicos. Fechas,
clasificaciones, revisiones, pertenencias y vecinos se representan en
relaciones uno a muchos o muchos a muchos. No hay arrays de fechas, listas de
radios o clasificaciones en una columna operacional. La fila original tipada y
el libro completo son archivos de preservación; no se consultan como sustituto
del modelo relacional normalizado.

## 2FN

En claves compuestas, todos los atributos no clave describen la asociación
completa: `(radio,version_censo) -> poblacion`, `(radio,vecino,regla)` no tiene
atributos adicionales y `(universo,radio)` sólo representa pertenencia. El hash
de procedencia censal depende de la versión, por eso se separó en
`version_contexto_censal(version -> fuente_sha256)`, no se repite en cada radio.
Las magnitudes de `analytics.contexto_radio` son materializaciones controladas.

## 3FN

- `pais_id -> nombre,codigo`; `(pais,nombre)` y los códigos declarados
  establecen identidad de catálogo. Provincia no repite el nombre de país.
- `departamento_id -> provincia_id,nombre,codigo`; localidad no repite la
  provincia. Radio referencia fracción y versión geométrica, sin repetir los
  nombres de toda la jerarquía. Códigos son texto, con ceros iniciales.
- `registro_id -> fila_id,identificador_externo,grupo_etario_id,domicilio_id,
  estado,disponible_desde`. No contiene atributos de archivo, provincia,
  clasificación canónica o semana. `identificador_externo` NO es una clave.
- `observacion_clasificacion_id -> registro,columna,literal,revision`;
  `(version_regla,literal_canonico) -> categoria,estado_validacion`. La categoría
  se obtiene mediante la regla vinculada en otra relación, no se repite con
  su literal normalizado en cada registro.
- `fecha_observada_id -> registro,tipo,columna,valor,estado,parser`; las fechas
  conservan su significado. No se guarda una semana independiente que pueda
  divergir de la fecha. La política temporal ordena tipos por versión.
- `version_geometria -> fuente_sha256,crs`; la geometría del radio depende de
  su identidad versionada. Proveedor/método/versión pertenecen al proceso de
  geocodificación, mientras confianza y revisión pertenecen al resultado.
- La asignación evalúa una geocodificación contra una versión geométrica.
  Sus candidatos están en una relación separada: no se duplica la versión
  determinada por un radio seleccionado dentro de la misma fila de asignación.
- `cobertura_id -> fuente,universo,criterio,intervalo`; estado, evidencia y
  responsable de cada revisión pertenecen a `revision_cobertura`. No se
  transforma evidencia de un criterio en cobertura de otra definición.

`normalizacion_domicilio` conserva propuestas observadas de dirección, nombre
de calle y referencia literal del proveedor. No se afirmó que esa referencia
opaca sea una clave oficial global que determine un nombre único: puede variar
por fuente/proveedor y requerir revisión. El original permanece en staging.
Si se acredita un catálogo oficial de calles, debe incorporarse con su ámbito,
clave y versión; no se inventa esa dependencia a partir de una etiqueta.

## Verificación y límites

La revisión determinista añade `version_resolucion -> politica,entrada_sha256,
evidencia,creada_en` y dependencias compuestas `(version,observacion_padre) ->
interpretacion,motivo`. No copia los campos de identidad de la observación
padre. La resolución de asignación conserva un candidato nullable, con su
pertenencia espacial comprobada por trigger; la versión territorial se obtiene
de la asignación y no se duplica como FK independiente. El JSONB de evidencia
es un documento de auditoría, no un sustituto de las relaciones operacionales.
Los anexos son inmutables y las ejecuciones seleccionan su versión por FK.

La revisión de dependencias se contrasta con las PK, FK, UNIQUE, CHECK, índices
y triggers del esquema PostgreSQL real. Las pruebas ficticias intentan crear
catálogos duplicados, referencias inexistentes, columnas de otra fuente,
geometrías con otro SRID y selecciones ambiguas. No se sostiene que un algoritmo
de introspección descubra todas las dependencias semánticas posibles: las
dependencias anteriores son el contrato revisado. Una relación nueva necesita
la misma revisión. Densidad, estacionalidad y conteos se calculan en analítica.
