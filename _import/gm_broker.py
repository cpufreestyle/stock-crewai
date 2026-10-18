"""掘金量化仿真平台对接 - 双轨同步（队列 + Python 3.10 桥接 worker）

本地虚拟盘（portfolio.json）为唯一主记录，每笔本地成交后自动镜像下单到
掘金仿真账户（https://www.myquant.cn），参与绩效排行 / 投资大赛。

背景: gmtrade SDK 官方只发布到 Python 3.10（PyPI 无 cp311+ wheel），
主环境为 3.11+，因此采用桥接架构:

    主程序(3.11) --入队--> history/gm_sync_queue.json --派发--> gm_sync_worker.py(.gmenv/3.10)

- 掘金侧任何失败（未安装/未配置/网络/拒单）只记录日志，绝不阻塞本地交易
- 未配置 GM_TOKEN 时自动禁用，零开销
- 一次性搭建桥接环境: powershell -File setup_gm_env.ps1

配置(.env):
    GM_ENABLED=true
    GM_TOKEN=你的Token（官网 交易-账户管理-API交易指引 处复制）
    GM_ACCOUNT_ID=你的账户ID
    GM_ENDPOINT=api.myquant.cn:9000      # 可选，默认官方仿真地址
    GM_PYTHON=自定义worker解释器路径      # 可选，默认 .gmenv\\Scripts\\python.exe

验证: python gm_broker.py
"""
import os
import subprocess
import sys
import uuid
from datetime import datetime
from typing import Dict, List, Optional

from safe_io import safe_load_json, safe_update_json

_PROJECT_DIR = os.path.dirname(os.path.abspath(__file__))
WORKER_SCRIPT = os.path.join(_PROJECT_DIR, "gm_sync_worker.py")
QUEUE_FILE = os.path.join(_PROJECT_DIR, "history", "gm_sync_queue.json")
WORKER_LOG = os.path.join(_PROJECT_DIR, "history", "gm_sync_worker.log")
GM_ENV_DIR = os.path.join(_PROJECT_DIR, ".gmenv")
DONE_KEEP = 200          # done 列表保留条数
_worker_warned = False


# ============ 配置 ============

def _env(key: str, default: str = "") -> str:
    return os.getenv(key, "").strip() or default


def gm_config() -> Dict:
    """读取掘金配置（环境变量优先于 .env 由 python-dotenv 在入口加载）"""
    return {
        "enabled": _env("GM_ENABLED").lower() in ("1", "true", "yes", "on"),
        "token": _env("GM_TOKEN"),
        "account_id": _env("GM_ACCOUNT_ID"),
        "endpoint": _env("GM_ENDPOINT", "api.myquant.cn:9000"),
    }


def to_gm_symbol(stock_code: str) -> Optional[str]:
    """A股代码转掘金格式（6/9 开头沪市，0/3 开头深市，其余不支持）"""
    code = str(stock_code).strip()
    if not code.isdigit() or len(code) != 6:
        return None
    if code.startswith(("6", "9")):
        return f"SHSE.{code}"
    if code.startswith(("0", "3")):
        return f"SZSE.{code}"
    return None  # 北交所等板块掘金股票账户不支持


# ============ 队列 ============

def enqueue_trade(action: str, stock_code: str, price: float, shares: int,
                  stock_name: str = "") -> Dict:
    """本地成交入队，返回队列条目"""
    entry = {
        "id": f"{datetime.now():%Y%m%d%H%M%S}-{action}-{stock_code}-{uuid.uuid4().hex[:6]}",
        "ts": datetime.now().isoformat(),
        "action": action,
        "code": stock_code,
        "name": stock_name,
        "price": round(float(price), 3),
        "shares": int(shares),
        "attempts": 0,
        "status": "pending",
    }

    def _update(q: Dict) -> Dict:
        q.setdefault("pending", []).append(entry)
        q["done"] = q.get("done", [])[-DONE_KEEP:]
        return q

    safe_update_json(QUEUE_FILE, _update, default={"pending": [], "done": []})
    return entry


def queue_stats() -> Dict:
    q = safe_load_json(QUEUE_FILE, default={"pending": [], "done": []})
    pending = q.get("pending", [])
    running = [i for i in pending if i.get("status") == "running"]
    return {
        "pending": len(pending) - len(running),
        "running": len(running),
        "done": len(q.get("done", [])),
        "last_done": (q.get("done") or [{}])[-1],
    }


# ============ worker 派发 ============

def find_worker_python() -> Optional[List[str]]:
    """定位 worker 解释器: GM_PYTHON > .gmenv > py -3.10"""
    custom = _env("GM_PYTHON")
    if custom:
        return [custom] if os.path.exists(custom) or sys.platform != "win32" else None
    env_python = os.path.join(GM_ENV_DIR, "Scripts", "python.exe")
    if os.path.exists(env_python):
        return [env_python]
    # 最后尝试 py 启动器
    try:
        probe = subprocess.run(
            ["py", "-3.10", "-c", "print(1)"],
            capture_output=True, timeout=15, creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0,
        )
        if probe.returncode == 0:
            return ["py", "-3.10"]
    except Exception:
        pass
    return None


def dispatch_worker() -> bool:
    """后台启动 worker 处理队列（fire-and-forget，单实例锁在 worker 内保证）"""
    global _worker_warned
    py_cmd = find_worker_python()
    if not py_cmd:
        if not _worker_warned:
            print("[掘金] 未找到 worker 解释器(.gmenv 或 py -3.10)，订单保留在队列中；"
                  "可运行 setup_gm_env.ps1 搭建，或稍后手动执行 gm_sync_worker.py")
            _worker_warned = True
        return False
    try:
        flags = subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0
        with open(WORKER_LOG, "a", encoding="utf-8") as log:
            subprocess.Popen(
                py_cmd + [WORKER_SCRIPT],
                cwd=_PROJECT_DIR,
                stdout=log,
                stderr=subprocess.STDOUT,
                creationflags=flags,
            )
        return True
    except Exception as e:
        print(f"[掘金] worker 启动失败（订单保留在队列中）: {e}")
        return False


# ============ 同步入口（portfolio_tracker 挂钩调用） ============

def mirror_trade(action: str, stock_code: str, price: float, shares: int,
                 stock_name: str = "") -> Dict:
    """本地成交入队并派发 worker 同步到掘金仿真

    任何异常在此兜底，绝不影响本地交易。
    """
    try:
        cfg = gm_config()
        if not (cfg["enabled"] and cfg["token"] and cfg["account_id"]):
            return {"queued": False, "reason": "disabled"}
        if to_gm_symbol(stock_code) is None:
            return {"queued": False, "reason": f"unsupported code: {stock_code}"}
        if action not in ("buy", "sell"):
            return {"queued": False, "reason": f"unknown action: {action}"}

        entry = enqueue_trade(action, stock_code, price, shares, stock_name)
        print(f"[掘金] 已入队 {action} {stock_name or stock_code} {shares}股@{price:.2f} (id={entry['id']})")
        dispatch_worker()
        return {"queued": True, "id": entry["id"]}
    except Exception as e:
        print(f"[掘金] 同步入队失败 {stock_code}（不影响本地）: {e}")
        return {"queued": False, "error": str(e)}


# ============ 重试/维护 ============

def reset_for_tests():
    """重置模块级状态（仅供测试）"""
    global _worker_warned
    _worker_warned = False


if __name__ == "__main__":
    if sys.platform == "win32":
        try:
            sys.stdout.reconfigure(encoding="utf-8")
        except Exception:
            pass
    print("=" * 60)
    print("  掘金仿真对接状态检查")
    print("=" * 60)
    cfg = gm_config()
    print(f"GM_ENABLED : {os.getenv('GM_ENABLED', '(未设置)')}")
    print(f"GM_TOKEN   : {'已配置' if cfg['token'] else '未配置'}")
    print(f"账户ID     : {cfg['account_id'] or '未配置'}")
    print(f"服务地址   : {cfg['endpoint']}")
    print(f"同步状态   : {'✅ 启用' if cfg['enabled'] and cfg['token'] and cfg['account_id'] else '❌ 禁用'}")
    py_cmd = find_worker_python()
    print(f"worker     : {' '.join(py_cmd) if py_cmd else '❌ 未找到（运行 setup_gm_env.ps1 搭建）'}")
    stats = queue_stats()
    print(f"同步队列   : 待处理 {stats['pending']} / 执行中 {stats['running']} / 已完成 {stats['done']}")
    last = stats["last_done"]
    if last.get("id"):
        print(f"最近一条   : [{last.get('status')}] {last.get('action')} {last.get('name') or last.get('code')} "
              f"{last.get('shares')}股 → {last.get('result', '')[:80]}")
