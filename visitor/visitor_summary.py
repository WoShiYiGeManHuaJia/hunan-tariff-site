# -*- coding: utf-8 -*-
"""
运营商资费变化 · 访客自助推送脚本（自包含，只依赖 Python 标准库）

用法：
    python3 visitor_summary.py            # 正常推送
    python3 visitor_summary.py --test     # 只发一条测试消息，验证配置是否配对

需要的环境变量（在你的仓库 Settings → Secrets 里填，或本地 .env）：
    至少填一个推送渠道：
      DINGTALK_WEBHOOK / DINGTALK_SECRET(加签，可选) / DINGTALK_KEYWORD(可选)
      FEISHU_WEBHOOK   / FEISHU_SECRET(可选)
      WECOM_WEBHOOK
      SMTP_HOST / SMTP_PORT / SMTP_USER / SMTP_PASS / MAIL_TO
    可选过滤（不填 = 全部）：
      PUSH_OPS    只推哪些运营商：mobile,unicom,telecom,gb
      PUSH_PROVS  只统计哪些省份（拼音）：quanguo,hunan,guangdong
      SINCE_HOURS 统计最近多少小时，默认 24
      DATA_SOURCE 数据源，auto(默认) / raw / jsdelivr

数据来源是本脚本所在仓库之外的公开数据仓，只读不写，
不会影响原站任何配置。
"""
import os, sys, json, hmac, hashlib, base64, smtplib, urllib.request, urllib.parse
from datetime import datetime, timedelta, timezone

CST = timezone(timedelta(hours=8))
TEST_MODE = "--test" in sys.argv
SINCE_HOURS = float(os.getenv("SINCE_HOURS") or "24")

DATA_REPO = os.getenv(
    "DATA_REPO",
    "WoShiYiGeManHuaJia/hunan-tariff-site")   # 公开数据源仓库
DATA_BRANCH = os.getenv("DATA_BRANCH", "main")
DATA_SOURCE = (os.getenv("DATA_SOURCE", "auto").strip().lower() or "auto")

SITES = [
    ("data/history.json",          "移动", "🔵", "mobile"),
    ("unicom/data/history.json",   "联通", "🟠", "unicom"),
    ("telecom/data/history.json",  "电信", "🟢", "telecom"),
    ("gb/data/history.json",       "广电", "🟣", "gb"),
]

SEC_CN = {
    "quanguo": "全网(全国)", "beijing": "北京", "tianjin": "天津", "hebei": "河北",
    "shanxi": "山西", "neimenggu": "内蒙古", "liaoning": "辽宁", "jilin": "吉林",
    "heilongjiang": "黑龙江", "shanghai": "上海", "jiangsu": "江苏", "zhejiang": "浙江",
    "anhui": "安徽", "fujian": "福建", "jiangxi": "江西", "shandong": "山东",
    "henan": "河南", "hubei": "湖北", "hunan": "湖南", "guangdong": "广东",
    "guangxi": "广西", "hainan": "海南", "chongqing": "重庆", "sichuan": "四川",
    "guizhou": "贵州", "yunnan": "云南", "xizang": "西藏", "shaanxi": "陕西",
    "gansu": "甘肃", "qinghai": "青海", "ningxia": "宁夏", "xinjiang": "新疆",
}
def sec_cn(k): return SEC_CN.get(str(k).strip().lower(), k)
def env_list(k): return [x.strip().lower() for x in os.getenv(k, "").split(",") if x.strip()]
PUSH_OPS, PUSH_PROVS = env_list("PUSH_OPS"), env_list("PUSH_PROVS")

def urls_for(path):
    raw = "https://raw.githubusercontent.com/%s/%s/%s" % (DATA_REPO, DATA_BRANCH, path)
    cdn = "https://cdn.jsdelivr.net/gh/%s@%s/%s" % (DATA_REPO, DATA_BRANCH, path)
    if DATA_SOURCE == "raw":      return [raw, cdn]
    if DATA_SOURCE == "jsdelivr": return [cdn, raw]
    return [raw, cdn]           # auto：GitHub Actions 内 raw 最快，境外/本地退回 CDN

def fetch_json(path):
    last = None
    for u in urls_for(path):
        for attempt in (1, 2):
            try:
                req = urllib.request.Request(u, headers={"User-Agent": "visitor-notify"})
                with urllib.request.urlopen(req, timeout=45) as r:
                    return json.loads(r.read().decode("utf-8", "ignore"))
            except Exception as e:
                last = e
    print("  ⚠ 拉取失败（已试全部数据源）：%s -> %s" % (path, str(last)[:90]))
    return None

def parse_ts(ts):
    if not ts: return None
    for f in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%dT%H:%M:%S", "%Y-%m-%d %H:%M"):
        try: return datetime.strptime(str(ts).strip(), f).replace(tzinfo=CST)
        except ValueError: continue
    return None

def summarize(hist, since):
    """只取窗口内最新一条，与网站「变化历史」同源同口径。"""
    if not isinstance(hist, list): return 0, 0, 0, []
    latest, latest_dt = None, None
    for e in hist:
        dt = parse_ts(e.get("ts"))
        if dt and dt >= since and (latest_dt is None or dt > latest_dt):
            latest, latest_dt = e, dt
    if latest is None: return 0, 0, 0, []
    a = r = m = 0; secs = []
    for k, v in latest.items():
        if k == "ts" or not isinstance(v, dict): continue
        if PUSH_PROVS and str(k).strip().lower() not in PUSH_PROVS: continue
        aa = int(v.get("added", 0) or 0); rr = int(v.get("removed", 0) or 0)
        mm = int(v.get("modified", 0) or 0)
        if not (aa or rr or mm): continue
        a += aa; r += rr; m += mm
        secs.append((sec_cn(k), aa, rr, mm))
    return a, r, m, secs

# ───────────────── 推送通道 ─────────────────
def post(url, body, headers=None):
    data = json.dumps(body, ensure_ascii=False).encode("utf-8")
    req = urllib.request.Request(url, data=data, method="POST",
        headers=dict({"Content-Type": "application/json"}, **(headers or {})))
    with urllib.request.urlopen(req, timeout=30) as r:
        return r.status, r.read().decode("utf-8", "ignore")

def send_dingtalk(title, text):
    wh = (os.getenv("DINGTALK_WEBHOOK") or "").strip()
    if not wh: return None
    url = wh
    sec = (os.getenv("DINGTALK_SECRET") or "").strip()
    if sec:
        ts = str(int(datetime.now().timestamp() * 1000))
        sign = base64.b64encode(hmac.new(sec.encode(), ("%s\n%s" % (ts, sec)).encode(),
                                         hashlib.sha256).digest()).decode()
        url += "&timestamp=%s&sign=%s" % (ts, urllib.parse.quote(sign))
    kw = (os.getenv("DINGTALK_KEYWORD") or "").strip()
    _, body = post(url, {"msgtype": "markdown", "markdown": {"title": kw + title, "text": kw + text}})
    return "ok" in body or "success" in body

def send_feishu(title, text):
    wh = (os.getenv("FEISHU_WEBHOOK") or "").strip()
    if not wh: return None
    headers = {}
    sec = (os.getenv("FEISHU_SECRET") or "").strip()
    if sec:
        ts = str(int(datetime.now().timestamp()))
        headers["X-Lark-Request-Timestamp"] = ts
        headers["X-Lark-Signature"] = base64.b64encode(
            hmac.new(("%s\n%s" % (ts, sec)).encode(), b"", hashlib.sha256).digest()).decode()
    _, body = post(wh, {"msg_type": "text", "content": {"text": title + "\n\n" + text}}, headers)
    return '"StatusCode":0' in body or '"code":0' in body or "success" in body

def send_wecom(title, text):
    wh = (os.getenv("WECOM_WEBHOOK") or "").strip()
    if not wh: return None
    _, body = post(wh, {"msgtype": "text", "text": {"content": title + "\n\n" + text}})
    return '"errcode":0' in body

def send_email(title, text):
    host = (os.getenv("SMTP_HOST") or "").strip()
    to = (os.getenv("MAIL_TO") or "").strip()
    if not (host and to): return None
    port = int(os.getenv("SMTP_PORT") or "465")
    user = (os.getenv("SMTP_USER") or "").strip()
    pwd = os.getenv("SMTP_PASS") or ""
    import email.mime.text as MT, email.header as EH
    msg = MT.MIMEText(text, "plain", "utf-8")
    msg["Subject"] = EH.Header(title, "utf-8")
    msg["From"] = user or to; msg["To"] = to
    try:
        if port == 465:
            s = smtplib.SMTP_SSL(host, port, timeout=30)
        else:
            s = smtplib.SMTP(host, port, timeout=30); s.starttls()
        if user: s.login(user, pwd)
        s.sendmail(msg["From"], [to], msg.as_string()); s.quit()
        return True
    except Exception as e:
        print("  邮件发送失败：%s" % str(e)[:120]); return False

def send_all(title, text):
    res = []
    for nm, fn in (("钉钉", send_dingtalk), ("飞书", send_feishu),
                   ("企业微信", send_wecom), ("邮箱", send_email)):
        try:
            r = fn(title, text)
            if r is None: continue
            res.append((nm, bool(r)))
            print("  %s %s：%s" % ("✓" if r else "✗", nm, "已发出" if r else "失败"))
        except Exception as e:
            res.append((nm, False)); print("  ✗ %s：%s" % (nm, str(e)[:110]))
    return res

# ───────────────── 主流程 ─────────────────
def main():
    if TEST_MODE:
        ok = send_all("✅ 推送通道配置成功",
            "你的「运营商资费变化」定时推送已接通。\n\n"
            "运营商：%s\n省份：%s\n\n下次有变化会自动推到这里。"
            % ("、".join(n for _, n, _, o in SITES if (not PUSH_OPS or o in PUSH_OPS)) or "全部",
               "、".join(sec_cn(x) for x in PUSH_PROVS) or "全部"))
        if not ok:
            print("❌ 一个通道都没发送成功，请检查 Secrets 里的 Webhook 是否填对。")
        return

    now = datetime.now(CST)
    since = now - timedelta(hours=SINCE_HOURS)
    print("统计窗口: %s 之后 (北京时间)" % since.strftime("%Y-%m-%d %H:%M"))

    lines = ["**统计范围**：%s ~ %s" % (since.strftime("%m-%d %H:%M"), now.strftime("%m-%d %H:%M")), ""]
    if PUSH_OPS:
        lines += ["**运营商**：" + "、".join(n for _, n, _, o in SITES if o in PUSH_OPS), ""]
    if PUSH_PROVS:
        lines += ["**省份**：" + "、".join(sec_cn(x) for x in PUSH_PROVS), ""]

    any_change = False; grand = [0, 0, 0]
    for path, name, icon, op in SITES:
        if PUSH_OPS and op not in PUSH_OPS: continue
        hist = fetch_json(path)
        if hist is None:
            lines.append("- %s **%s**：数据拉取失败（已跳过）" % (icon, name)); continue
        a, r, m, secs = summarize(hist, since)
        grand[0] += a; grand[1] += r; grand[2] += m
        if not (a or r or m):
            lines.append("- %s **%s**：无变化" % (icon, name)); continue
        any_change = True
        lines.append("- %s **%s**：新增 %d、下架 %d、修改 %d" % (icon, name, a, r, m))
        if PUSH_PROVS:
            for sn, sa, sr, sm in sorted(secs, key=lambda x: -(x[1] + x[2] + x[3]))[:12]:
                lines.append("　└ %s：新增 %d、下架 %d、修改 %d" % (sn, sa, sr, sm))

    lines += ["", "**合计**：新增 %d、下架 %d、修改 %d" % tuple(grand)]
    if not any_change:
        lines += ["", "> 本时段内无资费变化。"]
    text = "\n".join(lines)
    print(text)

    if not any_change and os.getenv("GITHUB_EVENT_NAME", "").strip() == "schedule" \
       and not os.getenv("FORCE_PUSH"):
        print("\n⏭ 无变化（定时触发）→ 跳过推送，不重复发旧内容。")
        return
    send_all("资费汇总 新增%d 下架%d 修改%d" % tuple(grand), text)

if __name__ == "__main__":
    main()
