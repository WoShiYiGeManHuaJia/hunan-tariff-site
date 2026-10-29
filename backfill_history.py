"""补录：全民百G礼包网龄版 5 个新档位（被字段结构升级检测吞掉的真实新增）。

背景：本轮给 fetcher 增加「短信」字段后，新旧快照字段键集合不一致，
build_site 判定为「格式升级」并直接重建基线、整板块不计数 —— 于是这 5 条
9-18 上线的真新增没进 history。此处按业务名差集补录回去。
"""
import json
import os

ROOT = os.path.dirname(os.path.abspath(__file__))
NAMES = [
    "全民百G礼包网龄版15元200G档（立即）",
    "全民百G礼包网龄版10元100G档（立即）",
    "全民百G礼包网龄版10元90G档（立即）",
    "全民百G礼包网龄版10元80G档（立即）",
    "全民百G礼包网龄版10元70G档（立即）",
]
TS = "2026-09-18 16:44:35"   # 该轮快照时间戳

hist_path = os.path.join(ROOT, "data", "history.json")
hunan_path = os.path.join(ROOT, "data", "hunan.json")

history = json.load(open(hist_path, encoding="utf-8"))
hunan = json.load(open(hunan_path, encoding="utf-8"))

by_name = {it["name"]: it for it in (hunan.get("items") or [])}

if any(r.get("ts") == TS and any(
        n in ((r.get("hunan") or {}).get("added_names") or []) for n in NAMES)
       for r in history):
    print("[跳过] 已补录过，不重复写入")
    raise SystemExit(0)

# 板块键沿用最近一条记录
secs = [k for k in history[-1].keys() if k != "ts"]
rec = {"ts": TS}
for s in secs:
    rec[s] = {"added": 0, "removed": 0, "modified": 0,
              "added_names": [], "removed_names": [], "modified_names": []}

found, details = [], {}
for n in NAMES:
    it = by_name.get(n)
    if not it:
        print("[警告] 快照里找不到：", n)
        continue
    found.append(n)
    details[n] = it.get("fields") or {}

if not found:
    print("[失败] 一条都没找到，未写入")
    raise SystemExit(1)

rec["hunan"] = {
    "added": len(found),
    "removed": 0,
    "modified": 0,
    "added_names": found,
    "removed_names": [],
    "modified_names": [],
    "added_details": details,
    "note": "retroactive",   # 事后补录（原轮次被结构升级逻辑吞掉）
}

# 按时间顺序插入
pos = len(history)
for i, r in enumerate(history):
    if r.get("ts", "") > TS:
        pos = i
        break
history.insert(pos, rec)

json.dump(history, open(hist_path, "w", encoding="utf-8"),
          ensure_ascii=False, indent=1)
print(f"[完成] 补录 {len(found)} 条到 history（位置 {pos}，ts={TS}）")
for n in found:
    f = details[n]
    print(f"   {n}  {f.get('资费标准')} · 通话{f.get('国内通话')} · "
          f"流量{f.get('国内通用流量')} · 短信{f.get('短信') or '(待重抓)'} · "
          f"{f.get('方案编号')}")
