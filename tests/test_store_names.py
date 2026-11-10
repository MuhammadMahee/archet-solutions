"""Renaming a store preserves identity, import matching, and original audit data."""
from copy import deepcopy

from api.store_names import store_name, store_labels
from api.store_hours_directory import map_schedule_rows


def test_canonical_labels_only_change_store_fields():
    history={'store':'109 MARTHA ST SUITE 227','before_data':{'store':'Martha','employee':'MARTHA',
             'cell_overrides':{'store':'109 MARTHA ST SUITE 227'},'punches':[{'store':'EULESS'}]},'remark':'MARTHA'}
    original=deepcopy(history)
    rendered=store_labels(history)
    assert rendered['store']=='EULESS'
    assert rendered['before_data']['cell_overrides']['store']==rendered['store']
    assert rendered['before_data']['punches'][0]['store']==rendered['store']
    assert rendered['before_data']['employee']=='MARTHA' and rendered['remark']=='MARTHA'
    assert history==original
    assert store_name(' euless ')==rendered['store']
    assert store_name('109 MARTHA ST SUITE 227')==rendered['store']
    assert store_name('EULESS EAST')=='EULESS EAST'


def test_old_and_new_schedule_names_map_to_same_store_id():
    old={'carrier':'TOTAL WIRELESS','company':'ARBF','market':'TOTAL','store':'109 MARTHA ST SUITE 227'}
    new={**old,'store':store_name(old['store'])}
    first=map_schedule_rows([old],[])[0]
    second=map_schedule_rows([new],[])[0]
    assert first['store_id']==second['store_id']=='WB-4cf8ebe635f5c58dabb8aa0b'
    existing={**old,'dealer':'ARBF','store_id':first['store_id'],'source_id':None}
    matched=map_schedule_rows([new],[existing])[0]
    assert matched['action']=='Update' and matched['store_id']==first['store_id']
