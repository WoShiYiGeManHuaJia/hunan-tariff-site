#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""第二轮探测：联通分页全量 / 电信正文替代来源"""
import json, os, time, base64, gzip, random, re, ssl
import urllib.request, urllib.parse
from Crypto.Cipher import AES, PKCS1_v1_5
from Crypto.PublicKey import RSA
from Crypto.Util.Padding import pad

UA_M = ("Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X) AppleWebKit/605.1.15 "
        "(KHTML, like Gecko) Version/17.0 Mobile/15E148 Safari/604.1")
UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36")

# ───────── 联通 ─────────
UNI_LIST = "https://www.10010.com/mall/service/query/announcementquery"
UNI_HDRS = {
    "User-Agent": UA,
    "Content-Type": "application/x-www-form-urlencoded; charset=UTF-8",
    "Referer": "https://www.10010.com/wt_links/index.html",
    "Origin": "https://www.10010.com",
    "X-Requested-With": "XMLHttpRequest",
    "Accept": "application/json, text/javascript, */*; q=0.01",
    "Accept-Language": "zh-CN,zh;q=0.9",
}


def uni_post(data):
    req = urllib.request.Request(UNI_LIST, data=urllib.parse.urlencode(data).encode(),
                                 headers=UNI_HDRS, method="POST")
    with urllib.request.urlopen(req, timeout=30) as r:
        return json.loads(r.read().decode("utf-8", "replace"))


def probe_unicom_all():
    print("=" * 60)
    print("[联通] 分页全量")
    all_rows, total = [], None
    for p in range(1, 5):
        try:
            j = uni_post({"pageNo": str(p), "pageSize": "100", "province": "074",
                          "condition": "0", "title": ""})
        except Exception as e:
            print("  page%d ERR %s" % (p, repr(e)[:90]))
            break
        lst = j.get("result") or []
        total = j.get("totalCount")
        print("  page%d -> %d 条 (totalCount=%s)" % (p, len(lst), total))
        all_rows += lst
        if not lst or len(all_rows) >= (total or 0):
            break
        time.sleep(0.5)
    rows = sorted(all_rows, key=lambda r: (r.get("publishTime") or ""), reverse=True)
    print("  合计 %d 条，最新 8 条：" % len(rows))
    for r in rows[:8]:
        print("     %s | %s | %s" % ((r.get("publishTime") or "")[:10],
                                      (r.get("title") or "")[:34], r.get("id")))
    # 其它 condition 值是否含更新的公告
    for cond in ["1", "2"]:
        try:
            j = uni_post({"pageNo": "1", "pageSize": "20", "province": "074",
                          "condition": cond, "title": ""})
            lst = j.get("result") or []
            d = sorted([(x.get("publishTime") or "")[:10] for x in lst], reverse=True)
            print("  condition=%s -> %d 条 最新=%s" % (cond, len(lst), d[:3]))
        except Exception as e:
            print("  condition=%s ERR %s" % (cond, repr(e)[:80]))
        time.sleep(0.5)


# ───────── 电信 ─────────
TC_REC = "https://www.189.cn/wtBusiness/wtservice/nc/recPos/getRecPosInfo.do"
TC_PROV = "600203"
TC_FCODE = "Y121043001"
TC_PUBKEY = (
    "MIIBIjANBgkqhkiG9w0BAQEFAAOCAQ8AMIIBCgKCAQEAmUa6oMSBZrhfOjXCaYYIE9Lvj+r8nBIv"
    "CpydQmeG5CbeK5Qlwor+kFCrrPtcoYSowuUCB7YYsLYF6HVvf3Utw9FdLq7T8uNnfz2wxvp3N3Mi"
    "f5Rbhs7skrMvfy83zl7g9a1Xgz4OxmYbrm70E08F4Hu5K+86x9Qo+k8hSnJ4mkfb/fFL1/Im1n+i"
    "p2dBJ+vZt6mq8GykuAxQm4pb1UZw37HtdSR3WnU9Li0gDvXdJ87DAP0r7xF2DfTAQiAKP+3mdwlb"
    "KZ8hM0W7Do/7w+fBaOi+GCFJKvNDNVuH7G1OaEUuQH1xr3hoYAgqMdKOZWlZH+wbNqyAOxPL9V5K"
    "LF/30wIDAQAB"
)


def tc_post(url, obj, tries=2):
    pub = RSA.import_key(base64.b64decode(TC_PUBKEY))
    key = os.urandom(16); iv = os.urandom(16)
    ct = AES.new(key, AES.MODE_CBC, iv).encrypt(pad(json.dumps(obj, ensure_ascii=False).encode(), 16))
    inner = json.dumps({"key": base64.b64encode(key).decode(),
                        "iv": base64.b64encode(iv).decode()}, separators=(",", ":"))
    payload = {"param": base64.b64encode(ct).decode(),
               "key": base64.b64encode(PKCS1_v1_5.new(pub).encrypt(inner.encode())).decode()}
    tid = "".join("%x" % random.randint(0, 15) for _ in range(32))
    req = urllib.request.Request(url, data=json.dumps(payload, separators=(",", ":")).encode(),
                                 method="POST",
                                 headers={"User-Agent": UA, "Content-Type": "application/json;charset=UTF-8",
                                          "Accept": "application/json, text/plain, */*",
                                          "Origin": "https://www.189.cn",
                                          "Referer": "https://www.189.cn/web/notice/index.html",
                                          "Fcode": TC_FCODE, "TransactionId": tid,
                                          "Accept-Language": "zh-CN,zh;q=0.9"})
    last = None
    for a in range(tries):
        try:
            with urllib.request.urlopen(req, timeout=30) as r:
                raw = r.read()
                if r.headers.get("Content-Encoding") == "gzip":
                    raw = gzip.decompress(raw)
                return json.loads(raw.decode("utf-8", "replace"))
        except Exception as e:
            last = "ERR " + repr(e)[:120]
            time.sleep(2)
    return {"__err": last}


def http_get(url, hdrs=None, timeout=25):
    req = urllib.request.Request(url, headers=hdrs or {"User-Agent": UA,
                                                       "Accept-Language": "zh-CN,zh;q=0.9"})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            raw = r.read()
            if r.headers.get("Content-Encoding") == "gzip":
                raw = gzip.decompress(raw)
            return r.status, raw.decode("utf-8", "replace")
    except Exception as e:
        return None, repr(e)[:120]


def probe_telecom_alt():
    print("=" * 60)
    print("[电信] 正文替代来源探测")
    # 1) 官网公告页能否直连
    for u in ["https://www.189.cn/web/notice/index.html",
              "https://www.189.cn/web/notice"]:
        st, body = http_get(u)
        print("  GET %-48s -> %s len=%s" % (u[:48], st, len(body) if isinstance(body, str) else body))
        if st == 200 and isinstance(body, str):
            # 找详情链接格式
            links = set(re.findall(r'["\'](/web/[^"\']*detail[^"\']*)["\']', body)) or \
                    set(re.findall(r'["\'](/web/notice[^"\']{0,60})["\']', body))
            print("     候选链接:", list(links)[:8])
    # 2) 拿列表，尝试用 sceneId / mainOfferCode 构造详情 URL
    r = tc_post(TC_REC, {"shopId": "20001", "type": "wt_sy_bzzx", "order": 1,
                         "provinceCode": TC_PROV, "cityCode": ""})
    if r.get("__err"):
        print("  列表失败:", r["__err"]); return
    fis = []
    for d in (r.get("data") or []):
        for x in (d.get("floorItems") or []):
            fis.append(x)
    fis = [x for x in fis if x.get("externalOfferCode")]
    fis.sort(key=lambda x: str(x.get("liveStartTime") or ""), reverse=True)
    x = fis[0]
    eoc = x["externalOfferCode"]; sid = x.get("sceneId") or ""; mcode = x.get("mainOfferCode") or ""
    print("  样本: %s | eoc=%s sceneId=%s mainOfferCode=%s" % ((x.get("title") or "")[:24], eoc, sid[:40], mcode))
    cands = [
        "https://www.189.cn/web/notice/detail.html?offerCode=%s" % eoc,
        "https://www.189.cn/web/notice/index.html?offerCode=%s" % eoc,
        "https://www.189.cn/web/notice/detail.html?id=%s" % mcode,
        "https://www.189.cn/web/noticeDetail.html?offerCode=%s" % eoc,
    ]
    for u in cands:
        st, body = http_get(u)
        n = len(body) if isinstance(body, str) else 0
        print("  GET %-56s -> %s len=%s" % (u[:56], st, n))
        if st == 200 and n > 2000:
            txt = re.sub(r"<[^>]+>", " ", body)
            print("     文本片段:", re.sub(r"\s+", " ", txt)[:120])


if __name__ == "__main__":
    try:
        probe_unicom_all()
    except Exception:
        import traceback; print(traceback.format_exc()[:1200])
    try:
        probe_telecom_alt()
    except Exception:
        import traceback; print(traceback.format_exc()[:1200])
