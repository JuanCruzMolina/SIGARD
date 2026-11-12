# Entrenamiento histórico experimental separado

La solicitud expresa del responsable del 28/10/2026 autoriza nuevas versiones
privadas de A/B y, cuando cambia su muestra de ajuste, de los candidatos V3.
No reemplaza los permisos ni artefactos anteriores. Las salidas no se incorporan
al frontend, backend, recursos públicos o registro de consulta por fecha.

`official/spatial_ml/historical_expansion.py` prepara A/B reutilizando las
etiquetas y los siete predictores A del escenario existente. No ingiere fuentes.
Preserva positivos provisionales, negativos experimentales autorizados y
desconocidos. La historia B es presencia binaria en t−1…t−4 por fecha exacta,
con los cuatro indicadores originales y NaN nativos. Se rechazan claves
duplicadas, grillas incompatibles, negativos sin cobertura del escenario,
calendario distinto y contexto estático variable. No deduplica episodios sin
evidencia ni elimina filas sólo por falta de antecedentes.

El conjunto ampliado mantiene los 263 radios A/B y todos sus períodos
compatibles. Los años históricos que sólo tienen positivos no se convierten en
cohortes con ambas clases. El conjunto combinado puede ajustarse cuando hay
ambas clases, pero su distribución de etiquetas depende de la selección y de la
cobertura. Los supuestos de cero no se extienden automáticamente a otros años.
2022 conserva su tratamiento separado mientras no exista una resolución de
clasificación compatible respaldada por la evidencia local.

El protocolo privado fija los mismos hiperparámetros y umbral antes de ajustar.
Evalúa bloques cronológicos, purgando todo objetivo que no haya terminado antes
del primer origen evaluado. Compara con los originales congelados, un control
de configuración fija que sólo usa entrenamiento de 2024 y referencias de
prevalencia/persistencia. Los resultados de 2024 ya examinados son exploratorios;
no seleccionan variables, parámetros, umbrales ni nuevos algoritmos. La ausencia
de ambas clases se informa sin inventar métricas de discriminación histórica.

Después de guardar la evaluación, el ajuste final usa todas las etiquetas
compatibles hasta el corte histórico. Incluye las antiguas reservas y purgas
entre particiones: ya no conserva una prueba independiente en ese historial.
Esta ampliación no acredita mejora de generalización ni habilita producción.

V3 mantiene sus 256 radios, cantidades de registros del snapshot, máscaras,
reglas de predictores y horizontes t+1/t+2/t+4. Sólo corresponde un nuevo ajuste
si hay etiquetas admisibles adicionales respecto del ajuste final anterior;
pueden proceder de reservas anteriores ahora expresamente autorizadas. No se
cambian máscaras para recuperar desconocidos ni se reutilizan etiquetas A/B.
Se conservan los tres candidatos y las referencias de persistencia existentes,
sin una nueva selección sobre la comparación ya vista.

Los artefactos y el informe viven en carpetas privadas versionadas bajo
`ml/artifacts/official/` y `data/interim/official/`. El protocolo registra
autorización, entorno, entradas, hashes, features, períodos, particiones y
límites. Los modelos se verifican por serialización y comparación de hashes;
los originales, predicciones y métricas previas se conservan íntegros.

La nueva A es compatible con la transformación y validación del estimador de
la consulta por fecha, pero el servicio fija rutas, versiones y hashes del
modelo original. Habilitar otra versión requiere una tarea separada de registro
y política. B conserva el mismo esquema y necesita una fuente reciente
compatible, autorizada y disponible en origen; más entrenamiento histórico no
produce esos antecedentes. V3 tampoco incorpora automáticamente historia,
clima o cobertura de 2025/2026. Capacidad de inferencia no acredita validación.

Regresiones ficticias, sin datos oficiales:

```powershell
.\ml\venv\Scripts\python.exe -B -m pytest ml/tests/test_historical_expansion.py ml/tests/test_ab_date_inference.py -p no:cacheprovider
```

La ejecución real necesita el permiso privado específico y los derivados
verificados; las pruebas ficticias no constituyen permiso de entrenamiento.
