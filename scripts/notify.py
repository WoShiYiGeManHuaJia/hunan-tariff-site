# -*- coding: utf-8 -*-
"""多通道推送：钉钉 / 飞书 / 企业微信机器人 / 邮件

所有凭据均从环境变量读取（GitHub Actions 的 Secrets 或本地 .env），
代码内不含任何硬编码密钥。

已配置的通道都会被推送；未配置的自动跳过。
"""
import os
import sys
import json
import time
import hmac
import base64
import hashlib
import urllib.parse
import urllib.request
import urllib.error
import smtplib
import re
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from email.header import Header

CST = __import__("datetime").timezone(__import__("datetime").timedelta(hours=8))


def _env(k, d=""):
    return os.getenv(k, d).strip()


def _load_dotenv():
    """本地运行时自动读取 .env；已存在的环境变量优先（Actions Secrets 不受影响）。"""
    try:
        here = os.path.dirname(os.path.abspath(__file__))
    except NameError:          # 被 exec/内联执行时没有 __file__
        here = os.getcwd()
    for base in (here, os.path.dirname(here), os.path.dirname(os.path.dirname(here))):
        fp = os.path.join(base, ".env")
        if os.path.isfile(fp):
            try:
                with open(fp, encoding="utf-8") as f:
                    for line in f:
                        line = line.strip()
                        if not line or line.startswith("#") or "=" not in line:
                            continue
                        if line.startswith("export "):
                            line = line[7:]
                        k, _, v = line.partition("=")
                        k, v = k.strip(), v.strip().strip('"').strip("'")
                        if k and k not in os.environ:
                            os.environ[k] = v
            except Exception:
                pass
            return


_load_dotenv()


def _post(url, payload, timeout=30):
    body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    req = urllib.request.Request(
        url, data=body,
        headers={"Content-Type": "application/json;charset=utf-8"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.load(r)


def md_to_text(md):
    """markdown → 纯文本（邮件正文 / 飞书兜底用）"""
    t = re.sub(r"^#+\s*", "", md, flags=re.M)
    t = re.sub(r"\*\*(.+?)\*\*", r"\1", t)
    t = re.sub(r"\[(.+?)\]\((.+?)\)", r"\1 (\2)", t)
    t = re.sub(r"^\s*[-*]\s*", "· ", t, flags=re.M)
    return t.strip()


def md_to_html(md):
    """markdown → 简单 HTML（邮件正文）"""
    esc = md.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
    lines = []
    for ln in esc.split("\n"):
        s = ln.rstrip()
        if s.startswith("### "):
            lines.append("<h3>%s</h3>" % s[4:])
        elif s.startswith("## "):
            lines.append("<h2>%s</h2>" % s[3:])
        elif s.startswith("# "):
            lines.append("<h1>%s</h1>" % s[2:])
        elif re.match(r"^\s*[-*]\s+", s):
            lines.append("<li>%s</li>" % re.sub(r"^\s*[-*]\s+", "", s))
        elif not s.strip():
            lines.append("")
        else:
            lines.append("<p>%s</p>" % s)
    html = "\n".join(lines)
    html = re.sub(r"\*\*(.+?)\*\*", r"<b>\1</b>", html)
    html = re.sub(r"\[(.+?)\]\((.+?)\)", r'<a href="\2">\1</a>', html)
    html = re.sub(r"`(.+?)`", r"<code>\1</code>", html)
    return ("<div style='font-family:-apple-system,BlinkMacSystemFont,"
            "\"PingFang SC\",\"Microsoft YaHei\",sans-serif;font-size:14px;"
            "line-height:1.7;color:#222'>%s</div>" % html)


# ───────────────────────── 钉钉 ─────────────────────────
def send_dingtalk(title, md):
    webhook = _env("DINGTALK_WEBHOOK")
    if not webhook:
        return None
    secret = _env("DINGTALK_SECRET")
    url = webhook
    if secret:
        ts = str(round(time.time() * 1000))
        sign = urllib.parse.quote_plus(base64.b64encode(
            hmac.new(secret.encode(), ("%s\n%s" % (ts, secret)).encode(),
                     hashlib.sha256).digest()))
        url = "%s&timestamp=%s&sign=%s" % (url, ts, sign)
    try:
        res = _post(url, {"msgtype": "markdown",
                          "markdown": {"title": title[:64], "text": md}})
        ok = res.get("errcode") == 0
        return ok, "errcode=%s %s" % (res.get("errcode"), res.get("errmsg"))
    except urllib.error.HTTPError as e:
        return False, "HTTP %s %s" % (e.code, e.read().decode("utf-8", "ignore")[:150])
    except Exception as e:
        return False, str(e)


# ───────────────────────── 飞书 ─────────────────────────
def _feishu_sign(secret):
    # 飞书：待签串 = timestamp + "\n" + secret，HMAC-SHA256 的 key 为空
    ts = str(int(time.time()))
    sign = base64.b64encode(hmac.new(
        ("%s\n%s" % (ts, secret)).encode("utf-8"),
        b"", hashlib.sha256).digest()).decode("utf-8")
    return ts, sign


def send_feishu(title, md):
    webhook = _env("FEISHU_WEBHOOK")
    if not webhook:
        return None
    payload = {
        "msg_type": "interactive",
        "card": {
            "header": {"title": {"tag": "plain_text", "content": title[:64]},
                       "template": "blue"},
            "elements": [{"tag": "div", "text": {"tag": "lark_md", "content": md}}],
        },
    }
    secret = _env("FEISHU_SECRET")
    if secret:
        ts, sign = _feishu_sign(secret)
        payload["timestamp"] = ts
        payload["sign"] = sign
    try:
        res = _post(webhook, payload)
        ok = res.get("code") == 0 or res.get("StatusCode") == 0
        return ok, "code=%s %s" % (res.get("code"), res.get("msg"))
    except urllib.error.HTTPError as e:
        return False, "HTTP %s %s" % (e.code, e.read().decode("utf-8", "ignore")[:150])
    except Exception as e:
        return False, str(e)


# ───────────────────── 企业微信机器人 ─────────────────────
def send_wecom(title, md):
    webhook = _env("WECOM_WEBHOOK")
    if not webhook:
        return None
    content = md
    if len(content.encode("utf-8")) > 3800:      # 企微上限 4096 字节
        content = md_to_text(md)[:1800]
    try:
        res = _post(webhook, {"msgtype": "markdown",
                              "markdown": {"content": content}})
        ok = res.get("errcode") == 0
        return ok, "errcode=%s %s" % (res.get("errcode"), res.get("errmsg"))
    except urllib.error.HTTPError as e:
        return False, "HTTP %s %s" % (e.code, e.read().decode("utf-8", "ignore")[:150])
    except Exception as e:
        return False, str(e)


# ───────────────────────── 邮件 ─────────────────────────
def send_email(title, md):
    host = _env("SMTP_HOST")
    user = _env("SMTP_USER")
    to = _env("MAIL_TO")
    if not (host and user and to):
        return None
    pwd = _env("SMTP_PASS")
    port = int(_env("SMTP_PORT", "465") or 465)
    sender = _env("MAIL_FROM") or user
    name = _env("MAIL_FROM_NAME", "资费监控")

    msg = MIMEMultipart("alternative")
    msg["Subject"] = Header(title, "utf-8")
    msg["From"] = Header("%s <%s>" % (name, sender), "utf-8")
    msg["To"] = to
    msg.attach(MIMEText(md_to_text(md), "plain", "utf-8"))
    msg.attach(MIMEText(md_to_html(md), "html", "utf-8"))

    addrs = [a.strip() for a in to.replace(";", ",").split(",") if a.strip()]
    try:
        if port == 465:
            s = smtplib.SMTP_SSL(host, port, timeout=30)
        else:
            s = smtplib.SMTP(host, port, timeout=30)
            s.starttls()
        s.login(user, pwd)
        s.sendmail(sender, addrs, msg.as_string())
        s.quit()
        return True, "已发送给 %d 个收件人" % len(addrs)
    except Exception as e:
        return False, str(e)


CHANNELS = [
    ("钉钉", "DINGTALK_WEBHOOK", send_dingtalk),
    ("飞书", "FEISHU_WEBHOOK", send_feishu),
    ("企业微信", "WECOM_WEBHOOK", send_wecom),
    ("邮件", "SMTP_HOST", send_email),
]


def send_all(title, md, verbose=True):
    """向所有已配置通道推送，返回 [(通道, 成功?, 说明)]"""
    results = []
    for name, envkey, fn in CHANNELS:
        try:
            r = fn(title, md)
        except Exception as e:
            r = (False, "异常: %s" % e)
        if r is None:
            if verbose:
                print("  ⏭  %s：未配置（%s 为空），跳过" % (name, envkey))
            continue
        ok, note = r
        results.append((name, ok, note))
        if verbose:
            print("  %s %s：%s" % ("✅" if ok else "❌", name, note))
    return results


def _cli():
    if "--test" in sys.argv:
        title = "✅ 推送通道配置成功"
        lines = ["## ✅ 配置成功", "",
                 "你的通知通道已成功接入「运营商资费监控」。", "",
                 "**已启用通道**", ""]
        any_ok = False
        for name, envkey, fn in CHANNELS:
            on = bool(_env(envkey))
            lines.append("- %s %s：%s" % ("✅" if on else "⚪", name,
                                          "已配置" if on else "未配置"))
            if on:
                any_ok = True
        lines += ["", "下次资费变化将自动推送到这里。"]
        if not any_ok:
            print("❌ 一个通道都没配置。请在仓库 Secrets 或 .env 里至少填一个。")
            return 1
        res = send_all(title, "\n".join(lines))
        okc = [n for n, ok, _ in res if ok]
        print("\n测试完成：成功 %d / 已配置 %d  %s"
              % (len(okc), len(res), ("（%s）" % "、".join(okc)) if okc else ""))
        return 0 if okc else 1

    # 手动推送：--title / --text / --file
    title, text = "资费变化通知", ""
    if "--title" in sys.argv:
        title = sys.argv[sys.argv.index("--title") + 1]
    if "--text" in sys.argv:
        text = sys.argv[sys.argv.index("--text") + 1]
    if "--file" in sys.argv:
        text = open(sys.argv[sys.argv.index("--file") + 1], encoding="utf-8").read()
    if not text:
        print("用法: notify.py --test | --title 标题 --text 内容 | --file md文件")
        return 1
    send_all(title, text)
    return 0


if __name__ == "__main__":
    sys.exit(_cli())
