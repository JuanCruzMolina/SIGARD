# Consulta y visor predictivo privados

El repositorio incluye el código genérico del lector y del visor, sin sus
entradas sanitarias ni resultados reales. Para compartir la demostración web,
usar `npm run dev:demo` desde `frontend`: no requiere esos archivos.

## Consulta explícita V3

La consulta exige indicar la versión y disponer de artefactos privados
autorizados e íntegros. V1, V2, V3 y A/B conservan unidades y límites separados.
No se publican aquí resultados ni comparaciones de las ejecuciones reales.

```powershell
.\ml\venv\Scripts\python.exe -B -m sigard_ml.forecasting.local_query --artifacts ml/artifacts/official/sigard-principal-v3-experimental --list-dates
```

`--date YYYY-MM-DD`, `--horizon 1|2|4` y `--radio ID` filtran la consulta.
El lector reutiliza predicciones selladas; no carga estimadores ejecutables.
Una fecha sin origen disponible devuelve información insuficiente. La consulta
no fabrica ceros ni un total territorial completo cuando faltan estimaciones.

## Visor local

`npm.cmd --prefix frontend run build:predictive-viewer` compila código genérico
en `frontend/.tmp`. La incorporación posterior de datos autorizados produce
únicamente archivos `.private.html` bajo `data/interim/official/`.
Abrir esos archivos sólo desde disco bajo la cuenta autorizada. No compartirlos,
servirlos por HTTP ni incorporarlos a `frontend/public` o a la distribución.
El modo de archivo local no sustituye cifrado ni controles de acceso del sistema.

Las cantidades representan registros del escenario declarado, no riesgo clínico
ni incidencia acreditada. Se mantienen desconocidos, incertidumbre territorial,
procedencia y límites de disponibilidad. La probabilidad territorial está en
evaluación y no se habilitan alertas sanitarias ni producción.
