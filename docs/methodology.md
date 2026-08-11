# Metodología de SIGARD v0.1

## Arquitectura vigente

El contrato estático para frontend publica sólo la intersección entre semanas
con predicción temporal departamental y semanas con simulación espacial
experimental. El contexto territorial, por ser estable, no restringe el
selector. La validación temporal conserva todo el holdout aunque algunas semanas
no sean seleccionables territorialmente.

SIGARD separa tres preguntas que no deben fusionarse en un único score:

1. La predicción temporal departamental usa Random Forest para estimar el total
   oficial de Capital de la semana siguiente. No predice ubicaciones.
2. El **contexto territorial relativo** ordena los 263 radios mediante dos
   componentes: magnitud demográfico-residencial y densidad poblacional, con
   peso 50/50. Superficie queda sólo como atributo descriptivo. No representa
   incidencia, probabilidad de dengue ni riesgo sanitario oficial.
3. La **simulación espacial experimental** reutiliza predicciones del escenario
   sintético `spatial_clusters` como demostración semanal. No son observaciones,
   casos reales por radio ni validación epidemiológica espacial.

Ambas capas territoriales asignan percentiles con orden total determinista por
`score, radio_id`; sus cuatro niveles son posiciones relativas y no umbrales
sanitarios. La validación espacial con epidemiología georreferenciada real queda
pendiente.

## Pregunta técnica

Para cada radio censal y semana epidemiológica `t`, SIGARD busca estimar la
cantidad de casos asignados a ese radio en la semana epidemiológica siguiente,
`t + 1`.

El target es sintético porque los casos reales sólo están disponibles como
totales agregados de Capital. En consecuencia, el experimento evalúa si el
pipeline puede reproducir y predecir patrones del escenario simulado; no evalúa
capacidad real para localizar casos.

## Secuencia metodológica prevista

1. Preservar las fuentes originales sin modificaciones en `data/raw/`.
2. Validar cobertura, claves, unidades, geometrías y calendario epidemiológico.
3. Filtrar y agregar los casos observados de Capital por año-semana.
4. Integrar atributos censales oficiales por radio.
5. Agregar el clima a ventanas semanales documentadas.
6. Asignar sintéticamente cada total semanal entre los radios, conservando el
   total y usando una semilla determinista.
7. Construir el panel completo radio-semana, incluidas combinaciones con cero
   casos asignados.
8. Crear features disponibles hasta `t` y el target correspondiente a `t + 1`.
9. Comparar baselines temporales con Random Forest.
10. Evaluar en períodos futuros no vistos y publicar resultados versionados.

## Evaluación temporal

No se permite una partición aleatoria de filas. Radios de una misma semana
comparten el total agregado y el mecanismo de asignación; repartirlos entre
entrenamiento y prueba produciría dependencia y métricas optimistas.

La evaluación debe usar cortes cronológicos, por ejemplo:

- entrenamiento: semanas anteriores al corte;
- validación: bloque posterior para seleccionar configuración;
- prueba: bloque final, posterior y no utilizado en decisiones.

Cuando la cobertura lo permita, se preferirá validación de origen móvil o
expansivo. Las métricas se informarán por radio-semana y también agregadas por
semana para comprobar coherencia con los totales.

## Prevención de data leakage

- Ninguna feature de la fila `t` puede usar información de `t + 1` o posterior.
- Rezagos y ventanas móviles deben desplazarse antes de calcular el target.
- Imputadores, escaladores, selección de variables y ajustes equivalentes se
  aprenden sólo con entrenamiento.
- La asignación sintética de los períodos de evaluación no puede depender de
  estadísticas calculadas sobre el conjunto completo.
- No se usarán coordenadas puntuales sintéticas como features.
- No se usarán identificadores arbitrarios como sustitutos de información
  espacial o temporal.
- Si el algoritmo de asignación utiliza una variable, las métricas deben
  interpretarse considerando que el modelo podría estar reconstruyendo ese
  mecanismo.

## Baselines y métricas

Antes de Random Forest deben evaluarse baselines simples, como cero, media
histórica por radio o persistencia de la semana anterior. Las métricas concretas
se seleccionarán al inspeccionar la distribución del target, pero deberán
incluir errores adecuados para conteos y resultados agregados por semana.

Toda evaluación debe reportar período, versión de datos, semilla, features,
hiperparámetros y limitaciones. Una mejora sobre el baseline sólo expresa
capacidad predictiva dentro del escenario sintético.

## Reproducibilidad y ejecución

Toda operación estocástica debe recibir una semilla explícita y registrada.
Los resultados derivados deben poder reconstruirse a partir de fuentes,
configuración y versión de código.

El entrenamiento y la evaluación son procesos offline independientes del
backend. FastAPI consumirá resultados o artefactos ya producidos; nunca
entrenará durante una solicitud.

## Criterio de éxito de v0.1

`v0.1` será técnicamente satisfactoria si construye de forma reproducible el
panel radio-semana, conserva las identidades real/sintética/predicha, evita
fugas temporales, evalúa contra baselines y permite publicar resultados en el
mapa. Esto no constituye validación epidemiológica espacial.
