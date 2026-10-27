# Procedimiento de diagnóstico predictivo

El código de diagnóstico se conserva en `tools/diagnose_predictive_v3.py` y
`tools/experiment_predictive_v3_recency.py`. Sus pruebas usan fixtures generadas,
sin acceso a fuentes reales ni ejecución de los experimentos privados.

El procedimiento examina faltantes, cambios temporales, errores condicionados,
sesgo y sensibilidad de grupos de variables. La comparación debe usar el mismo
conjunto de etiquetas conocidas y conservar los cortes y modelos congelados.
Un análisis posterior a observar un período no constituye validación externa
ni justifica seleccionar otra configuración con ese período.

Los resultados, distribuciones, métricas y conclusiones de ejecuciones privadas
quedan fuera de Git. Los originales de los informes se conservan localmente bajo
`data/interim/official/`, con acceso restringido a sus responsables.
Publicar este procedimiento no autoriza ejecutar nuevos diagnósticos,
entrenamientos ni acceder a otras fuentes.
