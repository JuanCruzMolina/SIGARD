# Calendario epidemiológico argentino 2020–2026

Revisión: 2026-10-15. Versión validada: `ar-snvs-2020-2026-v1`.
Alcance: correspondencia fecha / año epidemiológico / semana, configuración,
contratos temporales y regresiones. No acredita cobertura, elegibilidad clínica
ni precisión geográfica. No se regeneran los paneles de las Fases 4, 4.1 o 4.2.

## Causa técnica

La implementación anterior obtenía `ISO(fecha + 1 día)`. La conversión inversa
tomaba el lunes ISO y restaba un día. El constructor de `EpidemiologicalWeek`
repetía esa misma suposición, por lo que sus controles internos no detectaban
el error: la ida, la vuelta y el contrato compartían una regla incorrecta.

Desplazar ISO conserva intervalos domingo–sábado, pero traslada también la
decisión del año epidemiológico de una semana lunes–domingo. No equivale a
exigir cuatro días del año nuevo dentro de la semana domingo–sábado. En
2026 el 1 de enero cae jueves: el intervalo 28/12/2025–03/01/2026 tiene sólo
tres días de 2026. La regla anterior lo llamaba SE1/2026 y al 04/01/2026,
SE2/2026. El calendario oficial llama a esos intervalos SE53/2025 y SE1/2026.

## Fuentes y límites anuales validados

Se consultaron los PDF nacionales enlazados desde
[Herramientas epidemiológicas del Ministerio de Salud](https://www.argentina.gob.ar/salud/epidemiologia/herramientas)
y el calendario 2020 del mismo organismo. Los límites se toman de las filas
de enero/diciembre de la página 1 de cada calendario; una fila cortada por el
cambio de mes/año se completa como intervalo domingo–sábado, contrastando
el calendario adyacente. No se usa el año civil del archivo como año-SE.

- **2020:** SE1, 29/12/2019–04/01/2020; SE53,
  27/12/2020–02/01/2021; **53 semanas**.
  [Calendario nacional 2020](https://www.argentina.gob.ar/sites/default/files/bancos/2020-02/calendario-epidemiologico2020.pdf).
  El [BIV 480, SE01/2020](https://www.argentina.gob.ar/sites/default/files/biv_480_2.pdf),
  página 7, identifica expresamente el 02/01/2020 como SE01.
- **2021:** SE1, 03/01–09/01/2021; SE52,
  26/12/2021–01/01/2022; **52 semanas**.
  [Calendario nacional 2021](https://www.argentina.gob.ar/sites/default/files/bancos/2021-11/Calendario_Epidemiologico_noviembre_2021_0.pdf),
  contrastado con enero de 2022. El PDF 2021 deja sin número la fila con
  01–02/01; esos días pertenecen a SE53/2020 según el calendario 2020.
  El [boletín PBA SE1/2021](https://www.ms.gba.gov.ar/sitios/media/files/2021/02/Bolet%C3%ADn-EPI-01-21.pdf)
  aparece indexado con cierre el 09/01/2021; su descarga directa falló durante
  esta revisión. La validación del límite no depende de esa descarga.
- **2022:** SE1, 02/01–08/01/2022; SE52,
  25/12–31/12/2022; **52 semanas**.
  [Calendario nacional 2022](https://www.argentina.gob.ar/sites/default/files/bancos/2021-12/calendario-epidemiologico-2022_ms.pdf).
  El [boletín Santa Fe SE52/2022](https://www.santafe.gov.ar/index.php/web/content/download/271048/1412989/file/BOLETIN_SE%2052_SANTA%20FE%20.pdf)
  utiliza el cierre anual en SE52. El
  [anuario oficial de Entre Ríos 2022](https://www.entrerios.gov.ar/dgec/wp-content/uploads/2023/11/Anuario-2022-final.pdf)
  explicita inicio 02/01 y fin 31/12 del calendario epidemiológico.
- **2023:** SE1, 01/01–07/01/2023; SE52,
  24/12–30/12/2023; **52 semanas**.
  [Calendario nacional 2023](https://www.argentina.gob.ar/sites/default/files/bancos/2022-12/Calendario_Epidemiologico_2023.pdf).
  Se contrastó el [BEN 635, SE1/2023](https://www.argentina.gob.ar/sites/default/files/2024/04/ben_635_se_1.pdf)
  y el índice oficial de boletines 2023.
- **2024:** SE1, 31/12/2023–06/01/2024; SE52,
  22/12–28/12/2024; **52 semanas**.
  [Calendario nacional 2024](https://www.argentina.gob.ar/sites/default/files/bancos/2023-11/calendario-epidemiologico-2024.pdf).
  El [índice BEN 2024](https://www.argentina.gob.ar/salud/boletin-epidemiologico-nacional/boletines-2024)
  identifica BEN 686 SE1 como 31 de diciembre–6 de enero.
- **2025:** SE1, 29/12/2024–04/01/2025; SE53,
  28/12/2025–03/01/2026; **53 semanas**, con contradicción publicada en el cierre.
  [Calendario nacional 2025](https://www.argentina.gob.ar/sites/default/files/2019/10/calendario2025-epidemio_812025.pdf).
  El [índice BEN 2025](https://www.argentina.gob.ar/salud/boletin-epidemiologico-nacional/boletines-2025)
  confirma BEN 738 SE1 del 29/12 al 04/01 y BEN 789 SE52 del 21 al 27/12.
  Para el último intervalo se aplica la resolución que sigue.
- **2026:** SE1, **04/01–10/01/2026**; SE52,
  27/12/2026–02/01/2027; **52 semanas**.
  [Calendario nacional 2026](https://www.argentina.gob.ar/sites/default/files/2019/10/29122025-calendario-epidemiologico_2026.pdf).
  El [índice oficial BEN 2026](https://www.argentina.gob.ar/node/489617)
  confirma BEN 791 SE1 del 4 al 10 de enero y BEN 792 SE2 del 11 al 17.

Todos los años adoptados son compatibles con semanas domingo–sábado y SE1
con al menos cuatro días del año nuevo. La implementación fija los límites
verificados, sin extrapolar esa regla a años sin verificar.

## Contradicción de las publicaciones y resolución explícita

El PDF 2025 `calendario2025-epidemio_812025.pdf`, página 1, termina con una
fila **1** para 28/12–03/01, después de SE52 del 21 al 27/12. Su lectura
literal asignaría ese intervalo a SE1/2026.

El PDF 2026 `29122025-calendario-epidemiologico_2026.pdf`, página 1, marca
01–03/01 como **53** y 04–10/01 como **1**. Además, el índice nacional de
2026 identifica **BEN 790 SE53 (28 de diciembre al 3 de enero de 2026)**,
seguido por **BEN 791 SE1 (4 al 10 de enero)**. El
[boletín provincial PBA SE53](https://www.gba.gob.ar/saludprovincia/boletines_epidemiologicos/semana_53_28122025_03012026)
identifica el intervalo completo 28/12/2025–03/01/2026.

**Decisión v1:** prevalecen, para este límite, el calendario nacional 2026
y su concordancia con los boletines posteriores. Así, el intervalo pertenece
a **2025-SE53**, no a 2026-SE1. No se encontró una fe de erratas que retire
formalmente el PDF 2025; se registra el conflicto y no se afirma unanimidad
de las publicaciones. El perfil histórico reproduce la asignación anterior
de SIGARD y coincide con aquella fila del PDF 2025; no representa una segunda
validación oficial de todo 2026.

También hay erratas editoriales en índices, como SE36/2025 anunciada del
31 de agosto al 7 de septiembre (ocho días). Se conserva el intervalo del
calendario 2025, 31/08–06/09; un encabezado aislado no redefine una semana.
No se identificaron otros conflictos de límites anuales en los calendarios
2020–2024 consultados. Las fechas de publicación o los nombres de los PDF
no se usan como fecha del evento ni como año epidemiológico.

## Implementación, configuración y reproducción

- `official.calendar_rules` contiene `Calendar` y `CalendarYear` inmutables,
  límites anuales explícitos, evidencia por año y validación de continuidad.
  `ar-snvs-2020-2026-v1` admite fechas desde 29/12/2019 hasta 02/01/2027,
  correspondientes a los años epidemiológicos 2020–2026. Rechaza extrapolación.
- `official.calendar` conserva sus tres funciones públicas y añade el argumento
  opcional `calendar=`. El contrato `EpidemiologicalWeek` valida contra la misma
  instancia y expone `calendar_version`; no repite la hipótesis ISO.
- `sigard-iso-shift-v0` conserva la regla previa para reproducción histórica
  explícita, con el rango antiguo de años epidemiológicos 1678–2260.
  `validation.temporal.epidemiological_week_start` y la agregación climática
  del MVP quedan vinculadas a ese perfil para preservar su historia 2015–2024.
  El adaptador vectorial permite `calendar=DEFAULT_CALENDAR` y devuelve `NaT`
  para SE inválidas, en lugar de aceptar una SE53 desbordada al año siguiente.
- `ml/configs/official.calendar.example.json` separa calendario validado,
  reproducción histórica, período de análisis y extensión de cobertura
  desactivada. Es una configuración para la API de calendario y una futura
  ejecución explícita; no amplía automáticamente los CLI de paneles existentes.

```python
import json
from datetime import date
from pathlib import Path
from sigard_ml.official.calendar import week_from_date
from sigard_ml.official.calendar_rules import calendar_from_config

config = json.loads(Path("ml/configs/official.calendar.example.json").read_text(encoding="utf-8"))
calendar = calendar_from_config(config["calendar"])
week = week_from_date(date(2026, 1, 4), calendar=calendar)  # 2026-SE1
previous = calendar_from_config(config["historical_replay_calendar"])
old_week = week_from_date(date(2026, 1, 4), calendar=previous)  # 2026-SE2
```

Para ampliar el calendario se puede entregar a `calendar_from_config` una
nueva `version` y una lista `years` con `year`, `start` (ISO), `weeks` y
`evidence` por año. Deben ser contiguos, comenzar domingo y tener 52/53 semanas.
No se admite redefinir las dos versiones reservadas. Conservar la configuración
completa junto al resultado; una versión personalizada no se registra globalmente.
La futura generación de paneles deberá persistir la versión seleccionada en
metadatos y rechazar mezclas. Esta revisión no escribe esos metadatos anteriores.

La cobertura de análisis permanece **01/01/2020–31/12/2024**. Aunque la última
semana intersectante lleve etiqueta **2025-SE1** (29/12/2024–04/01/2025), no
incorpora registros posteriores al 31/12/2024. La extensión necesita nuevas
fuentes, evidencia de cobertura y una ejecución posterior con salidas nuevas.

## Impacto sobre los paneles preservados

La comparación diaria del intervalo 2020–2024 no cambia ninguna etiqueta,
inicio ni fin de semana. El primer desacuerdo con v0 aparece el **28/12/2025**:

- 28/12/2025–03/01/2026: v0 2026-SE1; v1 2025-SE53.
- 04/01/2026–10/01/2026: v0 2026-SE2; v1 2026-SE1.
- En el resto de 2026 la numeración v1 es una semana menor que v0; el último
  intervalo 27/12/2026–02/01/2027 es v1 2026-SE52 y v0 2026-SE53.

Los intervalos físicos siguen siendo domingo–sábado. Conteos agrupados por
fecha de inicio no migrarían entre intervalos por esta corrección; claves
año-SE, sumas por año epidemiológico y cualquier unión por esas claves sí
cambiarían para esos intervalos futuros. No reinterpretar un par año-SE
histórico con la nueva versión: `make_week(2026, 1)` ahora comienza siete días
después. Conservar la fecha de inicio y la versión histórica al comparar.

- **Fase 4:** no se esperan cambios de conteos, pendientes, etiquetas ni
  ventanas parciales en el período vigente. La selección de fecha no cambia.
- **Fase 4.1:** lo mismo para las políticas estricta y ampliada; la corrección
  no cambia la jerarquía ni recupera fechas adicionales.
- **Fase 4.2:** no cambian cobertura, ceros ni objetivos por fecha exacta +7 días
  en el período vigente. La etiqueta del límite de año se valida con v1.
  Los datos históricos no adquieren disponibilidad retrospectiva por este cambio.

La auditoría local leyó **8 paneles** y **4 auditorías de registros** ya existentes:
**0 etiquetas de panel cambiadas y 0 asignaciones de registros cambiadas**.
Comprobó SHA-256 antes/después sobre fuentes Excel y archivos preservados del
árbol de observaciones, sin diferencias. No exportó filas individuales ni
regeneró paneles. El diagnóstico y los hashes se guardaron exclusivamente en
`data/interim/official/calendar_validation_20261015_v1/`, fuera de Git.

```powershell
.\ml\venv\Scripts\python.exe -m sigard_ml.official.calendar_audit --output-dir data/interim/official/calendar_validation_20261015_v1
```

El comando exige un destino nuevo dentro de `data/interim` y rechaza sobrescribir.
Es diagnóstico: no ejecuta ingestión, geocodificación, ML ni generación de paneles.

## Validación

`ml/tests/test_official_calendar.py` incluye límites inicial/final de los siete
años, días 01/01 y 31/12, sábados/domingos, bisiestos 2020/2024, SE53 válidas
(2020 y 2025), inválidas (2021–2024 y 2026), ida/vuelta de todos los días del
calendario, reproducción v0, configuración extensible sin mutación global,
contratos directos, asignación de fecha de referencia y objetivo +7 días.
Prueba expresamente **04/01/2026 → 2026-SE1, 04/01–10/01**, además del
03/01/2026 → 2025-SE53 y 11/01/2026 → 2026-SE2.

Las pruebas de integración de calendario emplean registros ficticios. Los
paneles reales sólo se leen en la auditoría privada. Se excluye de pytest
`test_local_pipeline_expected_contract`, que ejecuta la preparación temporal
con datos locales ajenos al alcance de esta corrección.

Resultados del 15/10/2026:

- Suite de dependencias: **259 passed, 1 deselected** (75,50 s), incluyendo las
  primeras 49 regresiones de calendario, contratos, ingestión, calidad,
  panel observado, recuperación de fechas, cobertura y transformación temporal.
- Suite final de calendario, con dos regresiones adicionales de auditoría:
  **51 passed** (1,54 s). Ambas suites se superponen; no sumar sus totales.
- Auditoría privada de los ocho paneles y cuatro auditorías: sin cambios de
  etiquetas/asignaciones; hashes preservados; sin regeneración.
- `git diff --check`: sin errores; Git informa avisos de normalización LF/CRLF
  en archivos preexistentes del árbol de trabajo.

```powershell
.\ml\venv\Scripts\python.exe -m pytest ml/tests/test_official_calendar.py ml/tests/test_official_contracts.py ml/tests/test_official_ingestion.py ml/tests/test_official_quality.py ml/tests/test_official_observed.py ml/tests/test_official_date_recovery.py ml/tests/test_official_coverage.py ml/tests/test_temporal_pipeline.py -k 'not test_local_pipeline_expected_contract' --basetemp=ml/.tmp/calendar-dependent-20261015 -p no:cacheprovider --tb=short
.\ml\venv\Scripts\python.exe -m pytest ml/tests/test_official_calendar.py --basetemp=ml/.tmp/calendar-final-20261015 -p no:cacheprovider --tb=short
```

Archivos intervenidos en esta revisión: `official/calendar.py`,
`official/calendar_rules.py`, `official/calendar_audit.py`, `official/contracts.py`,
`validation/temporal.py`, `transformation/temporal.py` (todos bajo
`ml/src/sigard_ml/`); `ml/configs/official.calendar.example.json`,
`ml/configs/temporal_weekly.json`, `ml/tests/test_official_calendar.py`;
este documento, `docs/official-pipeline.md`, `docs/official-observed-panel.md`
y `docs/data-contract.md`. Los diagnósticos privados son archivos nuevos
ignorados bajo `data/interim`; no forman parte del código versionable.

Rama verificada: `entrenamiento-ML`. El árbol ya tenía cambios previos de las
fases oficiales al comenzar; se conservaron. No se hizo commit, push ni staging.
No se modificaron Excel, paneles, frontend o backend durante esta revisión;
no hubo geocodificación, entrenamiento ni incorporación de registros 2025/2026.
