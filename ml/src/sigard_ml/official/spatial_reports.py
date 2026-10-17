"""Diagnósticos agregados seguros; sin coordenadas, etiquetas libres o radios."""

from sigard_ml.official.reports import safe_count
from sigard_ml.official.spatial_assignment import possible_radios, prepare_points
from sigard_ml.official.spatial_settings import METRIC_CRS
from pyproj import CRS


def safe_counts(values):
    return {str(key): safe_count(int(value)) for key, value in values.items()}


def repetition_profile(assignments):
    groups = assignments.dropna(subset=["coordinate_group_ref"]).drop_duplicates("coordinate_group_ref")
    sizes = groups.coordinate_group_size
    bands = {}
    for name, lower, upper in (("one", 1, 1), ("two_to_four", 2, 4), ("five_to_nine", 5, 9),
                               ("ten_to_49", 10, 49), ("50_to_99", 50, 99), ("100_or_more", 100, float("inf"))):
        selected = sizes.between(lower, upper)
        bands[name] = {"coordinate_groups": safe_count(int(selected.sum())),
                       "records": safe_count(int(sizes[selected].sum()))}
    return {"bands": bands, "scope": "whole_authorized_delivery_exact_numeric_pairs",
            "repeated_coordinate_groups": safe_count(int(sizes.gt(1).sum())),
            "repeated_coordinate_records": safe_count(int(sizes[sizes.gt(1)].sum())),
            "largest_group_records": safe_count(int(sizes.max())) if len(sizes) else 0,
            "records_in_five_largest_groups": safe_count(int(sizes.nlargest(5).sum())),
            "interpretation": "Shared positions may reflect shared residence or geocoding references; no records removed."}


def boundary_sensitivity(frame, assignments, radios, coordinate_crs, distances):
    """Sondeos de distancia, ponderados por registros y por posiciones distintas."""
    points, _ = prepare_points(frame.reset_index(drop=True), CRS(coordinate_crs) if coordinate_crs else None)
    metric_points = points.to_crs(METRIC_CRS) if points is not None else None
    metric_radios = radios.to_crs(METRIC_CRS)
    interior = assignments.geometry_status.eq("unique_interior")
    distinct = assignments.loc[interior].drop_duplicates("coordinate_group_ref")
    probes = []
    for distance in distances:
        nearby = interior & assignments.distance_to_boundary_m.le(distance)
        alternative_groups = alternative_records = 0
        for index, group in distinct.loc[distinct.distance_to_boundary_m.le(distance)].iterrows():
            if len(possible_radios(metric_points.iloc[index], metric_radios, distance)) > 1:
                alternative_groups += 1
                alternative_records += int(group.coordinate_group_size)
        probes.append({"probe_distance_m": float(distance),
                       "interior_records_near_boundary": safe_count(int(nearby.sum())),
                       "distinct_interior_coordinates_near_boundary": safe_count(
                           int(assignments.loc[nearby, "coordinate_group_ref"].nunique())),
                       "coordinates_with_multiple_scenario_radios": safe_count(alternative_groups),
                       "records_with_multiple_scenario_radios": safe_count(alternative_records)})
    return {"meaning": "Exploratory distances, not validated geocoder error radii or probabilities.", "probes": probes}


def geographic_quality(assignments, sensitivity):
    geometry = assignments.geometry_status.value_counts()
    states = assignments.assignment_state.value_counts()
    usable = assignments.coordinate_status.eq("usable")
    return {"records_analyzed": safe_count(len(assignments)),
            "usable_coordinates_under_declared_or_assumed_crs": safe_count(int(usable.sum())),
            "unique_coordinates": safe_count(int(assignments.coordinate_group_ref.nunique())),
            "missing_coordinates": safe_count(int(assignments.coordinate_status.eq("missing_coordinates").sum())),
            "geometric_status_counts": safe_counts({name: geometry.get(name, 0) for name in
                 ("unique_interior", "boundary", "multiple_matches", "outside_territory", "missing_coordinates",
                  "invalid_coordinates", "unknown_crs")}),
            "assignment_state_counts": safe_counts({name: states.get(name, 0) for name in
                 ("unique_geometry", "uncertain", "ambiguous", "unassigned")}),
            "unassignable_records": safe_count(int(assignments.assignment_state.isin(["ambiguous", "unassigned"]).sum())),
            "geocoding_categories": safe_counts(assignments.geocoding_category.value_counts()),
            "uncertainty_reason_counts": safe_counts(assignments.uncertainty_reasons.explode().dropna().value_counts()),
            "eligibility_counts": safe_counts(assignments.eligibility.value_counts()),
            "repetition": repetition_profile(assignments), "boundary_sensitivity": sensitivity,
            "case_counts_generated": False, "training_labels_generated": False,
            "small_positive_counts_suppressed": True}


def viability_text(report):
    summary = report["summary"]
    cartography = report["cartography"]
    evidence = report["geographic_evidence"]
    lines = ["# SIGARD: viabilidad territorial preliminar (privado)", "",
             f"Transformación: {report['transformation_version']}. Unidad: registro de fuente sin elegibilidad resuelta.",
             f"Registros analizados: {summary['records_analyzed']}. Coordenadas diferentes: {summary['unique_coordinates']}.",
             "No son conteos de casos confirmados ni etiquetas para entrenamiento.", "",
             "## Cartografía", "",
             f"Radios: {cartography['radio_count']}; identificadores únicos y geometrías válidas.",
             f"Igualdad con fuente censal original: {cartography['original_geometry_match']}.",
             f"Pares superpuestos con área positiva: {cartography['positive_area_overlap_pairs']}.",
             f"Área de superposición por pares: {cartography['pairwise_overlap_area_m2']:.6f} m².",
             "Las geometrías se conservan. Las múltiples coincidencias nunca reciben un radio elegido arbitrariamente.",
             "El territorio se define por la unión de los radios de Capital. No se dispone de un límite departamental independiente",
             "en esta comprobación: la correspondencia se apoya en los códigos censales, nombres y cartografía de origen.",
             "EPSG:4326 se usa para intercambio y pruebas topológicas. EPSG:32719 se usa para distancias en metros.",
             f"Todo Capital dentro del área nominal de UTM 19S: {cartography['nominal_metric_area_contains_entire_territory']}.",
             f"Desviación máxima de escala en la envolvente local: {cartography['bounding_box_max_scale_deviation_pct']:.4f}%; "
             f"tolerancia numérica de este diagnóstico: {cartography['diagnostic_scale_tolerance_pct']:g}%.",
             "Capital se extiende al este de la zona nominal 19S. Se conserva la convención vigente para distancias locales",
             "con esa distorsión cuantificada, sin afirmar cobertura nominal completa. Los umbrales muy próximos requieren",
             "considerar esta aproximación numérica. No es un margen de error del geocodificador.", "",
             "## Evidencia de las posiciones", "",
             f"CRS confirmado: {evidence['crs_confirmed']}. Hipótesis de trabajo: {evidence['coordinate_crs']}.",
             f"Procedencia documentada: {evidence['provenance_documented']}; significado geográfico: {evidence['location_role']}.",
             f"Margen documentado disponible: {evidence['documented_uncertainty_available']}.",
             "Estar dentro de Capital sólo verifica compatibilidad geométrica bajo el CRS utilizado. No demuestra exactitud.",
             "Las etiquetas de calle, interpolación y barrio no cuantifican error ni garantizan una ubicación de residencia.",
             "Las repeticiones se estudian para toda la entrega, a diferencia del control por hoja de Fase 2.",
             "Pueden reflejar domicilios compartidos o referencias del geocodificador. No se eliminan filas por esa señal.", "",
             "## Resultados agregados", ""]
    for state, count in summary["geometric_status_counts"].items():
        lines.append(f"- Geometría {state}: {count} registros.")
    for state, count in summary["assignment_state_counts"].items():
        lines.append(f"- Asignación {state}: {count} registros.")
    lines += ["", f"Registros que comparten posición: {summary['repetition']['repeated_coordinate_records']}.",
              f"Registros en las cinco concentraciones mayores: {summary['repetition']['records_in_five_largest_groups']}.",
              "Estas concentraciones no demuestran agrupamientos epidemiológicos.", "",
              "## Sensibilidad a límites", "",
              "Distancias exploratorias, elegidas para inspeccionar distintas escalas. No constituyen precisión real del geocodificador.",
              "Se distinguen registros y coordenadas distintas para que las repeticiones no aparenten evidencia independiente."]
    for probe in summary["boundary_sensitivity"]["probes"]:
        lines.append(f"- A {probe['probe_distance_m']:g} m: {probe['interior_records_near_boundary']} registros interiores y "
                     f"{probe['distinct_interior_coordinates_near_boundary']} coordenadas cerca de límites; "
                     f"{probe['records_with_multiple_scenario_radios']} registros con más de un radio en el sondeo.")
    lines += ["", "## Viabilidad y pasos previos al panel observado", "",
              "Los 263 radios son utilizables para diagnóstico geométrico. Su adecuación como resolución epidemiológica no está demostrada.",
              "Sin validación externa de posiciones y significado geográfico, no puede justificarse un panel observado definitivo por radio.",
              "La asignación interior única conserva un candidato; su confianza geográfica se evalúa aparte y nunca certifica precisión epidemiológica.",
              "Debe obtenerse documentación del CRS, proveedor, consulta, método, ubicación representada y errores observados,",
              "y validar una muestra autorizada contra referencias confiables sin publicar posiciones individuales.",
              "Después debe compararse la estabilidad de radios frente a errores documentados, manteniendo control de repeticiones.",
              "Si esa estabilidad es insuficiente, evaluar fracciones censales, conjuntos contiguos de radios o unidades administrativas",
              "con límites oficiales y correspondencias verificadas. Agrupar reduce sensibilidad a límites internos, pero no corrige",
              "errores de ubicación, sesgos de geocodificación ni elegibilidad pendiente. No se implementan agrupaciones en esta fase.",
              "Confirmar unidad de registro, clasificación de caso, deduplicación, fechas y cobertura antes de contar casos o entrenar.",
              "No se generaron paneles, etiquetas, modelos ni GeoJSON de pacientes. Cantidades positivas menores de cinco se suprimen.", ""]
    return "\n".join(lines)
