"""
共享状态存储 - 所有 Agent 的结构化共享内存
SQLite-backed，支持事务、历史查询、原子更新
"""
import json
import sqlite3
import logging
import time
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

logger = logging.getLogger("orchestrator")

# 默认数据库路径
DEFAULT_DB_PATH = Path(__file__).parent.parent / "state.db"


class StateStore:
    """SQLite-backed 共享状态存储"""

    def __init__(self, db_path: str = None):
        self.db_path = db_path or str(DEFAULT_DB_PATH)
        self._conn = sqlite3.connect(self.db_path, check_same_thread=False)
        self._conn.execute("PRAGMA journal_mode=WAL")  # 并发读写
        self._conn.execute("PRAGMA synchronous=NORMAL")
        self._init_tables()
        logger.info(f"[StateStore] initialized: {self.db_path}")

    def _init_tables(self):
        """初始化数据表"""
        self._conn.executescript("""
            CREATE TABLE IF NOT EXISTS state (
                key     TEXT PRIMARY KEY,
                value   TEXT NOT NULL,
                updated REAL NOT NULL
            );

            CREATE TABLE IF NOT EXISTS state_history (
                id      INTEGER PRIMARY KEY AUTOINCREMENT,
                key     TEXT NOT NULL,
                value   TEXT NOT NULL,
                updated REAL NOT NULL
            );

            CREATE TABLE IF NOT EXISTS agent_status (
                agent   TEXT PRIMARY KEY,
                status  TEXT NOT NULL DEFAULT 'idle',
                task    TEXT DEFAULT '',
                started REAL DEFAULT 0,
                updated REAL NOT NULL
            );

            CREATE TABLE IF NOT EXISTS trade_log (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                action      TEXT NOT NULL,
                code        TEXT NOT NULL,
                name        TEXT DEFAULT '',
                shares      INTEGER DEFAULT 0,
                price       REAL DEFAULT 0,
                reason      TEXT DEFAULT '',
                agent       TEXT DEFAULT '',
                approved    INTEGER DEFAULT 0,
                executed_at REAL DEFAULT 0,
                created_at  REAL NOT NULL
            );

            CREATE INDEX IF NOT EXISTS idx_history_key ON state_history(key, updated DESC);
            CREATE INDEX IF NOT EXISTS idx_trades_time ON trade_log(created_at DESC);
        """)
        self._conn.commit()

    # ── 通用状态读写 ──────────────────────────────────────────────

    def get(self, key: str, default: Any = None) -> Any:
        """读取状态"""
        row = self._conn.execute(
            "SELECT value FROM state WHERE key = ?", (key,)
        ).fetchone()
        if row is None:
            return default
        try:
            return json.loads(row[0])
        except json.JSONDecodeError:
            return row[0]

    def set(self, key: str, value: Any) -> None:
        """写入状态（带历史记录）"""
        now = time.time()
        value_json = json.dumps(value, ensure_ascii=False, default=str)

        self._conn.execute("""
            INSERT OR REPLACE INTO state (key, value, updated) VALUES (?, ?, ?)
        """, (key, value_json, now))

        # 写入历史
        self._conn.execute("""
            INSERT INTO state_history (key, value, updated) VALUES (?, ?, ?)
        """, (key, value_json, now))

        self._conn.commit()

    def delete(self, key: str) -> None:
        self._conn.execute("DELETE FROM state WHERE key = ?", (key,))
        self._conn.commit()

    def get_history(self, key: str, limit: int = 10) -> List[Dict]:
        """获取某个 key 的变更历史"""
        rows = self._conn.execute("""
            SELECT value, updated FROM state_history
            WHERE key = ? ORDER BY updated DESC LIMIT ?
        """, (key, limit)).fetchall()
        result = []
        for value_json, updated in rows:
            try:
                val = json.loads(value_json)
            except:
                val = value_json
            result.append({
                "value": val,
                "updated": datetime.fromtimestamp(updated).isoformat(),
            })
        return result

    # ── 类型化接口 ────────────────────────────────────────────────

    def get_market_state(self) -> Dict:
        return self.get("market_state", {})

    def set_market_state(self, state: Dict) -> None:
        self.set("market_state", state)

    def get_stock_picks(self) -> List[Dict]:
        return self.get("stock_picks", [])

    def set_stock_picks(self, picks: List[Dict]) -> None:
        self.set("stock_picks", picks)

    def get_risk_assessment(self) -> Dict:
        return self.get("risk_assessment", {})

    def set_risk_assessment(self, assessment: Dict) -> None:
        self.set("risk_assessment", assessment)

    def get_trade_plan(self) -> Dict:
        return self.get("trade_plan", {})

    def set_trade_plan(self, plan: Dict) -> None:
        self.set("trade_plan", plan)

    def get_performance_report(self) -> Dict:
        return self.get("performance_report", {})

    def set_performance_report(self, report: Dict) -> None:
        self.set("performance_report", report)

    # ── Agent 状态 ────────────────────────────────────────────────

    def get_agent_status(self) -> Dict[str, Dict]:
        """获取所有 Agent 状态"""
        rows = self._conn.execute(
            "SELECT agent, status, task, started, updated FROM agent_status"
        ).fetchall()
        return {
            row[0]: {
                "status": row[1],
                "task": row[2],
                "started": datetime.fromtimestamp(row[3]).isoformat() if row[3] else None,
                "updated": datetime.fromtimestamp(row[4]).isoformat(),
            }
            for row in rows
        }

    def update_agent_status(self, agent: str, status: str, task: str = "") -> None:
        """更新 Agent 运行状态"""
        now = time.time()
        started = now if status == "running" else 0
        self._conn.execute("""
            INSERT OR REPLACE INTO agent_status (agent, status, task, started, updated)
            VALUES (?, ?, ?, ?, ?)
        """, (agent, status, task, started, now))
        self._conn.commit()
        logger.info(f"[StateStore] agent_status: {agent} → {status} ({task})")

    # ── 交易记录 ──────────────────────────────────────────────────

    def log_trade(self, action: str, code: str, name: str = "", shares: int = 0,
                  price: float = 0, reason: str = "", agent: str = "",
                  approved: bool = False) -> int:
        """记录交易"""
        now = time.time()
        cursor = self._conn.execute("""
            INSERT INTO trade_log (action, code, name, shares, price, reason, agent, approved, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (action, code, name, shares, price, reason, agent, 1 if approved else 0, now))
        self._conn.commit()
        return cursor.lastrowid

    def approve_trade(self, trade_id: int) -> bool:
        """审批交易"""
        self._conn.execute(
            "UPDATE trade_log SET approved = 1 WHERE id = ?", (trade_id,)
        )
        self._conn.commit()
        return True

    def get_pending_trades(self) -> List[Dict]:
        """获取待审批交易"""
        rows = self._conn.execute("""
            SELECT id, action, code, name, shares, price, reason, agent, created_at
            FROM trade_log WHERE approved = 0 AND executed_at = 0
            ORDER BY created_at DESC
        """).fetchall()
        return [
            {
                "id": r[0], "action": r[1], "code": r[2], "name": r[3],
                "shares": r[4], "price": r[5], "reason": r[6], "agent": r[7],
                "created_at": datetime.fromtimestamp(r[8]).isoformat(),
            }
            for r in rows
        ]

    def get_recent_trades(self, limit: int = 20) -> List[Dict]:
        """获取最近交易"""
        rows = self._conn.execute("""
            SELECT id, action, code, name, shares, price, reason, agent, approved, executed_at, created_at
            FROM trade_log ORDER BY created_at DESC LIMIT ?
        """, (limit,)).fetchall()
        return [
            {
                "id": r[0], "action": r[1], "code": r[2], "name": r[3],
                "shares": r[4], "price": r[5], "reason": r[6], "agent": r[7],
                "approved": bool(r[8]), "executed_at": r[9],
                "created_at": datetime.fromtimestamp(r[10]).isoformat(),
            }
            for r in rows
        ]

    # ── 清理 ──────────────────────────────────────────────────────

    def cleanup_history(self, max_age_days: int = 30) -> int:
        """清理过期历史"""
        cutoff = time.time() - max_age_days * 86400
        cursor = self._conn.execute(
            "DELETE FROM state_history WHERE updated < ?", (cutoff,)
        )
        self._conn.commit()
        return cursor.rowcount

    def close(self):
        self._conn.close()


# ── 全局实例 ──────────────────────────────────────────────────────
_global_store: Optional[StateStore] = None

def get_state_store() -> StateStore:
    global _global_store
    if _global_store is None:
        _global_store = StateStore()
    return _global_store


# ── 测试 ──────────────────────────────────────────────────────────
if __name__ == "__main__":
    store = StateStore(":memory:")

    # 测试状态读写
    store.set_market_state({"regime": "震荡市", "heat": "中"})
    print("market_state:", store.get_market_state())

    store.set_stock_picks([
        {"code": "000858", "name": "五粮液", "reason": "估值低+趋势好"},
        {"code": "600519", "name": "贵州茅台", "reason": "龙头+分红好"},
    ])
    print("stock_picks:", store.get_stock_picks())

    # Agent 状态
    store.update_agent_status("researcher", "running", "选股分析")
    store.update_agent_status("risk_manager", "idle", "")
    print("agent_status:", store.get_agent_status())

    # 交易记录
    tid = store.log_trade("buy", "000858", "五粮液", 100, 150.5, "估值低", "trader")
    print("pending_trades:", store.get_pending_trades())
    store.approve_trade(tid)
    print("approved!")

    # 历史
    store.set_market_state({"regime": "牛市", "heat": "高"})
    print("history:", store.get_history("market_state", limit=3))

    print("\n✅ StateStore 测试通过")
