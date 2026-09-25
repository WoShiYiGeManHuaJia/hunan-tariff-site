#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""中国电信公告抓取（湖南）

接口(来自 www.189.cn/web/notice 前端 chunk)：
  列表分类  POST https://www.189.cn/wtBusiness/wtservice/nc/search/list.do
            {shopId:"20001", type:"wt_sy_bzzx", floorType:"1", provinceCode, cityCode}
  分类条目  POST 同上 + order=<分类order>   → data[0].floorItems
  详情      POST https://www.189.cn/wtBusiness/wtservice/nc/announcement/getAnnouncementDetail.do
            {type, offerCode, provinceCode, cityCode} → {link, content, title}
加密: AES-CBC(随机key/iv) 加密 body, RSA-PKCS1v1.5(公钥) 加密 {key,iv} → {param,key}
"""
import json, os, sys, time, uuid, base64, datetime, traceback
import urllib.request
from Crypto.Cipher import AES, PKCS1_v1_5
from Crypto.PublicKey import RSA
from Crypto.Util.Padding import pad
from Crypto.Random import get_random_bytes

UA = ("Mozilla/5.0 (Linux; Android 13; SM-S9110) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/120.0 Mobile Safari/537.36")
BASE = "https://www.189.cn"
PUBKEY_B64 = "MIIBIjANBgkqhkiG9w0BAQEFAAOCAQ8AMIIBCgKCAQEAmUa6oMSBZrhfOjXCaYYIE9Lvj+r8nBIvCpydQmeG5CbeK5Qlwor+kFCrrPtcoYSowuUCB7YYsLYF6HVvf3Utw9FdLq7T8uNnfz2wxvp3N3Mif5Rbhs7skrMvfy83zl7g9a1Xgz4OxmYbrm70E08F4Hu5K+86x9Qo+k8hSnJ4mkfb/fFL1/Im1n+ip2dBJ+vZt6mq8GykuAxQm4pb1UZw37HtdSR3WnU9Li0gDvXdJ87DAP0r7xF2DfTAQiAKP+3mdwlbKZ8hM0W7Do/7w+fBaOi+GCFJKvNDNVuH7G1OaEUuQH1xr3hoYAgqMdKOZWlZH+wbNqyAOxPL9V5KLF/30wIDAQAB"
PROV = os.environ.get("TC_PROV", "600203")   # 湖南
CITY = os.environ.get("TC_CITY", "hn")
MAX_KEEP = int(os.environ.get("TC_KEEP", "15"))
TYPE = "wt_sy_bzzx"

_rsa = None


def _cipher():
    global _rsa
    if _rsa is None:
        _rsa = PKCS1_v1_5.new(RSA.import_key(base64.b64decode(PUBKEY_B64)))
    return _rsa


def spost(path, obj, timeout=40, tries=3):
    last = ""
    for a in range(tries):
        try:
            aeskey = get_random_bytes(16)
            iv = get_random_bytes(16)
            ct = AES.new(aeskey, AES.MODE_CBC, iv).encrypt(
                pad(json.dumps(obj, ensure_ascii=False).encode("utf-8"), 16))
            k = base64.b64encode(_cipher().encrypt(json.dumps(
                {"key": base64.b64encode(aeskey).decode(),
                 "iv": base64.b64encode(iv).decode()}).encode())).decode()
            body = json.dumps({"param": base64.b64encode(ct).decode(), "key": k}).encode()
            req = urllib.request.Request(BASE + path, data=body, method="POST", headers={
                "User-Agent": UA,
                "Referer": "https://www.189.cn/web/notice",
                "Accept": "application/json, text/plain, */*",
                "Content-Type": "application/json;charset=UTF-8",
                "Origin": "https://www.189.cn",
                "Fcode": "Y121043001",
                "TransactionId": uuid.uuid4().hex,
            })
            with urllib.request.urlopen(req, timeout=timeout) as r:
                return json.loads(r.read().decode("utf-8", "ignore"))
        except Exception as e:
            last = "ERR " + str(e)[:200]
            time.sleep(1.5 * (a + 1))
    return {"__err": last}


def fmt_date(s):
    t = str(s or "").strip()
    if len(t) >= 8 and t[:8].isdigit():
        return "%s-%s-%s" % (t[:4], t[4:6], t[6:8])
    return t[:10]


def fetch_all():
    tabs = spost("/wtBusiness/wtservice/nc/search/list.do",
                 {"shopId": "20001", "type": TYPE, "floorType": "1",
                  "provinceCode": PROV, "cityCode": CITY})
    if tabs.get("__err"):
        raise RuntimeError("tab list failed: " + tabs["__err"])
    if tabs.get("code") != "S_COMMON_0000":
        raise RuntimeError("tab list code=%s msg=%s" % (tabs.get("code"), tabs.get("message")))
    tabdata = tabs.get("data") or []
    items = []
    for t in tabdata:
        order = t.get("order")
        tabname = t.get("title") or ""
        if order is None:
            continue
        d = spost("/wtBusiness/wtservice/nc/search/list.do",
                  {"shopId": "20001", "type": TYPE, "order": order,
                   "provinceCode": PROV, "cityCode": CITY})
        fis = ((d.get("data") or [{}])[0].get("floorItems") or [])
        for f in fis:
            items.append({
                "title": f.get("title") or "",
                "date": fmt_date(f.get("liveStartTime")),
                "offerCode": f.get("externalOfferCode") or "",
                "type": f.get("type") or TYPE,
                "link": f.get("link") or "",
                "linkType": f.get("linkType") or "",
                "tab": tabname,
            })
        time.sleep(0.5)
    # 去重 + 按日期降序
    seen = set()
    uniq = []
    for it in sorted(items, key=lambda x: (x["date"], x["title"]), reverse=True):
        k = (it["title"], it["date"])
        if k in seen:
            continue
        seen.add(k)
        uniq.append(it)
    return uniq[:MAX_KEEP]


def fetch_detail(it):
    d = spost("/wtBusiness/wtservice/nc/announcement/getAnnouncementDetail.do",
              {"type": it["type"], "offerCode": it["offerCode"],
               "provinceCode": PROV, "cityCode": CITY})
    data = d.get("data") or {}
    it["url"] = data.get("link") or it.get("link") or ""
    it["content"] = (data.get("content") or "").strip()
    return it


def main():
    out = fetch_all()
    for it in out:
        try:
            fetch_detail(it)
        except Exception:
            pass
        time.sleep(0.4)
    res = {"updated": datetime.datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S") + " UTC",
           "province": "湖南", "source": "https://www.189.cn/web/notice", "items": out}
    dst = sys.argv[1] if len(sys.argv) > 1 else None
    if dst:
        os.makedirs(os.path.dirname(dst), exist_ok=True)
        with open(dst, "w", encoding="utf-8") as f:
            json.dump(res, f, ensure_ascii=False, indent=1)
    return res


if __name__ == "__main__":
    try:
        r = main()
        print("OK count=%d" % len(r["items"]))
        for it in r["items"][:15]:
            print(" -", it["date"], it["title"][:40], "|", (it.get("url") or "")[:60])
    except Exception:
        print("FAIL")
        print(traceback.format_exc()[:3000])
        sys.exit(1)
