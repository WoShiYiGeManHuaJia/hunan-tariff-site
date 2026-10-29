# -*- coding: utf-8 -*-
import json, os, urllib.request, http.cookiejar, traceback
BASE = "https://m.client.10010.com/servicequerybusiness/queryTariffNew/"
HDRS = {
    "User-Agent": "Mozilla/5.0 (iPhone; CPU iPhone OS 16_0 like Mac OS X) AppleWebKit/605.1.15 Mobile/15E148 MicroMessenger/8.0.47",
    "Referer": "http://img.client.10010.com/zifeizhuanquwt/index.html",
    "Accept": "application/json, text/plain, */*",
}
HERE = os.path.dirname(os.path.abspath(__file__))
out = []
def log(*a):
    s = " ".join(str(x) for x in a); print(s); out.append(s)
for path, q in [
    ("indexData", ""),
    ("TariffMenuDataRetrieval", "provinceId=074&cityId=&tariffAttributes=2&firstLevel=1&secondLevel=1001&name=&startFee=0&endFee=999999&pageNum=1&pageSize=500"),
]:
    try:
        cj = http.cookiejar.CookieJar()
        op = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(cj))
        req = urllib.request.Request(BASE + path + ("?" + q if q else ""), headers=HDRS)
        with op.open(req, timeout=30) as r:
            d = json.loads(r.read().decode("utf-8"))
        log(path, "OK keys=", list(d.keys())[:6])
        if path == "TariffMenuDataRetrieval":
            lst = (d.get("data") or {}).get("tariffList") or []
            log("  tariffList n=", len(lst), "sample=", [x.get("title") for x in lst[:3]])
        else:
            pl = (d.get("data") or {}).get("provinceList") or []
            log("  provinceList n=", len(pl), "sample=", [(p.get("provName"), p.get("provCode")) for p in pl[:3]])
    except Exception as e:
        log(path, "FAIL", traceback.format_exc()[-400:])
open(os.path.join(HERE, "probe_out.txt"), "w", encoding="utf-8").write("\n".join(out))
