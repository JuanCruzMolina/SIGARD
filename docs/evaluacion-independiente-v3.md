# Evaluación independiente de V3 congelada

Este procedimiento queda preparado, sin ejecutarlo sobre otra entrega ni solicitarla.
Opera sólo en local y conserva V1/V2/V3 y A/B. No entrena, selecciona otro modelo,
ajusta hiperparámetros ni habilita producción. El candidato principal por horizonte
es el `best_ml` del manifiesto V3; los demás se informan como secundarios.

## Preparación y frontera de confianza

El custodio recibe la nueva entrega autorizada y prepara **agregados derivados**,
con el territorio operativo de 256 radios, las máscaras de calidad y la semántica
de V3. No pasar originales identificables a este programa. Reutilizar las reglas
de [preparación existentes](principal-count-input-contract.md) y la implementación
congelada `v3.feature_frame`; la preparación revisada debe acreditar sus valores
y procedencia. Este evaluador recibe el panel ya preparado: no es un nuevo
importador epidemiológico y no valida por sí solo el significado de las fuentes.

La preparación debe separar físicamente features y etiquetas. El analista no abre
etiquetas hasta sellar todas las predicciones. Los archivos viven en una carpeta
nueva bajo `data/interim/official/independent_.../`, excluida de Git. No reemplazar
el snapshot histórico ni los paquetes de entrenamiento. El permiso debe nombrar
la entrega exacta; la declaración histórica de las cinco fuentes no autoriza
automáticamente una entrega nueva.

Cada permiso JSON contiene `status="approved"`, `purpose` (`independent_features`
o `independent_labels`), `payload_sha256`, `source_version`, `authorization_basis`
(`project_owner_declared_provision` o `external_provider_permission`),
`reviewer_ref`, `authorization_ref`, `limits`, `decided_on` ISO,
`training_embargo=true`, `previously_used_or_reviewed=false`, `local_only=true`.
La declaración debe provenir del responsable competente. SHA-256 acredita
integridad, no firma institucional, autenticidad ni ausencia de exposición previa.
No se exige nuevamente P1–P6 para el experimento de agregados; tampoco se acredita
con ello el objetivo epidemiológico definitivo.

## Contrato del panel de features

El JSON de entrada tiene:

- `schema="sigard-v3-independent-panel-1"`, `model_version="sigard-principal-v3-experimental"`.
- `territory_version="la-rioja-46014010-256-v1"`, `unit="snapshot_record_count"`,
  `target_definition="principal-confirmed-snapshot-2"`.
- `feature_rule="frozen-v3-origin-closed-1"`, `feature_order` exactamente igual a
  `v3.FEATURES`, `radios` exactamente iguales a los del artefacto congelado.
- `source_version`, `availability_evidence_ref`, `preparation_review_ref` y
  `zero_meaning="no_record_in_filtered_snapshot_not_epidemiological_absence"`.
- `rows`: una fila por `radio_id`, `horizon` (1, 2 o 4), `origin_week`,
  `target_week`, `cutoff_date`, `features`, `lineage`. Deben estar los tres
  horizontes y todos los radios por origen. Las fechas son ISO `YYYY-MM-DD`;
  origen/objetivo dominicales, objetivo = origen + horizonte y corte = sábado
  del origen, ya cerrado. No se incluyen etiquetas en este archivo.

`features` es un diccionario de las 17 variables V3, con números finitos o null.
`lineage` tiene las mismas claves. Para una feature null su procedencia es null;
para una conocida indica `max_event_week`, `available_on`, `source_ref`.
Se rechaza información de eventos posteriores al origen, disponibilidad posterior
al corte y rezagos fechados después de su semana admisible. Debe acreditarse el
cierre completo de los agregados. No inferir disponibilidad histórica a partir de
la fecha de extracción. La revisión de preparación vincula cada variable con la
transformación congelada; las fechas declaradas no prueban por sí solas que su
valor fue calculado correctamente.

El programa exige orígenes y objetivos posteriores al último período observado
registrado y modelos ajustados antes de cada origen. El custodio además comprueba
que el período no apareció en decisiones o revisiones previas, incluso fuera de
los manifiestos de entrenamiento. Cambios de territorio, definición, unidad o
semántica requieren resolver compatibilidad antes de evaluar, sin adaptar el
modelo mirando sus resultados. Desconocidos siguen null; no se fabrican ceros.

## Sellado y evaluación

Con el entorno ML congelado compatible, desde la raíz:

```powershell
.\ml\venv\Scripts\python.exe -B -m sigard_ml.forecasting.independent_evaluation seal --features data/interim/official/independent_ENTREGA/features.private.json --authorization data/interim/official/independent_ENTREGA/features-permission.private.json --output data/interim/official/independent_ENTREGA/sealed
```

`seal` verifica permisos e integridad antes de interpretar el panel, comprueba
compatibilidad con la implementación V3 congelada y carga únicamente los joblib
locales de confianza. Ejecuta los tres candidatos y los tres baselines **sin
reentrenarlos**. Guarda predicciones, huellas, selección previa, umbrales aprendidos
en desarrollo y un recibo `seal.private.json`. No recibe rutas de etiquetas.
Conservar el recibo también bajo custodia independiente para detectar reemplazos;
el sello local es una evidencia de integridad, no una certificación criptográfica
del momento de generación. La separación entre comandos es operativa, no otra
ronda de investigación.

Después, el custodio entrega el JSON de etiquetas con el mismo `schema`, `unit`,
`territory_version`, `target_definition`, `source_version` y `seal_sha256` del recibo.
Sus `rows` tienen `radio_id`, `target_week`, `target_count`, `state`,
`available_on`, `source_ref`. Debe cubrir exactamente la unión de claves selladas
(compartidas entre horizontes), incluyendo desconocidos explícitos:

- `state="usable_snapshot"`: entero no negativo y disponibilidad desde el cierre
  del objetivo hasta la fecha actual. Cero conserva exclusivamente su significado
  de ausencia de registro en el snapshot filtrado autorizado.
- `state="unknown"`, `"pending"` o `"temporal_problem"`: `target_count=null`.
  No se exige disponibilidad conocida para un desenlace desconocido.

```powershell
.\ml\venv\Scripts\python.exe -B -m sigard_ml.forecasting.independent_evaluation score --labels data/interim/official/independent_ENTREGA/labels.private.json --authorization data/interim/official/independent_ENTREGA/labels-permission.private.json --sealed data/interim/official/independent_ENTREGA/sealed
```

`score` rechaza alteraciones y evaluaciones repetidas; aplica la misma máscara
utilizable a todos los métodos, exige al menos cuatro semanas con etiquetas y
produce `evaluation.private.json`, `report.private.md`, `completion.private.json`.
Incluye MAE/RMSE/sesgo, diferencias e intervalos pareados por bloques de semanas,
victorias, años, colas y semanas altas con umbrales históricos, sensibilidad a
retirar las tres semanas de mayor ganancia y a bloques de 1/3/4/8 semanas.
La estabilidad futura se describe en tres bloques cronológicos, sin ajuste de
modelos en ellos. Cuatro semanas permiten emitir el diagnóstico mínimo del
protocolo, pero no acreditan suficiencia para una confirmación externa.

El informe contrasta el candidato ya designado con ambas persistencias y muestra
las condiciones numéricas congeladas. Ausencia de semanas altas o de colas no se
considera éxito. Los demás candidatos no sustituyen al principal según los nuevos
resultados. No se aplican correcciones de selección a los intervalos exploratorios;
t+1 es principal y t+2/t+4 complementarios. La etiqueta automática puede ser
«mejora preliminar» o «mejora no demostrada»; «mejora respaldada» requiere revisar
independencia, soporte temporal y calidad de la evidencia con el responsable.

El embargo de entrenamiento permanece **activo incluso al terminar**. Este flujo
no entrega archivos al entrenador ni modifica modelos; tampoco impide que otra
herramienta externa viole el embargo. El responsable conserva los nuevos datos
fuera de paquetes de entrenamiento hasta cerrar y registrar su evaluación
independiente. Cualquier incorporación posterior necesita una decisión separada.

## Comprobación técnica

`ml/tests/test_thesis_validation.py` usa exclusivamente radios y valores ficticios,
dobles de modelos sin `fit`, y almacenamiento temporal. Comprueba recorrido de
sellado/evaluación, desconocidos, integridad, embargo, incompatibilidades y fuga
temporal. No constituye una evaluación epidemiológica nueva.
