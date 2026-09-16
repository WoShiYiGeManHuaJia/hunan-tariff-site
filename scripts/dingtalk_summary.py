# -*- coding: utf-8 -*-
"""四站资费变化汇总 → 钉钉推送。

用法：
  SINCE_HOURS=24 python3 scripts/dingtalk_summary.py
只统计最近 N 小时内的变化，避免推送历史旧账。
"""
import json
import os
import sys
import time
import hmac
import base64
import hashlib
import urllib.parse
import urllib.request
from datetime import datetime, timezone, timedelta

def _load_dotenv():
    """本地运行时自动读取仓库根目录的 .env（GitHub Actions 里无需此文件）。

    只在本文件所在目录及其上级查找 .env，且已存在的环境变量优先，
    不会被 .env 覆盖 —— 保证 Actions 的 Secrets 始终生效。
    """
    try:
        here = os.path.dirname(os.path.abspath(__file__))
    except NameError:          # 被 exec/内联执行时没有 __file__
        here = os.getcwd()
    for base in (here, os.path.dirname(here), os.path.dirname(os.path.dirname(here))):
        fp = os.path.join(base, ".env")
        if os.path.isfile(fp):
            try:
                with open(fp, encoding="utf-8") as f:
                    for line in f:
                        line = line.strip()
                        if not line or line.startswith("#") or "=" not in line:
                            continue
                        if line.startswith("export "):
                            line = line[7:]
                        k, _, v = line.partition("=")
                        k, v = k.strip(), v.strip().strip('"').strip("'")
                        if k and k not in os.environ:   # 环境变量优先
                            os.environ[k] = v
            except Exception:
                pass
            return


_load_dotenv()

WEBHOOK = os.getenv("DINGTALK_WEBHOOK", "").strip()
SECRET = os.getenv("DINGTALK_SECRET", "").strip()
SINCE_HOURS = float(os.getenv("SINCE_HOURS") or "24")
SITE_ROOT = os.getenv("SITE_ROOT") or "."
# 明细只列关注的省份（默认湖南），其余省份不展示
# 注意：os.getenv 的默认值只在「变量未设置」时生效；workflow 里通过
# ${{ vars.FOCUS_SEC }} 传入空串时，默认值不会生效，需显式回退。
FOCUS_SEC = (os.getenv("FOCUS_SEC", "").strip().lower() or "hunan")
# 支持多个关注省份（逗号分隔，如 hunan,guangdong,zhejiang）。
# 旧配置只填一个时行为不变；填多个则消息里逐个列出明细。
FOCUS_LIST = [x.strip() for x in FOCUS_SEC.split(",") if x.strip()] or ["hunan"]
# 结尾附带的资费站访问链接
# 同样注意：workflow 用 ${{ vars.SITE_URL }} 传入，未配置时是空串，
# os.getenv 默认值不生效，必须显式回退，否则结尾链接整体消失。
DEFAULT_SITE = "https://woshiyigemanhuajia.github.io/hunan-tariff-site/"
SITE_URL = (os.getenv("SITE_URL", "").strip().rstrip("/") or DEFAULT_SITE.rstrip("/"))
# 测试模式：只发一条「配置成功」消息，不读任何数据
TEST_MODE = "--test" in sys.argv

# 站名 -> (history 路径, 显示名, 图标)
SITES = [
    ("data/history.json", "移动", "🔵"),
    ("unicom/data/history.json", "联通", "🟠"),
    ("telecom/data/history.json", "电信", "🟢"),
    ("gb/data/history.json", "广电", "🟣"),
]

CST = timezone(timedelta(hours=8))

# 板块 key（拼音）-> 中文名。数据里存的是拼音，直接展示会看不懂。
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


def sec_cn(k):
    """板块 key 转中文名；未收录的原样返回。"""
    return SEC_CN.get(str(k).strip().lower(), k)




def parse_ts(ts):
    """解析历史记录时间戳，返回 aware datetime 或 None"""
    if not ts:
        return None
    s = str(ts).strip()
    for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%dT%H:%M:%S", "%Y-%m-%d %H:%M"):
        try:
            return datetime.strptime(s, fmt).replace(tzinfo=CST)
        except ValueError:
            continue
    return None


def load_history(path):
    fp = os.path.join(SITE_ROOT, path)
    if not os.path.exists(fp):
        return []
    try:
        with open(fp, encoding="utf-8") as f:
            d = json.load(f)
        return d if isinstance(d, list) else []
    except Exception:
        return []


def load_latest_time(path):
    """读该站 latest.json 的「最后检查时间」。

    history.json 只在有真实变化时才写入，latest.json 每轮抓取都会更新。
    两者不同步会让钉钉看起来「滞后于网站」——其实只是该时段确实没变化。
    这里补上检查时间，让消息能说清「查过了，但没变化」。
    """
    fp = os.path.join(SITE_ROOT, path.replace("history.json", "latest.json"))
    if not os.path.exists(fp):
        return None
    try:
        with open(fp, encoding="utf-8") as f:
            d = json.load(f)
        for k in ("updated_at", "updated", "ts", "generated_at"):
            v = parse_ts(d.get(k))
            if v:
                return v
    except Exception:
        pass
    return None


def last_change_time(hist):
    """history 里最后一次「真实变化」的时间（全 0 记录不算）。"""
    for e in reversed(hist or []):
        dt = parse_ts(e.get("ts"))
        if not dt:
            continue
        changed = False
        for k, v in e.items():
            if k == "ts" or not isinstance(v, dict):
                continue
            if (int(v.get("added", 0) or 0) or int(v.get("removed", 0) or 0)
                    or int(v.get("modified", 0) or 0)):
                changed = True
                break
        if changed:
            return dt
    return None


def human_ago(dt, now):
    """把时间差说成人话：刚 / N 分钟前 / N 小时前 / N 天前"""
    if not dt:
        return None
    secs = (now - dt).total_seconds()
    if secs < 0:
        secs = 0
    if secs < 3600:
        m = int(secs // 60)
        return "刚刚" if m <= 2 else "%d 分钟前" % m
    if secs < 86400:
        return "%d 小时前" % int(secs // 3600)
    return "%d 天前" % int(secs // 86400)


def summarize(hist, since):
    """汇总某站「最新一轮」的变化。

    注意：这里刻意不累加窗口内所有轮次。之前累加导致 24h 内每轮推送
    都会重复报同一批旧 diff（例如湖南卡了三天后首次补抓那轮的一次性
    大 diff），而网站「变化历史」显示的是最新一条 —— 两边看起来
    永远对不上，用户会以为钉钉在推老数据。
    改为只取窗口内最后一条记录，与网站同源同口径。
    """
    tot_add = tot_rm = tot_mod = 0
    secs = []
    batches = []
    latest = None
    latest_dt = None
    for e in hist:
        dt = parse_ts(e.get("ts"))
        if dt and dt < since:
            continue
        latest = e
        latest_dt = dt
    hist = [latest] if latest is not None else []
    for e in hist:
        dt = parse_ts(e.get("ts"))
        if dt and dt < since:
            continue
        for k, v in e.items():
            if k == "ts" or not isinstance(v, dict):
                continue
            a = int(v.get("added", 0) or 0)
            r = int(v.get("removed", 0) or 0)
            m = int(v.get("modified", 0) or 0)
            if not (a or r or m):
                continue
            tot_add += a
            tot_rm += r
            tot_mod += m
            note = v.get("note")
            # 批量同改说明：同一个字段同一种改法改了很多条时，提炼一句人话
            if m:
                for d in batch_notes(v):
                    batches.append((sec_cn(k), d))
            secs.append((sec_cn(k), a, r, m, note, str(k).strip().lower()))
    return tot_add, tot_rm, tot_mod, secs, batches


def _short(v, n=28):
    """把字段值压缩成短串，避免超长把消息撑爆。"""
    t = str(v or "").strip().replace("\n", " ")
    return t if len(t) <= n else t[:n] + "…"


def batch_notes(sec_obj, min_items=5, min_ratio=0.6):
    """识别「批量同改」：同一个字段、同一种改法，一次性改了很多条。

    移动常做这类操作（实测广东 113 条「下线日期」统一从 2026年9月30日
    延到 2026年12月31日）。汇总只报「修改 113」，用户看不出是真改还是
    又出 bug，还得再来问。这里自动提炼成一句人话附在下面。

    返回形如：  广东：113 条均为「下线日期」2026年9月30日 → 2026年12月31日
    """
    bef = sec_obj.get("modified_before") or {}
    aft = sec_obj.get("modified_after") or {}
    if not isinstance(bef, dict) or not isinstance(aft, dict) or not bef:
        return []
    groups = {}
    changed = 0
    for name, b in bef.items():
        a = aft.get(name)
        if not isinstance(b, dict) or not isinstance(a, dict):
            continue
        changed += 1
        for f in set(b) | set(a):
            if b.get(f) != a.get(f):
                key = (str(f), str(b.get(f)), str(a.get(f)))
                groups.setdefault(key, []).append(name)
    if not changed or not groups:
        return []
    # 占比最大的那种改法
    (field, old, new), names = max(groups.items(), key=lambda kv: len(kv[1]))
    cnt = len(names)
    if cnt < min_items or cnt < changed * min_ratio:
        return []
    if old and new:
        desc = "%d 条均为「%s」%s → %s" % (cnt, field, _short(old), _short(new))
    else:
        desc = "%d 条均为「%s」变更" % (cnt, field)
    rest = changed - cnt
    if rest > 0:
        desc += "（另有 %d 条其他改动）" % rest
    # before/after 明细未必覆盖全部修改条数（实测 113 条只记了 60 条明细），
    # 说明里要点明，否则用户拿 60 去对 113 会以为漏了一半。
    total = int(sec_obj.get("modified") or 0)
    if total and total > changed:
        desc += "；该板块共修改 %d 条，明细仅记录 %d 条" % (total, changed)
    return [desc]


def send_ding(title, text):
    if not WEBHOOK:
        print("未配置 DINGTALK_WEBHOOK，跳过推送")
        return False
    url = WEBHOOK
    if SECRET:
        ts = str(round(time.time() * 1000))
        h = hmac.new(SECRET.encode(), ("%s\n%s" % (ts, SECRET)).encode(), hashlib.sha256)
        sign = urllib.parse.quote_plus(base64.b64encode(h.digest()))
        url = "%s&timestamp=%s&sign=%s" % (url, ts, sign)
    body = json.dumps({"msgtype": "markdown",
                       "markdown": {"title": title, "text": text}},
                      ensure_ascii=False).encode("utf-8")
    req = urllib.request.Request(url, data=body,
                                 headers={"Content-Type": "application/json;charset=utf-8"})
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            res = json.load(r)
    except urllib.error.HTTPError as e:
        print("❌ 钉钉返回 HTTP %s：%s" % (e.code, e.read().decode("utf-8", "ignore")[:200]))
        return False
    except Exception as e:
        print("❌ 请求失败：%s" % e)
        return False
    ok = res.get("errcode") == 0
    print("钉钉返回: errcode=%s errmsg=%s" % (res.get("errcode"), res.get("errmsg")))
    return ok


def send_notify(title, text):
    """优先用多通道模块（钉钉/飞书/企业微信/邮件）；不可用时退回纯钉钉。"""
    try:
        import notify
        print("使用多通道推送模块 notify.py")
        return notify.send_all(title, text)
    except ImportError:
        print("未找到 notify.py，退回仅钉钉推送")
        ok = send_ding(title, text)
        return [("钉钉", bool(ok), "")]


def main():
    # 测试模式：验证 webhook/加签是否配对正确，不读数据
    if TEST_MODE:
        # 多通道时可能只配了飞书/企微/邮件而没配钉钉，交给 notify 统一判断
        try:
            import notify
            any_cfg = any(notify._env(k) for _, k, _ in notify.CHANNELS)
        except Exception:
            any_cfg = bool(WEBHOOK)
        if not any_cfg:
            print("❌ 一个通道都没配置。请在仓库 Secrets 或 .env 里至少填一个"
                  "（DINGTALK_WEBHOOK / FEISHU_WEBHOOK / WECOM_WEBHOOK / SMTP_*）。")
            return
        res = send_notify(
            "✅ 推送通道配置成功",
            "## ✅ 配置成功\n\n"
            "你的通知通道已成功接入「运营商资费监控」。\n\n"
            "**当前配置**\n\n"
            "- 关注省份：`%s`\n"
            "- 站点链接：%s\n\n"
            "下次资费变化将自动推送到这里。"
            % (FOCUS_SEC, SITE_URL or "未配置"))
        okc = [n for n, ok, _ in (res or []) if ok]
        print("测试完成：成功 %d / 已配置 %d%s"
              % (len(okc), len(res or []),
                 ("（%s）" % "、".join(okc)) if okc else ""))
        return

    now = datetime.now(CST)
    since = now - timedelta(hours=SINCE_HOURS)
    print("统计窗口: %s 之后 (CST)" % since.strftime("%Y-%m-%d %H:%M"))

    lines = ["## 资费变化汇总", "",
             "**统计范围**：%s ~ %s (北京时间)" %
             (since.strftime("%m-%d %H:%M"), now.strftime("%m-%d %H:%M")), ""]
    any_change = False
    grand = [0, 0, 0]

    for path, name, icon in SITES:
        hist = load_history(path)
        a, r, m, secs, batches = summarize(hist, since)
        grand[0] += a; grand[1] += r; grand[2] += m
        if not (a or r or m):
            # 说清「查过了但没变化」，而不是干巴巴一句「无变化」——
            # 否则用户看到网站时间戳在跳、钉钉却说无变化，会以为钉钉滞后。
            checked = load_latest_time(path)
            prev = last_change_time(hist)
            bits = []
            if checked:
                bits.append("数据至 %s" % checked.strftime("%m-%d %H:%M"))
            if prev:
                bits.append("上次变化 %s" % human_ago(prev, now))
            suffix = "（%s）" % "，".join(bits) if bits else ""
            lines.append("- %s **%s**：无变化%s" % (icon, name, suffix))
            continue
        any_change = True
        lines.append("- %s **%s**：新增 %d、下架 %d、修改 %d" % (icon, name, a, r, m))
        # 批量同改：附一句说明，避免只看到一个大数字却不知道改了什么
        for sec_name, desc in batches[:3]:
            lines.append("　└ %s：%s" % (sec_name, desc))
        # 推送只要总览：不列省份明细。
        # 明细请在网站「变化历史」查看（那里是完整分省数据，同源同口径）。

    lines.append("")
    lines.append("**合计**：新增 %d、下架 %d、修改 %d" % tuple(grand))
    if not any_change:
        lines.append("")
        lines.append("> 本时段内四家运营商均无资费变化。")

    # 结尾固定附链接（主站 + 四家子站直达），不再依赖外部配置是否填对
    lines.append("")
    lines.append("---")
    lines.append("🔗 [资费站入口](%s/)" % SITE_URL)
    lines.append("　[移动](%s/) ｜ [联通](%s/unicom/) ｜ [电信](%s/telecom/) ｜ [广电](%s/gb/)"
                 % (SITE_URL, SITE_URL, SITE_URL, SITE_URL))

    text = "\n".join(lines)
    print(text)

    # 本轮无变化时：定时触发直接跳过推送，不再把上一轮的旧变化当新消息重发。
    # （曾导致每天两次都收到昨晚同一条内容，误以为推送延迟了 12 小时。）
    # 手动触发（workflow_dispatch）仍然照常推 —— 那是站长主动要看，不是自动播报。
    ev = os.getenv("GITHUB_EVENT_NAME", "").strip()
    skip = (not any_change) and ev == "schedule" and not os.getenv("FORCE_PUSH")
    if skip:
        print("\n⏭ 本轮四家均无变化（定时触发）→ 跳过推送，不再重发旧内容。")
        print("   如需强制推送，设置 FORCE_PUSH=1（或在网页手动 Run workflow）。")
        return

    title = "资费汇总 新增%d 下架%d 修改%d" % tuple(grand)
    send_notify(title, text)


if __name__ == "__main__":
    main()
