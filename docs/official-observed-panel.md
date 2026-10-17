# Fase 4: panel exploratorio oficial por radio y semana

La Fase 4 construye un producto **privado, provisional y retrospectivo**, separado
del futuro panel epidemiológico validado. Cuenta registros elegibles bajo una
política explícita; no los llama casos únicos validados. El objetivo futuro del
circuito oficial es estimar probabilidad de registrar casos en la semana siguiente.
Aquí no se generan etiquetas ni se entrenan modelos, ni se modifica el objetivo
de conteo del MVP sintético o el Random Forest temporal departamental existente.

## Decisión geográfica aceptada

El proyecto acepta los candidatos aproximados ya disponibles y declara Nominatim
y Georef como proveedores. No se exige precisión domiciliaria para este avance,
no se hace ninguna solicitud a esos servicios y no se crean nuevas coordenadas.
La atribución del proveedor por fila no está verificada. Se conserva la hipótesis
de CRS, rol desconocido, precisión declarada, incertidumbre y procedencia de
[Fase 3](official-geography.md); aceptar un candidato no valida residencia exacta.

## Ejecución y configuración

Desde la raíz del repositorio, exclusivamente en `entrenamiento-ML`:

```powershell
# Modo conservador: conserva pendientes; no incluye etiquetas confirmadas automáticamente.
.\ml\venv\Scripts\python.exe -B -m sigard_ml.official.observed_pipeline --config data/interim/official/access.private.json

# Escenario explícito de análisis provisional.
.\ml\venv\Scripts\python.exe -B -m sigard_ml.official.observed_pipeline --config data/interim/official/access.private.json --exploratory
```

`--observed-config ml/configs/official.observed.example.json` permite reemplazar
parámetros. Los valores predeterminados, versiones y correspondencias están en
`official/observed_settings.py`. El ejemplo no contiene referencias de registros
ni evidencia privada. Guardar configuraciones reales y resoluciones manuales
en `data/interim/official/observed/`, fuera de Git y Docker público.

`--exploratory` es imprescindible para activar inclusiones provisionales: la
configuración JSON no habilita por sí sola ese escenario. No existe un modo que
declare automáticamente el panel validado. `--diagnose-failure` sólo imprime el
tipo de error y funciones/líneas; nunca el texto de excepciones o valores de filas.

## Flujo y módulos

1. `observed_reading.py` consume normalizados de Fase 2 mediante su autorización
   existente. Recupera IDs con `excel.read_sheet`, únicamente para referencias
   opacas y fechas alternativas identificadas por encabezados literales. No modifica
   los Parquet anteriores ni guarda identificadores originales. Comprueba las claves
   técnicas de todas las filas y conserva el valor original del inicio de síntomas.
2. Verifica las huellas de asignaciones, reporte, normalizados y cartografía de
   Fase 3. Si difieren, se detiene; no regenera automáticamente esas salidas.
3. `classification.py` aplica correspondencias de etiquetas completas.
4. `eligibility.py` decide inclusión, exclusión o revisión para el análisis.
5. `episodes.py` agrupa identidades candidatas y conserva todas las filas.
6. `observed_dates.py` aplica un campo temporal explícito o la jerarquía configurada y reutiliza
   `calendar.week_from_date` y `make_week`.
7. `coverage.py` evalúa declaraciones respaldadas y estados de observación.
8. `observed_panel.py` construye y verifica la grilla completa radio-semana.
9. `observed_reports.py` concilia registros y genera resúmenes seguros.
10. `observed_pipeline.py` coordina y escribe exclusivamente resultados privados.

## Clasificación y elegibilidad

La tabla usa el campo `classification_label` reconocido por Fase 2, nunca campos
de domicilio, texto clínico ajeno o una búsqueda de palabras dentro de la fila.
Normaliza Unicode, mayúsculas y espacios, conservando el resto de la etiqueta.
Las variantes con serotipo y nexo epidemiológico tienen entradas literales propias.
Una etiqueta nueva, contradictoria o no incluida queda `indeterminado`.

Las categorías canónicas son `confirmado`, `probable`, `sospechoso`, `descartado`
e `indeterminado`. Las correspondencias se versionan y no constituyen criterios
clínicos validados. El inventario privado permite revisar las etiquetas completas
y sus frecuencias; stdout sólo muestra categorías canónicas y conteos seguros.

La política conservadora excluye `descartado` y deja las demás categorías para
revisión. La exploratoria inicial admite sólo `confirmado`, excluye `probable`,
`sospechoso` y `descartado` por su definición de análisis, y deja `indeterminado`
pendiente. Incluir otras categorías exige configurar la política y cambiar su
versión; no se puede incluir `indeterminado` ni usar categorías contradictorias.
Una exclusión por escenario no equivale a un diagnóstico de descarte.

El alcance dengue de la entrega y las clasificaciones siguen sujetos a revisión
epidemiológica; una etiqueta genérica confirmada no acredita por sí sola evento,
episodio, cobertura ni caso clínicamente validado.

## Identidad y episodios

La clave de fila sigue siendo `source_id + sheet_ref + record_ref`. `record_ref`
identifica una fila en una versión del Excel, no una persona o un episodio.
`event_ref` es SHA-256 del identificador normalizado con el mismo criterio de
Fase 2 y alcance global de la entrega. Es pseudonimización privada, no anonimización.

Un ID no repetido queda `singleton_provisional`: puede aportar una fila al
escenario explícito, pero no demuestra identidad epidemiológica validada. Un ID
repetido queda `repeated_identifier_pending`; todas sus filas se excluyen del
conteo principal hasta revisión. Un ID ausente también queda pendiente.
Compartir coordenadas no agrupa episodios ni elimina registros.

`episode_resolutions` admite decisiones manuales por claves técnicas, con
`episode_ref`, `countable` y `evidence_ref`. Deben cubrir todo el grupo repetido y
declarar exactamente un representante por cada episodio revisado. Pueden separar
episodios distintos dentro del grupo o agrupar varias filas; el código no elige
la primera, la más reciente ni la de clasificación más favorable. Todas las
filas permanecen y los representantes no elegidos quedan auditados. La revisión
de identidad no valida automáticamente elegibilidad, fecha ni geografía.

## Fechas y calendario

La regla predeterminada usa únicamente `symptom_onset`, con los estados y fechas
ya interpretados en Fase 2. `date_hierarchy=null` mantiene ese comportamiento.
La [Fase 4.1](official-date-recovery.md) agrega una política explícita con el orden
inicio de síntomas, consulta médica, toma de muestra y notificación. Las fechas
alternativas no confirman el inicio real de síntomas; se marcan como aproximadas.
No se agregan formatos por conjetura, no se restan días y no se altera la fuente.
El código comprueba el corte del procesamiento, fechas futuras, período solicitado,
ambigüedad y rango del calendario. Apertura y revisión administrativa no son respaldos.

El calendario vigente es domingo-sábado, versión `ar-snvs-2020-2026-v1`.
`week_from_date` y `make_week` usan límites anuales oficiales explícitos;
`EpidemiologicalWeek` valida contra esa misma versión. La
[validación 2020–2026](official-calendar.md) documenta fuentes, contradicción
del cierre 2025 y reproducción de la regla anterior `sigard-iso-shift-v0`.
Esta corrección no regenera los paneles existentes ni amplía su cobertura.

El período inicial es 2020-01-01 a 2024-12-31. La grilla incluye las semanas
completas que lo intersectan, incluso sus etiquetas año-SE fuera de esos años
calendario. Las semanas de los extremos son ventanas parciales; no justifican
ceros. No se incorporan filas con fecha fuera del intervalo solicitado.

## Contrato del panel

La unidad es `provisional_eligible_source_records_radio_epidemiological_week`.
Los campos principales son:

- `radio_censal`: cadena de nueve dígitos, del universo de 263 radios.
- `fraccion_censal`: prefijo censal de siete dígitos, preparado para comparar
  posteriormente radio y fracción sin reconstruir identidades individuales.
- `anio_epidemiologico`, `semana_epidemiologica`, `fecha_inicio_semana`,
  `fecha_fin_semana`: año-SE y límites domingo-sábado.
- `registros_elegibles_provisionales`: entero nullable; una ausencia permanece null.
- `estado_observacion`, `cobertura_temporal`, `cobertura_declarada`,
  `evidencia_cobertura`, `ventana_semanal_parcial`: semántica y respaldo del conteo.
- `registros_asignacion_incierta`, `tipos_geocodificacion`, `fuentes_con_registros`:
  calidad y fuentes de las filas incorporadas.
- `registros_pendientes_posibles`: pendientes que podrían afectar esa celda.
- Versiones de transformación, clasificación, elegibilidad, identidad, fecha,
  cobertura y asignación geográfica; estado provisional y disponibilidad histórica.
- `validado=false`, `apto_entrenamiento=false`.

El panel no incluye IDs de evento, referencias de fila, domicilios ni posiciones.
La auditoría privada contiene referencias opacas, decisiones, fecha, candidato,
fracción y diagnóstico espacial. Tampoco copia nombres, documentos, direcciones
ni coordenadas exactas. La procedencia global, versiones de fuentes, huellas,
decisión geográfica y opciones se conservan en `metadata.json`.

Desde Fase 4.1 conserva también `fecha_inicio_sintomas_original`, su tipo de valor,
`fecha_referencia`, `tipo_fecha_referencia`, `fecha_aproximada` y
`motivo_seleccion_fecha`, más los motivos de rechazo de los campos precedentes.
Las versiones nuevas se escriben en carpetas independientes; el panel anterior
permanece como referencia reproducible y se compara por claves técnicas y conteos.

## Ceros, ausencias y cobertura parcial

Las declaraciones `coverage` necesitan `start` domingo, `end` sábado,
`state=complete|partial|outside`, `evidence_ref` y, opcionalmente, `radio_ids`.
Sin `radio_ids`, cubren los 263 radios. No se permiten declaraciones superpuestas
ni radios ajenos. No se infiere cobertura por años de archivos o fechas extremas.

- `registros_observados`: hay filas incorporadas. Con cobertura desconocida, el
  número es un conteo observado bajo la política, no un total completo garantizado.
- `cero_con_cobertura_comprobada`: cero únicamente con evidencia de cobertura
  completa, semana íntegra y sin pendientes potencialmente relevantes.
- `sin_informacion_suficiente`: null cuando no existe respaldo para un cero.
- `cobertura_parcial`: conteo positivo disponible o null; nunca cero inferido.
- `fuera_de_cobertura`: null respaldado por declaración explícita. Si hay
  registros que la contradicen, el constructor se detiene para revisión.

Un pendiente sin fecha puede afectar todas las semanas de su radio candidato;
sin radio puede afectar todos los radios de su semana; sin ambos, toda la grilla.
Esto impide que la evidencia de cobertura produzca ceros ignorando esas filas.
Los conteos de pendientes por celda **no son sumables** entre celdas: una misma
fila puede afectar varias. No es una asignación espacial/temporal artificial.
Los totales únicos de pendientes se obtienen de la conciliación de filas.

## Conciliación e integridad

Cada fila tiene un solo desenlace: `included`, `excluded` o `pending`. Se verifica
que los tres sumen las filas iniciales y que la suma del panel coincida con las
incluidas. Los motivos pueden solaparse y se reportan como indicadores separados.
No se cuenta más de una vez una clave de fila o un episodio candidato contable.

El código compara huellas antes y después de ejecución para las fuentes,
derivados de Fases 2/3, cartografía, modelos, artefactos científicos y datos públicos
de frontend. Los modos conservador y exploratorio tienen subcarpetas distintas;
se comprueba también que ejecutar un modo no sobrescriba el otro. No hay commits,
publicación, cambios de backend/frontend ni ejecución de entrenamiento.

## Productos privados

Dentro de `data/interim/official/observed/conservative/` o `exploratory/`:

- `panel.parquet`: grilla agregada con enteros nullable.
- `records_audit.parquet`: una fila por registro original, sin eliminar pendientes.
- `reconciliation.json` y `.md`: estadísticas seguras y explicación de resultados.
- `classification_inventory.private.json`: etiquetas completas y conteos seguros
  para revisar las correspondencias localmente; no se imprime en Codex.
- `metadata.json`: procedencia, período, versiones, reglas y límites.
- `integrity_manifest.json`: huellas de entradas y salidas.

Los Parquet son privados y conservan cantidades exactas para reproducibilidad.
Los reportes suprimen cantidades positivas menores de cinco, no presentan filas
ni desgloses epidemiológicos por radio. Las exclusiones Git/Docker existentes
cubren toda esta carpeta. No se escribe en `data/processed/` ni en rutas públicas.

## Auxiliares y ausencia de información futura

No se incorporó ninguna variable auxiliar real. `observed_auxiliary.py` prepara
una unión de tabla larga con `radio_censal`, `fecha_inicio_semana`, `name`,
`value`, `observed_through`, `available_on` y `source_ref`. Requiere claves válidas,
valores únicos y completos, nombres admitidos por `FeatureValue` y disponibilidad
no posterior al sábado de la semana de origen. Conserva las fechas y procedencia
en columnas específicas de cada variable. Rechaza coordenadas, variables objetivo,
datos futuros, sobrescrituras y radios/semanas ajenos.

Población, densidad, hogares, viviendas, clima e historia podrían vincularse
después de comprobar fuentes y fechas. El censo 2022 no debe presentarse como
información disponible en 2020. No se crea un historial sustituyendo null por cero
y no se usa el resultado de la semana siguiente como predictor.

No se reconstruyó disponibilidad histórica de registros o clasificaciones. El
panel queda **retrospectivo** y no acredita una simulación de predicción futura.
Antes de entrenar se debe aprobar el tratamiento de disponibilidad, cobertura,
episodios, clasificaciones y etiquetas, manteniendo el escenario provisional
separado del panel epidemiológico validado.

## Pruebas ficticias

```powershell
.\ml\venv\Scripts\python.exe -B -m pytest ml/tests/test_official_contracts.py ml/tests/test_official_ingestion.py ml/tests/test_official_quality.py ml/tests/test_official_spatial.py ml/tests/test_official_observed.py -p no:cacheprovider --basetemp=ml/.tmp/phase4-check
```

Elegir una carpeta temporal nueva si otra ejecución dejó conflictos de permisos.
Las pruebas cubren correspondencias exactas, modo conservador, opción exploratoria,
IDs repetidos y ausentes, resoluciones explícitas, fechas y calendario, todos los
estados de cobertura, pendientes, ceros, conciliación, privacidad, reejecución,
integridad de fuentes y salidas anteriores, rama y fugas temporales en auxiliares.
