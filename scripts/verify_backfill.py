#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
1) 把被压缩成单行的 history.json 恢复为缩进格式（内容与顺序完全不变）
2) 生成一份校验报告 backfill_report.txt
"""
import json, os

SITES = [
    ("移动", "data/history.json", True),
    ("联通", "unicom/data/history.json", False),
    ("电信", "telecom/data/history.json", False),
    ("广电", "gb/data/history.json", False),
]


def stat(hist):
    recs = len(hist) if isinstance(hist, list) else 0
    names = dets = 0
    missing = []
    for rec in hist if isinstance(hist, list) else []:
        if not isinstance(rec, dict):
            continue
        for scope, blk in rec.items():
            if scope == "ts" or not isinstance(blk, dict):
                continue
            for kind in ("added", "removed"):
                ns = blk.get(kind + "_names") or []
                dt = blk.get(kind + "_details") or {}
                if not isinstance(ns, list):
                    continue
                names += len(ns)
                for n in ns:
                    if isinstance(n, str) and isinstance(dt, dict) and n in dt:
                        dets += 1
                    elif isinstance(n, str):
                        missing.append((rec.get("ts"), scope, kind, n))
    return recs, names, dets, missing


def main():
    lines = []
    for label, path, want_indent in SITES:
        if not os.path.exists(path):
            lines.append("[%s] %s 不存在" % (label, path)); continue
        txt = open(path, encoding="utf-8").read()
        hist = json.loads(txt)
        recs, names, dets, missing = stat(hist)

        # 恢复缩进
        if want_indent and txt.strip().count("\n") < 10:
            with open(path, "w", encoding="utf-8") as f:
                json.dump(hist, f, ensure_ascii=False, indent=2)
            lines.append("[%s] 已恢复缩进格式" % label)

        lines.append("[%s] 记录 %d · 业务名 %d · 有字段 %d · 仍缺 %d"
                     % (label, recs, names, dets, len(missing)))
        for m in missing[:12]:
            lines.append("    缺: %s | %s | %s | %s" % m)
        if len(missing) > 12:
            lines.append("    ...另有 %d 条" % (len(missing) - 12))

    # 专项：小家电
    p = "data/history.json"
    if os.path.exists(p):
        hist = json.load(open(p, encoding="utf-8"))
        for rec in hist:
            for scope, blk in rec.items():
                if scope == "ts" or not isinstance(blk, dict):
                    continue
                for kind in ("added", "removed"):
                    dt = blk.get(kind + "_details") or {}
                    for n in dt:
                        if "小家电" in str(n):
                            v = dt[n]
                            lines.append("[小家电] %s | %s/%s | 字段数 %d" % (n, scope, kind, len(v)))
                            lines.append("    " + json.dumps(v, ensure_ascii=False)[:300])
    open("backfill_report.txt", "w", encoding="utf-8").write("\n".join(lines))
    print("\n".join(lines))


if __name__ == "__main__":
    main()
