# SIGARD Fase 4.1: recuperación temporal privada

Esta fase amplía el panel exploratorio existente mediante fechas alternativas
identificadas. No modifica los modelos, backend o frontend, no repite geocodificación,
no entrena ni publica. El resultado sigue siendo retrospectivo, provisional y privado.
La unidad permanece registro elegible provisional por radio censal y semana epidemiológica.

## Política editable

`observed_settings.py` conserva `date_hierarchy=null`: procesamiento estricto
predeterminado sin respaldo. La jerarquía completa es:

1. `symptom_onset`: inicio de síntomas.
2. `consultation_on`: consulta médica.
3. `sample_on`: toma de muestra.
4. `notified_on`: notificación.

Se admiten prefijos de ese orden, incluido sólo inicio de síntomas. Para el
módulo principal se admite además la opción explícita `symptom_onset, sample_on`
(`PRINCIPAL_DATE_HIERARCHY`), con su propia versión de regla. No altera el orden
histórico predeterminado ni sus salidas. En esa opción no se sustituye un inicio
interpretable futuro/fuera de ventana por muestra para hacer entrar la fila.
Cambiar la
política exige una versión de fecha propia y una carpeta versionada independiente.
El ejemplo `ml/configs/official.date-recovery.example.json` contiene la jerarquía
completa y puede editarse manualmente. El comparador sólo permite modificar fechas,
su versión y la salida: reutiliza las demás reglas de la referencia anterior.

La primera fecha válida dentro del período y corte es la referencia. Fechas ausentes,
no interpretables, imposibles, ambiguas, futuras o fuera del período se rechazan
individualmente y se pasa al campo siguiente. Sin fecha válida, la fila queda
pendiente si las otras reglas no determinan una exclusión. Una exclusión por
elegibilidad o por representante de episodio continúa siendo una exclusión.
Ningún problema de identidad, elegibilidad o geografía se resuelve con una fecha.

`observed_reading.py` identifica columnas mediante correspondencias literales
de `observed_dates.REFERENCE_HEADERS`. No usa una columna sólo porque contenga
valores interpretables como fechas, ni acepta un índice sin significado identificado.
Encabezados duplicados para una misma fecha requieren revisión. La fecha de apertura,
actualización, revisión administrativa, consulta al geocodificador o modificación
del Excel no equivale a consulta médica ni a notificación.

Los formatos son los explícitos de Fase 2: día/mes/año de cuatro dígitos, ISO y
fechas nativas de Excel. No se interpretan números como seriales, años abreviados
ni fórmulas. Si se ofrecen formatos explícitos contradictorios, se rechaza el valor
ambiguo. La convención día primero está documentada, no se infiere fila por fila.
No se construyen fechas, no se descuentan retrasos y no se completa una fecha desde
su número de semana.

## Trazabilidad por fila

La auditoría privada conserva:

- `fecha_inicio_sintomas_original`: texto original sin limpiar; fechas nativas en ISO.
- `tipo_valor_fecha_inicio_sintomas_original`: tipo de celda para distinguir texto,
  fecha nativa y ausencia. El original exacto permanece en el Excel inmutable,
  identificado por su hash y clave técnica de fila.
- `fecha_referencia` y `reference_date`: fecha seleccionada para calcular la semana.
- `tipo_fecha_referencia`: `inicio_sintomas`, `consulta_medica`, `toma_muestra` o
  `notificacion`; null si no hay referencia.
- `fecha_aproximada`: true cuando la referencia es alternativa al inicio de síntomas.
- `motivo_seleccion_fecha`: selección directa, respaldo o ausencia de fecha válida.
- `date_selection_rejections`: campo y estado de cada fecha anterior rechazada.
- `reference_date_field`, versión de regla, alternativas interpretadas, sus estados
  y referencias de columna, sin otros valores clínicos o identificadores originales.
- `semana_potencialmente_afectada_por_retraso`: true para referencias alternativas.

La fecha alternativa no representa necesariamente el inicio real de síntomas.
La semana verdadera puede diferir por retraso entre síntomas, atención, muestra y
notificación. Sin inicio interpretable no se puede medir ese desplazamiento por fila.
El comparador informa retrasos observables donde existen ambas fechas de síntomas
y muestra, incluyendo inconsistencias de orden, sin imputarlos a los recuperados.

## Ejecución reproducible

```powershell
.\ml\venv\Scripts\python.exe -B -m sigard_ml.official.date_recovery_pipeline --config data/interim/official/access.private.json --recovery-config ml/configs/official.date-recovery.example.json
```

Se ejecuta únicamente en `entrenamiento-ML`. Requiere el panel exploratorio estricto
anterior, fuentes autorizadas, normalizados y asignaciones de Fase 3 vigentes.
Antes de escribir se verifica el manifiesto del panel anterior. Se generan dos
escenarios reutilizando `run_observed_pipeline`, sin volver a asignar coordenadas:

- `data/interim/official/observed/date_recovery_041/strict/exploratory/`.
- `data/interim/official/observed/date_recovery_041/expanded/exploratory/`.

El estricto reproduce desenlaces, fechas, semanas, conteos, ausencias e incertidumbre
del panel anterior. Los 263 radios, calendario domingo-sábado, identidad,
deduplicación, clasificaciones, elegibilidad y cobertura no cambian. Se verifica
que cada incorporación provenga de un pendiente exclusivamente por fecha y que
ninguna semana de un registro ya incorporado cambie.

La raíz versionada conserva `comparison.private.json`, `comparison.md`,
`scenario_configs.private.json` e `integrity_manifest.json`. Los escenarios tienen
los mismos productos privados de Fase 4. El JSON comparativo incluye combinaciones
excluyentes de motivos, oportunidades independientes por alternativa, recuperaciones
según jerarquía, pendientes restantes, semanas representadas, distribución semanal
y por año epidemiológico y diagnóstico de retrasos. Las huellas comprueban la
conservación de fuentes, Fases 2/3, panel previo y artefactos científicos.
Los manifiestos de otros escenarios se verifican durante ejecución pero no se
incluyen como dependencias científicas recursivas entre versiones.

Un cero en la distribución comparativa significa ausencia de filas incluidas bajo
esa política, no ausencia epidemiológica comprobada. No se traslada al panel como
cero: las celdas sin evidencia suficiente continúan null. La grilla completa y las
semanas con registros incorporados se informan por separado.

Todos los datos, configuraciones reales, auditorías y diagnósticos quedan en
almacenamiento privado excluido de Git y Docker público. La documentación
versionable no contiene conteos de la entrega sanitaria. Los reportes de texto
suprimen cantidades positivas menores de cinco; el JSON comparativo privado
conserva cantidades exactas para conciliación local.

## Pruebas ficticias

```powershell
.\ml\venv\Scripts\python.exe -B -m pytest ml/tests/test_official_contracts.py ml/tests/test_official_ingestion.py ml/tests/test_official_quality.py ml/tests/test_official_spatial.py ml/tests/test_official_observed.py ml/tests/test_official_date_recovery.py -p no:cacheprovider --basetemp=ml/.tmp/phase41-check
```

Las pruebas cubren todos los niveles de respaldo, inválidas, ambigüedad, ausencia,
límites del período/corte, cambios de semana y año, semántica de encabezados,
conservación del original, otros motivos pendientes, conciliación, autorización,
protección del panel anterior y reproducibilidad de todos los archivos. Los libros,
personas y posiciones de las pruebas son ficticios. No acceden a la entrega real.
