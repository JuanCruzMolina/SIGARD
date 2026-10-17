# Fase 5B.2: conciliación local de originales y selecciones

## Estado vigente: suspendida por decisión del responsable

La conciliación con originales queda suspendida y su infraestructura se conserva.
El alcance vigente comprende exclusivamente los cinco Excel procesados ya
configurados. Los archivos en revisión quedan fuera del procesamiento y de la
auditoría actual; no se solicitan sus rutas. Las instrucciones de ejecución que
siguen describen una capacidad futura, no una tarea pendiente de esta versión.
Su reactivación requiere una nueva indicación explícita del responsable.

Los registros actuales constituyen el universo de trabajo versionado, sin
acreditar el universo epidemiológico definitivo ni cobertura de semanas sin
registros. Incorporaciones futuras deben declarar nuevas versiones y hashes de
fuentes y regenerar los derivados dependientes en destinos nuevos, conservando
la procedencia y los resultados anteriores. Esta suspensión no modifica las
limitaciones de clasificación, fechas, cobertura o asignación espacial, ni el
objetivo predictivo o el Modelo A.

La herramienta `sigard_ml.official.selection_reconciliation_pipeline` compara
roles declarados explícitamente: `original`, `manual_working` y `processed`.
No infiere equivalencia por nombres ni busca originales recorriendo carpetas
personales. Sin rutas originales declaradas, no ejecuta la lectura sanitaria.
La disponibilidad de las copias intermedias debe indicarse como proporcionada,
desconocida, no conservada o sin copia separada; no se inventa esa etapa.

## Configuración privada

El ejemplo público deja fuentes vacías y autorización desactivada. La
configuración real debe guardarse bajo `data/interim/official/`, fuera de Git.
Cada rol declara ruta absoluta XLSX, versión, condición local privada, hashes
esperados cuando están disponibles, hojas/fila de encabezado y columnas.
Los cinco procesados deben fijarse a las versiones/hashes del circuito actual;
el total esperado sigue siendo el ya conciliado en las fases anteriores.

La preparación privada identifica los procesados conocidos, dejando originales
y copias intermedias sin completar hasta que el responsable aporte sus rutas y
correspondencias. No se leen archivos nominales fuera del alcance declarado.

Tras completar las rutas se puede ejecutar un perfil local:

```powershell
.\ml\venv\Scripts\python.exe -B -m sigard_ml.official.selection_reconciliation_pipeline --config <configuracion-privada> --mode profile
```

Luego debe documentarse la hipótesis de selección y usar un destino **nuevo**:

```powershell
.\ml\venv\Scripts\python.exe -B -m sigard_ml.official.selection_reconciliation_pipeline --config <configuracion-privada> --mode compare
```

La regla identifica una columna de clasificación, etiquetas literales aceptadas,
valores de provincia/departamento de residencia y, sólo si está expresamente
documentado, filtros por disponibilidad de fecha o domicilio. No usa búsquedas
parciales de palabras ni clasifica desde el nombre del archivo. Las otras columnas
de clasificación se incluyen en inventarios agregados para revisión, sin
equiparar una clasificación manual/algorítmica a confirmación clínica validada.

## Protección de los datos

- Lectura local de XLSX en modo de sólo lectura, sin ejecutar fórmulas o enlaces.
- No se incorporan SDKs remotos, servicios de geocodificación, entrenadores ni
  telemetría de contenido a los scripts.
- Las filas y los identificadores se procesan exclusivamente en memoria.
- Cotejo con HMAC-SHA-256 y clave efímera por ejecución; no se exportan ni la
  clave ni los tokens. Los resultados agregados son invariantes a esa clave.
- No se proyectan nombres, documentos o coordenadas. El domicilio sólo se
  transforma en presencia/ausencia/desconocido; su texto no se conserva.
- Sólo se escriben agregados y metadatos/versiones/hashes privados. No hay
  tablas de filas, exportaciones de candidatos individuales o IDs pseudonimizados.
- Consola de vocabulario cerrado: estado y cantidades agregadas, sin etiquetas
  libres, rutas, nombres de hojas, valores de pacientes ni excepciones originales.
- Los informes con dominios de clasificación/residencia son para revisión local
  del responsable; no se deben volcar sus contenidos libres al chat o servicios.
- Se rechazan fuentes públicas y archivos del repositorio no ignorados por Git.
  El destino debe ser nuevo y estar directamente dentro del interim oficial privado.

Las fuentes y artefactos científicos se protegen por hashes antes/después; las
entradas externas declaradas también se verifican al finalizar. Los errores de
lectura se devuelven sin texto de las excepciones de datos. Si el entorno no
permite esta separación, debe detenerse la ejecución y elegir almacenamiento local
privado adecuado antes de leer las filas.

## Semántica del cotejo

Se informa por separado:

- Filas originales, intermedias y procesadas.
- Dominios/frecuencias de clasificaciones y residencia, y fechas clínicas agregadas.
- Filas seleccionadas/excluidas/desconocidas bajo la hipótesis literal explícita.
- Candidatos únicos por ID, registros con ID faltante y registros sin contraparte
  identificable en el otro archivo.
- Grupos repetidos/ambiguos y sus multiplicidades, conservando todas las filas.
- Diferencias de clasificación y residencia sólo en pares con candidato único.
- Originales seleccionados sin candidato procesado y procesados con candidato
  original que no satisface la regla propuesta.
- Asociación de fecha/domicilio ausente con filas no representadas, sin atribuir
  automáticamente esa ausencia como causa histórica de exclusión.

La normalización de ID preserva ceros iniciales y rechaza números inseguros o
fórmulas; no se completa un ID desde nombres/documentos. Un candidato por ID no
prueba que se trate del mismo episodio epidemiológico. Las repeticiones no se
deduplican ni se emparejan seleccionando la primera fila. Los IDs faltantes son
no cotejables, no registros demostrablemente ajenos a la fuente.

El cotejo se ejecuta original–procesado y, si existe una copia de trabajo declarada,
también original–trabajo y trabajo–procesado. La igualdad de bytes se informa por
SHA-256 independientemente de nombres y roles; no prueba por sí sola la procedencia
o semántica clínica declarada.

## Cobertura y alcance

La configuración conserva separadamente período solicitado, período de extracción,
campo temporal/corte y referencias documentales. Los perfiles informan extremos
clínicos observados. La fecha de creación/modificación del Excel no se usa como
fecha de extracción. Ninguna coincidencia, ausencia o extremo observado declara
completitud automáticamente.

Una reproducción exacta de una selección literal no valida su significado
epidemiológico: requieren revisión el diccionario de eventos, el criterio de
confirmación histórico y el procedimiento territorial real. Especialmente debe
conciliarse la fuente 2022 con todos los campos de clasificación disponibles.
Los paneles, etiquetas, features y modelos existentes permanecen intactos; no se
generan negativos ni se entrena.

## Pruebas

```powershell
.\ml\venv\Scripts\python.exe -B -m pytest ml/tests/test_official_selection_reconciliation.py -p no:cacheprovider --basetemp=ml/.tmp/phase5b2-check
```

Las pruebas usan libros totalmente ficticios y verifican protección de identidad,
agregación, ambigüedades, diferencias de campos, reglas no clínicas, ausencia de
fecha/domicilio, fórmulas, encabezados ambiguos, integridad, reproducibilidad,
destinos privados y bloqueo antes de lectura si faltan rutas originales.
