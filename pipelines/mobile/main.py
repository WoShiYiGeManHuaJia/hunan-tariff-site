# 中国移动资费监控软件 - 主入口
# 用法:
#   单次检查:  python main.py --once
#   循环监控:  python main.py --loop
#   初始化快照(不通知): python main.py --init
# 注意：源站（移动网关）会触发 TLS legacy renegotiation，较新 OpenSSL 默认拒绝。
#   在本文件最顶部注入 OPENSSL_CONF，确保任何 ssl 库初始化前生效（见 openssl_legacy.cnf）。
import json
import os

_SSL_CNF = os.path.join(os.path.dirname(os.path.abspath(__file__)), "openssl_legacy.cnf")
if os.path.exists(_SSL_CNF):
    os.environ.setdefault("OPENSSL_CONF", _SSL_CNF)

import time

import fetcher
import notifier
import snapshot
from config import CHECK_INTERVAL

# 防误报护栏：本次抓取数量低于上次的该比例时，判定为"抓取不全"而非真实下架
ABNORMAL_DROP_RATIO = 0.7


def _nochange_notify_disabled() -> bool:
    """「无变化」心跳推送开关。

    环境变量 NOCHANGE_NOTIFY=0 时关闭心跳（避免无变化时空扰）；
    默认（未配置/为空）开启心跳，用于确认监控仍在正常运行。
    """
    return os.getenv("NOCHANGE_NOTIFY", "").strip() == "0"


def _is_abnormal_drop(section: str, new_items: list) -> bool:
    """本次抓取数量骤减（<上次70%）视为异常，跳过对比，避免误报下架"""
    old = snapshot.load_snapshot(section)
    if old is None:
        return False
    old_n = len(old.get("items") or [])
    new_n = len(new_items or [])
    # 上次一条都没有，或本次缺少不算异常（后续有基线再判断）
    if old_n == 0:
        return False
    return new_n < old_n * ABNORMAL_DROP_RATIO


# 诊断文件路径（仓库根目录 _diag.json），记录每轮各板块实抓条数与拦截原因，
# 供排查「源站到底还返不返回数据」。日志在 Actions 上不易取，落文件最可靠。
_ROOT_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def _write_diag(diag: dict):
    try:
        p = os.path.join(_ROOT_DIR, "_diag.json")
        with open(p, "w", encoding="utf-8") as f:
            json.dump(diag, f, ensure_ascii=False, indent=2)
    except Exception as e:
        print(f"[diag] 写入失败: {e}")


def run_once(send_mail=True):
    """执行一轮抓取+对比+通知"""
    print("开始抓取资费数据...")
    data = fetcher.fetch_all()
    diag = {"ts": time.strftime("%Y-%m-%d %H:%M:%S"), "sections": {}}

    reports = []
    first_time = False  # 本轮是否有板块首次建立基线
    skipped = []        # 被防误报护栏拦截的板块
    for section, new_data in data.items():
        new_items = new_data.get("items", [])
        print(f"对比板块 {section} ({len(new_items)} 条)")
        diag["sections"][section] = {
            "n": len(new_items),
            "err": (new_data.get("error") or "")[:120],
        }

        # 确认源站降级（fetcher 写入 DEGRADE: 标记）且已有基线才跳过对比防误报；
        # 首次运行无基线时必须建立基线，即使本轮网络异常也不跳过（用户要求）。
        # 分类部分失败（Errno 101 抖动等）已抓到多数数据时同样不跳过，
        # 交由下方 _is_abnormal_drop 数量护栏兜底，避免整省无 diff 产出。
        degrade_confirm = "DEGRADE:" in (new_data.get("error") or "")
        if degrade_confirm and snapshot.load_snapshot(section) is not None:
            # 降级但仍有数据时照写快照（不做对比、不通知），交由构建侧判定：
            # build_site 连续 SEC_DEGRADE_ACCEPT 轮偏低才接受并重建基线。
            # 此前直接跳过导致 snapshots/ 为空，湖南/河南的数据长期冻结在旧快照。
            if new_items:
                snapshot.save_snapshot(section, new_data)
                print(f"  [降级] 板块 {section} 本轮 {len(new_items)} 条，"
                      f"已存快照交由构建侧判定（不对比、不通知）")
                diag["sections"][section]["reason"] = "degrade_saved"
            else:
                print(f"  [降级] 板块 {section} 本轮 0 条，跳过对比")
                diag["sections"][section]["reason"] = "degrade_empty"
            skipped.append(section)
            continue
        if not new_items:
            print(f"  [异常] 板块 {section} 未抓到任何数据，跳过对比")
            diag["sections"][section]["reason"] = "empty"
            skipped.append(section)
            continue

        # 防误报护栏：抓取数量骤减，不对比、不覆盖快照，只提醒
        if _is_abnormal_drop(section, new_items):
            print(f"  [护栏] 板块 {section} 抓取数量异常骤减，跳过对比")
            diag["sections"][section]["reason"] = "guard"
            skipped.append(section)
            continue

        # 首次运行：板块还没有基线快照，仅建立基线，不对比不发送
        if snapshot.load_snapshot(section) is None:
            snapshot.check_section(section, new_data)
            print(f"  [首次] 板块 {section} 已建立基线快照，本次不通知")
            diag["sections"][section]["reason"] = "baseline"
            first_time = True
            continue

        r = snapshot.check_section(section, new_data)
        if r:
            reports.append(r)

    if skipped:
        # 用户要求：不再推送"抓取不全/故障"类提醒，避免与正常变更消息重复打扰（仅保留运行日志）
        print(f"[护栏] 异常板块 {len(skipped)} 个: {skipped}")
        skipped_this_round = True
    else:
        skipped_this_round = False

    if reports:
        print(f"[变化] 检测到 {len(reports)} 个板块有变更")
        if send_mail:
            if len(reports) == 1:
                # 单板块变化：单独详细推送，方便查看具体业务
                r = reports[0]
                try:
                    if notifier.send_mail([r]):
                        print(f"[notify] 已推送板块 {r['section']} 变更通知")
                except Exception as e:
                    print(f"[notify] 板块 {r['section']} 推送失败: {e}")
            else:
                # 多省份变化：只推一条各省简单计数汇总，避免刷屏
                try:
                    if notifier.send_summary(reports):
                        print("[notify] 已推送多省变化汇总")
                except Exception as e:
                    print(f"[notify] 多省汇总推送失败: {e}")
        else:
            for r in reports:
                print(f"  {r['section']} 新增 {len(r['added'])} 条 / 消失 {len(r['removed'])} 条")
    elif not skipped_this_round:
        print("本次无资费变化。")
        # 无变化也发一条心跳通知（首次建基线那轮除外；NOCHANGE_NOTIFY=0 可关闭）
        if send_mail and not first_time and not _nochange_notify_disabled():
            try:
                import datetime
                beijing = datetime.datetime.now(datetime.timezone(datetime.timedelta(hours=8)))
                notifier.send_nochange(beijing.strftime("%Y-%m-%d %H:%M:%S"))
                print("[notify] 已发送无变化心跳通知")
            except Exception as e:
                print(f"[notify] 心跳发送失败: {e}")
    _write_diag(diag)


def main():
    import sys
    args = sys.argv[1:]
    if "--init" in args:
        print("初始化快照（不通知）...")
        run_once(send_mail=False)
        print("初始化完成。下次运行将基于此快照对比。")
    elif "--once" in args:
        run_once()
    else:
        print(f"进入循环监控模式，每 {CHECK_INTERVAL}s 检查一次 (Ctrl+C 退出)")
        run_once(send_mail=False)  # 首轮先建快照
        while True:
            time.sleep(CHECK_INTERVAL)
            try:
                run_once()
            except Exception as e:
                print(f"[error] {e}")


if __name__ == "__main__":
    main()
