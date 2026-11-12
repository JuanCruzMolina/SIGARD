"""Own one manually started WSL PostgreSQL/PostGIS cluster on loopback 55439.

Never reads .env, Docker, API settings or port 5432. Init refuses existing data.
"""
import argparse,json,secrets,subprocess,sys
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
SCRIPT=ROOT/'backend/database/epidemiology/local-cluster.sh'

def linux(path):
    p=Path(path).resolve().as_posix()
    if len(p)<3 or p[1:3]!=':/':raise ValueError('Windows local path required')
    return '/mnt/'+p[0].lower()+p[2:]

def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action',choices=['init','start','stop','status'])
    parser.add_argument('--config',default=str(ROOT/'data/interim/official/database-local-v1/connection.private.json'))
    args=parser.parse_args()
    config=Path(args.config).resolve()
    if not config.is_relative_to(ROOT/'data/interim/official'):raise ValueError('Private configuration path required')
    try:
        extra=[]
        if args.action=='init':
            if config.exists():raise ValueError('Do not overwrite cluster identity')
            config.parent.mkdir(parents=True,exist_ok=True)
            password=secrets.token_urlsafe(36)
            pw=config.parent/'admin-password.private'
            if pw.exists():raise ValueError('Do not overwrite password file')
            pw.write_text(password,encoding='ascii');extra=[linux(pw)]
        result=subprocess.run(['wsl.exe','bash',linux(SCRIPT),args.action,*extra],capture_output=True)
        if result.returncode:raise ValueError('Owned cluster action failed')
        if args.action=='init':
            result=subprocess.run(['wsl.exe','bash',linux(SCRIPT),'start'],capture_output=True)
            if result.returncode:raise ValueError('Owned cluster start failed')
            import psycopg2
            conn=psycopg2.connect(host='127.0.0.1',port=55439,dbname='postgres',user='sigard_epi_owner',password=password,connect_timeout=5)
            conn.autocommit=True
            with conn.cursor() as cur:
                cur.execute('SHOW cluster_name')
                if cur.fetchone()[0]!='sigard-epi-local-v1':raise ValueError('Wrong cluster')
                cur.execute('CREATE DATABASE sigard_epi_local_v1');cur.execute('CREATE DATABASE sigard_epi_test_v1')
            conn.close()
            url=f'postgresql+psycopg2://sigard_epi_owner:{password}@127.0.0.1:55439/sigard_epi_local_v1'
            config.write_text(json.dumps(dict(url=url,test_url=url.replace('sigard_epi_local_v1','sigard_epi_test_v1'))),encoding='utf-8')
        print(json.dumps(dict(status='complete',action=args.action,port=55439,credentials_printed=False)))
        return 0
    except Exception:
        print(json.dumps(dict(status='blocked_or_failed',reason='check_owned_cluster_and_private_configuration')),file=sys.stderr)
        return 1

if __name__=='__main__':raise SystemExit(main())
