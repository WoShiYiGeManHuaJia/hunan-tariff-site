# -*- coding: utf-8 -*-
"""一次性核验：被判「下架」的业务是否仍在联通接口返回。

接口 pageSize 硬限 500、服务端按随机子集轮换，单轮采不全。
这里对指定板块做多轮大采样，累计去重后检查目标名单是否仍出现。
"""
import json, time, os, sys, hashlib, collections
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "pipelines"))
import unicom_pipeline as U

TARGET = json.load(open(os.path.join(os.path.dirname(os.path.abspath(__file__)), "verify_flat.json"), encoding="utf-8"))
BUDGET = float(os.getenv("VERIFY_BUDGET") or "540")   # 每板块秒数
MAXPASS = int(os.getenv("VERIFY_PASS") or "40")

def sample(scope):
    jobs = U.build_jobs()
    if scope == "quanguo":
        pid, cid, attr = "", "", 1
    else:
        pid, cid, attr = jobs[scope]
    seen = {}
    t0 = time.time()
    passes = 0
    empty_run = 0
    while passes < MAXPASS and (time.time() - t0) < BUDGET:
        passes += 1
        before = len(seen)
        for pn in range(1, 21):
            q = ("provinceId=%s&cityId=%s&tariffAttributes=%s&firstLevel=1&secondLevel=%s"
                 "&name=&startFee=0&endFee=999999&pageNum=%d&pageSize=500") % (
                pid, cid, attr, "1001", pn, 500)
            try:
                d = U.api("TariffMenuDataRetrieval", q)
            except Exception as e:
                print("   req fail p%d pn%d: %s" % (passes, pn, str(e)[:60]))
                continue
            for x in ((d.get("data") or {}).get("tariffList") or []):
                if x.get("id") is None:
                    continue
                seen[str(x["id"])] = x.get("title", "")
            if (time.time() - t0) > BUDGET:
                break
        got = len(seen) - before
        print("   pass %d: +%d cum %d (%.0fs)" % (passes, got, len(seen), time.time() - t0))
        if got == 0:
            empty_run += 1
            if empty_run >= 4:
                break
        else:
            empty_run = 0
    return seen

res = {}
for scope in ("hunan", "quanguo", "guangdong"):
    names = TARGET.get(scope) or []
    if not names:
        continue
    print("=== %s 目标 %d 条，开始采样 ===" % (scope, len(names)))
    seen = sample(scope)
    title_set = set(v for v in seen.values())
    title_set |= set(seen.keys())
    hit = [n for n in names if n in title_set]
    miss = [n for n in names if n not in title_set]
    res[scope] = {"target": len(names), "sampled": len(seen),
                  "still_present": len(hit), "absent": len(miss),
                  "present_sample": hit[:12], "absent_sample": miss[:12]}
    print("   %s: 采样 %d 条 / 目标 %d → 仍查到 %d，未查到 %d"
          % (scope, len(seen), len(names), len(hit), len(miss)))

json.dump(res, open("verify_result.json", "w", encoding="utf-8"), ensure_ascii=False, indent=1)
print(json.dumps(res, ensure_ascii=False)[:1500])
