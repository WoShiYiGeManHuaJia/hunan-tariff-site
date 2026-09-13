import sys
sys.path.insert(0, 'pipelines')
from pipeline_common import diff_items

def item(id_, fee='39元', data='30GB', report='R1'):
    return {'id': id_, 'title': 'A套餐', 'fee': fee, 'firstLevel': '套餐', 'secondLevel': '普通',
            'detail': {'reportNo': report, 'commonData': data, 'serviceContent': '权益'}}

def test_field_change_same_id():
    r = diff_items([item('A')], [item('A', data='50GB')])
    assert len(r['added_items']) == 0 and len(r['removed_items']) == 0 and len(r['modified_items']) == 1
    assert {x['field'] for x in r['modified_details']['A套餐']} == {'commonData'}

def test_price_change_id_drift():
    r = diff_items([item('A')], [item('B', fee='49元')])
    assert len(r['added_items']) == 0 and len(r['removed_items']) == 0 and len(r['modified_items']) == 1
    assert any(x['field'] == 'fee' for x in r['modified_details']['A套餐'])

def test_real_add_remove():
    r = diff_items([item('A')], [item('B', report='R2', fee='99元')])
    assert len(r['added_items']) == 1 and len(r['removed_items']) == 1 and len(r['modified_items']) == 0
