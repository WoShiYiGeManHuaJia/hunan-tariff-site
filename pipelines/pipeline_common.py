# -*- coding: utf-8 -*-
"""四管线（移动/联通/电信/广电）公共工具。

抽出来的原因：四家运营商都会在官方资费池里混入「测试数据 / 内部验证 / 废弃占位」
的业务，若不统一过滤，这些脏数据会被当成真实变更写进 history 并推送到钉钉。
此前电信站已出现官方测试数据落库（见 history 中的「【测试】…请忽略」）。
"""
import re

# 标题命中任一关键词即判定为测试/作废数据
_TEST_PAT = re.compile(
    r"(测试|试用|验证数据|请勿|请忽略|勿参考|不代表真实|废弃|作废|"
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
HIST_DETAIL_LIMIT = int(__import__("os").getenv("HIST_DETAIL_LIMIT") or "20")
HIST_NAME_LIMIT = int(__import__("os").getenv("HIST_NAME_LIMIT") or "30")
# *_list 是联通/广电保存的「精简详情对象数组」，每个元素含 serviceContent 等长文本。
# 一个板块曾存到 1164 个元素（约 0.4MB），是 history 膨胀的真正元凶
# —— 首版只限制了 _names/_details，漏掉 _list 导致压缩几乎无效（42MB→26MB）。
HIST_LIST_LIMIT = int(__import__("os").getenv("HIST_LIST_LIMIT") or "12")


_DETAIL_TEXT_LIMIT = int(__import__("os").getenv("HIST_DETAIL_TEXT_LIMIT") or "200")


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
import re as _re2

_SKIP_FIELDS = {"timestamp", "responseContent", "data"}


def _norm_txt(v):
    x = "" if v is None else str(v)
    x = _re2.sub(r"<br\s*/?>", " ", x, flags=_re2.I)
    x = _re2.sub(r"</?p[^>]*>", " ", x, flags=_re2.I)
    x = _re2.sub(r"<[^>]*>", "", x)
    x = _re2.sub(r"&(?:nbsp|amp|lt|gt|quot|#39);", " ", x, flags=_re2.I)
    return _re2.sub(r"\s+", " ", x).strip()


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
import os as _os

# 用 `or` 而非 getenv 默认值：前者对「变量被设为空串」同样生效
# （workflow 里 ${{ vars.X }} 未配置时展开为空串，会把默认值顶掉）
NOISE_RATIO = float(_os.getenv("NOISE_RATIO") or "0.3")     # 变化率阈值 30%
NOISE_MIN_ABS = int(__import__("os").getenv("NOISE_MIN_ABS") or "50")    # 绝对条数门槛（小额变化不误伤）


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
