# -*- coding: utf-8 -*-
"""联通资费监控管线（可在 GitHub Actions 直接运行，路径全部相对脚本目录）

职责：抓取联通「全网 + 31 省」全量资费 → 与上一版数据 diff → 输出站点数据目录
      （{scope}.json + latest.json + _baseline.json + history.json），供 workflow 推公开仓。
设计：
- index 省份表动态从 indexData 获取，无需本地静态索引文件。
- 上一版数据由 --prev-dir 指定（workflow 中为公开仓 unicom/data 的 checkout 副本）；缺省/缺失视为首次，仅建基线、不记变化。
- 数据文件不进私有仓 git（避免仓库膨胀），仅公开仓保留当前版 + history.json 累积。
用法:
  python3 unicom_pipeline.py --prev-dir PATH --out-dir PATH [--scopes hunan,quanguo]
"""
import json, time, os, sys, urllib.request, http.cookiejar, hashlib, argparse, math

from pipeline_common import (is_sampling_noise, mark_noise, has_real_change,
                             modified_details_for, filter_test_items, slim_change, diff_items, stable_business_key)

PROG_DIR = os.path.dirname(os.path.abspath(__file__))
BASE_API = "https://m.client.10010.com/servicequerybusiness/queryTariffNew/"
HDRS = {
    "User-Agent": "Mozilla/5.0 (iPhone; CPU iPhone OS 16_0 like Mac OS X) AppleWebKit/605.1.15 Mobile/15E148 MicroMessenger/8.0.47",
    "Referer": "http://img.client.10010.com/zifeizhuanquwt/index.html",
    "Accept": "application/json, text/plain, */*",
}
_cj = http.cookiejar.CookieJar()
_op = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(_cj))

NAME = {
    "quanguo": "全网(全国)",
    "beijing": "北京", "tianjin": "天津", "hebei": "河北", "shanxi": "山西", "neimenggu": "内蒙古",
    "liaoning": "辽宁", "jilin": "吉林", "heilongjiang": "黑龙江", "shanghai": "上海", "jiangsu": "江苏",
    "zhejiang": "浙江", "anhui": "安徽", "fujian": "福建", "jiangxi": "江西", "shandong": "山东",
    "henan": "河南", "hubei": "湖北", "hunan": "湖南", "guangdong": "广东", "guangxi": "广西",
    "hainan": "海南", "chongqing": "重庆", "sichuan": "四川", "guizhou": "贵州", "yunnan": "云南",
    "xizang": "西藏", "shaanxi": "陕西", "gansu": "甘肃", "qinghai": "青海", "ningxia": "宁夏", "xinjiang": "新疆",
}
CN2CODE = {
    "北京": "beijing", "天津": "tianjin", "河北": "hebei", "山西": "shanxi", "内蒙古": "neimenggu",
    "辽宁": "liaoning", "吉林": "jilin", "黑龙江": "heilongjiang", "上海": "shanghai", "江苏": "jiangsu",
    "浙江": "zhejiang", "安徽": "anhui", "福建": "fujian", "江西": "jiangxi", "山东": "shandong",
    "河南": "henan", "湖北": "hubei", "湖南": "hunan", "广东": "guangdong", "广西": "guangxi",
    "海南": "hainan", "重庆": "chongqing", "四川": "sichuan", "贵州": "guizhou", "云南": "yunnan",
    "西藏": "xizang", "陕西": "shaanxi", "甘肃": "gansu", "青海": "qinghai", "宁夏": "ningxia", "新疆": "xinjiang",
}
FIRST_LEVELS = ["套餐", "加装包", "营销活动", "标准资费", "港澳台/国际资费", "停售套餐"]

# history.json 体积上限（字节）。超过则对存量历史做压缩自愈，
# 防止前端一次性全量下载几十 MB 导致页面在移动端打不开。
HIST_MAX_BYTES = int(os.getenv("UNICOM_HIST_MAX_BYTES") or str(3 * 1024 * 1024))


def _get(path, q=""):
    url = BASE_API + path + ("?" + q if q else "")
    req = urllib.request.Request(url, headers=HDRS)
    with _op.open(req, timeout=30) as r:
        return json.loads(r.read().decode("utf-8"))


def api(path, q="", retries=5):
    for a in range(retries):
        try:
            return _get(path, q)
        except Exception as e:
            if a == retries - 1:
                raise
            wait = 1.5 * (a + 1)
            print("[fetch] %s 失败(%s)，%.1fs 后重试(%d/%d)" % (
                path, (getattr(e, "reason", None) or str(e))[:60], wait, a + 2, retries))
            time.sleep(wait)


def build_jobs():
    """动态获取省份表：quanguo + 31 省 (provCode, cityCode, attr)。"""
    d = api("indexData")
    jobs = {"quanguo": ("", "", 1)}
    for p in (d.get("data") or {}).get("provinceList") or []:
        code = CN2CODE.get(p.get("provName"))
        if code and code not in jobs:
            jobs[code] = (p["provCode"], p["cityCode"], 2)
    return jobs


def fetch_pool(province_id, city_id, attr, pages=20, passes=12, min_rounds=60, empty_stop=30,
               page_size=500, stale_stop=60, time_budget=300, partial=None):
    """采集板块套餐池：接口为随机子集轮换(非严格分页，pageSize 硬限 500)。

    策略：循环多轮遍历 pageNum(1..pages) 反复采样，按 id 去重累积，
    直到「已跑 >=min_rounds 轮 且 连续 empty_stop 轮无新增」才收敛终止，避免
    旧逻辑单轮增量<5 就提前退出导致的只采到 500 条随机子集、基线不全的问题。

    ★ 分页失效检测（已修正误判）：
      部分板块（实测 quanguo 全网、beijing 北京）的 total 恒等于 page_size，
      说明服务端忽略了 pageNum，每轮都回同一批随机子集 —— 再跑多少轮都不会增加。
      旧逻辑会一直空转到 passes 上限，且子集随机轮换会让上轮的条目"消失"，
      被下游 diff 误判成"下架"（这正是联通变化异常的主要来源）。
      处理：连续 stale_stop 轮返回完全相同的条目集合时判定分页失效并提前终止，
      交由下游护栏兜底（不产生伪下架）。

      ★★ 2026-09-12 修复：原判据额外要求 "累计条数为 page_size 整倍数"，
      导致湖南等 7 个恰好抓到 1000(=500×2) 条的省份被误杀。
      该条件与"分页失效"无因果关系，已移除；stale_stop 20 → 60 提高误判门槛。
    """
    seen = {}
    empty_run = 0
    rounds = 0
    stale_run = 0
    prev_sig = None
    t_start = time.time()
    for _ in range(passes):
        for pn in range(1, pages + 1):
            rounds += 1
            q = ("provinceId=%s&cityId=%s&tariffAttributes=%s&firstLevel=1&secondLevel=%s"
                 "&name=&startFee=0&endFee=999999&pageNum=%d&pageSize=%d") % (
                province_id, city_id, attr, "1001", pn, page_size)
            try:
                d = api("TariffMenuDataRetrieval", q)
            except Exception as e:
                print("    round %d 失败: %s" % (rounds, (getattr(e, "reason", None) or e)))
                # 中途失败：只采到部分数据。此前直接 return seen，下游照常 diff，
                # 基线 1000 条 → 本轮 300 条会被记成「下架 700」。
                # 这里回传标记，由调用方决定跳过（不落盘、不 diff）。
                if isinstance(partial, dict):
                    partial["failed"] = True
                return seen
            lst = (d.get("data") or {}).get("tariffList") or []
            before = len(seen)
            for x in lst:
                seen[x["id"]] = {
                    "id": x["id"], "title": x.get("title", ""), "fee": x.get("fee", ""),
                    "firstLevel": x.get("firstLevel", ""), "secondLevel": x.get("secondLevel", ""),
                }
            added = len(seen) - before

            # 本轮返回条目的指纹（判断是否与上一轮完全相同 = 服务端无视 pageNum）
            sig = hash(tuple(sorted(str(x.get("id")) for x in lst)))
            if prev_sig is not None and sig == prev_sig and lst:
                stale_run += 1
            else:
                stale_run = 0
            prev_sig = sig

            if added > 0 or pn in (1, pages) or rounds % 6 == 0:
                print("    round %d page %d: ret %d cum %d (+%d)" % (rounds, pn, len(lst), len(seen), added))

            # 分页失效：连续多轮返回完全相同的条目集合（服务端忽略 pageNum）
            #
            # ★ 修复：去掉了 "len(seen) % page_size == 0" 这个条件。
            #   原判据把"恰好抓到 500/1000/1500/2000 条"误当成"分页失效"，
            #   导致湖南/广东/广西/海南/河南/湖北/四川 7 省一律卡在 1000 条；
            #   而贵州(2036)、云南(2000)、山东(1159) 因非整倍数侥幸跑满。
            #   ——"是 500 整倍数"与"分页失效"毫无因果关系，属巧合被当成规律。
            #   真正的信号只有 stale_run（连续多轮返回完全相同集合）。
            if stale_run >= stale_stop:
                print("    ⚠ 分页失效：连续 %d 轮返回完全相同条目(cum=%d)，"
                      "服务端忽略 pageNum，提前终止" % (stale_run, len(seen)))
                return seen

            if added == 0:
                empty_run += 1
                if rounds >= min_rounds and empty_run >= empty_stop:
                    print("    收敛: 已跑 %d 轮且连续 %d 轮无新增，终止" % (rounds, empty_stop))
                    return seen
            else:
                empty_run = 0

            # 时间预算兜底：单板块超时即止，避免整轮 job 跑飞
            if time_budget and (time.time() - t_start) > time_budget:
                print("    ⏱ 达到时间预算 %.0fs（已跑 %d 轮，cum=%d），终止该板块"
                      % (time_budget, rounds, len(seen)))
                return seen
            time.sleep(0.25)
    return seen


def _fmt_date(s):
    """多种官方日期格式 → YYYY-MM-DD（不支持则原样截断）"""
    if not s:
        return ""
    t = str(s).strip()
    if len(t) >= 10 and t[4] == "-":
        return t[:10]
    if len(t) >= 8 and t[:8].isdigit():
        return "%s-%s-%s" % (t[:4], t[4:6], t[6:8])
    return t[:10]


def _extract(dl, item):
    return {
        "name": dl.get("name", item.get("name", "")),
        "reportNo": dl.get("reportNo", ""),
        "codeType": dl.get("codeType", ""),
        "feesStandard": dl.get("feesStandard", ""),
        "feeUnit": dl.get("feeUnit", ""),
        "minute": dl.get("minute", ""),
        "commonData": dl.get("commonData", ""),
        "dataUnit": dl.get("dataUnit", ""),
        "sms": dl.get("sms", ""),
        "orientTraffic": dl.get("orientTraffic", ""),
        "iptv": dl.get("iptv", ""),
        "broadBand": dl.get("broadBand", ""),
        "extraFees": dl.get("otherFees", ""),
        "serviceContent": dl.get("serviceContent", ""),
        "useScope": dl.get("useScope", ""),
        "validPeriod": dl.get("validPeriod", ""),
        "onlinePeriod": dl.get("onlinePeriod", ""),
        "saleChnl": dl.get("saleChnl", ""),
        "onDate": _fmt_date(dl.get("startDate")),
        "offDate": _fmt_date(dl.get("endDate")),
        "unsubscribe": dl.get("unsubscribe", ""),
        "responsibility": dl.get("contractDuty", ""),
        "otherNotes": dl.get("otherDesc", ""),
        "firstLevelType": item.get("firstLevelType", ""),
        "secondLevelType": item.get("secondLevelType", ""),
    }


def fetch_detail(ids, batch=10):
    out = {}
    for i in range(0, len(ids), batch):
        chunk = ids[i:i + batch]
        try:
            d = api("operateData/" + "_".join(chunk))
        except Exception:
            for cid in chunk:
                try:
                    d2 = api("operateData/" + cid)
                    data = d2.get("data") or {}
                    dlist = data.get("dataList") or (data.get("detailList") if isinstance(data.get("detailList"), list) else [])
                    for item in dlist:
                        if isinstance(item, dict):
                            dl = (item.get("detailsList") or [{}])[0] or {}
                            out[cid] = _extract(dl, item)
                except Exception:
                    pass
                time.sleep(0.3)
            continue
        data = d.get("data") or {}
        dlist = data.get("dataList") or (data.get("detailList") if isinstance(data.get("detailList"), list) else [])
        for idx, item in enumerate(dlist):
            if not isinstance(item, dict):
                continue
            dl = (item.get("detailsList") or [{}])[0] or {}
            key = chunk[idx] if idx < len(chunk) else (item.get("id") or item.get("reportNo") or item.get("name"))
            out[key] = _extract(dl, item)
        time.sleep(0.3)
    return out


def build_scope(scope, province_id, city_id, attr):
    _partial = {}
    pool = fetch_pool(province_id, city_id, attr, partial=_partial)
    ids = list(pool.keys())
    print("  scope %s 列表共 %d 条，抓明细..." % (scope, len(ids)))
    detail = fetch_detail(ids)
    print("  明细 %d 条" % len(detail))
    for k in pool:
        pool[k]["detail"] = detail.get(k, {})
        it = pool[k]
        if it["detail"]:
            it["fee"] = it["detail"].get("feesStandard", "") or it["fee"]
    items = list(pool.values())
    # 剔除官方混入的测试/作废业务：留着会被 diff 判成真实上下架并推送
    items = filter_test_items(items)
    return {"scope": scope, "items": items, "partial": bool(_partial.get("failed"))}


def digest_item(it):
    return json.dumps([it.get("id"), it.get("title"), it.get("fee"), it.get("firstLevel")], ensure_ascii=False)


def digest_stable(it):
    """跨板块业务身份；与公共 Diff 使用同一套键，价格变化不会造成身份变化。"""
    return stable_business_key(it)


def _brief(it):
    """历史页弹窗展示用的配置快照。

    此前只固定取 13 个字段且 serviceContent 截断 200 字，弹窗"只有几行字"
    看不懂。现改为保存 detail 全量字段（长文本放宽到 600 字），
    前端 briefTable 会按 PLAN_LABELS 翻译并跳过空值/内部字段。
    """
    d = it.get("detail") or {}
    out = {"title": it.get("title", ""), "fee": it.get("fee", ""),
           "firstLevel": it.get("firstLevel", ""), "secondLevel": it.get("secondLevel", "")}
    for k, v in d.items():
        if k in ("timestamp", "responseContent", "data"):
            continue
        if isinstance(v, str) and len(v) > 600:
            v = v[:600] + "…"
        out[k] = v
    return out

def _title_key(it):
    return it.get("title", "") or it.get("name", "")


def field_snapshot(it):
    """把一条资费条目转为可读字段快照（新增/下架详情弹窗用，对齐移动站 added/removed_details 结构）"""
    d = it.get("detail") or {}
    snap = {}
    for k in ("title", "fee", "firstLevel", "secondLevel"):
        v = it.get(k, "")
        v = "" if v is None else v
        if v != "":
            snap[k] = v
    for k in ("feesStandard", "feeUnit", "minute", "commonData", "dataUnit", "orientTraffic",
              "validPeriod", "saleChnl", "serviceContent", "codeType", "reportNo", "extraFees",
              "useScope", "broadBand", "sms", "onlinePeriod",
              "onDate", "offDate"):   # 上下线日期：前端据此识别采样轮换造成的伪新增/伪下架
        v = d.get(k, "")
        v = "" if v is None else v
        if v != "" and v != "0":
            snap[k] = v
    return snap


def _item_date(it, key):
    d = it.get("detail") or {}
    v = d.get(key) or it.get(key) or ""
    return str(v)[:10]


def filter_sampling_fakes(added, removed, now, grace_days=30):
    """剔除接口随机采样造成的伪新增 / 伪下架。

    联通接口 pageSize 有限，服务端每轮返回的是全量里的随机子集，于是：
      · 上轮没采到、这轮采到 → 被记成"新增"，但这些业务 onDate 往往是几年前
      · 这轮没采到         → 被记成"下架"，但其 offDate 还在未来（根本没下架）
    判据（用上下线日期识破，不依赖采样运气）：
      · 伪新增：onDate 早于本轮 grace_days 天以上 → 实为往期已上线、本轮补录
      · 伪下架：offDate 晚于本轮                 → 仍在架，只是本轮没采到
    """
    import datetime as _dt
    now_d = str(now)[:10]
    try:
        cut = (_dt.date(*map(int, now_d.split("-"))) - _dt.timedelta(days=grace_days)).isoformat()
    except Exception:
        cut = now_d
    real_a, real_r, fa, fr = [], [], 0, 0
    for x in added or []:
        on = _item_date(x, "onDate")
        if len(on) == 10 and on[:4].isdigit() and on < cut:
            fa += 1
        else:
            real_a.append(x)
    for x in removed or []:
        off = _item_date(x, "offDate")
        if len(off) == 10 and off[:4].isdigit() and off > now_d:
            fr += 1
        else:
            real_r.append(x)
    return real_a, real_r, {"fake_added": fa, "fake_removed": fr}


def diff_scope(prev, cur):
    r = diff_items(prev.get("items") or [], cur.get("items") or [], detail_limit=60)
    added, removed, modified = r["added_items"], r["removed_items"], r["modified_items"]
    # 注：原 shifted 分支（total_n>0 and raw_n/total_n>0.5 and not added and not removed...）
    # 是永不可达的死代码 —— raw_added=len(added)，故 not added/removed 成立时 raw_n 必为 0，
    # 0>0.5 恒假。ID 漂移检测实际从未生效，已移除；真正防漂移由 stable_business_key 兜底。
    return {"added": len(added), "removed": len(removed), "modified": len(modified),
            "added_names": [x.get("title", "") for x in added][:20],
            "removed_names": [x.get("title", "") for x in removed][:20],
            "modified_names": [x.get("title", "") for x in modified][:20],
            "modified_details": r["modified_details"],
            "added_details": {(x.get("title","") or x.get("name","")): field_snapshot(x) for x in added},
            "removed_details": {(x.get("title","") or x.get("name","")): field_snapshot(x) for x in removed},
            "added_list": [_brief(x) for x in added[:24]],
            "removed_list": [_brief(x) for x in removed[:24]],
            "modified_list": [_brief(x) for x in modified[:24]]}


def load(path):
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def save(path, obj):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(obj, f, ensure_ascii=False, separators=(",", ":"))


# ═══════════════ 累积池（采样噪声根治）═══════════════
# 联通接口 pageSize 硬限 500，服务端按随机子集轮换返回，单轮永远采不全。
# 若直接把「上一轮采到的」当完整基线做 diff，于是：
#   · 上轮采得少、本轮采得多 → 差额全记成「新增」
#   · 上轮采到、本轮没采到   → 全记成「下架」
# 实测：全网真实约 1000 条，history 却累计「新增 6148 条」（虚高 6 倍）；
# 且相隔 12 分钟的两轮输出完全相同的新增数 —— 同一批存量业务
# 因基线反复被残缺数据污染而被重复计入新增。
#
# 根治办法是维护「累积池」：所有见过的业务按稳定指纹去重留存，
# 只有「从未见过」才算新增，「连续多轮消失」才算下架。
# 展示数据（{板块}.json）改由池构建，页面数字单调收敛、不再忽大忽小。
#
# ★ 不要用「噪声判据 + 归零」替代本方案：仿真显示真实新增5/下架3 与
#   采样噪声 251 条混合时，变化率 50% 超过阈值会把真实变化一并吞掉（漏报）。
#   累积池能区分「从未见过」与「本轮没采到」，阈值判据不能。
POOL_FILE = "_pool.json"
# 连续多少轮没再采到才认定真下架。
# 固定阈值行不通：误判率 = (1-采样率)^阈值，采样越稀薄越需要多等几轮。
#   · 采样 40% 时阈值 4 就有 13% 概率误判（实测每轮假下架 52 条）
#   · 采样 10% 时阈值 4 误判率高达 66%
# 故改为按本轮采样率自适应：误判概率压到 1% 以下所需的轮数。
MISS_CONFIRM_FIXED = os.getenv("UNICOM_MISS_CONFIRM")
# 预热期阈值：池未收敛前不记变化。
# 联通接口 pageSize 硬限 500，单轮只返回随机子集，冷启动那一轮只能采到一小部分。
# 第二轮采到「池里没有的」会全部算成新增 —— 实测湖南冷启动 383 条 → 第二轮 1229 条，
# 凭空多出「新增 846」，其实都是早就在售的老业务，只是第一轮没被采到。
# 因此池需要多轮补齐；在增长收敛前，added/removed 一律不记为变化。
# 统计口径：用命中率估采样率 p，推算「本轮本该补齐几条」，超出部分才算真新增。
# 单靠「增长率」不够 —— 池按指数逼近全集，增长率永远 >0（实测收敛后仍有 1~5%），
# 按增长率设阈值会在池仅 88% 时就误判收敛，继续报 59/22/25 这类假新增。
WARMUP_FILL = float(os.getenv("UNICOM_WARMUP_FILL") or "0.90")  # 池完整度达此比例才算收敛
FILL_MARGIN = float(os.getenv("UNICOM_FILL_MARGIN") or "1.5")   # 补齐量容差倍数
TOTAL_EMA = float(os.getenv("UNICOM_TOTAL_EMA") or "0.7")       # 全集估计平滑系数

# ★ 收敛判定（彻底修复「永远无变化」）：不能只看完整度，必须看池是否已停止增长。
#   池按几何级数逼近全集，完整度永远 <100%、增长率永远 >0；
#   只有「连续多轮几乎不再有新条目进来」才说明残余未采到的业务已耗尽，
#   此后"新见到"即为真新增。
# 0.003 实测过严：随机采样偶尔捞到一批老业务，单轮增长就冲到 0.4%~5%，
#   连续计数被反复清零，plateau 永远攒不够，只能等 FORCE_ROUNDS 兜底。
#   放宽到 1%：湖南（池 1412 / 全集估 1418，仅差 6 条）单轮最多涨 0.42%，
#   可稳定达标；而广东/全网仍以 5%/轮增长，自然被挡在门外继续建池，
#   不会提前收敛去报假新增 —— 正好实现「谁满了谁先报」。
PLATEAU_GROW = float(os.getenv("UNICOM_PLATEAU_GROW") or "0.01")      # 单轮增长率阈值
PLATEAU_NEED = int(os.getenv("UNICOM_PLATEAU_NEED") or "3")         # 需连续几轮
MIN_CONVERGE_ROUNDS = int(os.getenv("UNICOM_MIN_ROUNDS") or "4")
FORCE_ROUNDS = int(os.getenv("UNICOM_FORCE_ROUNDS") or "10")        # 兜底：绝不无限沉默

MISS_CONFIRM_MIN = int(os.getenv("UNICOM_MISS_CONFIRM_MIN") or "6")
MISS_CONFIRM_MAX = int(os.getenv("UNICOM_MISS_CONFIRM_MAX") or "40")
# 可接受的误判概率（把存量业务误判成已下架）。
# ★ 2026-09-14 加严 0.01 → 0.0001：
#   采样率 65% 时，容忍 1% 误判只需连续 5 轮未采到，但 0.35^5≈0.5%，
#   2000 条里就有约 10 条被误删；下一轮重新采到又被当成"新增"报出来，
#   形成「假下架 → 假新增」循环（实测每轮凭空多出 5~12 条）。
#   按 0.0001 反推需连续约 9 轮未采到，误判降到 0.2 条以下，循环消除。
MISS_FP_TARGET = float(os.getenv("UNICOM_MISS_FP") or "0.0001")
# 阈值平滑系数（越大越迟钝：0.8 表示新采样率只占 20% 权重）
NEED_EMA = float(os.getenv("UNICOM_NEED_EMA") or "0.8")
# 池体积上限（条），超限时按 miss 从大到小淘汰，防止无限膨胀
POOL_MAX = int(os.getenv("UNICOM_POOL_MAX") or "40000")


def _miss_need(hit_n, pool_n):
    """按本轮真实采样率推算「确认下架」所需的连续未出现轮数。

    某业务本轮没被采到的概率 = 1 - p（p 为采样率），连续 k 轮都采不到
    才判下架，误判概率就是 (1-p)^k。反解出让误判低于 MISS_FP_TARGET 的 k：
        k = ln(target) / ln(1 - p)

    ★ 采样率必须按「命中池内已见业务的条数 / 池内总条数」来算，
      不能用「本轮总条数 / 池内条数」：池尚未收敛时本轮条数可能反而
      大于池内已有量（会算出 p>1），导致阈值被压到最小、误判下架激增。
    """
    if MISS_CONFIRM_FIXED:
        return max(1, int(MISS_CONFIRM_FIXED))
    if pool_n <= 0 or hit_n <= 0:
        return MISS_CONFIRM_MIN
    p = min(0.95, max(0.01, float(hit_n) / float(pool_n)))
    try:
        k = math.log(MISS_FP_TARGET) / math.log(1.0 - p)
    except Exception:
        return MISS_CONFIRM_MIN
    return max(MISS_CONFIRM_MIN, min(MISS_CONFIRM_MAX, int(k) + 1))


def load_pool(datadir):
    """读取累积池。返回 (pool, meta)，meta 存每个板块的平滑阈值等状态。"""
    fp = os.path.join(datadir, POOL_FILE)
    # 首次运行时池文件不存在，直接 open 会抛 FileNotFoundError 并把整轮干掉
    if not os.path.exists(fp):
        return {}, {}
    try:
        d = load(fp)
    except Exception:
        return {}, {}
    if not isinstance(d, dict):
        return {}, {}
    return (d.get("pool") or {}), (d.get("meta") or {})


def save_pool(datadir, pool, meta=None):
    # 淘汰：miss 越大越优先清理（最久没见过的先走）
    for sc in list(pool.keys()):
        recs = pool[sc]
        if not isinstance(recs, dict) or len(recs) <= POOL_MAX:
            continue
        over = len(recs) - POOL_MAX
        for fp, _ in sorted(recs.items(),
                            key=lambda kv: -(kv[1].get("miss") or 0))[:over]:
            recs.pop(fp, None)
    save(os.path.join(datadir, POOL_FILE), {"pool": pool, "meta": meta or {}})


def pool_update(scope, cur_items, pool, meta=None):
    """用本轮采集结果更新累积池。

    返回 (added_items, removed_items, is_coldstart, is_warmup)
      added       —— 首次见到的业务（真新增候选）
      removed     —— 连续 MISS_CONFIRM 轮未再采到（确认真下架）
      is_coldstart—— 本板块首次建池，本轮只建基线、不记任何变化
      is_warmup   —— 池仍在补齐（增长率未收敛），本轮同样不记变化
    """
    if meta is None:
        meta = {}
    if scope not in pool:
        # 冷启动：本轮条目全部入池，不产生任何变化记录
        pool[scope] = {}
        for x in cur_items:
            pool[scope][digest_stable(x)] = {"item": x, "miss": 0}
        return [], [], True, True

    recs = pool[scope]
    pool_n_before = len(recs)      # 更新前池内量，用于估算采样率
    cur_fps = set()
    added = []
    for x in cur_items:
        fp = digest_stable(x)
        cur_fps.add(fp)
        rec = recs.get(fp)
        if rec is None:
            recs[fp] = {"item": x, "miss": 0}
            added.append(x)
        else:
            rec["item"] = x      # 用最新快照刷新（fee 等字段可能更新）
            rec["miss"] = 0

    removed = []
    # 命中已见业务的条数 = 本轮总条数 - 首次见到的条数
    hit_n = len(cur_items) - len(added)
    need_raw = _miss_need(hit_n, pool_n_before)
    # 阈值平滑：need 逐轮抖动会让已累积 miss 的业务突然集体达标被删
    # （实测每轮假下架 60+）。用 EMA 抹平，只让阈值缓慢跟随采样率变化。
    prev_need = (meta.get(scope) or {}).get("need")
    need = int(round(NEED_EMA * (prev_need if prev_need else need_raw)
                     + (1 - NEED_EMA) * need_raw))
    need = max(MISS_CONFIRM_MIN, min(MISS_CONFIRM_MAX, need))

    # 预热期判定：单轮采样只看到随机子集，池补齐期间「首次见到」≠ 真新增。
    #   p         = 命中已见条数 / 池内条数        （采样率）
    #   est_total = 本轮总条数 / p                （全集规模估计）
    #   expected  = (est_total - 池内) * p        （本轮"本该"补齐几条）
    m0 = meta.get(scope) or {}
    rounds = int(m0.get("rounds") or 0) + 1
    p = (float(hit_n) / float(pool_n_before)) if pool_n_before else 0.0
    est_raw = (float(len(cur_items)) / p) if p > 0 else 0.0
    prev_est = float(m0.get("est_total") or 0)
    est_total = (TOTAL_EMA * prev_est + (1 - TOTAL_EMA) * est_raw) if prev_est else est_raw
    expected_fill = max(0.0, est_total - pool_n_before) * p if p > 0 else 0.0
    fill_ratio = (float(pool_n_before) / est_total) if est_total > 0 else 0.0
    grow = (float(len(added)) / float(pool_n_before)) if pool_n_before else 1.0

    # 收敛判定：连续 PLATEAU_NEED 轮增长率 <= PLATEAU_GROW，视为池已补齐。
    plateau = int(m0.get("plateau") or 0)
    plateau = plateau + 1 if grow <= PLATEAU_GROW else 0
    plateau_ok = (plateau >= PLATEAU_NEED) and (rounds >= MIN_CONVERGE_ROUNDS)
    forced = rounds >= FORCE_ROUNDS
    converged = bool(m0.get("converged")) or plateau_ok or forced
    warmup = not converged
    # 只有「真平台收敛」（连续多轮零增长，池确实不涨了）才认为噪声归零。
    # ★ 强制收敛（FORCE_ROUNDS 兜底）时池仍在涨，若也把噪声归零，
    #   每轮新见到的几十条会全部当成新增报出来 —— 正是要避免的假新增。
    #   因此强制收敛仍走统计扣减，靠 FILL_MARGIN 保留超出预期部分的真变化。
    if plateau_ok or bool(m0.get("converged")) and (m0.get("plateau") or 0) >= PLATEAU_NEED:
        expected_fill = 0.0
        true_plateau = True
    else:
        true_plateau = False

    for fp, rec in list(recs.items()):
        if fp in cur_fps:
            continue
        miss = int(rec.get("miss") or 0) + 1
        # 预热期池不完整，miss 计数不可信，此时绝不判下架
        if (not warmup) and miss >= need:
            removed.append(rec.get("item") or {})
            recs.pop(fp, None)
        else:
            rec["miss"] = miss

    meta[scope] = {"need": need, "pool": len(recs), "rounds": rounds,
                   "grow": round(grow, 4), "est_total": round(est_total, 1),
                   "fill": round(fill_ratio, 3), "plateau": plateau,
                   "converged": converged}
    if warmup:
        print("    [预热 %d 轮] 池内 %d / 全集约 %d（完整度 %.0f%%）；"
              "本轮新见 %d 条、增长 %.2f%%，其中约 %d 条属建池补齐 → 不计入资费变化"
              % (rounds, pool_n_before, int(est_total), 100.0 * fill_ratio,
                 len(added), 100.0 * grow, int(expected_fill)))
        return [], [], False, True
    # 已收敛：仍可能有零星补齐，只报显著超出补齐预期的部分
    excess = int(len(added) - expected_fill * FILL_MARGIN)
    if excess <= 0:
        if len(added):
            print("    [已收敛] 本轮新见 %d 条，未超出补齐预期 %d 条 → 不报"
                  % (len(added), int(expected_fill * FILL_MARGIN)))
        return [], removed, False, False
    if excess < len(added):
        print("    [已收敛] 本轮新见 %d 条，扣除补齐预期 %d 条，按 %d 条计"
              % (len(added), int(expected_fill * FILL_MARGIN), excess))
        added = added[:excess]
    if (not warmup) and len(added) and true_plateau:
        print("    [已收敛·池已补齐] 本轮新见 %d 条，全部计为新增" % len(added))
    if need != MISS_CONFIRM_MIN:
        print("    [命中 %d / 池内 %d] 采样率约 %.0f%%，下架确认需连续 %d 轮未采到"
              % (hit_n, pool_n_before,
                 100.0 * hit_n / pool_n_before if pool_n_before else 0, need))
    return added, removed, False, False


def pool_items(pool, scope):
    """池内全部在售业务的展示条目（供 {板块}.json 与 latest 使用）。"""
    recs = pool.get(scope) or {}
    return [r.get("item") for r in recs.values() if r.get("item")]


def _flush_pool(pool, datadir, now):
    """把累积池内容写成展示文件 {板块}.json。

    展示数据取自池内「在售」条目（miss < 确认阈值的都已留存），
    因此页面条数只会随发现新业务单调增长，不会因某轮采样少而骤降。
    """
    n = 0
    for sc in pool.keys():
        items = pool_items(pool, sc)
        save(os.path.join(datadir, sc + ".json"),
             {"scope": sc, "items": items, "timestamp": now})
        n += 1
    print("  [池] 已写出 %d 个板块展示数据" % n)


# 注：原 update_baseline() / _baseline.json 已移除。
# 它全仓只写不读（前端、workflow、其它脚本均未读取），每轮却要对
# 32 板块 × 上千条做 md5 + titles 排序，是纯死数据、白耗 CPU / IO。


def build_latest(scopes, datadir):
    sections, prov_total, prov_stats = [], set(), {}
    q_total = None
    for sc in scopes:
        p = os.path.join(datadir, sc + ".json")
        if not os.path.exists(p):
            continue
        d = load(p)
        items = d["items"]
        fl_count = {}
        onsale = 0
        for it in items:
            fl = it.get("firstLevel") or "其他"
            fl_count[fl] = fl_count.get(fl, 0) + 1
            if fl != "停售套餐":
                onsale += 1
        if sc == "quanguo":
            q_total = len(items)
        else:
            prov_total.update(x["id"] for x in items)
            prov_stats[sc] = {"total": len(items), "onsale": onsale,
                              "dist": {k: fl_count.get(k, 0) for k in FIRST_LEVELS}}
        sections.append({"section": sc, "name": NAME.get(sc, sc), "total": len(items), "onsale": onsale,
                         "updated": d.get("timestamp") or ""})
    # 排序：quanguo 最前 → 湖南第二 → 其余按编码（用户要求湖南历史/列表置顶）
    sections.sort(key=lambda s: (0, "") if s["section"] == "quanguo" else
                  (1, "") if s["section"] == "hunan" else (2, s["section"]))
    default = "hunan" if any(s["section"] == "hunan" for s in sections) else (sections[1]["section"] if len(sections) > 1 else "")
    now = time.strftime("%Y-%m-%d %H:%M:%S")
    latest = {"sections": sections, "default": default, "quanguo_total": q_total, "prov_total": len(prov_total),
              "prov_stats": prov_stats, "updated": now, "timestamp": now}
    save(os.path.join(datadir, "latest.json"), latest)
    print("latest.json 已生成: quanguo=%s prov_total=%s sections=%d" % (q_total, len(prov_total), len(sections)))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--prev-dir", required=True, help="上一版站点 data 目录（公开仓 unicom/data checkout）")
    ap.add_argument("--out-dir", required=True, help="本轮站点 data 输出目录")
    ap.add_argument("--scopes", default="", help="逗号分隔，默认全部32板块")
    ap.add_argument("--rebuild", action="store_true",
                    help="重建基线模式：仅抓取并覆盖渲染数据/基线/latest，跳过对比与历史记录（用于管线改造后或接口大改版时防伪历史）")
    args = ap.parse_args()
    prev_dir, out_dir = args.prev_dir, args.out_dir
    jobs = build_jobs()
    # 板块名可能填错（如省份拼音拼错）：此前直接 sys.exit(1) 会让整轮抓取
    # 全部失败。改为忽略无效项、保留有效项；全部无效时退回全量，避免抓成空集。
    if args.scopes:
        wanted = [s.strip() for s in args.scopes.split(",") if s.strip()]
        bad = [s for s in wanted if s not in jobs]
        if bad:
            print("忽略未知板块:", bad)
        scopes = [s for s in wanted if s in jobs]
        if not scopes:
            print("!! 指定板块全部无效，退回全量")
            scopes = ["quanguo"] + [k for k in jobs if k != "quanguo"]
    else:
        scopes = ["quanguo"] + [k for k in jobs if k != "quanguo"]
    scopes = list(dict.fromkeys(scopes))

    now = time.strftime("%Y-%m-%d %H:%M:%S")
    print("== 任务数:", len(scopes), "==")
    # 先读入上一版快照（若 prev_dir 与 out_dir 同目录，必须在抓取覆盖前读完）
    prev_data_raw = {}
    for sc in scopes:
        p = os.path.join(prev_dir, sc + ".json")
        prev_data_raw[sc] = load(p) if os.path.exists(p) else None

    # 全网产品稳定指纹全集（上轮全网 ∪ 本轮全网，防某轮全网未抓全时被误算进省特有）
    qu_fp = set()
    for it in ((prev_data_raw.get("quanguo") or {}).get("items") or []):
        qu_fp.add(digest_stable(it))

    # 累积池：见过的业务按稳定指纹留存，只有「从未见过/连续多轮消失」才算变化
    pool, meta = load_pool(out_dir)

    partial_scopes = set()
    cur_data = {}
    for sc in scopes:
        prov, city, attr = jobs[sc]
        print("=== 抓取 %s (prov=%s city=%s) ===" % (sc, prov or "-", city or "-"))
        d = build_scope(sc, prov, city, attr)
        d["timestamp"] = now
        if d.get("partial"):
            # 采集不完整：本轮结果不可信，保留旧数据、不参与 diff，避免假下架
            print("  !! %s 本轮采集不完整（中途请求失败），保留旧数据、不记变化" % sc)
            partial_scopes.add(sc)
            continue
        # 不再直接写入展示文件：展示数据改由累积池构建，
        # 否则单轮采得少时会把残缺结果存成下轮基线，导致下轮凭空多出大量「新增」。
        cur_data[sc] = d.get("items") or []
        print("  %s 本轮采集 %d 条" % (sc, len(cur_data[sc])))

    # 全网产品指纹全集（上轮 ∪ 本轮 ∪ 累积池），供省板块剔除全网产品
    for it in (cur_data.get("quanguo") or []):
        qu_fp.add(digest_stable(it))
    for fp in (pool.get("quanguo") or {}):
        qu_fp.add(fp)

    # 省板块对比口径：省板块入池前剔除全网产品（展示文件仍保留 全网+本省特有）。
    # 全网产品变化只记在全网板块，不再“复制进31省”，清除 09-03 那种伪历史；各省历史只记本省特有变化。
    # （剔除逻辑见下方 pool_update 调用处，此处不再需要 clean_scope 包装）

    hp = os.path.join(out_dir, "history.json")

    # ── 存量瘦身（一次性自愈）──
    # 旧版把每个变化的完整详情全量塞进 history，累积到 42MB，前端需一次性下载。
    # 这里在每次运行时对已有历史统一压缩，无需手工 --rebuild，跑一轮即自动收敛。
    if os.path.exists(hp):
        try:
            _old_hist = load(hp) or []
            _before = len(json.dumps(_old_hist, ensure_ascii=False))
            if _before > HIST_MAX_BYTES:
                _new_hist = [slim_change(e) for e in _old_hist]
                _after = len(json.dumps(_new_hist, ensure_ascii=False))
                save(hp, _new_hist)
                print("  [瘦身] history.json %.1fMB → %.1fMB（%d 条）"
                      % (_before / 1048576, _after / 1048576, len(_new_hist)))
        except Exception as e:
            print("  [瘦身] 跳过（读取失败: %s）" % e)

    # 重建基线模式：不对比 prev、不写历史，仅更新渲染数据/基线/latest
    if args.rebuild:
        print("== 重建基线模式：清空累积池、跳过对比与历史，仅刷新数据/latest ==")
        pool = {}
        for sc in scopes:
            if sc in partial_scopes or sc not in cur_data:
                continue
            cur_items = cur_data[sc]
            if sc != "quanguo":
                cur_items = [x for x in cur_items if digest_stable(x) not in qu_fp]
            pool[sc] = {digest_stable(x): {"item": x, "miss": 0} for x in cur_items}
            print("  %s 重建基线 %d 条" % (sc, len(pool[sc])))
        _flush_pool(pool, out_dir, now)
        save_pool(out_dir, pool, meta)
        # 传全量板块（而非本轮 scopes）：focus 模式下未抓的省份仍保留在页面上
        build_latest(list(pool.keys()), out_dir)
        print("完成(重建)，history 保持现有 %d 条" % len(load(hp) if os.path.exists(hp) else []))
        return

    # ── 用累积池判变化（替代单轮 diff）──
    history = load(hp) if os.path.exists(hp) else []
    changes = {}
    _DET_LIMIT = int(os.getenv("UNICOM_DETAILS_LIMIT") or "200")
    for sc in scopes:
        if sc in partial_scopes or sc not in cur_data:
            continue
        cur_items = cur_data[sc]
        if sc != "quanguo":
            # 省板块对比口径：剔除全网产品（与原逻辑一致）
            cur_items = [x for x in cur_items if digest_stable(x) not in qu_fp]
        cur_items = filter_test_items(cur_items, verbose=False)
        added, removed, cold, warm = pool_update(sc, cur_items, pool, meta)
        # 采样轮换会产生大量假变更：老业务被记成新增、仍在架的被记成下架。
        # 先按上下线日期剔除，再决定是否记录本轮。
        added, removed, _fakes = filter_sampling_fakes(added, removed, now)
        if _fakes["fake_added"] or _fakes["fake_removed"]:
            print("  %s 剔除采样噪声：伪新增 %d / 伪下架 %d"
                  % (sc, _fakes["fake_added"], _fakes["fake_removed"]))
        if cold:
            print("  %s 首次，累积池建基线（不记变化），入池 %d 条" % (sc, len(pool.get(sc) or {})))
            continue
        if warm:
            print("  %s 池补齐中，本轮不记变化（池内 %d 条）" % (sc, len(pool.get(sc) or {})))
            continue
        if not added and not removed:
            print("  %s 无变化（池内 %d 条）" % (sc, len(pool.get(sc) or {})))
            continue
        r = {
            "added": len(added), "removed": len(removed), "modified": 0,
            "added_names": [x.get("title", "") for x in added],
            "removed_names": [x.get("title", "") for x in removed],
            "modified_names": [],
            "added_details": dict(list({_title_key(x): field_snapshot(x) for x in added}.items())[:_DET_LIMIT]),
            "removed_details": dict(list({_title_key(x): field_snapshot(x) for x in removed}.items())[:_DET_LIMIT]),
            "modified_details": {},
            "added_list": [_brief(x) for x in added],
            "removed_list": [_brief(x) for x in removed],
            "modified_list": [],
        }
        print("  %s 新增 %d / 下架 %d（池内 %d 条）" % (sc, len(added), len(removed), len(pool.get(sc) or {})))
        r = slim_change(r)
        if has_real_change(r):
            changes[sc] = r
    if changes:
        entry = {"ts": now}
        entry.update(changes)
        history.append(entry)
        # 历史记录长期增长会导致 history.json 无限膨胀（names/details 已全量），保留最近 N 条即可
        history = history[-int(os.getenv("UNICOM_HISTORY_LIMIT") or "30"):]
        print("检测到变化:", {k: "add%d/rm%d/mod%d" % (v["added"], v["removed"], v["modified"]) for k, v in changes.items()})
    else:
        print("本次检测：无变化")
    save(hp, history)

    # 展示数据由累积池构建：页面数字单调收敛，不再随单轮采样运气忽大忽小
    _flush_pool(pool, out_dir, now)
    save_pool(out_dir, pool, meta)
    # 传全量板块（而非本轮 scopes）：focus 模式下未抓的省份仍保留在页面上
    build_latest(list(pool.keys()), out_dir)
    print("完成，history 共 %d 条，累积池 %d 个板块" % (len(history), len(pool)))


if __name__ == "__main__":
    main()
