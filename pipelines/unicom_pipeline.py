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
import json, time, os, sys, urllib.request, http.cookiejar, hashlib, argparse

from pipeline_common import is_sampling_noise, mark_noise, modified_details_for, filter_test_items, slim_change

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
HIST_MAX_BYTES = int(os.getenv("UNICOM_HIST_MAX_BYTES", str(3 * 1024 * 1024)))


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
               page_size=500, stale_stop=60, time_budget=300):
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
    pool = fetch_pool(province_id, city_id, attr)
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
    return {"scope": scope, "items": items}


def digest_item(it):
    return json.dumps([it.get("id"), it.get("title"), it.get("fee"), it.get("firstLevel")], ensure_ascii=False)


def digest_stable(it):
    """稳定指纹：不含 id（接口 id 可能逐轮漂移），用 标题+资费+一级分类+二级分类 标识业务实体。"""
    return json.dumps([it.get("title", ""), it.get("fee", ""), it.get("firstLevel", ""), it.get("secondLevel", "")], ensure_ascii=False)


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

def diff_scope(prev, cur):
    from collections import Counter
    p_items = prev.get("items") or []
    c_items = cur.get("items") or []
    # 稳定指纹多重集：用 Counter 精确抵消同名同价多实体，避免集合碰撞吞掉真实增减
    p_count = Counter(digest_stable(x) for x in p_items)
    c_count = Counter(digest_stable(x) for x in c_items)
    p_left = {f: max(0, n - c_count.get(f, 0)) for f, n in p_count.items()}
    c_left = {f: max(0, n - p_count.get(f, 0)) for f, n in c_count.items()}
    added, removed = [], []
    for x in c_items:
        f = digest_stable(x)
        if c_left.get(f, 0) > 0:
            added.append(x); c_left[f] -= 1
    for x in p_items:
        f = digest_stable(x)
        if p_left.get(f, 0) > 0:
            removed.append(x); p_left[f] -= 1
    pmap = {x["id"]: x for x in p_items}
    cmap = {x["id"]: x for x in c_items}
    modified = [cmap[i] for i in cmap if i in pmap and digest_item(cmap[i]) != digest_item(pmap[i])]
    # 全量对称错位护栏：id 层面大面积漂移（>50%），但稳定指纹层面净变化为 0 → 实为 id 漂移的基线错位，重建基线不记变化
    raw_added = sum(1 for i in cmap if i not in pmap)
    raw_removed = sum(1 for i in pmap if i not in cmap)
    raw_n = raw_added + raw_removed
    total_n = len(p_items) + len(c_items)
    if total_n > 0 and raw_n / total_n > 0.5 and not added and not removed and not modified:
        return {"shifted": True, "added": 0, "removed": 0, "modified": 0,
                "added_names": [], "removed_names": [], "modified_names": [],
                "added_list": [], "removed_list": [], "modified_list": [],
                "raw_added": raw_added, "raw_removed": raw_removed}
    # names 已全量展示，详情快照保留合理上限即可（对齐移动端策略，防止巨量变更撑爆 history）
    _DET_LIMIT = int(os.getenv("UNICOM_DETAILS_LIMIT", "200"))
    _det = {_title_key(x): field_snapshot(x) for x in added}
    _rde = {_title_key(x): field_snapshot(x) for x in removed}
    _mde = {_title_key(m): field_diff(pmap.get(m.get("id")), m) for m in modified}
    return {
        "added": len(added), "removed": len(removed), "modified": len(modified),
        "added_names": [x.get("title", "") for x in added],
        "removed_names": [x.get("title", "") for x in removed],
        "modified_names": [x.get("title", "") for x in modified],
        "modified_details": modified_details_for(pmap, modified),
        "added_details": dict(list(_det.items())[:_DET_LIMIT]),
        "removed_details": dict(list(_rde.items())[:_DET_LIMIT]),
        "modified_details": dict(list(_mde.items())[:_DET_LIMIT]),
        "added_list": [_brief(x) for x in added],
        "removed_list": [_brief(x) for x in removed],
        "modified_list": [_brief(x) for x in modified],
    }


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
              "useScope", "broadBand", "sms", "onlinePeriod"):
        v = d.get(k, "")
        v = "" if v is None else v
        if v != "" and v != "0":
            snap[k] = v
    return snap


def field_diff(old, new):
    """字段级修改明细：比较新旧条目的平铺字段，返回 [{field, from, to}]（修改详情弹窗用）"""
    def _flat(it):
        base = field_snapshot(it)
        d = it.get("detail") or {}
        for k in d:
            if k not in base:
                base[k] = d[k] if d[k] is not None else ""
        return base
    fo, fn = _flat(old), _flat(new)
    diff = []
    for k in fo:
        vo, vn = fo.get(k), fn.get(k)
        so, sn = ("" if vo is None else str(vo)), ("" if vn is None else str(vn))
        if so != sn:
            diff.append({"field": k, "from": so, "to": sn})
    return diff


def load(path):
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def save(path, obj):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(obj, f, ensure_ascii=False, separators=(",", ":"))


def update_baseline(scopes, datadir):
    base = {}
    for sc in scopes:
        cur = load(os.path.join(datadir, sc + ".json"))
        items = [x["id"] for x in cur["items"]]
        base[sc] = {"count": len(items),
                    "hash": hashlib.md5(json.dumps(items, ensure_ascii=False).encode("utf-8")).hexdigest(),
                    "titles": sorted(x["title"] for x in cur["items"])}
    save(os.path.join(datadir, "_baseline.json"), base)


def build_latest(scopes, datadir):
    sections, prov_total, prov_stats = [], set(), {}
    q_total = None
    for sc in scopes:
        d = load(os.path.join(datadir, sc + ".json"))
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
    scopes = args.scopes.split(",") if args.scopes else (["quanguo"] + [k for k in jobs if k != "quanguo"])
    missing = [s for s in scopes if s not in jobs]
    if missing:
        print("未知板块:", missing); sys.exit(1)

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

    for sc in scopes:
        prov, city, attr = jobs[sc]
        print("=== 抓取 %s (prov=%s city=%s) ===" % (sc, prov or "-", city or "-"))
        d = build_scope(sc, prov, city, attr)
        d["timestamp"] = now
        save(os.path.join(out_dir, sc + ".json"), d)
        if sc == "quanguo":
            for it in (d.get("items") or []):
                qu_fp.add(digest_stable(it))

    # 省板块对比口径：对比前双方都剔除全网产品（仅有 diff 环节生效，展示文件仍保留 全网+本省特有）。
    # 全网产品变化只记在全网板块，不再“复制进31省”，清除 09-03 那种伪历史；各省历史只记本省特有变化。
    def clean_scope(snap):
        if snap is None:
            return None
        return {"items": [x for x in (snap.get("items") or [])
                          if digest_stable(x) not in qu_fp]}

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
        print("== 重建基线模式：跳过对比与历史，仅刷新数据/基线/latest ==")
        update_baseline(scopes, out_dir)
        build_latest(scopes, out_dir)
        print("完成(重建)，history 保持现有 %d 条" % len(load(hp) if os.path.exists(hp) else []))
        return

    prev_data = {sc: clean_scope(prev_data_raw[sc]) for sc in scopes}

    # diff（上一版已入内存）
    history = load(hp) if os.path.exists(hp) else []
    changes = {}
    for sc in scopes:
        if sc == "quanguo":
            prev_use = prev_data[sc]
            cur_use = load(os.path.join(out_dir, sc + ".json"))
        else:
            prev_use = prev_data[sc]
            cur_use = clean_scope(load(os.path.join(out_dir, sc + ".json")))
        if prev_use is None:
            print("  %s 首次，建基线（不记变化）" % sc)
            continue
        r = diff_scope(prev_use, cur_use)
        _bt = len((prev_use or {}).get("items") or [])
        if is_sampling_noise(r, _bt):
            print("    >> 采样噪声：" + str(mark_noise(r, _bt).get("note", "")))
        r = mark_noise(r, _bt)
        changes[sc] = slim_change(r)
    if changes:
        entry = {"ts": now}
        entry.update(changes)
        history.append(entry)
        # 历史记录长期增长会导致 history.json 无限膨胀（names/details 已全量），保留最近 N 条即可
        history = history[-int(os.getenv("UNICOM_HISTORY_LIMIT", "30")):]
        print("检测到变化:", {k: "add%d/rm%d/mod%d" % (v["added"], v["removed"], v["modified"]) for k, v in changes.items()})
    else:
        print("本次检测：无变化")
    save(hp, history)

    update_baseline(scopes, out_dir)
    build_latest(scopes, out_dir)
    print("完成，history 共 %d 条" % len(history))


if __name__ == "__main__":
    main()
