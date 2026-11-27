import os, sys, json, hashlib, uuid, time, base64, hmac, subprocess, atexit
import urllib.request, urllib.error, urllib.parse

ROOT = os.getcwd()
ACC  = '9156c2cae565fdf42d208827b523e47e'
CF   = os.environ['CF']
PAT  = os.environ['PAT']
REPO = os.environ.get('GITHUB_REPOSITORY', '')
BASE = 'https://api.cloudflare.com/client/v4/accounts/%s/pages/projects/hnvip' % ACC
API  = BASE + '/deployments'
SITE = 'https://hnvip.pages.dev'
FORCE = os.environ.get('FORCE', 'false') == 'true'
REPAIR = os.environ.get('REPAIR', 'false') == 'true'
EVENT = os.environ.get('EVENT', '')
S = {}


def gh(method, path, body=None):
    url = 'https://api.github.com/repos/' + REPO + '/contents/' + path
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(url, data=data, method=method,
        headers={'Authorization': 'token ' + PAT, 'User-Agent': 'hnvip-live',
                 'Accept': 'application/vnd.github+json', 'Content-Type': 'application/json'})
    for i in range(6):
        try:
            return json.loads(urllib.request.urlopen(req, timeout=60).read())
        except urllib.error.HTTPError as e:
            if e.code == 404:
                return None
            print('  gh retry', i, e.code)
            time.sleep(4)
        except Exception as e:
            print('  gh retry', i, str(e)[:90])
            time.sleep(4)
    return None


def flush():
    txt = ('checked_at=%s\nevent=%s\nhttp=%s\nrepo_updated=%s\nonline_updated=%s\n'
           'match=%s\nstage=%s\ndep=%s\nattempts=%s\nerror=%s\n'
           % (time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime()), EVENT,
              S.get('http', '?'), S.get('repo', '?'), S.get('online', '?'),
              S.get('match', 'false'), S.get('stage', '?'), S.get('dep', '?'),
              S.get('attempts', '0'), S.get('error', '')))
    print('--- STATE ---\n' + txt)
    cur = gh('GET', 'hnvip_live_state.txt')
    p = {'message': 'hnvip live state ' + ('OK' if S.get('match') == 'true' else 'CHECK'),
         'content': base64.b64encode(txt.encode()).decode(), 'branch': 'main'}
    if isinstance(cur, dict) and cur.get('sha'):
        p['sha'] = cur['sha']
    gh('PUT', 'hnvip_live_state.txt', p)


atexit.register(flush)


def curl_json(url, timeout=40):
    r = subprocess.run(['curl', '-sS', '-L', '--max-time', str(timeout),
                        '-H', 'Cache-Control: no-cache', '-H', 'User-Agent: hnvip-live/1.0', url],
                       capture_output=True, text=True, timeout=timeout + 15)
    if r.returncode:
        raise RuntimeError('curl %d %s' % (r.returncode, (r.stderr or '')[:140]))
    return r.stdout


def site():
    """返回 (http_code, online_updated)；任何异常都当不可达，不误判成功。"""
    code = 0
    try:
        r = subprocess.run(['curl', '-sS', '-o', '/dev/null', '-w', '%{http_code}', '-L',
                            '--max-time', '30', SITE + '/'],
                           capture_output=True, text=True, timeout=40)
        code = int((r.stdout or '0').strip() or 0)
    except Exception as e:
        print('  probe ERR', str(e)[:90])
    upd = '?'
    try:
        upd = json.loads(curl_json(SITE + '/data/latest.json?_=' + str(time.time_ns()))).get('updated', '?')
    except Exception as e:
        print('  read ERR', str(e)[:90])
    return code, upd


def deploy_once():
    files = {}
    for dp, dn, fn in os.walk(ROOT):
        dn[:] = [d for d in dn if d not in ('.git', '.github')]
        for f in fn:
            p = os.path.join(dp, f)
            rel = os.path.relpath(p, ROOT).replace(os.sep, '/')
            sz = os.path.getsize(p)
            if sz > 24 * 1024 * 1024:
                print('SKIP >24MB:', rel, sz)
                continue
            # CF Pages 直传 manifest 必须是 [hash, size] 数组；对象格式会 stage=success 但产物为空 → 全站 500
            files['/' + rel] = [hashlib.sha1(open(p, 'rb').read()).hexdigest(), sz]
    print('files:', len(files), '| has index:', '/index.html' in files)
    if '/index.html' not in files:
        raise RuntimeError('index.html 缺失，中止')

    boundary = '----x' + uuid.uuid4().hex

    def field(name, val, ctype=None, fname=None):
        b = ('--%s\r\n' % boundary).encode()
        b += (('Content-Disposition: form-data; name="%s"; filename="%s"\r\n' % (name, fname))
              if fname else ('Content-Disposition: form-data; name="%s"\r\n' % name)).encode()
        if ctype:
            b += ('Content-Type: %s\r\n' % ctype).encode()
        return b + b'\r\n' + val + b'\r\n'

    body = field('manifest', json.dumps(files).encode(), 'application/json')
    for path, (h, sz) in files.items():
        body += field(h, open(ROOT + path, 'rb').read(), 'application/octet-stream', h)
    body += ('--%s--\r\n' % boundary).encode()

    req = urllib.request.Request(API, data=body, method='POST')
    req.add_header('Authorization', 'Bearer ' + CF)
    req.add_header('Content-Type', 'multipart/form-data; boundary=' + boundary)
    req.add_header('User-Agent', 'hnvip-live/1.0')
    try:
        out = json.loads(urllib.request.urlopen(req, timeout=900).read())
    except urllib.error.HTTPError as e:
        print('DEPLOY HTTP ERR', e.code, e.read().decode()[:500])
        raise
    dep = out['result']
    dep_id = dep['id']
    S['dep'] = dep_id
    S['stage'] = 'queued'
    print('DEP_ID', dep_id, 'env', dep.get('environment'))

    # 直传创建的 deployment 卡在 queued，必须 retry 才真正构建
    try:
        q = urllib.request.Request(API + '/' + dep_id + '/retry', data=b'', method='POST')
        q.add_header('Authorization', 'Bearer ' + CF)
        print('RETRY HTTP', urllib.request.urlopen(q, timeout=120).status)
    except Exception as e:
        print('RETRY WARN', str(e)[:160])

    stage = 'unknown'
    for i in range(40):
        time.sleep(10)
        try:
            q = urllib.request.Request(API + '/' + dep_id)
            q.add_header('Authorization', 'Bearer ' + CF)
            stage = json.loads(urllib.request.urlopen(q, timeout=60).read())['result']['latest_stage']['status']
        except Exception as e:
            print('poll', i, 'ERR', str(e)[:90])
            continue
        print('stage[%d]' % i, stage)
        if stage in ('success', 'failure', 'cancelled'):
            break
    S['stage'] = stage
    print('FINAL_STAGE', stage)
    if stage != 'success':
        raise RuntimeError('部署未成功: ' + stage)


def cf_json(url, method='GET', body=None, timeout=120):
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(url, data=data, method=method)
    req.add_header('Authorization', 'Bearer ' + CF)
    req.add_header('Content-Type', 'application/json')
    return json.loads(urllib.request.urlopen(req, timeout=timeout).read())


def disable_auto_deploy():
    """把 hnvip 从 GitHub 自动构建项目改回纯直传，避免 GitHub 失败构建顶掉生产 → 全站 500。"""
    try:
        proj = cf_json(BASE)['result']
        src = proj.get('source') or {}
        print('BEFORE source.type=%s prod_enabled=%s depl_enabled=%s'
              % (src.get('type'), (src.get('config') or {}).get('production_deployments_enabled'),
                 (src.get('config') or {}).get('deployments_enabled')))
        attempts = [{'type': 'ad_hoc'}]
        cfg = dict(src.get('config') or {})
        cfg['production_deployments_enabled'] = False
        cfg['deployments_enabled'] = False
        cfg['preview_deployment_setting'] = 'none'
        fallback = dict(src); fallback['config'] = cfg
        attempts.append(fallback)
        for s in attempts:
            try:
                r = cf_json(BASE, 'PATCH', {'name': proj.get('name', 'hnvip'), 'source': s})
                if r.get('success'):
                    print('PATCH OK source.type=%s' % s.get('type'))
                    return
                print('PATCH refused', str(r.get('errors'))[:180])
            except urllib.error.HTTPError as e:
                print('PATCH HTTP', e.code, e.read().decode()[:180])
            except Exception as e:
                print('PATCH ERR', str(e)[:140])
        print('WARN 项目配置未改成功，继续直传 + 生产切换')
    except Exception as e:
        print('WARN 读取项目失败', str(e)[:140])


def promote(dep_id):
    """把生产别名切到指定成功部署。直传部署 success 但别名仍指向坏构建时用它自愈。"""
    try:
        r = cf_json(API + '/' + dep_id + '/rollback', 'POST', {})
        print('PROMOTE', r.get('success'), str(r.get('errors'))[:180])
    except urllib.error.HTTPError as e:
        print('PROMOTE HTTP', e.code, e.read().decode()[:220])
    except Exception as e:
        print('PROMOTE ERR', str(e)[:160])


def alert(msg):
    # 默认关闭：需要异常告警时，在仓库 Variables 里设 HNVIP_ALERT=1
    if os.environ.get('ALERT', '') != '1':
        return
    wh, sec = os.environ.get('DING_WEBHOOK', ''), os.environ.get('DING_SECRET', '')
    if not wh or not sec:
        return
    ts = str(round(time.time() * 1000))
    sign = urllib.parse.quote(base64.b64encode(
        hmac.new(sec.encode(), (ts + '\n' + sec).encode(), hashlib.sha256).digest()).decode())
    url = wh + ('&' if '?' in wh else '?') + 'timestamp=' + ts + '&sign=' + sign
    body = json.dumps({'msgtype': 'text', 'text': {'content':
        '[资费站自愈告警] ' + msg + '\n' + time.strftime('%Y-%m-%d %H:%M UTC', time.gmtime())}}).encode()
    try:
        req = urllib.request.Request(url, data=body, headers={'Content-Type': 'application/json'})
        print('ALERT', urllib.request.urlopen(req, timeout=30).read().decode()[:120])
    except Exception as e:
        print('ALERT ERR', str(e)[:120])


def main():
    if REPAIR:
        disable_auto_deploy()
    repo_upd = json.load(open(ROOT + '/data/latest.json')).get('updated', '?')
    S['repo'] = repo_upd
    code, online = site()
    S.update({'http': code, 'online': online})
    print('PRECHECK http=%s online=%s repo=%s force=%s event=%s' % (code, online, repo_upd, FORCE, EVENT))

    # 定时/手动巡检：线上已一致就不制造部署，这是防队列堆积的关键
    if (not FORCE) and EVENT != 'push' and code == 200 and online == repo_upd:
        S['match'] = 'true'
        S['stage'] = 'skipped'
        S['attempts'] = '0'
        print('OK 线上已一致，本轮跳过直传（0 次部署）')
        return
    if EVENT == 'push':
        print('数据刚提交，按预期直传一次')

    ok = False
    err = ''
    for attempt in (1, 2):
        S['attempts'] = str(attempt)
        try:
            deploy_once()
            for k in range(8):
                time.sleep(15 if k == 0 else 20)
                code, online = site()
                S.update({'http': code, 'online': online})
                print('  自检[%d/%d] http=%s online=%s' % (attempt, k + 1, code, online))
                if code == 200 and online == repo_upd:
                    break
            if code == 200 and online == repo_upd:
                ok = True
                break
            # 部署本身 success，但生产别名仍指向坏构建 → 强制切到本次成功部署
            if S.get('dep') and S.get('stage') == 'success':
                promote(S['dep'])
                time.sleep(20)
                code, online = site()
                S.update({'http': code, 'online': online})
                print('  promote 后 http=%s online=%s' % (code, online))
                if code == 200 and online == repo_upd:
                    ok = True
                    break
            err = '第%d次：部署成功但线上不可用 (http=%s, %s != %s)' % (attempt, code, online, repo_upd)
        except Exception as e:
            err = '第%d次异常：%s' % (attempt, str(e)[:220])
        print(err)

    S['match'] = str(ok).lower()
    S['error'] = '' if ok else err
    if ok:
        print('OK 线上已与仓库一致')
    else:
        alert('连续 2 次直传后站点仍异常：' + err)
        raise SystemExit(err)


main()
