#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
源站接口探测（第二轮 · 决定性）—— 回答「到底漏没漏、漏在哪」。

第一轮已确认（结论不用再试）：
  · 换 UA 连抓 4 次：721/721/721/721，名称集合完全相同
    → 固定集合，多轮并集【无效】
  · limit=100 page=1 →216、page=2 →505，合计 721 = limit=10000 的 721
    → 该分类【已抓全】，没有截断

本轮只回答两个问题：
  1. data.page 里有没有总数？逐 bean 的 nonModuleListTotal 是否 > 实收？
  2. type1 × type2 还有没有没抓的组合？

每完成一节就把结果落盘（含被超时取消时也能拿到已跑完的部分）。
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
TAG = os.environ.get("GITHUB_RUN_ID") or time.strftime("%Y%m%d-%H%M%S")


def log(s=""):
    print(s)
    OUT.append(str(s))
    flush()


def flush():
    try:
        pdir = os.path.join(ROOT, "probe")
        os.makedirs(pdir, exist_ok=True)
        body = "\n".join(OUT)
        for name in ("probe2_%s.txt" % TAG, "probe2.txt"):
            with io.open(os.path.join(pdir, name), "w", encoding="utf-8") as f:
                f.write(body)
    except Exception:
        pass


try:
    import fetcher as F
except Exception as e:
    log("IMPORT_FAIL: %s" % e)
    F = None


def retry(fn, times=3, wait=4):
    last = None
    for i in range(times):
        try:
            return fn()
        except Exception as e:
            last = e
            time.sleep(wait)
    raise last


def post(op, attr="2", t1="1", t2="2", code="731", **over):
    p = {"cellNum": "99999999999", "province": code, "isPublic": "1",
         "linkScn": "1", "tariffAttr": attr, "type1": t1, "type2": t2,
         "page": 1, "limit": 10000, "xk": "p2-%d" % int(time.time() * 1000)}
    p.update(over)
    return retry(lambda: json.loads(F._post(op, F._encrypt(p))))


def n_of(d):
    return sum(len(b.get("nonModuleList") or [])
               for b in ((d.get("data") or {}).get("beans") or []))


def main():
    log("=" * 70)
    log("源站接口探测（第二轮）")
    log("=" * 70)
    if F is None:
        return 1
    op = F._build_opener()

    # ---- 1. page + bean 总数 ----
    log("")
    log("[1] data.page / bean 级总数")
    try:
        d = post(op)
        log("    page = %s" % json.dumps((d.get("data") or {}).get("page"),
                                         ensure_ascii=False)[:300])
        beans = (d.get("data") or {}).get("beans") or []
        st, sr, bad = 0, 0, 0
        for b in beans:
            try:
                tot = int(b.get("nonModuleListTotal"))
            except Exception:
                tot = len(b.get("nonModuleList") or [])
            real = len(b.get("nonModuleList") or [])
            st += tot
            sr += real
            if tot > real:
                bad += 1
                if bad <= 6:
                    log("    截断: %s 应到%d 实收%d"
                        % (str(b.get("tariffName"))[:20], tot, real))
        log("    bean %d 个：应到 %d / 实收 %d / 截断 %d 个"
            % (len(beans), st, sr, bad))
        log("    >>> %s" % ("每个 bean 内部被截断，需按 bean 补抓"
                            if bad else "bean 内部未截断（本分类已抓全）"))
    except Exception as e:
        log("    失败: %s" % str(e)[:150])

    # ---- 2. 分类枚举（精简：只跑必要的） ----
    log("")
    log("[2] type1 × type2 枚举（* = fetcher 已抓，? = 没抓）")
    known = {("1", "1"), ("1", "2"), ("1", "3"),
             ("2", "1"), ("2", "2"), ("2", "3")}
    for t1 in ("1", "2", "3"):
        row = []
        for t2 in ("1", "2", "3", "4"):
            try:
                n = n_of(post(op, t1=t1, t2=t2))
                row.append("%s%s=%d%s" % (t1, t2, n,
                                          "*" if (t1, t2) in known else "?"))
            except Exception:
                row.append("%s%s=err" % (t1, t2))
            time.sleep(2)
        log("    type1=%s : %s" % (t1, "  ".join(row)))

    log("")
    log("=" * 70)
    log("第二轮探测结束")
    log("=" * 70)
    return 0


if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        log("FATAL: %s" % str(e)[:300])
    flush()
    print("WROTE probe/probe2_%s.txt" % TAG)
    sys.exit(0)
