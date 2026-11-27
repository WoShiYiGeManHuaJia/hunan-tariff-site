import os, json, time, base64, urllib.request, urllib.error
CF=os.environ['CF']; PAT=os.environ['PAT']; REPO=os.environ['GITHUB_REPOSITORY']
ACC='9156c2cae565fdf42d208827b523e47e'
PU='https://api.cloudflare.com/client/v4/accounts/'+ACC+'/pages/projects'
B=PU+'/hnvip'; D=B+'/deployments'
L=[]
def log(*a):
    s=' '.join(str(x) for x in a); print(s); L.append(s)
def req(url,method='GET',body=None):
    data=json.dumps(body).encode() if body is not None else None
    r=urllib.request.Request(url,data=data,method=method,
        headers={'Authorization':'Bearer '+CF,'Content-Type':'application/json','User-Agent':'hnvip-purge/1.0'})
    resp=urllib.request.urlopen(r,timeout=90); raw=resp.read()
    try: return resp.status, json.loads(raw)
    except Exception: return resp.status, (raw.decode('utf8','replace')[:200] if raw else '')
def http_err(e):
    try: return e.code, e.read().decode('utf8','replace')[:200]
    except Exception: return e.code, ''

# 1. 取全部部署 id
ids=[]
for page in range(1,9):
    try:
        st,d=req(D+'?page=%d&per_page=100'%page)
        arr=(d.get('result') or []) if isinstance(d,dict) else []
        if not arr: break
        ids += [x['id'] for x in arr]
        log('page',page,'got',len(arr),'total',len(ids))
        if len(arr)<100: break
    except urllib.error.HTTPError as e: log('LIST HTTP',*http_err(e)); break
    except Exception as e: log('LIST ERR',str(e)[:120]); break
log('TOTAL DEPLOYMENTS',len(ids))

# 2. 逐个删，每 40 个试删项目
deleted=0; project_gone=False
for i,did in enumerate(ids):
    try:
        req(D+'/'+did,'DELETE'); deleted+=1
    except urllib.error.HTTPError as e:
        c,_=http_err(e)
        if c!=404: log('del ERR',did[:8],c)
    except Exception as e: log('del ERR',did[:8],str(e)[:60])
    if (i+1)%40==0 or (i+1)==len(ids):
        log('deleted',deleted,'/',len(ids))
        for k in range(2):
            try:
                st,d=req(B,'DELETE'); log('PROJECT DELETE',st,str(d)[:160])
                if isinstance(d,dict) and d.get('success'): project_gone=True; break
            except urllib.error.HTTPError as e: log('PROJECT DEL HTTP',*http_err(e))
            except Exception as e: log('PROJECT DEL ERR',str(e)[:100])
            time.sleep(4)
        if project_gone: break
        time.sleep(2)

if not project_gone:
    for k in range(3):
        try:
            st,d=req(B,'DELETE'); log('FINAL PROJECT DELETE',st,str(d)[:160])
            if isinstance(d,dict) and d.get('success'): project_gone=True; break
        except urllib.error.HTTPError as e: log('FINAL DEL HTTP',*http_err(e))
        except Exception as e: log('FINAL DEL ERR',str(e)[:100])
        time.sleep(6)
log('PROJECT_GONE',project_gone)

# 3. 重建为纯直传项目（不带 source）
created=False
if project_gone:
    for k in range(4):
        try:
            st,d=req(PU,'POST',{'name':'hnvip','production_branch':'main'})
            log('CREATE',st,str(d)[:420])
            if isinstance(d,dict) and d.get('success'): created=True; break
        except urllib.error.HTTPError as e: log('CREATE HTTP',*http_err(e))
        except Exception as e: log('CREATE ERR',str(e)[:150])
        time.sleep(8)
    try:
        st,d=req(B)
        p=(d.get('result') or {}) if isinstance(d,dict) else {}
        src=p.get('source') or {}
        log('AFTER source.type=',src.get('type'),'subdomain=',p.get('subdomain'))
    except urllib.error.HTTPError as e: log('AFTER HTTP',*http_err(e))
    except Exception as e: log('AFTER ERR',str(e)[:120])
log('CREATED',created)

# 4. 触发一次直传
if created:
    try:
        u='https://api.github.com/repos/'+REPO+'/actions/workflows/hnvip-live.yml/dispatches'
        r=urllib.request.Request(u,data=json.dumps({'ref':'main','inputs':{'force':'true'}}).encode(),method='POST',
            headers={'Authorization':'token '+PAT,'User-Agent':'x','Accept':'application/vnd.github+json','Content-Type':'application/json'})
        log('DISPATCH',urllib.request.urlopen(r,timeout=60).status)
    except urllib.error.HTTPError as e: log('DISPATCH HTTP',*http_err(e))
    except Exception as e: log('DISPATCH ERR',str(e)[:120])

txt='\n'.join(L)+'\n'
url='https://api.github.com/repos/'+REPO+'/contents/hnvip_purge_log.txt'
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
d={'message':'purge log','content':base64.b64encode(txt.encode()).decode(),'branch':'main'}
if sha: d['sha']=sha
try: gh('PUT',d); print('LOG WRITTEN')
except Exception as e: print('LOG ERR',str(e)[:120])
