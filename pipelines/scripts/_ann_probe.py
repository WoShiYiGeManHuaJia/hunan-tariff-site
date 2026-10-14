#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""公告抓取探测（电信详情为空 / 联通列表不更新）——只打印，不写盘"""
import json, os, sys, time, re, base64, gzip, random, ssl
import urllib.request
from Crypto.Cipher import AES, PKCS1_v1_5
from Crypto.PublicKey import RSA
from Crypto.Util.Padding import pad

UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36")

# ── 电信 ─────────────────────────────────────────────
TC_REC = "https://www.189.cn/wtBusiness/wtservice/nc/recPos/getRecPosInfo.do"
TC_DET = "https://www.189.cn/wtBusiness/wtservice/nc/announcement/getAnnouncementDetail.do"
TC_PROV = "600203"
TC_TYPE = "wt_sy_bzzx"
TC_FCODE = "Y121043001"
TC_PUBKEY = (
    "MIIBIjANBgkqhkiG9w0BAQEFAAOCAQ8AMIIBCgKCAQEAmUa6oMSBZrhfOjXCaYYIE9Lvj+r8nBIv"
    "CpydQmeG5CbeK5Qlwor+kFCrrPtcoYSowuUCB7YYsLYF6HVvf3Utw9FdLq7T8uNnfz2wxvp3N3Mi"
    "f5Rbhs7skrMvfy83zl7g9a1Xgz4OxmYbrm70E08F4Hu5K+86x9Qo+k8hSnJ4mkfb/fFL1/Im1n+i"
    "p2dBJ+vZt6mq8GykuAxQm4pb1UZw37HtdSR3WnU9Li0gDvXdJ87DAP0r7xF2DfTAQiAKP+3mdwlb"
    "KZ8hM0W7Do/7w+fBaOi+GCFJKvNDNVuH7G1OaEUuQH1xr3hoYAgqMdKOZWlZH+wbNqyAOxPL9V5K"
    "LF/30wIDAQAB"
)


def tc_post(url, obj, tries=3):
    pub = RSA.import_key(base64.b64decode(TC_PUBKEY))
    last = None
    for a in range(tries):
        try:
            key = os.urandom(16)
            iv = os.urandom(16)
            ct = AES.new(key, AES.MODE_CBC, iv).encrypt(pad(json.dumps(obj, ensure_ascii=False).encode(), 16))
            inner = json.dumps({"key": base64.b64encode(key).decode(),
                                "iv": base64.b64encode(iv).decode()}, separators=(",", ":"))
            payload = {"param": base64.b64encode(ct).decode(),
                       "key": base64.b64encode(PKCS1_v1_5.new(pub).encrypt(inner.encode())).decode()}
            tid = "".join("%x" % random.randint(0, 15) for _ in range(32))
            req = urllib.request.Request(
                url, data=json.dumps(payload, separators=(",", ":")).encode(), method="POST",
                headers={"User-Agent": UA, "Content-Type": "application/json;charset=UTF-8",
                         "Accept": "application/json, text/plain, */*",
                         "Origin": "https://www.189.cn",
                         "Referer": "https://www.189.cn/web/notice/index.html",
                         "Fcode": TC_FCODE, "TransactionId": tid,
                         "Accept-Language": "zh-CN,zh;q=0.9"})
            with urllib.request.urlopen(req, timeout=30) as r:
                raw = r.read()
                if r.headers.get("Content-Encoding") == "gzip":
                    raw = gzip.decompress(raw)
                return json.loads(raw.decode("utf-8", "replace"))
        except Exception as e:
            last = "ERR " + repr(e)[:160]
            time.sleep(2 * (a + 1))
    return {"__err": last}


def probe_telecom():
    print("=" * 60)
    print("[电信] 列表接口")
    r = tc_post(TC_REC, {"shopId": "20001", "type": TC_TYPE, "order": 1,
                         "provinceCode": TC_PROV, "cityCode": ""})
    if r.get("__err"):
        print("  列表失败:", r["__err"])
        return
    print("  code=%s message=%s" % (r.get("code"), r.get("message")))
    fis = []
    for d in (r.get("data") or []):
        for x in (d.get("floorItems") or []):
            fis.append(x)
    print("  floorItems =", len(fis))
    if not fis:
        return
    for x in fis[:3]:
        print("  --- item ---")
        for k in sorted(x.keys()):
            v = x.get(k)
            s = str(v)
            print("     %-22s %s" % (k, s[:70]))
    # 详情尝试
    print("[电信] 详情接口尝试（最新 3 条 × 4 种参数组合）")
    for x in fis[:3]:
        title = (x.get("title") or "")[:22]
        eoc = x.get("externalOfferCode") or ""
        oid = x.get("offerCode") or ""
        iid = x.get("id") or ""
        typ = x.get("type") or TC_TYPE
        print("  ## %s | externalOfferCode=%r offerCode=%r id=%r type=%r"
              % (title, eoc, oid, iid, typ))
        combos = [
            ("A type自身+eoc", {"type": typ, "offerCode": eoc, "provinceCode": TC_PROV, "cityCode": ""}),
            ("B type自身+id", {"type": typ, "offerCode": iid, "provinceCode": TC_PROV, "cityCode": ""}),
            ("C 写死type+eoc", {"type": TC_TYPE, "offerCode": eoc, "provinceCode": TC_PROV, "cityCode": ""}),
            ("D 加shopId", {"shopId": "20001", "type": typ, "offerCode": eoc,
                            "provinceCode": TC_PROV, "cityCode": ""}),
        ]
        for nm, obj in combos:
            d = tc_post(TC_DET, obj, tries=2)
            if d.get("__err"):
                print("     %-14s ERR %s" % (nm, d["__err"][:90]))
                continue
            node = d.get("data") or {}
            c = node.get("content") or ""
            print("     %-14s code=%s msg=%s dataKeys=%s content=%d字"
                  % (nm, d.get("code"), str(d.get("message"))[:30],
                     (list(node.keys())[:8] if isinstance(node, dict) else type(node).__name__),
                     len(str(c))))
            time.sleep(1.2)


# ── 联通 ─────────────────────────────────────────────
UNI_LIST = "https://www.10010.com/mall/service/query/announcementquery"
UNI_DET = "https://www.10010.com/mall/service/query/announcementquerydetail"
UNI_HDRS = {
    "User-Agent": UA,
    "Content-Type": "application/x-www-form-urlencoded; charset=UTF-8",
    "Referer": "https://www.10010.com/wt_links/index.html",
    "Origin": "https://www.10010.com",
    "X-Requested-With": "XMLHttpRequest",
    "Accept": "application/json, text/javascript, */*; q=0.01",
    "Accept-Language": "zh-CN,zh;q=0.9",
}


def uni_post(url, data):
    req = urllib.request.Request(url, data=urllib.parse.urlencode(data).encode(),
                                 headers=UNI_HDRS, method="POST")
    with urllib.request.urlopen(req, timeout=30) as r:
        return json.loads(r.read().decode("utf-8", "replace"))


def probe_unicom():
    print("=" * 60)
    print("[联通] 列表接口")
    import urllib.parse
    for prov in ["074", ""]:
        for ps in ["100", "12"]:
            try:
                j = uni_post(UNI_LIST, {"pageNo": "1", "pageSize": ps,
                                        "province": prov, "condition": "0", "title": ""})
            except Exception as e:
                print("  province=%r pageSize=%s -> ERR %s" % (prov, ps, repr(e)[:110]))
                continue
            lst = j.get("result") or []
            dates = sorted([(r.get("publishTime") or "")[:10] for r in lst], reverse=True)
            print("  province=%-4r pageSize=%-4s 顶层keys=%s result=%d 最新日期=%s"
                  % (prov, ps, list(j.keys())[:10], len(lst), dates[:3]))
            for k in ("total", "totalCount", "pageCount", "records", "count"):
                if k in j:
                    print("      %s=%s" % (k, j[k]))
            if lst:
                print("      首条字段:", {k: str(v)[:40] for k, v in list(lst[0].items())[:12]})
            time.sleep(0.6)
    # 详情抽查
    try:
        j = uni_post(UNI_LIST, {"pageNo": "1", "pageSize": "12",
                                "province": "074", "condition": "0", "title": ""})
        lst = j.get("result") or []
        for row in sorted(lst, key=lambda r: (r.get("publishTime") or ""), reverse=True)[:2]:
            did = row.get("id")
            d = uni_post(UNI_DET, {"announcementId": did, "pageSize": "12",
                                   "pageNo": "1", "province": "074"})
            n = d.get("tNoticeDto") or {}
            print("  详情 id=%s noticeTime=%s content=%d字 keys=%s"
                  % (did, str(n.get("noticeTime"))[:20], len(str(n.get("noticeDetails") or "")),
                     list(n.keys())[:8]))
            time.sleep(0.6)
    except Exception as e:
        print("  详情探测失败:", repr(e)[:120])


if __name__ == "__main__":
    import urllib.parse
    try:
        probe_telecom()
    except Exception:
        import traceback
        print("[电信] 探测异常\n" + traceback.format_exc()[:1500])
    try:
        probe_unicom()
    except Exception:
        import traceback
        print("[联通] 探测异常\n" + traceback.format_exc()[:1500])
