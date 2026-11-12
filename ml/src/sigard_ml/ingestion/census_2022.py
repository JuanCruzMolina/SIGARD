"""Local census context and exact, auditable linkage; no fitting or DB writes.

Reuses the territorial configuration, frozen membership and normalized census
storage. Category labels are a literal inventory, not an official dictionary.
"""
import argparse
import hashlib
import json
from pathlib import Path

import pandas as pd

from sigard_ml.ingestion.epidemiology.complementary import CensusCSV
from sigard_ml.ingestion.epidemiology.db import connect
from sigard_ml.validation.territorial import normalize_code, compare_id_sets

VERSION = 'census-2022-linkage-1'
ROOT = Path(__file__).resolve().parents[4]
TOTALS = ('population', 'households', 'dwellings')


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def link_context(master, common, sources, definitions):
    """Keep every master radio and missing values; never join by row position."""
    master = master.copy()
    master['radio_id'] = normalize_code(master.radio_id, 9, 'radio_id')
    common = normalize_code(pd.Series(list(common), dtype='string'), 9, 'radio_id')
    if master.radio_id.duplicated().any() or common.duplicated().any():
        raise ValueError('census_duplicate_territory')
    if not set(common) <= set(master.radio_id):
        raise ValueError('census_common_outside_master')
    for col in ('fraccion', 'radio'):
        master[col] = normalize_code(master[col], 2, col)
    if not master.radio_id.eq('46014'+master.fraccion+master.radio).all():
        raise ValueError('census_master_components_mismatch')
    context = master[['radio_id', 'fraccion', 'radio']].copy()
    context['common_evaluation'] = context.radio_id.isin(common)
    context['exclusion_reason'] = context.common_evaluation.map(
        {True: '', False: 'outside_frozen_common_membership'})
    report = {}
    for name in TOTALS:
        frame = sources[name]
        definition = definitions[name]
        selected = frame.loc[frame.cod_variable.eq(definition['variable'])]
        if selected.empty:
            raise ValueError('census_required_variable_absent')
        if selected.duplicated(['codigo', 'cod_variable', 'cod_categoria']).any():
            raise ValueError('census_duplicate_aggregation_key')
        field = definition['output_column']
        totals = selected.groupby('codigo').cantidad.sum(min_count=1).rename(field+'_2022')
        report[name] = compare_id_sets(master.radio_id, totals.index)
        context = context.merge(totals, left_on='radio_id', right_index=True,
                                how='left', validate='one_to_one')
        # The existing master must be reproducible from the same variables.
        if field in master:
            expected = master.set_index('radio_id')[field].reindex(context.radio_id)
            actual = context[field+'_2022']
            mismatch = actual.notna().to_numpy() & (actual.to_numpy()!=expected.to_numpy())
            if mismatch.any():
                raise ValueError('census_existing_master_total_mismatch')
    context['census_reference_year'] = 2022
    context['available_on'] = None
    context['data_kind'] = 'observed_census_aggregate_context'
    return context.sort_values('radio_id').reset_index(drop=True), report


def attach_asof(panel, context, *, available_on=None):
    """Optional future feature preparation; unknown arrival keeps predictors NULL.

    Does not change the frozen motor feature lists or membership. The caller must
    supply a documented release date; year 2022 alone is not availability proof.
    """
    if context.radio_id.duplicated().any() or panel.duplicated(['radio_id','origin_end']).any():
        raise ValueError('census_duplicate_feature_key')
    if panel[['radio_id','origin_end']].isna().any().any() or not set(panel.radio_id)<=set(context.radio_id):
        raise ValueError('census_feature_codes_or_origins_invalid')
    features = ['poblacion_2022','hogares_2022','viviendas_2022']
    result = panel.merge(context[['radio_id',*features]], on='radio_id', how='left',
                         validate='many_to_one')
    origin = pd.to_datetime(result.origin_end, errors='raise')
    eligible = pd.Series(False, index=result.index)
    if available_on is not None:
        release = pd.Timestamp(available_on)
        if pd.isna(release) or release.year < 2022:
            raise ValueError('census_invalid_release_date')
        eligible = origin.ge(release) & origin.dt.year.ge(2022)
    for field in features:
        result[field+'_asof'] = result[field].where(eligible)
    return result


def verify_database(conn, context, sources, hashes, master_sha256):
    """SELECT-only reconciliation with existing IDs, geometry version and lots."""
    with conn.cursor() as cur:
        cur.execute('''SELECT r.id,r.codigo,p.codigo,d.codigo,f.codigo,g.fuente_sha256,
            EXISTS(SELECT 1 FROM territory.miembro_universo m2
              JOIN territory.universo u2 ON u2.id=m2.universo_id
              WHERE m2.radio_id=r.id AND u2.version='v3-256-subset-v1')
            FROM territory.radio_censal r
            JOIN territory.fraccion_censal f ON f.id=r.fraccion_id
            JOIN territory.departamento d ON d.id=f.departamento_id
            JOIN territory.provincia p ON p.id=d.provincia_id
            JOIN territory.version_geometria g ON g.id=r.version_geometria_id
            JOIN territory.miembro_universo m ON m.radio_id=r.id
            JOIN territory.universo u ON u.id=m.universo_id
            WHERE u.version='ab-263-master-v1' ORDER BY r.codigo''')
        rows = cur.fetchall()
        mapping = pd.DataFrame(rows, columns=['postgres_radio_id','radio_id','province',
            'department','fraction','master_sha256','common_evaluation'])
        if mapping.empty or mapping.radio_id.duplicated().any() or mapping.postgres_radio_id.duplicated().any():
            raise ValueError('census_database_ambiguous_master')
        if set(mapping.master_sha256)!={master_sha256}:
            raise ValueError('census_database_geometry_version_mismatch')
        if any(compare_id_sets(context.radio_id,mapping.radio_id).values()):
            raise ValueError('census_database_master_membership_mismatch')
        checked = mapping.merge(context[['radio_id','fraccion','common_evaluation']],
            on='radio_id',validate='one_to_one',suffixes=('_db','_local'))
        if not (checked.province.eq('46') & checked.department.eq('014') &
                normalize_code(checked.fraction,2,'fraction').eq(checked.fraccion) &
                checked.common_evaluation_db.eq(checked.common_evaluation_local)).all():
            raise ValueError('census_database_dimensions_or_common_mismatch')
        batches = {}
        for name in TOTALS:
            cur.execute('''SELECT b.id FROM ingestion.lotes_complementarios_vigentes b
                JOIN ingestion.archivo_fuente a ON a.id=b.archivo_id
                WHERE b.tipo='census_aggregate' AND a.sha256=%s ORDER BY b.id''',(hashes[name],))
            ids = [row[0] for row in cur.fetchall()]
            batches[name] = dict(batch_ids=ids, verified=False)
            for bid in ids:
                cur.execute('''SELECT r.id,r.codigo,v.codigo,c.codigo,c.descripcion,o.cantidad
                    FROM territory.observacion_censal o
                    JOIN territory.radio_censal r ON r.id=o.radio_id
                    JOIN territory.categoria_censal c ON c.id=o.categoria_id
                    JOIN territory.variable_censal v ON v.id=c.variable_id
                    WHERE o.lote_id=%s''',(bid,))
                observed = sorted(cur.fetchall())
                frame = sources[name]
                frame = frame.loc[frame.codigo.isin(context.radio_id)]
                ids_by_code = mapping.set_index('radio_id').postgres_radio_id.to_dict()
                expected = sorted((ids_by_code[r.codigo],r.codigo,r.cod_variable,r.cod_categoria,r.categoria,int(r.cantidad))
                                  for r in frame.itertuples())
                if observed!=expected:
                    raise ValueError('census_database_observations_mismatch')
            batches[name]['verified'] = bool(ids)
    return mapping, batches


def prepare(root, output, *, connection=None):
    root, output = Path(root).resolve(), Path(output).resolve()
    if not any(output.is_relative_to(root/'data'/kind) for kind in ('interim','processed')) or output.exists():
        raise ValueError('census_new_local_output_required')
    config_path = root/'ml/configs/territorial_master.json'
    config = json.loads(config_path.read_text(encoding='utf-8-sig'))
    master_path = root/config['outputs']['parquet']
    common_dir = root/'data/processed/principal_territory_46014010_256_v1'
    manifest = json.loads((common_dir/'manifest.json').read_text(encoding='utf-8-sig'))
    master_hash = digest(master_path)
    if (master_hash!=manifest['configuration']['inputs']['master']['sha256'] or
        digest(common_dir/'territory.parquet')!=manifest['outputs_sha256']['territory.parquet']):
        raise ValueError('census_frozen_territory_hash_mismatch')
    master = pd.read_parquet(master_path,columns=['radio_id','fraccion','radio','poblacion','hogares','viviendas'])
    common = pd.read_parquet(common_dir/'territory.parquet',columns=['radio_id']).radio_id
    if len(master)!=263 or len(common)!=256:
        raise ValueError('census_unexpected_universe_size')
    sources, hashes, inventory, categories, paths = {}, {}, {}, [], {}
    for name in TOTALS:
        path = root/config['sources'][name]['path']
        content = path.read_bytes()
        hashes[name] = hashlib.sha256(content).hexdigest()
        paths[name] = path
        adapted = CensusCSV().read(content)
        sources[name] = adapted.frame
        inventory[name] = dict(path=str(path.relative_to(root)),sha256=hashes[name],
            source_rows=adapted.source_rows,capital_rows=len(adapted.frame),
            capital_radios=int(adapted.frame.codigo.nunique()))
        catalog = adapted.frame.groupby(['cod_variable','cod_categoria','categoria'],as_index=False).agg(
            radios=('codigo','nunique'))
        catalog['source'] = name
        categories.append(catalog)
    context, linkage = link_context(master,common,sources,config['sources'])
    report = dict(version=VERSION,reference_year=2022,unit='census_radio',
        cartography=config['sources']['cartography']['path'],
        cartography_evidence='existing_local_config_and_frozen_master_hash; no_geometry_rebuild',
        master_sha256=master_hash,config_sha256=digest(config_path),
        common_manifest_sha256=digest(common_dir/'manifest.json'),
        sources=inventory,linkage=linkage,radios=len(context),common_radios=int(context.common_evaluation.sum()),
        excluded_ids=context.loc[~context.common_evaluation,'radio_id'].tolist(),
        dictionary_status='literal_csv_categories_and_existing_config_only; independent_dictionary_not_found',
        availability_verified=False,training_performed=False,models_modified=False,
        database_status='not_checked',transformation=VERSION)
    mapping = None
    if connection is not None:
        url = json.loads(Path(connection).read_text(encoding='utf-8-sig'))['url']
        with connect(url) as conn:
            conn.set_session(readonly=True)
            mapping, batches = verify_database(conn,context,sources,hashes,master_hash)
        report.update(database_status='checked_read_only',database_batches=batches)
    for name,path in paths.items():
        if digest(path)!=hashes[name]:raise ValueError('census_source_changed')
    if digest(master_path)!=master_hash:raise ValueError('census_master_changed')
    output.mkdir(parents=True)
    context.to_parquet(output/'context.parquet',index=False)
    pd.concat(categories,ignore_index=True).to_csv(output/'category_inventory.csv',index=False)
    if mapping is not None: mapping.to_csv(output/'postgres_linkage.csv',index=False)
    report['outputs_sha256'] = {p.name:digest(p) for p in output.iterdir()}
    (output/'manifest.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output',type=Path,required=True)
    parser.add_argument('--connection',type=Path)
    args = parser.parse_args()
    report = prepare(ROOT,args.output,connection=args.connection)
    print(json.dumps({k:report[k] for k in ('version','radios','common_radios','database_status','training_performed')}))


if __name__=='__main__':
    main()
