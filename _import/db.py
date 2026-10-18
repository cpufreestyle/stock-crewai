"""SQLite 数据持久化 - 替代 JSON 文件存储"""
import json
import os
import sqlite3
from datetime import datetime
from typing import Dict, List, Optional

from config import PORTFOLIO_FILE, TRADE_LOG_FILE, NET_VALUE_HISTORY_FILE

DB_FILE = "stock_crewai.db"


def get_db() -> sqlite3.Connection:
    """获取数据库连接"""
    conn = sqlite3.connect(DB_FILE)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")  # 并发安全
    conn.execute("PRAGMA foreign_keys=ON")
    return conn


def init_db():
    """初始化数据库表"""
    conn = get_db()
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS portfolio (
            id INTEGER PRIMARY KEY CHECK (id = 1),
            data TEXT NOT NULL
        );
        
        CREATE TABLE IF NOT EXISTS trades (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            date TEXT NOT NULL,
            code TEXT NOT NULL,
            name TEXT NOT NULL,
            action TEXT NOT NULL,
            price REAL NOT NULL,
            shares INTEGER NOT NULL,
            pnl REAL DEFAULT 0,
            pnl_pct REAL DEFAULT 0,
            reason TEXT DEFAULT '',
            created_at TEXT DEFAULT (datetime('now'))
        );
        
        CREATE TABLE IF NOT EXISTS net_value_history (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            date TEXT NOT NULL,
            total_value REAL NOT NULL,
            cash REAL NOT NULL,
            position_value REAL DEFAULT 0,
            return_pct REAL DEFAULT 0,
            positions_count INTEGER DEFAULT 0,
            created_at TEXT DEFAULT (datetime('now'))
        );
        
        CREATE INDEX IF NOT EXISTS idx_trades_date ON trades(date);
        CREATE INDEX IF NOT EXISTS idx_net_value_date ON net_value_history(date);
    """)
    conn.commit()
    conn.close()


# ============= Portfolio =============

def load_portfolio_db() -> Dict:
    """从 SQLite 加载持仓"""
    conn = get_db()
    row = conn.execute("SELECT data FROM portfolio WHERE id = 1").fetchone()
    conn.close()
    if row:
        return json.loads(row["data"])
    return {
        "positions": {},
        "cash": 100000,
        "total_capital": 100000,
        "created": datetime.now().isoformat(),
        "total_value": 100000,
        "total_return_pct": 0.0,
    }


def save_portfolio_db(portfolio: Dict):
    """保存持仓到 SQLite"""
    conn = get_db()
    conn.execute(
        "INSERT OR REPLACE INTO portfolio (id, data) VALUES (1, ?)",
        (json.dumps(portfolio, ensure_ascii=False),),
    )
    conn.commit()
    conn.close()


# ============= Trades =============

def save_trade(trade: Dict):
    """保存交易记录"""
    conn = get_db()
    conn.execute(
        """INSERT INTO trades (date, code, name, action, price, shares, pnl, pnl_pct, reason)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (
            trade.get("date", datetime.now().isoformat()),
            trade["code"],
            trade["name"],
            trade["action"],
            trade["price"],
            trade["shares"],
            trade.get("pnl", 0),
            trade.get("pnl_pct", 0),
            trade.get("reason", ""),
        ),
    )
    conn.commit()
    conn.close()


def load_trades(month: str = None, limit: int = 100) -> List[Dict]:
    """加载交易记录"""
    conn = get_db()
    if month:
        rows = conn.execute(
            "SELECT * FROM trades WHERE date LIKE ? ORDER BY date DESC LIMIT ?",
            (f"{month}%", limit),
        ).fetchall()
    else:
        rows = conn.execute(
            "SELECT * FROM trades ORDER BY date DESC LIMIT ?", (limit,)
        ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


# ============= Net Value History =============

def save_net_value(total_value: float, cash: float, position_value: float = 0,
                   return_pct: float = 0, positions_count: int = 0):
    """保存净值记录"""
    conn = get_db()
    conn.execute(
        """INSERT INTO net_value_history 
           (date, total_value, cash, position_value, return_pct, positions_count)
           VALUES (?, ?, ?, ?, ?, ?)""",
        (datetime.now().isoformat(), total_value, cash, position_value, return_pct, positions_count),
    )
    conn.commit()
    conn.close()


def load_net_value_history(days: int = 30) -> List[Dict]:
    """加载净值历史"""
    conn = get_db()
    rows = conn.execute(
        """SELECT * FROM net_value_history 
           WHERE date >= datetime('now', ?) 
           ORDER BY date DESC""",
        (f"-{days} days",),
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


# ============= Migration =============

def migrate_from_json():
    """从 JSON 文件迁移数据到 SQLite"""
    init_db()
    conn = get_db()
    
    # 迁移 portfolio.json
    if os.path.exists(PORTFOLIO_FILE):
        with open(PORTFOLIO_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
        conn.execute("INSERT OR REPLACE INTO portfolio (id, data) VALUES (1, ?)",
                     (json.dumps(data, ensure_ascii=False),))
        print(f"  ✅ portfolio.json → SQLite")
    
    # 迁移交易记录
    history_dir = os.path.join(os.path.dirname(__file__), "history")
    if os.path.exists(history_dir):
        for fname in os.listdir(history_dir):
            if fname.startswith("trades_") and fname.endswith(".json"):
                fpath = os.path.join(history_dir, fname)
                with open(fpath, "r", encoding="utf-8") as f:
                    trades = json.load(f)
                for t in trades:
                    conn.execute(
                        """INSERT OR IGNORE INTO trades 
                           (date, code, name, action, price, shares, pnl, pnl_pct, reason)
                           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                        (
                            t.get("date", ""),
                            t.get("code", t.get("stock_code", "")),
                            t.get("name", ""),
                            t.get("action", ""),
                            t.get("price", 0),
                            t.get("shares", 0),
                            t.get("pnl", 0),
                            t.get("pnl_pct", 0),
                            t.get("reason", ""),
                        ),
                    )
                print(f"  ✅ {fname} → SQLite ({len(trades)} records)")
    
    # 迁移净值历史
    if os.path.exists(NET_VALUE_HISTORY_FILE):
        with open(NET_VALUE_HISTORY_FILE, "r", encoding="utf-8") as f:
            history = json.load(f)
        if isinstance(history, list):
            for h in history:
                conn.execute(
                    """INSERT OR IGNORE INTO net_value_history 
                       (date, total_value, cash, position_value, return_pct, positions_count)
                       VALUES (?, ?, ?, ?, ?, ?)""",
                    (
                        h.get("date", ""),
                        h.get("total_value", 0),
                        h.get("cash", 0),
                        h.get("position_value", 0),
                        h.get("return_pct", 0),
                        h.get("positions_count", 0),
                    ),
                )
            print(f"  ✅ {NET_VALUE_HISTORY_FILE} → SQLite ({len(history)} records)")
    
    conn.commit()
    conn.close()
    print("迁移完成！")


if __name__ == "__main__":
    print("开始数据迁移...")
    migrate_from_json()
