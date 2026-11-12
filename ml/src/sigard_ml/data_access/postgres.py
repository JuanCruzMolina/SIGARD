"""Shared PostgreSQL/PostGIS readers. Never read tabular files or fit models.

Connections are supplied by ingestion.epidemiology.db.connect, which validates
the private loopback cluster. Dataset versions are always explicit. The legacy
equivalence flag is a review gate, not something this reader can grant.
"""

from datetime import timedelta

import numpy as np
import pandas as pd
from psycopg2 import sql

from sigard_ml.official.calendar_rules import CALENDAR_VERSION, DEFAULT_CALENDAR


class DatasetBlocked(ValueError):
    """A non-sensitive, stable reason suitable for private CLI responses."""


class MLRepository:
    def __init__(self, conn):
        self.conn = conn

    def query(self, statement, parameters=()):
        with self.conn.cursor() as cur:
            cur.execute(statement, parameters)
            return pd.DataFrame(cur.fetchall(), columns=[d.name for d in cur.description])

    def calendar(self):
        return self.query('''SELECT inicio,fin,anio,numero,semanas_anio,calendario_version
            FROM analytics.semana_epidemiologica WHERE calendario_version=%s ORDER BY inicio''',
            (CALENDAR_VERSION,))

    def records(self, *, resolution_version, batch_ids, eligible_only=False):
        # Reuse the reviewed date/classification/identity selection. No second
        # implementation of clinical eligibility and no access to source books.
        from sigard_ml.forecasting.core_data import read_records, eligibility
        rows = read_records(self.conn, resolution_version=resolution_version, batch_ids=batch_ids)
        return [r for r in rows if eligibility(r) == 'included'] if eligible_only else rows

    def territory(self, universe_version, *, geometry=False):
        geom = sql.SQL(',ST_AsEWKB(r.geom) AS geometry_ewkb') if geometry else sql.SQL('')
        return self.query(sql.SQL('''SELECT r.codigo radio_id,g.version geometry_version,
            g.fuente_sha256 geometry_source_sha256,x.poblacion population,
            x.superficie_km2 area_km2,x.poblacion/x.superficie_km2 population_density,
            x.cantidad_vecinos neighbor_count,x.fuente_sha256 context_source_sha256,
            x.disponible_desde available_on {} FROM territory.miembro_universo m
            JOIN territory.universo u ON u.id=m.universo_id
            JOIN territory.radio_censal r ON r.id=m.radio_id
            JOIN territory.version_geometria g ON g.id=r.version_geometria_id
            JOIN analytics.contexto_radio x ON x.universo_id=m.universo_id AND x.radio_id=m.radio_id
            WHERE u.version=%s ORDER BY r.codigo''').format(geom), (universe_version,))

    def run(self, version):
        frame = self.query('SELECT * FROM analytics.ejecuciones_ml WHERE version=%s', (version,))
        if len(frame) != 1:
            raise DatasetBlocked('unknown_analytical_version')
        result = frame.iloc[0].to_dict()
        sources = self.query('''SELECT lote_id,sha256,current FROM analytics.fuentes_ml
            WHERE ejecucion_id=%s ORDER BY lote_id''', (result['id'],))
        result['sources'] = sources.to_dict('records')
        if sources.empty or not sources.current.all():
            raise DatasetBlocked('source_batch_missing_or_withdrawn')
        if result['calendario_version'] != CALENDAR_VERSION:
            raise DatasetBlocked('calendar_contract_changed')
        return result

    def weekly(self, version):
        self.run(version)
        return self.query('''SELECT * FROM analytics.conteos_con_procedencia
            WHERE dataset_version=%s ORDER BY radio_codigo,semana_inicio''', (version,))

    def climate(self, version):
        run = self.run(version)
        return self.query('''SELECT w.inicio,w.fin,c.temperatura,c.humedad,c.precipitacion,
            c.compatible,c.disponible_desde,c.fuente_sha256
            FROM analytics.clima_semana c JOIN analytics.semana_epidemiologica w ON w.id=c.semana_id
            WHERE c.version=%s AND w.calendario_version=%s ORDER BY w.inicio''',
            (run['clima_version'], run['calendario_version']))

    def legacy_frame(self, family, version, *, outcomes=True, origin=None, horizon=1,
                     require_equivalence=True):
        from sigard_ml.official.spatial_ml.historical_expansion import FEATURES as AB_FEATURES
        from sigard_ml.forecasting.v3 import FEATURES as V3_FEATURES
        if family not in ('A', 'B', 'V3') or horizon not in (1, 2, 4) or (family != 'V3' and horizon != 1):
            raise DatasetBlocked('unsupported_model_or_horizon')
        run = self.run(version)
        universe, size = ('v3-256-subset-v1', 256) if family == 'V3' else ('ab-263-master-v1', 263)
        if run['universe_version'] != universe:
            raise DatasetBlocked('universe_contract_changed')
        if require_equivalence and not run['equivalencia_ml_verificada']:
            raise DatasetBlocked('historical_dataset_equivalence_unverified')
        features = list(V3_FEATURES if family == 'V3' else AB_FEATURES[family])
        keys = ['radio_id', 'origin_week'] if family == 'V3' else ['radio_censal', 'fecha_inicio_semana']
        dates = ['cutoff_date', 'target_week'] if family == 'V3' else ['fin_origen', 'fecha_inicio_semana_objetivo']
        target = 'target_count' if family == 'V3' else 'objetivo_semana_siguiente'
        columns = keys + dates + features + ([target] if outcomes else [])
        conditions = [sql.SQL('dataset_version=%s')]
        parameters = [version]
        if family == 'V3':
            conditions.append(sql.SQL('horizon_weeks=%s')); parameters.append(horizon)
        if origin is not None:
            conditions.append(sql.SQL('{}=%s').format(sql.Identifier(keys[1]))); parameters.append(origin)
        frame = self.query(sql.SQL('SELECT {} FROM analytics.{} WHERE {} ORDER BY {}').format(
            sql.SQL(',').join(map(sql.Identifier, columns)), sql.Identifier('ml_' + family.lower()),
            sql.SQL(' AND ').join(conditions), sql.SQL(',').join(map(sql.Identifier, keys))), parameters)
        if frame.empty:
            raise DatasetBlocked('origin_or_dataset_unavailable')
        if frame.duplicated(keys).any() or frame[keys].isna().any().any():
            raise DatasetBlocked('duplicate_or_missing_keys')
        if frame.groupby(keys[1])[keys[0]].nunique().ne(size).any():
            raise DatasetBlocked('incomplete_territorial_grid')
        numeric = frame[features].astype(float)
        if np.isinf(numeric.to_numpy()).any():
            raise DatasetBlocked('nonfinite_features')
        if family in ('A', 'B') and numeric[AB_FEATURES['A']].isna().any().any():
            if require_equivalence:
                raise DatasetBlocked('mandatory_features_unavailable')
        if outcomes:
            values = frame[target].dropna()
            if family != 'V3' and not values.isin([0, 1]).all():
                raise DatasetBlocked('nonbinary_labels')
            if family == 'V3' and (values.lt(0).any() or values.mod(1).ne(0).any()):
                raise DatasetBlocked('invalid_count_labels')
        expected = frame[keys[1]].map(lambda d: d + timedelta(weeks=horizon))
        if not frame[dates[1]].eq(expected).all():
            raise DatasetBlocked('target_horizon_changed')
        if any(DEFAULT_CALENDAR.week_bounds(*DEFAULT_CALENDAR.date_week(d))[0] != d for d in frame[keys[1]].unique()):
            raise DatasetBlocked('invalid_origin_calendar')
        frame.attrs['provenance'] = run
        return frame

    def core_series(self, version):
        frame = self.query('''SELECT s.inicio,s.fin,s.anio,s.numero,s.semanas_anio,s.registros_observados,
            s.conteo_conservador,s.conteo_experimental,s.cobertura,s.fechas_muestra,s.pendientes_fecha,
            s.disponible_desde,s.disponibilidad_verificada,c.temperatura,c.humedad,c.precipitacion,
            c.dias,c.disponible_desde AS clima_disponible_desde
            FROM analytics.serie_predictiva_lectura s JOIN analytics.clima_predictivo c
            ON c.dataset_version=s.dataset_version AND c.semana_id=s.semana_id
            WHERE s.dataset_version=%s AND s.unidad_codigo='capital' ORDER BY s.inicio''', (version,))
        if frame.empty:
            raise DatasetBlocked('unknown_dataset_version')
        return frame

    def research_metadata(self, version):
        """New approved Option B contract; deliberately no historical-equivalence gate."""
        frame = self.query('SELECT * FROM analytics.metadatos_investigacion WHERE version=%s', (version,))
        if len(frame) != 1:
            raise DatasetBlocked('unknown_new_research_dataset')
        meta = frame.iloc[0].to_dict()
        if not meta['lotes_vigentes']:
            raise DatasetBlocked('research_source_batch_withdrawn')
        from sigard_ml.forecasting.option_b_data import ZERO_POLICY
        if meta['politica_ceros'] != ZERO_POLICY or meta['calendario_version'] != CALENDAR_VERSION:
            raise DatasetBlocked('new_research_policy_or_calendar_changed')
        if meta['protocolo'].get('research_training_authorized') is not True:
            raise DatasetBlocked('new_research_training_not_authorized')
        from sigard_ml.forecasting.core_data import canonical_hash
        pinned = meta['contrato']['territory'][meta['universe_version']]
        context = self.query('''SELECT DISTINCT radio_censal,superficie_km2,poblacion,cantidad_vecinos,
            version_territorial,contexto_sha256 FROM analytics.base_investigacion
            WHERE dataset_version=%s ORDER BY radio_censal''',(version,))
        edges = self.query('''SELECT origen,vecino FROM analytics.vecindad_investigacion
            WHERE dataset_version=%s ORDER BY origen,vecino''',(version,))
        if (canonical_hash(context.to_dict('records')) != pinned['context_sha256']
                or canonical_hash(edges.to_dict('records')) != pinned['edges_sha256']):
            raise DatasetBlocked('research_territorial_context_changed')
        return meta

    def research_frame(self, family, version, *, outcomes=True, origin=None, horizon=1):
        from sigard_ml.forecasting.option_b_data import UNIVERSES
        from sigard_ml.official.spatial_ml.historical_expansion import FEATURES as AB_FEATURES
        from sigard_ml.forecasting.v3 import FEATURES as V3_FEATURES
        if family not in ('A','B','V3') or horizon not in (1,2,4) or (family != 'V3' and horizon != 1):
            raise DatasetBlocked('unsupported_model_or_horizon')
        meta = self.research_metadata(version)
        universe,size = UNIVERSES['v3' if family == 'V3' else 'ab']
        if meta['universe_version'] != universe:
            raise DatasetBlocked('new_research_universe_incompatible')
        features = list(V3_FEATURES if family == 'V3' else AB_FEATURES[family])
        keys = ['radio_id','origin_week'] if family == 'V3' else ['radio_censal','fecha_inicio_semana']
        dates = ['cutoff_date','target_week'] if family == 'V3' else ['fin_origen','fecha_inicio_semana_objetivo']
        target = 'target_count' if family == 'V3' else 'objetivo_semana_siguiente'
        extra = ['temperature_lag_1','humidity_lag_1','precipitation_lag_1','continuous_scope'] if family == 'V3' else []
        columns = keys + dates + features + extra + ([target] if outcomes else [])
        conditions = [sql.SQL('dataset_version=%s')]; parameters = [version]
        if family == 'V3':
            conditions.append(sql.SQL('horizon_weeks=%s')); parameters.append(horizon)
        if origin is not None:
            conditions.append(sql.SQL('{}=%s').format(sql.Identifier(keys[1]))); parameters.append(origin)
        frame = self.query(sql.SQL('SELECT {} FROM analytics.{} WHERE {} ORDER BY {}').format(
            sql.SQL(',').join(map(sql.Identifier,columns)),sql.Identifier('investigacion_'+family.lower()),
            sql.SQL(' AND ').join(conditions),sql.SQL(',').join(map(sql.Identifier,keys))),parameters)
        if frame.empty:
            raise DatasetBlocked('origin_outside_experimental_coverage')
        if (frame.duplicated(keys).any() or frame[keys].isna().any().any()
                or frame.groupby(keys[1])[keys[0]].nunique().ne(size).any()):
            raise DatasetBlocked('research_grid_duplicate_or_incomplete')
        values = frame[features].astype(float)
        if np.isinf(values.to_numpy()).any():
            raise DatasetBlocked('research_nonfinite_features')
        if family != 'V3' and values[AB_FEATURES['A']].isna().any().any():
            raise DatasetBlocked('research_mandatory_static_features_missing')
        expected = frame[keys[1]].map(lambda d:d+timedelta(weeks=horizon))
        if not frame[dates[1]].eq(expected).all():
            raise DatasetBlocked('research_target_horizon_changed')
        if outcomes:
            y = frame[target].dropna()
            if (family != 'V3' and not y.isin([0,1]).all()) or (family == 'V3' and (y.lt(0).any() or y.mod(1).ne(0).any())):
                raise DatasetBlocked('research_target_invalid')
        if family == 'V3':
            from sigard_ml.forecasting.v2 import predictor_weeks
            allowed = predictor_weeks(frame)
            continuous = frame.groupby('origin_week').continuous_scope.all()
            allowed &= set(continuous.index[continuous])
            frame['predictor_admissible'] = frame.origin_week.isin(allowed)
            frame['target_end'] = frame.target_week.map(lambda d:d+timedelta(days=6))
        else:
            frame['target_end'] = frame.fecha_inicio_semana_objetivo.map(lambda d:d+timedelta(days=6))
        frame.attrs['provenance'] = meta
        return frame
