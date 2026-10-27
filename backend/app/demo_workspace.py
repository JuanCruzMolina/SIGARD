"""Fictional thesis workspace, attached ONLY by the disposable demo factory.

No private artifact/source readers, trained models, geocoders or network calls.
All routes require the existing DB-verified administrator role. State and audit
live in the same owned SQLite and are deleted with its session.
"""
import csv
from datetime import date, datetime, timedelta, timezone
import io
import json
import uuid

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import Column, Integer, JSON, MetaData, String, Table, insert, select, update
from sqlalchemy.orm import Session
from typing import Literal

from .database import get_db
from .models import User
from .security import get_current_admin

RADIOS = tuple(f'D{i:02d}' for i in range(1, 7))
WEEKS = tuple(date(2024, 3, 3)+timedelta(weeks=i) for i in range(8))
TARGETS = WEEKS[-3:]
VERSION = 'fictional-thesis-contract-1'
metadata = MetaData()
state = Table('demo_workspace_state', metadata, Column('key', String(80), primary_key=True), Column('value', JSON, nullable=False))
audit = Table('demo_workspace_audit', metadata, Column('id', Integer, primary_key=True),
              Column('actor_id', Integer, nullable=False), Column('action', String(40), nullable=False),
              Column('created_at', String(40), nullable=False), Column('details', JSON, nullable=False))


class DemoInput(BaseModel):
    model_config = ConfigDict(extra='forbid')


class ImportInput(DemoInput):
    marker: Literal['SIGARD_FICTIONAL_V1']
    csv_text: str = Field(max_length=12000)


class AlertRule(DemoInput):
    name: str = Field(min_length=3, max_length=80)
    radio_id: str = 'all'
    horizon: Literal[1, 2, 4] = 1
    threshold: float = Field(ge=0, le=100, allow_inf_nan=False)
    enabled: bool = True


class EvaluateInput(DemoInput):
    target_date: date
    horizon: Literal[1, 2, 4] = 1


class ReviewInput(DemoInput):
    candidate_id: str = Field(max_length=40)


def fixture_csv():
    stream=io.StringIO()
    writer=csv.writer(stream,lineterminator='\n')
    writer.writerow(['week_start','radio_id','count'])
    for index,week in enumerate(WEEKS):
        for i,radio in enumerate(RADIOS):
            value='' if radio=='D06' or (radio=='D05' and index%2==0) else (index+2*i)%5
            writer.writerow([week.isoformat(),radio,value])
    return stream.getvalue()


def parse_fixture(text):
    try:
        reader=csv.DictReader(io.StringIO(text),strict=True)
        if reader.fieldnames!=['week_start','radio_id','count']:
            raise ValueError()
        result={}
        for row in reader:
            if set(row)!=set(reader.fieldnames) or None in row.values():
                raise ValueError()
            week=date.fromisoformat(row['week_start'])
            radio=row['radio_id']
            key=f'{week}:{radio}'
            if week not in WEEKS or radio not in RADIOS or key in result:
                raise ValueError()
            value=row['count']
            if value!='' and (not value.isascii() or not value.isdigit() or len(value)>2):
                raise ValueError()
            result[key]=int(value) if value!='' else None
        if len(result)!=len(WEEKS)*len(RADIOS):
            raise ValueError()
        return result
    except (ValueError,csv.Error,TypeError):
        raise HTTPException(422,'Lote ficticio inválido: usá las 48 claves del ejemplo, conteos enteros 0–99 o vacíos. No se aceptan datos personales.') from None


def read_state(db,key,default):
    value=db.scalar(select(state.c.value).where(state.c.key==key))
    return default if value is None else value


def save_state(db,key,value):
    if db.scalar(select(state.c.key).where(state.c.key==key)) is None:
        db.execute(insert(state).values(key=key,value=value))
    else:
        db.execute(update(state).where(state.c.key==key).values(value=value))


def record(db,admin,action,details):
    db.execute(insert(audit).values(actor_id=admin.id,action=action,
        created_at=datetime.now(timezone.utc).isoformat(),details=details))


def query_fixture(counts,target_date,horizon,method):
    target=target_date-timedelta(days=(target_date.weekday()+1)%7)
    origin=target-timedelta(weeks=horizon)
    available=target in TARGETS
    rows=[]
    for radio in RADIOS:
        recent=counts.get(f'{origin-timedelta(weeks=1)}:{radio}') if available else None
        history=[v for k,v in counts.items() if k.endswith(f':{radio}') and date.fromisoformat(k[:10])<origin and v is not None] if available else []
        expected=recent if recent is not None else sum(history)/len(history) if history else None
        # Explicitly illustrative response contract; NEVER invokes real V3.
        if method=='v3_experimental' and expected is not None:
            expected=float(expected)+.25
        status='insufficient_data' if expected is None else 'available' if recent is not None else 'available_with_historical_mean_fallback'
        rows.append(dict(radio_id=radio,expected_count=expected,estimate_status=status,
            available_features=0 if expected is None else 2 if recent is None else 3))
    known=[r['expected_count'] for r in rows if r['expected_count'] is not None]
    return dict(fictional=True,dataset_version=VERSION,model_version=f'fixture-{method}',
        method=method,probability_available=False,model_executed=False,
        target_week=target.isoformat(),target_end=(target+timedelta(days=6)).isoformat(),
        origin_week=origin.isoformat(),information_cutoff=(origin+timedelta(days=6)).isoformat(),horizon=horizon,
        status='available' if available else 'insufficient_data',radios=rows,
        expected_eligible_total=sum(known) if known else None,total_city=None,
        eligible_radios=len(known),radios_without_estimate=len(rows)-len(known))


def attach_demo_workspace(app):
    if app.state.engine.url.get_backend_name()!='sqlite':
        raise RuntimeError('El espacio ficticio exige SQLite de demo')
    metadata.create_all(app.state.engine)
    router=APIRouter(prefix='/api/v1/admin/demo',tags=['demo ficticia'])

    @router.get('/catalog')
    def catalog(_:User=Depends(get_current_admin)):
        features=[]
        for i,radio in enumerate(RADIOS):
            x,y=(i%3)*.02,(i//3)*.02
            features.append(dict(type='Feature',properties=dict(radio_id=radio),geometry=dict(type='Polygon',
                coordinates=[[[x,y],[x+.018,y],[x+.018,y+.018],[x,y+.018],[x,y]]])))
        return dict(fictional=True,dataset_version=VERSION,radios=RADIOS,horizons=[1,2,4],
            target_weeks=[w.isoformat() for w in TARGETS],fixture_csv=fixture_csv(),
            geometry=dict(type='FeatureCollection',features=features))

    @router.get('/query')
    def query(target_date:date,horizon:int=Query(default=1,ge=1,le=4),method:Literal['persistence','v3_experimental']='persistence',
              radio_id:str|None=Query(default=None,max_length=10),db:Session=Depends(get_db),admin:User=Depends(get_current_admin)):
        if horizon not in (1,2,4):
            raise HTTPException(422,'Horizonte inválido: usá 1, 2 o 4 semanas')
        if radio_id is not None and radio_id not in RADIOS:
            raise HTTPException(422,'Radio ficticio desconocido')
        result=query_fixture(read_state(db,'counts',parse_fixture(fixture_csv())),target_date,horizon,method)
        result['selected_radio_id']=radio_id
        record(db,admin,'query',dict(target_date=str(target_date),horizon=horizon,method=method,radio_id=radio_id))
        db.commit()
        return result

    @router.post('/ingestion')
    def ingest(payload:ImportInput,db:Session=Depends(get_db),admin:User=Depends(get_current_admin)):
        counts=parse_fixture(payload.csv_text)
        save_state(db,'counts',counts)
        save_state(db,'candidates',[])
        known=sum(v is not None for v in counts.values())
        record(db,admin,'ingestion',dict(rows=len(counts),known=known))
        db.commit()
        return dict(fictional=True,rows=len(counts),known=known,unknown=len(counts)-known,raw_modified=False)

    @router.get('/alerts')
    def alerts(db:Session=Depends(get_db),_:User=Depends(get_current_admin)):
        return dict(rules=read_state(db,'rules',[]),candidates=read_state(db,'candidates',[]),official=False)

    @router.post('/alerts',status_code=201)
    def create_rule(payload:AlertRule,db:Session=Depends(get_db),admin:User=Depends(get_current_admin)):
        if payload.radio_id not in ('all',*RADIOS):
            raise HTTPException(422,'Radio ficticio desconocido')
        rules=read_state(db,'rules',[])
        if len(rules)>=20:
            raise HTTPException(409,'La demo admite hasta 20 reglas')
        rule=dict(payload.model_dump(),id=str(uuid.uuid4()))
        save_state(db,'rules',[*rules,rule])
        save_state(db,'candidates',[])
        record(db,admin,'alert_create',dict(rule_id=rule['id']))
        db.commit()
        return rule

    @router.patch('/alerts/{rule_id}')
    def change_rule(rule_id:str,payload:AlertRule,db:Session=Depends(get_db),admin:User=Depends(get_current_admin)):
        if payload.radio_id not in ('all',*RADIOS):
            raise HTTPException(422,'Radio ficticio desconocido')
        rules=read_state(db,'rules',[])
        if not any(r['id']==rule_id for r in rules):
            raise HTTPException(404,'Regla no encontrada')
        rule=dict(payload.model_dump(),id=rule_id)
        save_state(db,'rules',[rule if r['id']==rule_id else r for r in rules])
        save_state(db,'candidates',[])
        record(db,admin,'alert_update',dict(rule_id=rule_id))
        db.commit()
        return rule

    @router.post('/alerts/evaluate')
    def evaluate(payload:EvaluateInput,db:Session=Depends(get_db),admin:User=Depends(get_current_admin)):
        result=query_fixture(read_state(db,'counts',parse_fixture(fixture_csv())),payload.target_date,payload.horizon,'persistence')
        if result['status']!='available':
            save_state(db,'candidates',[])
            record(db,admin,'alert_no_data',dict(target_date=str(payload.target_date),horizon=payload.horizon))
            db.commit()
            raise HTTPException(409,'Sin datos ficticios para evaluar esta fecha; no se generan alertas')
        candidates=[]
        for rule in read_state(db,'rules',[]):
            if not rule['enabled'] or rule['horizon']!=payload.horizon:
                continue
            for row in result['radios']:
                if rule['radio_id'] in ('all',row['radio_id']) and row['expected_count'] is not None and row['expected_count']>=rule['threshold']:
                    candidates.append(dict(id=str(uuid.uuid4()),rule_id=rule['id'],rule_name=rule['name'],
                        radio_id=row['radio_id'],expected_count=row['expected_count'],target_week=result['target_week'],
                        threshold=rule['threshold'],status='experimental_candidate',official=False))
        save_state(db,'candidates',candidates)
        record(db,admin,'alert_evaluate',dict(candidate_count=len(candidates)))
        db.commit()
        return dict(candidates=candidates,official=False)

    @router.post('/alerts/review')
    def review(payload:ReviewInput,db:Session=Depends(get_db),admin:User=Depends(get_current_admin)):
        candidates=read_state(db,'candidates',[])
        if not any(c['id']==payload.candidate_id for c in candidates):
            raise HTTPException(404,'Candidata no encontrada')
        for candidate in candidates:
            if candidate['id']==payload.candidate_id:
                candidate['status']='reviewed_demo'
        save_state(db,'candidates',candidates)
        record(db,admin,'alert_review',dict(candidate_id=payload.candidate_id))
        db.commit()
        return dict(candidates=candidates,official=False,notifications_sent=0)

    @router.get('/audit')
    def audit_history(db:Session=Depends(get_db),_:User=Depends(get_current_admin)):
        rows=db.execute(select(audit.c.action,audit.c.created_at,audit.c.details).order_by(audit.c.id.desc()).limit(30)).mappings()
        return dict(items=[dict(row) for row in rows])

    app.include_router(router)
