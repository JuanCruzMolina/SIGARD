# Distribución de código y demostración ficticia

Esta versión se distribuye en la rama `entrenamiento-ML` del repositorio
original. Los commits nuevos incorporan el código sanitizado y conservan la
historia remota anterior, sin publicar los commits locales descartados.

La demostración compartible utiliza código versionado y recursos públicos
aprobados. No necesita fuentes epidemiológicas, archivos `.env`, predicciones
experimentales, modelos serializados ni informes privados.

Desde un clon de la rama revisada, con Node/npm y Python instalados, ejecutar
en PowerShell desde la raíz:

```powershell
python -m venv backend/.venv
.\backend\.venv\Scripts\python.exe -m pip install -r backend/requirements.research.txt
npm.cmd --prefix frontend ci
npm.cmd --prefix frontend run dev:demo
```

Si las dependencias ya están instaladas, desde `frontend` basta con
`npm run dev:demo`. Abrir `http://127.0.0.1:5173/`.
La cuenta administrativa es ficticia y se genera por sesión; sus credenciales
aparecen una sola vez en la terminal. No guardarlas ni compartirlas.
Ctrl+C cierra los procesos propios y elimina la base SQLite temporal.
No iniciar simultáneamente `dev`, otra demo o sus pruebas.

La demo no requiere Docker ni PostgreSQL. Los reportes, el lote de ingestión y
el espacio de análisis son ficticios; el mapa general y el directorio conservan
los recursos públicos aprobados. La opción V3 de demo usa valores ficticios y
no ejecuta el modelo real. `npm run dev` tiene otro alcance: necesita el lector
y los artefactos privados A/B que no se distribuyen en el clon.

Las dependencias y la primera instalación necesitan acceso a sus registros.
Las comprobaciones de navegador requieren además una instalación de Puppeteer
ya disponible mediante `SIGARD_BROWSER_MODULE`; no es requisito de la demo manual.

## Revisión antes de distribuir

Las exclusiones priorizan `data/raw`, `data/interim/official`,
`data/processed/official`, `ml/artifacts/official` y nombres privados explícitos.
CSV, GeoJSON y Markdown ficticios fuera de esas rutas pueden versionarse;
`frontend/public` mantiene exclusivamente su inventario aprobado por hash.
No colocar fuentes reales en rutas de fixtures ni levantar esas exclusiones
para copiar un informe. Los originales de informes y figuras de investigación
permanecen en almacenamiento privado local excluido de Git.

Antes de publicar, ejecutar la auditoría estática, revisar los archivos y todo
el historial que quedará alcanzable desde la rama, y probar una exportación
que sólo contenga archivos versionados. Revisar también secretos y datos
incrustados en documentación, constantes, pruebas y figuras.

`.gitignore` no elimina datos ya versionados. El alcance de esta entrega es
evitar datos privados en los nuevos commits; el historial remoto preexistente
no se reescribe en esta actualización.

## Actualizar una instalación existente

Desde la raíz de un checkout limpio del repositorio original:

```powershell
git switch entrenamiento-ML
git pull --ff-only origin entrenamiento-ML
.\backend\.venv\Scripts\python.exe -m pip install -r backend/requirements.research.txt
npm.cmd --prefix frontend ci
npm.cmd --prefix frontend run dev:demo
```

Si todavía no existe `backend/.venv`, crearlo primero con
`python -m venv backend/.venv`. Abrir `http://127.0.0.1:5173/`.
Desde `frontend` el mismo inicio se ejecuta con `npm run dev:demo`.

## Clonar por primera vez

```powershell
git clone --branch entrenamiento-ML https://github.com/JuanCruzMolina/SIGARD.git
cd SIGARD
```

Después seguir la instalación de dependencias y el inicio de demo indicados
arriba. El clon no necesita fuentes sanitarias, artefactos A/B ni modelos
privados para ejecutar esta demostración.
