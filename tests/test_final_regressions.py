import os, sys, tempfile
ROOT=os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT,'pipelines'))
from pipeline_common import diff_items, stable_business_key
from mobile import snapshot

def m(id_, name='同名套餐', fee='39元', plan='A'):
    return {'id':id_, 'name':name, 'fields':{'资费类型':'套餐','归属':'全国','资费标准':fee,'方案编号':plan}}

# reportNo-only changes should still be modified when business name/category is stable
old={'id':'1','title':'套餐A','fee':'39','firstLevel':'套餐','secondLevel':'普通','detail':{'reportNo':'R1','commonData':'30GB'}}
new={'id':'2','title':'套餐A','fee':'49','firstLevel':'套餐','secondLevel':'普通','detail':{'reportNo':'R2','commonData':'50GB'}}
r=diff_items([old],[new]); assert (len(r['added_items']),len(r['removed_items']),len(r['modified_items']))==(0,0,1)
# duplicate identities are paired one-to-one
r=diff_items([old|{'id':'3','fee':'59'}, old|{'id':'4','fee':'69'}],[new|{'id':'5','fee':'59'}, new|{'id':'6','fee':'79'}])
assert len(r['modified_items'])==2 and not r['added_items'] and not r['removed_items']
# mobile duplicate-safe diff
r=snapshot.diff([m('1',fee='39'),m('2',fee='59')],[m('3',fee='49'),m('4',fee='69')])
assert len(r['modified'])==2 and not r['added'] and not r['removed']
# mobile real add/remove with distinct business names
r=snapshot.diff([m('1',name='旧套餐',plan='OLD')],[m('2',name='新套餐',plan='NEW')])
assert len(r['added'])==1 and len(r['removed'])==1 and not r['modified']
print('FINAL REGRESSIONS: PASS')
