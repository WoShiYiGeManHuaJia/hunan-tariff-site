# 快照模块：存储历史数据并对比变化
import json
import os
import time

SNAPSHOT_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "snapshots")
os.makedirs(SNAPSHOT_DIR, exist_ok=True)


def _snapshot_path(section: str) -> str:
    return os.path.join(SNAPSHOT_DIR, f"{section}.json")


def load_snapshot(section: str):
    """读取上次抓取结果，不存在返回 None"""
    path = _snapshot_path(section)
    if not os.path.exists(path):
        return None
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return None


def save_snapshot(section: str, data: dict):
    """保存本次抓取结果。

    紧凑格式（无缩进/无多余空格）：快照体量大（33 省约 60MB），
    indent=2 会让工作区再膨胀约 16%，拖慢 Actions 每次 checkout。
    原子写入：先写临时文件再 os.replace，避免进程中途被 kill 时
    留下半个 JSON，导致下一轮基线损坏、全量误报。
    """
    path = _snapshot_path(section)
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, separators=(",", ":"))
    os.replace(tmp, path)


def _parse_name(item) -> str:
    """从资费条目里解析业务名称。新版 item 为 dict{'name':...}，兼容旧版字符串。"""
    if isinstance(item, dict):
        return (item.get("name") or "").strip()
    if isinstance(item, str):
        for sep in ("：", ":"):
            if sep in item:
                return item.split(sep, 1)[0].strip()
        return item.strip()
    return ""


def _same_structure(old_items: list, new_items: list) -> bool:
    """新旧快照数据格式是否一致（都是结构化 dict 或都是字符串）。"""
    def is_dict(l):
        return bool(l) and isinstance(l[0], dict)
    return is_dict(old_items) == is_dict(new_items)


def _field_keys(items: list):
    """取快照条目统一的 fields 字段键集合；无结构字段时返回 None。"""
    for it in (items or []):
        if isinstance(it, dict):
            f = it.get("fields")
            if isinstance(f, dict):
                return tuple(sorted(f.keys()))
    return None


def _structure_upgraded(old_items: list, new_items: list) -> bool:
    """新旧快照字段结构是否不一致（字段集新增/删减，如新增采集字段）。"""
    ok, nk = _field_keys(old_items), _field_keys(new_items)
    return ok is not None and nk is not None and ok != nk


def _norm(v):
    if v is None:
        return ""
    if isinstance(v, (dict, list)):
        return json.dumps(v, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return str(v).strip()


def _mobile_key(item):
    """移动业务身份键：优先稳定业务编号，否则名称+分类；绝不包含价格/字段内容。"""
    if not isinstance(item, dict):
        return ("text", _parse_name(item))
    fields = item.get("fields") if isinstance(item.get("fields"), dict) else {}
    for k in ("productCode", "goodsCode", "businessCode", "code", "方案编号"):
        v = fields.get(k) or item.get(k)
        if v not in (None, ""):
            return ("code", k, _norm(v))
    return ("name", _norm(item.get("name")), _norm(fields.get("资费类型")), _norm(fields.get("归属")))


def _mobile_fields(item):
    if isinstance(item, dict):
        f = item.get("fields")
        if isinstance(f, dict):
            return {k: v for k, v in f.items()}
        return {k: v for k, v in item.items() if k not in ("id", "name")}
    return {"name": item}


def _changed(old, new):
    a, b = _mobile_fields(old), _mobile_fields(new)
    return {k: (a.get(k), b.get(k)) for k in sorted(set(a) | set(b)) if _norm(a.get(k)) != _norm(b.get(k))}


def diff(old_items: list, new_items: list) -> dict:
    """重复安全的移动 Diff：同身份一对一匹配，避免同名条目互相覆盖。"""
    old, new = list(old_items or []), list(new_items or [])
    used_old, used_new = set(), set()
    pairs = []

    def groups(items, key_fn, used):
        out = {}
        for i, x in enumerate(items):
            if i not in used:
                out.setdefault(key_fn(x), []).append(i)
        return out

    # 先精确 ID；只有唯一 ID 才配对。
    om, nm = groups(old, lambda x: _norm(x.get("id")) if isinstance(x, dict) else "", used_old), groups(new, lambda x: _norm(x.get("id")) if isinstance(x, dict) else "", used_new)
    for k in set(om) & set(nm):
        if k and len(om[k]) == len(nm[k]) == 1:
            oi, ni = om[k][0], nm[k][0]; used_old.add(oi); used_new.add(ni); pairs.append((oi, ni))

    # 再稳定业务键；多条同身份时一对一，不覆盖。
    om, nm = groups(old, _mobile_key, used_old), groups(new, _mobile_key, used_new)
    for k in set(om) & set(nm):
        for oi, ni in zip(om[k], nm[k]):
            used_old.add(oi); used_new.add(ni); pairs.append((oi, ni))

    added = [new[i] for i in range(len(new)) if i not in used_new]
    removed = [old[i] for i in range(len(old)) if i not in used_old]
    modified = []
    for oi, ni in pairs:
        changed = _changed(old[oi], new[ni])
        if changed:
            modified.append({"name": _parse_name(new[ni]), "old": _mobile_fields(old[oi]), "new": _mobile_fields(new[ni]), "changed": changed})
    return {"added": added, "removed": removed, "modified": modified}

def check_section(section: str, new_data: dict):
    """对比某板块变化，返回变化报告 dict 或 None。
    若旧快照格式与新数据不兼容（如升级前的字符串快照），先重建基线不通知。"""
    old = load_snapshot(section)
    if old is not None and not _same_structure(old.get("items", []), new_data.get("items", [])):
        print(f"  [基线] 板块 {section} 快照格式已升级，重建基线不通知")
        save_snapshot(section, new_data)
        return None
    # 字段结构升级（如新增采集字段）同样重建基线，避免一次性全量误报"修改"
    if old is not None and _structure_upgraded(old.get("items", []), new_data.get("items", [])):
        print(f"  [基线] 板块 {section} 快照字段结构升级，重建基线不通知")
        save_snapshot(section, new_data)
        return None

    d = diff(old.get("items") if old else [], new_data.get("items", []))
    has_change = bool(d["added"] or d["removed"] or d["modified"])
    report = {
        "section": section,
        "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
        "added": d["added"],
        "removed": d["removed"],
        "modified": d["modified"],
        "keep_old": None if not old else old.get("timestamp"),
    }
    save_snapshot(section, new_data)
    return report if has_change else None
