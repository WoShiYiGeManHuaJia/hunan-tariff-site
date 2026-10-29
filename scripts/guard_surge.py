#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
变化暴涨/暴跌熔断 —— 防止「抓取不稳定」被误报成真实资费变化。

背景（两类事故，都已真实发生过）：
  A. 假新增洪峰：上轮被源站限流只抓到子集，本轮抓全后，那批本来就存在、
     只是上轮没抓到的存量业务被全部判成「新增」——曾一次虚报 3177 条。
  B. 抓取震荡：源站返回「确定性子集」时，某批业务这轮抓到、下轮没抓到，
     于是反复「新增 → 下架 → 新增」，history 里全是噪声，推送天天刷屏。

策略：本轮构建完成后、写入 history 之前，逐板块检查变化量：
  · 新增 或 下架 条数超过阈值（绝对数 + 占在架比例 双判据）→ 判定该板块
    本轮抓取不稳定，把该板块的变化作废（added/removed/modified 清零，
    名字列表移到 suppressed 字段留档），避免污染 history 与推送。
  · 只作废「疑似不稳」的板块，其余板块照常记录，不搞一刀切。

用法：python scripts/guard_surge.py           # 检查并熔断
      python scripts/guard_surge.py --dry-run # 只报告不改写
退出码：0=正常，1=已熔断（有板块被作废），2=数据异常
"""
import argparse
import json
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA = os.path.join(ROOT, "data")

# 绝对条数阈值：单板块新增/下架超过这么多就熔断
ABS_LIMIT = int(os.getenv("SURGE_ABS_LIMIT") or "150")
# 占在架比例阈值：超过该比例也熔断（小省份用比例更准）
RATIO_LIMIT = float(os.getenv("SURGE_RATIO_LIMIT") or "0.08")
# 在架条数太少时不按熔断处理（新板块首次建基线）
MIN_TOTAL = int(os.getenv("SURGE_MIN_TOTAL") or "50")


def _items(sec):
    p = os.path.join(DATA, "%s.json" % sec)
    if not os.path.exists(p):
        return None
    try:
        d = json.load(open(p, encoding="utf-8"))
        return d.get("items") or []
    except Exception:
        return None


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true", help="只报告，不改写")
    args = ap.parse_args()

    hpath = os.path.join(DATA, "history.json")
    if not os.path.exists(hpath):
        print("[guard] 无 history.json")
        return 2
    hist = json.load(open(hpath, encoding="utf-8"))
    if not hist:
        print("[guard] history 为空")
        return 2

    rec = hist[-1]          # 只检查最新一轮
    print("=" * 66)
    print("变化暴涨熔断检查")
    print("=" * 66)
    print("记录: %s" % rec.get("ts"))
    print("阈值: 绝对 %d 条 / 占在架 %.0f%%（在架<%d 不熔断）"
          % (ABS_LIMIT, RATIO_LIMIT * 100, MIN_TOTAL))
    print("-" * 66)

    hit = 0
    for sec, blk in rec.items():
        if sec == "ts" or not isinstance(blk, dict):
            continue
        added = blk.get("added") or 0
        removed = blk.get("removed") or 0
        if not added and not removed:
            continue
        items = _items(sec)
        total = len(items) if items is not None else 0
        if total < MIN_TOTAL:
            continue
        worst, kind = max((added, "新增"), (removed, "下架"))
        by_abs = worst > ABS_LIMIT
        by_ratio = total and (worst / total) > RATIO_LIMIT
        if not (by_abs or by_ratio):
            continue
        hit += 1
        print("\n⚠ 【%s】在架 %d 条" % (sec, total))
        print("   新增 %d / 下架 %d / 修改 %d" % (
            added, removed, blk.get("modified") or 0))
        print("   触发: %s %d 条（绝对%s / 比例%s）" % (
            kind, worst,
            "超" if by_abs else "未超",
            "超" if by_ratio else "未超"))
        if not args.dry_run:
            # 作废本轮该板块变化：计数清零，名字列表留档便于事后核对
            for k in ("added", "removed", "modified", "restored"):
                blk["suppressed_%s" % k] = blk.get(k) or 0
                blk[k] = 0
            for k in ("added_names", "removed_names", "modified_names",
                      "restored_names"):
                if blk.get(k):
                    blk["suppressed_%s" % k] = blk[k]
                    blk[k] = []
            blk["_suppressed_reason"] = "变化量异常，疑似抓取不稳（熔断）"
            print("   → 已作废本轮该板块变化（原值留档 suppressed_*）")

    print("\n" + "-" * 66)
    if not hit:
        print("各板块变化量正常，未熔断。")
        return 0
    if args.dry_run:
        print("（--dry-run）发现 %d 个板块异常，未改写。" % hit)
        return 1
    json.dump(hist, open(hpath, "w", encoding="utf-8"),
              ensure_ascii=False, separators=(",", ":"))
    print("已熔断 %d 个板块并写回 history.json。" % hit)
    print("提示：这些板块本轮数据仍已入库，只是变化不计入历史，"
          "下一轮恢复稳定后会自动补记。")
    return 1


if __name__ == "__main__":
    sys.exit(main())
