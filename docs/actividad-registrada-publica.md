# Actividad registrada — mapa público con datos reales protegidos (módulo 3)

Estado: **implementado y probado sólo con datos ficticios. Desactivado por defecto.** No se
generó ningún paquete con datos reales. La publicación requiere una autorización del
Ministerio de Salud de La Rioja que todavía no está formalizada.

## Qué muestra

- **Mapa por radio censal** en bloques fijos de 4 semanas epidemiológicas, con categorías de
  nivel; nunca muestra conteos exactos por radio.
- **Serie semanal de la ciudad**: todos los registros elegibles del departamento.
- **Período histórico**: SE 1/2020 a SE 24/2024, sin 2022. Un banner fijo al pie de la ventana
  indica «Datos históricos: período … No reflejan la situación actual.». El texto se arma con el
  primer y el último bloque del paquete. Cada bloque muestra su rango de fechas. La fecha de
  generación del paquete aparece aparte y rotulada como tal.

No son casos confirmados, ni incidencia acreditada, ni ubicaciones de casos. La asignación a radio
proviene mayormente de geocodificación aproximada.

## Parámetros de protección (`sigard-public-activity-minimum5-blocks4-v1`)

| Parámetro | Valor |
|---|---|
| Bloques | 4 semanas fijas, sin solapamiento; la SE 53 se suma al bloque 13 |
| Años | 2020, 2021, 2023, 2024 hasta la SE 24; **2022 excluido** (clasificación distinta: se contaron sospechosos, probables y descartados) |
| Mínimo publicable | 5 registros |
| Población mínima del radio | 100 habitantes (Censo 2022); con población desconocida, el radio queda protegido |
| Niveles | Bajo 5–9 · Medio 10–19 · Alto ≥ 20 |
| Protegido | «Menos de 5 registros (protegido)»: incluye el cero y la protección complementaria |
| Serie de la ciudad | valor exacto si es ≥ 5; si no, «<5»; «oculto» como último recurso |
| Fuera del área analizada | los 7 radios fuera del universo común: sin dato, sus registros cuentan sólo en la ciudad |

Conteo por radio: registros con radio asignado en el universo común. Conteo de ciudad: todos los
registros elegibles del departamento. Un bloque con algún dato faltante se omite y no se imputa.

### Supresión primaria
Un radio queda protegido si tiene 0–4 registros en el bloque o si su población es menor que 100
o desconocida.

### Supresión complementaria (modelo de atacante del peor caso)
Para el peor caso se supone que el atacante conoce:
- las semanas publicadas de la ciudad;
- los niveles publicados (como intervalos; «Alto» no tiene tope);
- la población censal, y por lo tanto qué radios están protegidos por población;
- **la cantidad exacta de registros fuera de los radios publicados**;
- cuáles radios son complementarios.

Con esa información se calcula la cota inferior que puede probarse para cada radio protegido
sensible:
- los protegidos primarios por conteo valen 0–4;
- los protegidos por población y los complementarios no tienen tope.

Si algún radio queda con una cota ≥ 1, es decir, si se puede probar que tiene registros, se
protege además el radio publicado de menor conteo. Ese radio pasa a no tener tope y la cota vuelve
a 0. Si ya no queda ningún radio publicado, se ocultan las semanas de ciudad de ese bloque.

Las diferencias entre bloques consecutivos no comparten semanas, por lo que no permiten deducir
valores semanales por radio.

**Limitación documentada:** no se modela la inversión del algoritmo de selección. Un atacante que
conozca la regla podría deducir información de grupo, por ejemplo «uno de estos dos radios tiene
registros». Esta limitación se registra en el informe.

## Herramienta offline

`ml/src/sigard_ml/publication/activity_package.py`

```powershell
# Paquete ficticio para pruebas locales (nunca dentro de frontend/)
$env:PYTHONPATH='ml/src'; .\ml\venv\Scripts\python.exe -B -m sigard_ml.publication.activity_package fixture --output ml/.tmp/activity-fixture
# Paquete real: SÓLO con pedido expreso del responsable (no ejecutado)
.\ml\venv\Scripts\python.exe -B -m sigard_ml.publication.activity_package build `
  --connection data/interim/official/<conexion>.private.json `
  --config data/interim/official/<config>.private.json `
  --output data/processed/official/public-activity-v1
```

- El archivo de configuración contiene `dataset_version`, `input_sha256` (hash de etapa 1) y
  `package_version`.
- La herramienta lee como lector `analytics.consolidacion_radio_semana`,
  `consolidacion_departamento` y `consolidacion_territorio`, y verifica el hash de entrada.
- El paquete real sólo puede escribirse en `data/processed/official/`, carpeta ignorada por Git.
  Nunca se escribe en `frontend/` y nunca sobrescribe un paquete existente.
- Salida:
  - `activity.json`: niveles y serie de la ciudad;
  - `risk-report.json` y `risk-report.md`: celdas publicadas, protegidas y complementarias, mínimo
    publicado, comprobaciones y limitaciones;
  - `manifest.json`: versión, política, período, procedencia y SHA‑256 de cada archivo.
- La auditoría independiente vuelve a verificar el paquete producido. Si encuentra alguna
  revelación, el paquete no se escribe.

## Autorización y forma de servir

`GET /api/v1/public/activity` (`backend/app/public_activity.py`) responde **404** salvo que se
cumplan **todas** estas condiciones:

1. Existe `data/interim/official/public-activity-authorization.private.json` con este contenido:
   ```json
   {"fecha": "AAAA-MM-DD", "responsable_institucional": "…", "cargo": "…",
    "alcance": {"anios": [2020, 2021, 2023, 2024], "nivel": "radio_censal_bloque_4_semanas_y_ciudad_semanal"},
    "referencia_documental": "…", "manifest_sha256": "<sha256 de manifest.json>"}
   ```
2. El SHA‑256 de `manifest.json` coincide con el autorizado. Un paquete regenerado no hereda la
   autorización.
3. Cada archivo del manifiesto verifica su hash.
4. El informe de riesgo da `passed` con 0 revelaciones.
5. El contenido respeta el contrato y el alcance: tipo `real`, años autorizados, sin 2022, sin
   solapamientos, niveles válidos y semanas de ciudad ≥ 5 o «<5»/«oculto».

Comportamiento y parámetros:
- La respuesta pública incluye sólo la fecha de autorización. No expone responsable, cargo ni
  referencia.
- Las rutas se pueden cambiar con `PUBLIC_ACTIVITY_DIR` y `PUBLIC_ACTIVITY_AUTHORIZATION`.
- **Ninguna variable de entorno habilita datos reales.** `SIGARD_PUBLIC_ACTIVITY=fixture` sirve
  únicamente un paquete ficticio generado, con celdas abstractas ajenas a la cartografía real.

El frontend (`/actividad`) consulta sólo la API. El enlace «Actividad registrada» aparece sólo
cuando la API responde un paquete válido. Con datos reales, la geometría proviene del recurso
público ya aprobado `territorial_context.geojson`. El paquete nunca se incluye en `frontend/public`
ni en `dist`. Con la API en Vercel o sin ella, la vista queda desactivada y el sitio no cambia.

## Pruebas

| Prueba | Alcance |
|---|---|
| `ml/tests/test_public_activity_package.py` (15) | Fixtures de ataque: radio protegido único frente al total exacto, cota de «Medio», registros externos conocidos, radio protegido por población, umbral de población, ciudad <5, sólo niveles, SE 53, exclusión de 2022 y de la SE >24/2024, radio enmascarado, bloque incompleto, auditoría ante manipulación, guardas de escritura y manifiesto, determinismo |
| `backend/tests/test_public_activity.py` (22) | Desactivado por defecto; variables de entorno que no habilitan; fixture ficticia; autorización ligada al hash; manipulación; informe; alcance y contrato; fixture no autorizable; autorización incompleta |
| `npm run test:public-activity` (5) | Contrato, banner y período, bandera desactivada, ausencia del paquete en `public`/`dist` y lectura sólo por API |
| `npm run test:public-activity:browser` | Con Vite activo y fixture: carga < 5 s, banner y período en todos los bloques, trama, leyenda, teclado, tablas, móvil y escritorio, contraste, vista desactivada y `/mapa` intacto. Capturas en `data/interim/official/public-activity-review-v1/` (privado) |

## Pendiente

- Autorización institucional formal.
- Generación del paquete real, sólo a pedido.
- Ejecución contra la base de investigación real: `load_inputs` sólo se probó por contrato.
- Revisión del riesgo de grupo por parte del responsable.
