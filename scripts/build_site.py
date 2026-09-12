#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""构建站点数据：snapshots -> _site（供 GitHub Pages 展示）
由 build-site.yml 在云端 runner 上调用。
输入：
  snapshots/*.json（当前快照：quanguo + 任意省份，仓库 main 检出）
  _prev/*.json（上次快照副本，来自 gh-pages 分支 prev/ 目录，首次为空）
输出：
  _site/  静态站点内容（含 data/ 与 prev/）

板块由 snapshots/ 目录自动发现：quanguo 固定在前，其余省份按文件名排序；
省份显示名内置本文件，与抓取侧 province_table.section_name 保持一致。
"""
import collections
import datetime
import json
import os
import shutil

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SNAP = os.path.join(ROOT, "snapshots")
PREV = os.path.join(ROOT, "_prev")
SITE = os.path.join(ROOT, "_site")
SITE_SRC = os.path.join(ROOT, "site")   # 静态页面源码（index.html / style.css / app.js）
DATA = os.path.join(SITE, "data")
PREV_OUT = os.path.join(SITE, "prev")
os.makedirs(DATA, exist_ok=True)
os.makedirs(PREV_OUT, exist_ok=True)

# 板块 -> 显示名（31 省 + 全网，与官网 tariffZonePers.js 代码表一致）
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

# 展示站默认选中的省份（前端记忆用户选择，首次访问用此值）
DEFAULT_PROV = "hunan"


def sec_name(sec):
    return SECTION_NAMES.get(sec, sec)


def all_sections():
    """发现 snapshots/ 下所有板块（quanguo 排最前，其余按 SECTION_NAMES 声明排序）。"""
    secs = []
    if os.path.isdir(SNAP):
        for fn in sorted(os.listdir(SNAP)):
            if fn.endswith(".json") and os.path.isfile(os.path.join(SNAP, fn)):
                sec = fn[:-5]
                if sec in SECTION_NAMES:
                    secs.append(sec)
    if "quanguo" in secs:
        secs.remove("quanguo")
        secs = ["quanguo"] + secs
    return secs


def load(path):
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return None


def name_of(item):
    return (item.get("name") or "").strip()


def _norm_val(v):
    """归一化字段值：剥离源站混入的 HTML 标签与多余空白。

    不处理的话，纯 <p></p> / 换行 之类的变化也会被记为「修改」，
    前端展示时修改前后看起来一模一样，用户无法判断到底改了什么。
    """
    import re as _re
    x = "" if v is None else str(v)
    x = _re.sub(r"<br\s*/?>", " ", x, flags=_re.I)
    x = _re.sub(r"</?p[^>]*>", " ", x, flags=_re.I)
    x = _re.sub(r"<[^>]*>", "", x)
    x = _re.sub(r"&(?:nbsp|amp|lt|gt|quot|#39);", " ", x, flags=_re.I)
    return _re.sub(r"\s+", " ", x).strip()


def field_diff(old, new):
    """字段级修改明细：对比两个业务条目的 fields 字典，返回 [{field, from, to}, ...]。"""
    def fields_of(item):
        f = item.get("fields") if isinstance(item, dict) else None
        return f if isinstance(f, dict) else {}
    of, nf = fields_of(old), fields_of(new)
    keys = list(of.keys())
    for k in nf:
        if k not in keys:
            keys.append(k)
    out = []
    for k in keys:
        ov, nv = of.get(k), nf.get(k)
        os_ = _norm_val(ov)
        ns_ = _norm_val(nv)
        if os_ != ns_:
            out.append({"field": k, "from": os_, "to": ns_})
    return out


def _clip_fields(fields, limit=300):
    """截断字段值中的超长文本，避免历史文件被个别长描述撑爆。"""
    out = {}
    for k, v in (fields or {}).items():
        if isinstance(v, str) and len(v) > limit:
            out[k] = v[:limit] + "…"
        else:
            out[k] = v
    return out


def diff_items(old_items, new_items):
    """返回 (新增, 下架, 修改, 修改明细 name->[{field,from,to}],
             修改前快照 name->fields, 修改后快照 name->fields)。以名称为 key。

    除了字段级差异明细，还保留修改前后的**完整字段快照**，供前端并排对比
    —— 只看差异片段无法判断改动落在哪个业务上下文里（用户明确要求）。
    """
    om = {name_of(i): i for i in (old_items or [])}
    nm = {name_of(i): i for i in (new_items or [])}
    added = [nm[k] for k in nm if k not in om]
    removed = [om[k] for k in om if k not in nm]
    modified = []
    modified_details = {}
    mod_before, mod_after = {}, {}
    for k in om:
        if k in nm and om[k] != nm[k]:
            modified.append(om[k])
            modified_details[k] = field_diff(om[k], nm[k])
            mod_before[k] = _clip_fields(om[k].get("fields") or {})
            mod_after[k] = _clip_fields(nm[k].get("fields") or {})
    return added, removed, modified, modified_details, mod_before, mod_after


def _field_keys(items):
    """取快照条目统一的字段键集合；无结构字段时返回 None。"""
    for it in (items or []):
        f = it.get("fields") if isinstance(it, dict) else None
        if isinstance(f, dict):
            return tuple(sorted(f.keys()))
    return None


def _structure_upgraded(old_items, new_items):
    """新旧快照字段结构是否不一致（如字段集新增/删减），是则视为格式升级。"""
    ok, nk = _field_keys(old_items), _field_keys(new_items)
    return ok is not None and nk is not None and ok != nk


def clean_upgrade_false_records(history, st):
    """剔除字段结构升级造成的全量误报记录：
    某条记录里某板块 modified 数量 >= 该板块业务总量的 90%，几乎不可能真实发生，
    判定为新增字段（如"其他说明"）升级时快照整体 diff 产生的假数据，予以清理。"""
    cleaned = []
    for rec0 in history:
        if not isinstance(rec0, dict):
            cleaned.append(rec0)
            continue
        suspicious = False
        for sec, d in rec0.items():
            if sec == "ts" or not isinstance(d, dict) or d.get("note") == "baseline":
                continue
            mod = d.get("modified") or 0
            total = len(st[sec][1]) if sec in st else 0
            if total and mod >= total * 0.9:
                suspicious = True
                break
        if not suspicious:
            cleaned.append(rec0)
    return cleaned


def same_change(a, b):
    """判断两条历史记录的业务变更是否等效（忽略 ts 与字段级明细），用于防止重复记录。"""
    if not isinstance(a, dict) or not isinstance(b, dict):
        return False
    keys = set(a) | set(b)
    for k in keys:
        if k == "ts":
            continue
        av, bv = a.get(k), b.get(k)
        if isinstance(av, dict) and isinstance(bv, dict):
            if av.get("note") or bv.get("note"):
                if av.get("note") != bv.get("note"):
                    return False
                continue
            for sk in ("added", "removed", "modified", "added_names", "removed_names", "modified_names"):
                if av.get(sk) != bv.get(sk):
                    return False
        elif av != bv:
            return False
    return True


def is_reverse_change(a, b):
    """判断两条记录是否互为「反向抖动」。

    典型症状：上一轮记 add=14，本轮记 rm=14（同一批业务）；字段级修改的
    from/to 也整体互换。这不是真实业务变化，而是基线/源站在两个状态间回弹
    （prev 基线未落地、或源站返回了上一版数据）造成的假变化。
    逐板块判定：任一方向相反即视为抖动。
    """
    if not isinstance(a, dict) or not isinstance(b, dict):
        return False
    flipped = 0
    checked = 0
    for sec in set(a) | set(b):
        if sec == "ts":
            continue
        av, bv = a.get(sec), b.get(sec)
        if not isinstance(av, dict) or not isinstance(bv, dict):
            continue
        if av.get("note") or bv.get("note"):
            continue
        a_add, a_rm = av.get("added", 0), av.get("removed", 0)
        b_add, b_rm = bv.get("added", 0), bv.get("removed", 0)
        # 只有存在实际增删时才判定（纯 modified 不算反向增删）
        if a_add + a_rm > 0 or b_add + b_rm > 0:
            checked += 1
            if a_add == b_rm and a_rm == b_add and (a_add + a_rm) > 0:
                flipped += 1
    if not checked:
        return False
    # 过半板块出现「增删互换」→ 判定为整体回弹
    return flipped > 0 and flipped >= checked * 0.6


def stat_section(sec):
    j = load(os.path.join(SNAP, sec + ".json"))
    items = (j or {}).get("items") or []
    dist = collections.defaultdict(collections.Counter)
    for it in items:
        f = it.get("fields") or {}
        own = f.get("归属") or "未知"
        t = f.get("资费类型") or "未知"
        dist[own][t] += 1
    return j, items, dict(dist)


def union_prov_dist(st, sections):
    """31 省专区并集（不含全网），按业务名去重，返回 (条数, 归属x类型分布)"""
    names = {}
    for sec in sections:
        if sec == "quanguo":
            continue
        items = st[sec][1]
        for it in items:
            n = (it.get("name") or "").strip()
            if n:
                names.setdefault(n, it)
    d = collections.defaultdict(collections.Counter)
    for it in names.values():
        f = it.get("fields") or {}
        own = f.get("归属") or "未知"
        t = f.get("资费类型") or "未知"
        d[own][t] += 1
    return len(names), dict(d)


def prov_stats_map(st, sections):
    """每省资费统计（总数 / 个人 / 政企 / 归属x类型分布），供总览页省份切换秒级联动"""
    out = {}
    for sec in sections:
        if sec == "quanguo":
            continue
        _j, items, dist = st[sec]
        personal = sum((dist.get("个人资费") or {}).values())
        gq = sum((dist.get("政企资费") or {}).values())
        out[sec] = {"total": len(items), "personal": personal, "gq": gq, "dist": dist}
    return out


def main():
    now = datetime.datetime.now(
        datetime.timezone(datetime.timedelta(hours=8))
    ).strftime("%Y-%m-%d %H:%M:%S")
    sections = all_sections()
    if not sections:
        sections = ["quanguo"]

    # 0) 先复制静态页面源码（index.html / style.css / app.js）到站点根目录
    if os.path.isdir(SITE_SRC):
        shutil.copytree(SITE_SRC, SITE, dirs_exist_ok=True)
        print("已复制静态页面源码 -> _site/")

    # 1) 复制当前快照到站点 data/
    st = {}   # section -> (json, items, dist)
    for sec in sections:
        src = os.path.join(SNAP, sec + ".json")
        if os.path.exists(src):
            shutil.copy(src, os.path.join(DATA, sec + ".json"))
        st[sec] = stat_section(sec)

    # 2) latest.json（仪表盘统计：sections 索引 + 全网/31省/各省分布）
    def_sec = DEFAULT_PROV if DEFAULT_PROV in sections else (sections[0] if sections else "quanguo")
    updated = ""
    for sec in sections:
        j = st[sec][0]
        ts = (j or {}).get("timestamp") or ""
        if ts > updated:
            updated = ts
    prov_total, prov_dist = union_prov_dist(st, sections)
    latest = {
        "updated": updated or now,
        "default": def_sec,
        "sections": [
            {
                "section": sec,
                "name": sec_name(sec),
                "total": len(st[sec][1]),
                "updated": (st[sec][0] or {}).get("timestamp") or "",
            }
            for sec in sections
        ],
        "quanguo_total": len(st.get("quanguo", (None, [], {}))[1]),
        "prov_total": prov_total,                 # 31省专区去重合计（不含全网）
        "prov_dist": prov_dist,                   # 31省去重后的归属x类型分布
        "prov_stats": prov_stats_map(st, sections),  # 每省统计，供总览页省份切换联动
        "hunan_total": len(st.get(def_sec, (None, [], {}))[1]),
        "dist": st.get("quanguo", (None, [], {}))[2],
        "def_dist": dict(st.get(def_sec, (None, [], {}))[2].get("个人资费", {})),
    }
    with open(os.path.join(DATA, "latest.json"), "w", encoding="utf-8") as f:
        json.dump(latest, f, ensure_ascii=False, indent=2)

    # 3) 变化历史：逐板块对比上次快照副本（_prev/），rec 含全部板块变更 + 字段级修改明细
    history = load(os.path.join(PREV, "history.json")) or []
    # 清理历史上因字段结构升级产生的全量误报记录（如采集字段新增"其他说明"时全量 modified）
    _pre_clean = len(history)
    history = clean_upgrade_false_records(history, st)
    if len(history) != _pre_clean:
        print(f"[清理] 剔除 {_pre_clean - len(history)} 条字段升级误报历史记录")
    rec = {"ts": now}
    has_change = False
    diff_details = {}   # sec -> {name: [{field,from,to}, ...]} 供回填旧记录
    for sec in sections:
        j, items, _dist = st[sec]
        old = load(os.path.join(PREV, sec + ".json"))
        old_items = (old or {}).get("items") if old else None
        if old_items is None:
            rec[sec] = {"note": "baseline"}
            continue
        # 字段结构升级检测：旧/新快照字段键集合不一致时重建基线，避免一次性全量 modified 误报
        if _structure_upgraded(old_items, items):
            print(f"  [升级] 板块 {sec} 字段结构变化，重建基线不计数")
            rec[sec] = {"note": "baseline"}
            continue
        added, removed, modified, modified_details, mod_before, mod_after = diff_items(old_items, items)
        if added or removed or modified:
            has_change = True
        rec[sec] = {
            "added": len(added),
            "removed": len(removed),
            "modified": len(modified),
            "added_names": [name_of(a) for a in added],
            "removed_names": [name_of(r) for r in removed],
            "modified_names": [name_of(m) for m in modified],
        }
        if added:
            rec[sec]["added_details"] = {
                name_of(a): (a.get("fields") or {}) for a in added
            }
        if removed:
            rec[sec]["removed_details"] = {
                name_of(r): (r.get("fields") or {}) for r in removed
            }
        if modified_details:
            diff_details[sec] = modified_details
            # 字段级修改明细量可能极大（一次大调整数百条），完整保留会让 history 膨胀；
            # names 已全量展示，details 保留合理上限即可（默认 500，可用环境变量覆盖）。
            MDET_LIMIT = int(os.getenv("MODIFIED_DETAILS_LIMIT", "500"))
            rec[sec]["modified_details"] = dict(list(modified_details.items())[:MDET_LIMIT])
            # 修改前后完整字段快照（供前端并排对比），同样限量防止膨胀
            MSNAP_LIMIT = int(os.getenv("MODIFIED_SNAPSHOT_LIMIT", "60"))
            rec[sec]["modified_before"] = dict(list(mod_before.items())[:MSNAP_LIMIT])
            rec[sec]["modified_after"] = dict(list(mod_after.items())[:MSNAP_LIMIT])

    # 回填历史记录中缺失的字段级修改明细（当日志只有名称列表、无 detail 时，用本次 diff 补齐）
    for rec0 in history:
        for sec in sections:
            d = rec0.get(sec)
            if not isinstance(d, dict) or d.get("note") == "baseline":
                continue
            if d.get("modified") and not d.get("modified_details"):
                md = diff_details.get(sec) or {}
                fill = {n: md[n] for n in (d.get("modified_names") or []) if n in md}
                if fill:
                    d["modified_details"] = fill

    # 等效变更去重：本次变更与上一条完全相同（prev 基线未更新时）不重复记录
    if has_change and history and is_reverse_change(history[-1], rec):
        # 与上一条完全反向 → 基线回弹产生的假变化，丢弃且不更新历史
        print("  !! 检测到与上一条反向的抖动变化（基线回弹），本轮不记录")
        has_change = False

    if has_change and not (history and same_change(history[-1], rec)):
        history.append(rec)
        history = history[-60:]
    with open(os.path.join(DATA, "history.json"), "w", encoding="utf-8") as f:
        json.dump(history, f, ensure_ascii=False, indent=2)

    # 4) 保存本次快照副本到站点 prev/（下次 diff 用）
    for sec in sections:
        src = os.path.join(SNAP, sec + ".json")
        if os.path.exists(src):
            shutil.copy(src, os.path.join(PREV_OUT, sec + ".json"))
    shutil.copy(os.path.join(DATA, "history.json"), os.path.join(PREV_OUT, "history.json"))

    print("site built:", json.dumps({
        "sections": [sec_name(s) for s in sections],
        "updated": latest["updated"],
        "quanguo_total": latest["quanguo_total"],
        "prov_total": latest["prov_total"],
        "default": sec_name(def_sec),
        "default_total": latest["hunan_total"],
        "history_records": len(history),
        "this_change": has_change,
    }, ensure_ascii=False))


if __name__ == "__main__":
    main()
