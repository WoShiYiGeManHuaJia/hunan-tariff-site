#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""公告抓取脚本：湖南移动公告 + 联通公告，各只保留最新 15 条，输出 announce.json

用法:
    python3 scripts/announce_fetch.py --move-dir site/data --uni-dir unicom/data
说明:
    - 移动(湖南)公告列表/详情均为静态 JSON，GET 直取；
      详情接口触发 TLS legacy renegotiation，需注入 openssl_legacy.cnf(见下)。
    - 联通公告列表/详情为 POST 接口，需带 XHR 特征头(否则中文被替换成 ?)。
    - 输出文件:
        <move-dir>/announce.json  移动站公告数据
        <uni-dir>/announce.json   联通站公告数据
"""
import os
import re
import json
import sys
import time
import datetime

# 源站(移动网关) TLS legacy renegotiation 兼容(与 main.py 同款处理)
_SSL_CNF = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "openssl_legacy.cnf")
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
UNI_PROVINCE = "031"  # 与 https://www.10010.com/wt_links/index.html#/announcementPage 一致
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
    raw = _http_post(UNI_LIST_URL, {"pageNo": "1", "pageSize": str(MAX_KEEP + 5),
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
    items = [x for x in items if x["id"]][:MAX_KEEP]
    print(f"[联通] 列表 {len(lst)} 条，取最新 {len(items)} 条")
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


def write_json(items, path):
    data = {"updated": now_str(), "count": len(items), "items": items}
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=1)
    print(f"已写入 {path} ({len(items)} 条)")


def _resolve(root, p):
    return p if os.path.isabs(p) else os.path.join(root, p)


def main():
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    args = sys.argv[1:]
    move_dir = uni_dir = None
    for i, a in enumerate(args):
        if a == "--move-dir" and i + 1 < len(args):
            move_dir = _resolve(root, args[i + 1])
        if a == "--uni-dir" and i + 1 < len(args):
            uni_dir = _resolve(root, args[i + 1])
    if move_dir:
        write_json(fetch_move(), os.path.join(move_dir, "announce.json"))
    if uni_dir:
        write_json(fetch_uni(), os.path.join(uni_dir, "announce.json"))
    if not move_dir and not uni_dir:
        print(__doc__)


if __name__ == "__main__":
    main()
