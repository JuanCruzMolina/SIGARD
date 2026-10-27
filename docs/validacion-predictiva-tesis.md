# Protocolo de validación predictiva frente a persistencia

`sigard_ml.forecasting.thesis_validation` implementa comparación pareada de
errores congelados. No entrena ni selecciona un modelo nuevo.

Se compara cada candidato con persistencia rezagada y último origen cerrado,
con el mismo soporte, horizonte y corte. Se describen MAE, RMSE, sesgo,
estabilidad, colas y semanas de mayor cantidad. Los intervalos se calculan
mediante remuestreo pareado por bloques de semanas, respetando huecos y cambios
de modelo. La semilla y el tamaño de bloques deben registrarse explícitamente.

Un período ya examinado no es una reserva independiente. Los intervalos de
errores retrospectivos no acreditan episodios, cobertura, calibración ni
capacidad operativa. La superioridad de un método requiere revisión científica
y evidencia compatible con la unidad y la disponibilidad real de variables.

El [procedimiento independiente](evaluacion-independiente-v3.md) separa features,
sellado de predicciones y apertura posterior de etiquetas autorizadas.
Los resultados, tablas y figuras privados no se distribuyen. El renderizador
`tools/render_thesis_validation.py` escribe sus salidas en almacenamiento privado.
Las pruebas públicas ejercitan aritmética y contratos con datos ficticios.
