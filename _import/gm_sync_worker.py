"""掘金仿真同步 worker - 运行在 .gmenv(Python 3.10 + gmtrade)

职责: 读取 history/gm_sync_queue.json 中待同步订单，登录掘金仿真账户逐单提交，
回写结果。由 gm_broker.dispatch_worker() 后台派发，也可手动运行:

    .gmenv\\Scripts\\python.exe gm_sync_worker.py           # 处理队列
    .gmenv\\Scripts\\python.exe gm_sync_worker.py --dry-run # 仅登录+查资金持仓，不下单
    .gmenv\\Scripts\\python.exe gm_sync_worker.py --retry   # 把 failed 也重新入队

单实例保护: history/gm_sync_queue.json.worker.lock（filelock 非阻塞）
卡死恢复: status=running 且 claimed_at 超过 5 分钟的条目自动回收重试
"""
import argparse
import os
import sys
from datetime import datetime

# 保证独立运行时可导入（worker 不依赖项目其他模块）
_PROJECT_DIR = os.path.dirname(os.path.abspath(__file__))
_QUEUE_FILE = os.path.join(_PROJECT_DIR, "history", "gm_sync_queue.json")
_WORKER_LOCK = _QUEUE_FILE + ".worker.lock"
_DONE_KEEP = 200
_STALE_SECONDS = 300  # running 条目回收阈值


def _env(key, default=""):
    """环境变量优先，.env 文件兜底（worker 内置轻量解析，不依赖 python-dotenv）"""
    v = os.environ.get(key, "").strip()
    if v:
        return v
    env_path = os.path.join(_PROJECT_DIR, ".env")
    if os.path.exists(env_path):
        try:
            with open(env_path, "r", encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if not line or line.startswith("#") or "=" not in line:
                        continue
                    k, _, val = line.partition("=")
                    if k.strip() == key:
                        return val.strip().strip('"').strip("'")
        except Exception:
            pass
    return default


def to_gm_symbol(stock_code):
    """A股代码转掘金格式（与 gm_broker.to_gm_symbol 保持一致）"""
    code = str(stock_code).strip()
    if not code.isdigit() or len(code) != 6:
        return None
    if code.startswith(("6", "9")):
        return "SHSE.%s" % code
    if code.startswith(("0", "3")):
        return "SZSE.%s" % code
    return None


def _log(msg):
    print("[%s] %s" % (datetime.now().strftime("%Y-%m-%d %H:%M:%S"), msg), flush=True)


# ============ 队列操作（与主环境 safe_io 相同的锁协议: 文件路径 + ".lock"） ============

def _locked(queue_file, timeout=30):
    from filelock import FileLock
    return FileLock(queue_file + ".lock", timeout=timeout)


def load_queue():
    import json
    with _locked(_QUEUE_FILE):
        if not os.path.exists(_QUEUE_FILE):
            return {"pending": [], "done": []}
        with open(_QUEUE_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
    data.setdefault("pending", [])
    data.setdefault("done", [])
    return data


def claim_batch():
    """认领待处理条目: pending/超时running → running（attempts+1），返回认领列表"""
    import json
    now = datetime.now()
    with _locked(_QUEUE_FILE):
        if not os.path.exists(_QUEUE_FILE):
            return [], {"pending": [], "done": []}
        with open(_QUEUE_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
        data.setdefault("pending", [])
        data.setdefault("done", [])

        claimed = []
        for item in data["pending"]:
            if item.get("status") in (None, "", "pending"):
                item["status"] = "running"
                item["attempts"] = item.get("attempts", 0) + 1
                item["claimed_at"] = now.isoformat()
                claimed.append(item)
            elif item.get("status") == "running":
                # worker 崩溃残留：超时回收
                claimed_at = item.get("claimed_at", "")
                try:
                    elapsed = (now - datetime.fromisoformat(claimed_at)).total_seconds()
                except Exception:
                    elapsed = _STALE_SECONDS + 1
                if elapsed > _STALE_SECONDS:
                    item["attempts"] = item.get("attempts", 0) + 1
                    item["claimed_at"] = now.isoformat()
                    claimed.append(item)

        with open(_QUEUE_FILE, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
    return claimed, data


def finish_batch(results):
    """按 id 把 running 条目移入 done（status=done/failed + result）"""
    import json
    with _locked(_QUEUE_FILE):
        if not os.path.exists(_QUEUE_FILE):
            return
        with open(_QUEUE_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
        data.setdefault("pending", [])
        data.setdefault("done", [])

        for r in results:
            data["pending"] = [i for i in data["pending"] if i.get("id") != r["id"]]
            data["done"].append({
                **r,
                "finished_at": datetime.now().isoformat(),
            })
        data["done"] = data["done"][-_DONE_KEEP:]

        with open(_QUEUE_FILE, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)


# ============ 掘金下单 ============

def login_gm():
    """登录掘金仿真，返回 gmtrade.api 模块；配置缺失抛异常"""
    try:
        from gmtrade import api as gm
    except Exception as e:
        raise RuntimeError("gmtrade 未安装（在 .gmenv 中: pip install gmtrade）: %s" % e)

    token = _env("GM_TOKEN")
    account_id = _env("GM_ACCOUNT_ID")
    endpoint = _env("GM_ENDPOINT", "api.myquant.cn:9000")
    if not token or not account_id:
        raise RuntimeError("GM_TOKEN / GM_ACCOUNT_ID 未配置（.env）")

    gm.set_token(token)
    gm.set_endpoint(endpoint)
    gm.login(gm.account(account_id=account_id))
    # gm.login 失败只打内部警告不抛异常，用 get_cash 探针确认会话真正可用
    if getattr(gm.get_cash(), "available", None) is None:
        raise RuntimeError("登录失败（token/账户ID 无效或服务不可达），请用 --dry-run 排查")
    return gm


def submit_order(gm, item):
    """提交单笔委托，返回 (ok, message)"""
    symbol = to_gm_symbol(item["code"])
    if symbol is None:
        return False, "不支持的代码: %s" % item["code"]

    action, price, shares = item["action"], float(item["price"]), int(item["shares"])
    if action == "buy":
        volume = shares // 100 * 100
        if volume < 100:
            return False, "买入不足一手(%d股)，跳过" % shares
        side, effect = gm.OrderSide_Buy, gm.PositionEffect_Open
    elif action == "sell":
        if shares < 1:
            return False, "卖出数量无效: %d" % shares
        volume = shares
        side, effect = gm.OrderSide_Sell, gm.PositionEffect_Close
    else:
        return False, "未知操作: %s" % action
    if price <= 0:
        return False, "价格无效: %s" % price

    order = gm.order_volume(
        symbol=symbol,
        volume=volume,
        side=side,
        order_type=gm.OrderType_Limit,
        position_effect=effect,
        price=round(price, 2),
    )
    order_id = getattr(order, "cl_ord_id", "") or getattr(order, "order_id", "")
    return True, "%s %s %d股@%.2f 单号:%s" % (action, symbol, volume, price, order_id)


def process_queue():
    """主流程: 认领 → 登录 → 逐单提交 → 回写"""
    from filelock import FileLock, Timeout

    try:
        worker_lock = FileLock(_WORKER_LOCK, timeout=1)
        worker_lock.acquire()
    except Timeout:
        _log("另一个 worker 实例正在运行，退出")
        return 0
    except Exception as e:
        _log("获取单实例锁失败: %s" % e)
        return 1

    try:
        claimed, _ = claim_batch()
        if not claimed:
            _log("队列无待处理订单")
            return 0

        _log("待同步 %d 笔，登录掘金仿真..." % len(claimed))
        try:
            gm = login_gm()
        except Exception as e:
            _log("登录失败，订单保留在队列: %s" % e)
            # 不标记 failed，等待下次重试（网络/配置恢复后）
            return 1

        results = []
        for item in claimed:
            base = dict(id=item["id"], action=item["action"], code=item["code"],
                        name=item.get("name", ""), price=item.get("price"),
                        shares=item.get("shares"), attempts=item.get("attempts"))
            try:
                ok, msg = submit_order(gm, item)
                base.update(status="done" if ok else "failed", result=msg)
                _log(("✅ " if ok else "❌ ") + msg)
            except Exception as e:
                base.update(status="failed", result="异常: %s" % e)
                _log("❌ %s %s 异常: %s" % (item["action"], item["code"], e))
            results.append(base)

        finish_batch(results)
        done_n = sum(1 for r in results if r["status"] == "done")
        _log("GM_SYNC done=%d failed=%d" % (done_n, len(results) - done_n))
        return 0
    finally:
        try:
            worker_lock.release()
        except Exception:
            pass


def dry_run():
    """登录 + 查询资金/持仓，验证配置（不下单）"""
    try:
        gm = login_gm()
    except Exception as e:
        _log("登录失败: %s" % e)
        return 1
    try:
        cash = gm.get_cash()
        print("可用资金: %s" % getattr(cash, "available", None))
        print("总资产  : %s" % getattr(cash, "total_value", None))
        poss = gm.get_positions() or []
        print("持仓 %d 只:" % len(poss))
        for p in poss:
            if getattr(p, "volume", 0):
                print("  - %s  %d股 (冻结 %s)" % (getattr(p, "symbol", ""), p.volume, getattr(p, "frozen", 0)))
        return 0
    except Exception as e:
        _log("查询失败: %s" % e)
        return 1


def retry_failed():
    """把 done 中 failed 的条目重新入队"""
    import json
    with _locked(_QUEUE_FILE):
        if not os.path.exists(_QUEUE_FILE):
            print("队列为空")
            return 0
        with open(_QUEUE_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
        failed = [i for i in data.get("done", []) if i.get("status") == "failed"]
        for i in failed:
            data["pending"].append({
                "id": i["id"] + "-r", "ts": datetime.now().isoformat(),
                "action": i["action"], "code": i["code"], "name": i.get("name", ""),
                "price": i.get("price"), "shares": i.get("shares"),
                "attempts": 0, "status": "pending",
            })
        data["done"] = [i for i in data.get("done", []) if i.get("status") != "failed"]
        with open(_QUEUE_FILE, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
    print("已重新入队 %d 笔失败订单" % len(failed))
    return 0


if __name__ == "__main__":
    if sys.platform == "win32":
        try:
            sys.stdout.reconfigure(encoding="utf-8")
        except Exception:
            pass
    parser = argparse.ArgumentParser(description="掘金仿真同步 worker")
    parser.add_argument("--dry-run", action="store_true", help="仅登录验证，不下单")
    parser.add_argument("--retry", action="store_true", help="把 failed 订单重新入队")
    args = parser.parse_args()

    if args.dry_run:
        sys.exit(dry_run())
    if args.retry:
        sys.exit(retry_failed())
    sys.exit(process_queue())
