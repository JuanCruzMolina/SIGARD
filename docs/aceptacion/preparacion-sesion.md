# Preparación de la sesión de aceptación

Todos los comandos se ejecutan en PowerShell desde la raíz del repositorio.

Reglas generales:
- Docker Desktop permanece **apagado**.
- No se usa el PostgreSQL de `127.0.0.1:5432`.
- Los entornos `dev`, `dev:demo` y `dev:alerts` comparten el puerto 5173: **nunca se ejecutan
  en paralelo**. Se detiene uno con Ctrl+C antes de iniciar el siguiente.

| Entorno | Tareas | Comando | Puertos |
|---|---|---|---|
| A | E1–E5 | `npm.cmd --prefix frontend run dev:demo` | 5173 · 8766 (API demo ficticia, SQLite temporal) |
| B | E6–E7 | `npm.cmd --prefix frontend run dev` | 5173 · 8765 (API predictiva, sólo lectura) |
| C | E8 | `dev` (como B) **+** API pública con fixture en otra terminal | 5173 · 8765 · 8000 |
| D | E9–E10 | `npm.cmd --prefix frontend run dev:alerts` | 5173 · 8765 · 8767 (API de alertas) |

Abrir siempre `http://127.0.0.1:5173/`, en una ventana privada nueva por participante.

## 1. Verificación previa (día anterior)

```powershell
git switch entrenamiento-ML
git status --short                      # debe estar vacío
git rev-parse HEAD                      # anotar en el acta
.\backend\.venv\Scripts\python.exe -B tools/check_repository_security.py   # tracked_sensitive_candidates: 0
git diff --check
npm.cmd --prefix frontend run lint
npm.cmd --prefix frontend run build
npm.cmd --prefix frontend run test:security
npm.cmd --prefix frontend run test:public-activity
npm.cmd --prefix frontend run test:citizen
.\backend\.venv\Scripts\python.exe -B backend/tests/publication_isolated.py --backend-regression
# Sin autorización de publicación real (debe responder False), salvo que exista la autorización formal:
Test-Path data\interim\official\public-activity-authorization.private.json
# Puertos libres (no debe listar nada):
Get-NetTCPConnection -LocalPort 5173,8000,8765,8766,8767 -State Listen -ErrorAction SilentlyContinue
```

Con Vite activo (entorno B) también se pueden correr las pruebas de navegador. Si Puppeteer no
está en el proyecto, se indica su ruta con `$env:SIGARD_BROWSER_MODULE`:
- `npm.cmd --prefix frontend run test:accounts:browser`
- `npm.cmd --prefix frontend run test:public-activity:browser`

Guardar las salidas como anexos del acta, en la carpeta privada
`data/interim/official/aceptacion/<fecha>/`.

## 2. Cuenta de administrador

- **Entorno A (`dev:demo`):** la cuenta se genera en cada arranque. Correo y contraseña aparecen
  **una sola vez** en la terminal. El moderador los copia a mano en un papel para la persona
  participante y lo destruye al terminar. No se fotografían ni se guardan, y la terminal no debe
  quedar a la vista ni en grabaciones.
- **Entorno D (`dev:alerts`):** cuenta persistente en el almacén privado de alertas. Se crea
  **una vez** en forma interactiva; la contraseña no se muestra:
  ```powershell
  .\backend\.venv\Scripts\python.exe -B backend/app/alerts_local.py create-admin
  ```
  Usar un correo de función (por ejemplo `aceptacion@example.test`) y una contraseña entregada
  en papel. Nunca se escriben en el repositorio.

## 3. Levantar cada entorno

### Entorno A — prevención, reporte, administración y contenido preventivo
```powershell
npm.cmd --prefix frontend run dev:demo
```
Esperar a la línea de «listo» y a las credenciales. Base SQLite temporal; Ctrl+C la elimina.

### Entorno B — visor predictivo
```powershell
npm.cmd --prefix frontend run dev
```
Abrir `/mapa`. En «Opciones avanzadas» debe leerse «Modo de divulgación: protegido» y no debe
existir selector de valores exactos. Ese control sólo aparece si `dev` se inicia con
`SIGARD_PRIVATE_VIEW=1`, y **nunca se usa en la sesión**: verificar que la variable no está
definida (`$env:SIGARD_PRIVATE_VIEW` vacío). Tener lista la semana asignada para E6.

### Entorno C — «Actividad registrada» con fixture ficticia
Con el entorno B en marcha, abrir **otra** terminal. Desde una carpeta temporal propia, para no
leer ningún `.env`:
```powershell
$root = (Get-Location).Path
New-Item -ItemType Directory -Force backend\.tmp\aceptacion-actividad | Out-Null
Set-Location backend\.tmp\aceptacion-actividad
$env:SECRET_KEY = -join ((48..57)+(97..122) | Get-Random -Count 36 | ForEach-Object {[char]$_})
$env:DATABASE_URL = 'sqlite:///./aceptacion.sqlite3'
$env:AUTO_CREATE_SCHEMA = 'true'
$env:SIGARD_PUBLIC_ACTIVITY = 'fixture'
$env:CORS_ORIGINS = 'http://127.0.0.1:5173'
& "$root\backend\.venv\Scripts\python.exe" -B -m uvicorn app.main:app --app-dir "$root\backend" --host 127.0.0.1 --port 8000
```
- Recargar el navegador: aparece «Actividad registrada» en el menú. Comprobar el aviso «Datos
  ficticios de prueba».
- Para cerrar: Ctrl+C, luego `Set-Location $root`,
  `Remove-Item -Recurse -Force backend\.tmp\aceptacion-actividad` y cerrar esa terminal, para que
  las variables no queden activas.
- **Paquete real:** sólo con la autorización institucional formal. Entonces se omite
  `SIGARD_PUBLIC_ACTIVITY` y la API valida autorización, manifiesto e informe. Sin autorización
  responde 404 y la vista no aparece.

### Entorno D — alertas internas
```powershell
npm.cmd --prefix frontend run dev:alerts
```
La precarga de predicciones tarda unos 25 s. Iniciar sesión en «Administración» con la cuenta
del punto 2 y abrir «Alertas internas». Tener listos el umbral y la semana de E9.

## 4. Orden sugerido por participante

A (E1–E5 según el perfil) → B (E6–E7) → C (E8) → D (E9–E10) → cuestionario.

Cada cambio de entorno lleva unos 30–60 s, que no se cuentan en los tiempos de tarea. Se pueden
agrupar participantes por entorno para reducir los cambios.

## 5. Restablecer entre participantes

| Entorno | Acción |
|---|---|
| A | Ctrl+C (elimina la SQLite y la cuenta) y volver a iniciar `dev:demo`: base vacía y credenciales nuevas |
| B | Sin estado propio: cerrar la ventana privada y abrir otra |
| C | Sin estado: la fixture es fija. Cerrar la ventana privada |
| D | Reglas y decisiones **persisten**. Para empezar en limpio: detener `dev:alerts`, renombrar el almacén privado con el código del participante y volver a crear la cuenta (comandos debajo) |

Comandos del entorno D (no borra nada; conserva la evidencia de cada participante):
```powershell
Rename-Item data\interim\official\internal-alerts-v1 internal-alerts-v1-P01
.\backend\.venv\Scripts\python.exe -B backend/app/alerts_local.py create-admin
```
Alternativa más rápida: cada participante nombra su regla «Prueba P0X» y el observador filtra
por ese nombre.

En todos los casos: cerrar la ventana privada, comprobar que no quedó ninguna sesión
administrativa abierta y destruir el papel con las credenciales de `dev:demo`.

## 6. Checklist del día

- [ ] Commit anotado y árbol limpio (`git status --short` vacío).
- [ ] Verificación previa aprobada y salidas guardadas en la carpeta privada.
- [ ] Docker apagado; puertos 5173/8000/8765/8766/8767 libres antes de empezar.
- [ ] `$env:SIGARD_PRIVATE_VIEW` vacío: el visor sólo ofrece modo protegido.
- [ ] Cuenta de `dev:alerts` creada y probada.
- [ ] Sin archivo de autorización real (o, si existe, número y SHA anotados en el acta).
- [ ] Tarjetas E1–E10 impresas con la semana y el umbral asignados.
- [ ] Consentimientos impresos; cuestionarios impresos (`cuestionario-sus.md`).
- [ ] Copia privada de `planilla-resultados.csv` en `data/interim/official/aceptacion/<fecha>/`.
  Una fila `tarea` por participante y tarea, y una fila `cuestionario` por participante.
- [ ] Cronómetro, ventana privada del navegador y pantalla externa para la persona participante,
  con la terminal fuera de su vista.
- [ ] Grabación sólo con consentimiento, sin terminal ni credenciales.
- [ ] Al terminar:
  - detener todos los entornos (Ctrl+C);
  - borrar `backend\.tmp\aceptacion-actividad`;
  - destruir los papeles con credenciales;
  - correr de nuevo `check_repository_security.py` y `git status --short`.
