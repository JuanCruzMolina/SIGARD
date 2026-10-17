# SIGARD Fase 4.2: cobertura, ceros y objetivo semanal

La [Fase 4.3](official-universe.md) revisa el universo y prepara declaraciones
de cobertura asumida sin modificar esta fase ni regenerar sus paneles. Sus
capacidades negativas condicionales no son ceros generados ni evidencia de
completitud temporal.

Esta fase consume los paneles estricto y ampliado y sus auditorías privadas de
Fase 4.1. No cambia elegibilidad, identidad, fechas ni geografía; no relee las
filas clínicas de Excel, no geocodifica y no entrena. Conserva la grilla de
263 radios y el calendario domingo-sábado.

## Procedencia y cobertura

`provenance_declaration` conserva declaraciones sobre entrega, selección manual
y criterio territorial. Es una declaración de procedencia, no una verificación
automática de continuidad de vigilancia. `selection_geographic_basis` distingue
`patient_residence`, `notifying_establishment` y `unknown`; no reemplaza el rol de
las coordenadas de Fase 3. Filtrar Capital no demuestra por sí solo residencia
del paciente ni ubicación de exposición. Las clasificaciones existentes siguen
bajo las reglas de Fase 4.1 y se incluyen en un inventario para reconciliar la selección manual.

`source_period_declarations` permite registrar intervalos solicitados por fuente,
con `source_id`, `start`, `end`, `date_basis` y `declaration_ref`. Su ausencia se
informa como período solicitado no documentado. No se usa el nombre del archivo
para suplirlo. Estas declaraciones tampoco activan ceros.

El inventario deriva los intervalos observados de los normalizados autorizados
y las auditorías anteriores, con huellas verificadas. Separa fechas de síntomas,
muestras y referencias utilizadas, semanas representadas, semanas sin fechas
entre extremos y solapamientos entre fuentes. Un extremo observado, una semana
sin filas o un solapamiento no prueban cobertura ni duplicidad epidemiológica.
La lista de semanas sin registros no es una lista de semanas sin casos.

## Configuración editable

El ejemplo no sensible está en `ml/configs/official.coverage.example.json`.
Guardar configuraciones reales y evidencias dentro de `data/interim/official/`.
El manifiesto usado en la ejecución real es un archivo privado separado de las
salidas; su hash queda protegido durante la ejecución.

`coverage_declarations` contiene intervalos de estado `complete`, `partial` o
`unknown`, con una referencia de declaración, radios opcionales y los paneles
temporales a los que se aplica. Los intervalos son inclusivos y deben constituir
una decisión única por radio y semana. Un intervalo que sólo cubre parte de una
semana la deja parcial, aunque declare completitud.

Ejemplo **ficticio**, que no autoriza cobertura de la entrega real:

```json
{
  "start": "2024-01-07",
  "end": "2024-01-27",
  "state": "complete",
  "date_panels": ["strict", "expanded"],
  "declaration_ref": "fictional_explicit_completeness_statement"
}
```

No aplicar una extracción definida por notificación al calendario de síntomas
o muestras sin revisar ese alcance. `date_panels` hace explícita esa decisión.
Cambiar intervalos o políticas requiere actualizar `coverage_version` para
identificar la revisión; la configuración exacta y sus hashes quedan conservados.

`coverage_verifications` se mantiene separada. Cada resolución documentada exige
intervalo, estado, `date_panels`, `verification_ref`, `geographic_basis=patient_residence`,
`rules_verified` para elegibilidad, identidad, política de fechas, alcance territorial
y asignación espacial, y `evidence_files` con ruta privada y SHA-256.
Las evidencias deben respaldar la resolución sobre continuidad, extracción y
selección. No basta declarar entrega completa ni marcar una bandera sin respaldo.
El programa verifica autorización, estructura e integridad de los archivos; sus
hashes no demuestran automáticamente la verdad epidemiológica de la resolución.

`zero_policy.enabled=false` desactiva todos los ceros.
`allow_declared_complete_in_exploratory=false` desactiva los basados sólo en
declaraciones. No se permite desactivar el bloqueo por pendientes o semana parcial.

## Dos escenarios de cobertura por cada política de fechas

- **Conservador:** conserva positivos provisionales; genera cero sólo con cobertura
  comprobada bajo una resolución documentada y reglas revisadas.
- **Exploratorio:** también permite cobertura completa declarada explícitamente;
  esos ceros se marcan `cero_provisional=true` y `cero_declarado_provisional`.

Estos escenarios califican **cobertura**, no sustituyen los modos de elegibilidad
de Fase 4. Mantienen los mismos registros incorporados por Fase 4.1, también en
el escenario conservador de cobertura. Todos los conteos siguen siendo provisionales.

Un cero requiere una semana completa dentro del período, ausencia de registros
elegibles incorporados y ausencia de pendientes que puedan modificar esa celda.
Cobertura parcial documentada prevalece sobre una declaración de completitud.
Si no hay evidencia suficiente para cero, `casos_observados` permanece null.
Un conteo positivo conocido se conserva incluso con cobertura desconocida: es
evidencia de registros incorporados y no garantiza el total epidemiológico completo.

Se reutiliza `observed_panel.pending_counts`. Un pendiente sin fecha puede afectar
todas las semanas de su radio candidato; sin radio, todos los radios de su semana;
sin ambos, toda la grilla. No se restringe su intervalo al año del archivo ni a
las fechas de otros registros. Esos conteos por celda no son sumables entre celdas.

## Contrato del panel y objetivo

Campos solicitados:

- `radio_censal`, `anio_epidemiologico`, `semana_epidemiologica`: unidad radio-semana.
- `casos_observados`: entero nullable de registros elegibles provisionales,
  no casos únicos validados. El nombre se mantiene por el contrato solicitado.
- `estado_cobertura`: `desconocida`, `parcial`, `parcial_por_pendientes`,
  `completa_comprobada` o `completa_declarada_provisional`.
- `objetivo_semana_siguiente`: 1 si existe un registro elegible provisional en
  la semana exacta siguiente; 0 si su conteo es cero bajo la política explícita;
  null si es desconocido o está fuera de la grilla disponible.
- `objetivo_valido`: true exclusivamente cuando el resultado binario es conocido.
  No significa validación epidemiológica ni disponibilidad histórica del registro.
- `escenario`: `conservative` o `exploratory`; `panel_fechas`: `strict` o `expanded`.
- `calidad_geografica`: calidad del candidato heredado; no acredita residencia exacta.

Además conserva límites de semana, cobertura declarada y comprobada con referencias
separadas, pendientes, incertidumbre espacial, versiones, conteos con fecha aproximada,
`cero_provisional`, `objetivo_provisional` y `objetivo_con_fecha_aproximada`.
Una muestra no se convierte en inicio de síntomas. Las referencias alternativas
pueden desplazar la semana; no se estiman retrasos para corregirlas.

`weekly_targets.attach_next_week_target` cruza por radio y fecha de inicio + siete
días, no desplaza a la siguiente fila disponible. Un hueco semanal no salta a un
período futuro. No se etiqueta una observación desconocida como negativa. La última
semana no tiene objetivo conocido sin una semana siguiente disponible.

`origin_count_predictors` sólo proyecta identificadores temporales/territoriales
y conteo del origen; no incluye objetivo, conteo futuro ni calidad del objetivo.
Es una proyección retrospectiva para revisión, no un dataset habilitado para entrenar.
La disponibilidad histórica de registros y clasificaciones no se reconstruye.
Todos los paneles mantienen `validado=false` y `apto_entrenamiento=false`.
El objetivo binario oficial preparado no cambia el objetivo ni modelos del MVP v0.1.

## Diagnóstico de viabilidad

Se informan observaciones y etiquetas por separado, positivos/negativos/desconocidos,
semanas con cobertura suficiente por celda y para todos los radios, radios sin positivos,
distribución semanal, actividad por año epidemiológico y ejemplos con conteo de origen
conocido. Los umbrales editables de actividad son descriptivos: no constituyen requisitos
validados de tamaño muestral ni habilitan entrenamiento.

`evaluation_start` debe ser domingo. La partición diagnóstica admite en entrenamiento
sólo objetivos cuya semana termina antes del inicio de evaluación, y en evaluación
orígenes desde ese inicio. Excluye el origen cuyo objetivo cruza el límite, conservando
por separado positivos y negativos. No usa particiones aleatorias ni calcula métricas.
Sin ambas clases respaldadas no es viable entrenar/evaluar un clasificador binario.
La disponibilidad histórica y las reglas epidemiológicas requieren revisión incluso
si existieran ambas clases en una partición retrospectiva.

## Ejecución y productos privados

```powershell
.\ml\venv\Scripts\python.exe -B -m sigard_ml.official.coverage_pipeline --config data/interim/official/access.private.json --coverage-config data/interim/official/observed/coverage_042.private.json
```

Se ejecuta exclusivamente en `entrenamiento-ML`. Verifica permisos y manifiestos de
Fase 4.1, normalizados y claves de auditoría. No regenera fases anteriores. Escribe:

- `data/interim/official/observed/coverage_042/strict/conservative/panel.parquet`.
- `data/interim/official/observed/coverage_042/strict/exploratory/panel.parquet`.
- `data/interim/official/observed/coverage_042/expanded/conservative/panel.parquet`.
- `data/interim/official/observed/coverage_042/expanded/exploratory/panel.parquet`.

La raíz incluye `coverage_inventory.private.json`, `viability.private.json`,
`viability.md`, `configuration.private.json`, `metadata.json` e `integrity_manifest.json`.
Los JSON privados conservan cifras exactas, intervalos y códigos censales para
revisión local; el texto suprime cantidades positivas menores de cinco.
Las huellas protegen Excel, normalizados, Fases 3/4/4.1 y artefactos científicos.
Las carpetas están excluidas de Git y Docker público. No se publica ni entrena.

## Pruebas ficticias

```powershell
.\ml\venv\Scripts\python.exe -B -m pytest ml/tests/test_official_contracts.py ml/tests/test_official_ingestion.py ml/tests/test_official_quality.py ml/tests/test_official_spatial.py ml/tests/test_official_observed.py ml/tests/test_official_date_recovery.py ml/tests/test_official_coverage.py -p no:cacheprovider --basetemp=ml/.tmp/phase42-check
```

Se prueban cobertura completa/parcial/desconocida, respaldo privado, declaraciones,
ceros inválidos, pendientes sin fecha o identidad, límites y cambios de año,
objetivos 0/1/null, huecos de semana, aislamiento del objetivo respecto a predictores,
corte cronológico, autorización, integridad y reproducibilidad. No se usan filas reales.
