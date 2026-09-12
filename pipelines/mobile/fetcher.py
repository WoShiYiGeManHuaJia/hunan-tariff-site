# -*- coding: utf-8 -*-
# 抓取模块（纯 HTTP 接口版，零浏览器依赖）
# 相比旧版（Playwright 开浏览器渲染 DOM，约 20 秒）：
#   1) 直接请求数据接口 getTariffListInfo，拿到加密响应后 AES-128-CBC 解密
#   2) 全量一次拉取，无翻页、无渲染等待，两次请求 1~2 秒完成
#   3) 彻底绕开 GitHub Actions 出口 IP 被源站风控、JS 资源加载失败等浏览器路径问题
#
# 接口协议（逆向自页面前端 JS）：
#   - 请求：明文 JSON -> AES-128-CBC(Key/IV 固定) -> hex 大写，POST 到 getTariffListInfo
#   - 响应：{"body":"<hex 密文>"} -> AES-128-CBC 解密 -> 明文 JSON(资费列表)
#   - 板块：tariffAttr=1 为"全网资费"，tariffAttr=2 为"湖南资费"
import concurrent.futures
import json
import os
import random
import ssl
import threading
import time
import uuid
import urllib.request
import urllib.error

from Crypto.Cipher import AES

from config import SECTIONS
from province_table import SECTION_INFO

AES_KEY = b"1234123412ABCDEF"
AES_IV = b"ABCDEF1234123412"

API_URL = (
    "https://h.app.coc.10086.cn/website/nrapigate/nrtariff/new/Tariff/"
    "getTariffListInfo"
)
PAGE_URL = (
    "https://h.app.coc.10086.cn/cmcc-app/pc-pages/"
    "tariffZonePers.html?pageId=834148205904408576&prov=731&channelId=P00000010677"
)
# UA 指纹池：源站按「IP+UA 指纹」隔离限流配额，同一 UA 池总配额有限、耗尽后返回确定性子集。
# 因此每个分类抓取前都轮换一个真实移动端 UA（12 个分类 = 12 个独立配额池），互不挤占。
UA_POOL = [
    "Mozilla/5.0 (Linux; Android 13; SM-S9110) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/120.0 Mobile Safari/537.36",
    "Mozilla/5.0 (Linux; Android 13; SM-S9180) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/119.0 Mobile Safari/537.36",
    "Mozilla/5.0 (Linux; Android 13; ELE-AL00) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/116.0 Mobile Safari/537.36",
    "Mozilla/5.0 (Linux; Android 12; V2141A) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/115.0 Mobile Safari/537.36",
    "Mozilla/5.0 (Linux; Android 12; 2201123C) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/111.0 Mobile Safari/537.36",
    "Mozilla/5.0 (Linux; Android 13; PGT-AN00) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/113.0 Mobile Safari/537.36",
    "Mozilla/5.0 (Linux; Android 12; 21091116AC) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/108.0 Mobile Safari/537.36",
    "Mozilla/5.0 (Linux; Android 11; PDEM30) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/106.0 Mobile Safari/537.36",
    "Mozilla/5.0 (Linux; Android 14; Pixel 8) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/120.0 Mobile Safari/537.36",
    "Mozilla/5.0 (Linux; Android 13; 2304FPN6DC) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/118.0 Mobile Safari/537.36",
    "Mozilla/5.0 (iPhone; CPU iPhone OS 17_2 like Mac OS X) AppleWebKit/605.1.15 "
    "(KHTML, like Gecko) Version/17.2 Mobile/15E148 Safari/604.1",
    "Mozilla/5.0 (iPhone; CPU iPhone OS 16_6 like Mac OS X) AppleWebKit/605.1.15 "
    "(KHTML, like Gecko) Version/16.6 Mobile/15E148 Safari/604.1",
    "Mozilla/5.0 (iPhone; CPU iPhone OS 17_1 like Mac OS X) AppleWebKit/605.1.15 "
    "(KHTML, like Gecko) Version/17.1 Mobile/15E148 Safari/604.1",
    "Mozilla/5.0 (iPhone; CPU iPhone OS 16_5 like Mac OS X) AppleWebKit/605.1.15 "
    "(KHTML, like Gecko) Version/16.5 Mobile/15E148 Safari/604.1",
    "Mozilla/5.0 (Linux; Android 13; 2211133C) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/117.0 Mobile Safari/537.36",
    "Mozilla/5.0 (Linux; Android 12; RMX3300) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/114.0 Mobile Safari/537.36",
    "Mozilla/5.0 (Linux; Android 11; V1938A) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/110.0 Mobile Safari/537.36",
    "Mozilla/5.0 (iPhone; CPU iPhone OS 15_8 like Mac OS X) AppleWebKit/605.1.15 "
    "(KHTML, like Gecko) Version/15.8 Mobile/15E148 Safari/604.1",
    "Mozilla/5.0 (Linux; Android 13; 22081212C) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/116.0 Mobile Safari/537.36",
    "Mozilla/5.0 (Linux; Android 12; CPH2293) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/112.0 Mobile Safari/537.36",
]
UA = UA_POOL[0]  # 每个分类抓取前会再次轮换

# 湖南 14 地市码 -> 中文
HN_CITY = {
    "7310": "长沙", "7311": "株洲", "7300": "岳阳", "7312": "湘潭", "7340": "衡阳",
    "7350": "郴州", "7360": "常德", "7370": "益阳", "7380": "娄底", "7390": "邵阳",
    "7430": "湘西", "7440": "张家界", "7450": "怀化", "7460": "永州",
}
# 省码 -> 中文
PROV_CN = {
    "BJ": "北京", "TJ": "天津", "HE": "河北", "SX": "山西", "NM": "内蒙古",
    "LN": "辽宁", "JL": "吉林", "HL": "黑龙江", "SH": "上海", "JS": "江苏",
    "ZJ": "浙江", "AH": "安徽", "FJ": "福建", "JX": "江西", "SD": "山东",
    "HA": "河南", "HB": "湖北", "HN": "湖南", "GD": "广东", "GX": "广西",
    "HI": "海南", "CQ": "重庆", "SC": "四川", "GZ": "贵州", "YN": "云南",
    "XZ": "西藏", "SN": "陕西", "GS": "甘肃", "QH": "青海", "NX": "宁夏",
    "XJ": "新疆",
}

# 统一输出字段键（缺失/为空补空串，保证快照字段集稳定可比）
FIELD_KEYS = [
    "资费标准", "方案编号", "资费类型", "归属", "适用范围", "适用地区", "销售渠道",
    "上线日期", "下线日期", "有效期限", "在网要求", "退订方式", "违约责任",
    "国内通话", "国内通用流量", "定向流量", "宽带", "移动高清", "权益",
    "超出资费说明", "其他服务内容", "其他说明",
]

# 分类映射：type1=个人/政企，type2=套餐/加装包/营销活动
TYPE1_CN = {"1": "个人资费", "2": "政企资费"}
TYPE2_CN = {"1": "套餐", "2": "加装包", "3": "营销活动"}
# 每个板块要抓的分类组合 (type1, type2)，覆盖 六大类 全量
TYPE_COMBOS = [("1", "1"), ("1", "2"), ("1", "3"),
               ("2", "1"), ("2", "2"), ("2", "3")]
# 分类间请求间隔（秒）。连续请求序列中后段分类会被源站瞬时限流降级(缺量)，
# 实测 8s 间隔可保证 6 个分类全量返回；间隔过大则单轮耗时过久，取 8s 均衡。
# 并发模式下该值仅作为批次间的基础间隔，实际等待远小于串行模式。
FETCH_INTERVAL = float(os.getenv("FETCH_INTERVAL", "8.0"))
# 板块间间隔（秒）。串行模式沿用 FETCH_INTERVAL；并发模式默认 2s，
# 因为并发已把单板块耗时压到秒级，再用 8s 会白白拖长整轮。
SECTION_INTERVAL = float(os.getenv("SECTION_INTERVAL", "2.0"))
# 分类并发度：同一板块内同时发起多少个分类请求。
# 源站按「IP+UA 指纹」隔离限流配额，每个分类用独立 UA，故并发不会互相挤占。
# 默认 3（保守，兼顾速度与安全）；实测抓取不全时可下调为 1（退化为串行）。
# 设为 1 即完全等价于旧的串行行为，可随时回退。
FETCH_WORKERS = max(1, int(os.getenv("FETCH_WORKERS", "3")))


def _s(v):
    return "" if v is None else str(v).strip()


def _fmt_day(s):
    s = _s(s)
    if len(s) == 8 and s.isdigit():
        return "%s年%s月%s日" % (int(s[:4]), int(s[4:6]), int(s[6:8]))
    return s


def _area_cn(s):
    parts = [x.strip() for x in _s(s).split(",") if x.strip()]
    out = []
    for p in parts:
        if p in HN_CITY:
            out.append(HN_CITY[p])
        elif p in PROV_CN:
            out.append(PROV_CN[p])
        elif p and p.isalpha():
            # 未收录省码（如港澳台），保留原码
            out.append(p)
        else:
            out.append(p)
    return "、".join(out)


def _nm_to_fields(nm):
    """把一个 nonModule（具体资费档）映射为中文键值 fields"""
    f = {}
    t1 = str(nm.get("type1") or "1")
    t2 = str(nm.get("type2") or "1")
    f["资费标准"] = (_s(nm.get("fees")) + _s(nm.get("feesUnit"))).strip()
    f["方案编号"] = _s(nm.get("reportNo")) or _s(nm.get("goodsid"))
    f["资费类型"] = TYPE2_CN.get(t2, "套餐")
    f["归属"] = TYPE1_CN.get(t1, "个人资费")
    f["适用范围"] = _s(nm.get("applicablePeople"))
    f["适用地区"] = _area_cn(nm.get("applicableArea"))
    f["销售渠道"] = _s(nm.get("channel"))
    f["上线日期"] = _fmt_day(nm.get("onlineDay"))
    f["下线日期"] = _fmt_day(nm.get("offineDay"))
    f["有效期限"] = _s(nm.get("validPeriod"))
    f["在网要求"] = _s(nm.get("duration"))
    f["退订方式"] = _s(nm.get("unsubscribe"))
    f["违约责任"] = _s(nm.get("responsibility"))
    f["国内通话"] = ("%s分钟" % _s(nm.get("call"))) if _s(nm.get("call")) else ""
    f["国内通用流量"] = _s(nm.get("data")) + _s(nm.get("dataUnit"))
    f["定向流量"] = _s(nm.get("orientTraffic")) + _s(nm.get("orientTrafficUnit"))
    f["宽带"] = _s(nm.get("brandwidth"))
    f["移动高清"] = _s(nm.get("iptv"))
    f["权益"] = _s(nm.get("rights"))
    f["超出资费说明"] = _s(nm.get("extraFees"))
    f["其他服务内容"] = _s(nm.get("otherContent"))
    f["其他说明"] = _s(nm.get("others"))   # 官方「其他说明」详情正文（多行），此前遗漏未采集
    return f


def _pkcs7_unpad(pt):
    if not pt:
        return pt
    p = pt[-1]
    if 1 <= p <= 16 and pt[-p:] == bytes([p]) * p:
        return pt[:-p]
    return pt


def _encrypt(params: dict) -> str:
    plain = json.dumps(params, separators=(",", ":"), ensure_ascii=False).encode()
    pad_len = 16 - (len(plain) % 16)
    plain = plain + bytes([pad_len]) * pad_len
    cipher = AES.new(AES_KEY, AES.MODE_CBC, AES_IV)
    return cipher.encrypt(plain).hex().upper()


def _decrypt(hexstr: str) -> str:
    raw = bytes.fromhex(hexstr)
    cipher = AES.new(AES_KEY, AES.MODE_CBC, AES_IV)
    return _pkcs7_unpad(cipher.decrypt(raw)).decode("utf-8")


def _build_opener():
    ctx = ssl.create_default_context()
    try:
        ctx.options |= ssl.OP_LEGACY_SERVER_CONNECT
    except AttributeError:
        pass
    opener = urllib.request.build_opener(urllib.request.HTTPSHandler(context=ctx))
    return opener


def _is_conn_error(e) -> bool:
    """链接/握手类瞬时错误（GitHub Actions 出口到移动网关偶发 Errno 101
    Network is unreachable、SSL 握手失败、超时等）：源站并未降级，只是
    runner 侧网络抖动，重试后大概率恢复，应加大重试窗口而非归因降级。"""
    if isinstance(e, (urllib.error.URLError, ssl.SSLError, TimeoutError, OSError)):
        return True
    s = str(e)
    return "Network is unreachable" in s or "Errno 101" in s or "timed out" in s.lower()


def _post(opener, body_hex: str) -> str:
    """POST 加密请求。单请求 60s 超时。

    链接/握手类瞬时错误（Errno 101 Network is unreachable 等）：指数退避
    2/4/8/16/30s、最多 6 次重试——此类错误代表 runner 侧网络抖动而非源站
    降级，拉长重试防误判，重试后多数当轮即可恢复；
    其他（业务/解密）错误维持 3/6/12s 共 4 次，避免个别分类连续退避拖垮整轮。"""
    last = None
    for i in range(6):
        try:
            req = urllib.request.Request(
                API_URL, data=body_hex.encode(), method="POST", headers={
                    "User-Agent": ua or UA,
                    "Referer": PAGE_URL,
                    "Accept": "application/json, text/plain, */*",
                    "Content-Type": "application/json; charset=UTF-8",
                    "X-Requested-With": "XMLHttpRequest",
                })
            with opener.open(req, timeout=60) as resp:
                data = json.loads(resp.read().decode("utf-8", "replace"))
            return _decrypt(data.get("body") or "")
        except Exception as e:  # 含 SSL 握手失败等瞬时错误
            last = e
            conn = _is_conn_error(e)
            max_retry = 6 if conn else 4
            wait_seq = (2, 4, 8, 16, 30) if conn else (3, 6, 12)
            if i < max_retry - 1:
                wait = wait_seq[i] if i < len(wait_seq) else wait_seq[-1]
                print(f"[fetch] 请求失败，{wait}s 后重试({i + 2}/{max_retry}): {e}")
                time.sleep(wait)
            else:
                break
    raise last


def _fetch_cell(opener, tariff_attr: str, type1: str, type2: str,
                prov_code: str = "731", ua: str = None):
    """拉取一个板块(tariffAttr)下某个分类(type1/type2)的全量资费，返回 [{name, fields}]（按 name 去重）"""
    params = {
        "cellNum": "99999999999", "province": prov_code, "isPublic": "1",
        "linkScn": "1", "tariffAttr": tariff_attr, "type1": type1, "type2": type2,
        "page": 1, "limit": 10000, "xk": str(uuid.uuid4()),
    }
    plain = _post(opener, _encrypt(params))
    data = json.loads(plain)
    beans = ((data or {}).get("data") or {}).get("beans") or []
    items_by_name = {}
    for b in beans:
        for nm in (b.get("nonModuleList") or []):
            name = _s(nm.get("name"))
            if not name:
                continue
            if name not in items_by_name:
                mapped = _nm_to_fields(nm)
                items_by_name[name] = {
                    "name": name,
                    "fields": {k: (mapped.get(k) or "") for k in FIELD_KEYS},
                }
    return list(items_by_name.values())


# 分类历史峰值文件路径（伴随快照目录持久化）
_PEAK_PATH = os.path.join(
    os.path.dirname(os.path.abspath(__file__)), "snapshots", "peaks.json")
# 分类条目数低于历史峰值的该比例，判定该 UA 指纹池被源站降级
DEGRADE_RATIO = 0.6


def _migrate_peaks(old: dict) -> dict:
    """旧版 peaks.json 为 {attr,t1,t2: 峰值}（31 省共用湖南基准，导致各省被误判降级）。
    升级为按板块隔离 {section: {attr,t1,t2: 峰值}}：
    旧 key 首字段 attr=1 -> quanguo；attr=2 -> 湖南（历史只有全网/湖南跑过）。
    各省无历史峰值，首次运行不判降级、直接建基线，后续各自独立基准。"""
    out = {}
    if not isinstance(old, dict):
        return out
    # 已升级格式：{sec: {key: val}}
    sample = next(iter(old.values()), None)
    if isinstance(sample, dict):
        return old
    for k, v in old.items():
        attr = str(k).split(",")[0]
        sec = "quanguo" if attr == "1" else "hunan"
        out.setdefault(sec, {})[k] = v
    return out


def _load_peaks() -> dict:
    try:
        with open(_PEAK_PATH, "r", encoding="utf-8") as f:
            return _migrate_peaks(json.load(f))
    except Exception:
        return {}


def _save_peaks(peaks: dict):
    try:
        os.makedirs(os.path.dirname(_PEAK_PATH), exist_ok=True)
        with open(_PEAK_PATH, "w", encoding="utf-8") as f:
            json.dump(peaks, f, ensure_ascii=False, indent=2)
    except Exception as e:
        print(f"[fetch] 峰值文件写入失败: {e}")



_ua_idx = 0
_ua_lock = threading.Lock()


def _pick_ua():
    """轮换一个真实移动端 UA（每个分类独立指纹池，互不挤占配额）。

    并发抓取时多线程同时调用，故加锁保证每个分类拿到互不相同的 UA，
    否则两个分类共用同一指纹池会互相挤占限流配额。
    """
    global UA, _ua_idx
    with _ua_lock:
        UA = UA_POOL[_ua_idx % len(UA_POOL)]
        _ua_idx += 1
    return UA


def _section_map() -> dict:
    """板块 -> (tariffAttr, prov_code)。quanguo=全网(a1)；其余省份 a2 + prov_code。"""
    m = {"quanguo": ("1", "731")}
    for sec, (code, _name) in SECTION_INFO.items():
        m.setdefault(sec, ("2", code))
    return m


def _evaluate_degrade(cell_counts: dict, peaks: dict, failed_keys: set):
    """降级自检（纯函数，可单测）。返回 (confirmed, degraded_desc, has_net_error)。

    - 仅基于『本轮成功抓取』的分类判断；抓取失败(网络/接口错误)的分类不参与——
      Errno 101 是 runner 侧网络抖动，缺分类绝不能当作源站降级，否则会 31 省
      错判跳过、整轮无 diff 产出。
    - 总量守恒：成功分类汇总条数 >= 其历史峰值 90% 视为源站真实业务调整，
      不做降级判断（分类间此消彼长）。
    - 保守判定：需 ≥2 个成功分类同时低于峰值 60% 才确认降级（单个分类正常
      业务调整不算）；本轮存在抓取失败分类时一律归因网络异常，不判降级。
    """
    _pk = [k for k in cell_counts if peaks.get(k)]
    _pt = sum((peaks.get(k) or 0) for k in _pk)
    _ct = sum((cell_counts.get(k) or 0) for k in _pk)
    _conserved = bool(_pt) and _ct >= _pt * 0.9
    degraded = []
    if not _conserved:
        for key in _pk:
            cur = cell_counts[key]
            if cur < peaks[key] * DEGRADE_RATIO:
                t1, t2 = key.split(",")[1:]
                degraded.append(
                    f"{TYPE1_CN.get(t1)}/{TYPE2_CN.get(t2)}(本轮{cur}<峰值{int(peaks[key])})")
    has_net_error = bool(failed_keys)
    confirmed = (not has_net_error) and len(degraded) >= 2
    return confirmed, degraded, has_net_error


def _fetch_board(sec: str, attr: str, code: str, opener) -> tuple:
    """抓取单个板块六大分类并合并（fetch_all / fetch_section 共用）。

    并发度 FETCH_WORKERS：同一板块内并行发起多个分类请求，每个分类用独立 UA 指纹。
    返回 (items, errors, cell_counts, failed_keys)。
    """
    merged = {}
    errors = []
    cell_counts = {}
    failed_keys = set()
    lock = threading.Lock()

    def work(t1, t2):
        ua = _pick_ua()  # 每个分类独立 UA 指纹池，避免同一池被打满降级
        key = f"{attr},{t1},{t2}"
        try:
            items = _fetch_cell(opener, attr, t1, t2, code, ua)
            with lock:
                for it in items:
                    # 板块内跨分类业务名不重复；重复时保留首个
                    merged.setdefault(it["name"], it)
                cell_counts[key] = len(items)
        except Exception as e:
            with lock:
                failed_keys.add(key)
                err = f"[{TYPE1_CN.get(t1, t1)}/{TYPE2_CN.get(t2, t2)}] {e}"
                if err not in errors:
                    errors.append(err)
            print(f"[fetch] 板块 {sec} 分类({t1},{t2}) 抓取失败: {e}")

    workers = min(FETCH_WORKERS, len(TYPE_COMBOS))
    with concurrent.futures.ThreadPoolExecutor(max_workers=workers) as ex:
        # 逐批提交：每批 workers 个分类并发，批间留 FETCH_INTERVAL 降温，
        # 避免一次性 6 并发被源站判定为异常流量。
        combos = list(TYPE_COMBOS)
        for i in range(0, len(combos), workers):
            batch = combos[i:i + workers]
            list(ex.map(lambda c: work(*c), batch))
            if i + workers < len(combos):
                time.sleep(FETCH_INTERVAL)

    return list(merged.values()), errors, cell_counts, failed_keys


def _pack(sec: str, items: list, errors: list) -> dict:
    return {
        "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
        "section": sec,
        "items": items,
        "error": ("；".join(errors)) if errors else None,
    }


def fetch_section(sec: str, prov_code: str = "731") -> dict:
    """抓取单个板块(section)的全量资费。供初始化收录/单省刷新调用。"""
    if sec == "quanguo":
        attr, code = "1", "731"
    else:
        attr, code = "2", prov_code
    opener = _build_opener()
    items, errors, _counts, _failed = _fetch_board(sec, attr, code, opener)
    return _pack(sec, items, errors)


def fetch_all() -> dict:
    """返回 {section: {"timestamp", "section", "items", "error"}}。

    每个板块聚合六大类：type1(个人/政企) × type2(套餐/加装包/营销活动) 全量资费。
    防降级：
      - 每轮运行轮换 UA 指纹开启新配额池（源站按 IP+UA 池隔离限流）；
      - 分类并发抓取（FETCH_WORKERS，默认 3），把单轮从 ~25min sleep 压到分钟级；
      - 分类条数低于历史峰值 60% 且 ≥2 个分类同时触发才判定降级，
        整板块标记 error，由上层跳过对比防误报。
    """
    SECTIONS_MAP = _section_map()
    result = {}
    try:
        opener = _build_opener()
        peaks = _load_peaks()
        peaks_updated = False
        for sec in SECTIONS:
            attr, code = SECTIONS_MAP.get(sec, ("1", "731"))
            items, errors, cell_counts, failed_keys = _fetch_board(
                sec, attr, code, opener)

            # 分类级降级自检（保守双阈值 + 失败分类排除 + 网络异常归因）
            #   峰值按板块隔离（peaks[sec]）：各省独立基准，互不影响；
            #   板块无历史峰值（扩建初期/首次）时不判降级，直接建基线。
            peaks_sec = peaks.get(sec) or {}
            confirmed, degraded, has_net_error = _evaluate_degrade(
                cell_counts, peaks_sec, failed_keys)
            if confirmed:
                errors.insert(0, f"DEGRADE:疑似源站降级({'；'.join(degraded)})")
            else:
                changed = False
                for key, cur in cell_counts.items():
                    if cur > peaks_sec.get(key, 0):
                        peaks_sec[key] = cur
                        changed = True
                if changed:
                    peaks[sec] = peaks_sec
                    peaks_updated = True

            # 板块之间休息降温（无论是否降级都要休眠：降级时源站压力大，更该缓一缓）
            if sec != SECTIONS[-1]:
                time.sleep(SECTION_INTERVAL)

            result[sec] = _pack(sec, items, errors)
            if confirmed:
                status = "（确认降级，跳过对比！）"
            elif failed_keys:
                status = f"（{len(failed_keys)} 个分类网络异常，已尽力重试）"
            else:
                status = ""
            print(f"[fetch] 板块 {sec} 抓取 {len(items)} 条{status}")
        if peaks_updated:
            _save_peaks(peaks)
    except Exception as e:
        print(f"[fetch] 抓取整体失败: {e}")
        for sec in SECTIONS:
            result[sec] = _pack(sec, [], [str(e)])
    return result


if __name__ == "__main__":
    r = fetch_all()
    for sec, d in r.items():
        print(sec, len(d.get("items") or []))
