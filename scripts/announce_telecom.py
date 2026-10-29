#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""中国电信公告抓取（湖南）

关键点（踩坑记录 2026-09-26）：
  * 详情接口此前一直 412，原因是请求头/节奏不对。可用配方（tcann7 实测 15/15 成功）：
      - Referer 必须是 https://www.189.cn/web/notice/index.html（少了 index.html 会被 WAF 挡）
      - 必须带 CookieJar（带会话）
      - 每条之间 sleep 1.3s，失败退避 2/4/6s
      - type 用 floorItems 自带的 type（有 wt_sy_bzzx / wt_sy_jtgg 两种）
  加密: AES-CBC(随机 key/iv) 加密 body, RSA-PKCS1v1_5(公钥) 加密 {key,iv} -> {param,key}
"""
import json, os, sys, time, re, base64, gzip, random, datetime, traceback
import urllib.request, http.cookiejar
from Crypto.Cipher import AES, PKCS1_v1_5
from Crypto.PublicKey import RSA
from Crypto.Util.Padding import pad

UA = ("Mozilla/5.0 (Linux; Android 13; SM-S9110) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/120.0 Mobile Safari/537.36")
BASE = "https://www.189.cn"
REC = BASE + "/wtBusiness/wtservice/nc/recPos/getRecPosInfo.do"
DET = BASE + "/wtBusiness/wtservice/nc/announcement/getAnnouncementDetail.do"
PUBKEY_B64 = ("MIIBIjANBgkqhkiG9w0BAQEFAAOCAQ8AMIIBCgKCAQEAmUa6oMSBZrhfOjXCaYYIE9Lvj+r8nBIv"
              "CpydQmeG5CbeK5Qlwor+kFCrrPtcoYSowuUCB7YYsLYF6HVvf3Utw9FdLq7T8uNnfz2wxvp3N3Mi"
              "f5Rbhs7skrMvfy83zl7g9a1Xgz4OxmYbrm70E08F4Hu5K+86x9Qo+k8hSnJ4mkfb/fFL1/Im1n+i"
              "p2dBJ+vZt6mq8GykuAxQm4pb1UZw37HtdSR3WnU9Li0gDvXdJ87DAP0r7xF2DfTAQiAKP+3mdwl"
              "bKZ8hM0W7Do/7w+fBaOi+GCFJKvNDNVuH7G1OaEUuQH1xr3hoYAgqMdKOZWlZH+wbNqyAOxPL9V5"
              "KLF/30wIDAQAB")
PROV = os.environ.get("TC_PROV", "600203")   # 湖南
CITY = os.environ.get("TC_CITY", "")
MAX_KEEP = int(os.environ.get("TC_KEEP", "15"))
TYPE = "wt_sy_bzzx"

_pub = None
_opener = None


def _rsa():
    global _pub
    if _pub is None:
        _pub = RSA.import_key(base64.b64decode(PUBKEY_B64))
    return PKCS1_v1_5.new(_pub)


def _op():
    global _opener
    if _opener is None:
        cj = http.cookiejar.CookieJar()
        _opener = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(cj))
    return _opener


def post(url, obj, tries=3):
    last = ""
    for a in range(tries):
        try:
            key = os.urandom(16)
            iv = os.urandom(16)
            ct = AES.new(key, AES.MODE_CBC, iv).encrypt(
                pad(json.dumps(obj, ensure_ascii=False).encode("utf-8"), 16))
            inner = json.dumps({"key": base64.b64encode(key).decode(),
                                "iv": base64.b64encode(iv).decode()},
                               separators=(",", ":"))
            payload = {"param": base64.b64encode(ct).decode(),
                       "key": base64.b64encode(_rsa().encrypt(inner.encode())).decode()}
            tid = "".join("%x" % random.randint(0, 15) for _ in range(32))
            req = urllib.request.Request(
                url, data=json.dumps(payload, separators=(",", ":")).encode(),
                method="POST", headers={
                    "User-Agent": UA,
                    "Content-Type": "application/json;charset=UTF-8",
                    "Accept": "application/json, text/plain, */*",
                    "Origin": "https://www.189.cn",
                    "Referer": "https://www.189.cn/web/notice/index.html",
                    "Fcode": "Y121043001",
                    "TransactionId": tid,
                })
            with _op().open(req, timeout=30) as r:
                raw = r.read()
                if r.headers.get("Content-Encoding") == "gzip":
                    raw = gzip.decompress(raw)
                return json.loads(raw.decode("utf-8", "replace"))
        except Exception as e:
            last = "ERR " + str(e)[:180]
            time.sleep(2 * (a + 1))
    return {"__err": last}


def fmt_date(s):
    t = str(s or "").strip()
    if len(t) >= 8 and t[:8].isdigit():
        return "%s-%s-%s" % (t[:4], t[4:6], t[6:8])
    return t[:10]


TAG = re.compile(r"<[^>]+>")
BAD = re.compile(r"(?is)<(script|style|iframe)[^>]*>.*?</\1>")
BRK = re.compile(r"(?i)<(br|/p|/div|/tr|/li)[^>]*>")


def to_text(h):
    h = BAD.sub("", h or "")
    h = BRK.sub("\n", h)
    t = TAG.sub("", h)
    t = (t.replace("&nbsp;", " ").replace("&amp;", "&")
          .replace("&lt;", "<").replace("&gt;", ">").replace("&quot;", '"'))
    t = re.sub(r"[ \t\u3000]+", " ", t)
    t = re.sub(r"\n{3,}", "\n\n", t)
    return t.strip()


def clean_html(h):
    h = BAD.sub("", h or "")
    h = re.sub(r'(?i)\s(?:on\w+|javascript:)\s*=\s*"[^"]*"', "", h)
    h = re.sub(r"(?i)\son\w+\s*=\s*'[^']*'", "", h)
    return h.strip()


def fetch_list():
    """先拿 order=1 的全量 floorItems（143 条，含所有 tab），按日期降序取最新 15 条。"""
    r = post(REC, {"shopId": "20001", "type": TYPE, "order": 1,
                   "provinceCode": PROV, "cityCode": CITY})
    if r.get("__err"):
        raise RuntimeError("list failed: " + r["__err"])
    if r.get("code") != "S_COMMON_0000":
        raise RuntimeError("list code=%s msg=%s" % (r.get("code"), r.get("message")))
    fis = []
    for d in (r.get("data") or []):
        for x in (d.get("floorItems") or []):
            fis.append(x)
    out, seen = [], set()
    for x in sorted(fis, key=lambda v: str(v.get("liveStartTime") or ""), reverse=True):
        t = (x.get("title") or "").strip()
        dt = fmt_date(x.get("liveStartTime"))
        if not t or (t, dt) in seen:
            continue
        seen.add((t, dt))
        lk = x.get("link") or ""
        if lk and lk.startswith("/"):
            lk = BASE + lk
        out.append({"title": t, "date": dt,
                    "offerCode": x.get("externalOfferCode") or "",
                    "type": x.get("type") or TYPE,
                    "link": lk,
                    "tab": x.get("tabTitle") or x.get("title") or ""})
        if len(out) >= MAX_KEEP:
            break
    return out


def fetch_detail(it):
    d = post(DET, {"type": it["type"], "offerCode": it["offerCode"],
                   "provinceCode": PROV, "cityCode": CITY})
    if d.get("code") != "S_COMMON_0000":
        return False
    data = d.get("data") or {}
    c = clean_html(data.get("content") or "")
    pu = data.get("link") or it.get("link") or ""
    if pu and pu.startswith("/"):
        pu = BASE + pu
    txt = to_text(c)
    it["page_url"] = pu
    it["content"] = c
    it["summary"] = txt[:100] if txt else ("（图片公告，点击查看）" if "<img" in c.lower() else "")
    return bool(c)


def load_old(dst):
    if not dst or not os.path.exists(dst):
        return {}
    try:
        j = json.load(open(dst, encoding="utf-8"))
        m = {}
        for it in j.get("items", []):
            if it.get("content"):
                m[it.get("offerCode") or it.get("title")] = it
        return m
    except Exception:
        return {}


def main():
    dst = sys.argv[1] if len(sys.argv) > 1 else None
    items = fetch_list()
    old = load_old(dst)
    ok = 0
    for i, it in enumerate(items):
        k = it["offerCode"] or it["title"]
        if fetch_detail(it):
            ok += 1
        elif k in old:                     # 抓失败就复用上次正文，绝不回退成空
            o = old[k]
            it["content"] = o.get("content", "")
            it["summary"] = o.get("summary", "")
            it["page_url"] = o.get("page_url", "")
        time.sleep(1.3)
    tz = datetime.timezone(datetime.timedelta(hours=8))
    res = {"updated": datetime.datetime.now(tz).strftime("%Y-%m-%d %H:%M:%S"),
           "count": len(items), "province": "湖南",
           "source": "https://www.189.cn/web/notice", "items": items}
    print("[电信公告] 列表 %d 条，正文成功 %d 条" % (len(items), ok))
    for it in items:
        print("  *", it["date"], "|", it["title"][:34],
              "| 正文", len(it.get("content") or ""), "字")
    if dst:
        os.makedirs(os.path.dirname(dst), exist_ok=True)
        with open(dst, "w", encoding="utf-8") as f:
            json.dump(res, f, ensure_ascii=False, indent=1)
        print("已写入", dst)
    return res


if __name__ == "__main__":
    try:
        main()
    except Exception:
        print("FAIL")
        print(traceback.format_exc()[:3000])
        sys.exit(1)
