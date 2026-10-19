#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
源站接口探测 —— 诊断「漏抓」根因（一次性脚本，手动触发）。

结果同时打印到日志并写入 probe/result.txt（由 workflow 提交回仓库），
这样即使 Actions 日志接口不可用也能读到结论。

探测项：
  1. 响应结构：data 顶层有没有总数（total/count）字段？
     → 有总数 = 可精确判定「抓全了没」
  2. 多轮子集合一性：同一分类换 UA 连抓 N 次，条数是否一致？
     → 不一致 = 确定性子集，多轮并集有效
     → 一致但偏少 = 固定配额上限，多轮无效，需换手段
  3. 分页可行性：limit 改小、翻 page，条数是否变化？
     → 有效 = 可用分页绕开单次配额上限
  4. isPublic / linkScn 等参数是否影响返回条数
"""
import io
import json
import os
import ssl
import sys
import time
import urllib.request
import uuid

OUT = []


def log(s=""):
    print(s)
    OUT.append(str(s))


try:
    from Crypto.Cipher import AES
except Exception as e:
    log("IMPORT_FAIL: %s" % e)
    AES = None

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
    return urllib.request.build_opener(urllib.request.HTTPCookieProcessor(),
                                       urllib.request.HTTPSHandler(context=ctx))


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
    log("=" * 68)
    log("源站接口探测")
    log("=" * 68)
    if AES is None:
        log("Crypto 不可用，终止")
        return 1

    op = _opener()

    # ---- 1. 响应结构 ----
    log("")
    log("[1] 响应结构")
    try:
        d = call(op, 0)
        data = d.get("data") or {}
        log("    响应顶层 keys : %s" % list(d.keys()))
        log("    data 顶层 keys: %s" % list(data.keys()))
        beans = data.get("beans") or []
        log("    beans 数量    : %d" % len(beans))
        if beans:
            log("    bean[0] keys  : %s" % list(beans[0].keys()))
            nm = beans[0].get("nonModuleList") or []
            if nm:
                log("    条目字段      : %s" % list(nm[0].keys())[:20])
        guess = [k for k in data.keys()
                 if any(w in k.lower() for w in
                        ("total", "count", "size", "num", "sum", "rows"))]
        log("    >>> 疑似总数字段: %s" % (guess or "无"))
        log("    本轮条目数    : %d" % count_names(d))
    except Exception as e:
        log("    失败: %s" % str(e)[:200])
        return 1

    # ---- 2. 多轮子集合一性 ----
    log("")
    log("[2] 同分类换 UA 连抓 4 次（判断是否确定性子集）")
    sizes = []
    for i in range(4):
        try:
            n = count_names(call(op, i))
            sizes.append(n)
            log("    UA#%d -> %d 条" % (i, n))
        except Exception as e:
            sizes.append(-1)
            log("    UA#%d -> 失败 %s" % (i, str(e)[:100]))
        time.sleep(8)
    ok = [s for s in sizes if s > 0]
    if len(set(ok)) == 1:
        log("    >>> 完全一致：源站返回固定集合，多轮并集【无效】")
    else:
        log("    >>> 不一致 %s：确定性子集，多轮并集【有效】" % sizes)

    # ---- 3. 分页可行性 ----
    log("")
    log("[3] 分页试探（limit 改小 / 翻页）")
    base = ok[0] if ok else 0
    for lim, pg in ((100, 1), (100, 2), (500, 1), (2000, 1)):
        try:
            n = count_names(call(op, 0, limit=lim, page=pg))
            log("    limit=%-5d page=%d -> %d 条" % (lim, pg, n))
        except Exception as e:
            log("    limit=%-5d page=%d -> 失败 %s" % (lim, pg, str(e)[:100]))
        time.sleep(6)

    # ---- 4. 参数敏感性 ----
    log("")
    log("[4] 参数敏感性（isPublic / linkScn）")
    for key, val in (("isPublic", "0"), ("linkScn", "0")):
        try:
            n = count_names(call(op, 0, **{key: val}))
            log("    %s=%s -> %d 条（基准 %d）" % (key, val, n, base))
        except Exception as e:
            log("    %s=%s -> 失败 %s" % (key, val, str(e)[:100]))
        time.sleep(6)

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
    # 结果落盘，供 workflow 提交回仓库（日志接口不可用时也能读到）
    try:
        root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        pdir = os.path.join(root, "probe")
        os.makedirs(pdir, exist_ok=True)
        with io.open(os.path.join(pdir, "result.txt"), "w",
                     encoding="utf-8") as f:
            f.write("\n".join(OUT))
    except Exception as e:
        print("写文件失败", e)
    sys.exit(0)   # 永远成功，保证 workflow 走到提交步骤
