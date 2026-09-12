# 中国移动资费监控软件 - 配置文件
# 两种配置方式：
#  1) 直接改本文件（本地运行）
#  2) 通过环境变量注入（GitHub Actions 云端运行，更安全，见 secret_说明.txt）
# 通知通道仅钉钉，配置见 secret_说明.txt
import os

from province_table import PROVINCES, DEFAULT_SECTIONS

# ============ 抓取配置 ============
# 页面 URL（固定模板，勿改）
PAGE_URL = (
    "https://h.app.coc.10086.cn/cmcc-app/pc-pages/"
    "tariffZonePers.html?pageId=834148205904408576&prov=731&channelId=P00000010677"
)

# 板块：quanguo=全网资费（全国），其余为省份板块（见 province_table.py）
# 默认监控 全网 + 湖南；如需纳入更多省份，可通过环境变量 TRACK_PROVINCES
# 注入省份 section（逗号分隔，如 "hunan,guangdong,zhejiang"）。
_VALID = set(["quanguo"] + [sec for sec, _c, _n in PROVINCES])

_track_env = os.getenv("TRACK_PROVINCES", "").strip()
if _track_env:
    _wanted = [s.strip() for s in _track_env.split(",")
               if s.strip() and s.strip() != "quanguo"]
    # 剔除拼错/不存在的省份，避免下游按不存在的板块去抓取而静默空转
    _bad = [s for s in _wanted if s not in _VALID]
    if _bad:
        print("[config] 忽略未知省份: %s" % ",".join(_bad))
    _wanted = [s for s in _wanted if s in _VALID]
    # 全被过滤掉时退回默认，避免抓成空集
    SECTIONS = ["quanguo"] + _wanted if _wanted else list(DEFAULT_SECTIONS)
else:
    SECTIONS = list(DEFAULT_SECTIONS)
# 去重保序
SECTIONS = list(dict.fromkeys(SECTIONS))

# 轮询间隔（秒），本地循环模式用，默认 1 小时
CHECK_INTERVAL = int(os.getenv("CHECK_INTERVAL") or "3600")

# 无头浏览器（服务器环境建议 True）
HEADLESS = True
