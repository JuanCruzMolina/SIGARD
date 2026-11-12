"""Entirely generated census aggregates; abstract codes, no real cartography."""
from datetime import date
import pandas as pd
import pytest

from sigard_ml.ingestion.census_2022 import link_context, attach_asof, verify_database
from sigard_ml.ingestion.epidemiology.complementary import CensusCSV


def census(**changes):
    row = dict(codigo='460149999',cod_prov='46',cod_dep='014',fraccion='99',radio='99',
               cod_variable='FICTIONAL_VARIABLE',cod_categoria='1',categoria='FICTICIA',cantidad='5')
    row.update(changes)
    return pd.DataFrame([row])


def read(frame):
    return CensusCSV().read(frame.to_csv(index=False).encode()).frame


def fixture():
    master = pd.DataFrame(dict(radio_id=['460149999','460149998'],fraccion=['99','99'],radio=['99','98']))
    source = read(pd.concat([census(),census(codigo='460149998',radio='98',cantidad='7')]))
    definitions = {name:dict(variable='FICTIONAL_VARIABLE',output_column=field)
                   for name,field in zip(('population','households','dwellings'),('poblacion','hogares','viviendas'))}
    return master,{name:source.copy() for name in definitions},definitions


def test_normalizes_components_before_filtering_and_rejects_mismatch():
    frame = read(census(cod_dep='14'))
    assert frame.iloc[0].cod_dep=='014'
    with pytest.raises(ValueError,match='component_code_mismatch'):
        read(census(radio='98'))


@pytest.mark.parametrize('changes',[
    {'codigo':'FICTIONAL-KEY'},{'cod_dep':'14.0'},{'radio':''},
    {'cantidad':'-1'},{'cantidad':'1.5'},{'cantidad':'inf'},
    {'categoria':''},{'cod_categoria':''},
])
def test_invalid_source_is_rejected(changes):
    with pytest.raises(ValueError): read(census(**changes))


def test_duplicates_and_conflicting_category_labels_are_rejected():
    with pytest.raises(ValueError,match='duplicate_key'):
        read(pd.concat([census(),census(cod_dep='14')]))
    with pytest.raises(ValueError,match='conflicting_category_labels'):
        read(pd.concat([census(),census(codigo='460149998',radio='98',categoria='OTRA')]))


def test_linkage_preserves_mask_and_reports_missing_without_zero_imputation():
    master,sources,definitions=fixture()
    sources['households']=sources['households'].iloc[:1]
    context,report=link_context(master,['460149999'],sources,definitions)
    excluded=context.set_index('radio_id').loc['460149998']
    assert not excluded.common_evaluation and excluded.exclusion_reason
    assert pd.isna(excluded.hogares_2022)
    assert report['households']['missing_from_source']==['460149998']
    assert context.poblacion_2022.sum()==12
    reversed_context,_=link_context(master.iloc[::-1],['460149999'],sources,definitions)
    pd.testing.assert_frame_equal(context,reversed_context)


def test_nonmaster_codes_reported_and_not_assigned_by_position():
    master,sources,definitions=fixture()
    sources['population']=pd.concat([sources['population'],read(census(codigo='460149997',radio='97'))])
    context,report=link_context(master,['460149999'],sources,definitions)
    assert len(context)==2
    assert report['population']['not_in_cartography']==['460149997']


def test_ambiguous_master_common_and_changed_existing_counts_fail():
    master,sources,definitions=fixture()
    with pytest.raises(ValueError,match='duplicate_territory'):
        link_context(pd.concat([master,master]),[],sources,definitions)
    with pytest.raises(ValueError,match='common_outside_master'):
        link_context(master,['460149997'],sources,definitions)
    master['poblacion']=[99,99]
    with pytest.raises(ValueError,match='existing_master_total_mismatch'):
        link_context(master,[],sources,definitions)


def test_asof_unknown_or_future_release_does_not_leak_into_old_origins():
    master,sources,definitions=fixture()
    context,_=link_context(master,['460149999'],sources,definitions)
    panel=pd.DataFrame(dict(radio_id=['460149999']*3,
        origin_end=[date(2021,6,5),date(2023,6,3),date(2024,6,1)]))
    unknown=attach_asof(panel,context)
    assert unknown.filter(like='_asof').isna().all().all()
    known=attach_asof(panel,context,available_on=date(2023,6,3))
    assert pd.isna(known.iloc[0].poblacion_2022_asof)
    assert known.iloc[1].poblacion_2022_asof==5
    moved=attach_asof(panel,context,available_on=date(2025,1,1))
    assert moved.filter(like='_asof').isna().all().all()
    with pytest.raises(ValueError):attach_asof(panel,context,available_on=date(2021,1,1))
    panel.radio_id=1  # DB surrogate IDs must never be mistaken for census codes.
    with pytest.raises(ValueError):attach_asof(panel,context)


class Cursor:
    def __init__(self, answers): self.answers=iter(answers)
    def __enter__(self):return self
    def __exit__(self,*args):pass
    def execute(self,sql,params=None):
        assert sql.lstrip().startswith('SELECT')
        self.result=next(self.answers)
    def fetchall(self):return self.result


class Connection:
    def __init__(self,answers):self.cur=Cursor(answers)
    def cursor(self):return self.cur


def test_database_links_surrogate_ids_and_reconciles_each_existing_batch():
    master,sources,definitions=fixture()
    context,_=link_context(master,['460149999'],sources,definitions)
    rows=[(42,'460149999','46','014','99','a'*64,True),
          (73,'460149998','46','014','99','a'*64,False)]
    observations=[(42,'460149999','FICTIONAL_VARIABLE','1','FICTICIA',5),
                  (73,'460149998','FICTIONAL_VARIABLE','1','FICTICIA',7)]
    answers=[rows]
    for _ in range(3): answers.extend([[(1,)],observations])
    mapping,batches=verify_database(Connection(answers),context,sources,
                                   {name:'b'*64 for name in sources},'a'*64)
    assert set(mapping.postgres_radio_id)=={42,73}
    assert all(b['verified'] for b in batches.values())
    with pytest.raises(ValueError,match='geometry_version_mismatch'):
        verify_database(Connection([rows]),context,sources,{},'c'*64)
    wrong=[(999,*observations[0][1:]),observations[1]]
    with pytest.raises(ValueError,match='observations_mismatch'):
        verify_database(Connection([rows,[(1,)],wrong]),context,sources,
                        {name:'b'*64 for name in sources},'a'*64)


def test_database_absent_batches_are_not_claimed_as_imported():
    master,sources,definitions=fixture()
    context,_=link_context(master,[],sources,definitions)
    rows=[(42,'460149999','46','014','99','a'*64,False),
          (73,'460149998','46','014','99','a'*64,False)]
    _,batches=verify_database(Connection([rows,[],[],[]]),context,sources,
                             {name:'b'*64 for name in sources},'a'*64)
    assert not any(b['verified'] for b in batches.values())
