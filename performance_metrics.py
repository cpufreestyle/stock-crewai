# -*- coding: utf-8 -*-
"""模拟盘绩效指标计算（从 run_virtual_v4.calculate_performance_metrics 抽出）

原来这段逻辑内联在 run_virtual_v4.py 里，且重复实现了最大回撤与夏普计算；
现已统一走 quant_metrics，并把纯计算部分与读日志文件的 I/O 分离，便于单测。
"""
import json
from pathlib import Path
from typing import List, Optional

from quant_metrics import calculate_max_drawdown

# 采样与年化假设：盘内每跑一次记一笔，每天 6 次，一年约 252 个交易日
SAMPLES_PER_DAY = 6
TRADING_DAYS = 252
RISK_FREE_ANNUAL = 3.0
MIN_SAMPLES = 10
MAX_LOG_FILES = 720


def read_total_values(history_dir: Path, max_files: int = MAX_LOG_FILES) -> List[float]:
    """按修改时间读 run_log_*.json，取出每笔的 total_value"""
    log_files = sorted(history_dir.glob("run_log_*.json"),
                       key=lambda f: f.stat().st_mtime)[-max_files:]
    values = []
    for f in log_files:
        try:
            with open(f, "r", encoding="utf-8") as fp:
                data = json.load(fp)
            values.append(data.get("portfolio", {}).get("total_value", 0))
        except Exception:
            continue
    return values


def compute_metrics(values: List[float]) -> Optional[dict]:
    """由净值序列算绩效指标；样本不足返回 None"""
    if len(values) < MIN_SAMPLES:
        return None

    returns = []
    for i in range(1, len(values)):
        if values[i-1] > 0:
            returns.append((values[i] - values[i-1]) / values[i-1])
    if not returns:
        return None

    mean_ret = sum(returns) / len(returns) * 100
    std_ret = (sum((r * 100 - mean_ret) ** 2 for r in returns) / (len(returns) - 1)) ** 0.5

    annual_ret = mean_ret * TRADING_DAYS * SAMPLES_PER_DAY
    annual_std = std_ret * (TRADING_DAYS * SAMPLES_PER_DAY) ** 0.5
    sharpe = (annual_ret - RISK_FREE_ANNUAL) / annual_std if annual_std > 0 else 0
    max_dd = calculate_max_drawdown(values)
    win_rate = sum(1 for r in returns if r > 0) / len(returns) * 100

    return {
        "sharpe_ratio": round(sharpe, 2),
        "max_drawdown": round(max_dd, 2),
        "annual_return": round(annual_ret, 2),
        "annual_volatility": round(annual_std, 2),
        "win_rate": round(win_rate, 1),
        "total_days": len(values),
        "avg_return_per_trade": round(mean_ret, 4),
    }

