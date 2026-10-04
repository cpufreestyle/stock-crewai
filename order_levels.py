# -*- coding: utf-8 -*-
"""下单价格档位计算（从 run_virtual_v4.execute_buy 抽出）

止损止盈价是直接决定亏多少钱的部分：ATR 路径与固定比例路径必须等价可测，
否则改一个倍数就会静默改变风险敞口。
"""
from typing import Optional, Tuple


def fixed_levels(price: float, stop_ratio: float, profit_ratio: float) -> Tuple[float, float]:
    """固定比例止损止盈（买入价 * 0.92 / * 1.20）"""
    return round(price * stop_ratio, 2), round(price * profit_ratio, 2)


def atr_levels(price: float, atr: float, stop_mult: float, profit_mult: float) -> Tuple[float, float]:
    """ATR 动态止损止盈（价格 -/+ N 倍 ATR）"""
    return round(price - stop_mult * atr, 2), round(price + profit_mult * atr, 2)


def resolve_levels(price: float, atr: Optional[float],
                   stop_ratio: float, profit_ratio: float,
                   stop_mult: float, profit_mult: float) -> Tuple[float, float]:
    """按优先级选止损止盈价：ATR 有效则用动态，否则退回固定比例。

    与 run_virtual_v4.execute_buy 的分支保持一致：atr 为 None/0/缺省都走固定比例。
    """
    if atr:
        return atr_levels(price, atr, stop_mult, profit_mult)
    return fixed_levels(price, stop_ratio, profit_ratio)

