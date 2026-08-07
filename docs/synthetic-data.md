# Datos sintéticos en SIGARD v0.1

## Motivo

La fuente epidemiológica real aporta totales de casos para Capital por año y
semana epidemiológica, pero no identifica el radio censal de residencia. Para
probar el pipeline espacio-temporal se necesita una distribución por radio; en
`v0.1` esa distribución se simula.

## Productos sintéticos

### Asignación semanal por radio

Cada total observado de Capital se reparte entre los radios pertenecientes al
área de estudio. El resultado es un conteo entero no negativo por radio-semana.

La asignación debe cumplir:

- conservación exacta del total observado de cada semana;
- inclusión explícita de radios con cero casos;
- semilla determinista registrada;
- versión del método y sus parámetros;
- universo de radios y fuentes de ponderación identificados;
- etiqueta inequívoca `sintético` en almacenamiento, API y visualización.

La etapa 3 implementa dos escenarios explícitos y separados:

- `population_proportional`: sorteo multinomial ponderado por población;
- `spatial_clusters`: sorteo multinomial ponderado por población, focos
  reproducibles, vecindad censal, persistencia parcial y ruido configurable.

La configuración versionada `ml/configs/synthetic_allocation.json` registra las
columnas efectivas, variables, semilla y parámetros. Ningún escenario usa clima
ni coordenadas para distribuir casos. Las salidas denominan al total real
`department_cases_observed` y al conteo por radio
`synthetic_cases_assigned`, evitando describir este último como observado.

### Coordenadas puntuales

Se puede generar un punto dentro de la geometría del radio por cada caso
asignado sintéticamente. Los puntos:

- existen únicamente para visualización cartográfica;
- deben caer dentro de su radio correspondiente;
- deben ser reproducibles a partir de una semilla;
- no representan domicilios, lugares de contagio ni ubicaciones observadas;
- no deben incorporarse al entrenamiento ni a la evaluación del modelo.

Cuando la interfaz muestre puntos, debe incluir una indicación visible de que
son simulados. Una vista coroplética por radio es preferible cuando los puntos
puedan inducir una interpretación individual.

## Relación con los datos reales y las predicciones

Los conceptos no son intercambiables:

| Concepto | Cobertura espacial | Naturaleza |
| --- | --- | --- |
| `casos_observados_capital` | Capital completa | Real y agregado |
| `casos_asignados_sinteticos` | Radio censal | Simulado a partir del total real |
| `casos_predichos` | Radio censal y semana futura | Salida del modelo |

Una asignación sintética es el target usado para entrenar; no es una predicción.
Una predicción estima una asignación futura; no es un caso observado.

## Reproducibilidad

La semilla maestra debe fijarse en configuración versionada. Si se derivan
semillas por año, semana o radio, la regla de derivación también debe
versionarse. Repetir el proceso con las mismas fuentes, configuración y versión
de código debe producir la misma asignación y los mismos puntos.

Cada ejecución debe registrar:

- identificador y versión de las fuentes;
- semilla maestra y semillas derivadas;
- método, parámetros y versión;
- fecha lógica de ejecución;
- controles de conservación de totales y pertenencia geométrica.

## Riesgos de interpretación

Un modelo puede obtener buenas métricas al aprender las reglas del generador
sintético, especialmente si recibe las mismas variables usadas para ponderar la
asignación. Esto no prueba que haya aprendido la distribución real del dengue.

Por tanto:

- las métricas deben rotularse como resultados sobre datos espaciales
  sintéticos;
- deben compararse distintos supuestos o semillas cuando se analice robustez;
- nunca deben recomendarse intervenciones sanitarias basadas sólo en este
  prototipo;
- la validación epidemiológica requeriría datos espaciales reales, gobernanza y
  evaluación externa apropiadas.

## Seguridad

La generación sintética no autoriza almacenar datos sensibles. No deben
guardarse credenciales, secretos, archivos `.env` ni datos personales en
`data/` o en artefactos generados. Los datasets y modelos derivados permanecen
fuera de Git.
