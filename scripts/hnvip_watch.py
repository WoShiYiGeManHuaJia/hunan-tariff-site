import os, json, time, base64, subprocess, urllib.request, urllib.error
CF=os.environ['CF']; PAT=os.environ['PAT']; REPO=os.environ['GITHUB_REPOSITORY']
ACC='9156c2cae565fdf42d208827b523e47e'
B='https://api.cloudflare.com/client/v4/accounts/'+ACC+'/pages/projects/hnvip'
S='https://hnvip.pages.dev'
L=[]
def log(*a):
    s=' '.join(str(x) for x in a); print(s); L.append(s)
def curl(args,timeout=40):
    return subprocess.run(args,capture_output=True,text=True,timeout=timeout)
def probe():
    code=0; upd='?'
    try:
        r=curl(['curl','-sS','-o','/dev/null','-w','%{http_code}','-L','--max-time','30',S+'/'])
        code=int((r.stdout or '0').strip() or 0)
    except Exception as e: log('probe ERR',str(e)[:80])
    try:
        r=curl(['curl','-sS','-L','--max-time','35','-H','Cache-Control: no-cache',
                S+'/data/latest.json?_='+str(time.time_ns())],timeout=50)
        upd=json.loads(r.stdout).get('updated','?')
    except Exception as e: log('read ERR',str(e)[:80])
    return code,upd
repo=json.load(open('data/latest.json')).get('updated','?')
code,upd=probe()
log('WATCH http',code,'online',upd,'repo',repo)
need = not (code==200 and upd==repo)
if need:
    # 只让 Cloudflare 用正确仓库重新构建一次，绝不直传、绝不并发上传
    try:
        r=urllib.request.Request(B+'/deployments',data=json.dumps({'branch':'main'}).encode(),method='POST',
            headers={'Authorization':'Bearer '+CF,'Content-Type':'application/json','User-Agent':'hnvip-watch/1.0'})
        log('REBUILD',urllib.request.urlopen(r,timeout=90).status)
        for i in range(10):
            time.sleep(15)
            c,u=probe(); log(' after',i,c,u)
            if c==200 and u==repo: break
        code,upd=probe()
    except urllib.error.HTTPError as e: log('REBUILD HTTP',e.code,e.read().decode()[:200])
    except Exception as e: log('REBUILD ERR',str(e)[:150])
else:
    log('OK 线上与仓库一致，0 次构建')
log('FINAL http',code,'online',upd)
txt='\n'.join(L)+'\n'
url='https://api.github.com/repos/'+REPO+'/contents/hnvip_watch_state.txt'
def gh(m,b):
    r=urllib.request.Request(url,data=json.dumps(b).encode(),method=m,
        headers={'Authorization':'token '+PAT,'User-Agent':'x','Accept':'application/vnd.github+json','Content-Type':'application/json'})
    resp=urllib.request.urlopen(r,timeout=60); raw=resp.read()
    return json.loads(raw) if raw else {}
sha=None
try: sha=gh('GET',{}).get('sha')
except urllib.error.HTTPError as e:
    if e.code!=404: log('gh GET',e.code)
except Exception as e: log('gh GET ERR',str(e)[:80])
d={'message':'watch state','content':base64.b64encode(txt.encode()).decode(),'branch':'main'}
if sha:d['sha']=sha
try: gh('PUT',d); print('WRITTEN')
except Exception as e: print('WRITE ERR',str(e)[:100])
