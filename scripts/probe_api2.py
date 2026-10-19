#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
源站接口探测（第二轮，决定性）—— 回答「到底漏没漏、漏在哪」。

第一轮已确认：
  · 换 UA 连抓 4 次条数完全一致（721/721/721/721），名称集合也完全相同
    → 源站返回固定集合，多轮并集【无效】，不用再折腾 UA
  · data 里有 "page" 字段，每个 bean 有 nonModuleListTotal / moduleListTotal
    → 很可能存在「总数」，可精确判定抓全与否

本轮三件事：
  1. 打印 data.page 内容 —— 是否有 total / totalPage / pageSize
  2. 逐 bean 比对 nonModuleListTotal 与实收条数 —— 判断每个 bean 是否被截断
  3. 枚举 type1 × type2 全组合 —— 现有 6 个分类之外是否还有没抓的类别
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
            log("      (第%d次失败: %s)" % (i + 1, str(e)[:60]))
            time.sleep(wait)
    raise last


def post(op, attr="2", t1="1", t2="2", code="731", **over):
    p = {"cellNum": "99999999999", "province": code, "isPublic": "1",
         "linkScn": "1", "tariffAttr": attr, "type1": t1, "type2": t2,
         "page": 1, "limit": 10000, "xk": "p2-%d" % int(time.time() * 1000)}
    p.update(over)
    return retry(lambda: json.loads(F._post(op, F._encrypt(p))))


def main():
    log("=" * 70)
    log("源站接口探测（第二轮 · 决定性）")
    log("=" * 70)
    if F is None:
        return 1
    op = F._build_opener()

    # ---- 1. page 字段 ----
    log("")
    log("[1] data.page 内容（是否有总数/分页信息）")
    try:
        d = post(op)
        page = (d.get("data") or {}).get("page")
        log("    page = %s" % json.dumps(page, ensure_ascii=False)[:300])
    except Exception as e:
        log("    失败: %s" % str(e)[:150])
        return 1

    # ---- 2. 逐 bean 比对总数 ----
    log("")
    log("[2] 逐 bean 比对 nonModuleListTotal 与实收条数")
    try:
        beans = (d.get("data") or {}).get("beans") or []
        sum_total, sum_real, bad = 0, 0, 0
        for b in beans:
            tot = b.get("nonModuleListTotal")
            real = len(b.get("nonModuleList") or [])
            try:
                tot = int(tot)
            except Exception:
                tot = real
            sum_total += tot
            sum_real += real
            if tot > real:
                bad += 1
                if bad <= 8:
                    log("    截断: %s  应到 %d 实收 %d"
                        % (str(b.get("tariffName"))[:22], tot, real))
        log("    bean 数 %d" % len(beans))
        log("    应到合计 %d / 实收合计 %d" % (sum_total, sum_real))
        log("    >>> 被截断的 bean: %d 个" % bad)
        if bad:
            log("    >>> 结论：每个 bean 内部被截断，需要按 bean 分页补抓")
        else:
            log("    >>> 结论：bean 内部未被截断（差异需看下一步分类枚举）")
    except Exception as e:
        log("    失败: %s" % str(e)[:150])

    # ---- 3. 枚举 type1 × type2 ----
    log("")
    log("[3] 枚举 type1 × type2 全组合（现有 6 类之外还有没有）")
    known = {("1", "1"), ("1", "2"), ("1", "3"),
             ("2", "1"), ("2", "2"), ("2", "3")}
    for t1 in ("1", "2", "3", "4"):
        row = []
        for t2 in ("1", "2", "3", "4", "5"):
            try:
                dd = post(op, t1=t1, t2=t2)
                n = sum(len(b.get("nonModuleList") or [])
                        for b in ((dd.get("data") or {}).get("beans") or []))
                mark = "*" if (t1, t2) in known else "?"
                row.append("%s%s=%d" % (t1, t2, n) + mark if n else "%s%s=-" % (t1, t2))
            except Exception as e:
                row.append("%s%s=err" % (t1, t2))
            time.sleep(3)
        log("    type1=%s : %s" % (t1, "  ".join(row)))
    log("    （* = 现有 fetcher 已抓的分类，? = 目前没抓的）")

    # ---- 4. 按 bean 分页可行性 ----
    log("")
    log("[4] 翻页可行性（page=2/3 是否还有数据）")
    for pg in (1, 2, 3):
        try:
            n = sum(len(b.get("nonModuleList") or [])
                    for b in ((post(op, page=pg).get("data") or {}).get("beans") or []))
            log("    page=%d -> %d 条" % (pg, n))
        except Exception as e:
            log("    page=%d -> 失败 %s" % (pg, str(e)[:80]))
        time.sleep(4)

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
    try:
        pdir = os.path.join(ROOT, "probe")
        os.makedirs(pdir, exist_ok=True)
        tag = os.environ.get("GITHUB_RUN_ID") or time.strftime("%Y%m%d-%H%M%S")
        body = "\n".join(OUT)
        for name in ("probe2_%s.txt" % tag, "probe2.txt"):
            with io.open(os.path.join(pdir, name), "w", encoding="utf-8") as f:
                f.write(body)
        print("WROTE probe/probe2_%s.txt" % tag)
    except Exception as e:
        print("写文件失败", e)
    sys.exit(0)
