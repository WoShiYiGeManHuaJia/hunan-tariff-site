#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""公告抓取脚本：湖南移动公告 + 湖南联通公告 + 湖南电信公告，各只保留最新 15 条，输出 announce.json

用法:
    python3 scripts/announce_fetch.py --move-dir site/data --uni-dir unicom/data --tc-dir telecom/data
说明:
    - 移动(湖南)公告列表/详情均为静态 JSON，GET 直取；
      详情接口触发 TLS legacy renegotiation，需注入 openssl_legacy.cnf(见下)。
    - 联通公告列表/详情为 POST 接口，需带 XHR 特征头(否则中文被替换成 ?)。
    - 电信(湖南)公告走 189.cn 推荐位接口，请求体 AES-CBC + RSA 加密；
      省份由 provinceCode=600203(湖南) 在源站侧限定，只出湖南，不含其他省。
      详情接口受瑞数 WAF 保护未开放，故只有标题+日期+官网链接。
      抓到 0 条时【绝不落盘】，避免源站抖动把线上公告清成空。
    - 输出文件:
        <move-dir>/announce.json  移动站公告数据
        <uni-dir>/announce.json   联通站公告数据
        <tc-dir>/announce.json    电信站公告数据
"""
import os
import re
import json
import sys
import time
import datetime

# 源站(移动网关) TLS legacy renegotiation 兼容(与 main.py 同款处理)
_SSL_CNF = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "mobile", "openssl_legacy.cnf")
if os.path.exists(_SSL_CNF):
    os.environ.setdefault("OPENSSL_CONF", _SSL_CNF)

import urllib.request
import urllib.parse

UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36")
MAX_KEEP = 15

# ---------------- 移动(湖南) ----------------
MOVE_LIST_URL = ("https://www.10086.cn/aboutus/news/pannounce/hn/731/5004505_873_2361.json")
MOVE_DETAIL_PREFIX = ("https://www.10086.cn/aboutus/news/pannounce/hn/731/5004505_873_2361_detail_")
MOVE_DETAIL_PAGE = ("https://www.10086.cn/aboutus/news/pannounce/hn/index_731_731_detail_{id}.html")
MOVE_SITE = "https://www.10086.cn"

# ---------------- 联通 ----------------
UNI_LIST_URL = "https://www.10010.com/mall/service/query/announcementquery"
UNI_DETAIL_URL = "https://www.10010.com/mall/service/query/announcementquerydetail"
UNI_PROVINCE = "074"  # 湖南（实测：011北京 013天津 017山东 018河北 030安徽 031上海
                      #   034江苏 036浙江 038福建 050海南 051广东 059广西 071湖北
                      #   074湖南 075江西 076河南 079西藏；原值 031 = 上海，抓错省了）
UNI_DETAIL_PAGE = ("https://www.10010.com/wt_links/index.html#/announcementDetail?announcementId={id}"
                   "&pageSize=12&pageNo=1")
UNI_IMG_HOST = "https://m1.img.10010.com"

UNI_HDRS = {
    "User-Agent": UA,
    "Content-Type": "application/x-www-form-urlencoded; charset=UTF-8",
    "Referer": "https://www.10010.com/wt_links/index.html",
    "Origin": "https://www.10010.com",
    "X-Requested-With": "XMLHttpRequest",
    "Accept": "application/json, text/javascript, */*; q=0.01",
    "Accept-Language": "zh-CN,zh;q=0.9",
}

# ---------------- 电信(湖南 600203) ----------------
# 公告走 189.cn 网厅「帮助中心/公告」推荐位接口：
#   POST /wtBusiness/wtservice/nc/recPos/getRecPosInfo.do
#   请求体 AES-CBC 加密 + RSA(内置公钥) 加密 key/iv，响应为明文 JSON。
# 列表已含标题与时间；详情接口为瑞数 WAF 保护且未开放，故只出标题+日期+官网链接。
TC_REC_URL = "https://www.189.cn/wtBusiness/wtservice/nc/recPos/getRecPosInfo.do"
TC_PROVINCE = "600203"          # 湖南（与资费接口同一套 provCode；只抓湖南，不含其他省）
TC_SHOP_ID = "20001"
TC_TYPE = "wt_sy_bzzx"          # 首页-帮助中心/公告位
TC_ORDER = 1                    # order=1 → 「公告」；order=2 → 「购物指南」（不要）
TC_FCODE = "Y121043001"
TC_NOTICE_PAGE = "https://www.189.cn/web/notice"
TC_PUBKEY_B64 = (
    "MIIBIjANBgkqhkiG9w0BAQEFAAOCAQ8AMIIBCgKCAQEAmUa6oMSBZrhfOjXCaYYIE9Lvj+r8nBIv"
    "CpydQmeG5CbeK5Qlwor+kFCrrPtcoYSowuUCB7YYsLYF6HVvf3Utw9FdLq7T8uNnfz2wxvp3N3Mi"
    "f5Rbhs7skrMvfy83zl7g9a1Xgz4OxmYbrm70E08F4Hu5K+86x9Qo+k8hSnJ4mkfb/fFL1/Im1n+i"
    "p2dBJ+vZt6mq8GykuAxQm4pb1UZw37HtdSR3WnU9Li0gDvXdJ87DAP0r7xF2DfTAQiAKP+3mdwlb"
    "KZ8hM0W7Do/7w+fBaOi+GCFJKvNDNVuH7G1OaEUuQH1xr3hoYAgqMdKOZWlZH+wbNqyAOxPL9V5K"
    "LF/30wIDAQAB"
)
# 省份由 provinceCode(600203=湖南) 在源站侧就限定死了，本地不再按标题二次过滤：
# 湖南电信官网把少量全国性/集团公告也挂在该省公告位下（如「规范互联网渠道售卡管理」），
# 这些同样是湖南站发布的内容，按标题过滤反而会漏掉张家界/株洲等只带市名的湖南公告。
TC_MUST = ()
TC_CITY_HINT = ("长沙", "株洲", "湘潭", "衡阳", "岳阳", "常德", "郴州", "益阳", "娄底",
                "邵阳", "湘西", "张家界", "怀化", "永州")

# 富文本中需要保留的基础标签
KEEP_TAGS = {"p", "br", "div", "span", "a", "img", "strong", "b", "em", "i", "u",
             "ul", "ol", "li", "table", "tr", "td", "th", "tbody", "thead", "h1",
             "h2", "h3", "h4", "blockquote"}


def _http_get(url, headers=None, timeout=30):
    req = urllib.request.Request(url, headers=headers or {"User-Agent": UA})
    return urllib.request.urlopen(req, timeout=timeout).read().decode("utf-8", "ignore")


def _http_post(url, form, headers=None, timeout=30):
    data = urllib.parse.urlencode(form).encode("utf-8")
    req = urllib.request.Request(url, data=data, method="POST",
                                 headers=headers or {"User-Agent": UA})
    return urllib.request.urlopen(req, timeout=timeout).read().decode("utf-8", "ignore")


def strip_style(html):
    """去掉富文本中的 mso-*/font-* 等内联样式，保留 color / background / 基础的排版值"""
    def _fix(m):
        attrs = m.group(1)
        keep = []
        for kv in re.findall(r'([\w-]+)\s*:\s*([^;]+);?', attrs):
            k, v = kv[0].strip().lower(), kv[1].strip()
            if not k or not v:
                continue
            lower = (k + ":" + v.lower())
            if k in ("color", "vertical-align", "text-align", "background-color"):
                keep.append(f"{k}:{v}")
            elif v.startswith("#") and k.startswith("backg"):
                keep.append(f"{k}:{v}")
            elif k.startswith("background") and len(v) > 4:
                keep.append(f"{k}:{v}")
        return ' style="' + ";".join(keep) + '"' if keep else ""
    return re.sub(r'\sstyle="([^"]*)"', _fix, html)


def _safe_proto(url):
    """协议白名单：只放行 http/https/mailto 与相对链接，其余(javascript:/data: 等)置空。

    防止抓来的公告正文里夹带 javascript: 或 data:text/html 造成 XSS。
    """
    if not url:
        return ""
    u = str(url).strip()
    # 相对链接 / 锚点 / 站内路径：直接放行
    if u.startswith(("/", "#", "./", "../")):
        return u
    low = u.lower()
    for ok in ("http://", "https://", "mailto:"):
        if low.startswith(ok):
            return u
    return ""


def clean_html(raw):
    """清洗 CMS/Word 富文本为简洁 HTML（保留表格/链接/图片），并补全站内相对链接"""
    if not raw:
        return ""
    h = raw
    h = re.sub(r"<\?xml.*?\?>", "", h, flags=re.S)
    h = re.sub(r"<style.*?</style>", "", h, flags=re.S | re.I)
    h = re.sub(r"<script.*?</script>", "", h, flags=re.S | re.I)
    h = re.sub(r"<!--.*?-->", "", h, flags=re.S)
    # 只保留基础标签，其余(如 span 大量嵌套)一并剥掉标签保留文本
    h = re.sub(r"<(?!/?(p|br|div|a|img|strong|b|em|i|u|ul|ol|li|table|tr|td|th|tbody|thead|h\d|blockquote)(\s|/|>))[^>]*>", "", h, flags=re.I)
    h = strip_style(h)
    # 清理空属性与僵尸 span
    h = re.sub(r'\s+(class|id|lang|dir|colspan|rowspan|border|width|height|align|cellpadding|cellspacing)="[^"]*"', "", h, flags=re.I)
    h = re.sub(r"\s+class=['\"][^'\"]*['\"]", "", h, flags=re.I)
    # 补全图片相对路径
    h = re.sub(r'(<img[^>]*?src=)["\'](?!https?://|data:)([^"\']*)["\']',
               lambda m: m.group(1) + '"' + _abs_link(m.group(2), "move") + '"', h, flags=re.I)
    h = re.sub(r'(<a[^>]*?href=)["\'](?!https?://|#|mailto:)([^"\']*)["\']',
               lambda m: m.group(1) + '"' + _abs_link(m.group(2), "move") + '"', h, flags=re.I)
    # 逐段切分，保留换行
    h = h.replace("</p>", "</p>\n").replace("<br>", "<br>\n").replace("<br/>", "<br>\n").replace("<br />", "<br>\n")
    h = re.sub(r"\n{3,}", "\n\n", h)
    # 链接/图片协议白名单兜底：仅保留 http/https/mailto 与相对链接，其余(如 javascript:/data:text)置空
    h = re.sub(r'(<a[^>]*?href=)["\']([^"\']*)["\']',
               lambda m: m.group(1) + '"' + _safe_proto(m.group(2)) + '"', h, flags=re.I)
    h = re.sub(r'(<img[^>]*?src=)["\']([^"\']*)["\']',
               lambda m: m.group(1) + '"' + _safe_proto(m.group(2)) + '"', h, flags=re.I)
    return h.strip()


_img_dom = {"move": "https://www.10086.cn", "uni": UNI_IMG_HOST}
def _abs_link(path, kind):
    if path.startswith(("http://", "https://", "data:")):
        return path
    if path.startswith("/"):
        if kind == "move":
            return MOVE_SITE + path
        return UNI_IMG_HOST + path
    return path


def html_to_text(h):
    """提取富文本纯文本(用于摘要)"""
    t = re.sub(r"<br\s*/?>", "\n", h, flags=re.I)
    t = re.sub(r"</(p|div|tr|li|h\d)>", "\n", t, flags=re.I)
    t = re.sub(r"<[^>]+>", "", t)
    t = htmlmod_unescape(t)
    return re.sub(r"\s+", " ", t).strip()


def htmlmod_unescape(s):
    import html as _h
    return _h.unescape(s)


def find_attachments(content_html, site):
    """从正文中提取附件(下载链接)"""
    out = []
    for m in re.finditer(r'<a[^>]*href="([^"]+)"[^>]*>(.*?)</a>', content_html, flags=re.S | re.I):
        href, name_raw = m.group(1), m.group(2)
        if "/uploadBaseDir/" in href or re.search(r'\.(xlsx?|pdf|docx?|zip|rar|png|jpg|jpeg)(\?|$)', href, flags=re.I):
            name = html_to_text(name_raw).strip() or os.path.basename(href.split("?")[0]) or "附件"
            link = href if href.startswith("http") else (site + href)
            if link not in [a["url"] for a in out]:
                out.append({"name": name[:60], "url": link})
    return out


def now_str():
    return datetime.datetime.now(datetime.timezone(datetime.timedelta(hours=8))).strftime("%Y-%m-%d %H:%M")


# ---------------- 移动抓取 ----------------
def fetch_move():
    print("[移动] 拉取公告列表 ...")
    raw = _http_get(MOVE_LIST_URL)
    j = json.loads(raw)
    lst = j["cData"]["list"] or []
    items = []
    for row in lst:
        href = row.get("detail_href") or ""
        mid = None
        m = re.search(r"_detail_(\d+)\.", href)
        if m:
            mid = m.group(1)
        if mid is None:
            continue
        items.append({
            "id": mid,
            "title": row.get("noticeTitle") or "",
            "date": row.get("publishTime") or "",
            "page_url": MOVE_DETAIL_PAGE.format(id=mid),
        })
    items.sort(key=lambda x: x["date"], reverse=True)
    items = items[:MAX_KEEP]
    print(f"[移动] 列表 {len(lst)} 条，取最新 {len(items)} 条")
    for it in items:
        try:
            dj = json.loads(_http_get(MOVE_DETAIL_PREFIX + it["id"] + ".json"))
            c = dj.get("cData", {}).get("content", {})
            text = c.get("text") or ""
            content = clean_html(text)
            it["summary"] = html_to_text(content)[:120]
            it["content"] = content
            it["attachments"] = find_attachments(content, MOVE_SITE)
        except Exception as e:
            print(f"[移动] 详情 {it['id']} 失败: {e}")
            it["summary"], it["content"], it["attachments"] = "", "", []
        # 避免请求过快
        time.sleep(0.4)
    return items


# ---------------- 联通抓取 ----------------
def fetch_uni():
    print("[联通] 拉取公告列表 ...")
    # 源站返回顺序 ≠ 时间顺序，且 pageSize 过小时「取最新 N 条」会漏掉真正最新的公告。
    # 改为一次多拉(100条)、按发布日期降序后再截断，确保拿到的是时间上最新的 MAX_KEEP 条。
    raw = _http_post(UNI_LIST_URL, {"pageNo": "1", "pageSize": "100",
                                    "province": UNI_PROVINCE, "condition": "0", "title": ""}, UNI_HDRS)
    j = json.loads(raw)
    lst = j.get("result") or []
    items = []
    for row in lst:
        items.append({
            "id": row.get("id") or "",
            "title": row.get("title") or "",
            "date": (row.get("publishTime") or "")[:10],
            "page_url": UNI_DETAIL_PAGE.format(id=row.get("id") or ""),
        })
    items = [x for x in items if x["id"]]
    items.sort(key=lambda x: x["date"], reverse=True)
    items = items[:MAX_KEEP]
    print(f"[联通] 列表 {len(lst)} 条，按日期降序取最新 {len(items)} 条")
    for it in items:
        try:
            dj = json.loads(_http_post(UNI_DETAIL_URL, {
                "announcementId": it["id"], "pageSize": "12", "pageNo": "1",
                "province": UNI_PROVINCE}, UNI_HDRS))
            n = dj.get("tNoticeDto") or {}
            text = n.get("noticeDetails") or ""
            content = clean_html(text)
            content = re.sub(r'(<img[^>]*?src=)["\'](?!https?://)([^"\']*)["\']',
                             lambda m: m.group(1) + '"' + UNI_IMG_HOST + m.group(2) + '"', content, flags=re.I)
            it["title"] = n.get("title") or it["title"]
            it["date"] = (n.get("noticeTime") or it["date"])[:10]
            it["summary"] = html_to_text(content)[:120]
            it["content"] = content
            it["attachments"] = find_attachments(content, UNI_IMG_HOST)
        except Exception as e:
            print(f"[联通] 详情 {it['id']} 失败: {e}")
            it["summary"], it["content"], it["attachments"] = "", "", []
        time.sleep(0.4)
    return items


# ---------------- 电信抓取（湖南 600203） ----------------
def _tc_post(obj):
    """电信网厅接口：AES-CBC 加密 body + RSA 加密 key/iv，响应明文 JSON"""
    from Crypto.Cipher import AES, PKCS1_v1_5
    from Crypto.PublicKey import RSA
    from Crypto.Util.Padding import pad
    import base64, gzip, random

    pub = RSA.import_key(base64.b64decode(TC_PUBKEY_B64))
    key = os.urandom(16)
    iv = os.urandom(16)
    ct = AES.new(key, AES.MODE_CBC, iv).encrypt(pad(json.dumps(obj, ensure_ascii=False).encode(), 16))
    inner = json.dumps({"key": base64.b64encode(key).decode(),
                        "iv": base64.b64encode(iv).decode()}, separators=(",", ":"))
    payload = {"param": base64.b64encode(ct).decode(),
               "key": base64.b64encode(PKCS1_v1_5.new(pub).encrypt(inner.encode())).decode()}
    tid = "".join("%x" % random.randint(0, 15) for _ in range(32))
    req = urllib.request.Request(
        TC_REC_URL, data=json.dumps(payload, separators=(",", ":")).encode(), method="POST",
        headers={"User-Agent": UA, "Content-Type": "application/json;charset=UTF-8",
                 "Accept": "application/json, text/plain, */*", "Origin": "https://www.189.cn",
                 "Referer": "https://www.189.cn/web/notice/index.html",
                 "Fcode": TC_FCODE, "TransactionId": tid, "Accept-Language": "zh-CN,zh;q=0.9"})
    last = None
    for a in range(4):
        try:
            with urllib.request.urlopen(req, timeout=30) as r:
                raw = r.read()
                if r.headers.get("Content-Encoding") == "gzip":
                    raw = gzip.decompress(raw)
                return json.loads(raw.decode("utf-8", "replace"))
        except Exception as e:
            last = e
            time.sleep(2 * (a + 1))
    raise last


def _tc_date(s):
    """20260918145157 / 2026-09-18 12:00 → 2026-09-18"""
    t = str(s or "").strip()
    if len(t) >= 8 and t[:8].isdigit():
        return "%s-%s-%s" % (t[:4], t[4:6], t[6:8])
    return t[:10]


def fetch_telecom():
    print("[电信] 拉取湖南公告列表 (provinceCode=%s) ..." % TC_PROVINCE)
    r = _tc_post({"shopId": TC_SHOP_ID, "type": TC_TYPE, "order": TC_ORDER,
                  "provinceCode": TC_PROVINCE, "cityCode": ""})
    if r.get("code") not in (None, "S_COMMON_0000", "0"):
        print("[电信] 接口返回异常: code=%s msg=%s" % (r.get("code"), r.get("message")))
    data = r.get("data") or []
    raw = []
    for d in data:
        for x in (d.get("floorItems") or []):
            raw.append(x)
    print("[电信] 列表 %d 条" % len(raw))
    if not raw:
        print("[电信] !! 未取到公告，保持线上数据不变")
        return None
    items = []
    for x in raw:
        title = (x.get("title") or "").strip()
        if not title:
            continue
        dt = _tc_date(x.get("liveStartTime") or x.get("publishTime") or x.get("createTime") or "")
        eid = x.get("externalOfferCode") or x.get("offerCode") or x.get("id") or ""
        items.append({
            "id": str(eid),
            "title": title,
            "date": dt,
            # 详情接口受瑞数 WAF 保护、未开放，统一跳官网公告页
            "page_url": TC_NOTICE_PAGE,
            "summary": "",
            "content": "",
            "attachments": [],
        })
    # 源站返回并非时间序，先按日期降序再截断，确保是「最新 15 条」
    items.sort(key=lambda x: (x["date"], x["id"]), reverse=True)
    items = items[:MAX_KEEP]
    print("[电信] 按日期降序取最新 %d 条" % len(items))
    for it in items[:3]:
        print("   * %s | %s" % (it["date"], it["title"][:40]))
    return items


def write_json(items, path):
    data = {"updated": now_str(), "count": len(items), "items": items}
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=1)
    print(f"已写入 {path} ({len(items)} 条)")


def _resolve(root, p):
    return p if os.path.isabs(p) else os.path.join(root, p)


def main():
    # __file__ = <repo>/pipelines/scripts/announce_fetch.py，需上三级才是仓库根。
    # 旧代码只上两级 -> root=<repo>/pipelines，导致相对目录 unicom/data 被写到
    # <repo>/pipelines/unicom/data/announce.json，该路径从不参与同步，线上公告永远不更新。
    root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    args = sys.argv[1:]
    move_dir = uni_dir = tc_dir = None
    for i, a in enumerate(args):
        if a == "--move-dir" and i + 1 < len(args):
            move_dir = _resolve(root, args[i + 1])
        if a == "--uni-dir" and i + 1 < len(args):
            uni_dir = _resolve(root, args[i + 1])
        if a == "--tc-dir" and i + 1 < len(args):
            tc_dir = _resolve(root, args[i + 1])
    if move_dir:
        write_json(fetch_move(), os.path.join(move_dir, "announce.json"))
    if uni_dir:
        write_json(fetch_uni(), os.path.join(uni_dir, "announce.json"))
    if tc_dir:
        its = fetch_telecom()
        if its is None:
            # 抓空绝不落盘：避免源站抖动/WAF 拦截把线上公告清成 0 条
            print("[电信] 跳过写入（未取到数据，保持线上公告不变）")
        else:
            write_json(its, os.path.join(tc_dir, "announce.json"))
    if not move_dir and not uni_dir and not tc_dir:
        print(__doc__)


if __name__ == "__main__":
    main()
