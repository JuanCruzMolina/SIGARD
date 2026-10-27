# Escenario experimental de cobertura asumida

`sigard_ml.official.spatial_ml.assumed_scenario_pipeline` consume los derivados
preservados de Fases 5A y 5B. No abre Excel, ingiere datos, geocodifica, recalcula
características ni entrena. El ejemplo público carece de autorización y no es
ejecutable hasta proporcionar la decisión privada explícita.

Esta versión sólo admite semanas objetivo completas entre 2024-01-07 y
2024-06-08, fuente `delivery_2024_2026`, 263 radios y política ampliada. La
autorización refiere al universo listo congelado, no a exhaustividad de
vigilancia. No se procesan archivos en revisión ni se reactiva la conciliación.

Se usa un contrato separado de cobertura comprobada/declarada de fases
anteriores: no se falsifican períodos de extracción o pruebas faltantes.
El escenario asumido no satisface requisitos de cobertura verificada.

Una etiqueta desconocida sólo pasa a `0` si su semana t+1 está dentro del
intervalo, no es parcial, tiene conteo original desconocido y cero pendientes
posibles. El tipo explícito es `cero_asumido_experimental`. Los positivos,
ceros heredados y bloqueos se preservan. Una celda t+1 ausente no se salta.

Sólo se materializan etiquetas: `casos_observados` conserva sus null, como los
predictores históricos. La matriz A proyecta las siete características ya
seleccionadas, sin ajustes. Etiquetas, bloqueos, cobertura y procedencia quedan
fuera de los predictores. La configuración A se copia exactamente como referencia.

Se exige una carpeta privada nueva, ignorada por Git: etiquetas, autorización
semanal, matriz A, particiones, distribuciones agregadas por radio/semana objetivo,
informe, configuración, metadatos y manifiesto. Se vinculan versiones/hashes de
fuentes listas, calendario, entradas, decisión e implementación y se comprueba
conservación de fuentes, derivados y modelos previos conocidos.

Se auditan los planes heredados y un plan limitado al intervalo autorizado con
fronteras de origen 2024-03-03 y 2024-05-05. Se purgan objetivos que cruzan
fronteras; todos los radios comparten cortes, sin división aleatoria.
Se cuentan ambas clases, desconocidos y semanas por clase. Tener ambas clases
no valida tamaño muestral, independencia ni entrenamiento.

El universo de trabajo lo define el paquete privado autorizado; no acredita
el universo epidemiológico definitivo. Persisten limitaciones de clasificación, fechas,
residencia, asignación espacial, disponibilidad censal histórica y maduración.
La evaluación es retrospectiva, no operativa validada. Las etiquetas estrictas
sólo se consultan para sensibilidad descriptiva, sin materializar otros ceros.

```powershell
.\ml\venv\Scripts\python.exe -B -m sigard_ml.official.spatial_ml.assumed_scenario_pipeline --config <configuracion-privada>
.\ml\venv\Scripts\python.exe -B -m pytest ml/tests/test_official_assumed_scenario.py -p no:cacheprovider
```

Pruebas ficticias con fit y lectura de Excel prohibidos: autorización, límites,
faltantes, bloqueos, t+1, calendario, purga, clases, conservación, destinos
privados, reproducibilidad y rechazo de entradas alteradas. El entrenamiento
requiere una autorización posterior independiente.
