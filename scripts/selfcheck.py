#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
构建后自检：把「各省不跑 / 数据回退 / 假新增」这类问题在 CI 里直接暴露出来，
而不是等用户打开页面才发现。

检查项：
  1. 板块新鲜度   —— 每个板块的 updated 是否超过阈值（默认 36 小时）
  2. 快照不倒退   —— pipelines/mobile/snapshots/<sec>.json 的 timestamp 是否早于线上
  3. 条目数不塌陷 —— 板块条目数是否相对上一轮出现大幅缩水
  4. 历史分片对齐 —— history.json 里有变化的记录是否都有对应 data/hist/<ts>.json
  5. 单轮新增合理性 —— 单条记录新增数是否异常（>2000 极可能是死快照回放）

用法：python3 scripts/selfcheck.py [--max-age-hours 36]
退出码：0 全部通过；1 存在 error 级问题
"""
import json
import os
import re
import sys
from datetime import datetime, timedelta, timezone

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA = os.path.join(ROOT, "data")
SNAP = os.path.join(ROOT, "pipelines", "mobile", "snapshots")
CST = timezone(timedelta(hours=8))

errors = []
warns = []


def err(msg):
    errors.append(msg)
    print("::error::" + msg)


def warn(msg):
    warns.append(msg)
    print("::warning::" + msg)


def load(p):
    try:
        with open(p, encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return None


def parse_ts(s):
    """解析 'YYYY-MM-DD HH:MM:SS'，失败返回 None"""
    try:
        return datetime.strptime(str(s)[:19], "%Y-%m-%d %H:%M:%S").replace(tzinfo=CST)
    except Exception:
        return None


def main():
    max_age = 36
    if "--max-age-hours" in sys.argv:
        i = sys.argv.index("--max-age-hours")
        if i + 1 < len(sys.argv):
            max_age = float(sys.argv[i + 1])

    latest = load(os.path.join(DATA, "latest.json"))
    if not latest:
        err("latest.json 读取失败")
        return 1

    now = datetime.now(CST)
    sections = latest.get("sections") or []
    print(f"[自检] 板块数 {len(sections)} | latest updated = {latest.get('updated')}")

    # ── 1. 板块新鲜度 ──
    stale = []
    for s in sections:
        ts = parse_ts(s.get("updated") or "")
        if ts is None:
            stale.append((s.get("section"), s.get("name"), "无时间戳"))
            continue
        age = (now - ts).total_seconds() / 3600.0
        if age > max_age:
            stale.append((s.get("section"), s.get("name"), f"{s.get('updated')[:16]}（{age:.0f}h 前）"))
    if stale:
        err(f"{len(stale)}/{len(sections)} 个板块数据已过期（> {max_age:.0f}h）："
            + "、".join(f"{n}({t})" for _, n, t in stale[:6])
            + ("…" if len(stale) > 6 else ""))
    else:
        print(f"[自检] ✓ 全部 {len(sections)} 个板块均在 {max_age:.0f}h 内更新")

    # ── 2. 快照时间不倒退 ──
    back = []
    for s in sections:
        sec = s.get("section")
        online = load(os.path.join(DATA, sec + ".json"))
        snap = load(os.path.join(SNAP, sec + ".json"))
        if not online or not snap:
            continue
        o = online.get("timestamp") or ""
        n = snap.get("timestamp") or ""
        if o and n and n < o:
            back.append((s.get("name"), n[:16], o[:16]))
    if back:
        err(f"{len(back)} 个板块快照时间早于线上（会触发倒退保护、该板块本轮不比对）："
            + "、".join(f"{a}(快照{b} < 线上{c})" for a, b, c in back[:5]))
    else:
        print("[自检] ✓ 快照时间均未倒退")

    # ── 3. 条目数不塌陷 ──
    shrink = []
    for s in sections:
        sec = s.get("section")
        total = s.get("total") or 0
        snap = load(os.path.join(SNAP, sec + ".json"))
        if not snap:
            continue
        n = len(snap.get("items") or [])
        if total > 0 and n > 0 and n < total * 0.5:
            shrink.append((s.get("name"), n, total))
    if shrink:
        warn(f"{len(shrink)} 个板块本轮快照条目数不足线上 50%："
             + "、".join(f"{a}({b}/{c})" for a, b, c in shrink[:5]))
    else:
        print("[自检] ✓ 无板块条目数塌陷")

    # ── 4. 历史分片对齐 ──
    hist_dir = os.path.join(DATA, "hist")
    have = set()
    if os.path.isdir(hist_dir):
        have = {f for f in os.listdir(hist_dir) if f.endswith(".json")}
    h = load(os.path.join(DATA, "history.json")) or []
    miss = []
    for r in h:
        tot = 0
        for k, v in r.items():
            if k == "ts" or not isinstance(v, dict):
                continue
            tot += sum((v.get(x) or 0) for x in ("added", "removed", "modified", "restored"))
        if tot and (re.sub(r"[^0-9A-Za-z]", "-", r["ts"]) + ".json") not in have:
            miss.append(r["ts"])
    if miss:
        err(f"{len(miss)} 条有变化的记录缺少详情分片（页面点开会是空的）：" + "、".join(miss[:5]))
    else:
        print(f"[自检] ✓ history {len(h)} 条与分片 {len(have)} 个一一对应")

    # ── 5. 单轮新增合理性 ──
    for r in h[-5:]:
        added = sum((v.get("added") or 0) for k, v in r.items()
                    if k != "ts" and isinstance(v, dict))
        if added > 2000:
            err(f"记录 {r['ts']} 单轮新增 {added} 条，极可能是死快照回放的假数据，请核查")
    print("[自检] ✓ 最近 5 轮无异常量级新增")

    print(f"\n[自检] 结果：error {len(errors)} 项 / warning {len(warns)} 项")
    return 1 if errors else 0


if __name__ == "__main__":
    sys.exit(main())
