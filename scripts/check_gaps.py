#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
方案编号连续性自检 —— 用于发现「静默漏抓」。

背景：源站按「IP + UA 指纹」隔离限流配额，配额耗尽时会返回**确定性子集**
（即每次都缺同一批条目，而不是随机缺）。这种缺失不会触发原有的条数降级
检测（条数只是略少），也不会产生 diff（因为从来没抓到过），于是表现为
「该省长期无变化」——极易被误判成源站没更新。

原理：同一批录入的资费，方案编号是连续的（如 26HN200889 ~ 26HN200893）。
若某个板块里存在一段编号「两头都有、中间整段缺失」，说明中间那批被漏了。

用法：
    python scripts/check_gaps.py                  # 检查全部板块
    python scripts/check_gaps.py --min-gap 3      # 缺口≥3 才报告
输出：
    人类可读报告 + 退出码（0=无缺口，1=发现缺口，2=数据异常）
"""
import argparse
import json
import os
import re
import sys
from collections import defaultdict

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA = os.path.join(ROOT, "data")

# 方案编号形如 26HN200910 / 24HN203498 / 25GD000123
# 结构：<2位年份><2位省码><6位序号>
PAT = re.compile(r"(\d{2})([A-Z]{2})(\d{6})")

# 省码 -> 中文名（用于报告）
PROV_CN = {
    "HN": "湖南", "GD": "广东", "BJ": "北京", "SH": "上海", "CQ": "重庆",
    "TJ": "天津", "HB": "河北", "SX": "山西", "NM": "内蒙古", "LN": "辽宁",
    "JL": "吉林", "HL": "黑龙江", "JS": "江苏", "ZJ": "浙江", "AH": "安徽",
    "FJ": "福建", "JX": "江西", "SD": "山东", "HA": "河南", "HB2": "湖北",
    "GX": "广西", "HI": "海南", "SC": "四川", "GZ": "贵州", "YN": "云南",
    "XZ": "西藏", "SN": "陕西", "GS": "甘肃", "QH": "青海", "NX": "宁夏",
    "XJ": "新疆",
}


def load_sections(latest_path):
    """从 latest.json 读取板块列表（不含条目，条目在各省分片里）"""
    with open(latest_path, "r", encoding="utf-8") as f:
        return json.load(f)


def iter_items(path):
    with open(path, "r", encoding="utf-8") as f:
        d = json.load(f)
    if isinstance(d, dict):
        return d.get("items") or []
    return d if isinstance(d, list) else []


def collect_nums(items):
    """收集条目里的方案编号 -> {省码: [(序号, 业务名)]}"""
    out = defaultdict(list)
    for x in items:
        if not isinstance(x, dict):
            continue
        fields = x.get("fields") or {}
        raw = str(fields.get("方案编号") or x.get("方案编号") or "")
        m = PAT.search(raw)
        if not m:
            continue
        year, pcode, seq = m.group(1), m.group(2), int(m.group(3))
        out[pcode].append((seq, str(x.get("name") or "")[:38], raw))
    return out


def find_gaps(nums, min_gap, max_gap):
    """找「两头都有、中间整段缺失」的连续缺口"""
    gaps = []
    for pcode, lst in nums.items():
        lst.sort()
        seqs = [s for s, _n, _r in lst]
        uniq = sorted(set(seqs))
        for i in range(len(uniq) - 1):
            lo, hi = uniq[i], uniq[i + 1]
            miss = hi - lo - 1
            if miss < min_gap or miss > max_gap:
                continue
            # 缺口两侧的样本业务名，便于人工核对
            left = next((n for s, n, _r in lst if s == lo), "")
            right = next((n for s, n, _r in lst if s == hi), "")
            gaps.append({
                "pcode": pcode,
                "prov": PROV_CN.get(pcode, pcode),
                "lo": lo, "hi": hi, "miss": miss,
                "missing": list(range(lo + 1, hi)),
                "left_name": left, "right_name": right,
            })
    return gaps


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--min-gap", type=int, default=3,
                    help="缺口数量达到多少才报告（默认 3）")
    ap.add_argument("--max-gap", type=int, default=40,
                    help="缺口数量超过多少视为正常批次间隔（默认 40）")
    ap.add_argument("--sections", default="",
                    help="只检查指定板块，逗号分隔（默认全部）")
    args = ap.parse_args()

    latest = os.path.join(DATA, "latest.json")
    if not os.path.exists(latest):
        print("[gaps] 找不到 data/latest.json")
        return 2
    meta = load_sections(latest)
    secs = []
    for s in (meta.get("sections") or []):
        k = s.get("section")
        if not k:
            continue
        if args.sections and k not in args.sections.split(","):
            continue
        secs.append((k, s.get("name") or k))

    total_gaps = 0
    print("=" * 68)
    print("方案编号连续性自检（查静默漏抓）")
    print("=" * 68)
    for sec, sname in secs:
        p1 = os.path.join(DATA, "%s.json" % sec)
        if not os.path.exists(p1):
            continue
        items = iter_items(p1)
        nums = collect_nums(items)
        gaps = find_gaps(nums, args.min_gap, args.max_gap)
        if not gaps:
            continue
        print("\n【%s】%s  条目 %d" % (sname, sec, len(items)))
        for g in gaps:
            total_gaps += g["miss"]
            print("  ⚠ %s %s%d ~ %d 缺 %d 个：%s…%s" % (
                g["prov"], "" , g["lo"], g["hi"], g["miss"],
                str(g["missing"][:3])[1:-1],
                "" if g["miss"] <= 3 else " …%d" % g["missing"][-1]))
            print("      左邻 %s" % g["left_name"])
            print("      右邻 %s" % g["right_name"])

    print("\n" + "-" * 68)
    if total_gaps:
        print("发现疑似漏抓编号 %d 个 —— 极可能是源站限流返回了确定性子集，" % total_gaps)
        print("建议：对该板块加大重试轮次 / 换 UA 池重抓，抓全后再比对。")
        return 1
    print("未发现编号缺口。")
    return 0


if __name__ == "__main__":
    sys.exit(main())
