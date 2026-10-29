#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""从 data/*.json 重建 data/latest.json（仪表盘统计）。

用途：抓取那一轮如果一条都没抓到（源站异常 / 网络失败），
build_site.py 会因为 snapshots/ 为空而写出「全 0」的 latest.json，
页面就显示 0 条。但 data/*.json 里的真实数据是完好的。

本脚本绕过 snapshots，直接读 data/*.json 重算统计，
用于在抓取失败时把仪表盘恢复成正确数字。

用法：
    python3 scripts/rebuild_latest.py
"""
import collections
import datetime
import json
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA = os.path.join(ROOT, "data")

SECTION_NAMES = {
    "quanguo": "全网(全国)",
    "beijing": "北京", "tianjin": "天津", "hebei": "河北", "shanxi": "山西",
    "neimenggu": "内蒙古", "liaoning": "辽宁", "jilin": "吉林",
    "heilongjiang": "黑龙江", "shanghai": "上海", "jiangsu": "江苏",
    "zhejiang": "浙江", "anhui": "安徽", "fujian": "福建", "jiangxi": "江西",
    "shandong": "山东", "henan": "河南", "hubei": "湖北", "hunan": "湖南",
    "guangdong": "广东", "guangxi": "广西", "hainan": "海南", "chongqing": "重庆",
    "sichuan": "四川", "guizhou": "贵州", "yunnan": "云南", "xizang": "西藏",
    "shaanxi": "陕西", "gansu": "甘肃", "qinghai": "青海", "ningxia": "宁夏",
    "xinjiang": "新疆",
}
DEFAULT_PROV = "hunan"


def sec_name(sec):
    return SECTION_NAMES.get(sec, sec)


def load(p):
    try:
        with open(p, encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return None


def stat_section(sec):
    j = load(os.path.join(DATA, sec + ".json"))
    items = (j or {}).get("items") or []
    dist = collections.defaultdict(collections.Counter)
    for it in items:
        f = it.get("fields") or {}
        dist[f.get("归属") or "未知"][f.get("资费类型") or "未知"] += 1
    return j, items, dict((k, dict(v)) for k, v in dist.items())


def union_prov_dist(st, sections):
    names = {}
    for sec in sections:
        if sec == "quanguo":
            continue
        for it in st[sec][1]:
            n = (it.get("name") or "").strip()
            if n:
                names.setdefault(n, it)
    d = collections.defaultdict(collections.Counter)
    for it in names.values():
        f = it.get("fields") or {}
        d[f.get("归属") or "未知"][f.get("资费类型") or "未知"] += 1
    return len(names), dict((k, dict(v)) for k, v in d.items())


def prov_stats_map(st, sections):
    out = {}
    for sec in sections:
        if sec == "quanguo":
            continue
        _j, items, dist = st[sec]
        out[sec] = {
            "total": len(items),
            "personal": sum((dist.get("个人资费") or {}).values()),
            "gq": sum((dist.get("政企资费") or {}).values()),
            "dist": dist,
        }
    return out


def main():
    if not os.path.isdir(DATA):
        print("data/ 不存在，跳过")
        return 1
    secs = []
    for fn in sorted(os.listdir(DATA)):
        if fn.endswith(".json"):
            sec = fn[:-5]
            if sec in SECTION_NAMES:
                secs.append(sec)
    if "quanguo" in secs:
        secs.remove("quanguo")
        secs.insert(0, "quanguo")
    if not secs:
        print("data/ 下没有板块文件，跳过")
        return 1

    st = dict((s, stat_section(s)) for s in secs)

    updated = ""
    for sec in secs:
        ts = (st[sec][0] or {}).get("timestamp") or ""
        if ts > updated:
            updated = ts
    if not updated:
        updated = datetime.datetime.now(
            datetime.timezone(datetime.timedelta(hours=8))
        ).strftime("%Y-%m-%d %H:%M:%S")

    def_sec = DEFAULT_PROV if DEFAULT_PROV in secs else secs[0]
    prov_total, prov_dist = union_prov_dist(st, secs)
    latest = {
        "updated": updated,
        "default": def_sec,
        "sections": [
            {
                "section": sec,
                "name": sec_name(sec),
                "total": len(st[sec][1]),
                "updated": (st[sec][0] or {}).get("timestamp") or "",
            }
            for sec in secs
        ],
        "quanguo_total": len(st.get("quanguo", (None, [], {}))[1]),
        "prov_total": prov_total,
        "prov_dist": prov_dist,
        "prov_stats": prov_stats_map(st, secs),
        "hunan_total": len(st.get(def_sec, (None, [], {}))[1]),
        "dist": st.get("quanguo", (None, [], {}))[2],
        "def_dist": dict(st.get(def_sec, (None, [], {}))[2].get("个人资费", {})),
    }
    out = os.path.join(DATA, "latest.json")
    with open(out, "w", encoding="utf-8") as f:
        json.dump(latest, f, ensure_ascii=False, indent=2)

    print("rebuilt latest.json:")
    print("  sections   : %d" % len(secs))
    print("  updated    : %s" % latest["updated"])
    print("  quanguo    : %d" % latest["quanguo_total"])
    print("  省份去重合计: %d" % latest["prov_total"])
    for s in latest["sections"][:6]:
        print("    - %-8s %5d 条  %s" % (s["name"], s["total"], s["updated"]))
    return 0


if __name__ == "__main__":
    sys.exit(main())
