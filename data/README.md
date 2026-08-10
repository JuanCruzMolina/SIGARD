# Datos de SIGARD

Este directorio organiza los datos locales utilizados por el proyecto. Los
archivos de datos no se versionan en Git.

- `raw/`: fuentes originales e inmutables. No deben editarse ni sobrescribirse.
- `interim/`: resultados parciales de limpieza, transformación o integración.
- `processed/`: datasets finales, validados y listos para consumo por los
  procesos de análisis, machine learning o aplicación.

Los archivos `.gitkeep` se versionan únicamente para conservar esta estructura
de directorios vacíos. Nunca deben almacenarse aquí credenciales, secretos ni
datos personales, sanitarios o sensibles.
