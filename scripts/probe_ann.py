#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
移动公告探测 —— 诊断「源站上新了但没同步」。

沙盒访问 10086.cn 被 403，故走 Actions 抓取并落盘。

查四件事：
  1. 列表接口返回多少条、最新一条的日期和标题
  2. 列表 JSON 是否带分页字段（pageNo/total/recordCount）
  3. 翻页（pageNo=2 之类）是否还有更新的公告
  4. 逐条打印前 20 条的 publishTime，看排序与截断
"""
import io
import json
import os
import re
import ssl
import sys
import time
import urllib.request

OUT = []


def log(s=""):
    print(s)
    OUT.append(str(s))


UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36")
BASE = ("https://www.10086.cn/aboutus/news/pannounce/hn/731/"
        "5004505_873_2361")


def get(url, times=5):
    ctx = ssl.create_default_context()
    try:
        ctx.options |= ssl.OP_LEGACY_SERVER_CONNECT
    except AttributeError:
        pass
    op = urllib.request.build_opener(urllib.request.HTTPSHandler(context=ctx))
    last = None
    for i in range(times):
        try:
            req = urllib.request.Request(
                url, headers={"User-Agent": UA,
                              "Referer": "https://www.10086.cn/"})
            return op.open(req, timeout=45).read().decode("utf-8", "ignore")
        except Exception as e:
            last = e
            log("      (第%d次失败 %s)" % (i + 1, str(e)[:70]))
            time.sleep(4)
    raise last


def main():
    log("=" * 70)
    log("移动公告探测")
    log("=" * 70)

    # 1. 主列表
    log("")
    log("[1] 列表接口 %s.json" % BASE.split("/")[-1])
    try:
        raw = get(BASE + ".json")
        j = json.loads(raw)
        log("    顶层 keys: %s" % list(j.keys()))
        cd = j.get("cData") or {}
        log("    cData keys: %s" % list(cd.keys()))
        lst = cd.get("list") or []
        log("    list 条数: %d" % len(lst))
        paging = {k: v for k, v in cd.items()
                  if any(w in str(k).lower() for w in
                         ("page", "total", "count", "size", "record", "num"))}
        log("    >>> 疑似分页字段: %s" % (paging or "无"))
        if lst:
            log("    首条字段: %s" % list(lst[0].keys()))
            log("    最新 20 条：")
            for i, r in enumerate(lst[:20]):
                log("      %2d %s | %s" % (
                    i, r.get("publishTime"), str(r.get("noticeTitle"))[:46]))
    except Exception as e:
        log("    失败: %s" % str(e)[:200])
        return 1

    # 2. 分页试探
    log("")
    log("[2] 分页试探（_2.json / _1.json / index 变体）")
    for suffix in (".json", "_1.json", "_2.json"):
        u = BASE + suffix
        try:
            t = get(u, times=2)
            n = len(((json.loads(t).get("cData") or {}).get("list") or []))
            log("    %s -> %d 条" % (suffix, n))
        except Exception as e:
            log("    %s -> 失败 %s" % (suffix, str(e)[:70]))
        time.sleep(3)

    # 3. 栏目首页，看是否有别的列表地址
    log("")
    log("[3] 栏目首页（找真实列表地址）")
    for u in ("https://www.10086.cn/aboutus/news/pannounce/hn/index_731_731.html",
              "https://www.10086.cn/aboutus/news/pannounce/hn/index_731.html"):
        try:
            t = get(u, times=2)
            ids = sorted(set(re.findall(r"_detail_(\d+)\.", t)))
            log("    %s -> %d 字节, detail id %d 个" % (u.split("/")[-1], len(t), len(ids)))
            if ids:
                log("       前 5 个 id: %s" % ids[:5])
        except Exception as e:
            log("    %s -> 失败 %s" % (u.split("/")[-1], str(e)[:70]))
        time.sleep(3)

    log("")
    log("=" * 70)
    log("探测结束")
    log("=" * 70)
    return 0


if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        log("FATAL: %s" % str(e)[:300])
    try:
        root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        pdir = os.path.join(root, "probe")
        os.makedirs(pdir, exist_ok=True)
        tag = os.environ.get("GITHUB_RUN_ID") or time.strftime("%Y%m%d-%H%M%S")
        body = "\n".join(OUT)
        for name in ("ann_%s.txt" % tag, "ann.txt"):
            with io.open(os.path.join(pdir, name), "w", encoding="utf-8") as f:
                f.write(body)
        print("WROTE probe/ann_%s.txt" % tag)
    except Exception as e:
        print("写文件失败", e)
    sys.exit(0)
