# Pipeline territorial oficial: fase 1

La fase 2 incorpora lectura y calidad local. Ver
[implementación, configuración y límites actuales](official-ingestion.md).
El alcance de fase 1 documentado a continuación se conserva como antecedente.

## Estado y alcance histórico de fase 1

Implementación inicial independiente en `ml/src/sigard_ml/official/`.
Hay contratos, validadores estructurales, autorización en memoria e interfaces.
No hay lector de Excel, deduplicador, unión espacial, agregador, entrenador ni
exportador ejecutable. Ninguna fuente está habilitada por defecto. Las pruebas
usan valores ficticios y no necesitan los cinco archivos del Ministerio.

Este circuito no modifica el modelo temporal departamental, sus features,
hiperparámetros, métricas ni predicciones. Tampoco sustituye la simulación
espacial, el contexto territorial o los contratos consumidos por React.

## Arquitectura y reutilización

El flujo futuro, con implementaciones pendientes, es:

```text
Fuente externa / extracto previamente autorizado [Control A]
  -> ingestión y validación de registros privados
  -> resolución de episodios elegibles
  -> procesamiento geográfico y asignación trazable
  -> panel observado radio censal - semana epidemiológica
  -> features conocidas al corte
  -> aprobación de dataset, objetivo y evaluación [Control B]
  -> entrenamiento y evaluación offline
  -> revisión científica y de privacidad [Control C]
  -> adaptación al sistema de publicación versionada existente
  -> API y mapa
```

Se reutilizarán los componentes existentes según sus límites:

- `official.calendar`: calendario domingo-sábado validado para 2020–2026,
  versión `ar-snvs-2020-2026-v1`, con límites anuales explícitos y rechazo
  de SE53 inexistentes. No depende del calendario histórico del MVP.
  `validation.temporal.epidemiological_week_start` conserva por defecto
  `sigard-iso-shift-v0` y admite una versión explícita. Ver
  [fuentes, contradicción 2025/2026 y reproducción](official-calendar.md).
- `evaluation.temporal.build_temporal_split`: candidato para separar semanas
  objetivo completas, adaptando el nombre de columna. No se reutilizará una
  partición congelada del dataset sintético.
- `models.persistence.PersistenceBaseline`: reutilizable indicando
  `current_cases_column="observed_cases"`; su valor predeterminado es sintético.
- Maestro censal: geometría, población, hogares, viviendas, densidad y vecinos
  reutilizables tras verificar versión, CRS y universo. No se ejecutó su
  pipeline ni se abrió su artefacto durante esta fase.
- `features.radio_week`: panel y rezagos están ligados a
  `synthetic_cases_assigned`; no se conectan al circuito oficial. La futura
  implementación observada usará búsquedas por fecha exacta.
- `backend/app/publication_import.py`: ofrece transacciones, idempotencia y
  versionado, pero actualmente acepta seis contratos del MVP y activa el lote
  al importar. No debe invocarse con estos objetos internos. Su extensión y
  recuperación se revisarán en fase 7.
- `frontend/src/services/sigardData.js`: conserva API y fallback estático; no
  recibe objetos privados del nuevo paquete.

No se crearon siete paquetes vacíos: los puertos en `interfaces.py` permiten
añadir cada etapa cuando tenga una implementación y pruebas concretas.

## Contratos internos

`contracts.py` define objetos inmutables con validación al construirlos. Los
errores estructurales no incluyen los valores rechazados.

- `DatasetMetadata`: identidad, versiones de fuente y transformación, período,
  cartografía, unidad y esquema `0.1.0`. Admite `official_observed` o
  `fictional_fixture`; rechaza la etiqueta sintética experimental. Una etiqueta
  declarada no acredita autorización ni calidad.
- `EpidemiologicalWeek`: año, SE, inicio, fin, convención e instancia inmutable
  de calendario; expone `calendar_version`. La validación del calendario no
  acredita cobertura ni la semántica clínica de los registros.
- `EpidemiologicalRecord`: referencias opacas, unidad de registro, regla de
  clasificación, elegibilidad, fecha epidemiológica y disponibilidad opcionales.
  Un paciente, notificación, muestra o actualización no equivale automáticamente
  a un episodio elegible. La fecha epidemiológica y la regla de episodios se
  definirán con el custodio en fase 2.
- `Coordinates`: objeto privado con x/y, CRS declarado y rol de ubicación.
  Comprueba finitud y rangos globales para `EPSG:4326`; no verifica todavía CRS,
  límites de Capital ni geometrías. Ausencia se representa con `None`.
  Residencia no implica lugar de contagio. La transformación y sospechas
  geográficas corresponden a fase 3; no se rellenará con centroides.
- `TerritorialAssignment`: referencia de episodio, versión cartográfica,
  estado y radio sólo para asignación válida. Coordenadas ausentes o inválidas,
  CRS desconocido, exterior, límites y ambigüedad quedan sin radio.
- `QualityReport`: conteos agregados y códigos cerrados, sin muestras ni textos
  libres. Posibles duplicados se informan; no se eliminan sin reglas aprobadas.
  Los códigos pueden solaparse y no deben sumarse como rechazos. Es un reporte
  privado, sin autorización automática para divulgación.
- `ObservedRadioWeek` y `ObservedPanel`: claves radio-semana únicas, período
  coherente, conteos enteros no negativos, ceros explícitos y ausencias nulas.
  `geographic_coverage` es una fracción opcional de 0 a 1; su denominador se
  definirá en fase 4. Completitud de los 263 radios, continuidad, conciliación
  de episodios y justificación de ceros aún deben implementarse.
- `FeatureValue`, `TrainingExample` y `TrainingDataset`: lista explícita de
  variables agregadas permitidas, fecha hasta la que se observó cada señal y
  fecha de disponibilidad, horizonte semanal y claves únicas. Rechazan
  variables declaradas futuras, coordenadas, identificadores y columnas
  sintéticas. Esto no prueba el cálculo: en fase 4 se verificará procedencia y
  ausencia de filtración temporal en las transformaciones.
- `TerritorialPrediction`: corte, semana objetivo, radio, objetivo, valor y
  referencias de modelo/dataset. Distingue cantidades esperadas, probabilidades
  y tasas por 100.000 habitantes. Los contratos admiten tres opciones; no se
  seleccionó un objetivo real. Cada dataset acepta uno solo. Incidencia
  requerirá denominadores válidos. No es un contrato público.

La evaluación se declara `retrospective` o `as_of_reconstructed`. El segundo
valor exigirá evidencia de disponibilidad histórica; una etiqueta no constituye
validación operativa. Entrenamiento, incertidumbre, baselines y métricas
apropiadas quedan para fases 5 y 6.

Los objetos privados omiten registros y coordenadas de su representación
`repr`. No es cifrado ni un filtro universal: serialización manual, `asdict`,
tracebacks con variables locales y logs explícitos podrían exponerlos. No deben
volcarse. Referencias opacas nunca deben contener nombres, DNI, domicilios ni
texto clínico. No se implementó un serializador de registros privados.

## Autorización y almacenamiento

`access.py` define `SourceAuthorization` y `SourceRegistry`. El registro vacío
deniega todas las fuentes. Cada autorización exige ruta absoluta, versión,
hojas exactas, referencia del subconjunto y usos enumerados. Antes de aceptar
una solicitud comprueba habilitación, alcance exacto, extracto aprobado y
referencias documentales de permiso, custodia, confidencialidad y almacenamiento.
No abre, resuelve ni consulta la existencia del archivo.

`approved_extract` indica que la fuente accesible completa y las hojas
seleccionadas están autorizadas. Un libro completo autorizado puede cumplirlo;
un libro mixto pendiente necesita un extracto o acceso limitado aprobado.
`subset_ref` no es un filtro para abrir primero todo el libro. Esta fase sólo
expresa el contrato de extractos; no implementa acceso limitado.

Es una barrera de aplicación, no control de acceso del sistema operativo ni
verificación de autenticidad documental. El lector futuro debe comprobarla
antes de IO y verificar integridad y alcance de la fuente accesible. Los usos
permitidos no sustituyen aprobaciones B de entrenamiento ni C de publicación;
los puertos respectivos exigen referencias separadas.

El registro no tiene aún cargador de configuración privada: se añadirá en fase
2 fuera de configuraciones versionadas. Fuentes externas inmutables, parciales
en `data/interim/official/`, paneles protegidos en `data/processed/official/` y
modelos en `ml/artifacts/official/`. Son rutas reservadas documentalmente; no se
generaron datasets ni modelos. `.gitignore` ya excluye datos y modelos pero no
aporta confidencialidad. ACL, respaldo, retención y cifrado deben acordarse
antes de tratar datos reales.

## Docker

Ya existen frontend, backend, PostGIS con volumen persistente, migraciones,
publicación y ML offline bajo perfil `tools`. El Dockerfile ML empaqueta `src/`;
incluirá el paquete nuevo sin dependencias adicionales. No se modificó Compose
ni se construyó o ejecutó una imagen durante fase 1.

No ejecutar el futuro circuito oficial mediante el montaje actual `./data`
sin revisar alcance: puede exponer fuentes pendientes y ML tiene escritura
sobre artefactos públicos. Fase 8 limitará montajes a extractos autorizados
externos de sólo lectura, configuración privada y salidas protegidas, sin
publicación automática. Se reutilizarán imagen y trabajos temporales.

## Reproducción y verificación

Desde la raíz, usando el entorno existente:

```powershell
.\ml\venv\Scripts\python.exe -m pytest ml/tests/test_official_contracts.py -p no:cacheprovider
```

Si el temporal predeterminado tiene problemas de permisos, indicar
`--basetemp=ml/.tmp/<directorio-nuevo-exclusivo>`. Pytest puede eliminar el
directorio indicado; nunca usar una carpeta con datos o trabajo previo.

Las pruebas cubren denegación por defecto, alcance y usos independientes,
autorización sin IO, calendario, tipos, ausencia versus cero, datos inválidos,
unicidad, objetivos, unidades, reportes reproducibles y disponibilidad temporal.
Los puntos son ficticios y sólo comprueban el contrato de coordenadas; los
casos interiores/exteriores/limítrofes se probarán al implementar unión espacial
en fase 3. No se entrena siquiera un modelo ficticio en esta fase.

Para regresión se seleccionan pruebas existentes que crean sus propios fixtures.
No ejecutar toda `ml/tests` sin revisar efectos: contiene pruebas que leen
fuentes y artefactos locales, y algunas ejecutan pipelines sobre ellos.

Verificación de fase 1 realizada el 2026-10-09:

```powershell
.\ml\venv\Scripts\python.exe -m pytest ml/tests/test_official_contracts.py ml/tests/test_territorial_validation.py ml/tests/test_baseline_evaluation.py ml/tests/test_synthetic_allocation.py ml/tests/test_temporal_pipeline.py -k 'not test_local_pipeline_expected_contract' --basetemp=ml/.tmp/official-phase1-regression-20261009-4fde726b -p no:cacheprovider --tb=short
```

Resultado: **85 pruebas aprobadas y 1 deseleccionada** en 1,50 segundos.
La deseleccionada lee fuentes locales y queda fuera del alcance autorizado.
El primer intento de la suite nueva tuvo 48 aprobadas y 14 errores de preparación
por permisos del temporal predeterminado de pytest; una carpeta exclusiva dentro
de `ml/.tmp/` permitió ejecutarla correctamente. No se cambió una prueba existente
para resolver ese problema. El diff documental pasó `git diff --check`.

## Habilitación de la próxima fase

Puede construirse el lector y validadores con fixtures. Antes de cualquier
acceso oficial se necesita, según Control A solicitado por el usuario:

1. Ruta local externa de almacenamiento.
2. Archivos, hojas y subconjuntos exactamente aprobados; extracto si hay mezcla
   de registros aprobados y pendientes.
3. Usos permitidos: inspección, procesamiento, entrenamiento, evaluación y
   posible publicación, por alcance.
4. Restricciones de confidencialidad, almacenamiento, retención y respaldo.
5. Evidencia de autorización documentada y responsable de custodia.

Después de inspección autorizada se definirán unidad de registro,
clasificaciones, deduplicación, fechas, calendario, CRS y semántica de ubicación.
Antes de entrenar se presentarán cobertura, calidad, distribución, objetivo,
variables y protocolo para Control B. Antes del mapa se presentarán evaluación,
contrato público, supresión/agregación de cantidades pequeñas, propuesta visual,
archivos afectados y recuperación para Control C. No hay commits, pushes,
merges ni rebases autorizados (Control D).
