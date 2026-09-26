# -*- coding: utf-8 -*-
"""一次性核验：被判「下架」的业务是否仍在联通公开资费接口返回。

接口 pageSize 硬限 500、服务端按随机子集轮换返回，单轮采不全。
本脚本对指定板块做多轮大采样，累计去重后检查目标名单是否仍出现。
不依赖仓库其它模块，可独立运行。
"""
import json, time, os, urllib.request, http.cookiejar, sys

BASE = "https://m.client.10010.com/servicequerybusiness/queryTariffNew/"
HDRS = {
    "User-Agent": "Mozilla/5.0 (iPhone; CPU iPhone OS 16_0 like Mac OS X) AppleWebKit/605.1.15 Mobile/15E148 MicroMessenger/8.0.47",
    "Referer": "http://img.client.10010.com/zifeizhuanquwt/index.html",
    "Accept": "application/json, text/plain, */*",
}
_cj = http.cookiejar.CookieJar()
_op = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(_cj))

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
OUTD = os.path.join(ROOT, "unicom", "data")
os.makedirs(OUTD, exist_ok=True)
LOG = open(os.path.join(OUTD, "verify_out.txt"), "w", encoding="utf-8")
log = None


def log(*a):
    s = " ".join(str(x) for x in a)
    print(s)
    LOG.write(s + "\n")
    LOG.flush()


def get(path, q=""):
    req = urllib.request.Request(BASE + path + ("?" + q if q else ""), headers=HDRS)
    with _op.open(req, timeout=30) as r:
        return json.loads(r.read().decode("utf-8"))


def jobs():
    d = get("indexData")
    m = {}
    for p in (d.get("data") or {}).get("provinceList") or []:
        if p.get("provCode") and p.get("provName"):
            m[p["provName"]] = (p["provCode"], p.get("cityCode") or "")
    return m


BUDGET = float(os.getenv("VERIFY_BUDGET") or "420")
MAXPASS = int(os.getenv("VERIFY_PASS") or "40")


def sample(pid, cid, attr):
    seen = {}
    t0 = time.time()
    empty = 0
    for p in range(1, MAXPASS + 1):
        before = len(seen)
        for pn in range(1, 21):
            q = ("provinceId=%s&cityId=%s&tariffAttributes=%s&firstLevel=1&secondLevel=%s"
                 "&name=&startFee=0&endFee=999999&pageNum=%d&pageSize=500") % (
                pid, cid, attr, "1001", pn, 500)
            try:
                d = get("TariffMenuDataRetrieval", q)
            except Exception as e:
                log("   reqfail p%d pn%d %s" % (p, pn, str(e)[:50]))
                continue
            for x in ((d.get("data") or {}).get("tariffList") or []):
                if x.get("id") is None:
                    continue
                seen[str(x["id"])] = x.get("title", "")
            if time.time() - t0 > BUDGET:
                break
        log("   pass %d: +%d cum %d (%.0fs)" % (p, len(seen) - before, len(seen), time.time() - t0))
        if len(seen) == before:
            empty += 1
            if empty >= 4:
                break
        else:
            empty = 0
        if time.time() - t0 > BUDGET:
            break
    return seen


def main():
    tgt = json.load(open(os.path.join(HERE, "verify_flat.json"), encoding="utf-8"))
    try:
        J = jobs()
    except Exception as e:
        log("jobs() failed:", str(e)[:120])
        J = {}
    log("province map sample:", {k: J[k] for k in list(J)[:3]} if J else "EMPTY")
    res = {}
    plan = [("hunan", "湖南", 2), ("quanguo", None, 1), ("guangdong", "广东", 2)]
    for sc, cn, attr in plan:
        names = tgt.get(sc) or []
        if not names:
            continue
        if sc == "quanguo":
            pid, cid = "", ""
        else:
            if cn not in J:
                log("skip", sc, "no provCode")
                continue
            pid, cid = J[cn]
        log("=== %s target=%d pid=%s cid=%s attr=%s ===" % (sc, len(names), pid, cid, attr))
        seen = sample(pid, cid, attr)
        ts = set(seen.values())
        hit = [n for n in names if n in ts]
        miss = [n for n in names if n not in ts]
        res[sc] = {"target": len(names), "sampled_unique": len(seen),
                   "still_present": len(hit), "absent": len(miss),
                   "present_sample": hit[:15], "absent_sample": miss[:10]}
        log("   -> sampled=%d still=%d absent=%d" % (len(seen), len(hit), len(miss)))
    json.dump(res, open(os.path.join(OUTD, "verify_result.json"), "w", encoding="utf-8"),
              ensure_ascii=False, indent=1)
    log("DONE")


if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        import traceback
        log("FATAL", traceback.format_exc()[-800:])
