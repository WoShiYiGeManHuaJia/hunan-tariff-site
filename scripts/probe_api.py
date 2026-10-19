#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
源站接口探测 —— 诊断「漏抓」根因（一次性脚本，手动触发）。

复用 pipelines/mobile/fetcher.py 里已验证可用的 SSL/请求实现，
避免自己造轮子导致握手失败（曾因 SSL legacy renegotiation 直接失败）。

探测项：
  1. 响应结构：有没有总数（total/count）字段 → 能否精确判定抓全
  2. 多轮子集合一性：换 UA 连抓 N 次条数是否一致 → 并集策略是否有效
  3. 分页可行性：limit 改小 / 翻 page → 能否用分页绕开配额
  4. 参数敏感性：isPublic / linkScn 是否影响返回条数

结果写入 probe/result.txt，由 workflow 用 contents API 写回仓库。
"""
import io
import json
import os
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, os.path.join(ROOT, "pipelines", "mobile"))

OUT = []


def log(s=""):
    print(s)
    OUT.append(str(s))


try:
    import fetcher as F
except Exception as e:
    log("IMPORT_FAIL: %s" % e)
    F = None


def main():
    log("=" * 68)
    log("源站接口探测")
    log("=" * 68)
    if F is None:
        return 1

    op = F._build_opener()

    # ---- 1. 响应结构 ----
    log("")
    log("[1] 响应结构")
    try:
        raw = F._post(op, F._encrypt({
            "cellNum": "99999999999", "province": "731", "isPublic": "1",
            "linkScn": "1", "tariffAttr": "2", "type1": "1", "type2": "2",
            "page": 1, "limit": 10000, "xk": "probe-1",
        }))
        data = json.loads(raw)
        d = data.get("data") or {}
        log("    响应顶层 keys : %s" % list(data.keys()))
        log("    data 顶层 keys: %s" % list(d.keys()))
        beans = d.get("beans") or []
        log("    beans 数量    : %d" % len(beans))
        if beans:
            log("    bean[0] keys  : %s" % list(beans[0].keys()))
            nm = beans[0].get("nonModuleList") or []
            if nm:
                log("    条目字段数    : %d" % len(nm[0]))
        guess = [k for k in list(d.keys()) + list(data.keys())
                 if any(w in str(k).lower() for w in
                        ("total", "count", "size", "num", "sum", "rows", "page"))]
        log("    >>> 疑似总数/分页字段: %s" % (guess or "无"))
        n0 = F._fetch_cell(op, "2", "1", "2", "731")
        log("    本分类条目数  : %d" % len(n0))
    except Exception as e:
        log("    失败: %s" % str(e)[:200])
        return 1

    # ---- 2. 多轮子集合一性 ----
    log("")
    log("[2] 换 UA 连抓 4 次（判断是否确定性子集）")
    sizes, sets = [], []
    for i in range(4):
        try:
            items = F._fetch_cell(op, "2", "1", "2", "731",
                                  ua=F.UA_POOL[i % len(F.UA_POOL)])
            sizes.append(len(items))
            sets.append(set(x["name"] for x in items))
            log("    UA#%d -> %d 条" % (i, len(items)))
        except Exception as e:
            sizes.append(-1)
            log("    UA#%d -> 失败 %s" % (i, str(e)[:100]))
        time.sleep(6)
    ok = [s for s in sizes if s > 0]
    if len(set(ok)) == 1:
        log("    >>> 条数完全一致：固定集合，多轮并集【无效】")
    else:
        log("    >>> 条数不一致 %s：确定性子集，并集【有效】" % sizes)
    if len(sets) >= 2 and sets[0]:
        if sets[0] == sets[1]:
            log("    >>> 名称集合完全相同：换 UA 没带来任何新条目")
        else:
            log("    >>> 名称集合有差异：UA#0 独有 %d，UA#1 独有 %d"
                % (len(sets[0] - sets[1]), len(sets[1] - sets[0])))

    # ---- 3. 分页可行性 ----
    log("")
    log("[3] 分页试探（limit 改小 / 翻页）")
    for lim, pg in ((100, 1), (100, 2), (500, 1), (2000, 1), (10000, 2)):
        try:
            raw = F._post(op, F._encrypt({
                "cellNum": "99999999999", "province": "731", "isPublic": "1",
                "linkScn": "1", "tariffAttr": "2", "type1": "1", "type2": "2",
                "page": pg, "limit": lim, "xk": "probe-%d-%d" % (lim, pg),
            }))
            d2 = json.loads(raw).get("data") or {}
            n = sum(len(b.get("nonModuleList") or [])
                    for b in (d2.get("beans") or []))
            log("    limit=%-5d page=%d -> %d 条" % (lim, pg, n))
        except Exception as e:
            log("    limit=%-5d page=%d -> 失败 %s" % (lim, pg, str(e)[:100]))
        time.sleep(5)

    # ---- 4. 参数敏感性 ----
    log("")
    log("[4] 参数敏感性（isPublic / linkScn / tariffAttr）")
    base = ok[0] if ok else 0
    for key, val in (("isPublic", "0"), ("linkScn", "0"), ("tariffAttr", "1")):
        try:
            raw = F._post(op, F._encrypt({
                "cellNum": "99999999999", "province": "731", "isPublic": "1",
                "linkScn": "1", "tariffAttr": "2", "type1": "1", "type2": "2",
                "page": 1, "limit": 10000, "xk": "probe-%s-%s" % (key, val),
                key: val,
            }))
            d3 = json.loads(raw).get("data") or {}
            n = sum(len(b.get("nonModuleList") or [])
                    for b in (d3.get("beans") or []))
            log("    %s=%s -> %d 条（基准 %d）" % (key, val, n, base))
        except Exception as e:
            log("    %s=%s -> 失败 %s" % (key, val, str(e)[:100]))
        time.sleep(5)

    log("")
    log("=" * 68)
    log("探测结束")
    log("=" * 68)
    return 0


if __name__ == "__main__":
    rc = 0
    try:
        rc = main()
    except Exception as e:
        log("FATAL: %s" % str(e)[:300])
        rc = 2
    try:
        pdir = os.path.join(ROOT, "probe")
        os.makedirs(pdir, exist_ok=True)
        with io.open(os.path.join(pdir, "result.txt"), "w",
                     encoding="utf-8") as f:
            f.write("\n".join(OUT))
    except Exception as e:
        print("写文件失败", e)
    sys.exit(0)
