# Distribución de código y demostración ficticia

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

`.gitignore` no elimina datos ya versionados. Un commit correctivo no retira
contenido del historial publicado. Si la base remota ya contiene información
privada, detener el push y resolver su tratamiento con el responsable; una
auditoría estática aprobada no acredita por sí sola ausencia de datos sanitarios.
