import os, json, time, base64, subprocess, urllib.request, urllib.error

REPO = os.environ.get('GITHUB_REPOSITORY', '')
PAT = os.environ['PAT']
SITE = 'https://hnvip.pages.dev'


def gh(method, path, body=None, api_path=False):
    url = ('https://api.github.com' + path) if api_path else (
        'https://api.github.com/repos/' + REPO + '/contents/' + path)
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(url, data=data, method=method,
        headers={'Authorization': 'token ' + PAT, 'User-Agent': 'hnvip-guard',
                 'Accept': 'application/vnd.github+json', 'Content-Type': 'application/json'})
    for i in range(5):
        try:
            resp = urllib.request.urlopen(req, timeout=60)
            raw = resp.read()
            # dispatches 成功返回 204 空 body，必须直接成功，否则重试会重复触发部署
            if resp.status == 204 or not raw:
                return {}
            return json.loads(raw)
        except urllib.error.HTTPError as e:
            if e.code == 404:
                return None
            print('  gh retry', i, e.code)
            time.sleep(4)
        except Exception as e:
            print('  gh retry', i, str(e)[:90])
            time.sleep(4)
    return None


def read_online():
    code, upd = 0, '?'
    try:
        r = subprocess.run(['curl', '-sS', '-o', '/dev/null', '-w', '%{http_code}', '-L',
                            '--max-time', '30', SITE + '/'], capture_output=True, text=True, timeout=40)
        code = int((r.stdout or '0').strip() or 0)
    except Exception as e:
        print('  probe ERR', str(e)[:90])
    try:
        r = subprocess.run(['curl', '-sS', '-L', '--max-time', '40', '-H', 'Cache-Control: no-cache',
                            SITE + '/data/latest.json?_=' + str(time.time_ns())],
                           capture_output=True, text=True, timeout=55)
        upd = json.loads(r.stdout).get('updated', '?')
    except Exception as e:
        print('  read ERR', str(e)[:90])
    return code, upd


repo_upd = json.load(open('data/latest.json')).get('updated', '?')
code, online = read_online()
print('GUARD http=%s online=%s repo=%s' % (code, online, repo_upd))

need = not (code == 200 and online == repo_upd)
action = 'dispatch' if need else 'skip'
if need:
    # 触发一次干净直传；concurrency 同组会排队，不会并发
    r = gh('POST', '/repos/' + REPO + '/actions/workflows/hnvip-live.yml/dispatches',
           {'ref': 'main', 'inputs': {'force': 'true'}}, api_path=True)
    print('DISPATCH', 'ok' if r is not None else 'FAILED')

txt = ('checked_at=%s\nhttp=%s\nrepo_updated=%s\nonline_updated=%s\nneed=%s\naction=%s\n'
       % (time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime()), code, repo_upd, online,
          str(need).lower(), action))
print('--- GUARD STATE ---\n' + txt)
cur = gh('GET', 'hnvip_guard_state.txt')
p = {'message': 'hnvip guard ' + action,
     'content': base64.b64encode(txt.encode()).decode(), 'branch': 'main'}
if isinstance(cur, dict) and cur.get('sha'):
    p['sha'] = cur['sha']
gh('PUT', 'hnvip_guard_state.txt', p)
print('DONE', action)
