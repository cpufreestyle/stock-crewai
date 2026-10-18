"""交易防护模块 - 实盘接入的防御性检查

供 run_virtual_v4.py 及 trade_tools 使用的统一防线：
1. 熔断检查（circuit_breaker 包装）
2. 价格合理性校验（涨跌停范围 / 停牌 / stale quote 检测）
"""
import logging
from typing import Dict, Optional

logger = logging.getLogger(__name__)

# 涨跌幅限制（普通主板 ±10%，创业板/科创板 ±20%）
def _limit_pct(code: str) -> float:
    if code.startswith(("300", "301", "688")):
        return 0.20
    return 0.10

# 与参考价的最大偏离比例（stale quote / 异常行情防护）
MAX_PRICE_DEVIATION = 0.05


def check_circuit_breaker(total_value: Optional[float] = None) -> tuple:
    """熔断检查。返回 (allowed: bool, reason: str)"""
    try:
        from circuit_breaker import CircuitBreaker
        cb = CircuitBreaker()
        if not cb.can_trade(total_value):
            status = cb.get_status()
            reason = status.get("reason", "熔断中")
            remaining = status.get("remaining_minutes")
            if remaining is not None:
                reason = f"{reason}（剩余冷却 {remaining} 分钟）"
            return False, f"熔断器触发: {reason}"
        return True, ""
    except Exception as e:
        # 防护模块自身故障时保守放行并记录（与 tools/risk_tools 行为一致）
        logger.warning("熔断检查异常，默认放行: %s", e)
        return True, ""


def validate_price(code: str, price: float, prev_close: Optional[float] = None,
                   reference_price: Optional[float] = None) -> tuple:
    """下单前价格合理性校验。返回 (valid: bool, reason: str)

    Args:
        code: 股票代码
        price: 拟委托价格
        prev_close: 昨收盘价（用于涨跌停范围校验）
        reference_price: 参考价（如候选筛选时的价格，检测 stale quote）
    """
    if not price or price <= 0:
        return False, f"价格无效: {price}"

    limit = _limit_pct(code)

    # 涨跌停范围校验（基于昨收）
    if prev_close and prev_close > 0:
        upper = round(prev_close * (1 + limit), 2)
        lower = round(prev_close * (1 - limit), 2)
        if price > upper + 0.001:
            return False, f"价格 {price} 超过涨停价 {upper}"
        if price < lower - 0.001:
            return False, f"价格 {price} 低于跌停价 {lower}"

    # stale quote 校验：与参考价偏离过大说明行情异常或延迟
    if reference_price and reference_price > 0:
        deviation = abs(price - reference_price) / reference_price
        if deviation > MAX_PRICE_DEVIATION:
            return False, (f"价格 {price} 与参考价 {reference_price:.2f} "
                           f"偏离 {deviation*100:.1f}%（>{MAX_PRICE_DEVIATION*100:.0f}%，疑似行情异常）")

    return True, ""


def get_prev_close(code: str, realtime_data: Optional[Dict] = None) -> Optional[float]:
    """从实时行情中提取昨收价"""
    if realtime_data and code in realtime_data:
        return realtime_data[code].get("last_close") or realtime_data[code].get("prev_close")
    return None
