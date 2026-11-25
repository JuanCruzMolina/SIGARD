# Preparación de la sesión de aceptación (kit v1.0.0)

Todos los comandos se ejecutan en PowerShell desde la raíz del repositorio.

Reglas generales:
- Docker Desktop permanece **apagado**. No se usa el PostgreSQL de `127.0.0.1:5432`.
- **Un único entorno** para los ocho escenarios: `npm run dev` con la fixture ficticia de
  «Actividad registrada». Desde F2 la API administrativa (8767) sirve el sitio público, las siete
  secciones de Administración y el visor predictivo; `dev:demo` no se usa en esta sesión porque no
  tiene visor, alertas ni auditoría.

| Entorno | Escenarios | Comando | Puertos |
|---|---|---|---|
| Único | E1–E8 | `dev` iniciado con `$env:SIGARD_PUBLIC_ACTIVITY = 'fixture'` | 5173 (sitio) · 8767 (API administrativa) |

Abrir siempre `http://127.0.0.1:5173/`, en una ventana privada nueva.

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
npm.cmd --prefix frontend run test:admin
.\backend\.venv\Scripts\python.exe -B backend/tests/publication_isolated.py --backend-regression
# Sin autorización de publicación real (debe responder False), salvo que exista la autorización formal:
Test-Path data\interim\official\public-activity-authorization.private.json
# Puertos libres (no debe listar nada):
Get-NetTCPConnection -LocalPort 5173,5174,8766,8767 -State Listen -ErrorAction SilentlyContinue
```

Pruebas de navegador recomendadas (cada una levanta y cierra su propio entorno; con los puertos
libres y **antes** de iniciar `dev`): `test:admin:browser`, `test:predictive:browser`,
`test:alerts:layout:browser`, `test:reports:layout:browser`, `test:content:layout:browser`,
`test:accounts:layout:browser` y `test:audit:layout:browser`. Guardar las salidas como anexos del
acta en la carpeta privada `data/interim/official/aceptacion/<fecha>/`.

## 2. Cuenta de administrador de la sesión

Cuenta persistente en el almacén privado de la Administración local
(`data/interim/official/internal-alerts-v1/`). `dev` arranca aunque no exista y muestra este
comando. Se crea **una vez**, en otra terminal y en forma interactiva (la contraseña no se
muestra), sin reiniciar `dev`:

```powershell
.\backend\.venv\Scripts\python.exe -B backend/app/alerts_local.py create-admin
```

Usar un correo de función (por ejemplo `aceptacion@example.test`) y una contraseña que se entrega
en papel a las referentes y se destruye al terminar. Nunca se escriben en el repositorio. Para E7
se prepara además la contraseña inicial inventada de `aceptacion-nueva@example.test`.

## 3. Levantar el entorno

```powershell
$env:SIGARD_PUBLIC_ACTIVITY = 'fixture'
Remove-Item Env:SIGARD_PRIVATE_VIEW -ErrorAction SilentlyContinue
npm.cmd --prefix frontend run dev
```

Comprobar antes de que lleguen las referentes (unos 2 minutos):
- La API precarga las predicciones durante unos 25 s; esperar a que la terminal lo indique.
- En el menú público aparece «Actividad registrada», con el aviso «Datos ficticios de prueba».
- `/admin/predictivo` sin sesión muestra el formulario de ingreso, no el visor.
- Con sesión: **Inicio** muestra cifras (no «No disponible»); en el visor, **Opciones avanzadas**
  dice «Modo de divulgación: protegido» y no hay selector de valores exactos.
- Elegir y anotar en las tarjetas:
  - E5: una semana de 2024 con actividad (con **Ir a la semana con más actividad** se encuentra);
  - E6: umbral (≥ 5) y una semana a evaluar que genere al menos una candidata con la regla
    pedida, más una semana de reserva. Probarlo con una regla de ensayo y desactivarla después
    (las reglas no se borran).
- Cerrar la sesión de prueba y abrir una ventana privada nueva para la sesión.

**Paquete real de «Actividad registrada»:** sólo con la autorización institucional formal. En ese
caso se omite `SIGARD_PUBLIC_ACTIVITY` y la API valida autorización, manifiesto e informe; sin
autorización responde 404 y la vista no aparece.

## 4. Desarrollo de la sesión

Orden fijo E1 → E8 (varios escenarios usan lo creado en los anteriores), alternando quién maneja
según `escenarios.md`. Tiempos y observaciones en `formulario-observaciones.md`. Al terminar los
escenarios: preguntas abiertas y cuestionario (`cuestionario-sus.md`), uno por referente.

## 5. Después de la sesión

1. **Ctrl+C** en la terminal de `dev` y `Remove-Item Env:SIGARD_PUBLIC_ACTIVITY`.
2. Conservar como evidencia lo creado en la sesión (reporte, edición publicada, regla, cuenta
   desactivada, eventos de auditoría) renombrando el almacén con la fecha; **no se borra**:

   ```powershell
   Rename-Item data\interim\official\internal-alerts-v1 internal-alerts-v1-aceptacion-AAAAMMDD
   ```

   La próxima vez que se inicie `dev`, el almacén empieza vacío y hay que volver a crear la cuenta
   (punto 2). El texto preventivo publicado en E4 queda sólo en el almacén renombrado.
3. Destruir los papeles con credenciales.
4. Correr de nuevo `check_repository_security.py` y `git status --short`.

## 6. Checklist del día

- [ ] Commit anotado y árbol limpio (`git status --short` vacío).
- [ ] Verificación previa aprobada y salidas guardadas en la carpeta privada.
- [ ] Docker apagado; puertos 5173/5174/8766/8767 libres antes de empezar.
- [ ] `$env:SIGARD_PRIVATE_VIEW` vacío: el visor sólo ofrece modo protegido.
- [ ] `$env:SIGARD_PUBLIC_ACTIVITY = 'fixture'` definido sólo en la terminal de la sesión.
- [ ] Cuenta de la sesión creada y probada; contraseña inicial de E7 preparada.
- [ ] Sin archivo de autorización real (o, si existe, número y SHA anotados en el acta).
- [ ] Tarjetas E1–E8 impresas con cuenta, semana, umbral y correo asignados.
- [ ] Consentimientos (2), cuestionarios (2) y `formulario-observaciones.md` impresos.
- [ ] Copia privada de `planilla-resultados.csv` en `data/interim/official/aceptacion/<fecha>/`.
- [ ] Cronómetro, ventana privada y pantalla externa para las referentes, con la terminal fuera de
      su vista.
- [ ] Grabación sólo con consentimiento de ambas, sin terminal ni credenciales.
