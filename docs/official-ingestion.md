# Fase 2: ingestión y calidad epidemiológica local

## Alcance

Esta fase lee únicamente los libros explícitamente habilitados de la entrega
autorizada. Inspecciona estructura, normaliza en memoria, informa calidad y puede
guardar una proyección privada mínima. No entrena, filtra casos confirmados,
deduplica, asigna radios, construye un panel radio-semana ni publica resultados.

El objetivo futuro solicitado es estimar la probabilidad de registrar casos de
dengue en semanas futuras por radio. Esta fase no construye todavía una etiqueta
binaria: antes deben definirse episodios, elegibilidad y cobertura. Ausencia de
notificaciones no constituye automáticamente una semana sin casos.

## Módulos y recorrido del código

- `access.py`: reutiliza las autorizaciones de fase 1. Ahora admite autorización
  explícita del libro completo con `all_sheets_approved`; su valor inicial es
  falso. Los permisos parciales siguen limitados a hojas declaradas de una
  fuente accesible íntegramente autorizada o un extracto aprobado.
- `settings.py`: aliases de columnas, vocabulario seguro de encabezados,
  límites de fecha, umbral de supresión y señales descriptivas de precisión.
- `excel.py`: abre XLSX en lectura, comprueba permiso antes de IO, detecta fila
  de encabezado o usa la configurada y devuelve un DataFrame privado. No evalúa
  fórmulas. No hay soporte XLS ni apertura de fuentes por búsqueda recursiva.
- `normalization.py`: normaliza espacios, formatos de fecha explícitos y coma
  decimal simple. No interpreta números como fechas seriales ni inventa fechas.
- `validation.py`: funciones sobre datos en memoria. Valida presencia, fechas,
  cronología, repeticiones e integridad estructural, sin resolver episodios.
- `geography.py`: rangos, faltantes, errores, repetición, decimales e inversión
  candidata. Opcionalmente compara contra el límite disuelto de los 263 radios.
  No calcula el radio al que pertenece un punto.
- `reports.py`: reportes agregados seguros y escritura atómica de archivos;
  la exportación de filas está separada de la validación.
- `pipeline.py`: carga configuración, verifica rutas y SHA-256, coordina etapas
  y ofrece el CLI. Las funciones siguen un recorrido directo, sin nuevos
  patrones de clases o servicios.

`contracts.py`, `calendar.py` e interfaces de fase 1 se conservan. Los objetos de
episodio y panel quedan reservados para fases siguientes; no se fabrican
episodios elegibles a partir de filas cuya unidad todavía es desconocida.

## Configuración editable

El ejemplo versionable `ml/configs/official.example.json` tiene `sources: []`:
no habilita fuentes. El manifiesto local de esta entrega está en
`data/interim/official/access.private.json` y queda excluido de Git e imágenes.
La autorización de esta ejecución procede de la instrucción del usuario para
la primera entrega. La identidad del custodio y las políticas formales de
retención/respaldo permanecen pendientes; el código no autentica documentación.

Parámetros que pueden cambiar manualmente, tras revisar su significado:

- `source_root`: carpeta autorizada; no se buscan libros fuera de ella.
- `sources`: nombres exactos, referencias técnicas, permisos y versiones.
  `expected_sha256` bloquea versiones cambiadas antes de leer sus celdas.
  Archivos nuevos no se incorporan automáticamente.
- `layouts`: opciones por `sheet_01`, etc. Permiten `header_row` y `column_map`
  con índices de columnas que empiezan en uno. Las entregas pueden usar
  posiciones distintas. Revisar el esquema antes de cambiar estos índices.
- `uses`: únicamente `inspection` y `processing` en fase 2. Entrenamiento,
  evaluación y publicación se rechazan desde la configuración.
- `as_of_date`: corte reproducible del control de fechas futuras.
- `date_formats`: formatos explícitos; el valor predeterminado está en
  `normalization.py`. No cambiar formatos para ocultar fechas inconsistentes.
- `allowed_classifications`: inicialmente `null`. Sólo completar con un
  diccionario validado por Epidemiología. Las menciones literales de palabras
  no equivalen a validación de un caso ni a un dominio epidemiológico aprobado.
- `geography`: ruta censal pública, CRS declarado/confirmado y umbral de baja
  precisión decimal. En esta fase sólo se admite CRS confirmado EPSG:4326;
  las transformaciones corresponden a fase 3.
- `write_normalized`: booleano que permite la proyección privada; nunca exporta
  al frontend. `output_dir` debe resolver dentro de `data/interim/official/` o
  `data/processed/official/`; destinos públicos se rechazan.

No usar un libro mixto con registros pendientes aunque la configuración permita
declararlo: la barrera de aplicación requiere que la fuente accesible ya sea
íntegramente autorizada. Los campos de referencia no prueban esa autorización.

## Qué significan los controles

Una fila estructuralmente completa tiene ID de evento y clasificación presentes,
inicio de síntomas interpretable y no futuro, y ambas coordenadas dentro de
rangos globales. No significa un episodio válido, un caso confirmado ni una
ubicación suficientemente precisa. Todas las filas conservan la unidad
`unresolved_source_record` y requieren revisión metodológica.

Fechas vacías y textos no interpretables se informan por separado. Los formatos
y tipos rechazados se resumen sin mostrar valores. Posibles marcas de ausencia
no se convierten automáticamente a fechas. La toma de muestra anterior a
síntomas se marca para revisión; no se descarta. Los períodos se describen por
años de fechas interpretables, no por el nombre del archivo.

Repeticiones exactas de filas e IDs repetidos son señales diferentes. IDs con
filas distintas podrían indicar actualización, muestra, repetición o episodio;
se requiere una regla de Epidemiología. Los IDs se usan sólo en memoria y no se
exportan. No se elimina ni se fusiona una fila.

Coordenadas válidas globalmente no garantizan precisión. Si CRS es desconocido,
el control de Capital usa una hipótesis de longitud/latitud geográficas y queda
marcado como provisional. Exterior e inversión no se corrigen automáticamente;
sin cartografía, el control devuelve `null`, nunca un cero tranquilizador.
Puntos en el límite se registran aparte. Decimales abundantes no acreditan
exactitud. La repetición puede deberse a hogares compartidos o a aproximaciones
por calle/barrio; las palabras de las etiquetas de precisión tampoco son prueba
de exactitud. No se asigna el primer polígono ni un centroide a registros faltantes.

No se reconstruyó disponibilidad histórica de las notificaciones ni de sus
correcciones. Estas fuentes no permiten todavía afirmar validación operativa.

## Salidas y confidencialidad

En el directorio protegido se generan:

- `structure_report.json`: referencias de hojas, encabezados filtrados por
  vocabulario técnico, columnas, tipos y faltantes. Palabras desconocidas se
  ocultan; no se imprimen nombres de hojas ni celdas.
- `quality_report.json` y `quality_report.md`: resúmenes técnicos seguros,
  integridad, hashes, versiones y preguntas pendientes.
- `normalized/*.parquet`, si se habilita: proyección privada con referencia
  determinista de fila, fechas normalizadas, clasificación, coordenadas
  candidatas, metadatos de geocodificación y flags. No contiene nombres, DNI,
  teléfonos, domicilios ni IDs originales de eventos. Sigue siendo información
  sanitaria protegida y no está anonimizada para publicación.

SHA-256 antes y después de leer garantiza detectar cambios de la fuente durante
la ejecución. El hash previsto del manifiesto permite comprobar la entrega.
La referencia de fila combina hash del libro y número de fila; facilita
trazabilidad local sin volcar identificadores. El reporte declara versión de
transformación, origen oficial y unidad provisional. No se mezclan fixtures
con la ejecución oficial ni derivados sintéticos con estas filas.

Conteos positivos menores de cinco se muestran como `<5`; no hay desglose por
radio, persona, domicilio, edad o coordenada. Es supresión técnica preliminar,
no un permiso ni una evaluación suficiente de divulgación. El CLI no imprime
excepciones originales ni tracebacks que puedan contener celdas. No usar un
depurador que suba valores o muestre variables locales de registros privados.

`.gitignore` protege fuentes, derivados y manifiestos; `.dockerignore` protege
los contextos. No sustituyen permisos del equipo, cifrado ni controles de
respaldo. Acordar estas políticas con el custodio antes de ampliar usos.

## Ejecución local

Requiere el entorno ML existente y `openpyxl==3.1.5`, disponible como extra
`official`. Para preparar otro equipo: `python -m pip install -e "ml[official,test]"`.
No se instalaron dependencias adicionales durante esta ejecución.

Desde la raíz:

```powershell
.\ml\venv\Scripts\python.exe -m sigard_ml.official.pipeline --config data/interim/official/access.private.json --inspect-only
.\ml\venv\Scripts\python.exe -m sigard_ml.official.pipeline --config data/interim/official/access.private.json
```

Ambos comandos muestran sólo reportes seguros y escriben en las rutas privadas.
Los archivos generados de esta fase pueden regenerarse; nunca se sobrescriben
originales, modelos, artefactos del frontend ni datasets vigentes.

No se modificó Compose ni se ejecutó una imagen. Sus contextos actuales están
separados y los servicios públicos no montan la carpeta oficial. El servicio ML
existente monta todo `data/` en lectura y tiene escritura sobre artefactos
públicos: no usarlo para esta entrega sin revisar montajes en fase 8.
Docker Desktop no respondió al chequeo de servicios activos; se verificó
configuración estática, no montajes efectivos de contenedores en ejecución.

## Pruebas y actualización

Las pruebas nuevas crean Excel y geometrías completamente ficticias. Cubren
permisos, hojas ausentes, esquema, fechas, nulos, formatos, duplicados,
coordenadas, privacidad, proyección y bloqueo de versiones cambiadas.

La verificación final ejecutó los tres módulos `test_official_*.py` y las
regresiones de validación territorial, baseline, asignación sintética y temporal:
123 pruebas aprobadas y una deseleccionada. Se excluyó
`test_local_pipeline_expected_contract` porque lee fuentes locales. Ninguna
prueba existente se modificó ni se ejecutó un entrenamiento.

Comando final ejecutado el 2026-10-09 (1,71 segundos):

```powershell
.\ml\venv\Scripts\python.exe -m pytest ml/tests/test_official_contracts.py ml/tests/test_official_ingestion.py ml/tests/test_official_quality.py ml/tests/test_territorial_validation.py ml/tests/test_baseline_evaluation.py ml/tests/test_synthetic_allocation.py ml/tests/test_temporal_pipeline.py -k 'not test_local_pipeline_expected_contract' --basetemp=ml/.tmp/phase2-handoff-20261009-7e13bc58 -p no:cacheprovider --tb=short
```

Usar una carpeta temporal nueva para repetirlo: pytest puede borrar la indicada.

Ante una entrega nueva: confirmar autorización, listar libros, inspeccionar
estructura, revisar esquema y versiones, ajustar el manifiesto privado y
ejecutar pruebas ficticias antes del procesamiento autorizado. Revisar reportes
y preguntas; no asumir que una versión cambiada conserva sus campos.

Fase 3 requiere aprobación expresa. Deben aclararse unidad de registro,
identificador de episodio, clasificación elegible, fechas, CRS, precisión,
procedencia y rol geográfico. Debe definirse qué hacer con coordenadas por calle
que pueden atravesar varios radios, repeticiones y ubicaciones limítrofes.
Se preservan los controles separados de entrenamiento real y publicación.
