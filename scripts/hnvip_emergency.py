import os, json, hashlib, uuid, time, base64, subprocess, urllib.request, urllib.error
import atexit

CF = os.environ['CF']; PAT = os.environ['PAT']; REPO = os.environ['GITHUB_REPOSITORY']
ACC = '9156c2cae565fdf42d208827b523e47e'
PU = 'https://api.cloudflare.com/client/v4/accounts/' + ACC + '/pages/projects'
B = PU + '/hnvip'; API = B + '/deployments'
SITE = 'https://hnvip.pages.dev'
L = []
def log(*a):
    s = ' '.join(str(x) for x in a); print(s, flush=True); L.append(s)

def cf(url, method='GET', body=None, timeout=120):
    data = json.dumps(body).encode() if body is not None else None
    r = urllib.request.Request(url, data=data, method=method,
        headers={'Authorization':'Bearer '+CF,'Content-Type':'application/json','User-Agent':'hnvip-emergency/1.0'})
    resp = urllib.request.urlopen(r, timeout=timeout); raw = resp.read()
    try: return json.loads(raw)
    except Exception: return {'raw': raw.decode('utf8','replace')[:300]}

def code(u):
    try:
        r = subprocess.run(['curl','-sS','-o','/dev/null','-w','%{http_code}','-L','--max-time','25',u],
                           capture_output=True, text=True, timeout=35)
        return int((r.stdout or '0').strip() or 0)
    except Exception: return 0

def deploy(files):
    """数组格式 manifest 直传；成功后立刻 rollback 把生产别名切过来。"""
    manifest = {}
    for path, blob in files.items():
        manifest[path] = [hashlib.sha1(blob).hexdigest(), len(blob)]
    log('DEPLOY files=%d has_index=%s' % (len(manifest), '/index.html' in manifest))
    boundary = '----x' + uuid.uuid4().hex
    def field(name, val, ctype=None, fname=None):
        b = ('--%s\r\n' % boundary).encode()
        b += (('Content-Disposition: form-data; name="%s"; filename="%s"\r\n' % (name,fname))
              if fname else ('Content-Disposition: form-data; name="%s"\r\n' % name)).encode()
        if ctype: b += ('Content-Type: %s\r\n' % ctype).encode()
        return b + b'\r\n' + val + b'\r\n'
    body = field('manifest', json.dumps(manifest).encode(), 'application/json')
    for path, blob in files.items():
        h = manifest[path][0]
        body += field(h, blob, 'application/octet-stream', h)
    body += ('--%s--\r\n' % boundary).encode()
    req = urllib.request.Request(API, data=body, method='POST')
    req.add_header('Authorization','Bearer '+CF)
    req.add_header('Content-Type','multipart/form-data; boundary='+boundary)
    try:
        out = json.loads(urllib.request.urlopen(req, timeout=900).read())
    except urllib.error.HTTPError as e:
        log('DEPLOY HTTP', e.code, e.read().decode()[:400]); raise
    dep = out['result']['id']; log('DEP_ID', dep)
    try:
        q = urllib.request.Request(API+'/'+dep+'/retry', data=b'', method='POST')
        q.add_header('Authorization','Bearer '+CF)
        log('RETRY', urllib.request.urlopen(q, timeout=120).status)
    except Exception as e: log('RETRY WARN', str(e)[:120])
    stage='unknown'
    for i in range(30):
        time.sleep(8)
        try:
            stage = cf(API+'/'+dep)['result']['latest_stage']['status']
        except Exception as e:
            log('poll',i,str(e)[:80]); continue
        log('stage[%d]'%i, stage)
        if stage in ('success','failure','cancelled'): break
    if stage != 'success': raise RuntimeError('stage='+stage)
    # 关键：把生产别名切到本次成功部署
    for k in range(3):
        try:
            r = cf(API+'/'+dep+'/rollback','POST',{})
            log('PROMOTE', r.get('success'), str(r.get('errors'))[:140])
            if r.get('success'): break
        except urllib.error.HTTPError as e:
            log('PROMOTE HTTP', e.code, e.read().decode()[:160])
        except Exception as e: log('PROMOTE ERR', str(e)[:120])
        time.sleep(5)
    return dep

def settle():
    for k in range(6):
        time.sleep(10)
        c = code(SITE + '/?_=' + str(time.time_ns()))
        log('  ROOT[%d] -> %s' % (k+1, c))
        if c == 200: return True
    return False

def write_log():
    txt = '\n'.join(L) + '\n'
    url = 'https://api.github.com/repos/' + REPO + '/contents/hnvip_emergency_log.txt'
    def gh(method, body_):
        r = urllib.request.Request(url, data=json.dumps(body_).encode(), method=method,
            headers={'Authorization':'token '+PAT,'User-Agent':'x',
                     'Accept':'application/vnd.github+json','Content-Type':'application/json'})
        resp = urllib.request.urlopen(r, timeout=60); raw = resp.read()
        return json.loads(raw) if raw else {}
    sha = None
    try: sha = gh('GET', {}).get('sha')
    except urllib.error.HTTPError as e:
        if e.code != 404: log('gh GET', e.code)
    except Exception as e: log('gh GET ERR', str(e)[:80])
    d = {'message':'[Skip CI] emergency log','content':base64.b64encode(txt.encode()).decode(),'branch':'main'}
    if sha: d['sha'] = sha
    try: gh('PUT', d); print('LOG WRITTEN', flush=True)
    except Exception as e: print('LOG ERR', str(e)[:120], flush=True)
atexit.register(write_log)

# ---------- 1. 先掐断 GitHub 自动构建（它每次 push 都用空构建抢生产别名 → 500） ----------
try:
    p = cf(B)['result']; src = p.get('source') or {}; cfg = dict(src.get('config') or {})
    log('PROJECT type=%s prod=%s depl=%s' % (src.get('type'), cfg.get('production_deployments_enabled'), cfg.get('deployments_enabled')))
    cfg['production_deployments_enabled'] = False
    cfg['deployments_enabled'] = False
    cfg['preview_deployment_setting'] = 'none'
    ns = dict(src); ns['config'] = cfg
    r = cf(B, 'PATCH', {'name':p.get('name','hnvip'),'source':ns})
    log('PATCH', r.get('success'), str(r.get('errors'))[:180])
    p2 = cf(B)['result']; c2 = (p2.get('source') or {}).get('config') or {}
    log('AFTER prod=%s depl=%s' % (c2.get('production_deployments_enabled'), c2.get('deployments_enabled')))
except urllib.error.HTTPError as e:
    log('PROJECT HTTP', e.code, e.read().decode()[:200])
    if e.code == 404:
        try:
            r = cf(PU, 'POST', {'name':'hnvip','production_branch':'main'})
            log('CREATE', r.get('success'), str(r.get('errors'))[:180]); time.sleep(5)
        except urllib.error.HTTPError as e2: log('CREATE HTTP', e2.code, e2.read().decode()[:200])
except Exception as e:
    log('PROJECT ERR', str(e)[:160])

# ---------- 2. 全量直传当前仓库 ----------
ROOT = os.getcwd()
files = {}
for dp, dn, fn in os.walk(ROOT):
    dn[:] = [d for d in dn if d not in ('.git','.github')]
    for f in fn:
        p = os.path.join(dp, f)
        rel = os.path.relpath(p, ROOT).replace(os.sep,'/')
        sz = os.path.getsize(p)
        if sz > 24*1024*1024: continue
        files['/'+rel] = open(p,'rb').read()
ok = False
try:
    deploy(files)
    ok = settle()
except Exception as e:
    log('FULL DEPLOY ERR', str(e)[:200])

# ---------- 3. 仍不行 → 单文件跳转页，保证裸地址 200 ----------
if not ok:
    log('FALLBACK → 最小跳转页')
    html = ('<!doctype html><html lang="zh-CN"><head><meta charset="utf-8">'
            '<meta name="viewport" content="width=device-width,initial-scale=1">'
            '<meta http-equiv="refresh" content="0;url=https://hunan-tariff-site.pages.dev/">'
            '<title>资费监控</title></head><body style="font:16px/1.6 sans-serif;padding:24px">'
            '<p>正在进入资费监控…</p>'
            '<p><a href="https://hunan-tariff-site.pages.dev/">点此直接打开</a></p>'
            '<script>location.replace("https://hunan-tariff-site.pages.dev/")</script>'
            '</body></html>').encode()
    try:
        deploy({'/index.html': html})
        ok = settle()
    except Exception as e:
        log('FALLBACK ERR', str(e)[:200])

log('FINAL_OK', ok, 'ROOT', code(SITE+'/'))
