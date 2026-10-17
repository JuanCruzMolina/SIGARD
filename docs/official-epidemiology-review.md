# SIGARD Fase 5B.1: decisiones epidemiológicas y cobertura

Versión `official-epidemiology-decision-review-0.5b.1`. Prepara un dossier y una
plantilla privada para el responsable a partir de las cinco fuentes autorizadas,
sus normalizados y los diagnósticos preservados de Fases 4.2, 4.3 y 5B. No
reingiere, abre Excel, geocodifica, calcula features, cambia el Modelo A, entrena,
modifica clasificaciones o materializa negativos.

## Ejecución y privacidad

```powershell
.\ml\venv\Scripts\python.exe -B -m sigard_ml.official.epidemiology_review_pipeline --config ml/configs/official.epidemiology-review.example.json
.\ml\venv\Scripts\python.exe -B -m pytest ml/tests/test_official_epidemiology_review.py -p no:cacheprovider --basetemp=ml/.tmp/phase5b1-check
```

Se exige `entrenamiento-ML`, autorización de inspección/procesamiento para todas
las fuentes, manifiestos válidos y destino nuevo privado directamente dentro
de `data/interim/official/`. El ejemplo usa `epidemiology_review_05b1_v1`.
Para repetir debe elegirse otro nombre; se rechazan sobrescrituras y rutas
públicas. Se comparan hashes de fuentes, paneles, datos y modelos antes/después.
No se requieren documentos externos para generar el diagnóstico: su ausencia
se informa como evidencia no disponible, sin completar decisiones en nombre del
responsable. Los informes, inventarios y plantillas permanecen fuera de Git/Docker.

## Evidencia epidemiológica y territorial

`epidemiology_review.py` cruza exclusivamente claves técnicas de las auditorías
preservadas con `classification_label` de los normalizados autorizados. No
reinterpreta etiquetas ni aplica una nueva correspondencia. Inventaría valores
literales completos, frecuencias, categorías y desenlaces por fuente; identifica
las columnas originales desde el informe de calidad y sus encabezados desde
la inspección estructural preservada. Los campos adicionales no proyectados
permanecen explícitamente desconocidos, sin reabrir los libros.

El diagnóstico distingue:

- Confirmación registrada, con criterio histórico todavía sin documentar.
- Categorías sospechoso/probable que no afirman confirmación, pero tampoco
  prueban ausencia de enfermedad.
- Descarte registrado para una fila, que no equivale a negativo radio-semana.
- Clasificación ausente/no mapeada, cuya confirmación permanece desconocida.

Se documenta el motivo mecánico de las banderas: `evaluate_eligibility` asigna
`epidemiological_eligibility_validated=False` y `prepare_records` asigna
`epidemiological_identity_validated=False`; la conjunción usada por Fase 5B no
puede validarse automáticamente con esas salidas. El diagnóstico localiza las
asignaciones mediante AST y conserva líneas/hashes. Cero banderas no es prueba
de que todos los registros rotulados confirmados sean incorrectos.

El responsable debe revisar la definición histórica de dengue, el diccionario de
evento, los valores literales del filtro y el criterio de confirmación aplicable.
No se impone laboratorio como única forma de confirmación: cualquier criterio
admitido, incluido nexo cuando corresponda, debe quedar documentado y referido
a su contexto histórico. La fuente 2022 se revisa por su identificador autorizado;
no se infiere confirmación ni año de observación desde nombres de archivo.

La revisión territorial reutiliza conteos de provincia/departamento de residencia
de Fase 4.3. Una concordancia total con La Rioja–Capital es compatible con el
filtro, pero no reconstruye qué columnas u operaciones se usaron manualmente.
Se requiere procedimiento, columnas/valores, fecha/operador, orden de filtros y
conciliación con la exportación previa. No se equipara establecimiento notificador
con residencia ni se decide residencia desde coordenadas.

## Cobertura y pendientes

Las propuestas reutilizan exactamente los intervalos candidatos por fuente,
política y tipo de fecha de Fase 4.3, con límites y observaciones de Fase 4.2.
Conservan `proposal_not_declaration`, confianza de completitud `none`, justificación
documental pendiente y materialización deshabilitada. Fuentes sin intervalo
elegible quedan sin propuesta fechada, con revisión de clasificación/universo
pendiente. Una ventana sin semana completa también queda identificada.

Para cada intervalo se detallan criterio temporal, criterio de confirmación por
validar, residencia propuesta, incertidumbres y celdas bloqueadas por pendientes.
Las capacidades se calculan sin asignar cero y no se suman sobre intervalos
superpuestos. El responsable puede aceptar/rechazar/corregir propuestas, pero
debe declarar fechas propias y documentar extracción, corte, filtros,
completitud, limitaciones y confianza. No se extiende ninguna ventana hasta
diciembre de 2024 por ser el límite configurado.

Un pendiente sin fecha conserva todo el período posible de su radio candidato;
si no tiene radio, mantiene alcance territorial amplio. Los pendientes por
identidad y elegibilidad se contabilizan con sus intersecciones y no se suman
entre celdas como registros únicos. Se concilian con Fase 4.3. No se eliminan
pendientes para habilitar ceros. Tampoco es obligatorio resolverlos todos si las
celdas afectadas permanecen desconocidas y fuera de los negativos autorizados.

La toma de muestra sigue siendo aproximación temporal, comparada con la política
estricta y la evidencia de demoras ya calculada; no se restan retrasos imputados.
La asignación geográfica aproximada ya fue aceptada por el proyecto. No se exige
certeza domiciliaria absoluta o nueva geocodificación: su incertidumbre se conserva
como limitación, sin presentar puntos de infección reales.

## Dossier, plantilla y habilitación futura

`decision_dossier.private.md` integra diagnóstico por fuente, clasificación 2022,
residencia, intervalos exactos candidatos, pendientes, decisiones y requisitos.
`decisions.template.private.json` deja sin completar responsable/firma, decisiones
por etiqueta, procedimiento territorial, fechas declaradas, evidencias, confianza
y autorizaciones. Los límites candidatos se incluyen únicamente como sugerencias:
`declared_start/end` permanecen null y `coverage_declarations` vacío.

Se distinguen dos rutas, sin modificar la configuración del Modelo A:

1. Experimento retrospectivo: decisiones epidemiológicas/territoriales documentadas,
   cobertura respaldada o escenario asumido expresamente autorizado, pendientes
   preservados, ambas clases suficientes en cortes cronológicos purgados,
   contexto censal retrospectivo reconocido y autorización posterior de entrenamiento.
2. Backtest operativo: además, disponibilidad histórica censal/territorial,
   maduración/disponibilidad de etiquetas en cada corte y respaldo punto en el
   tiempo para un baseline de persistencia; si no existe, abstenerse o usar el
   baseline de prevalencia del entrenamiento.

El Modelo A no usa rezagos: no se exige una historia de features epidemiológicas
que no forma parte de su entrada. Esto no elimina los requisitos de cobertura,
etiquetas y evaluación temporal ni valida automáticamente el contexto censal.
Una firma del documento no dispara procesamiento, negativos o entrenamiento.

Las salidas adicionales son inventario de clasificación agregado, revisión de
pendientes por claves opacas (sin nombres, documentos, domicilios o posiciones),
propuestas de cobertura, diagnóstico JSON, configuración, metadatos y manifiesto
SHA-256. El hash de la configuración del Modelo A demuestra su conservación.

Las pruebas ficticias cubren distinción de evidencia, banderas conservadoras,
alineación de registros, consistencia territorial, intersecciones de pendientes,
intervalos exactos y no autorizados, documentos externos ausentes, plantilla
sin firmar, reproducibilidad e integridad/permisos. La integración bloquea
explícitamente lectura de Excel, cálculo de features y entrenamiento.
