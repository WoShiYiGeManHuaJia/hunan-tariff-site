# -*- coding: utf-8 -*-
"""清洗历史记录中的「假新增」。

背景：某轮分类被源站限流降级只采到部分数据，缺量快照被存成新基线；下轮
恢复全量后，那批本就存在、只是上一轮没采到的存量业务被判成「新增」。
实测湖南 09-13「甄选青春福袋」上线日期 2025-09-06，被记作 09-13 上架，
相差 372 天；全站大量此类误报。

本脚本按「上线日期」逐条核验：上线日期早于记录日 STALE_ONLINE_DAYS 天
以上者判为漏采补录，从 added_names 移到 restored_names，同步调整计数。
不删除任何数据，可重复运行（已清洗过则跳过）。
"""
import json, os, re, sys, shutil, datetime

ROOT = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(ROOT, "pipelines", "mobile"))
import snapshot as S

HIST = os.path.join(ROOT, "data", "history.json")
# 默认 2 天：抓取每天多轮，真新增的上线日期必然在本轮或前一两天；
# 早于此的基本都是上一轮限流降级漏采、本轮补回的存量业务。
DAYS = int(os.getenv("STALE_ONLINE_DAYS", "2") or 2)


def load_online(section):
    """从 data/{section}.json 反查 名字 -> 上线日期"""
    p = os.path.join(ROOT, "data", f"{section}.json")
    if not os.path.exists(p):
        return {}
    try:
        d = json.load(open(p, encoding="utf-8"))
    except Exception:
        return {}
    out = {}
    for it in d.get("items", []):
        n = S._parse_name(it)
        f = it.get("fields") if isinstance(it, dict) else None
        if n and isinstance(f, dict):
            out[n] = S._parse_cn_date(f.get("上线日期"))
    return out


def ts_date(ts):
    m = re.match(r"(\d{4})-(\d{2})-(\d{2})", str(ts))
    return datetime.date(*map(int, m.groups())) if m else None


def main():
    if not os.path.exists(HIST):
        print("[跳过] 无 history.json")
        return 0
    hist = json.load(open(HIST, encoding="utf-8"))
    secs = set()
    for r in hist:
        secs |= {k for k in r.keys() if k != "ts" and isinstance(r.get(k), dict)}
    online = {s: load_online(s) for s in secs}

    stat = {"total": 0, "restored": 0, "kept": 0, "unknown": 0}
    changed = 0
    for rec in hist:
        td = ts_date(rec.get("ts"))
        for sec in secs:
            blk = rec.get(sec)
            if not isinstance(blk, dict):
                continue
            names = blk.get("added_names") or []
            if not names:
                continue
            # 幂等：已用同一判据清洗过则跳过；判据收紧(DAYS 变小)时重洗，
            # 把上轮已归入补录的名字并回池子一起重新判定，避免重复计数。
            if blk.get("_clean_days") == DAYS and blk.get("restored_names") is not None:
                continue
            pool = list(names) + list(blk.get("restored_names") or [])
            stat["total"] += len(pool)
            # 优先用本条记录自带的 added_details 上线日期（当时抓到的原始字段，
            # 比从最新快照反查更贴近当时口径），查不到再回退最新快照。
            det = blk.get("added_details") if isinstance(blk.get("added_details"), dict) else {}
            real, restored = [], []
            for n in pool:
                d = None
                f = det.get(n)
                if isinstance(f, dict):
                    d = S._parse_cn_date(f.get("上线日期"))
                if d is None:
                    d = online.get(sec, {}).get(n)
                if d is None:
                    stat["unknown"] += 1
                    real.append(n)                     # 查不到 → 宁可保留
                elif td is not None and (td - d).days > DAYS:
                    restored.append(n)
                else:
                    real.append(n)
            blk["added_names"] = real
            blk["added"] = len(real)
            blk["restored_names"] = restored
            blk["restored"] = len(restored)
            blk["_clean_days"] = DAYS
            stat["restored"] += len(restored)
            stat["kept"] += len(real)
            if restored:
                changed += 1

    print(f"[清洗] 历史新增 {stat['total']} 条")
    print(f"       判为补录 {stat['restored']} 条 / 保留真新增 {stat['kept']} 条")
    print(f"       快照查不到(保留) {stat['unknown']} 条")
    print(f"       涉及记录 {changed} 条")
    if stat["restored"] == 0:
        print("[无变化] 未写入")
        return 0
    shutil.copy(HIST, HIST + ".bak")
    json.dump(hist, open(HIST, "w", encoding="utf-8"),
              ensure_ascii=False, separators=(",", ":"))
    print("[已写入] 备份 data/history.json.bak")
    return 0


if __name__ == "__main__":
    sys.exit(main())
