#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
回填历史变更记录中「未存快照」的业务字段。

只做一件事：把 added_names / removed_names 里有名字、但 *_details 里没字段的业务，
从该省数据文件的历史版本里找回字段，补进 *_details。

安全约定：
  1) 只新增缺失的键，绝不修改、删除已有内容
  2) 记录条数、各省计数、names 数组一律不动
  3) 回填前后做完整性校验，不一致就直接放弃提交
"""
import json, os, sys, urllib.request, urllib.error

OWNER = "WoShiYiGeManHuaJia"
REPO = "hunan-tariff-site"
BRANCH = "main"
TOKEN = os.environ.get("GITHUB_TOKEN") or os.environ.get("GH_TOKEN") or ""
HDR = {"Authorization": "Bearer " + TOKEN, "User-Agent": "backfill",
       "Accept": "application/vnd.github+json"}

SITES = [
    ("移动", "data"),
    ("联通", "unicom/data"),
    ("电信", "telecom/data"),
    ("广电", "gb/data"),
]

PINYIN = {
    "全网": "quanguo", "全国": "quanguo", "全网(全国)": "quanguo",
    "北京": "beijing", "天津": "tianjin", "上海": "shanghai", "重庆": "chongqing",
    "河北": "hebei", "山西": "shanxi", "河南": "henan", "辽宁": "liaoning",
    "吉林": "jilin", "黑龙江": "heilongjiang", "内蒙古": "neimenggu",
    "江苏": "jiangsu", "浙江": "zhejiang", "安徽": "anhui", "福建": "fujian",
    "江西": "jiangxi", "山东": "shandong", "湖北": "hubei", "湖南": "hunan",
    "广东": "guangdong", "广西": "guangxi", "海南": "hainan", "四川": "sichuan",
    "贵州": "guizhou", "云南": "yunnan", "西藏": "xizang", "陕西": "shaanxi",
    "甘肃": "gansu", "青海": "qinghai", "宁夏": "ningxia", "新疆": "xinjiang",
}


def api(path):
    req = urllib.request.Request("https://api.github.com" + path, headers=HDR)
    with urllib.request.urlopen(req, timeout=90) as r:
        return json.loads(r.read().decode("utf-8", "ignore"))


def raw(path, ref=BRANCH):
    url = "https://raw.githubusercontent.com/%s/%s/%s/%s" % (OWNER, REPO, ref, path)
    req = urllib.request.Request(url, headers={"User-Agent": "backfill"})
    try:
        with urllib.request.urlopen(req, timeout=180) as r:
            return r.read().decode("utf-8", "ignore")
    except urllib.error.HTTPError as e:
        if e.code == 404:
            return None
        raise


def walk_items(obj, out):
    """从任意结构里捞出 (name, fields) 对"""
    if isinstance(obj, dict):
        name = None
        for k in ("name", "业务名称", "title", "方案名称", "planName"):
            v = obj.get(k)
            if isinstance(v, str) and v.strip():
                name = v.strip()
                break
        fld = None
        for k in ("fields", "detail", "details", "字段", "content", "attrs"):
            v = obj.get(k)
            if isinstance(v, dict) and v:
                fld = v
                break
        if name and fld is None:
            # 顶层就是扁平字段
            fld = {k: v for k, v in obj.items()
                   if isinstance(v, (str, int, float)) and k not in
                   ("name", "业务名称", "title", "方案名称", "planName")}
        if name:
            out.append((name, fld or {}))
        for v in obj.values():
            if isinstance(v, (dict, list)):
                walk_items(v, out)
    elif isinstance(obj, list):
        for it in obj:
            if isinstance(it, (dict, list)):
                walk_items(it, out)


def scope_files(data_dir, scope):
    """scope -> 候选数据文件路径"""
    p = PINYIN.get(scope) or PINYIN.get(str(scope).replace("(全国)", "").strip()) or scope
    cand = ["%s/%s.json" % (data_dir, p)]
    if scope not in PINYIN:
        cand.append("%s/%s.json" % (data_dir, scope))
    return cand


def commits_of(path, limit=14):
    try:
        cs = api("/repos/%s/%s/commits?path=%s&per_page=%d" % (OWNER, REPO, path, limit))
    except Exception:
        return []
    return [c["sha"] for c in cs if isinstance(c, dict)]


def main():
    if not TOKEN:
        print("!! 缺少 GITHUB_TOKEN"); sys.exit(1)

    total_fixed = 0
    total_missing = 0
    report = []

    for label, data_dir in SITES:
        hpath = "%s/history.json" % data_dir
        txt = raw(hpath)
        if not txt:
            print("[%s] history.json 不存在，跳过" % label); continue
        try:
            hist = json.loads(txt)
        except Exception as e:
            print("[%s] history.json 解析失败: %s，跳过" % (label, e)); continue
        if not isinstance(hist, list):
            print("[%s] 结构非列表，跳过" % label); continue

        before = json.dumps(hist, ensure_ascii=False, sort_keys=True)

        # 1) 收集缺失
        miss = []   # (idx, scope, kind, name)
        for i, rec in enumerate(hist):
            if not isinstance(rec, dict):
                continue
            for scope, blk in rec.items():
                if scope == "ts" or not isinstance(blk, dict):
                    continue
                for kind in ("added", "removed"):
                    names = blk.get(kind + "_names") or []
                    det = blk.get(kind + "_details") or {}
                    if not isinstance(names, list):
                        continue
                    if not isinstance(det, dict):
                        det = {}
                    for n in names:
                        if isinstance(n, str) and n and n not in det:
                            miss.append((i, scope, kind, n))
        if not miss:
            print("[%s] 无缺失" % label); continue

        print("[%s] 缺失 %d 条，开始回溯" % (label, len(miss)))
        total_missing += len(miss)

        # 2) 按 scope 分组，回溯该省历史版本
        cache = {}          # scope -> {name: fields}
        for scope in sorted({m[1] for m in miss}):
            got = {}
            for fp in scope_files(data_dir, scope):
                for sha in commits_of(fp):
                    m = load_prov_at(fp, sha)
                    if not m:
                        continue
                    need = {n for (_, s, _, n) in miss if s == scope} - set(got)
                    hit = {n: m[n] for n in need if n in m}
                    got.update(hit)
                    if not (need - set(got)):
                        break
                if got:
                    break
            cache[scope] = got
            print("   %s: 找到 %d 个" % (scope, len(got)))

        # 3) 回填（只新增）
        fixed = 0
        for i, scope, kind, n in miss:
            f = cache.get(scope, {}).get(n)
            if not f:
                continue
            rec = hist[i]
            blk = rec.get(scope)
            if not isinstance(blk, dict):
                continue
            key = kind + "_details"
            det = blk.get(key)
            if not isinstance(det, dict):
                det = {}
                blk[key] = det
            if n in det:
                continue
            det[n] = f
            fixed += 1

        after = json.dumps(hist, ensure_ascii=False, sort_keys=True)

        # 4) 完整性校验：条数、计数、names 必须一字不差
        ok = True
        back = json.loads(after)
        if len(back) != len(json.loads(before)):
            ok = False
        else:
            for a, b in zip(json.loads(before), back):
                if a.get("ts") != b.get("ts"):
                    ok = False; break
                for s, b0 in a.items():
                    if s == "ts" or not isinstance(b0, dict):
                        continue
                    b1 = b.get(s, {})
                    for k in ("added", "removed", "modified",
                              "added_names", "removed_names", "modified_names"):
                        if b0.get(k) != b1.get(k):
                            ok = False; break
                    if not ok:
                        break
                if not ok:
                    break
        if not ok:
            print("[%s] !! 校验未通过，放弃写入" % label)
            continue

        with open(hpath, "w", encoding="utf-8") as fh:
            json.dump(hist, fh, ensure_ascii=False)
        total_fixed += fixed
        report.append("%s 补齐 %d/%d" % (label, fixed, len(miss)))
        print("[%s] 补齐 %d/%d，已写回 %s" % (label, fixed, len(miss), hpath))

    print("\n==== 汇总 ====")
    print("缺失合计 %d，补齐 %d" % (total_missing, total_fixed))
    for r in report:
        print("  " + r)


def load_prov_at(path, sha):
    url = "https://raw.githubusercontent.com/%s/%s/%s/%s" % (OWNER, REPO, sha, path)
    req = urllib.request.Request(url, headers={"User-Agent": "backfill"})
    try:
        with urllib.request.urlopen(req, timeout=180) as r:
            txt = r.read().decode("utf-8", "ignore")
    except Exception:
        return {}
    try:
        d = json.loads(txt)
    except Exception:
        return {}
    out = []
    walk_items(d, out)
    return {n: f for n, f in out if f}


if __name__ == "__main__":
    main()
