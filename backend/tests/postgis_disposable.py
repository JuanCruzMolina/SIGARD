"""Own one tmpfs PostGIS container, verify, and remove only that exact resource.

Run from repository root with backend/.venv/Scripts/python.exe -B.
Never loads .env, Compose, private datasets or trained models.
"""

import json
import os
from pathlib import Path
import secrets
import shutil
import socket
import subprocess
import sys
import time

ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT/"backend"))
from postgis_support import SCHEMA_DB,ADMIN_DB,USER,PORT,validate_url

NAME="sigard-stage17-postgis"
IMAGE="postgis/postgis:17-3.5"
OUTPUT=ROOT/"backend/.tmp/postgis-integration"


def docker(*args,check=True,env=None):
    return subprocess.run(["docker",*args],capture_output=True,text=True,check=check,env=env)


def install_connection_guard():
    from sqlalchemy import event
    from sqlalchemy.engine import Engine
    from psycopg2.extensions import parse_dsn
    def guard(dialect,connection_record,args,params):
        if dialect.name != "postgresql": return
        values={**(parse_dsn(args[0]) if args else {}),**params}
        if (values.get("host")!="127.0.0.1" or int(values.get("port",0))!=PORT
                or values.get("user")!=USER or values.get("dbname") not in (SCHEMA_DB,ADMIN_DB)
                or any(k in values for k in ("service","hostaddr"))):
            raise RuntimeError("PostgreSQL connection outside owned test endpoint blocked before network access")
    event.listen(Engine,"do_connect",guard)


def configure():
    for key in list(os.environ):
        if key.startswith("PG") or key in ("DATABASE_URL","SECRET_KEY","ADMIN_BOOTSTRAP_EMAIL","ADMIN_BOOTSTRAP_PASSWORD"):
            os.environ.pop(key,None)
    marker="sigard-disposable-"+secrets.token_hex(8)
    os.environ.update(SIGARD_POSTGIS_RUN_ID=marker,PGPASSWORD=secrets.token_urlsafe(36),
        POSTGRES_PASSWORD=secrets.token_urlsafe(36),SECRET_KEY=secrets.token_urlsafe(48),
        AUTO_CREATE_SCHEMA="false",REPORT_RATE_LIMIT="1000",ADMIN_LOGIN_RATE_LIMIT="1000")
    os.environ["POSTGRES_PASSWORD"]=os.environ["PGPASSWORD"]
    for key,database in (("SIGARD_POSTGIS_URL",SCHEMA_DB),("SIGARD_TEST_POSTGRES_URL",ADMIN_DB)):
        os.environ[key]=f"postgresql+psycopg2://{USER}@127.0.0.1:{PORT}/{database}"
        validate_url(os.environ[key])
    os.environ["DATABASE_URL"]=os.environ["SIGARD_POSTGIS_URL"]
    from app.config import Settings,get_settings
    Settings.model_config["env_file"]=None
    get_settings.cache_clear()
    install_connection_guard()
    return marker


def main():
    OUTPUT.mkdir(parents=True,exist_ok=True)
    attempt=1+len(list(OUTPUT.glob("receipt-*.json")))
    receipt={"port":PORT,"bind":"127.0.0.1","image":IMAGE,"private_data_used":False,"dotenv_used":False,
             "cleanup_verified":False,"postgres_5432_connections":0,"tests_exit_code":None}
    container_id=None
    vite=None
    try:
        if subprocess.check_output(["git","branch","--show-current"],cwd=ROOT,text=True).strip()!="entrenamiento-ML":
            raise RuntimeError("Wrong branch")
        with socket.socket() as probe:
            probe.bind(("127.0.0.1",PORT))
        if docker("ps","-a","--filter",f"name=^/{NAME}$","--format","{{.Names}}").stdout.strip():
            raise RuntimeError("Container name already exists; refusing to reuse or remove it")
        docker("image","inspect",IMAGE,"--format","{{.Id}}")
        marker=configure()
        result=docker("run","--detach","--rm","--pull=never","--name",NAME,
            "--label",f"sigard.integration={marker}","--restart=no","--publish",f"127.0.0.1:{PORT}:5432",
            "--tmpfs","/var/lib/postgresql/data:rw","--env","POSTGRES_PASSWORD",
            "--env",f"POSTGRES_USER={USER}","--env",f"POSTGRES_DB={SCHEMA_DB}",IMAGE,
            "postgres","-c",f"cluster_name={marker}")
        container_id=result.stdout.strip()
        info=json.loads(docker("inspect",container_id).stdout)[0]
        receipt["instance_checks"]={
            "owned_identity":info["Name"]=="/"+NAME and info["Config"]["Labels"]["sigard.integration"]==marker,
            "exclusive_loopback_port":info["HostConfig"]["PortBindings"]=={"5432/tcp":[{"HostIp":"127.0.0.1","HostPort":str(PORT)}]},
            "no_shared_binds":not info["HostConfig"].get("Binds") and not info["HostConfig"].get("VolumesFrom"),
            "tmpfs_only":info["HostConfig"].get("Tmpfs")=={"/var/lib/postgresql/data":"rw"} and
                all(m["Type"]=="tmpfs" and m["Destination"]=="/var/lib/postgresql/data" for m in info["Mounts"]),
        }
        if not all(receipt["instance_checks"].values()):
            raise RuntimeError("Disposable container isolation check failed")
        # Inspect output with environment values is kept only in memory and never logged.
        from postgis_support import checked_engine
        deadline=time.monotonic()+45
        while True:
            try:
                engine=checked_engine(os.environ["SIGARD_POSTGIS_URL"])
                break
            except Exception:
                if time.monotonic()>deadline: raise RuntimeError("Disposable cluster did not become ready") from None
                time.sleep(.3)
        from sqlalchemy import text
        with engine.connect() as db:
            receipt["postgresql"]=db.scalar(text("SHOW server_version"))
            receipt["postgis"]=db.scalar(text("SELECT postgis_full_version()"))
        with engine.connect().execution_options(isolation_level="AUTOCOMMIT") as db:
            db.execute(text(f'CREATE DATABASE "{ADMIN_DB}" TEMPLATE template0'))
        engine.dispose()
        print("Isolated PostgreSQL/PostGIS ready on loopback 5435; starting tests.",flush=True)
        import pytest
        receipt["tests_exit_code"]=int(pytest.main([
            "backend/tests/test_postgis_integration.py","backend/tests/test_admin_accounts.py","backend/tests/test_citizen_reports.py",
            "-q","-x","-p","no:cacheprovider","--basetemp",str(OUTPUT/"pytest"),
            "--junitxml",str(OUTPUT/f"pytest-{attempt}.xml"),"--tb=short",
        ]))
        if receipt["tests_exit_code"]==0 and "--browser" in sys.argv:
            # Tests completed; browser starts with a clean fictitious store.
            from postgis_support import reset_schema
            engine=checked_engine(os.environ["SIGARD_POSTGIS_URL"])
            reset_schema(engine)
            engine.dispose()
            browser_env=dict(os.environ,SIGARD_POSTGIS_BROWSER="1",SIGARD_BROWSER_FRONTEND_URL="http://127.0.0.1:5174")
            browser_env["VITE_API_URL"]="http://localhost:8000"
            with socket.socket() as probe:
                probe.bind(("127.0.0.1",5174))
            vite=subprocess.Popen(["node","frontend/node_modules/vite/bin/vite.js","frontend","--host","127.0.0.1","--port","5174","--strictPort"],
                cwd=ROOT,env=browser_env,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,
                creationflags=subprocess.CREATE_NO_WINDOW if os.name=="nt" else 0)
            from urllib.request import urlopen
            deadline=time.monotonic()+20
            while True:
                if vite.poll() is not None: raise RuntimeError("Owned test Vite exited")
                try:
                    with urlopen("http://127.0.0.1:5174/prevencion",timeout=1): break
                except OSError:
                    if time.monotonic()>deadline: raise RuntimeError("Owned test Vite did not start")
                    time.sleep(.2)
            receipt["browser_exit_code"]=subprocess.run(["node","frontend/scripts/admin-accounts.browser.mjs"],cwd=ROOT,env=browser_env).returncode
    except Exception as exc:
        # Never print subprocess stderr/args or exception strings containing credentials.
        receipt["blocked_or_failed"]=type(exc).__name__
        print("Disposable integration stopped:",type(exc).__name__,flush=True)
    finally:
        if vite:
            vite.terminate()
            vite.wait(timeout=10)
        if container_id:
            current=docker("inspect","--format",'{{.Id}} {{index .Config.Labels "sigard.integration"}}',container_id,check=False)
            if current.returncode==0 and current.stdout.strip()==container_id+" "+os.environ["SIGARD_POSTGIS_RUN_ID"]:
                docker("stop",container_id)
                receipt["cleanup_verified"]=docker("inspect",container_id,check=False).returncode!=0
        for key in ("PGPASSWORD","POSTGRES_PASSWORD","SECRET_KEY","DATABASE_URL","SIGARD_POSTGIS_URL","SIGARD_TEST_POSTGRES_URL","SIGARD_POSTGIS_RUN_ID"):
            os.environ.pop(key,None)
        (OUTPUT/"receipt.json").write_text(json.dumps(receipt,indent=2),encoding="utf-8")
        (OUTPUT/f"receipt-{attempt}.json").write_text(json.dumps(receipt,indent=2),encoding="utf-8")
        temporary=(OUTPUT/"pytest").resolve()
        if temporary.parent==OUTPUT.resolve() and temporary.is_dir() and not temporary.is_symlink():
            shutil.rmtree(temporary)
        print(json.dumps(receipt),flush=True)
    return 0 if receipt["tests_exit_code"]==0 and receipt["cleanup_verified"] and receipt.get("browser_exit_code",0)==0 else 1


if __name__=="__main__":
    raise SystemExit(main())
