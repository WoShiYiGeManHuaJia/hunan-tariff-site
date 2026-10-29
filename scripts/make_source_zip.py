#!/usr/bin/env python3
"""生成「自己创建」下载用的源码压缩包 tariff-fetch-source.zip。

背景：配置中心 push-center.html 的「🛠 自己创建」按钮指向仓库根的
tariff-fetch-source.zip。该包此前是我手工打的一次性产物，之后改了
代码（如 SEC_DROP_RATIO 0.5→0.7、采样校验、钉钉只统计最新一轮）它
并不会跟着变——下载的人拿到的是旧代码，且毫无提示。

故改为脚本自动生成，并由 workflow 在每次构建后重打，保证包内代码
与仓库 main 分支一致。

用法：
    python3 scripts/make_source_zip.py

产出：
    仓库根 tariff-fetch-source.zip
"""
import os
import sys
import zipfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT = os.path.join(ROOT, "tariff-fetch-source.zip")

# 打包范围：抓取管线 + 构建/汇总脚本 + 云端 workflow + 说明
INCLUDE_DIRS = [
    "pipelines",
    "scripts",
    ".github/workflows",
]
INCLUDE_FILES = [
    "requirements.txt",
    "config.example.json",
]

# 排除：数据/快照/缓存/版本库等，避免把几十 MB 数据塞进包里
EXCLUDE_DIR_PARTS = {".git", "__pycache__", "snapshots", "_prev", "_site",
                     "data", "prev", "node_modules", ".github/workflows/.git"}
EXCLUDE_SUFFIX = {".pyc", ".pyo", ".zip", ".log", ".tmp", ".sqlite", ".db"}


def should_skip(path):
    parts = set(os.path.relpath(path, ROOT).split(os.sep))
    if parts & EXCLUDE_DIR_PARTS:
        return True
    return os.path.splitext(path)[1].lower() in EXCLUDE_SUFFIX


def main():
    count = 0
    # 先写临时文件再替换，避免打包中途失败留下半个 zip
    tmp = OUT + ".tmp"
    with zipfile.ZipFile(tmp, "w", zipfile.ZIP_DEFLATED) as z:
        for d in INCLUDE_DIRS:
            abs_d = os.path.join(ROOT, d)
            if not os.path.isdir(abs_d):
                print("  (跳过不存在的目录) %s" % d)
                continue
            for base, dirs, files in os.walk(abs_d):
                dirs[:] = [x for x in dirs if not should_skip(os.path.join(base, x))]
                for fn in sorted(files):
                    p = os.path.join(base, fn)
                    if should_skip(p):
                        continue
                    z.write(p, os.path.relpath(p, ROOT))
                    count += 1
        for fn in INCLUDE_FILES:
            p = os.path.join(ROOT, fn)
            if os.path.exists(p):
                z.write(p, fn)
                count += 1

        # 包内附一份跑法说明，避免下载的人面对一堆文件无从下手
        readme = """# 运营商资费抓取源码包

本包由 scripts/make_source_zip.py 自动生成，内容与仓库 main 分支同步。
数据源与历史快照（data/、snapshots/）不含在内，首次运行会自行生成。

## 目录

    pipelines/           四家抓取管线（mobile / unicom / telecom / gb）
    scripts/             站点构建 build_site.py、汇总推送 dingtalk_summary.py、
                         一致性校验 check_frontend_sync.py
    .github/workflows/   云端定时抓取与推送配置

## 跑法

    pip install -r requirements.txt

    # 抓取（以移动为例）
    python3 pipelines/mobile/main.py --once

    # 构建站点数据（产出 data/latest.json、data/history.json）
    python3 scripts/build_site.py

    # 推送汇总（需配置 DINGTALK_WEBHOOK 等环境变量）
    python3 scripts/dingtalk_summary.py

## 推送渠道环境变量

    DINGTALK_WEBHOOK      钉钉机器人 webhook
    DINGTALK_SECRET       钉钉加签密钥
    FEISHU_WEBHOOK        飞书机器人 webhook

## 改完前端记得校验

    python3 scripts/check_frontend_sync.py

app.js 有四份活跃副本（根/unicom/telecom/gb）+ 一份遗留副本（site/），
改公共逻辑容易漏改，退出码 1 即表示有副本缺失修复点。
"""
        z.writestr("怎么用.txt", readme)
        count += 1

    os.replace(tmp, OUT)
    size = os.path.getsize(OUT)
    print("已生成 %s（%d 个文件，%.0f KB）" % (
        os.path.relpath(OUT, ROOT), count, size / 1024))
    return 0


if __name__ == "__main__":
    sys.exit(main())
