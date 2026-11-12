"""Private SISA ingestion CLI. No source reads at normal API startup."""
import argparse
import json
from pathlib import Path
import sys

from sigard_ml.ingestion.epidemiology.reader import resolve_sources,read_book,profile,ROOT

def private_output(path):
    p=Path(path).resolve()
    allowed=(ROOT/'data/interim/official').resolve()
    if not p.is_relative_to(allowed) or p.exists():raise ValueError('new_private_report_path_required')
    p.parent.mkdir(parents=True,exist_ok=True)
    return p

def validate_db(conn):
    from sigard_ml.ingestion.epidemiology.reader import VERSION
    import hashlib
    with conn.cursor() as cur:
        cur.execute('''SELECT a.nombre_original,a.sha256,a.bytes,a.contenido_original,l.filas_leidas,l.filas_normalizadas,
            count(DISTINCT s.id),count(DISTINCT r.id) FROM ingestion.archivo_fuente a JOIN ingestion.lote_importacion l ON l.archivo_id=a.id
            LEFT JOIN ingestion.fila_staging s ON s.lote_id=l.id LEFT JOIN epidemiology.registro_epidemiologico r ON r.fila_id=s.id
            GROUP BY a.id,l.id''')
        files=[]
        for name,sha,size,raw,read,normalized,staged,records in cur.fetchall():
            valid=len(raw)==size and hashlib.sha256(bytes(raw)).hexdigest()==sha and read==normalized==staged==records
            files.append(dict(name=name,read=read,normalized=normalized,preserved=staged,records=records,raw_archive_hash_valid=valid))
        cur.execute("SELECT count(*) FROM information_schema.tables WHERE table_schema IN ('ingestion','epidemiology','territory','analytics') AND table_type='BASE TABLE'")
        tables=cur.fetchone()[0]
        cur.execute("SELECT count(*) FROM information_schema.table_constraints WHERE constraint_type='FOREIGN KEY' AND table_schema IN ('ingestion','epidemiology','territory','analytics')")
        fks=cur.fetchone()[0]
        cur.execute('SELECT postgis_full_version()');postgis=cur.fetchone()[0]
        cur.execute('SHOW server_version');postgres=cur.fetchone()[0]
        cur.execute("SELECT count(*) FROM epidemiology.relacion_registro WHERE tipo='same_external_id'");repeated=cur.fetchone()[0]
        cur.execute("SELECT count(*) FROM epidemiology.relacion_registro WHERE tipo='exact_duplicate'");exact=cur.fetchone()[0]
        cur.execute('SELECT codigo,count(*) FROM epidemiology.incidencia_validacion GROUP BY codigo');issues=dict(cur.fetchall())
        cur.execute('SELECT contenido,sha256 FROM ingestion.fila_staging ORDER BY id')
        payloads_checked=0;payload_hashes_valid=True
        for payload,expected in cur:
            actual=hashlib.sha256(json.dumps(payload,ensure_ascii=False,sort_keys=True,allow_nan=False).encode()).hexdigest()
            payloads_checked+=1;payload_hashes_valid=payload_hashes_valid and actual==expected
    return dict(files=files,tables=tables,foreign_keys=fks,postgresql=postgres,postgis=postgis,
        same_external_id_links=repeated,exact_duplicate_links=exact,validation_issues=issues,
        typed_payloads_checked=payloads_checked,typed_payload_hashes_valid=payload_hashes_valid,
        reconciled=all(f['raw_archive_hash_valid'] for f in files) and payload_hashes_valid)

def main():
    parser=argparse.ArgumentParser(description=__doc__)
    mode=parser.add_mutually_exclusive_group(required=True)
    mode.add_argument('--dry-run',action='store_true');mode.add_argument('--apply',action='store_true');mode.add_argument('--validate',action='store_true');mode.add_argument('--migrate',action='store_true')
    mode.add_argument('--load-territory',action='store_true');mode.add_argument('--assign-radios',action='store_true');mode.add_argument('--load-climate',action='store_true')
    parser.add_argument('--source-root');parser.add_argument('--files',nargs='+')
    parser.add_argument('--authorization',help='Private approved file/hash manifest, required for real apply')
    parser.add_argument('--master');parser.add_argument('--master-sha256')
    parser.add_argument('--membership');parser.add_argument('--membership-sha256')
    parser.add_argument('--climate-package');parser.add_argument('--climate-sha256');parser.add_argument('--climate-version')
    parser.add_argument('--report',required=True,help='New path under data/interim/official')
    args=parser.parse_args()
    try:
        report_path=private_output(args.report)
        if args.dry_run or args.apply:
            sources,missing=resolve_sources(args.source_root)
            if args.files:
                root=Path(args.source_root).resolve() if args.source_root else (sources[0].parent if sources else None)
                if root is None:raise ValueError('source_root_required')
                sources=[]
                for name in args.files:
                    p=(root/name).resolve()
                    if p.parent!=root or p.suffix.lower()!='.xlsx':raise ValueError('source_outside_authorized_directory')
                    if p.exists():sources.append(p)
                    else:missing.append(name)
            if args.dry_run:
                report=dict(sources=[profile(read_book(p)) for p in sources],missing=missing,database_written=False)
            else:
                if not args.authorization:raise ValueError('explicit_hash_authorization_required')
                permission=json.loads(Path(args.authorization).read_text(encoding='utf-8-sig'))
                if permission.get('status')!='approved' or permission.get('purpose')!='private_normalized_ingestion' or not permission.get('authorization_ref'):
                    raise ValueError('invalid_authorization')
                from sigard_ml.ingestion.epidemiology.db import connect
                from sigard_ml.ingestion.epidemiology.importer import import_book
                with connect() as conn:
                    imported=[]
                    for source in sources:
                        expected=permission['files'].get(source.name)
                        if not expected or (permission.get('source_root') and source.parent.resolve()!=Path(permission['source_root']).resolve()):
                            imported.append(dict(name=source.name,status='not_authorized'));continue
                        try:imported.append(import_book(conn,source,expected_sha256=expected,metadata=permission.get('source_metadata',{}).get(source.name)))
                        except Exception:imported.append(dict(name=source.name,status='failed_and_rolled_back'))
                    report=dict(imported=imported,missing=missing,database_written=True)
        elif args.load_territory or args.assign_radios or args.load_climate:
            from sigard_ml.ingestion.epidemiology.db import connect
            from sigard_ml.ingestion.epidemiology.reader import digest
            with connect() as conn:
                if args.assign_radios:
                    from sigard_ml.ingestion.epidemiology.territory import assign_radios
                    report=dict(assignments=assign_radios(conn))
                elif args.load_territory:
                    from sigard_ml.ingestion.epidemiology.territory import load_master
                    if not args.master or not args.master_sha256 or digest(args.master)!=args.master_sha256:raise ValueError('authorized_master_hash_required')
                    radios=None
                    if args.membership:
                        import pyarrow.parquet as pq
                        if not args.membership_sha256 or digest(args.membership)!=args.membership_sha256:raise ValueError('authorized_membership_hash_required')
                        radios=set(pq.read_table(args.membership,columns=['radio_id']).column('radio_id').to_pylist())
                    report=load_master(conn,Path(args.master),v3_radios=radios)
                else:
                    from sigard_ml.ingestion.epidemiology.climate import load_climate
                    if not all([args.climate_package,args.climate_sha256,args.climate_version]):raise ValueError('explicit_climate_contract_required')
                    report=load_climate(conn,Path(args.climate_package),expected_sha256=args.climate_sha256,version=args.climate_version)
        else:
            from sigard_ml.ingestion.epidemiology.db import connect,migrate
            if args.migrate:migrate();report=dict(migrations_applied=True)
            else:
                with connect() as conn:report=validate_db(conn)
        report_path.write_text(json.dumps(report,ensure_ascii=False,indent=2,allow_nan=False,default=str),encoding='utf-8')
        partial=bool(report.get('missing')) or any(r.get('status') in ['not_authorized','failed_and_rolled_back'] for r in report.get('imported',[])) or report.get('reconciled') is False
        print(json.dumps(dict(status='partial' if partial else 'complete',private_report_written=True)))
        return 1 if partial else 0
    except Exception:
        # No SQL exceptions, source cell values, URLs, passwords or raw tracebacks.
        print(json.dumps(dict(status='blocked_or_failed',reason='check_local_configuration_or_private_validation')),file=sys.stderr)
        return 1

if __name__=='__main__':raise SystemExit(main())
