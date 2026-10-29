import urllib.request, ssl, socket, hashlib, io, zipfile, re, subprocess, sys
ctx = ssl.create_default_context()
ctx.check_hostname = False
ctx.verify_mode = ssl.CERT_NONE

def dexinfo(raw):
    try:
        z = zipfile.ZipFile(io.BytesIO(raw))
        d = z.read('classes.dex')
    except Exception as e:
        return '解包失败 %s' % e
    tags = sorted(set(x.decode() for x in re.findall(rb'2026[0-9]{4}-[0-9]', d)))
    kws = {kw: (kw.encode('utf-8') in d) for kw in ['非本周','无需校园网','请连校园网','节假日']}
    return '构建号=%s  中文标记=%s' % (tags, kws)

URLS = [
    'https://hnvip.qd.je/nexio.apk',
    'http://hnvip.qd.je/nexio.apk',
    'https://woshiyigemanhuajia.github.io/hunan-tariff-site/nexio.apk',
    'https://cdn.jsdelivr.net/gh/WoShiYiGeManHuaJia/NexioSchedule@master/app-release.apk',
    'https://cdn.jsdelivr.net/gh/WoShiYiGeManHuaJia/hunan-tariff-site@main/nexio.apk',
]

print('=== DNS hnvip.qd.je ===')
try:
    print(socket.gethostbyname_ex('hnvip.qd.je'))
except Exception as e:
    print('解析失败', e)

for u in URLS:
    print('')
    print('=== %s ===' % u)
    try:
        req = urllib.request.Request(u, headers={'User-Agent': 'Mozilla/5.0'})
        resp = urllib.request.urlopen(req, timeout=240, context=ctx)
        raw = resp.read()
        print('HTTP', resp.status, 'bytes', len(raw))
        print('md5', hashlib.md5(raw).hexdigest())
        print(dexinfo(raw))
    except Exception as e:
        print('失败', repr(e)[:160])
