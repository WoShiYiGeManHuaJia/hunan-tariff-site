import os, json, time, base64, subprocess, urllib.request, urllib.error
CF=os.environ['CF']; PAT=os.environ['PAT']; REPO=os.environ['GITHUB_REPOSITORY']
ACC='9156c2cae565fdf42d208827b523e47e'
B='https://api.cloudflare.com/client/v4/accounts/'+ACC+'/pages/projects/hnvip'
out=[]
def log(*a):
    s=' '.join(str(x) for x in a); print(s); out.append(s)
def cf(u):
    r=urllib.request.Request(u,headers={'Authorization':'Bearer '+CF,'Content-Type':'application/json'})
    return json.loads(urllib.request.urlopen(r,timeout=60).read())
def code(u):
    try:
        r=subprocess.run(['curl','-sS','-o','/dev/null','-w','%{http_code}','-L','--max-time','25',u],
                         capture_output=True,text=True,timeout=35)
        return (r.stdout or '?').strip()
    except Exception as e: return 'ERR '+str(e)[:60]
def body(u):
    try:
        r=subprocess.run(['curl','-sS','-L','--max-time','25',u],capture_output=True,text=True,timeout=35)
        return (r.stdout or '')[:420].replace('\n',' ')
    except Exception as e: return 'ERR '+str(e)[:60]
try:
    p=cf(B)['result']
    src=p.get('source') or {}; cfg=src.get('config') or {}
    log('name',p.get('name'),'subdomain',p.get('subdomain'),'domains',p.get('domains'))
    log('source.type',src.get('type'),'repo_id',cfg.get('repo_id'),'repo_name',cfg.get('repo_name'))
    log('prod_enabled',cfg.get('production_deployments_enabled'),'depl_enabled',cfg.get('deployments_enabled'))
    log('build_config',json.dumps(p.get('build_config'),ensure_ascii=False)[:400])
    ld=p.get('latest_deployment') or {}
    log('latest',ld.get('id'),'stage',(ld.get('latest_stage') or {}).get('status'),
        'trigger',(ld.get('deployment_trigger') or {}).get('type'),'url',ld.get('url'))
    ds=cf(B+'/deployments?per_page=12').get('result',[])
    for d in ds[:10]:
        u=d.get('url'); c=code(u) if u else '?'
        log('DEP',d['id'][:8],d.get('environment'),(d.get('latest_stage') or {}).get('status'),
            (d.get('deployment_trigger') or {}).get('type'),d.get('created_on'),'->',c,u)
    log('ROOT https://hnvip.pages.dev/ ->',code('https://hnvip.pages.dev/'))
    log('ROOT body:',body('https://hnvip.pages.dev/'))
    log('LATEST https://hnvip.pages.dev/data/latest.json ->',code('https://hnvip.pages.dev/data/latest.json?_='+str(time.time_ns())))
    log('ALT https://hunan-tariff-site.pages.dev/ ->',code('https://hunan-tariff-site.pages.dev/'))
except Exception as e:
    log('DIAG EXC',str(e)[:300])
txt='\n'.join(out)+'\n'
url='https://api.github.com/repos/'+REPO+'/contents/hnvip_diagnose.txt'
def gh(method,body_):
    r=urllib.request.Request(url,data=json.dumps(body_).encode(),method=method,
        headers={'Authorization':'token '+PAT,'User-Agent':'x','Accept':'application/vnd.github+json','Content-Type':'application/json'})
    resp=urllib.request.urlopen(r,timeout=60); raw=resp.read()
    return json.loads(raw) if raw else {}
sha=None
try: sha=gh('GET',{}).get('sha')
except urllib.error.HTTPError as e:
    if e.code!=404: log('gh get',e.code)
except Exception as e: log('gh get ERR',str(e)[:80])
d={'message':'diag: hnvip 500 根因','content':base64.b64encode(txt.encode()).decode(),'branch':'main'}
if sha: d['sha']=sha
try: gh('PUT',d); print('WROTE')
except Exception as e: print('WRITE ERR',str(e)[:120])
