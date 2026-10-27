"""Contract/security checks with fictitious inputs in one owned temporary SQLite."""
from pathlib import Path
import os
import sys
from tempfile import TemporaryDirectory
from contextlib import ExitStack

BACKEND=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(BACKEND))


def main():
    from app.demo_local import create_demo_app,checked_directory
    with TemporaryDirectory(prefix='sigard-demo-',dir=BACKEND/'.tmp') as directory, ExitStack() as cleanup:
        os.chdir(directory)
        cleanup.callback(os.chdir,BACKEND)
        app,credentials=create_demo_app(checked_directory(directory))
        cleanup.callback(app.state.engine.dispose)
        from app import config
        from app.models import User
        from app.security import create_access_token,hash_password
        from app.main import create_app
        from app.demo_workspace import fixture_csv,parse_fixture
        from fastapi import HTTPException
        from fastapi.testclient import TestClient
        checks=0
        def check(condition):
            nonlocal checks
            assert condition
            checks+=1
        with TestClient(app) as client:
            base='/api/v1/admin/demo'
            for path in ['/catalog','/query?target_date=2024-04-07','/alerts','/audit']:
                check(client.get(base+path).status_code==401)
            token=client.post('/api/v1/admin/session',json={k:credentials[k] for k in ('email','password')}).json()['access_token']
            headers={'Authorization':f'Bearer {token}'}
            with app.state.SessionLocal() as db:
                user=User(email='fictional-citizen@example.test',password_hash=hash_password('fictional-passphrase'),rol='user')
                db.add(user); db.commit(); db.refresh(user)
                user_token=create_access_token(user,config.get_settings())
            check(client.get(base+'/catalog',headers={'Authorization':f'Bearer {user_token}'}).status_code==403)
            catalog=client.get(base+'/catalog',headers=headers).json()
            check(catalog['fictional'] and len(catalog['geometry']['features'])==6)
            for horizon in (1,2,4):
                response=client.get(base+f'/query?target_date=2024-04-07&horizon={horizon}',headers=headers)
                result=response.json()
                check(response.status_code==200 and result['method']=='persistence' and result['horizon']==horizon)
                check(result['probability_available'] is False and result['model_executed'] is False and result['total_city'] is None)
                check(result['radios'][-1]['expected_count'] is None and result['radios'][-1]['estimate_status']=='insufficient_data')
            result=client.get(base+'/query?target_date=2024-04-08&method=v3_experimental&radio_id=D01',headers=headers).json()
            check(result['target_week']=='2024-04-07' and result['model_version']=='fixture-v3_experimental' and result['selected_radio_id']=='D01')
            result=client.get(base+'/query?target_date=2026-10-26',headers=headers).json()
            check(result['status']=='insufficient_data' and result['expected_eligible_total'] is None and all(r['expected_count'] is None for r in result['radios']))
            for query in ('target_date=invalid','target_date=2024-04-07&horizon=3','target_date=2024-04-07&radio_id=REAL','target_date=2024-04-07&method=other'):
                response=client.get(base+'/query?'+query,headers=headers)
                check(response.status_code==422 and 'input' not in response.text)
            for text in ('week_start,radio_id,count,person\n2024-04-07,D01,1,forbidden',fixture_csv().replace(',D01,',',REAL,'),fixture_csv()+'2024-04-07,D01,1\n',fixture_csv().replace('2024-03-03,D01,0','2024-03-03,D01,-1')):
                check(client.post(base+'/ingestion',headers=headers,json={'marker':'SIGARD_FICTIONAL_V1','csv_text':text}).status_code==422)
            response=client.post(base+'/ingestion',headers=headers,json={'marker':'SIGARD_FICTIONAL_V1','csv_text':fixture_csv()})
            check(response.status_code==200 and response.json()['rows']==48 and response.json()['unknown']>0)
            check(sum(v is None for v in parse_fixture(fixture_csv()).values())==response.json()['unknown'])
            rule=dict(name='Regla completamente ficticia',radio_id='all',horizon=1,threshold=0,enabled=True)
            check(client.post(base+'/alerts',json=rule).status_code==401)
            check(client.post(base+'/alerts',headers=headers,json=dict(rule,threshold=-1)).status_code==422)
            check(client.post(base+'/alerts',headers=headers,json=dict(rule,radio_id='REAL')).status_code==422)
            created=client.post(base+'/alerts',headers=headers,json=rule)
            check(created.status_code==201)
            identity=created.json()['id']
            evaluated=client.post(base+'/alerts/evaluate',headers=headers,json=dict(target_date='2024-04-07',horizon=1)).json()
            check(len(evaluated['candidates'])==5 and evaluated['official'] is False)
            check(all(c['radio_id']!='D06' and c['status']=='experimental_candidate' for c in evaluated['candidates']))
            candidate=evaluated['candidates'][0]['id']
            response=client.post(base+'/alerts/review',headers=headers,json=dict(candidate_id=candidate))
            check(response.status_code==200 and response.json()['notifications_sent']==0)
            check(client.get(base+'/alerts',headers=headers).json()['candidates'][0]['status']=='reviewed_demo')
            check(client.post(base+'/alerts/evaluate',headers=headers,json=dict(target_date='2026-10-26',horizon=1)).status_code==409)
            check(client.get(base+'/alerts',headers=headers).json()['candidates']==[])
            check(client.patch(base+f'/alerts/{identity}',headers=headers,json=dict(rule,enabled=False)).status_code==200)
            check(client.post(base+'/alerts/evaluate',headers=headers,json=dict(target_date='2024-04-07',horizon=1)).json()['candidates']==[])
            history=client.get(base+'/audit',headers=headers).json()['items']
            check(any(event['action']=='alert_review' for event in history))
            check('password' not in str(history) and 'access_token' not in str(history))
            # UI storage is irrelevant: forged/expired tokens never grant access.
            check(client.get(base+'/catalog',headers={'Authorization':'Bearer fictional-forged-token'}).status_code==401)
            with app.state.SessionLocal() as db:
                admin=db.get(User,1); admin.token_version+=1; db.commit()
            check(client.get(base+'/catalog',headers=headers).status_code==401)
            check(app.state.engine.url.get_backend_name()=='sqlite')
        production=create_app(database_url=str(app.state.engine.url),auto_create_schema=False)
        with TestClient(production) as client:
            check(client.get('/api/v1/admin/demo/catalog').status_code==404)
        production.state.engine.dispose()
        app.state.engine.dispose()
        os.chdir(BACKEND)
    print(f'Fictional workspace: {checks} contract/security assertions passed; no ML or PostgreSQL')


if __name__=='__main__':
    main()
