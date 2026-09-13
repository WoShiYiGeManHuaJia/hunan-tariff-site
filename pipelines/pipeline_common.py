# -*- coding: utf-8 -*-
"""四管线（移动/联通/电信/广电）公共工具。

抽出来的原因：四家运营商都会在官方资费池里混入「测试数据 / 内部验证 / 废弃占位」
的业务，若不统一过滤，这些脏数据会被当成真实变更写进 history 并推送到钉钉。
此前电信站已出现官方测试数据落库（见 history 中的「【测试】…请忽略」）。
"""
import os
import re
import json

# 标题命中任一关键词即判定为测试/作废数据。
#
# ★ 不要把「试用」放进过滤词：全量扫描 44774 条移动业务，命中过滤词的 27 条里
#   只有 1 条是真测试数据（福建「测试-办59元套餐…」），其余 26 条全是真实在售
#   业务 —— 河南「众享阅读产品试用1个月」「高考王者尊享版试用2个月」等 24 条、
#   湖南「校讯通.免费试用」、山东「Token试用套餐」。
#   误伤率 96%，一旦给移动管线接上过滤，第一轮就会报 26 条假下架。
#   同理不纳入「体验」（如「体验版」「免费体验」在运营商业务中同样是正式资费）。
_TEST_PAT = re.compile(
    r"(测试|验证数据|请勿|请忽略|勿参考|不代表真实|废弃|作废|"
    r"test|demo|样例|示例|内部专用|压测|联调)",
    re.IGNORECASE,
)

# 明确的方括号包裹前缀，如「【测试】xxx」
_BRACKET_PAT = re.compile(r"^【[^】]{0,10}(测试|验证|示例|废弃|作废)[^】]{0,10}】")


def is_test_item(title: str) -> bool:
    """判断一条资费是否为测试/作废数据（仅看标题，避免误伤真实业务）。"""
    t = (title or "").strip()
    if not t:
        return False
    if _BRACKET_PAT.match(t):
        return True
    return bool(_TEST_PAT.search(t))


def filter_test_items(items: list, verbose: bool = True) -> list:
    """剔除测试/作废条目。返回过滤后的新列表（不改动原列表）。"""
    if not items:
        return items
    kept, dropped = [], []
    for x in items:
        title = x.get("title") or x.get("name") or ""
        if is_test_item(title):
            dropped.append(title)
        else:
            kept.append(x)
    if dropped and verbose:
        print("  [过滤] 剔除测试/作废数据 %d 条：%s" % (
            len(dropped), "、".join(dropped[:3]) + ("…" if len(dropped) > 3 else "")))
    return kept


# ── 历史记录瘦身 ──
# 单条 entry 最多保留多少条变化名称/详情明细。
# 一次接口大变动可能产生数百个变更，全量塞进 history 会让文件膨胀到几十 MB
# （联通 history.json 曾达 42MB，前端需一次性全量下载）。
HIST_DETAIL_LIMIT = int(os.getenv("HIST_DETAIL_LIMIT") or "20")
HIST_NAME_LIMIT = int(os.getenv("HIST_NAME_LIMIT") or "30")
# *_list 是联通/广电保存的「精简详情对象数组」，每个元素含 serviceContent 等长文本。
# 一个板块曾存到 1164 个元素（约 0.4MB），是 history 膨胀的真正元凶
# —— 首版只限制了 _names/_details，漏掉 _list 导致压缩几乎无效（42MB→26MB）。
HIST_LIST_LIMIT = int(os.getenv("HIST_LIST_LIMIT") or "12")


_DETAIL_TEXT_LIMIT = int(os.getenv("HIST_DETAIL_TEXT_LIMIT") or "200")


def _clip_detail(o):
    """截断详情对象里的长文本（serviceContent 等可长达数百字，
    20 条 × 长文本 是历史文件的主要体积来源）。"""
    if not isinstance(o, dict):
        return o
    out = {}
    for k, v in o.items():
        if isinstance(v, str) and len(v) > _DETAIL_TEXT_LIMIT:
            out[k] = v[:_DETAIL_TEXT_LIMIT] + "…"
        else:
            out[k] = v
    return out


def _slim_brief(o):
    """压缩 _list 里的单个精简详情对象：长文本字段截断。

    serviceContent 原存 200 字，一个板块上千条时能撑到 0.4MB。
    历史页弹窗展示 100 字足够判断业务内容，超长部分可去资费列表看。
    """
    if not isinstance(o, dict):
        return o
    out = dict(o)
    for k in ("serviceContent", "extraFees", "otherNotes", "useScope", "validPeriod"):
        v = out.get(k)
        if isinstance(v, str) and len(v) > 100:
            out[k] = v[:100] + "…"
    return out


def _slim_block(d: dict) -> dict:
    """压缩单个板块块（{"added":n,"added_names":[...],"added_details":{...}}）。"""
    out = {}
    trunc = {}
    for k, v in d.items():
        if k.endswith("_names") and isinstance(v, list) and len(v) > HIST_NAME_LIMIT:
            out[k] = v[:HIST_NAME_LIMIT]
            trunc[k] = len(v)
        elif k.endswith("_details") and isinstance(v, dict):
            keys = list(v.keys())[:HIST_DETAIL_LIMIT]
            out[k] = {kk: _clip_detail(v[kk]) for kk in keys}
            if len(v) > HIST_DETAIL_LIMIT:
                trunc[k] = len(v)
        elif k.endswith("_list") and isinstance(v, list):
            kept = v[:HIST_LIST_LIMIT]
            out[k] = [_slim_brief(x) for x in kept]
            if len(v) > HIST_LIST_LIMIT:
                trunc[k] = len(v)
        else:
            out[k] = v
    if trunc:
        out["_trunc"] = trunc
    return out


def slim_change(change: dict) -> dict:
    """压缩一条历史记录。

    entry 结构是 {"ts":..., "<板块>": {"added":n, "added_names":[...],
    "added_details":{...}}} —— 板块块嵌在第二层，必须递归下去才能裁到，
    只遍历顶层 key 是裁不动的（曾因此导致瘦身完全无效）。
    """
    if not isinstance(change, dict):
        return change
    # ★ 传入的本身就是板块块（管线 diff_scope 直接返回的变化记录，
    #   顶层就有 added/removed/modified），此前漏判导致新记录完全不压缩
    #   （联通 history 5.49MB → 13.94MB）
    if any(x in change for x in ("added", "removed", "modified")):
        return _slim_block(change)
    out = {}
    for k, v in change.items():
        # 板块块：含 added/removed/modified 计数字段则为变化记录
        if isinstance(v, dict) and any(x in v for x in ("added", "removed", "modified")):
            out[k] = _slim_block(v)
        else:
            out[k] = v
    return out


# ── 联通/电信/广电：字段级修改明细 ──
# 这三家的 history 只存 modified_names / modified_list（精简对象），
# 没有 {field, from, to}，前端也就无法做「修改前后」对比，只能弹当前配置。
_SKIP_FIELDS = {"timestamp", "responseContent", "data"}


def _norm_txt(v):
    x = "" if v is None else str(v)
    x = re.sub(r"<br\s*/?>", " ", x, flags=re.I)
    x = re.sub(r"</?p[^>]*>", " ", x, flags=re.I)
    x = re.sub(r"<[^>]*>", "", x)
    x = re.sub(r"&(?:nbsp|amp|lt|gt|quot|#39);", " ", x, flags=re.I)
    return re.sub(r"\s+", " ", x).strip()


def _item_id(it):
    """返回可用于精确匹配的业务 ID；空 ID 不参与 ID 匹配。"""
    v = it.get("id") if isinstance(it, dict) else None
    return str(v).strip() if v not in (None, "") else ""


def stable_business_key(it):
    """返回用于跨轮次/跨板块匹配的稳定业务身份。

    注意：价格、流量、权益、reportNo 等可能变化的字段绝不进入主身份键。
    reportNo 只在 diff_items 中作为“唯一且同分类”的辅助候选，避免编号变更
    或多个业务共用编号时把一个业务误判成新增+下架。
    """
    d = it.get("detail") if isinstance(it.get("detail"), dict) else {}
    # 比标题更可靠的产品实体编号；不要把 reportNo 当作唯一身份。
    for k in ("productCode", "goodsCode", "businessCode", "code"):
        v = d.get(k) or it.get(k)
        if v not in (None, ""):
            return json.dumps(["code", k, _norm_txt(v)], ensure_ascii=False, separators=(",", ":"))
    return json.dumps([
        _norm_txt(it.get("title") or it.get("name") or ""),
        _norm_txt(it.get("firstLevel", "")),
        _norm_txt(it.get("secondLevel", "")),
    ], ensure_ascii=False, separators=(",", ":"))


def _aux_report_key(it):
    """reportNo 辅助匹配键：只有在同一编号+分类唯一时才使用。"""
    d = it.get("detail") if isinstance(it.get("detail"), dict) else {}
    v = d.get("reportNo") or it.get("reportNo")
    if v in (None, ""):
        return ""
    return json.dumps([_norm_txt(v), _norm_txt(it.get("firstLevel", "")),
                       _norm_txt(it.get("secondLevel", ""))], ensure_ascii=False, separators=(",", ":"))


def diff_items(prev_items, cur_items, detail_limit=60):
    """统一四家运营商 Diff：ID → 强稳定身份 → 唯一 reportNo 辅助匹配。

    同一业务即使价格/流量/权益变化，也会落到 modified；官方 ID 漂移也不会
    制造假新增/下架。所有候选匹配都要求“一对一”，避免重复业务被字典覆盖。
    """
    old, new = list(prev_items or []), list(cur_items or [])
    used_old, used_new, pairs = set(), set(), []

    def unique_map(items, key_fn, allowed):
        m = {}
        for i, x in enumerate(items):
            if i not in allowed:
                k = key_fn(x)
                if k:
                    m.setdefault(k, []).append(i)
        return m

    # 1) 非空 ID 精确匹配；重复 ID 不强行匹配，避免覆盖。
    om = unique_map(old, _item_id, set())
    nm = unique_map(new, _item_id, set())
    for k in set(om) & set(nm):
        if len(om[k]) == 1 and len(nm[k]) == 1:
            oi, ni = om[k][0], nm[k][0]
            used_old.add(oi); used_new.add(ni); pairs.append((oi, ni, "id"))

    # 2) 稳定业务身份匹配；同 key 多条时按出现顺序一对一配对。
    om = unique_map(old, stable_business_key, used_old)
    nm = unique_map(new, stable_business_key, used_new)
    for k in set(om) & set(nm):
        for oi, ni in zip(om[k], nm[k]):
            used_old.add(oi); used_new.add(ni); pairs.append((oi, ni, "stable"))

    # 3) reportNo 仅作最后的辅助：必须 key 唯一，防止共用编号误合并。
    om = unique_map(old, _aux_report_key, used_old)
    nm = unique_map(new, _aux_report_key, used_new)
    for k in set(om) & set(nm):
        if len(om[k]) == 1 and len(nm[k]) == 1:
            oi, ni = om[k][0], nm[k][0]
            used_old.add(oi); used_new.add(ni); pairs.append((oi, ni, "report"))

    added = [x for i, x in enumerate(new) if i not in used_new]
    removed = [x for i, x in enumerate(old) if i not in used_old]
    modified, modified_pairs = [], []
    for oi, ni, match_type in pairs:
        a, b = old[oi], new[ni]
        diffs = field_diff_items(a, b)
        if diffs:
            modified.append(b)
            modified_pairs.append((a, b, diffs, match_type))

    md = {}
    for old_it, new_it, diffs, _ in modified_pairs[:detail_limit]:
        key = new_it.get("title") or new_it.get("name") or _item_id(new_it)
        if key:
            md[key] = diffs

    raw_added = len(added)
    raw_removed = len(removed)
    return {
        "added_items": added, "removed_items": removed,
        "modified_items": modified, "modified_details": md,
        "raw_added": raw_added, "raw_removed": raw_removed,
        "matched": len(pairs),
    }

def item_fields(it):
    """把一个条目展平为 {字段名: 值}（顶层字段 + detail 内部字段）。"""
    d = it.get("detail") or {}
    out = {}
    for k in ("title", "fee", "firstLevel", "secondLevel"):
        v = it.get(k)
        if v not in (None, ""):
            out[k] = v
    for k, v in d.items():
        if k in _SKIP_FIELDS:
            continue
        out[k] = v
    return out


def field_diff_items(old, new):
    """对比两个同 id 条目，返回 [{field, from, to}, ...]（值已剥离 HTML）。"""
    of, nf = item_fields(old), item_fields(new)
    keys = list(of.keys())
    for k in nf:
        if k not in keys:
            keys.append(k)
    out = []
    for k in keys:
        a, b = _norm_txt(of.get(k)), _norm_txt(nf.get(k))
        if a != b:
            out.append({"field": k, "from": a, "to": b})
    return out


def modified_details_for(pmap, mods, limit=60):
    """为「修改」列表生成字段级对比明细 {业务名: [{field, from, to}, ...]}。"""
    res = {}
    for m in (mods or []):
        old = pmap.get(m.get("id"))
        if not old:
            continue
        diffs = field_diff_items(old, m)
        if diffs:
            res[m.get("title") or m.get("name") or m.get("id")] = diffs
        if len(res) >= limit:
            break
    return res


# ── 采样噪声护栏 ──
# 联通/广电/电信的接口用「随机子集轮换」而非严格分页（pageSize 硬限 500，
# 每次返回的是全集中的不同随机 500 条）。因此即使业务没变，两次抓取的
# 样本集合也不同 —— 上一轮采到 A、这一轮没采到就被判「下架」，反之「新增」。
# 表现为单次数千条假变化，且清空历史后下一轮照样复现。
#
# 判据：单板块 (新增+下架) / 基线总量 超过阈值 → 认定是采样抖动而非真实变动。
# 用 `or` 而非 getenv 默认值：前者对「变量被设为空串」同样生效
# （workflow 里 ${{ vars.X }} 未配置时展开为空串，会把默认值顶掉）
NOISE_RATIO = float(os.getenv("NOISE_RATIO") or "0.3")     # 变化率阈值 30%
NOISE_MIN_ABS = int(os.getenv("NOISE_MIN_ABS") or "50")    # 绝对条数门槛（小额变化不误伤）


def is_sampling_noise(sec_result, base_total):
    """判断一个板块的变化是否属于采样噪声。

    sec_result: diff_scope 产出的板块字典（含 added/removed/modified）
    base_total: 该板块基线条数
    """
    if not isinstance(sec_result, dict):
        return False
    chg = int(sec_result.get("added", 0) or 0) + int(sec_result.get("removed", 0) or 0)
    if chg < NOISE_MIN_ABS:
        return False          # 变化太少，不可能是采样抖动
    if not base_total or base_total <= 0:
        return False
    return (chg / float(base_total)) > NOISE_RATIO


def has_real_change(sec_result):
    """该板块是否有值得写入 history 的实质变化。

    add/rm/mod 全为 0 且无 note 时返回 False —— 这类「无变化」记录
    会在变化历史里堆满空行，用户看不到任何信息却要逐条翻。
    带 note / shifted 的保留：note 解释了「本轮为何没计数」，
    本身具有诊断价值。
    """
    if not isinstance(sec_result, dict):
        return False
    if sec_result.get("note") or sec_result.get("shifted"):
        return True
    return bool(sec_result.get("added") or sec_result.get("removed")
                or sec_result.get("modified"))


def mark_noise(sec_result, base_total):
    """命中噪声判据时，把板块结果改写成一句汇总，丢弃逐条明细。"""
    if not is_sampling_noise(sec_result, base_total):
        return sec_result
    a = int(sec_result.get("added", 0) or 0)
    r = int(sec_result.get("removed", 0) or 0)
    m = int(sec_result.get("modified", 0) or 0)
    return {
        "added": 0, "removed": 0, "modified": m,   # 修改基于 id 匹配，不受采样影响，保留
        "added_names": [], "removed_names": [], "modified_names": sec_result.get("modified_names", []),
        "added_details": {}, "removed_details": {},
        "modified_details": sec_result.get("modified_details", {}),
        "added_list": [], "removed_list": [], "modified_list": sec_result.get("modified_list", []),
        "note": "本轮增删 %d 条，超过基线 %.0f%%（阈值 %.0f%%），判定为接口随机采样抖动，"
                "非真实业务变动，已忽略明细" % (a + r, (a + r) / float(base_total) * 100, NOISE_RATIO * 100),
    }
