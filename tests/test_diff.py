# -*- coding: utf-8 -*-
"""核心对比 / 护栏回归。直接运行: python3 tests/test_diff.py"""
import ast
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "pipelines"))
from pipeline_common import (  # noqa: E402
    diff_items, filter_test_items, is_test_item, slim_change,
    is_sampling_noise, mark_noise, has_real_change,
)


def item(id_, fee="39元", data="30GB", report="R1", title="A套餐"):
    return {
        "id": id_, "title": title, "fee": fee,
        "firstLevel": "套餐", "secondLevel": "普通",
        "detail": {"reportNo": report, "commonData": data, "serviceContent": "权益"},
    }


def test_field_change_same_id():
    r = diff_items([item("A")], [item("A", data="50GB")])
    assert len(r["added_items"]) == 0 and len(r["removed_items"]) == 0 and len(r["modified_items"]) == 1
    assert {x["field"] for x in r["modified_details"]["A套餐"]} == {"commonData"}


def test_price_change_id_drift():
    r = diff_items([item("A")], [item("B", fee="49元")])
    assert len(r["added_items"]) == 0 and len(r["removed_items"]) == 0 and len(r["modified_items"]) == 1
    assert any(x["field"] == "fee" for x in r["modified_details"]["A套餐"])


def test_real_add_remove():
    r = diff_items([item("A")], [item("B", report="R2", fee="99元", title="B套餐")])
    assert len(r["added_items"]) == 1 and len(r["removed_items"]) == 1 and len(r["modified_items"]) == 0



def test_report_change_same_business_is_modified():
    r = diff_items([item("A", report="R1")], [item("A", report="R2")])
    assert len(r["added_items"]) == 0 and len(r["removed_items"]) == 0
    assert len(r["modified_items"]) == 1


def test_duplicate_identity_is_not_collapsed():
    old = [item("A1", title="同名套餐", fee="39元"), item("A2", title="同名套餐", fee="59元")]
    new = [item("B1", title="同名套餐", fee="49元"), item("B2", title="同名套餐", fee="69元")]
    r = diff_items(old, new)
    assert len(r["added_items"]) == 0 and len(r["removed_items"]) == 0
    assert len(r["modified_items"]) == 2


def test_report_no_shared_by_two_businesses_does_not_merge():
    old = [item("A1", title="甲套餐", report="R"), item("A2", title="乙套餐", report="R")]
    new = [item("B1", title="甲套餐", report="R", fee="49元"), item("B2", title="乙套餐", report="R", fee="69元")]
    r = diff_items(old, new)
    assert len(r["added_items"]) == 0 and len(r["removed_items"]) == 0
    assert len(r["modified_items"]) == 2

def test_filter_test_items():
    dirty = [
        item("1", title="【测试】请忽略"),
        item("2", title="正式套餐"),
        item("3", title="内部专用验证数据"),
        item("4", title="5G 畅享套餐"),
    ]
    kept = filter_test_items(dirty, verbose=False)
    titles = [x["title"] for x in kept]
    assert titles == ["正式套餐", "5G 畅享套餐"]
    assert is_test_item("【测试】xxx")
    assert is_test_item("校园卡测试流量包")
    assert not is_test_item("5G 畅享套餐")


def test_slim_change_nested_and_list():
    change = {
        "ts": "2026-09-12 20:00:00",
        "hunan": {
            "added": 100,
            "added_names": ["n%d" % i for i in range(80)],
            "added_list": [{"title": "t", "serviceContent": "x" * 500} for _ in range(40)],
            "modified": 2,
            "modified_details": {"a": {"k": "v" * 400}},
        },
    }
    out = slim_change(change)
    assert len(out["hunan"]["added_names"]) <= 30
    assert len(out["hunan"]["added_list"]) <= 12
    assert out["hunan"]["added_list"][0]["serviceContent"].endswith("…")
    assert "_trunc" in out["hunan"]
    # 板块块本身（无外层包裹）也能压缩
    flat = slim_change(change["hunan"])
    assert len(flat["added_names"]) <= 30


def test_sampling_noise_guard():
    noisy = {"added": 400, "removed": 380, "modified": 3,
             "added_names": ["a"], "removed_names": ["b"], "modified_names": ["c"]}
    assert is_sampling_noise(noisy, 1000) is True
    marked = mark_noise(noisy, 1000)
    assert marked["added"] == 0 and marked["removed"] == 0
    assert marked["modified"] == 3
    assert marked.get("note")
    assert has_real_change(marked) is True  # 带 note，保留诊断

    tiny = {"added": 10, "removed": 8, "modified": 0}
    assert is_sampling_noise(tiny, 1000) is False
    quiet = {"added": 0, "removed": 0, "modified": 0}
    assert has_real_change(quiet) is False


def _imported_from(path, module):
    tree = ast.parse(open(path, encoding="utf-8").read())
    names = set()
    for n in ast.walk(tree):
        if isinstance(n, ast.ImportFrom) and n.module == module:
            for a in n.names:
                names.add(a.name)
    return names


def test_gb_imports_diff_items():
    path = os.path.join(ROOT, "pipelines", "gb_pipeline.py")
    src = open(path, encoding="utf-8").read()
    assert src.splitlines()[0].startswith("#!")
    names = _imported_from(path, "pipeline_common")
    assert "diff_items" in names, "广电管线必须 import diff_items，否则 diff 阶段 NameError"
    assert "filter_test_items" in names


def test_telecom_has_rebuild_flag():
    path = os.path.join(ROOT, "pipelines", "telecom_pipeline.py")
    src = open(path, encoding="utf-8").read()
    assert '"--rebuild"' in src or "'--rebuild'" in src
    assert "def _brief(" in src


def test_announce_openssl_path():
    path = os.path.join(ROOT, "pipelines", "scripts", "announce_fetch.py")
    src = open(path, encoding="utf-8").read()
    assert "mobile" in src and "openssl_legacy.cnf" in src
    cnf = os.path.join(ROOT, "pipelines", "mobile", "openssl_legacy.cnf")
    assert os.path.isfile(cnf)


def test_unicom_uses_brief():
    path = os.path.join(ROOT, "pipelines", "unicom_pipeline.py")
    src = open(path, encoding="utf-8").read()
    assert "_brief(x)" in src


if __name__ == "__main__":
    tests = [v for k, v in list(globals().items()) if k.startswith("test_") and callable(v)]
    failed = 0
    for fn in tests:
        try:
            fn()
            print("PASS", fn.__name__)
        except Exception as e:
            failed += 1
            print("FAIL", fn.__name__, type(e).__name__, e)
    print("—— %d passed, %d failed ——" % (len(tests) - failed, failed))
    sys.exit(1 if failed else 0)
