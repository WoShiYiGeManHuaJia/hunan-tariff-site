#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""中国电信资费监控管线（可在 GitHub Actions 直接运行，路径全部相对脚本目录）

职责：抓取电信「湖南(600203) + 全国(1000000037)」资费（对齐联通站 JSON schema）
      → 与上一版数据 diff → 输出站点数据目录（{scope}.json + latest.json + history.json）。
说明：其余 29 省 provCode 无公开口径且各省 h5 受瑞数 WAF 拦截，暂无法自动化，预留 SCOPES 可扩展。
用法:
  python3 telecom_pipeline.py --prev-dir PATH --out-dir PATH
"""
import urllib.request, json, time, base64, hashlib, os, sys, argparse

from pipeline_common import is_sampling_noise, mark_noise, modified_details_for, filter_test_items, slim_change
from Crypto.Cipher import AES
from Crypto.Util.Padding import pad

KEY = b"telecom_wap_2018"
UA = "Mozilla/5.0 (Linux; Android 13; SM-S9110) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0 Mobile Safari/537.36"
API = "https://www.189.cn/wapportalweb/wapportalweb/tariffSection.do"

SCOPES = {
    "hunan": {"prov": "600203", "name": "湖南"},
    "quanguo": {"prov": "1000000037", "name": "全国"},
}


def encrypt(m):
    return base64.b64encode(AES.new(KEY, AES.MODE_ECB).encrypt(pad(m.encode("utf-8"), 16))).decode("utf-8")


def call(fn, rc):
    body = encrypt(json.dumps({"headerInfo": {"functionCode": fn}, "requestContent": rc}, ensure_ascii=False))
    req = urllib.request.Request(API, data=body.encode("utf-8"), method="POST", headers={
        "User-Agent": UA,
        "Referer": "https://www.189.cn/wapportalweb/rateZone/index.html",
        "Accept": "application/json, text/plain, */*",
        "Content-Type": "text/plain;charset=UTF-8",
        "Origin": "https://www.189.cn",
        "x-qd-reqtime": str(int(time.time() * 1000)),
    })
    last = None
    for a in range(4):
        try:
            with urllib.request.urlopen(req, timeout=60) as r:
                return json.loads(r.read().decode("utf-8"))
        except Exception as e:
            last = e
            time.sleep(2 * (a + 1))
    raise last


def home(prov):
    d = call("tariffSectionHome", {"ticket": "", "sessionid": "", "provCode": prov})
    return d.get("responseContent", {})


def query(sess, prov, l1, l2=""):
    d = call("tariffSectionQuery", {"sessionid": sess, "type": 1, "provCode": prov, "lable1Id": l1, "lable2Id": l2})
    return d.get("responseContent", {})


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


def parse_item(x):
    """电信原始字段 → 联通站统一 schema"""
    fee = x.get("fees", "") or ""
    detail = {
        "name": x.get("name", ""),
        "reportNo": x.get("reportNo", ""),
        "codeType": x.get("lable1Name", ""),
        "feesStandard": fee,
        "feeUnit": x.get("feesUnit", ""),
        "minute": x.get("call", ""),
        "commonData": x.get("data", ""),
        "dataUnit": x.get("dataUnit", ""),
        "sms": x.get("sms", ""),
        "orientTraffic": x.get("orientTraffic", ""),
        "iptv": x.get("iptv", ""),
        "broadBand": x.get("bandwidth", ""),
        "extraFees": x.get("otherFees", ""),
        "serviceContent": x.get("rights", ""),
        "useScope": x.get("applicablePeople", ""),
        "validPeriod": x.get("validPeriod", ""),
        "saleChnl": x.get("channel", ""),
        "onDate": _fmt_date(x.get("onlineDay")),
        "offDate": _fmt_date(x.get("offlineDay")),
        "unsubscribe": x.get("unsubscribe", ""),
        "responsibility": x.get("responsibility", ""),
        "inNetReq": x.get("duration", ""),
        "otherNotes": x.get("otherContent", ""),
        "firstLevelType": x.get("type1", "1"),
        "secondLevelType": x.get("type2", "1"),
    }
    title = x.get("name", "")
    return {
        "id": x.get("id", "") or hashlib.md5((title + fee).encode("utf-8")).hexdigest(),
        "title": title,
        "fee": fee,
        "firstLevel": x.get("lable1Name", "其他"),
        "secondLevel": x.get("lable2Name", "") or "其他",
        "detail": detail,
    }


def fetch_scope(scope, prov):
    rc = home(prov)
    sess = rc.get("sessionid")
    boards = rc.get("lableOneList") or []
    items = []
    print("[%s] session=%s boards=%s" % (scope, sess, [b.get("name") for b in boards]))
    if not boards:
        print("  !! home 未返回板块，provCode=%s 可能受限" % prov)
        return []
    for b in boards:
        l1 = b["id"]
        rq = query(sess, prov, l1)
        lst = rq.get("zoneTitleList") or []
        for x in lst:
            items.append(parse_item(x))
        print("  [%s] count=%s got=%d" % (b.get("name"), rq.get("zoneTitleListCount"), len(lst)))
        time.sleep(0.45)
    seen, uniq = set(), []
    for it in items:
        if it["id"] in seen:
            continue
        seen.add(it["id"]); uniq.append(it)
    return uniq


def load(path):
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def save(path, obj):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(obj, f, ensure_ascii=False, separators=(",", ":"))


def digest_item(it):
    return json.dumps([it.get("id"), it.get("title"), it.get("fee"), it.get("firstLevel")], ensure_ascii=False)


def digest_stable(it):
    """稳定指纹：不含 id（接口 id 可能逐轮漂移），用 标题+资费+一级分类+二级分类 标识业务实体。"""
    return json.dumps([it.get("title", ""), it.get("fee", ""), it.get("firstLevel", ""), it.get("secondLevel", "")], ensure_ascii=False)


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
                "raw_added": raw_added, "raw_removed": raw_removed}
    return {
        "added": len(added), "removed": len(removed), "modified": len(modified),
        "added_names": [x.get("title", "") for x in added][:20],
        "removed_names": [x.get("title", "") for x in removed][:20],
        "modified_names": [x.get("title", "") for x in modified][:20],
        "modified_details": modified_details_for(pmap, modified[:20]),
    }


def build_latest(scopes, datadir):
    sections, prov_stats = [], {}
    q_total = None
    for scope in scopes:
        d = load(os.path.join(datadir, scope + ".json"))
        items = d["items"]
        total = len(items)
        dist = {}
        for it in items:
            fl = it["firstLevel"] or "其他"
            dist[fl] = dist.get(fl, 0) + 1
        if scope == "quanguo":
            q_total = total
        prov_stats[scope] = {"total": total, "onsale": total, "dist": dist}
        sections.append({"section": scope, "name": SCOPES[scope]["name"], "total": total,
                         "onsale": total, "updated": d.get("timestamp") or ""})
    now = time.strftime("%Y-%m-%d %H:%M:%S")
    latest = {"sections": sections, "default": "hunan", "quanguo_total": q_total,
              "prov_total": prov_stats.get("hunan", {}).get("total", 0),
              "prov_stats": prov_stats, "updated": now, "timestamp": now}
    save(os.path.join(datadir, "latest.json"), latest)
    print("latest.json 已生成: quanguo=%s hunan=%s" % (q_total, prov_stats.get("hunan", {}).get("total")))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--prev-dir", required=True)
    ap.add_argument("--out-dir", required=True)
    args = ap.parse_args()
    prev_dir, out_dir = args.prev_dir, args.out_dir
    scopes = list(SCOPES.keys())
    now = time.strftime("%Y-%m-%d %H:%M:%S")
    # 先读上一版
    prev_data = {sc: (load(os.path.join(prev_dir, sc + ".json")) if os.path.exists(os.path.join(prev_dir, sc + ".json")) else None) for sc in scopes}
    for scope in scopes:
        print("=== 抓取 %s (%s) ===" % (scope, SCOPES[scope]["name"]))
        items = fetch_scope(scope, SCOPES[scope]["prov"])
        # 剔除官方混入的测试/作废业务，避免其被当作真实变更写进 history 与推送
        items = filter_test_items(items)
        data = {"scope": scope, "timestamp": now, "items": items}
        save(os.path.join(out_dir, scope + ".json"), data)
        print("[%s] total=%d" % (scope, len(items)))
        time.sleep(1)
    hp = os.path.join(out_dir, "history.json")
    history = load(hp) if os.path.exists(hp) else []
    changes = {}
    for sc in scopes:
        cur = load(os.path.join(out_dir, sc + ".json"))
        if prev_data[sc] is None:
            print("  %s 首次，建基线（不记变化）" % sc)
            continue
        # prev 同步过滤：公开仓历史快照里可能仍残留测试数据，
        # 不过滤会让它们在本轮被判成"下架"而产生误报。
        prev_clean = prev_data[sc]
        if prev_clean and prev_clean.get("items"):
            kept = filter_test_items(prev_clean["items"])
            if len(kept) != len(prev_clean["items"]):
                prev_clean = dict(prev_clean, items=kept)
        r = diff_scope(prev_clean, cur)
        _bt = len((prev_clean or {}).get("items") or [])
        if is_sampling_noise(r, _bt):
            print("    >> 采样噪声：" + str(mark_noise(r, _bt).get("note", "")))
        r = mark_noise(r, _bt)
        changes[sc] = slim_change(r)
    if changes:
        entry = {"ts": now}
        entry.update(changes)
        history.append(entry)
        print("检测到变化:", {k: "add%d/rm%d/mod%d" % (v["added"], v["removed"], v["modified"]) for k, v in changes.items()})
    else:
        print("本次检测：无变化")
    save(hp, history)
    build_latest(scopes, out_dir)
    print("完成，history 共 %d 条" % len(history))


if __name__ == "__main__":
    main()
