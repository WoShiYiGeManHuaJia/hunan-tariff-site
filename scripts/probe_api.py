#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
源站接口探测 —— 诊断「漏抓」根因（一次性脚本，手动触发）。

复用 pipelines/mobile/fetcher.py 已验证的请求实现；源站 SSL 握手偶发
UNSAFE_LEGACY_RENEGOTIATION_DISABLED（fetcher 内部靠重试扛过去），
故所有请求都套重试，否则第一次失败就全线崩。

结果写入 probe/result_<run_id>.txt（唯一名，避免 contents API sha 冲突）。
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


def retry(fn, times=6, wait=5):
    last = None
    for i in range(times):
        try:
            return fn()
        except Exception as e:
            last = e
            log("    (第%d次失败: %s)" % (i + 1, str(e)[:70]))
            time.sleep(wait)
    raise last


def post(op, **params):
    base = {"cellNum": "99999999999", "province": "731", "isPublic": "1",
            "linkScn": "1", "tariffAttr": "2", "type1": "1", "type2": "2",
            "page": 1, "limit": 10000,
            "xk": "probe-%d" % int(time.time() * 1000)}
    base.update(params)
    return retry(lambda: F._post(op, F._encrypt(base)))


def n_items(raw):
    d = json.loads(raw).get("data") or {}
    return sum(len(b.get("nonModuleList") or []) for b in (d.get("beans") or []))


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
        raw = post(op)
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
        guess = [k for k in (list(d.keys()) + list(data.keys()))
                 if any(w in str(k).lower() for w in
                        ("total", "count", "size", "num", "sum", "rows",
                         "page", "pages"))]
        log("    >>> 疑似总数/分页字段: %s" % (guess or "无"))
        log("    本分类条目数  : %d" % n_items(raw))
    except Exception as e:
        log("    失败: %s" % str(e)[:200])
        return 1

    # ---- 2. 多轮子集合一性 ----
    log("")
    log("[2] 换 UA 连抓 4 次（判断是否确定性子集）")
    sizes, sets = [], []
    for i in range(4):
        try:
            it = retry(lambda i=i: F._fetch_cell(
                op, "2", "1", "2", "731",
                ua=F.UA_POOL[i % len(F.UA_POOL)]))
            sizes.append(len(it))
            sets.append(set(x["name"] for x in it))
            log("    UA#%d -> %d 条" % (i, len(it)))
        except Exception as e:
            sizes.append(-1)
            log("    UA#%d -> 失败 %s" % (i, str(e)[:90]))
        time.sleep(6)
    ok = [s for s in sizes if s > 0]
    if len(set(ok)) == 1:
        log("    >>> 条数完全一致：固定集合，多轮并集【无效】")
    else:
        log("    >>> 条数不一致 %s：确定性子集，并集【有效】" % sizes)
    if len(sets) >= 2 and sets[0] and sets[1]:
        if sets[0] == sets[1]:
            log("    >>> 名称集合完全相同：换 UA 未带来任何新条目")
        else:
            log("    >>> 集合有差异：UA#0 独有 %d / UA#1 独有 %d"
                % (len(sets[0] - sets[1]), len(sets[1] - sets[0])))

    # ---- 3. 分页可行性 ----
    log("")
    log("[3] 分页试探（limit 改小 / 翻页）")
    for lim, pg in ((100, 1), (100, 2), (500, 1), (2000, 1), (10000, 2)):
        try:
            n = n_items(post(op, limit=lim, page=pg))
            log("    limit=%-5d page=%d -> %d 条" % (lim, pg, n))
        except Exception as e:
            log("    limit=%-5d page=%d -> 失败 %s" % (lim, pg, str(e)[:90]))
        time.sleep(5)

    # ---- 4. 参数敏感性 ----
    log("")
    log("[4] 参数敏感性")
    base = ok[0] if ok else 0
    for key, val in (("isPublic", "0"), ("linkScn", "0"), ("tariffAttr", "1")):
        try:
            n = n_items(post(op, **{key: val}))
            log("    %s=%s -> %d 条（基准 %d）" % (key, val, n, base))
        except Exception as e:
            log("    %s=%s -> 失败 %s" % (key, val, str(e)[:90]))
        time.sleep(5)

    log("")
    log("=" * 68)
    log("探测结束")
    log("=" * 68)
    return 0


if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        log("FATAL: %s" % str(e)[:300])
    try:
        pdir = os.path.join(ROOT, "probe")
        os.makedirs(pdir, exist_ok=True)
        tag = os.environ.get("GITHUB_RUN_ID") or time.strftime("%Y%m%d-%H%M%S")
        body = "\n".join(OUT)
        with io.open(os.path.join(pdir, "result_%s.txt" % tag), "w",
                     encoding="utf-8") as f:
            f.write(body)
        with io.open(os.path.join(pdir, "result.txt"), "w",
                     encoding="utf-8") as f:
            f.write(body)
        print("WROTE probe/result_%s.txt" % tag)
    except Exception as e:
        print("写文件失败", e)
    sys.exit(0)
