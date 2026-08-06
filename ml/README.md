# Pipeline territorial de SIGARD

Esta etapa construye el maestro territorial de Capital, La Rioja, sin modificar
las fuentes locales. Requiere Python 3.11 o posterior.

## Instalación

Desde `ml/`, crear un entorno virtual e instalar las dependencias mínimas:

```powershell
python -m venv venv
venv\Scripts\python -m pip install --upgrade pip
venv\Scripts\python -m pip install -r requirements.txt
```

GeoPandas instala transitivamente Shapely, PyProj y el motor de lectura
geoespacial. PyArrow se declara de forma directa porque es necesario para la
salida Parquet; pytest sólo se usa para las pruebas.

## Ejecución

Desde la raíz del repositorio:

```powershell
ml\venv\Scripts\python -m sigard_ml.ingestion.territorial `
  --config ml/configs/territorial_master.json
```

Salidas locales, excluidas de Git:

- `data/processed/territorial_master.parquet`
- `data/processed/territorial_master.geojson`
- `data/processed/territorial_quality_report.json`

Para ejecutar las pruebas:

```powershell
ml\venv\Scripts\python -m pytest ml/tests
```
