#!/usr/bin/env python3
"""前端五份副本一致性校验。

背景：app.js 有四份活跃副本（根目录移动 + unicom/ + telecom/ + gb/），
外加 site/ 一份历史遗留副本。改公共逻辑时只改一份、漏掉其余是常事——
例如「变化历史里无变化板块不占位」那次，只改了根目录，site/ 仍是旧逻辑，
若哪天构建链恢复复制就会把修复悄悄回滚。

用法：
    python3 scripts/check_frontend_sync.py

退出码：
    0  全部一致
    1  发现不一致（会在 stdout 打印明细）
"""
import os
import sys
import re

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# 五份副本：根目录(移动) + 三个子站 + site/ 历史副本
COPIES = [
    ("移动(根)", "app.js"),
    ("联通", "unicom/app.js"),
    ("电信", "telecom/app.js"),
    ("广电", "gb/app.js"),
    ("site(遗留)", "site/app.js"),
]

# 关键修复点：(说明, 特征正则)
# 新增公共修复时，把特征加到这里即可纳入校验。
CHECKS = [
    ("无变化的省份不占位", r"if\s*\(!chips\.length\)\s*return\s*;"),
    ("整批无变化时给一行提示", r"本轮全部省份均无变化"),
    ("fetch 有超时保护", r"FETCH_TIMEOUT"),
    ("历史区自动加载", r"setupHistAutoLoad"),
    ("排序条存在", r"setupSortBar"),
]


def main():
    missing_any = False
    print("前端副本一致性校验")
    print("=" * 56)

    # 1) 文件是否都存在
    for label, rel in COPIES:
        p = os.path.join(ROOT, rel)
        if not os.path.exists(p):
            print("  ❌ %-12s 文件缺失: %s" % (label, rel))
            missing_any = True
    if missing_any:
        return 1

    # 2) 关键修复点是否都在
    contents = {}
    for label, rel in COPIES:
        with open(os.path.join(ROOT, rel), encoding="utf-8") as f:
            contents[label] = f.read()

    print("\n关键修复点覆盖情况：\n")
    for desc, pattern in CHECKS:
        hit = [lb for lb, c in contents.items() if re.search(pattern, c)]
        miss = [lb for lb, _ in COPIES if lb not in hit]
        if miss:
            print("  ❌ %-24s 缺失: %s" % (desc, "、".join(miss)))
            missing_any = True
        else:
            print("  ✅ %-24s 五份齐全" % desc)

    # 3) 根目录与其余各份的差异行数（提示用，不算失败）
    print("\n与根目录(移动)的归一化差异：\n")
    base = re.sub(r"\s+", " ", re.sub(r"/\*.*?\*/", "", contents["移动(根)"], flags=re.S)).strip()
    for label, _ in COPIES[1:]:
        cur = re.sub(r"\s+", " ", re.sub(r"/\*.*?\*/", "", contents[label], flags=re.S)).strip()
        d = abs(len(cur) - len(base))
        note = "（同源码）" if d == 0 else "（%d 字符差，各站渲染逻辑本就不同，属正常）" % d
        print("  %-12s %s" % (label, note))

    print("\n" + "=" * 56)
    if missing_any:
        print("结果：发现不一致，请补齐缺失的修复点后重新校验")
        return 1
    print("结果：全部一致 ✅")
    return 0


if __name__ == "__main__":
    sys.exit(main())
