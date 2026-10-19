#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
源站接口探测 —— 一次性诊断脚本（云端手动触发，不参与定时流程）。

目的：搞清楚「漏抓」到底能不能被判定，以及用什么手段能抓全。

探测项：
  1. 响应结构：data 顶层有哪些 key？有没有总数（total/count）字段？
     → 有总数 = 可以精确判定「抓全了没」；没有 = 只能靠多轮并集 + 编号连续性兜底
  2. 多轮子集合一性：同一分类换 UA 连抓 N 次，条数是否一致？
     → 不一致 = 源站确实在返回「确定性子集」，多轮并集有效
     → 一致但偏少 = 是固定配额上限，多轮无效，得换别的手段（分页/降速）
  3. 分页可行性：limit 改小、翻 page，条数是否变化？
     → 有效 = 可以用分页绕开单次配额上限

用法：python scripts/probe_api.py
输出：纯文本报告，跑完看 Actions 日志即可。
"""
import json
import os
import ssl
import sys
import time
import urllib.request
import uuid

from Crypto.Cipher import AES

AES_KEY = b"1234123412ABCDEF"
AES_IV = b"ABCDEF1234123412"
API_URL = ("https://h.app.coc.10086.cn/website/nrapigate/nrtariff/new/"
           "Tariff/getTariffListInfo")
REFERER = ("https://h.app.coc.10086.cn/cmcc-app/pc-pages/tariffZonePers.html"
           "?pageId=834148205904408576&prov=731&channelId=P00000010677")

UA_POOL = [
    "Mozilla/5.0 (Linux; Android 13; SM-S9110) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/120.0 Mobile Safari/537.36",
    "Mozilla/5.0 (Linux; Android 14; Pixel 8) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/120.0 Mobile Safari/537.36",
    "Mozilla/5.0 (Linux; Android 13; ELE-AL00) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/116.0 Mobile Safari/537.36",
    "Mozilla/5.0 (Linux; Android 12; V2141A) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/115.0 Mobile Safari/537.36",
    "Mozilla/5.0 (Linux; Android 13; PGT-AN00) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/113.0 Mobile Safari/537.36",
    "Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X) "
    "AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.0 Mobile Safari/604.1",
]


def _enc(p):
    b = json.dumps(p, separators=(",", ":"), ensure_ascii=False).encode()
    b = b + bytes([16 - len(b) % 16]) * (16 - len(b) % 16)
    return AES.new(AES_KEY, AES.MODE_CBC, AES_IV).encrypt(b).hex().upper()


def _dec(h):
    r = AES.new(AES_KEY, AES.MODE_CBC, AES_IV).decrypt(bytes.fromhex(h))
    return r[:-r[-1]].decode("utf-8")


def _opener():
    ctx = ssl.create_default_context()
    try:
        ctx.options |= ssl.OP_LEGACY_SERVER_CONNECT
    except AttributeError:
        pass
    return urllib.request.build_opener(urllib.request.HTTPSHandler(context=ctx))


def call(opener, ui, **over):
    params = {"cellNum": "99999999999", "province": "731", "isPublic": "1",
              "linkScn": "1", "tariffAttr": "2", "type1": "1", "type2": "2",
              "page": 1, "limit": 10000, "xk": str(uuid.uuid4())}
    params.update(over)
    ua = UA_POOL[ui % len(UA_POOL)]
    req = urllib.request.Request(
        API_URL, data=_enc(params).encode(),
        headers={"Content-Type": "application/json", "User-Agent": ua,
                 "Referer": REFERER, "Origin": "https://h.app.coc.10086.cn",
                 "Accept": "application/json"})
    raw = opener.open(req, timeout=60).read().decode()
    return json.loads(_dec(json.loads(raw)["body"]))


def count_names(d):
    n = 0
    for b in ((d.get("data") or {}).get("beans") or []):
        n += len(b.get("nonModuleList") or [])
    return n


def main():
    op = _opener()
    print("=" * 70)
    print("源站接口探测")
    print("=" * 70)

    # ---- 1. 响应结构 ----
    print("\n[1] 响应结构")
    try:
        d = call(op, 0)
        top = list((d.get("data") or {}).keys())
        print("    响应顶层 keys :", list(d.keys()))
        print("    data 顶层 keys:", top)
        beans = (d.get("data") or {}).get("beans") or []
        print("    beans 数量    :", len(beans))
        if beans:
            print("    bean[0] keys  :", list(beans[0].keys()))
            nm = (beans[0].get("nonModuleList") or [])
            if nm:
                print("    条目字段示例  :", list(nm[0].keys())[:18])
        guess = [k for k in top if any(
            w in k.lower() for w in ("total", "count", "size", "num", "sum"))]
        print("    >>> 疑似总数字段:", guess or "无（无法精确判定抓全，只能靠并集/编号）")
        n0 = count_names(d)
        print("    本轮条目数    :", n0)
    except Exception as e:
        print("    失败:", str(e)[:150])
        return 1

    # ---- 2. 多轮子集合一性 ----
    print("\n[2] 同分类换 UA 连抓 4 次（看是否返回确定性子集）")
    sizes = []
    for i in range(4):
        try:
            n = count_names(call(op, i))
            sizes.append(n)
            print("    UA#%d -> %d 条" % (i, n))
        except Exception as e:
            sizes.append(-1)
            print("    UA#%d -> 失败 %s" % (i, str(e)[:80]))
        time.sleep(8)
    ok = [s for s in sizes if s > 0]
    if len(set(ok)) == 1:
        print("    >>> 每次都一样：源站返回的是固定集合，多轮并集【无效】")
        print("    >>> 需要考虑：分页 / 降速 / 更长间隔")
    else:
        print("    >>> 条数不一致（%s）：源站在返回【确定性子集】，多轮并集【有效】"
              % sizes)

    # ---- 3. 分页可行性 ----
    print("\n[3] 分页试探（limit 改小 / 翻页）")
    for lim, pg in ((100, 1), (100, 2), (500, 1), (2000, 1)):
        try:
            n = count_names(call(op, 0, limit=lim, page=pg))
            print("    limit=%-5d page=%d -> %d 条" % (lim, pg, n))
        except Exception as e:
            print("    limit=%-5d page=%d -> 失败 %s" % (lim, pg, str(e)[:80]))
        time.sleep(6)

    print("\n" + "=" * 70)
    print("探测结束。请据此判断：")
    print("  · 有总数字段 -> 可精确校验，改用它做硬判定")
    print("  · 多轮不一致 -> 并集策略有效，加大 FETCH_ROUNDS")
    print("  · 分页有变化 -> 可用分页绕开配额")
    print("=" * 70)
    return 0


if __name__ == "__main__":
    sys.exit(main())
