# -*- coding: utf-8 -*-
"""共享 HTTP 层：连接复用 + gzip + 有界重试 + 全局限速 + 并发工具。

动机（2026-11-09 对广电真实接口实测，非估算）：
  - 开 gzip：单响应 248,020 B → 34,087 B（-86%），解压后条目数完全一致
  - keep-alive 复用连接：每请求省约 71 ms（约 7%）
  - 并发：8 请求串行 5.81s → 8 并发 1.27s（4.6x），4 并发 2.09s（2.8x）

原本三条管线各自用 urllib.urlopen 发请求，问题一致：
  1. 每次请求新建 TCP+TLS 连接，握手成本白白付出
  2. 不发 Accept-Encoding，几百 KB 的 JSON 明文传输
  3. 重试退避在「最后一次失败后还继续 sleep」，纯粹浪费跑批时间

本模块只做传输层，不碰任何业务解析与 diff 逻辑，
调用方把原来的 urlopen 换成这里的一行即可。

环境变量（全部有安全默认值，不配也能跑）：
  HTTP_WORKERS   并发度，默认 6；设为 1 即完全串行（便于 A/B 对比）
  HTTP_MAX_QPS   全局每秒请求上限，默认 8；设 0 关闭限速
  HTTP_TIMEOUT   单请求超时秒数，默认 30
  HTTP_RETRIES   重试次数，默认 4
"""
import gzip
import json
import os
import random
import ssl
import threading
import time
import zlib
from concurrent.futures import ThreadPoolExecutor
from urllib.parse import urlsplit

import http.client

# ── 可调参数 ──
DEFAULT_TIMEOUT = float(os.getenv("HTTP_TIMEOUT") or "30")
DEFAULT_WORKERS = int(os.getenv("HTTP_WORKERS") or "6")
RETRIES = int(os.getenv("HTTP_RETRIES") or "4")
# 全局限速：用令牌间隔代替原来「每个请求固定 sleep」，快时更充分利用、慢时自动让路
MAX_QPS = float(os.getenv("HTTP_MAX_QPS") or "8")

_tls = ssl.create_default_context()
_tls.check_hostname = True
_tls.verify_mode = ssl.CERT_REQUIRED

_local = threading.local()
_qps_lock = threading.Lock()
_next_slot = [0.0]


class FatalHTTPError(Exception):
    """不应重试的错误（如 400/403/404）。上层据此快速降级而不是空转重试。"""


def _pace():
    """全局限速：保证所有线程合计不超过 MAX_QPS。"""
    if MAX_QPS <= 0:
        return
    with _qps_lock:
        now = time.time()
        wait = _next_slot[0] - now
        if wait > 0:
            time.sleep(wait)
            now = _next_slot[0]
        _next_slot[0] = max(now, _next_slot[0]) + 1.0 / MAX_QPS


def _pool():
    p = getattr(_local, "pool", None)
    if p is None:
        p = _local.pool = {}
    return p


def _conn(host, timeout):
    key = (host, timeout)
    p = _pool()
    c = p.get(key)
    if c is None or getattr(c, "sock", None) is None and c.__dict__.get("_closed"):
        c = http.client.HTTPSConnection(host, timeout=timeout, context=_tls)
        p[key] = c
    return c


def _drop(host, timeout):
    c = _pool().pop((host, timeout), None)
    if c is not None:
        try:
            c.close()
        except Exception:
            pass


def request(url, body=None, headers=None, timeout=None, retries=None, method=None):
    """发一次请求，返回 (原始字节, HTTP 状态码)。

    自动处理：gzip/deflate 解压、连接复用、限速、重试与退避。
    4xx（除 408/429）立即抛 FatalHTTPError，不做无意义重试。
    """
    timeout = DEFAULT_TIMEOUT if timeout is None else timeout
    retries = RETRIES if retries is None else retries

    parts = urlsplit(url)
    host = parts.netloc
    path = parts.path + (("?" + parts.query) if parts.query else "")

    hdrs = {"Accept-Encoding": "gzip, deflate"}
    if headers:
        hdrs.update(headers)
    if isinstance(body, (dict, list)):
        body = json.dumps(body).encode("utf-8")
    elif isinstance(body, str):
        body = body.encode("utf-8")
    meth = method or ("POST" if body is not None else "GET")

    last = None
    for a in range(max(1, retries)):
        _pace()
        try:
            c = _conn(host, timeout)
            c.request(meth, path, body=body, headers=hdrs)
            r = c.getresponse()
            raw = r.read()
            enc = (r.getheader("Content-Encoding") or "").lower()
            if enc == "gzip":
                raw = gzip.decompress(raw)
            elif enc == "deflate":
                try:
                    raw = zlib.decompress(raw)
                except zlib.error:
                    raw = zlib.decompress(raw, -zlib.MAX_WBITS)
            if getattr(r, "will_close", False):
                _drop(host, timeout)
            status = r.status
            if 400 <= status < 500 and status not in (408, 429):
                raise FatalHTTPError("HTTP %d: %s" % (status, raw[:180]))
            if status >= 500:
                raise IOError("HTTP %d" % status)
            return raw, status
        except FatalHTTPError:
            raise
        except Exception as e:
            last = e
            _drop(host, timeout)
            if a >= max(1, retries) - 1:
                break                      # ★ 最后一次失败不再 sleep
            # 指数退避 + 抖动，避免多线程同时撞同一秒
            time.sleep((1.2 ** a) * (0.8 + 0.4 * random.random()))
    raise last if last is not None else IOError("request failed: %s" % url)


def post_json(url, body, headers=None, timeout=None, retries=None):
    raw, _ = request(url, body=body, headers=headers, timeout=timeout,
                     retries=retries, method="POST")
    return json.loads(raw.decode("utf-8", "replace"))


def get_json(url, headers=None, timeout=None, retries=None):
    raw, _ = request(url, headers=headers, timeout=timeout, retries=retries,
                     method="GET")
    return json.loads(raw.decode("utf-8", "replace"))


def map_parallel(fn, items, workers=None):
    """保持顺序的并发 map；workers<=1 退化为串行（方便对比与排错）。"""
    items = list(items)
    w = DEFAULT_WORKERS if workers is None else int(workers)
    if w <= 1 or len(items) <= 1:
        return [fn(x) for x in items]
    with ThreadPoolExecutor(max_workers=min(w, len(items))) as ex:
        return list(ex.map(fn, items))


def settings():
    """返回当前生效配置，便于日志打印与排错。"""
    return {"workers": DEFAULT_WORKERS, "max_qps": MAX_QPS,
            "timeout": DEFAULT_TIMEOUT, "retries": RETRIES}
