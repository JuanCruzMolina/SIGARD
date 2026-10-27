# Instrucciones del repositorio SIGARD

Estas reglas se aplican a todo el repositorio.

## Objetivo, estructura y trabajo habitual

- SIGARD es un prototipo académico territorial: preparación/ML offline en `ml/`,
  persistencia y FastAPI en `backend/`, React/Vite/Leaflet en `frontend/` y contratos
  en `docs/`. Vercel aloja sólo el frontend; API y PostGIS son independientes.
- Trabajar en `entrenamiento-ML`; conservar cambios previos y revisar el estado
  real antes de editar. Reutilizar módulos existentes; código sencillo, legible,
  modular y sin refactorizaciones ni dependencias nuevas innecesarias.
- Completar el objetivo de principio a fin. Resolver decisiones técnicas menores
  sin pedir confirmación; ante un bloqueo, continuar partes independientes.
- Desarrollo local: `npm.cmd --prefix frontend run dev`. No iniciar frontend,
  modelos o servicios si no son necesarios para el objetivo.
- Demo integral: `npm.cmd --prefix frontend run dev:demo` agrega API ciudadana
  ficticia en 127.0.0.1:8766 con SQLite temporal y cuenta generada por sesión.
  Ctrl+C elimina sus datos; `dev` conserva sólo frontend + A/B. No ejecutar demos
  y pruebas de demo simultáneamente; no guardar las credenciales de terminal.
- Backend aislado, sin `.env` ni PostgreSQL:
  `.\backend\.venv\Scripts\python.exe -B backend/tests/publication_isolated.py`;
  agregar `--backend-regression` para la regresión backend.
- Frontend: `npm.cmd --prefix frontend run lint`, `run build`, `run test:security`,
  `run test:research`, `run test:public-map` y `run test:dev`, según el cambio.
- ML: `.\ml\venv\Scripts\python.exe -B -m pytest <pruebas_ficticias> -p no:cacheprovider`.
  Seleccionar pruebas revisadas sin entrenamiento ni lectura de fuentes privadas.
- Seguridad: `.\backend\.venv\Scripts\python.exe -B tools/check_repository_security.py`
  (auditoría estática, no inicia Docker) y `git diff --check`.

## Alcance conceptual

- La unidad analítica de `v0.1` es `radio censal - semana epidemiológica`.
- Separar siempre: observaciones agregadas de Capital, asignaciones sintéticas
  por radio y predicciones del modelo.
- El objetivo del modelo es estimar la cantidad de casos asignados a cada radio
  para la semana epidemiológica siguiente.
- No presentar resultados sintéticos como evidencia epidemiológica ni como
  ubicaciones reales de casos.
- A/B clasifican presencia provisional experimental en t+1 en un estudio
  retrospectivo; no intercambiar ese objetivo con conteos del MVP ni con
  incidencia epidemiológica acreditada.

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
- No acceder a fuentes epidemiológicas adicionales pendientes de revisión ni
  publicar registros identificables. Las fixtures deben ser generadas, claramente
  ficticias y ajenas a cartografía, predicciones o fuentes reales; nunca escribirlas
  en `frontend/public`. La ingestión oficial y la publicación territorial son flujos
  independientes; aprobar pruebas no acredita elegibilidad epidemiológica.
- Conservar etiquetas, modelos, predicciones y artefactos A/B congelados. Sin
  autorización específica, no entrenar, ajustar, inferir, recalcular resultados
  ni repetir auditorías científicas completadas. No suplir evidencia institucional
  o científica faltante con supuestos técnicos.

## Modelado

- Evaluar con cortes temporales que simulen predicción futura; nunca usar una
  partición aleatoria de filas.
- Calcular features usando exclusivamente información disponible hasta la
  semana que origina la predicción.
- Ajustar transformaciones únicamente con el conjunto de entrenamiento.
- Comparar el modelo con baselines temporales simples antes de interpretar sus
  métricas.
- Ejecutar entrenamiento y evaluación fuera del proceso del backend.
- La modalidad explícita `provisional_aggregate_experiment` admite experimentos
  locales retrospectivos de conteos de registros agregados provisionales, sin
  acreditarlos como episodios ni exigir el cierre P1–P6 del objetivo definitivo.
  La declaración expresa del responsable del 26/10/2026 establece que las cinco
  entregas SISA le fueron proporcionadas para desarrollar SIGARD y entrenar ML,
  y autoriza procesamiento, entrenamiento, evaluación y artefactos privados de
  sus agregados para uso experimental local. Registrar ese fundamento como
  `project_owner_declared_provision`, sin atribuir firma institucional ni exigir
  nuevamente documentación P1–P6. Versionar permisos de paquete/fuentes para ese
  alcance agregado; mantener los permisos históricos de ingestión separados.
  P1–P6 siguen siendo limitaciones metodológicas del objetivo definitivo, no
  bloqueos de este experimento. No convertir desconocidos en ceros, acreditar
  episodios/cobertura, modificar A/B, publicar ni habilitar producción.
- La solicitud V2 del 26/10/2026 autoriza además un escenario privado separado
  de conteos del snapshot filtrado: ceros registrados asumidos sólo en semanas
  explícitamente incluidas, nunca ausencia epidemiológica. Conservar null ante
  pendientes, problemas temporales o fuera de ese alcance; mantener 2022 aparte.
  Se permite entrenar/evaluar conteos y presencia experimental y consultar por
  fecha en local con modelos anteriores al origen, sin activar producción.
  La prueba V1 ya observada sólo sirve para diagnóstico/comparación; seleccionar
  V2 exclusivamente dentro de desarrollo. No sobrescribir V1 ni reutilizar A/B.
- El cierre experimental conserva V1 y V2 congeladas. El GLM V2 condicional no
  se promueve; la consulta utiliza persistencia con respaldo histórico como
  referencia estadística simple. Probabilidad territorial en evaluación, sin
  puntajes visibles ni alertas. Las demostraciones se generan sólo como archivos
  privados locales; no reentrenar en tareas de presentación salvo defecto técnico
  demostrado ni convertirlas en una nueva etapa de investigación.
- La solicitud explícita V3 autoriza una nueva ejecución experimental local de
  tres candidatos (Poisson directo, presencia/cantidad y corrección de persistencia)
  sobre la grilla existente. Conservar V1/V2 y A/B; seleccionar sólo con walk-forward
  de desarrollo. Se admiten features de la semana de origen ya cerrada, siempre
  como reconstrucción retrospectiva, comparando también persistencia con esa
  información. No modificar por el período ya observado ni activar ML por defecto:
  la consulta exige versión explícita y respaldo de validación multifactorial.

## Arquitectura y cambios

- Mantener separadas preparación/ML, persistencia, API y visualización.
- El frontend está previsto para desplegarse en Vercel; no asumir que FastAPI o
  PostgreSQL se ejecutan allí.
- Actualizar los contratos documentales cuando cambien unidades, campos,
  supuestos o límites metodológicos.
- Evitar afirmar precisión espacial real mientras el objetivo por radio sea
  sintético.
- Docker Desktop debe permanecer apagado; no iniciarlo para inspeccionar o probar.
  No acceder al PostgreSQL existente en `127.0.0.1:5432`, iniciar servicios
  persistentes ni modificar reinicios, volúmenes o los 263 radios oficiales.
- El importador territorial se probó con SQLite aislado; su recorrido completo
  con PostGIS real sigue pendiente. No declararlo completo ni iniciar Docker
  para resolverlo. Mantener independientes contexto territorial, simulación
  espacial publicada y consulta retrospectiva A/B.

## Validación, Git y entrega

- Revisar contratos y dependencias antes de modificar. Corregir defectos
  comprobables con regresión; ejecutar pruebas focalizadas y regresiones
  relevantes, seguridad y lint/build cuando correspondan. Reutilizar evidencia
  vigente; no repetir suites ML extensas si no fueron afectadas.
- No considerar aprobada una prueba no ejecutada. Distinguir SQLite, simulación,
  evidencia histórica PostGIS y comprobación actual; registrar límites reales.
- Se autorizan commits locales de código y documentación no sensibles ya
  revisados y probados, separados por responsabilidad. Seleccionar rutas
  explícitas; nunca `git add .`/`git add -A` indiscriminados. Revisar diff staged,
  secretos y exclusiones antes de cada commit. Dejar fuera datos, modelos,
  predicciones, `.env`, `*.private.*` y cualquier cambio de seguridad dudosa.
- No hacer push, merge, rebase, force-push ni modificar `main` sin autorización
  explícita. No descartar cambios previos ni usar operaciones destructivas para
  limpiar el árbol. Las restricciones expresas de cada tarea tienen prioridad.
- Consultar sólo si es imprescindible ampliar acceso privado, usar servicios
  prohibidos, tomar decisiones científicas/institucionales o exceder el alcance
  con una operación destructiva o irreversible.
- Al finalizar informar brevemente: completado, cambios, pruebas y límites,
  commits/pendientes, bloqueos que requieren intervención y próximo hito útil.
  No iniciar ese hito automáticamente; dejar el resultado listo para revisión.
