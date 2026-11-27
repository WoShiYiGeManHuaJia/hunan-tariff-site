import os, json, time, base64, urllib.request, urllib.error
CF=os.environ['CF']; PAT=os.environ['PAT']; REPO=os.environ['GITHUB_REPOSITORY']
ACC='9156c2cae565fdf42d208827b523e47e'
PU='https://api.cloudflare.com/client/v4/accounts/'+ACC+'/pages/projects'
B=PU+'/hnvip'
L=[]
def log(*a):
    s=' '.join(str(x) for x in a); print(s); L.append(s)
def req(url,method='GET',body=None):
    data=json.dumps(body).encode() if body is not None else None
    r=urllib.request.Request(url,data=data,method=method,
        headers={'Authorization':'Bearer '+CF,'Content-Type':'application/json','User-Agent':'hnvip-rebuild/1.0'})
    resp=urllib.request.urlopen(r,timeout=90); raw=resp.read()
    try: return resp.status, json.loads(raw)
    except Exception: return resp.status, (raw.decode('utf8','replace')[:300] if raw else '')

def project():
    try:
        st,d=req(B)
        if isinstance(d,dict) and d.get('success'):
            p=d.get('result') or {}
            src=p.get('source') or {}
            log('EXISTS type=%s repo_id=%s prod=%s subdomain=%s' % (
                src.get('type'), (src.get('config') or {}).get('repo_id'),
                (src.get('config') or {}).get('production_deployments_enabled'), p.get('subdomain')))
            return src
        log('GET',st,str(d)[:200]); return None
    except urllib.error.HTTPError as e:
        log('GET HTTP',e.code,e.read().decode()[:200]); return None
    except Exception as e:
        log('GET ERR',str(e)[:150]); return None

src=project()
need_rebuild = (src is None) or (src.get('type') not in (None,'ad_hoc'))
log('need_rebuild',need_rebuild)
if need_rebuild:
    for attempt in range(3):
        try:
            st,d=req(B,'DELETE'); log('DELETE',st,str(d)[:220]); break
        except urllib.error.HTTPError as e: log('DELETE HTTP',e.code,e.read().decode()[:220])
        except Exception as e: log('DELETE ERR',str(e)[:150])
        time.sleep(8)
    time.sleep(6)
    for attempt in range(3):
        try:
            st,d=req(PU,'POST',{'name':'hnvip','production_branch':'main'})
            log('CREATE',st,str(d)[:500])
            if isinstance(d,dict) and d.get('success'): break
        except urllib.error.HTTPError as e:
            log('CREATE HTTP',e.code,e.read().decode()[:400])
        except Exception as e: log('CREATE ERR',str(e)[:200])
        time.sleep(10)
src2=project()
log('FINAL', 'ad_hoc' if (src2 is None or src2.get('type') in (None,'ad_hoc')) else 'STILL_GITHUB')
# 触发一次直传（复用 hnvip-live）
try:
    u='https://api.github.com/repos/'+REPO+'/actions/workflows/hnvip-live.yml/dispatches'
    r=urllib.request.Request(u,data=json.dumps({'ref':'main','inputs':{'force':'true'}}).encode(),method='POST',
        headers={'Authorization':'token '+PAT,'User-Agent':'x','Accept':'application/vnd.github+json','Content-Type':'application/json'})
    log('DISPATCH',urllib.request.urlopen(r,timeout=60).status)
except urllib.error.HTTPError as e: log('DISPATCH HTTP',e.code,e.read().decode()[:200])
except Exception as e: log('DISPATCH ERR',str(e)[:150])
# 写日志
txt='\n'.join(L)+'\n'
url='https://api.github.com/repos/'+REPO+'/contents/hnvip_rebuild_log.txt'
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
d={'message':'rebuild log','content':base64.b64encode(txt.encode()).decode(),'branch':'main'}
if sha: d['sha']=sha
try: gh('PUT',d); print('LOG WRITTEN')
except Exception as e: print('LOG ERR',str(e)[:120])
