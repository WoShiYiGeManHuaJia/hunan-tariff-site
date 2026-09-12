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
SINCE_HOURS = float(os.getenv("SINCE_HOURS", "24"))
SITE_ROOT = os.getenv("SITE_ROOT", ".")
# 明细只列关注的省份（默认湖南），其余省份不展示
FOCUS_SEC = os.getenv("FOCUS_SEC", "hunan").strip().lower()
# 结尾附带的资费站访问链接
SITE_URL = os.getenv("SITE_URL", "https://woshiyigemanhuajia.github.io/hunan-tariff-site/").strip()
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


def summarize(hist, since):
    """汇总某站 since 之后的变化"""
    tot_add = tot_rm = tot_mod = 0
    secs = []
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
            secs.append((sec_cn(k), a, r, m, note, str(k).strip().lower()))
    return tot_add, tot_rm, tot_mod, secs


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
        a, r, m, secs = summarize(hist, since)
        grand[0] += a; grand[1] += r; grand[2] += m
        if not (a or r or m):
            lines.append("- %s **%s**：无变化" % (icon, name))
            continue
        any_change = True
        lines.append("- %s **%s**：新增 %d、下架 %d、修改 %d" % (icon, name, a, r, m))
        # 只列关注的省份（默认湖南），同一省份多条记录合并
        focus = [x for x in secs if x[5] == FOCUS_SEC]
        fname = sec_cn(FOCUS_SEC)
        if focus:
            fa = sum(x[1] for x in focus)
            fr = sum(x[2] for x in focus)
            fm = sum(x[3] for x in focus)
            notes = [x[4] for x in focus if x[4]]
            if notes:
                lines.append("  - `%s`：%s" % (fname, notes[-1][:60]))
            else:
                lines.append("  - `%s`：新增%d 下架%d 修改%d" % (fname, fa, fr, fm))
        else:
            lines.append("  - `%s`：无变化" % fname)

    lines.append("")
    lines.append("**合计**：新增 %d、下架 %d、修改 %d" % tuple(grand))
    if not any_change:
        lines.append("")
        lines.append("> 本时段内四家运营商均无资费变化。")

    if SITE_URL:
        lines.append("")
        lines.append("🔗 [查看完整资费站](%s)" % SITE_URL)

    text = "\n".join(lines)
    print(text)
    title = "资费汇总 新增%d 下架%d 修改%d" % tuple(grand)
    send_notify(title, text)


if __name__ == "__main__":
    main()
