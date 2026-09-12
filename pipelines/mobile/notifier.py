# 消息通知模块：钉钉群机器人推送（唯一通知通道）
# ★ 分发版：钉钉地址不再写死在代码里，改为从环境变量读取，
#   由 GitHub 仓库「设置 → 密钥和变量 → 操作 → 新建仓库机密」配置，见《分享部署教程》
import hashlib
import hmac
import base64
import os
import time
import urllib.parse
import urllib.request
import json

from province_table import section_name

# ═══════════════ 钉钉机器人设置（从环境变量读取） ═══════════════
# 需要在 GitHub 仓库设置里配置两个"仓库机密(Secret)"：
#   DINGTALK_WEBHOOK = 你的钉钉群机器人 Webhook 地址
#   DINGTALK_SECRET  = 你的钉钉机器人加签密钥（没勾选加签就不用配，留空）
DINGTALK_WEBHOOK = os.getenv("DINGTALK_WEBHOOK", "").strip()
DINGTALK_SECRET = os.getenv("DINGTALK_SECRET", "").strip()
# 展示站短链（可点击查看资费数据），由公开短链服务生成，不暴露原始域名与仓库信息
APP_LINK = "https://woshiyigemanhuajia.github.io/hunan-tariff-site/"
# ══════════════════════════════════════════════


def _sign_url() -> str:
    """开启'加签'时生成带签名的 URL，未开启则原样返回"""
    if not DINGTALK_SECRET:
        return DINGTALK_WEBHOOK
    timestamp = str(round(time.time() * 1000))
    string_to_sign = f"{timestamp}\n{DINGTALK_SECRET}"
    hmac_code = hmac.new(
        DINGTALK_SECRET.encode("utf-8"),
        string_to_sign.encode("utf-8"),
        digestmod=hashlib.sha256,
    ).digest()
    sign = urllib.parse.quote_plus(base64.b64encode(hmac_code))
    return f"{DINGTALK_WEBHOOK}&timestamp={timestamp}&sign={sign}"


# 业务内容字段展示顺序（按用户要求的清单排列，其余字段自动排后面）
FIELD_ORDER = [
    "资费标准", "资费类型", "适用地区", "上线日期", "有效期限", "违约责任",
    "方案编号", "适用范围", "销售渠道", "下线日期", "在网要求", "退订方式",
    "超出资费说明",
    "国内通话", "国内通用流量", "宽带", "移动高清", "其他服务内容",
]
_ORDER = {f: i for i, f in enumerate(FIELD_ORDER)}

# 下架/精简展示只保留的基础信息（含分类标识，便于一眼看出哪类资费变化）
BASE_FIELDS = [
    "资费类型", "归属",
    "资费标准", "适用地区",
    "国内通话", "国内通用流量", "宽带", "移动高清",
    "超出资费说明", "其他服务内容",
]

# 字段图标：突出每行信息类别，价格/套餐内容重点靠前
FIELD_EMOJI = {
    "资费标准": "💰", "资费类型": "📋", "适用地区": "📍", "上线日期": "🟢",
    "有效期限": "⏳", "违约责任": "⚖️", "方案编号": "🔢", "适用范围": "👤",
    "销售渠道": "🏪", "下线日期": "⛔", "在网要求": "📵", "退订方式": "🔙",
    "超出资费说明": "💸",
    "国内通话": "📞", "国内通用流量": "📶", "宽带": "🌐", "移动高清": "📺",
    "其他服务内容": "📄", "定向流量": "🎯", "权益": "🎁",
}
DEFAULT_EMOJI = "📌"


def _sort_fields(fields: dict) -> list:
    """字段按清单顺序排序，清单外字段排后面"""
    return sorted(fields, key=lambda k: _ORDER.get(k, 1000))


def _tag(fields: dict) -> str:
    """生成分类标签："归属·资费类型"，如 个人资费·加装包"""
    a = (fields or {}).get("归属") or ""
    b = (fields or {}).get("资费类型") or ""
    return f"{a}·{b}".strip("·")


def _render_full(name: str, fields: dict, indent: str = "") -> list:
    """渲染一条业务的完整内容：分类标签 + 业务名称 + 分组带图标的全部字段"""
    tag = _tag(fields)
    lines = [f"{indent}- **【{tag}】{name}**"]
    for k in _sort_fields(fields):
        emoji = FIELD_EMOJI.get(k, DEFAULT_EMOJI)
        lines.append(f"{indent}  - {emoji} **{k}**：{fields[k]}")
    return lines


def _render_short(name: str, fields: dict, indent: str = "") -> list:
    """精简渲染：一行概要（分类·名称·资费标准·适用地区），用于变化量多时的防超长模式"""
    tag = _tag(fields)
    line = f"{indent}- **【{tag}】{name}**"
    fee = (fields or {}).get("资费标准") or ""
    area = (fields or {}).get("适用地区") or ""
    if fee or area:
        line += f"　({fee or '-'}｜{area or '-'})"
    return [line]


def _render_basic(name: str, fields: dict, indent: str = "") -> list:
    """渲染一条业务的基础信息：分类标签 + 只保留 BASE_FIELDS 中的字段"""
    tag = _tag(fields)
    lines = [f"{indent}- **【{tag}】{name}**"]
    for k in _sort_fields(fields):
        if k not in BASE_FIELDS:
            continue
        emoji = FIELD_EMOJI.get(k, DEFAULT_EMOJI)
        lines.append(f"{indent}  - {emoji} **{k}**：{fields[k]}")
    return lines


def _render_modified(name: str, changed: dict, indent: str = "") -> list:
    """渲染一条修改业务：业务名称突出 + 变化的字段对比"""
    lines = [f"{indent}- **【{name}】**"]
    for k in _sort_fields(changed):
        emoji = FIELD_EMOJI.get(k, DEFAULT_EMOJI)
        old_v, new_v = changed[k]
        if old_v is None:
            lines.append(f"{indent}  - {emoji} **{k}**：{new_v}（新增该字段）")
        elif new_v is None:
            lines.append(f"{indent}  - {emoji} **{k}**：{old_v}（该字段已移除）")
        else:
            lines.append(f"{indent}  - {emoji} **{k}**：{old_v} → {new_v}")
    return lines


def _build_content(reports: list) -> str:
    """把变化报告按新模板拼成钉钉消息正文（分组+空行+图标+分类标签，重点突出）。
    加装包/营销活动条目多，变化量大时自动切换精简渲染，并对超长消息截断，避免超限。"""
    MAX_BYTES = 18000  # 钉钉单条消息 body 上限约 20000 字节，留余量（中文 1 字=3 字节）
    SHORT_ABOVE = 6  # 单类变化超过该数量改用一行式精简渲染（markdown 版调低阈值防刷屏）

    lines = ["# 中国移动资费变更监控", ""]
    for r in reports:
        sec = r.get("section") or ""
        name = "全网资费(全国)" if sec == "quanguo" else f"{section_name(sec)}资费"
        lines.append(f"## 📡 {name}")
        lines.append(f"📅 检测时间：{r.get('timestamp', '')}")
        lines.append("")

        added = r.get("added") or []
        removed = r.get("removed") or []
        modified = r.get("modified") or []

        if added:
            lines.append(f"### 🆕 新增 {len(added)} 条")
            use_short = len(added) > SHORT_ABOVE
            for it in added:
                if isinstance(it, dict):
                    fn = _render_short if use_short else _render_full
                    lines += fn(it.get("name", ""), it.get("fields", {}))
                else:
                    lines.append(f"- **【{it}】**")
                lines.append("")
        if removed:
            lines.append(f"### ⬇️ 下架 {len(removed)} 条")
            use_short = len(removed) > SHORT_ABOVE
            for it in removed:
                if isinstance(it, dict):
                    fn = _render_short if use_short else _render_basic
                    lines += fn(it.get("name", ""), it.get("fields", {}))
                else:
                    lines.append(f"- **【{it}】**")
                lines.append("")
        if modified:
            lines.append(f"### 📝 修改 {len(modified)} 条")
            for m in modified:
                lines += _render_modified(m.get("name", ""), m.get("changed", {}))
                lines.append("")
    lines.append("详情请登录资费公示专区查看。")
    lines.append("")
    lines.append(f"- 🗂 点击查看资费数据：{APP_LINK}")
    lines.append(f"- 📊 变化历史直达：{APP_LINK}#history")
    content = "\n".join(lines)
    return _truncate_bytes(content, MAX_BYTES)


def _truncate_bytes(text: str, max_bytes: int = 18000) -> str:
    """按 UTF-8 字节数截断（钉钉单条消息 body 上限约 20000 字节，中文按 3 字节计），
    避免整包超限被钉钉拒绝返回 460101。"""
    raw = text.encode("utf-8")
    if len(raw) <= max_bytes:
        return text
    cut = raw[:max_bytes]
    while cut:
        try:
            cut.decode("utf-8")
            break
        except UnicodeDecodeError:
            cut = cut[:-1]
    return cut.decode("utf-8") + "\n…消息过长已截断，完整内容请到展示站查看。"


def _send_dingtalk(content: str) -> bool:
    """向钉钉群发送一条文本消息，返回是否成功"""
    if not DINGTALK_WEBHOOK:
        print("[notify] 未配置钉钉机器人 webhook，跳过发送")
        return False
    payload = json.dumps(
        {
            "msgtype": "markdown",
            "markdown": {"title": "中国移动资费监控", "text": content},
        }
    ).encode("utf-8")
    url = _sign_url()

    req = urllib.request.Request(
        url,
        data=payload,
        headers={"Content-Type": "application/json; charset=utf-8"},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=20) as resp:
        body = resp.read().decode("utf-8")
        print(f"[notify] 钉钉接口返回: {body}")
    return True


def send_mail(reports: list, subject: str = None) -> bool:
    """有变化时发送完整变更通知（函数名 send_mail 为历史遗留，实际走钉钉）。
    未配置钉钉 Webhook 时不发送。"""
    if not reports:
        return False
    return _send_dingtalk(_build_content(reports))


def _build_summary(reports: list) -> str:
    """把多个省份的变化汇总成一条简单消息：每个省份一行「新增/下架/修改」计数。"""
    lines = ["# 中国移动资费变更监控", ""]
    for r in reports:
        sec = r.get("section") or ""
        name = "全网资费(全国)" if sec == "quanguo" else f"{section_name(sec)}资费"
        added = len(r.get("added") or [])
        removed = len(r.get("removed") or [])
        modified = len(r.get("modified") or [])
        cnt = []
        if added:
            cnt.append(f"新增 {added}")
        if removed:
            cnt.append(f"下架 {removed}")
        if modified:
            cnt.append(f"修改 {modified}")
        lines.append(f"- 📡 **{name}**：{'、'.join(cnt) if cnt else '无'}")
    lines.append("")
    lines.append(f"- 🗂 点击查看资费数据：{APP_LINK}")
    lines.append(f"- 📊 变化历史直达：{APP_LINK}#history")
    return "\n".join(lines)


def send_summary(reports: list) -> bool:
    """多个板块发生变化时，只推送一条各省简单计数汇总，避免刷屏。"""
    if not reports:
        return False
    return _send_dingtalk(_build_summary(reports))


def send_nochange(timestamp: str = "") -> bool:
    """资费无变化时发送简短心跳通知，确认监控仍在正常运行"""
    content = (
        "# 中国移动资费变更监控\n\n"
        "本次未检测到资费变化。\n\n"
        f"- 📅 检测时间：{timestamp or '未知'}\n\n"
        f"- 🗂 点击查看资费数据：{APP_LINK}\n"
        f"- 📊 变化历史直达：{APP_LINK}#history"
    )
    return _send_dingtalk(content)


def send_alert(message: str) -> bool:
    """抓取异常提醒（不会误报下架，只是提示需要人工关注）"""
    content = (
        "# 中国移动资费监控 · 异常提醒\n\n"
        f"{message}\n\n"
        "本次已跳过对比，历史快照未受影响。\n"
        "若连续出现，建议手动打开资费页面确认。\n\n"
        f"- 🗂 点击查看资费数据：{APP_LINK}\n"
        f"- 📊 变化历史直达：{APP_LINK}#history"
    )
    return _send_dingtalk(content)
