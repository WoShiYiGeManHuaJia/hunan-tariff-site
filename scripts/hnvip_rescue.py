import os, json, time, base64, subprocess, urllib.request, urllib.error
CF=os.environ['CF']; PAT=os.environ['PAT']; REPO=os.environ['GITHUB_REPOSITORY']
ACC='9156c2cae565fdf42d208827b523e47e'
PU='https://api.cloudflare.com/client/v4/accounts/'+ACC+'/pages/projects'
GOOD=PU+'/changes-in-carrier-pricing'   # 这个一直 200，配置是对的
BAD=PU+'/hnvip'
L=[]
def log(*a):
    s=' '.join(str(x) for x in a); print(s); L.append(s)
def req(url,method='GET',body=None,timeout=90):
    data=json.dumps(body).encode() if body is not None else None
    r=urllib.request.Request(url,data=data,method=method,
        headers={'Authorization':'Bearer '+CF,'Content-Type':'application/json','User-Agent':'hnvip-rescue/1.0'})
    resp=urllib.request.urlopen(r,timeout=timeout); raw=resp.read()
    try: return resp.status,json.loads(raw)
    except Exception: return resp.status,(raw.decode('utf8','replace')[:300] if raw else '')
def err(e):
    try:return e.code,e.read().decode('utf8','replace')[:300]
    except Exception:return e.code,''

# 1. 取健康项目的 source 作模板
st,d=req(GOOD)
good=(d.get('result') or {}) if isinstance(d,dict) else {}
src=good.get('source') or {}
cfg=dict(src.get('config') or {})
log('GOOD source.type',src.get('type'),'repo',cfg.get('repo_name'),'repo_id',cfg.get('repo_id'),
    'prod',cfg.get('production_deployments_enabled'))
log('GOOD build_config',json.dumps(good.get('build_config'),ensure_ascii=False)[:200])

# 2. 把 hnvip 改绑到同一仓库（根因：之前被绑到 repo_id=1438392194，push 全空构建 → 500）
new_cfg={'owner':'WoShiYiGeManHuaJia','repo_name':'hunan-tariff-site',
         'production_branch':'main','pr_comments_enabled':False,
         'deployments_enabled':True,'production_deployments_enabled':True,
         'preview_deployment_setting':'none'}
for k in ('owner_id','repo_id'):
    if cfg.get(k): new_cfg[k]=cfg[k]
payload={'name':'hnvip','source':{'type':'github','config':new_cfg},
         'build_config':good.get('build_config') or {'build_command':'','destination_dir':'','root_dir':''}}
try:
    st,d=req(BAD,'PATCH',payload); log('PATCH',st,str(d)[:500])
except urllib.error.HTTPError as e: log('PATCH HTTP',*err(e))
except Exception as e: log('PATCH ERR',str(e)[:200])
time.sleep(5)
try:
    st,d=req(BAD); p=(d.get('result') or {}) if isinstance(d,dict) else {}
    c2=(p.get('source') or {}).get('config') or {}
    log('AFTER type',(p.get('source') or {}).get('type'),'repo_id',c2.get('repo_id'),
        'repo',c2.get('repo_name'),'prod',c2.get('production_deployments_enabled'))
except urllib.error.HTTPError as e: log('AFTER HTTP',*err(e))

# 3. 触发一次生产构建
try:
    st,d=req(BAD+'/deployments','POST',{'branch':'main'}); log('BUILD',st,str(d)[:400])
    dep=((d.get('result') or {}) if isinstance(d,dict) else {}).get('id')
except urllib.error.HTTPError as e: log('BUILD HTTP',*err(e)); dep=None
except Exception as e: log('BUILD ERR',str(e)[:200]); dep=None

# 4. 轮询 + 线上验证
def probe():
    try:
        r=subprocess.run(['curl','-sS','-o','/dev/null','-w','%{http_code}','-L','--max-time','30',
                          'https://hnvip.pages.dev/'],capture_output=True,text=True,timeout=40)
        return int((r.stdout or '0').strip() or 0)
    except Exception: return 0
def read_upd():
    try:
        r=subprocess.run(['curl','-sS','-L','--max-time','35','-H','Cache-Control: no-cache',
                          'https://hnvip.pages.dev/data/latest.json?_='+str(time.time_ns())],
                         capture_output=True,text=True,timeout=50)
        return json.loads(r.stdout).get('updated','?')
    except Exception: return '?'
for i in range(18):
    time.sleep(15)
    code=probe(); upd=read_upd()
    log('CHECK',i,'http',code,'online',upd)
    if code==200 and upd!='?': break
log('FINAL http',code,'online',upd)

txt='\n'.join(L)+'\n'
url='https://api.github.com/repos/'+REPO+'/contents/hnvip_rescue_log.txt'
def gh(method,body_):
    r=urllib.request.Request(url,data=json.dumps(body_).encode(),method=method,
        headers={'Authorization':'token '+PAT,'User-Agent':'x','Accept':'application/vnd.github+json','Content-Type':'application/json'})
    resp=urllib.request.urlopen(r,timeout=60); raw=resp.read()
    return json.loads(raw) if raw else {}
sha=None
try: sha=gh('GET',{}).get('sha')
except urllib.error.HTTPError as e:
    if e.code!=404: log('gh GET',e.code)
except Exception as e: log('gh GET ERR',str(e)[:80])
d={'message':'rescue log','content':base64.b64encode(txt.encode()).decode(),'branch':'main'}
if sha:d['sha']=sha
try: gh('PUT',d); print('LOG WRITTEN')
except Exception as e: print('LOG ERR',str(e)[:120])
