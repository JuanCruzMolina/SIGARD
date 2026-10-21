# Robustez descriptiva de los experimentos espaciales A/B

Ejecutor offline `sigard_ml.official.spatial_ml.robustness`, versión
`official-spatial-robustness-1.0`. No entrena, carga modelos, ejecuta inferencia,
ajusta calibración, modifica etiquetas ni cambia umbrales. No altera frontend,
backend o contratos de publicación. Código y pruebas aptos para versionado local;
los resultados y manifiestos privados permanecen fuera de Git.

La consolidación del 21/10/2026 corrigió la narrativa del generador: las
comparaciones ahora usan las métricas de entrada y conservan valores no definidos,
sin conclusiones fijadas para un experimento particular. Se verificó con fixtures
que invierten esas comparaciones y métricas ausentes. No se regeneraron informes
privados ni resultados A/B; sus hashes/manifiestos conservan la evidencia histórica.

Consume sólo las predicciones, evaluaciones y metadatos congelados de
`spatial_rf_05c_v1` y `spatial_rf_B_05f_v1`, vinculados al registro privado de
lectura existente. Reutiliza controles de manifiesto, destino privado nuevo,
métricas, bins y descomposición temporal AUC del diagnóstico 5D. No sigue las
rutas de fuentes originales heredadas en los manifiestos ni abre libros,
datasets epidemiológicos adicionales o matrices de preparación. Los archivos
de modelo se leen como bytes exclusivamente para SHA-256, sin deserialización.

Se exige la rama `entrenamiento-ML`, destinos ignorados por Git e inexistentes.
Se comprueba la igualdad exacta de etiquetas, claves, particiones y scores
A/baseline entre artefactos A/B. Se verifica el período aprobado, 263 radios,
8/8/4 semanas, objetivo t+1, umbral 0,5, clases guardadas y prior de entrenamiento.
Son comprobaciones de coherencia de artefactos, no nuevos validadores
epidemiológicos. Se conservan los controles y limitaciones existentes.

## Reproducción

```powershell
.\ml\venv\Scripts\python.exe -B -m sigard_ml.official.spatial_ml.robustness --output-dir data/processed/official/spatial_robustness_v2 --plot-python ml/.tmp/phase5d-venv/Scripts/python.exe
.\ml\venv\Scripts\python.exe -B -m pytest ml/tests/test_official_spatial_robustness.py ml/tests/test_official_research_diagnostics.py -p no:cacheprovider --basetemp=ml/.tmp/robustness-final-check
```

El render usa el entorno Matplotlib ya existente, sin instalaciones. Para una
nueva ejecución elegir otro destino. `spatial_robustness_v1` conserva la primera
ejecución técnica; `spatial_robustness_v2` contiene la entrega con síntesis y
proveniencia del render. No sobrescribir ninguna de ellas. Las suites de
entrenamiento no se ejecutan en esta fase.

## Productos privados

- `summary.private.md`: síntesis breve para revisión humana.
- `report.private.html`: informe técnico local con tablas, interpretación y
  tres gráficos; no carga recursos de red. Referencias externas sólo como links.
- `analysis.private.json` y tablas CSV: métricas globales/semanales, calibración,
  comparación con baseline, distribución de scores, transiciones entre semanas,
  sensibilidad al excluir una semana, errores pareados y descomposición AUC.
- `frozen_consistency.private.csv`: contraste de métricas con artefactos
  congelados B y métricas originales A/baseline, además de identidades semanales.
- PNG/SVG, versiones del render y manifiesto SHA-256 de entradas/salidas/código.

Todas las salidas son agregadas, sin pacientes, identificadores de radio ni
coordenadas. Datos y resultados privados permanecen excluidos de Git. Los hashes
se comprueban antes/después sobre todos los archivos de ambos experimentos,
incluidos productos agregados posteriores a sus manifiestos originales.

## Interpretación

Unidad: radio–semana, presencia binaria experimental en t+1; separada del
objetivo de conteos sintéticos del MVP. Sólo etiquetas conocidas entran en
métricas; desconocidos se conservan en denominadores de grilla, sin convertirlos
en negativos. Sin etiquetas, las métricas se mantienen no definidas; sin
alertas, Precision es no definida. AP no es PR-AUC trapezoidal.

El baseline es el prior ya calculado en entrenamiento: no se recalcula con
semanas de evaluación, ni al excluir semanas. Las comparaciones usan exactamente
el mismo período, población y etiquetas. El informe distingue ranking, error
probabilístico y balance FP/FN, sin elegir ganador sólo por ROC-AUC o recall.

La sensibilidad al excluir una semana reutiliza scores fijos; no es validación
cruzada ni intervalo de confianza. La comparación semanal macro no sustituye
métricas agrupadas. La AUC dentro de semana se pondera por pares positivos y
negativos; la agrupada incluye pares de semanas distintas. Los cuantiles del
score describen dispersión entre radios, no incertidumbre estadística. ECE y
bins son descriptivos; Brier no aísla calibración. Sin pruebas ni intervalos IID
ante dependencia espacial/temporal y pocas semanas.

Positivos provisionales, negativos asumidos, cobertura no plenamente acreditada,
disponibilidad histórica no acreditada, evaluación retrospectiva y prueba ya
examinada se mantienen explícitos. Ninguna variación del score se interpreta
como cambio real de incidencia. Se requiere revisión humana antes de cualquier
uso ulterior; no habilita publicación o despliegue. No selecciona modelos,
hiperparámetros, calibradores o umbrales usando prueba.

Se utilizaron las habilidades `statistical-analysis`, `scientific-writing` y
`matplotlib`; su referencia procedimental, verificada bibliográficamente, se
incluye en el informe privado. La revisión humana de resultados está pendiente.
