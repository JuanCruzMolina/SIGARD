# Instrucciones del repositorio SIGARD

Estas reglas se aplican a todo el repositorio.

## Alcance conceptual

- La unidad analítica de `v0.1` es `radio censal - semana epidemiológica`.
- Separar siempre: observaciones agregadas de Capital, asignaciones sintéticas
  por radio y predicciones del modelo.
- El objetivo del modelo es estimar la cantidad de casos asignados a cada radio
  para la semana epidemiológica siguiente.
- No presentar resultados sintéticos como evidencia epidemiológica ni como
  ubicaciones reales de casos.

## Datos y reproducibilidad

- Tratar `data/raw/` como inmutable: nunca editar ni sobrescribir fuentes.
- Escribir resultados parciales en `data/interim/` y resultados listos para
  consumo en `data/processed/`.
- Usar semillas explícitas y deterministas en toda generación sintética o
  entrenamiento estocástico.
- Conservar procedencia, período, unidad, versión de transformación y condición
  real/sintética de cada dataset derivado.
- No versionar datos, modelos entrenados, credenciales, secretos ni archivos
  `.env`.
- No incluir coordenadas sintéticas como features del modelo; son sólo para
  visualización.

## Modelado

- Evaluar con cortes temporales que simulen predicción futura; nunca usar una
  partición aleatoria de filas.
- Calcular features usando exclusivamente información disponible hasta la
  semana que origina la predicción.
- Ajustar transformaciones únicamente con el conjunto de entrenamiento.
- Comparar el modelo con baselines temporales simples antes de interpretar sus
  métricas.
- Ejecutar entrenamiento y evaluación fuera del proceso del backend.

## Arquitectura y cambios

- Mantener separadas preparación/ML, persistencia, API y visualización.
- El frontend está previsto para desplegarse en Vercel; no asumir que FastAPI o
  PostgreSQL se ejecutan allí.
- Actualizar los contratos documentales cuando cambien unidades, campos,
  supuestos o límites metodológicos.
- Evitar afirmar precisión espacial real mientras el objetivo por radio sea
  sintético.
