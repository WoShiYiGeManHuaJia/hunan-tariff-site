#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
push_once.py —— 独立运行一次「拉数据 → 算汇总 → 推送」

跟 notify.py 的分工：
  notify.py   只负责发送（需要别人把内容喂给它）
  push_once.py 自己去站点拉最新数据、算出变化、再调用 notify.py 发送

所以只要这一个脚本就能跑，不用先抓数据、不用本地有任何历史文件。

用法：
    python3 push_once.py            # 拉数据并推送
    python3 push_once.py --test     # 只发一条「配置成功」测试消息
    python3 push_once.py --dry      # 只打印要推的内容，不真发

配置（同目录 .env，或环境变量）：
    # 推送渠道（至少填一个，见配置页面）
    DINGTALK_WEBHOOK=   DINGTALK_SECRET=
    FEISHU_WEBHOOK=     FEISHU_SECRET=
    WECOM_WEBHOOK=
    SMTP_HOST=  SMTP_PORT=  SMTP_USER=  SMTP_PASS=  MAIL_TO=

    # 数据站点（默认官方站，自建可改）
    SITE_URL=https://woshiyigemanhuajia.github.io/hunan-tariff-site/
    FOCUS_SEC=hunan      # 明细里列哪个省，其余不列
    SINCE_HOURS=24       # 统计最近多少小时

定时（每天 9 点）：
    0 9 * * * cd /你的目录 && python3 push_once.py
"""

import os
import sys
import json
import time
import urllib.request
from datetime import datetime, timedelta, timezone

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
try:
    import notify
except ImportError:
    sys.stderr.write("缺少 notify.py，请与本脚本放同一目录\n")
    sys.exit(2)

CST = timezone(timedelta(hours=8))

# 四家运营商：显示名 / 图标 / 数据文件
ISPS = [
    ("移动", "🔵", "data/history.json"),
    ("联通", "🟠", "unicom/data/history.json"),
    ("电信", "🟢", "telecom/data/history.json"),
    ("广电", "🟣", "gb/data/history.json"),
]

PROV_NAMES = {
    "quanguo": "全国", "beijing": "北京", "tianjin": "天津", "hebei": "河北",
    "shanxi": "山西", "neimenggu": "内蒙古", "liaoning": "辽宁", "jilin": "吉林",
    "heilongjiang": "黑龙江", "shanghai": "上海", "jiangsu": "江苏", "zhejiang": "浙江",
    "anhui": "安徽", "fujian": "福建", "jiangxi": "江西", "shandong": "山东",
    "henan": "河南", "hubei": "湖北", "hunan": "湖南", "guangdong": "广东",
    "guangxi": "广西", "hainan": "海南", "chongqing": "重庆", "sichuan": "四川",
    "guizhou": "贵州", "yunnan": "云南", "xizang": "西藏", "shaanxi": "陕西",
    "gansu": "甘肃", "qinghai": "青海", "ningxia": "宁夏", "xinjiang": "新疆",
}


def cfg(k, d=""):
    return os.getenv(k, d).strip()


def prov_name(code):
    return PROV_NAMES.get((code or "").lower(), code)


def fetch_json(url, timeout=30):
    req = urllib.request.Request(
        url, headers={"User-Agent": "tariff-push/1.0", "Accept": "application/json"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read().decode("utf-8", "ignore"))


def _n(v):
    """变化条数可能是列表（明细）也可能是数字（只存了计数），都要能算。"""
    if v is None:
        return 0
    if isinstance(v, bool):
        return 0
    if isinstance(v, int):
        return v
    if isinstance(v, (list, tuple)):
        return len(v)
    if isinstance(v, dict):
        return len(v)
    return 0


def parse_ts(s):
    """解析 '2026-09-12 20:10:40' 这类时间字符串（北京时间）"""
    s = (s or "").strip()
    for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%dT%H:%M:%S", "%Y-%m-%d %H:%M"):
        try:
            return datetime.strptime(s, fmt).replace(tzinfo=CST)
        except ValueError:
            continue
    return None


def collect(base, rel, since_h):
    """从站点拉某个运营商的 history.json，汇总最近 since_h 小时内的变化。

    返回 (added, removed, modified, {section: (a,r,m)}, 数据条数)
    """
    try:
        hist = fetch_json(base.rstrip("/") + "/" + rel)
    except Exception as e:
        print("  ⚠ %s 拉取失败：%s" % (rel, e))
        return 0, 0, 0, {}, 0
    if not isinstance(hist, list) or not hist:
        return 0, 0, 0, {}, 0

    cutoff = datetime.now(CST) - timedelta(hours=since_h)
    ta = tr = tm = 0
    per = {}
    used = 0
    for entry in reversed(hist):
        ts = parse_ts(entry.get("ts"))
        if ts and ts < cutoff:
            break
        used += 1
        for sec, v in entry.items():
            if sec == "ts" or not isinstance(v, dict):
                continue
            a = _n(v.get("added") if v.get("added") is not None else v.get("added_names"))
            r = _n(v.get("removed") if v.get("removed") is not None else v.get("removed_names"))
            m = _n(v.get("modified") if v.get("modified") is not None else v.get("modified_names"))
            ta += a
            tr += r
            tm += m
            pa, pr, pm = per.get(sec, (0, 0, 0))
            per[sec] = (pa + a, pr + r, pm + m)
    return ta, tr, tm, per, used


def build(since_h, focus, site_url):
    base = site_url or "https://woshiyigemanhuajia.github.io/hunan-tariff-site/"
    now = datetime.now(CST)
    start = now - timedelta(hours=since_h)

    lines = ["## 资费变化汇总", ""]
    lines.append("**统计范围**：%s ~ %s (北京时间)"
                 % (start.strftime("%m-%d %H:%M"), now.strftime("%m-%d %H:%M")))
    lines.append("")

    TA = TR = TM = 0
    for name, icon, rel in ISPS:
        a, r, m, per, used = collect(base, rel, since_h)
        TA += a
        TR += r
        TM += m
        if not (a or r or m):
            lines.append("- %s %s：无变化" % (icon, name))
            continue
        lines.append("- %s %s：新增 %d、下架 %d、修改 %d" % (icon, name, a, r, m))
        fa, fr, fm = per.get(focus, (0, 0, 0))
        if (fa or fr or fm):
            lines.append("  - %s：新增%d 下架%d 修改%d" % (prov_name(focus), fa, fr, fm))
        else:
            lines.append("  - %s：无变化" % prov_name(focus))

    lines.append("")
    lines.append("**合计**：新增 %d、下架 %d、修改 %d" % (TA, TR, TM))
    if site_url:
        lines.append("")
        lines.append("🔗 [查看完整资费站](%s)" % (site_url.rstrip("/") + "/"))
    return "\n".join(lines), (TA, TR, TM)


def main():
    notify._load_dotenv()
    site_url = cfg("SITE_URL", "https://woshiyigemanhuajia.github.io/hunan-tariff-site/")
    focus = (cfg("FOCUS_SEC", "hunan") or "hunan").lower()
    try:
        since_h = int(cfg("SINCE_HOURS", "24") or 24)
    except ValueError:
        since_h = 24

    if "--test" in sys.argv:
        return notify._cli_test() if hasattr(notify, "_cli_test") else _test()

    md, (ta, tr, tm) = build(since_h, focus, site_url)

    if "--dry" in sys.argv:
        print(md)
        print("\n[--dry] 以上为将要推送的内容，未实际发送。")
        return 0

    if not (ta or tr or tm) and cfg("SKIP_EMPTY", "1") == "1":
        print("无变化，跳过推送。")
        return 0

    print(md)
    print()
    res = notify.send_all("资费变化汇总", md)
    ok = [n for n, good, _ in res if good]
    print("\n推送完成：成功 %d / %d %s" % (len(ok), len(res), ("（%s）" % "、".join(ok)) if ok else ""))
    return 0 if ok else 1


def _test():
    title = "✅ 推送通道配置成功"
    lines = ["## ✅ 配置成功", "",
             "你的通知通道已成功接入「运营商资费监控」。", "",
             "**已启用通道**", ""]
    any_ok = False
    for name, envkey, fn in notify.CHANNELS:
        on = bool(notify._env(envkey))
        lines.append("- %s %s：%s" % ("✅" if on else "⚪", name, "已配置" if on else "未配置"))
        if on:
            any_ok = True
    lines += ["", "下次资费变化将自动推送到这里。", "",
              "关注省份：%s，统计最近 %s 小时。" % (prov_name(cfg("FOCUS_SEC", "hunan")), cfg("SINCE_HOURS", "24"))]
    if not any_ok:
        print("❌ 一个通道都没配置。请在 .env 里至少填一个。")
        return 1
    res = notify.send_all(title, "\n".join(lines))
    ok = [n for n, good, _ in res if good]
    print("\n测试完成：成功 %d / 已配置 %d %s"
          % (len(ok), len(res), ("（%s）" % "、".join(ok)) if ok else ""))
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
