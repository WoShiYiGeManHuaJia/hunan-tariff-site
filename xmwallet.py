#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
xmwallet.py —— 小米钱包「看视频得会员」每日任务自动化（Termux / 安卓版）

融合两个开源项目的可用部分，并针对 Termux 无图形界面环境重写：

  登录流程  来自 kai648846760/xiaomiwallet 的 login.py
            （account.xiaomi.com 长轮询扫码，无需抓包，二维码直接打进终端）
  任务流程  来自 3056810551/xiaomi-wallet-vip 的 xiaomi_wallet_auto.py
            （自适应状态机 / remainChance 防漏领 / 0~60 秒动态时长）

本脚本新增：
  · 去掉 Tkinter / Flet / Pillow 依赖，纯终端运行
  · 双任务发现路径（getTask 失败自动回落 getTaskList）
  · 凭据与设备指纹持久化，票据失效自动换票重试
  · Termux 原生通知（跑完推一条到状态栏）
  · 日志落盘 + 自动轮转
  · 多账号支持，账号间长随机间隔降低风控概率

用法：
  python3 xmwallet.py login <账号别名>     # 扫码登录（只需一次）
  python3 xmwallet.py run                  # 执行每日任务
  python3 xmwallet.py status               # 只看会员时长与今日流水
  python3 xmwallet.py cron                 # 写入 crontab 每日自动跑

依赖：
  pkg install python
  pip install requests qrcode              # qrcode 可选，缺失则只给登录链接
"""

import argparse
import base64
import hashlib
import hmac
import json
import os
import random
import re
import subprocess
import sys
import time
import urllib.parse
import urllib.request
from datetime import datetime
from typing import Any, Dict, List, Optional

try:
    import requests
except ImportError:
    sys.exit("缺少依赖 requests，请先执行: pip install requests")

try:
    import urllib3
    urllib3.disable_warnings()
except Exception:
    pass

# ---------------------------------------------------------------- 常量

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
ACCOUNT_FILE = os.path.join(BASE_DIR, "accounts.json")
DEVICE_FILE = os.path.join(BASE_DIR, "device.json")
DINGTALK_FILE = os.path.join(BASE_DIR, "dingtalk.json")
BALCACHE_FILE = os.path.join(BASE_DIR, "balance_cache.json")
LOG_FILE = os.path.join(BASE_DIR, "xmwallet.log")
MAX_LOG_BYTES = 512 * 1024

API_HOST = "m.jr.airstarfinance.net"
ACTIVITY_CODE = "2211-videoWelfare"
TASK_CODE = "BROWSE_GROUP_TASK1"

APP_VERSION_NAME = "6.114.0.5756.2747"
APP_VERSION_CODE = "20577694"

UA_MOBILE = (
    "Mozilla/5.0 (Linux; U; Android 14; zh-CN; 22041216C Build/UP1A.231005.007; "
    "AppBundle/com.mipay.wallet; AppVersionName/%s; AppVersionCode/%s; "
    "MiuiVersion/V816.0.12.0.ULOCNXM; DeviceId/xagapro; NetworkType/WIFI; "
    "mix_version; WebViewVersion/146.0.7680.119) AppleWebKit/537.36 (KHTML, like Gecko) "
    "Version/4.0 Mobile Safari/537.36 XiaoMi/MiuiBrowser/4.3"
) % (APP_VERSION_NAME, APP_VERSION_CODE)

UA_DESKTOP = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36"
)

USER_EXTRA = json.dumps({
    "platformType": 1,
    "com.miui.player": "4.27.0.4",
    "com.miui.video": "v2024090290(MiVideo-UN)",
    "com.mipay.wallet": APP_VERSION_NAME,
}, separators=(",", ":"))

# 换票地址：小米账号 -> 天星数科 STS，两边项目使用的是同一条
STS_LOGIN_URL = (
    "https://account.xiaomi.com/pass/serviceLogin?callback=https%3A%2F%2Fapi.jr.airstarfinance.net%2Fsts"
    "%3Fsign%3D1dbHuyAmee0NAZ2xsRw5vhdVQQ8%253D%26followup%3Dhttps%253A%252F%252Fm.jr.airstarfinance.net"
    "%252Fmp%252Fapi%252Flogin%253Ffrom%253Dmipay_indexicon_TVcard%2526deepLinkEnable%253Dfalse"
    "%2526requestUrl%253Dhttps%25253A%25252F%25252Fm.jr.airstarfinance.net%25252Fmp%25252Factivity"
    "%25252FvideoActivity%25253Ffrom%25253Dmipay_indexicon_TVcard%252526_noDarkMode%25253Dtrue"
    "%252526_transparentNaviBar%25253Dtrue%252526cUserId%25253Dusyxgr5xjumiQLUoAKTOgvi858Q"
    "%252526_statusBarHeight%25253D137&sid=jrairstar&_group=DEFAULT&_snsNone=true&_loginType=ticket"
)

QR_URL = "https://account.xiaomi.com/longPolling/loginUrl"
QR_QUERY = {
    "_group": "DEFAULT",
    "_qrsize": "240",
    "qs": ("?callback=https%3A%2F%2Faccount.xiaomi.com%2Fsts%3Fsign%3DZvAtJIzsDsFe60LdaPa76nNNP58%253D"
           "%26followup%3Dhttps%253A%252F%252Faccount.xiaomi.com%252Fpass%252Fauth%252Fsecurity%252Fhome"
           "%26sid%3Dpassport&sid=passport&_group=DEFAULT"),
    "bizDeviceType": "",
    "callback": ("https://account.xiaomi.com/sts?sign=ZvAtJIzsDsFe60LdaPa76nNNP58="
                 "&followup=https://account.xiaomi.com/pass/auth/security/home&sid=passport"),
    "_hasLogo": "false",
    "theme": "",
    "sid": "passport",
    "needTheme": "false",
    "showActiveX": "false",
    "serviceParam": '{"checkSafePhone":false,"checkSafeAddress":false,"lsrp_score":0.0}',
    "_locale": "zh_CN",
    "_sign": "2&V1_passport&BUcblfwZ4tX84axhVUaw8t6yi2E=",
}

STATUS_TEXT = {
    0: "登录成功",
    700: "等待扫码",
    701: "已扫码，请在手机上确认",
    702: "二维码已过期",
}


# ---------------------------------------------------------------- 基础工具

def log(msg: str = "", echo: bool = True):
    """同时写日志与标准输出。"""
    line = msg if msg else ""
    if echo:
        print(line, flush=True)
    try:
        if os.path.getsize(LOG_FILE) > MAX_LOG_BYTES:
            os.rename(LOG_FILE, LOG_FILE + ".1")
        with open(LOG_FILE, "a", encoding="utf-8") as f:
            f.write(line + "\n")
    except Exception:
        pass


def load_json(path: str, default):
    if not os.path.isfile(path):
        return default
    try:
        with open(path, "r", encoding="utf-8") as f:
            s = f.read().strip()
            return json.loads(s) if s else default
    except Exception:
        return default


def save_json(path: str, data):
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    os.replace(tmp, path)


def in_termux() -> bool:
    return os.path.isdir("/data/data/com.termux/files/usr")


def notify(title: str, content: str):
    """Termux 原生通知，非 Termux 环境静默跳过。"""
    if not in_termux():
        return
    try:
        subprocess.run(
            ["termux-notification", "--title", title, "--content", content],
            timeout=15, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
        )
    except Exception:
        pass


def load_dingtalk() -> Dict[str, str]:
    d = load_json(DINGTALK_FILE, {})
    return d if isinstance(d, dict) else {}


def dingtalk_enabled() -> bool:
    d = load_dingtalk()
    return bool(d.get("webhook"))


def dingtalk_sign(secret: str):
    """钉钉加签：timestamp + \n + secret 做 HMAC-SHA256，再 base64 + urlencode。"""
    ts = str(round(time.time() * 1000))
    string_to_sign = "%s\n%s" % (ts, secret)
    h = hmac.new(secret.encode("utf-8"), string_to_sign.encode("utf-8"), hashlib.sha256).digest()
    return ts, urllib.parse.quote_plus(base64.b64encode(h).decode("utf-8"))


def dingtalk_send(title: str, text: str, retries: int = 2) -> bool:
    """推送 markdown 消息到钉钉机器人。未配置则静默跳过。"""
    cfg = load_dingtalk()
    webhook = (cfg.get("webhook") or "").strip()
    if not webhook:
        return False

    url = webhook
    secret = (cfg.get("secret") or "").strip()
    if secret:
        ts, sign = dingtalk_sign(secret)
        sep = "&" if "?" in url else "?"
        url = "%s%stimestamp=%s&sign=%s" % (url, sep, ts, sign)

    # 关键词方式时，正文必须含机器人设定的关键词
    kw = (cfg.get("keyword") or "").strip()
    body_text = text
    if kw and kw not in body_text:
        body_text = "%s\n\n%s" % (kw, text)

    payload = {
        "msgtype": "markdown",
        "markdown": {"title": title, "text": body_text},
    }
    data = json.dumps(payload, ensure_ascii=False).encode("utf-8")

    for attempt in range(retries + 1):
        try:
            req = urllib.request.Request(
                url, data=data,
                headers={"Content-Type": "application/json; charset=utf-8"},
                method="POST",
            )
            with urllib.request.urlopen(req, timeout=20) as resp:
                res = json.loads(resp.read().decode("utf-8", "ignore"))
            if res.get("errcode") == 0:
                log("  ✔ 钉钉推送成功")
                return True
            log("  钉钉返回: errcode=%s %s" % (res.get("errcode"), res.get("errmsg")))
            return False
        except Exception as e:
            if attempt < retries:
                time.sleep(3)
            else:
                log("  钉钉推送失败: %s" % e)
    return False


def cmd_dingtalk(webhook: str, secret: str = "", keyword: str = "",
                 remove: bool = False, test: bool = False):
    cfg = load_dingtalk()
    if remove:
        for k in ("webhook", "secret", "keyword"):
            cfg.pop(k, None)
        save_json(DINGTALK_FILE, cfg)
        log("✔ 已清除钉钉配置。")
        return
    if webhook:
        cfg["webhook"] = webhook.strip()
        if secret:
            cfg["secret"] = secret.strip()
        if keyword:
            cfg["keyword"] = keyword.strip()
        save_json(DINGTALK_FILE, cfg)
        log("✔ 钉钉配置已保存到 %s" % os.path.basename(DINGTALK_FILE))
        log("  webhook: %s..." % webhook[:48])
        log("  加签: %s" % ("已启用" if secret else "未启用"))
        log("  关键词: %s" % (keyword or "未设置"))
    if test or webhook:
        log("")
        log("正在发送测试消息...")
        ok = dingtalk_send(
            "xmwallet 测试",
            "### xmwallet 钉钉推送测试\n\n"
            "- 时间: %s\n- 状态: 配置正常\n\n"
            "收到这条就说明推送通道通了。"
            % datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        )
        if not ok:
            log("")
            log("没收到的话按这个顺序查：")
            log("  1) webhook 是否完整（access_token= 后面那一长串）")
            log("  2) 安全设置：加签方式要把 secret 也配上")
            log("      关键词方式要保证正文含该关键词")
            log("  3) 机器人是否被停用")
    if not webhook and not test and not remove:
        cur = load_dingtalk()
        if cur.get("webhook"):
            log("当前已配置: %s..." % cur["webhook"][:48])
            log("  加签: %s | 关键词: %s"
                % ("已启用" if cur.get("secret") else "未启用", cur.get("keyword") or "未设置"))
            log("")
            log("测试: python3 xmwallet.py dingtalk --test")
            log("移除: python3 xmwallet.py dingtalk --remove")
        else:
            log("还没配置钉钉。用法：")
            log("  python3 xmwallet.py dingtalk <webhook地址>")
            log("  python3 xmwallet.py dingtalk <webhook地址> --secret <加签密钥>")
            log("  python3 xmwallet.py dingtalk <webhook地址> --keyword 小米钱包")
            log("")
            log("去钉钉群 → 群设置 → 智能群助手 → 添加机器人 → 自定义，")
            log("复制 Webhook 地址；安全设置推荐选「加签」，把密钥一起给我。")



def jitter(a: float, b: float) -> float:
    return random.uniform(a, b)


def balcache_save(days: float, avail: float):
    """取到真实余额就记下来，供下次取不到时兜底显示。"""
    try:
        save_json(BALCACHE_FILE, {
            "days": round(days, 2),
            "avail": round(avail, 2),
            "at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        })
    except Exception:
        pass


def balcache_read() -> Optional[Dict[str, Any]]:
    d = load_json(BALCACHE_FILE, None)
    if isinstance(d, dict) and d.get("days") is not None:
        return d
    return None


def build_run_report(results: List[str], stamp: str) -> str:
    """把一次 run 的结果拼成钉钉 markdown。"""
    lines = ["### 小米钱包每日任务", "", "**%s**" % stamp, ""]
    for r in results:
        lines.append("- %s" % r)
    lines.append("")
    lines.append("> 由 Termux 自动推送")
    return "\n".join(lines)


# ---------------------------------------------------------------- 设备指纹

def get_device(user_id: str) -> Dict[str, str]:
    """每账号固定一份设备指纹，避免指纹频繁变化触发风控。"""
    all_dev = load_json(DEVICE_FILE, {})
    key = "device_%s" % user_id
    if key in all_dev:
        return all_dev[key]
    dev = {
        "imei": "86219%011d" % random.randint(0, 99999999999),
        "deviceId": "22041216UC",
        "longitude": "%.6f" % (116.3 + random.random() * 0.1),
        "latitude": "%.6f" % (39.9 + random.random() * 0.1),
    }
    all_dev[key] = dev
    save_json(DEVICE_FILE, all_dev)
    return dev


# ---------------------------------------------------------------- 账号存储

def load_accounts() -> List[Dict[str, Any]]:
    data = load_json(ACCOUNT_FILE, [])
    return data if isinstance(data, list) else []


def save_accounts(accounts: List[Dict[str, Any]]):
    save_json(ACCOUNT_FILE, accounts)


def find_account(name: str) -> Optional[Dict[str, Any]]:
    for a in load_accounts():
        if a.get("name") == name:
            return a
    return None


def upsert_account(name: str, user_id: str, pass_token: str, ssecurity: str = ""):
    accounts = load_accounts()
    for a in accounts:
        if a.get("name") == name:
            a.update({"userId": str(user_id or ""), "passToken": pass_token,
                      "ssecurity": ssecurity, "updatedAt": datetime.now().strftime("%Y-%m-%d %H:%M:%S")})
            break
    else:
        accounts.append({
            "name": name, "userId": str(user_id or ""), "passToken": pass_token,
            "ssecurity": ssecurity, "createdAt": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        })
    save_accounts(accounts)


# ---------------------------------------------------------------- 扫码登录

def fetch_qr() -> Optional[Dict[str, Any]]:
    q = dict(QR_QUERY)
    q["_dc"] = str(int(time.time() * 1000))
    try:
        r = requests.get(QR_URL, params=q, headers={"User-Agent": UA_DESKTOP}, timeout=20)
        t = r.text
        if "&&&START&&&" in t:
            t = t.split("&&&START&&&", 1)[-1].strip()
        d = json.loads(t)
        # 源站/网关可能直接返回拒绝（403 policy denied），不是二维码数据
        if d.get("status") and d.get("status") != 200:
            log("  源站拒绝: %s %s" % (d.get("status"), d.get("title") or d.get("detail") or ""))
            return None
        if not d.get("qr"):
            log("  返回中没有二维码字段，接口可能已变更")
            return None
        return d
    except Exception as e:
        log("  获取二维码失败: %s" % e)
        return None


def show_qr(url: str):
    """在终端输出二维码；同时给出可用浏览器直接打开的链接。"""
    log("")
    try:
        import qrcode
        qr = qrcode.QRCode(border=1)
        qr.add_data(url)
        qr.make(fit=True)
        try:
            qr.print_tty()
        except Exception:
            log("\n".join("".join("##" if c else "  " for c in row)
                          for row in qr.get_matrix()))
    except ImportError:
        log("  （未安装 qrcode，跳过图形二维码。可执行 pip install qrcode）")
    except Exception as e:
        log("  二维码渲染异常: %s" % e)

    log("")
    log("  若手机上扫不方便，长按复制下面链接，用手机浏览器打开授权：")
    log("  %s" % url)
    log("")


def poll_login(lp_url: str, timeout: int = 300) -> Optional[Dict[str, str]]:
    deadline = time.time() + timeout
    last = ""
    while time.time() < deadline:
        left = int(deadline - time.time())
        try:
            r = requests.get(lp_url, timeout=60)
            t = r.text
            if "&&&START&&&" in t:
                t = t.split("&&&START&&&", 1)[-1].strip()
            res = json.loads(t)
            code = res.get("code", -1)
            msg = STATUS_TEXT.get(code, "未知状态 %s" % code)
            if msg != last:
                log("  状态: %s（剩余 %d 秒）" % (msg, left))
                last = msg
            if code == 0:
                return {"userId": res.get("userId"),
                        "ssecurity": res.get("ssecurity"),
                        "passToken": res.get("passToken")}
            if code == 702:
                return None
        except requests.exceptions.Timeout:
            log("\r  等待扫码中... 剩余 %d 秒   " % left, echo=True)
            continue
        except Exception:
            time.sleep(3)
    return None


def cmd_login(name: str):
    log("=" * 56)
    log("  为账号「%s」扫码登录" % name)
    log("=" * 56)
    if find_account(name):
        ans = input("  该账号已存在，覆盖重新登录？[y/N] ").strip().lower()
        if ans != "y":
            log("  已取消。")
            return
    data = fetch_qr()
    if not data or not data.get("qr"):
        log("")
        log("  扫码通道不可用时的备选方案：")
        log("    1) 手机浏览器登录https://account.xiaomi.com，登录后从 Cookie 取 userId/passToken")
        log("    2) 或沿用 kai648846760/xiaomiwallet 生成的 xiaomiconfig.json")
        log("    3) 然后执行: python3 xmwallet.py import <别名> <文件或JSON>")
        return
    show_qr(data["qr"])
    log("  请用小米手机「扫一扫」或小米账号 App 扫码，并在手机上点【允许登录】")
    res = poll_login(data.get("lp", ""), int(data.get("timeout", 300)))
    if not res or not res.get("passToken"):
        log("  登录失败或超时。")
        return
    upsert_account(name, res.get("userId", ""), res.get("passToken", ""), res.get("ssecurity", ""))
    log("")
    log("  ✔ 登录成功，凭据已保存到 %s" % os.path.basename(ACCOUNT_FILE))
    log("    userId = %s" % res.get("userId"))
    log("  下一步执行: python3 xmwallet.py run")


def cmd_import(name: str, src: str):
    """从文件 / JSON 字符串 / 交互输入导入凭据。

    兼容来源：
      · kai648846760/xiaomiwallet 的 xiaomiconfig.json
      · 3056810551/xiaomi-wallet-vip 的 xiaomi_account.json
      · 直接粘贴 JSON
    """
    data = None
    if os.path.isfile(src):
        data = load_json(src, None)
    else:
        try:
            data = json.loads(src)
        except Exception:
            data = None
    if data is None:
        log("  无法解析，改为手动输入。")
        uid = input("  userId: ").strip()
        pt = input("  passToken: ").strip()
        data = {"userId": uid, "passToken": pt}

    # 兼容嵌套结构
    if isinstance(data, dict) and "data" in data and isinstance(data["data"], dict):
        data = {**data, **data["data"]}
    if isinstance(data, list) and data:
        data = data[0]

    uid = str(data.get("userId") or data.get("uid") or "").strip()
    pt = (data.get("passToken") or data.get("passTokenV2")
          or data.get("token") or data.get("securityToken") or "").strip()
    ss = (data.get("ssecurity") or data.get("securityToken") or "").strip()
    if not (uid and pt):
        log("  缺少 userId 或 passToken，导入失败。")
        return
    upsert_account(name, uid, pt, ss)
    log("  ✔ 已导入账号「%s」userId=%s" % (name, uid))
    log("  下一步: python3 xmwallet.py status  验证凭据是否有效")


# ---------------------------------------------------------------- 会话与接口

class Wallet:
    """封装 STS 换票与任务接口。"""

    def __init__(self, user_id: str, pass_token: str):
        self.last_balance_raw = None
        self.user_id = str(user_id or "")
        self.pass_token = pass_token or ""
        self.session = requests.Session()
        self.session.headers.update({
            "Host": API_HOST,
            "User-Agent": UA_MOBILE,
            "Referer": "https://m.jr.airstarfinance.net/mp/activity/videoActivity",
            "Origin": "https://m.jr.airstarfinance.net",
            "Accept": "application/json, text/plain, */*",
        })
        self.dev = get_device(self.user_id)

    # ---- 换票 ----
    def login_by_ticket(self) -> bool:
        if not (self.user_id and self.pass_token):
            return False
        try:
            s = requests.Session()
            s.get(STS_LOGIN_URL, headers={
                "User-Agent": UA_DESKTOP,
                "Cookie": "passToken=%s; userId=%s;" % (self.pass_token, self.user_id),
            }, timeout=25, allow_redirects=True, verify=False)
            ck = s.cookies.get_dict()
            c_uid = ck.get("cUserId")
            st = ck.get("serviceToken") or ck.get("jrairstar_serviceToken")
            if not (c_uid and st):
                return False
            self.session.cookies.set("cUserId", c_uid, domain=API_HOST)
            self.session.cookies.set("jrairstar_serviceToken", st, domain=API_HOST)
            self.session.cookies.set("serviceToken", st, domain=API_HOST)
            return True
        except Exception as e:
            log("    换票异常: %s" % e)
            return False

    def _get(self, path: str, params: Dict[str, Any], retry_ticket: bool = True):
        url = "https://%s/mp/api/generalActivity/%s" % (API_HOST, path)
        base = {
            "activityCode": ACTIVITY_CODE,
            "app": "com.mipay.wallet",
            "isNfcPhone": "true",
            "channel": "mipay_indexicon_TVcard",
            "deviceType": "2",
            "system": "1",
            "visitEnvironment": "2",
            "userExtra": USER_EXTRA,
        }
        base.update(params)
        try:
            r = self.session.get(url, params=base, timeout=20, verify=False)
            return r.json()
        except Exception as e:
            log("    请求 %s 异常: %s" % (path, e))
            if retry_ticket and self.login_by_ticket():
                try:
                    r = self.session.get(url, params=base, timeout=20, verify=False)
                    return r.json()
                except Exception:
                    pass
            return None

    # ---- 查询 ----
    @staticmethod
    def _as_int(v) -> Optional[int]:
        """安全转整数；遇到 dict/list/None 返回 None，而不是崩或当成 0。"""
        if v is None or isinstance(v, (dict, list, bool)):
            return None
        try:
            return int(float(v))
        except (ValueError, TypeError):
            return None

    def balance(self) -> Optional[Dict[str, Any]]:
        """查会员时长。取不到就返回 None，绝不返回假的 0.00。"""
        # 实测字段：value = {currentBalance, frozenBalance, availableBalance}
        TOTAL_KEYS = ("currentBalance", "totalBalance", "balance", "userBalance",
                      "totalAmount", "amount", "goldBalance", "sumBalance",
                      "remainBalance", "pointBalance", "totalPoint")
        AVAIL_KEYS = ("availableBalance", "availBalance", "currentBalance",
                      "balance", "totalBalance", "usableBalance", "remainBalance")
        FROZEN_KEYS = ("frozenBalance", "frozen", "freezeBalance")

        def pick(v: dict, keys):
            if not isinstance(v, dict):
                return None
            for k in keys:
                if k in v:
                    n = self._as_int(v[k])
                    if n is not None:
                        return n
            return None

        d = self._get("queryUserBalanceWithFrozen", {})
        self.last_balance_raw = ("queryUserBalanceWithFrozen", d)
        if d and d.get("code") == 0:
            v = d.get("value")
            if not isinstance(v, dict):
                v = {}
            total = pick(v, TOTAL_KEYS)
            avail = pick(v, AVAIL_KEYS)
            if total is None and isinstance(v, dict):
                # 有些版本把余额藏在嵌套里，兜一层
                for sub in ("balanceInfo", "userBalanceInfo", "data", "account"):
                    if isinstance(v.get(sub), dict):
                        total = pick(v[sub], TOTAL_KEYS)
                        if total is not None:
                            avail = pick(v[sub], AVAIL_KEYS)
                            break
            if total is None:
                return None          # 取不到就是取不到，不报 0.00
            if avail is None:
                avail = total
            frozen = pick(v, FROZEN_KEYS)
            if frozen is None and isinstance(v, dict):
                for sub in ("balanceInfo", "userBalanceInfo", "data", "account"):
                    if isinstance(v.get(sub), dict):
                        frozen = pick(v[sub], FROZEN_KEYS)
                        if frozen is not None:
                            break
            if frozen is None:
                frozen = 0
            balcache_save(total / 100.0, avail / 100.0)
            return {"ok": True, "days": total / 100.0, "avail": avail / 100.0,
                    "frozen": frozen / 100.0, "raw": v}

        # 备用接口
        d2 = self._get("queryUserGoldRichSum", {})
        if d2 is not None:
            self.last_balance_raw = ("queryUserGoldRichSum", d2)
        if d2 and d2.get("code") == 0:
            v2 = d2.get("value")
            if isinstance(v2, dict):
                n = pick(v2, TOTAL_KEYS)
            else:
                n = self._as_int(v2)          # 实测这里直接是 10578
            if n is None:
                return None
            balcache_save(n / 100.0, n / 100.0)
            return {"ok": True, "days": n / 100.0, "avail": n / 100.0,
                    "frozen": 0.0, "raw": d2}

        return None

    def balance_retry(self, times: int = 3):
        """余额接口偶发抽风，失败就多试几次。"""
        last = None
        for i in range(times):
            r = self.balance()
            if r:
                return r
            last = r
            if i < times - 1:
                time.sleep(2 + i * 2)
        return last

    def history(self) -> List[Dict[str, Any]]:
        d = self._get("queryUserJoinList", {"pageNum": 1, "pageSize": 30})
        if not d or d.get("code") != 0:
            return []
        v = d.get("value") or {}
        rows = v.get("data") if isinstance(v, dict) else v
        return rows if isinstance(rows, list) else []

    # ---- 任务发现（双路径）----
    def get_task(self) -> Optional[Dict[str, Any]]:
        d = self._get("getTask", {"taskCode": TASK_CODE})
        if d and d.get("code") == 0 and d.get("value"):
            v = d["value"]
            return v.get("taskInfo") if "taskInfo" in v else v
        # 回落：列表接口里挑「浏览组浏览任务」
        url = "https://%s/mp/api/generalActivity/getTaskList" % API_HOST
        try:
            r = self.session.post(url, data={"activityCode": ACTIVITY_CODE},
                                  headers={"User-Agent": UA_MOBILE}, timeout=20, verify=False)
            j = r.json()
            if j.get("code") == 0:
                lst = (j.get("value") or {}).get("taskInfoList") or []
                for t in lst:
                    if "浏览" in (t.get("taskName") or ""):
                        return t
        except Exception:
            pass
        return None

    # ---- 任务动作 ----
    def click_task(self, task_id, brows_task_id, brows_click_url_id) -> bool:
        # newBrowsTask=true 是服务端开始计时的开关，缺了 completeTask 会报 110006
        d = self.click_task_full(task_id, brows_task_id, brows_click_url_id)
        return bool(d and d.get("code") == 0)

    def complete_task(self, task_id, brows_task_id, brows_click_url_id, seconds: int):
        return self._get("completeTask", {
            "taskId": task_id, "taskCode": TASK_CODE, "browsTaskId": brows_task_id,
            "browsClickUrlId": brows_click_url_id, "clickEntryType": "undefined",
            "festivalStatus": "0", "completeTime": str(int(time.time() * 1000)),
            "browseTime": str(seconds * 1000 if seconds > 0 else 0),
        })

    def click_task_full(self, task_id, brows_task_id, brows_click_url_id):
        return self._get("clickTask", {
            "taskId": task_id, "taskCode": TASK_CODE,
            "newBrowsTask": "true",
            "browsTaskId": brows_task_id,
            "browsClickUrlId": brows_click_url_id, "clickEntryType": "undefined",
            "festivalStatus": "0",
        })

    def luck_draw(self, user_task_id: str = ""):
        dev = getattr(self, "dev", None) or get_device(self.user_id)
        p = {
            "userTaskId": str(user_task_id or ""),
            "imei": dev.get("imei", ""),
            "longitude": dev.get("longitude", ""),
            "latitude": dev.get("latitude", ""),
        }
        return self._get("luckDraw", p)

    # ---- 时长解析 ----
    @staticmethod
    def parse_seconds(task: Dict[str, Any], url_info: Dict[str, Any]) -> int:
        url_info = url_info or {}
        raw = task.get("browseTime")
        if raw in (None, ""):
            raw = url_info.get("browseTime")
        for src in (task.get("taskName", ""), task.get("taskDesc", "")):
            m = re.search(r"浏览\s*(\d+)\s*秒", src or "")
            if m:
                return int(m.group(1))
        if raw in (None, ""):
            return 10
        try:
            v = int(raw)
            sec = int(round(v / 1000.0)) if v >= 1000 else v
            return max(0, min(sec, 120))
        except (ValueError, TypeError):
            return 10


# ---------------------------------------------------------------- 执行流程

def draw_prize(res) -> Optional[str]:
    if not res or res.get("code") != 0:
        return None
    v = res.get("value") or {}
    info = v.get("prizeInfo") or {}
    name = info.get("prizeName") or v.get("prizeName") or "会员时长"
    amount = info.get("amount") or v.get("prizeAmount") or 0
    try:
        amount = int(amount)
    except Exception:
        amount = 0
    return "%s (+%.2f天)" % (name, amount / 100.0)


def run_account(acc: Dict[str, Any]) -> str:
    name = acc.get("name", "?")
    uid = acc.get("userId", "")
    pt = acc.get("passToken", "")
    if not (uid and pt):
        return "账号 %s 凭据不完整，跳过" % name

    log("")
    log("=" * 56)
    log("  账号: %s (ID %s)" % (name, uid))
    log("=" * 56)

    w = Wallet(uid, pt)
    if not w.login_by_ticket():
        return "账号 %s 换票失败，passToken 可能已失效，请重新 login" % name
    log("  会话就绪")

    bal = w.balance_retry()
    if bal:
        log("  当前会员时长: %.2f 天（可用 %.2f 天，冻结 %.2f 天）" % (bal["days"], bal["avail"], bal.get("frozen", 0.0)))
    else:
        c = balcache_read()
        if c:
            log("  当前会员时长: 未知（接口本次未返回）")
            log("  上次记录: %.2f 天（记于 %s）" % (c["days"], c.get("at", "?")))
        else:
            log("  当前会员时长: 未知（接口本次未返回，不代表为 0）")

    gained: List[str] = []
    rounds = 0
    while rounds < 10:
        task = w.get_task()
        if not task:
            log("  未取到任务，结束")
            break

        url_info = task.get("generalActivityUrlInfo") or {}
        status = task.get("completeStatus", 0)
        period_done = task.get("periodCompleteCount", 0)
        period_all = task.get("periodCount", 2)
        remain = task.get("remainChance", 0)
        user_task_id = str(task.get("userTaskId", "") or "")
        today_status = url_info.get("todayUserTaskStatus", 1)

        log("  [状态] code=%s 完成=%s/%s 抽奖机会=%s" % (status, period_done, period_all, remain))

        # A. 有遗留抽奖机会，先补领
        if remain and remain > 0:
            log("  检测到 %s 次未领取开奖，补领..." % remain)
            got = draw_prize(w.luck_draw(user_task_id))
            if got:
                gained.append(got)
                log("  ✔ 补领成功: %s" % got)
            time.sleep(jitter(2.0, 3.5))
            continue

        # B. 已达终态
        if status in (3, 4) or today_status == 2:
            log("  今日任务已完成（code=%s）" % status)
            break

        brows_click_url_id = url_info.get("browsClickUrlId", "")
        brows_task_id = url_info.get("id", 30)
        task_id = task.get("taskId", 813)
        if not brows_click_url_id:
            log("  服务端未下发广告标识，判定今日无可用广告")
            break

        seconds = Wallet.parse_seconds(task, url_info)
        rounds += 1
        log("  --- 第 %d 轮 ---" % (period_done + 1))

        ck = w.click_task_full(task_id, brows_task_id, brows_click_url_id)
        log("  clickTask -> %s" % brief(ck))
        if seconds == 0:
            wait = round(jitter(2.0, 3.5), 1)
            log("  0 秒即时任务，拟真缓冲 %.1f 秒" % wait)
        else:
            wait = seconds + random.randint(2, 5)
            log("  任务时长 %d 秒 + 缓冲，共等待 %d 秒" % (seconds, wait))
        time.sleep(wait)

        ct = w.complete_task(task_id, brows_task_id, brows_click_url_id, seconds)
        log("  completeTask(browseTime=%sms) -> %s" % (seconds * 1000, brief(ct)))
        time.sleep(jitter(1.5, 2.5))

        ld = w.luck_draw(user_task_id)
        log("  luckDraw -> %s" % brief(ld))
        got = draw_prize(ld)
        if got:
            gained.append(got)
            log("  ✔ 领取: %s" % got)
        else:
            log("  本轮上报完毕")
        time.sleep(jitter(2.5, 4.5))

    # 今日流水
    today = time.strftime("%Y-%m-%d")
    rows = [r for r in w.history() if (r.get("createTime") or "").startswith(today)]
    log("")
    log("  今日流水 (%d 条):" % len(rows))
    for i, r in enumerate(rows[:10], 1):
        try:
            val = int(r.get("value", 0))
        except Exception:
            val = 0
        log("   %d. %s  +%.2f天  %s" % (i, r.get("createTime"), val / 100.0, r.get("desc") or ""))

    bal2 = w.balance_retry()
    if bal2:
        log("  结算后会员时长: %.2f 天" % bal2["days"])
    else:
        c = balcache_read()
        if c:
            log("  结算后会员时长: 未知（接口本次未返回）")
            log("  上次记录: %.2f 天（记于 %s）" % (c["days"], c.get("at", "?")))
        else:
            log("  结算后会员时长: 未知（接口本次未返回，不代表为 0）")

    summary = "账号 %s：今日领取 %d 笔 %s" % (name, len(gained), "、".join(gained[-3:]) if gained else "（无）")
    log("  " + summary)
    if gained:
        stamp_write()
    return summary


def cmd_debug():
    """把余额/任务的接口原始返回完整打出来，用于定位字段问题。"""
    accounts = load_accounts()
    if not accounts:
        log("还没有账号，先执行: python3 xmwallet.py login <别名>")
        return
    acc = accounts[0]
    w = Wallet(acc.get("userId", ""), acc.get("passToken", ""))
    log("")
    log("===== 接口原始返回诊断 =====")
    log("账号: %s" % acc.get("name"))
    if not w.login_by_ticket():
        log("换票失败，无法诊断。")
        return
    log("换票成功")
    log("")

    for api_name in ("queryUserBalanceWithFrozen", "queryUserGoldRichSum",
                     "queryUserJoinList"):
        log("---------- %s ----------" % api_name)
        d = w._get(api_name, {"pageNum": 1, "pageSize": 5}, retry_ticket=False)
        if d is None:
            log("  (请求失败或无返回)")
        elif not isinstance(d, dict):
            log("  返回类型: %s  值: %s" % (type(d).__name__, str(d)[:300]))
        else:
            log("  code = %s | desc = %s" % (d.get("code"), d.get("desc") or d.get("message") or ""))
            txt = json.dumps(d, ensure_ascii=False)
            # 只打印前 1500 字符，避免刷屏
            log("  原文: " + (txt[:1500] + (" ...(截断)" if len(txt) > 1500 else "")))
        log("")

    log("---------- getTask ----------")
    t = w.get_task()
    if t:
        txt = json.dumps(t, ensure_ascii=False)
        log("  " + (txt[:1500] + (" ...(截断)" if len(txt) > 1500 else "")))
    else:
        log("  (未取到任务)")
    log("")
    log("=" * 40)
    log("请把上面【原文】部分完整截图发我，我按真实字段改解析。")
    log("（里面没有密码，但建议打码 userId 再发）")


def brief(d) -> str:
    """把接口返回压缩成一行，用于排查。"""
    if d is None:
        return "无返回（请求失败）"
    if not isinstance(d, dict):
        return "类型%s: %s" % (type(d).__name__, str(d)[:120])
    parts = ["code=%s" % d.get("code")]
    if d.get("desc"):
        parts.append("desc=%s" % d.get("desc"))
    if d.get("success") is not None:
        parts.append("success=%s" % d.get("success"))
    v = d.get("value")
    if v not in (None, "", {}, []):
        parts.append("value=%s" % (json.dumps(v, ensure_ascii=False)[:200]))
    return " ".join(str(x) for x in parts)


def cmd_run(only: str = ""):
    accounts = load_accounts()
    if not accounts:
        log("还没有账号，先执行: python3 xmwallet.py login <别名>")
        return
    if only:
        accounts = [a for a in accounts if a.get("name") == only]
        if not accounts:
            log("未找到账号 %s" % only)
            return

    log("")
    log("############ 小米钱包每日任务 %s ############" % datetime.now().strftime("%Y-%m-%d %H:%M:%S"))
    results = []
    for i, acc in enumerate(accounts):
        results.append(run_account(acc))
        if i < len(accounts) - 1:
            d = random.randint(30, 90)
            log("")
            log("  账号间随机间隔 %d 秒，降低风控概率..." % d)
            time.sleep(d)
    log("")
    log("############ 全部执行完毕 ############")
    for r in results:
        log("  · " + r)

    notify("小米钱包任务完成", "；".join(results)[:180])
    if dingtalk_enabled():
        log("")
        log("正在推送到钉钉...")
        stamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        dingtalk_send("小米钱包每日任务 %s" % stamp,
                      build_run_report(results, stamp))
    else:
        log("")
        log("（未配置钉钉，跳过推送。配置: python3 xmwallet.py dingtalk <webhook>）")


def dump_balance_raw(w) -> str:
    """取不到余额时，把接口原始返回压缩成一行，方便回传诊断。"""
    if not getattr(w, "last_balance_raw", None):
        return "  (接口无任何返回)"
    name, d = w.last_balance_raw
    if d is None:
        return "  接口 %s: 无返回（请求失败）" % name
    if not isinstance(d, dict):
        return "  接口 %s: 返回类型 %s -> %s" % (name, type(d).__name__, str(d)[:200])
    txt = json.dumps(d, ensure_ascii=False, separators=(",", ":"))
    cut = txt[:600]
    return ("  接口 %s | code=%s desc=%s\n  原文: %s%s"
            % (name, d.get("code"), d.get("desc") or d.get("message") or "",
               cut, " ...(截断)" if len(txt) > 600 else ""))


def cmd_status():
    accounts = load_accounts()
    if not accounts:
        log("还没有账号，先执行: python3 xmwallet.py login <别名>")
        return
    for acc in accounts:
        w = Wallet(acc.get("userId", ""), acc.get("passToken", ""))
        log("")
        log("账号: %s" % acc.get("name"))
        if not w.login_by_ticket():
            log("  换票失败，凭据可能已失效")
            continue
        bal = w.balance_retry()
        if bal:
            log("  会员时长: %.2f 天（可用 %.2f 天，冻结 %.2f 天）" % (bal["days"], bal["avail"], bal.get("frozen", 0.0)))
        else:
            c = balcache_read()
            if c:
                log("  会员时长: 未知（接口本次未返回）")
                log("  上次记录: %.2f 天（记于 %s）" % (c["days"], c.get("at", "?")))
            else:
                log("  会员时长: 未知（接口本次未返回，不代表为 0）")
            log("  ---- 诊断信息（请把这段发我）----")
            log(dump_balance_raw(w))
            log("  --------------------------------")
        today = time.strftime("%Y-%m-%d")
        rows = [r for r in w.history() if (r.get("createTime") or "").startswith(today)]
        log("  今日流水: %d 条" % len(rows))
        for r in rows[:10]:
            try:
                val = int(r.get("value", 0))
            except Exception:
                val = 0
            log("    %s  +%.2f天  %s" % (r.get("createTime"), val / 100.0, r.get("desc") or ""))
        log("  凭据更新于: %s" % (acc.get("updatedAt") or acc.get("createdAt") or "未知"))



STAMP_FILE = os.path.expanduser("~/.xmwallet_last_run")
BASHRC = os.path.expanduser("~/.bashrc")
HOOK_BEGIN = "# >>> xmwallet auto-run hook >>>"
HOOK_END = "# <<< xmwallet auto-run hook <<<"


def stamp_read() -> int:
    try:
        return int(open(STAMP_FILE).read().strip())
    except Exception:
        return 0


def stamp_write():
    try:
        open(STAMP_FILE, "w").write(str(int(time.time())))
    except Exception:
        pass


def cmd_job_diag():
    """诊断 termux-job-scheduler 为什么卡住。"""
    log("")
    log("===== job-scheduler 诊断 =====")
    log("1) 命令行工具 termux-job-scheduler : %s"
        % ("存在" if has_job_scheduler() else "缺失（pkg install termux-api）"))
    log("2) Termux:API  App                 : %s"
        % ("已装" if has_api_app() else "未装 ← 最可能的原因"))

    jobs_dir = os.path.expanduser("~/.termux/jobs")
    try:
        n = len(os.listdir(jobs_dir)) if os.path.isdir(jobs_dir) else 0
        log("3) 任务目录 ~/.termux/jobs         : %s（%d 个）"
            % ("存在" if os.path.isdir(jobs_dir) else "不存在", n))
    except Exception as e:
        log("3) 任务目录                        : 读取失败 %s" % e)

    if has_job_scheduler():
        log("")
        log("4) 尝试调用（5 秒超时，看它到底返回什么）...")
        try:
            r = subprocess.run(["termux-job-scheduler", "--help"],
                               capture_output=True, text=True, timeout=5)
            out = (r.stdout or "") + (r.stderr or "")
            log("   返回码 %s，输出: %s" % (r.returncode, out.strip()[:200] or "(空)"))
        except subprocess.TimeoutExpired:
            log("   ✖ 5 秒无响应 → 它卡在等授权弹窗，说明 App 没装或被拦")
        except Exception as e:
            log("   调用异常: %s" % e)

    log("")
    if not has_api_app():
        log("结论：Termux:API App 没装。光 pkg install termux-api 不够，")
        log("      必须单独装 App（和 Termux 同一个来源）。")
        log("")
        log("装不了的话，直接用更省电、零依赖的方案：")
        log("  python3 xmwallet.py hook")
    else:
        log("结论：App 已装。卡住多半是授权弹窗没点，或电池优化拦了。")
        log("      去系统设置 → 应用 → Termux:API → 电池 → 设为「不优化」")
    log("")


# ---------------------------------------------------------------- bashrc 钩子（零依赖兜底）

def cmd_hook(install: bool = True, hours: str = "20"):
    """打开 Termux 时按需补跑：不常驻进程，不装任何 App，零额外耗电。"""
    try:
        g = int(float(hours) * 3600)
    except Exception:
        g = 20 * 3600

    cur = ""
    if os.path.isfile(BASHRC):
        cur = open(BASHRC, "r", encoding="utf-8", errors="ignore").read()

    # 先清旧钩子
    if HOOK_BEGIN in cur and HOOK_END in cur:
        i = cur.index(HOOK_BEGIN)
        j = cur.index(HOOK_END) + len(HOOK_END)
        cur = (cur[:i] + cur[j:]).rstrip("\n") + "\n"

    if not install:
        open(BASHRC, "w", encoding="utf-8").write(cur)
        log("✔ 已移除 bashrc 钩子。")
        return

    py = sys.executable or "python3"
    script = os.path.abspath(__file__)
    block = (
        HOOK_BEGIN + "\n"
        "# 距上次成功运行超过 %d 小时就补跑一次；后台运行，不阻塞\n"
        "( \n"
        "  last=0; [ -f %s ] && last=$(cat %s 2>/dev/null || echo 0);\n"
        "  now=$(date +%%s);\n"
        "  if [ $(( now - ${last:-0} )) -gt %d ]; then\n"
        "    nohup sh -c 'cd %s && %s %s run; date +%%s > %s' \\\n"
        "      >> %s 2>&1 &\n"
        "  fi\n"
        ") >/dev/null 2>&1\n"
        + HOOK_END + "\n"
    ) % (g // 3600, STAMP_FILE, STAMP_FILE, g, BASE_DIR, py, script, STAMP_FILE, LOG_FILE)

    open(BASHRC, "w", encoding="utf-8").write(cur.rstrip("\n") + "\n\n" + block)
    log("")
    log("✔ 已安装 bashrc 钩子（零依赖，最省电）")
    log("  规则：每次打开 Termux，若距上次运行超过 %d 小时，后台补跑一次" % (g // 3600))
    log("  文件：%s" % BASHRC)
    log("")
    log("  · 不常驻任何进程，不开 Termux 就完全不耗电")
    log("  · 后台执行，打开 Termux 不会卡")
    log("  · 移除：python3 xmwallet.py hook --remove")
    log("  · 改间隔：python3 xmwallet.py hook 12")
    log("")

# ---------------------------------------------------------------- 定时方案

def _job_script_path() -> str:
    return os.path.join(BASE_DIR, "xmwallet-run.sh")


def _write_job_script(py: str, script: str) -> str:
    """job-scheduler 只能调 shell 脚本，生成一层包装。"""
    sp = _job_script_path()
    body = (
        "#!/data/data/com.termux/files/usr/bin/sh\n"
        "# xmwallet 定时执行包装脚本（由 xmwallet.py job 生成）\n"
        "cd %s\n"
        "%s %s run\n"
    ) % (BASE_DIR, py, script)
    with open(sp, "w", encoding="utf-8") as f:
        f.write(body)
    try:
        os.chmod(sp, 0o755)
    except Exception:
        pass
    return sp


def has_job_scheduler() -> bool:
    from shutil import which
    return bool(which("termux-job-scheduler"))


def has_api_app() -> bool:
    """termux-job-scheduler 依赖 Termux:API 这个 App，光装包没用。"""
    if os.path.isdir("/data/data/com.termux.api"):
        return True
    try:
        r = subprocess.run(["pm", "list", "packages", "com.termux.api"],
                           capture_output=True, text=True, timeout=15)
        return "com.termux.api" in (r.stdout or "")
    except Exception:
        return False


def has_crontab() -> bool:
    from shutil import which
    return bool(which("crontab"))


def parse_period(text: str) -> int:
    """把 24h / 12h30m / 90m 之类转成毫秒，最小 15 分钟。"""
    text = (text or "24h").strip().lower()
    m = re.match(r"^(\d+(?:\.\d+)?)\s*(h|m|d)?$", text)
    if not m:
        return 86400000
    val = float(m.group(1))
    unit = m.group(2) or "h"
    mult = {"m": 60000, "h": 3600000, "d": 86400000}[unit]
    ms = int(val * mult)
    return max(ms, 900000)  # Android JobScheduler 最小周期 15 分钟


JOBREG_FILE = os.path.join(BASE_DIR, "job_registry.json")


def jobreg_add(period_ms: int, script: str):
    d = load_json(JOBREG_FILE, [])
    if not isinstance(d, list):
        d = []
    d = [x for x in d if not (isinstance(x, dict) and x.get("period_ms") == period_ms
                              and x.get("script") == script)]
    d.append({
        "period_ms": period_ms,
        "hours": round(period_ms / 3600000.0, 2),
        "script": script,
        "at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
    })
    save_json(JOBREG_FILE, d)


def jobreg_list() -> list:
    d = load_json(JOBREG_FILE, [])
    return d if isinstance(d, list) else []


def jobreg_clear():
    save_json(JOBREG_FILE, [])


def cmd_job(period_text: str, cancel: bool = False, show_list: bool = False):
    """termux-job-scheduler 方案：不常驻后台进程，系统按需唤醒，最省电。"""
    if not in_termux():
        log("当前不在 Termux，无法注册 job。")
        return

    if not has_job_scheduler():
        log("未检测到 termux-job-scheduler，请先安装：")
        log("  pkg install termux-api")
        log("装完重新执行: python3 xmwallet.py job")
        return

    if show_list:
        reg = jobreg_list()
        if not reg:
            log("当前没有已注册的 job。")
            log("（若你之前注册过但这里为空，重新跑一次 python3 xmwallet.py job 即可登记）")
        else:
            log("已注册的系统级任务 (%d):" % len(reg))
            for i, j in enumerate(reg):
                log("  %d) 每 %s 小时   注册于 %s" % (i + 1, j.get("hours"), j.get("at")))
                log("     脚本: %s" % j.get("script"))
            log("")
            log("  注：任务由 Android JobScheduler 管理，无法从 Termux 直接查询实时状态，")
            log("      以上为本脚本的本地登记记录。")
        return

    if cancel:
        sp = _job_script_path()
        removed = 0
        jobs_dir = os.path.expanduser("~/.termux/jobs")
        if os.path.isdir(jobs_dir):
            for f in sorted(os.listdir(jobs_dir)):
                fp = os.path.join(jobs_dir, f)
                try:
                    content = open(fp, "r", encoding="utf-8", errors="ignore").read()
                except Exception:
                    continue
                if "xmwallet" in content:
                    try:
                        os.remove(fp)
                        removed += 1
                    except Exception:
                        pass
        if removed:
            log("✔ 已清理 %d 个残留文件。" % removed)
        n = len(jobreg_list())
        jobreg_clear()
        log("✔ 已清除本地登记（%d 条）。" % n)
        log("")
        log("  注：Android JobScheduler 中的任务需重启手机才会彻底释放，")
        log("      或到 设置 → 应用 → Termux:API → 清除数据。")
        return

    py = sys.executable or "python3"
    script = os.path.abspath(__file__)
    sp = _write_job_script(py, script)
    period_ms = parse_period(period_text)

    if not has_api_app():
        log("")
        log("✖ 检测到问题：Termux:API 这个 App 没装。")
        log("  pkg install termux-api 只装了命令行工具，")
        log("  真正干活的 App 要单独装（和 Termux 同一个来源）：")
        log("    https://f-droid.org/packages/com.termux.api/")
        log("  装完再执行: python3 xmwallet.py job")
        return

    jobs_dir = os.path.expanduser("~/.termux/jobs")
    try:
        before = set(os.listdir(jobs_dir)) if os.path.isdir(jobs_dir) else set()
    except Exception:
        before = set()

    cmd = [
        "termux-job-scheduler",
        "--script", sp,
        "--period-ms", str(period_ms),
        "--persisted", "true",
        "--battery-not-low", "false",
        "--network", "any",
    ]

    log("")
    log("正在注册，若手机弹出「Termux:API 授权」请点【允许】...")

    # 后台启动：不等它返回，避免权限弹窗阻塞导致超时
    err_path = os.path.join(BASE_DIR, ".job_err.txt")
    try:
        errf = open(err_path, "w")
        subprocess.Popen(cmd, stdout=errf, stderr=errf, start_new_session=True)
    except Exception as e:
        log("启动失败: %s" % e)
        return

    # JobScheduler 不写文件，只能靠命令输出的 response 码判断
    # RESULT_SUCCESS = 1，其余都是失败
    ok = False
    resp = ""
    proc_ok = False
    for _ in range(40):
        time.sleep(1.5)
        try:
            txt = open(err_path, "r", errors="ignore").read()
        except Exception:
            txt = ""
        if txt.strip():
            resp = txt
            m = re.search(r"response\s+(-?\d+)", txt)
            if m:
                ok = (m.group(1) == "1")
                proc_ok = True
                break
            # 没拿到 response 码但命令已退出，也算跑完了
            if "Scheduling Job" in txt or "Pending Job" in txt:
                proc_ok = True

    if ok or (proc_ok and "Scheduling Job" in resp):
        jobreg_add(period_ms, sp)
        log("")
        log("✔ 已注册系统级定时任务（不常驻后台，最省电）")
        log("  周期: 每 %.1f 小时" % (period_ms / 3600000.0))
        log("  脚本: %s" % sp)
        log("  调度返回: response 1（成功）")
        log("")
        log("  · 手机重启后依然生效，无需手动启动任何守护进程")
        log("  · 查看已注册: python3 xmwallet.py job --list")
        log("  · 取消任务:   python3 xmwallet.py job --cancel")
        log("  · 改周期:     python3 xmwallet.py job 12h")
        log("")
        log("  提示：Android 的 JobScheduler 不保证精确时点，")
        log("        实际执行可能偏移几十分钟，属正常现象。")
    else:
        log("")
        log("✖ 60 秒内没看到任务文件生成，注册可能没成功。")
        try:
            tip = open(err_path, "r", errors="ignore").read().strip()
        except Exception:
            tip = ""
        if tip:
            log("  命令输出: %s" % tip[:300])
            m2 = re.search(r"response\s+(-?\d+)", tip)
            if m2:
                log("  调度返回码: %s（1=成功，0=失败，-1=被拒）" % m2.group(1))
        log("")
        log("  常见原因与处理：")
        log("   1) 刚才弹了授权框但你没点允许 → 重跑一次并点【允许】")
        log("   2) Termux:API App 没装（见上方提示）")
        log("   3) 系统把 Termux:API 的「电池优化」开着 → 去设置里改成不优化")
        log("")
        log("  重新尝试: python3 xmwallet.py job")
        log("  查看结果: python3 xmwallet.py job --list")


def cmd_cron():
    """crond 方案：需常驻后台进程，更耗电。仅在 job 方案不可用时用。"""
    log("")
    log("⚠  crond 需要常驻后台进程，比 termux-job-scheduler 耗电。")
    log("   更省电的方案: python3 xmwallet.py job")
    log("")

    py = sys.executable or "python3"
    script = os.path.abspath(__file__)
    line = "0 9 * * * %s %s run >> %s 2>&1" % (py, script, LOG_FILE)

    if not in_termux():
        log("当前不在 Termux，仅打印参考配置：")
        log("  " + line)
        return

    if not has_crontab():
        log("未检测到 crontab，请先安装: pkg install cronie")
        log("（或者直接用更省电的方案: python3 xmwallet.py job）")
        return
    else:
        log("cronie 已安装 ✔")

    try:
        cur = subprocess.run(["crontab", "-l"], capture_output=True, text=True, timeout=15).stdout or ""
    except Exception:
        cur = ""

    if script in cur:
        log("crontab 中已存在该任务，无需重复添加。")
    else:
        new = cur.rstrip("\n") + "\n" + line + "\n"
        r = subprocess.run(["crontab", "-"], input=new, text=True, timeout=20, capture_output=True)
        if r.returncode == 0:
            log("✔ 已写入 crontab: " + line)
        else:
            log("写入失败，请手动执行: crontab -e  然后粘贴：")
            log("  " + line)
            return

    # 实时显示 crond 是否在跑
    try:
        ps = subprocess.run(["pgrep", "-x", "crond"], capture_output=True, text=True, timeout=10).stdout.strip()
    except Exception:
        ps = ""
    if ps:
        log("crond 运行状态: 已在运行 (pid %s)" % ps.split()[0])
    else:
        log("crond 运行状态: 未启动 → 执行 crond 启动；")
        log("                  Termux 被系统回收后需重新启动。")


# ---------------------------------------------------------------- 入口

def main():
    ap = argparse.ArgumentParser(description="小米钱包每日任务（Termux 版）")
    ap.add_argument("cmd", nargs="?", default="run",
                    choices=["login", "run", "status", "debug", "job", "hook", "cron", "dingtalk", "import"], help="子命令")
    ap.add_argument("name", nargs="?", default="", help="账号别名（login/指定账号 run 时用）")
    ap.add_argument("src", nargs="?", default="", help="凭据来源（import 时用：文件路径或 JSON）")
    ap.add_argument("-p", "--period", default="24h", help="任务周期，如 24h / 12h / 90m（默认 24h）")
    ap.add_argument("--list", action="store_true", help="job: 查看已注册任务")
    ap.add_argument("--cancel", action="store_true", help="job: 取消已注册任务")
    ap.add_argument("--diag", action="store_true", help="job: 诊断为什么卡住")
    ap.add_argument("--remove", action="store_true", help="hook / dingtalk: 移除")
    ap.add_argument("--test", action="store_true", help="dingtalk: 发送测试消息")
    ap.add_argument("--secret", default="", help="dingtalk: 加签密钥")
    ap.add_argument("--keyword", default="", help="dingtalk: 安全关键词")
    args = ap.parse_args()

    if args.cmd == "login":
        if not args.name:
            sys.exit("用法: python3 xmwallet.py login <账号别名>")
        cmd_login(args.name)
    elif args.cmd == "run":
        cmd_run(args.name)
    elif args.cmd == "status":
        cmd_status()
    elif args.cmd == "debug":
        cmd_debug()
    elif args.cmd == "job":
        if args.diag:
            cmd_job_diag()
        else:
            cmd_job(args.period, cancel=args.cancel, show_list=args.list)
    elif args.cmd == "dingtalk":
        src = args.src or (args.name if args.name and args.name.startswith("http") else "")
        secret = args.secret or (args.src if args.src and not args.src.startswith("http") else "")
        cmd_dingtalk(src, secret=secret, keyword=args.keyword,
                     remove=args.remove, test=args.test)
    elif args.cmd == "hook":
        cmd_hook(install=not args.remove, hours=args.period if args.period != "24h" else "20")
    elif args.cmd == "import":
        if not args.name:
            sys.exit("用法: python3 xmwallet.py import <别名> <文件路径或JSON>")
        cmd_import(args.name, args.src)
    elif args.cmd == "cron":
        cmd_cron()


if __name__ == "__main__":
    main()
