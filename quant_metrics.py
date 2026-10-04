#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""量化指标计算（夏普比率 / 最大回撤）

从 backtest.py 与 performance_report.py 的各两份重复实现合并而来。
合并时修掉两处共有的 ZeroDivisionError：peak 为 0 时直接崩（原 backtest.py:241）。
"""
from typing import List


def calculate_max_drawdown(values: List[float]) -> float:
    """计算最大回撤，返回百分比（0-100）"""
    if not values:
        return 0.0

    peak = values[0]
    max_dd = 0.0

    for v in values:
        if v > peak:
            peak = v
        if peak <= 0:
            # 峰值非正时回撤无定义，跳过而不是除零崩溃
            continue
        dd = (peak - v) / peak * 100
        if dd > max_dd:
            max_dd = dd

    return max_dd


def calculate_sharpe(returns: List[float], risk_free: float = 0.0) -> float:
    """计算夏普比率（简化版，年化因子由调用方决定）"""
    if len(returns) < 2:
        return 0.0

    mean_ret = sum(returns) / len(returns)
    std_ret = (sum((r - mean_ret) ** 2 for r in returns) / (len(returns) - 1)) ** 0.5

    if std_ret == 0:
        return 0.0

    return (mean_ret - risk_free) / std_ret

