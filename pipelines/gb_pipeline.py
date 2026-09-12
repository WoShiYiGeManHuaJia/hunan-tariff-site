from pipeline_common import (is_sampling_noise, mark_noise, has_real_change,
                             modified_details_for, slim_change)

#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""广电资费监控管线（可在 GitHub Actions 直接运行，路径全部相对脚本目录）

职责：抓取广电「全网 + 33 地区」资费（免费公示页 m.10099.com.cn/expensesNotice）
      → 与上一版数据 diff → 输出站点数据目录（{scope}.json + latest.json + history.json）
      → 由 workflow 推公开仓 gb/ 子目录（schema 对齐联通站）。
设计：
- 广电接口原生 HTTP 直连可用（无 WAF 强拦，acw_tc cookie 仅限流），请求按分类叶逐类抓取。
- 价格字段 productPrice 单位为「分」，解析为「元」字符串（fee），0/空 视为免费。
- 省份照广电官网区划：全网(ZZZZ) + 33 地区（含单独区划 广州/深圳）。
- 稳定指纹 diff 复用联通/电信范式；省板块对比前剔除与全网同指纹条目（防御接口偶发返回全网业务）。
- 抓取失败降级：某 scope 抓取为空且上版非空 → 本轮跳过该 scope（保留旧数据、不记变化）；
  全量失败率过半视为反爬恶化 → 仅保留 quanguo + hunan。
用法:
  python3 gb_pipeline.py --prev-dir PATH --out-dir PATH [--scopes hunan,quanguo] [--rebuild]
"""
import json, time, os, sys, urllib.request, ssl, hashlib, argparse

PROG_DIR = os.path.dirname(os.path.abspath(__file__))
API = "https://m.10099.com.cn/contact-web/api/goods/"
CHANNEL = "cd_20220914_514144"
_ctx = ssl.create_default_context()
_ctx.check_hostname = False
_ctx.verify_mode = ssl.CERT_NONE
HDRS = {
    "User-Agent": "Mozilla/5.0 (iPhone; CPU iPhone OS 16_0 like Mac OS X) AppleWebKit/605.1.15 Mobile/15E148 Safari/604.1",
    "Content-Type": "application/json",
    "Accept": "application/json, text/javascript, */*; q=0.01",
    "X-Requested-With": "XMLHttpRequest",
    "Origin": "https://m.10099.com.cn",
    "Referer": "https://m.10099.com.cn/expensesNotice/",
}

# 地区 key -> (areaCode, 显示名)。key 拼音对齐三站；广州/深圳为广电独立区划。
AREAS = [
    ("quanguo", "ZZZZ", "全网(全国)"),
    ("beijing", "BJ00", "北京"), ("tianjin", "TJ00", "天津"), ("hebei", "HB00", "河北"),
    ("shanxi", "SX00", "山西"), ("neimenggu", "NMG0", "内蒙古"), ("liaoning", "LN00", "辽宁"),
    ("jilin", "JL00", "吉林"), ("heilongjiang", "HLJ0", "黑龙江"), ("shanghai", "SH00", "上海"),
    ("jiangsu", "JS00", "江苏"), ("zhejiang", "ZJ00", "浙江"), ("anhui", "AH00", "安徽"),
    ("fujian", "FJ00", "福建"), ("jiangxi", "JX00", "江西"), ("shandong", "SD00", "山东"),
    ("henan", "HN01", "河南"), ("hubei", "HB01", "湖北"), ("hunan", "HN00", "湖南"),
    ("guangdong", "GD00", "广东"), ("shenzhen", "SZ00", "深圳"),
    ("guangxi", "GX00", "广西"), ("hainan", "HN02", "海南"), ("chongqing", "CQ00", "重庆"),
    ("sichuan", "SC00", "四川"), ("guizhou", "GZ01", "贵州"), ("yunnan", "YN00", "云南"),
    ("xizang", "XZ00", "西藏"), ("shaanxi", "SX01", "陕西"), ("gansu", "GS00", "甘肃"),
    ("qinghai", "QH00", "青海"), ("ningxia", "NX00", "宁夏"), ("xinjiang", "XJ00", "新疆"),
]
CODE2KEY = {c: k for k, c, _ in AREAS}
KEY2NAME = {k: n for k, _, n in AREAS}

# 分类 code -> 展示名（一级/二级）。树：GZ 公众 / ZQ 政企。
FIRST_MAP = {
    "GZ_TC": "套餐", "GZ_JZB": "加装包", "GZ_YXHD": "营销活动",
    "GZ_TSQTTC": "特殊群体套餐", "ZQ": "政企",
}
SECOND_MAP = {
    "GZ_TC_4G": "4G套餐", "GZ_TC_5G": "5G套餐", "GZ_TC_KD": "宽带", "GZ_TC_GH": "固话",
    "GZ_JZB_YYB": "语音包", "GZ_JZB_LLB": "流量包",
    "GZ_YXHD_HY": "合约", "GZ_YXHD_CX": "促销",
    "GZ_TSQTTC_4G": "4G", "GZ_TSQTTC_5G": "5G", "GZ_TSQTTC_KD": "宽带", "GZ_TSQTTC_GH": "固话",
}
# 分类树（静态，与官网一致；保持 stable 排序便于 diff）
TREE = [("GZ", None, [("GZ_TC", [("GZ_TC_4G",), ("GZ_TC_5G",), ("GZ_TC_KD",), ("GZ_TC_GH",)]),
                      ("GZ_JZB", [("GZ_JZB_YYB",), ("GZ_JZB_LLB",)]),
                      ("GZ_YXHD", [("GZ_YXHD_HY",), ("GZ_YXHD_CX",)]),
                      ("GZ_TSQTTC", [("GZ_TSQTTC_4G",), ("GZ_TSQTTC_5G",), ("GZ_TSQTTC_KD",), ("GZ_TSQTTC_GH",)])]),
        ("ZQ", None, [])]


def _post(path, body):
    data = json.dumps(body).encode("utf-8")
    req = urllib.request.Request(API + path, data=data, headers=HDRS, method="POST")
    last = None
    for a in range(4):
        try:
            with urllib.request.urlopen(req, timeout=40, context=_ctx) as r:
                return json.loads(r.read().decode("utf-8"))
        except Exception as e:
            last = e
            time.sleep(2 * (a + 1))
    raise last


def query(page_tree, area):
    """抓取一份完整 scope 数据，返回 (items, failed_leaf_count)"""
    items, seen, failed = [], set(), 0
    leaves = []
    for t1, _c, subs in page_tree:
        if not subs:
            leaves.append((t1, "", ""))
        for t2, sub2 in subs:
            if not sub2:
                leaves.append((t1, t2, ""))
            for (t3,) in sub2:
                leaves.append((t1, t2, t3))
    for t1, t2, t3 in leaves:
        body = {"channelId": CHANNEL, "type1": t1, "type2": t2, "type3": t3,
                "productName": "", "stateFlag": "1", "minPrice": "", "maxPrice": "",
                "applicableArea": area, "timestamp": int(time.time() * 1000)}
        try:
            d = _post("queryTariffAllByCond", body)
        except Exception as e:
            print("    %s/%s/%s 失败: %s" % (t1 or "-", t2 or "-", t3 or "-", repr(e)[:80]))
            failed += 1
            continue
        lst = d.get("data") or []
        for x in lst:
            x["_gb_key"] = t2 or t1
            x["_gb_subkey"] = t3 or (t2 if t1 != "ZQ" else "")
            if x.get("id") in seen:
                continue
            seen.add(x.get("id"))
            items.append(x)
        time.sleep(0.3)
    return items, failed


def _fmt_date(s):
    if not s:
        return ""
    t = str(s).strip()
    if len(t) >= 10 and t[4] == "-":
        return t[:10]
    if len(t) >= 8 and t[:8].isdigit():
        return "%s-%s-%s" % (t[:4], t[4:6], t[6:8])
    if "年" in t and "月" in t:
        m = __import__("re").search(r"(\d{4})年(\d{1,2})月(\d{1,2})", t)
        if m:
            return "%s-%02d-%02d" % (m.group(1), int(m.group(2)), int(m.group(3)))
    return t[:10]


def _price_str(p):
    """分 -> 元 字符串（去尾零）"""
    try:
        n = int(p)
    except Exception:
        n = 0
    if n == 0:
        return "0"
    return str(n / 100).rstrip("0").rstrip(".")


def parse_item(x):
    t2 = x.get("_gb_key") or x.get("type2") or ""
    t3 = x.get("_gb_subkey") or x.get("parentTypeCode") or ""
    first = FIRST_MAP.get(t2, "其他")
    second = SECOND_MAP.get(t3, "其他")
    if t2 == "ZQ" and second == "其他":
        second = "政企"
    price = _price_str(x.get("productPrice"))
    unit_raw = x.get("productPriceUnit") or "月"
    if unit_raw == "月起":
        fee_unit = "元/月起"
    elif unit_raw:
        fee_unit = "元/" + unit_raw
    else:
        fee_unit = ""
    f = {
        "name": x.get("productName", ""),
        "reportNo": x.get("filingNumber", ""),
        "codeType": x.get("parentTypeCode", ""),
        "feesStandard": price,
        "feeUnit": fee_unit,
        "minute": _num(x.get("domesticCall")),
        "commonData": _num(x.get("domesticTraffic")),
        "dataUnit": x.get("domesticTrafficUnit") or "GB",
        "sms": _num(x.get("sms")),
        "orientTraffic": _num(x.get("orientTraffic")),
        "iptv": _s(x.get("iptv")),
        "broadBand": _s(x.get("bandwidth")),
        "extraFees": "",
        "serviceContent": _pick(x.get("rights"), x.get("tariffAttr"), x.get("operatExplain")),
        "useScope": _s(x.get("applicablePeople")),
        "validPeriod": _s(x.get("validPeriod")),
        "onlinePeriod": "",
        "saleChnl": _s(x.get("saleChannel")),
        "onDate": _fmt_date(x.get("onlineDay")),
        "offDate": _fmt_date(x.get("offlineDay")),
        "unsubscribe": _s(x.get("unsubscribeMethod")),
        "responsibility": _s(x.get("responsibility")),
        "inNetReq": _s(x.get("onlineRequirements")),
        "otherNotes": " | ".join(filter(None, [_s(x.get("otherContent")), _s(x.get("otherExplain")),
                                               _s(x.get("familyNetwork")), _s(x.get("mutexRule")),
                                               _s(x.get("expirationRule")), _s(x.get("tariffAttr"))])),
        "regionTraffic": _num(x.get("regionTraffic")),
        "regionTrafficUnit": x.get("regionTrafficUnit") or "GB",
        "firstLevelType": "1" if first != "政企" else "2",
        "secondLevelType": second,
    }
    title = str(x.get("productName") or "").strip()
    return {
        "id": x.get("id", "") or hashlib.md5((title + price).encode("utf-8")).hexdigest(),
        "title": title,
        "fee": price,
        "firstLevel": first,
        "secondLevel": second,
        "detail": f,
    }


def _s(v):
    if v is None:
        return ""
    v = str(v).strip()
    return "" if v in ("", "无", "None", "null") else v


def _pick(*vals):
    for v in vals:
        s = _s(v)
        if s:
            return s
    return ""


def _num(v):
    return str(v) if v not in (None, "") and str(v).strip() not in ("", "无", "None") else ""


def fetch_scope(scope, area):
    raw, failed = query(TREE, area)
    items = [parse_item(x) for x in raw]
    print("  [%s] area=%s got=%d failed_leaf=%d" % (scope, area, len(items), failed))
    return items, failed


def digest_stable(it):
    """稳定指纹：标题+资费+一级+二级 标识业务实体（不含 id，防逐轮漂移）。"""
    return json.dumps([it.get("title", ""), it.get("fee", ""), it.get("firstLevel", ""), it.get("secondLevel", "")], ensure_ascii=False)


def digest_item(it):
    return json.dumps([it.get("id"), it.get("title"), it.get("fee"), it.get("firstLevel"), it.get("secondLevel")], ensure_ascii=False)


def _brief(it):
    """下架/新增时保存的配置快照。

    此前只存 7 个字段且 serviceContent 截断到 200 字，前端弹窗"只有几行字"，
    业务内容看不全。现改为保存 detail 全量字段（长文本放宽到 1200 字），
    前端 briefTable 会按 PLAN_LABELS 翻译并隐藏内部字段。
    """
    d = it.get("detail") or {}
    out = {"title": it.get("title", ""), "fee": it.get("fee", ""),
           "firstLevel": it.get("firstLevel", ""), "secondLevel": it.get("secondLevel", "")}
    for k, v in d.items():
        if k in ("timestamp", "responseContent", "data"):
            continue
        if isinstance(v, str) and len(v) > 1200:
            v = v[:1200] + "…"
        out[k] = v
    return out


def diff_scope(prev, cur):
    from collections import Counter
    p_items = prev.get("items") or []
    c_items = cur.get("items") or []
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
    raw_added = sum(1 for i in cmap if i not in pmap)
    raw_removed = sum(1 for i in pmap if i not in cmap)
    raw_n = raw_added + raw_removed
    total_n = len(p_items) + len(c_items)
    if total_n > 0 and raw_n / total_n > 0.5 and not added and not removed and not modified:
        return {"shifted": True, "added": 0, "removed": 0, "modified": 0,
                "added_names": [], "removed_names": [], "modified_names": [],
                "added_list": [], "removed_list": [], "modified_list": [],
                "raw_added": raw_added, "raw_removed": raw_removed}
    return {"added": len(added), "removed": len(removed), "modified": len(modified),
            "added_names": [x.get("title", "") for x in added][:24],
            "removed_names": [x.get("title", "") for x in removed][:24],
            "modified_names": [x.get("title", "") for x in modified][:24],
            "modified_details": modified_details_for(pmap, modified[:24]),
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


def build_latest(scopes, datadir):
    sections, prov_total, prov_stats = [], set(), {}
    q_total = None
    for sc in scopes:
        d = load(os.path.join(datadir, sc + ".json"))
        items = d["items"]
        dist = {}
        for it in items:
            fl = it.get("firstLevel") or "其他"
            dist[fl] = dist.get(fl, 0) + 1
        if sc == "quanguo":
            q_total = len(items)
        else:
            prov_total.update(x["title"] for x in items)
            prov_stats[sc] = {"total": len(items), "onsale": len(items), "dist": dist}
        sections.append({"section": sc, "name": KEY2NAME.get(sc, sc), "total": len(items), "onsale": len(items),
                         "updated": d.get("timestamp") or ""})
    # 排序：quanguo 最前 → 湖南第二 → 其余按键名（用户要求湖南置顶）
    sections.sort(key=lambda s: (0, "") if s["section"] == "quanguo" else
                  (1, "") if s["section"] == "hunan" else (2, s["section"]))
    default = "hunan" if any(s["section"] == "hunan" for s in sections) else (sections[1]["section"] if len(sections) > 1 else "quanguo")
    now = time.strftime("%Y-%m-%d %H:%M:%S")
    latest = {"sections": sections, "default": default, "quanguo_total": q_total, "prov_total": len(prov_total),
              "prov_stats": prov_stats, "updated": now, "timestamp": now}
    save(os.path.join(datadir, "latest.json"), latest)
    print("latest.json 已生成: quanguo=%s prov_total=%s sections=%d" % (q_total, len(prov_total), len(sections)))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--prev-dir", required=True)
    ap.add_argument("--out-dir", required=True)
    ap.add_argument("--scopes", default="", help="逗号分隔，默认全部34板块")
    ap.add_argument("--rebuild", action="store_true", help="重建基线：跳过对比与历史")
    args = ap.parse_args()
    prev_dir, out_dir = args.prev_dir, args.out_dir
    # 板块名填错时不再 sys.exit(1) 让整轮失败：忽略无效项、保留有效项，
    # 全部无效则退回全量（与联通/移动行为一致）。
    if args.scopes:
        wanted = [s.strip() for s in args.scopes.split(",") if s.strip()]
        bad = [s for s in wanted if s not in KEY2NAME]
        if bad:
            print("忽略未知板块:", bad)
        scopes = [s for s in wanted if s in KEY2NAME]
        if not scopes:
            print("!! 指定板块全部无效，退回全量")
            scopes = [k for k, _, _ in AREAS]
    else:
        scopes = [k for k, _, _ in AREAS]
    scopes = list(dict.fromkeys(scopes))

    now = time.strftime("%Y-%m-%d %H:%M:%S")
    print("== 广电任务数: %d ==" % len(scopes))
    prev_data_raw = {}
    for sc in scopes:
        p = os.path.join(prev_dir, sc + ".json")
        prev_data_raw[sc] = load(p) if os.path.exists(p) else None

    # 全网稳定指纹全集（上轮全网 ∪ 本轮全网），省板块 diff 前剔除
    qu_fp = set()
    for it in ((prev_data_raw.get("quanguo") or {}).get("items") or []):
        qu_fp.add(digest_stable(it))

    saved_scopes, failed_scopes = [], []
    for sc in scopes:
        area = dict((k, c) for k, c, _ in AREAS)[sc]
        print("=== 抓取 %s (%s) ===" % (sc, KEY2NAME[sc]))
        items, failed = fetch_scope(sc, area)
        ok = (failed == 0) or (len(items) > 0)
        data = {"scope": sc, "timestamp": now, "items": items}
        if sc == "quanguo":
            for it in items:
                qu_fp.add(digest_stable(it))
        # 保护条件此前写成 `ok and ...`：ok=False 恰是「彻底失败、无数据」，
        # 保护反而完全失效，空数据直接落盘把线上冲成 0 条。
        # 判据只看本轮结果本身：本轮为空且上版有数据 → 视为失败，跳过本轮。
        if len(items) == 0 and prev_data_raw.get(sc):
            print("  !! %s 抓取为空但上版有 %d 条，视为失败，跳过本轮" % (sc, len(prev_data_raw[sc]["items"])))
            failed_scopes.append(sc)
            continue
        save(os.path.join(out_dir, sc + ".json"), data)
        saved_scopes.append(sc)
        print("[%s] total=%d" % (sc, len(items)))
        time.sleep(0.8)
    # 反爬降级护栏：过半 scope 失败 → 只保留 quanguo+hunan 在本次已写文件中
    if failed_scopes and len(failed_scopes) > len(scopes) / 2:
        print("!! 大量 scope 抓取失败(%d/%d)，判定为反爬恶化，退守 全国+湖南" % (len(failed_scopes), len(scopes)))
        keep = set(saved_scopes) & {"quanguo", "hunan"}
        for sc in saved_scopes:
            if sc not in keep:
                # 此前直接 os.remove：本轮文件已覆盖旧数据，一删就是彻底清空，
                # 站点该省直接空白且被提交。改为回写上一版数据，退守但不清空。
                old = prev_data_raw.get(sc)
                if old:
                    save(os.path.join(out_dir, sc + ".json"), old)
                    print("  ↩ %s 回退为上一版 %d 条（不删除）" % (
                        sc, len(old.get("items") or [])))
                else:
                    os.remove(os.path.join(out_dir, sc + ".json"))

    # 省板块 diff 前剔除全网业务
    def clean_scope(snap):
        if snap is None:
            return None
        return {"items": [x for x in (snap.get("items") or []) if digest_stable(x) not in qu_fp]}

    hp = os.path.join(out_dir, "history.json")
    if args.rebuild:
        print("== 重建基线模式：跳过对比与历史 ==")
        build_latest(scopes, out_dir)
        print("完成(重建)")
        return

    prev_data = {sc: clean_scope(prev_data_raw[sc]) for sc in scopes}
    history = load(hp) if os.path.exists(hp) else []
    changes = {}
    for sc in scopes:
        p = os.path.join(out_dir, sc + ".json")
        if not os.path.exists(p):
            continue
        prev_use = prev_data[sc]
        cur_use = clean_scope(load(p))
        if prev_use is None:
            print("  %s 首次，建基线（不记变化）" % sc)
            continue
        r = diff_scope(prev_use, cur_use)
        _bt = len((prev_use or {}).get("items") or [])
        if is_sampling_noise(r, _bt):
            print("    >> 采样噪声：" + str(mark_noise(r, _bt).get("note", "")))
        r = slim_change(mark_noise(r, _bt))
        if has_real_change(r):
            changes[sc] = r
    if changes:
        entry = {"ts": now}
        entry.update(changes)
        history.append(entry)
        # 与电信/联通对齐：只保留最近 N 条，避免 history 无限膨胀
        # （前端需一次性下载，过大则移动端打不开）
        history = history[-int(os.getenv("HISTORY_LIMIT") or "30"):]
        print("检测到变化:", {k: "add%d/rm%d/mod%d" % (v["added"], v["removed"], v["modified"]) for k, v in changes.items()})
    else:
        print("本次检测：无变化")
    save(hp, history)
    build_latest(scopes, out_dir)
    print("完成，history 共 %d 条" % len(history))


if __name__ == "__main__":
    main()