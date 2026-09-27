"""
风控模块 - 仓位计算和风险管理
"""
import numpy as np
from typing import Dict, List, Optional


def kelly_criterion(win_rate: float, avg_win: float, avg_loss: float) -> float:
    """
    Kelly Criterion 计算最优仓位
    win_rate: 胜率 (0-1)
    avg_win: 平均盈利比例 (正数，如 0.15 表示15%)
    avg_loss: 平均亏损比例 (正数，如 0.10 表示10%)
    返回: 建议仓位比例 (0-1)
    """
    if avg_loss == 0:
        return 0
    b = avg_win / avg_loss  # 盈亏比
    q = 1 - win_rate
    p = win_rate
    
    kelly = (b * p - q) / b
    return max(0, min(kelly, 0.25))  # 限制最大仓位25%


def position_size(
    total_capital: float,
    entry_price: float,
    stop_loss_pct: float = 0.10,
    risk_per_trade: float = 0.02,
    volatility: float = None
) -> Dict:
    """
    计算仓位大小
    
    参数:
    - total_capital: 总资金
    - entry_price: 买入价
    - stop_loss_pct: 止损比例 (默认10%)
    - risk_per_trade: 每笔交易风险比例 (默认2%)
    - volatility: 历史波动率 (可选)
    
    返回:
    - shares: 买入股数
    - position_value: 持仓金额
    - position_pct: 仓位比例
    - risk_amount: 风险金额
    """
    # 风险金额 = 总资金 * 风险比例
    risk_amount = total_capital * risk_per_trade
    
    # 每股风险 = 买入价 * 止损比例
    risk_per_share = entry_price * stop_loss_pct
    
    # 股数 = 风险金额 / 每股价风险
    shares = int(risk_amount / risk_per_share / 100) * 100  # 整百股
    
    # 持仓金额和比例
    position_value = shares * entry_price
    position_pct = position_value / total_capital
    
    # 如果波动率高，降低仓位
    if volatility is not None and volatility > 0.03:
        adjust_factor = 0.03 / volatility
        shares = int(shares * adjust_factor / 100) * 100
        position_value = shares * entry_price
        position_pct = position_value / total_capital
    
    return {
        "shares": shares,
        "position_value": round(position_value, 2),
        "position_pct": round(position_pct * 100, 2),
        "risk_amount": round(risk_amount, 2),
        "stop_loss_price": round(entry_price * (1 - stop_loss_pct), 2),
        "max_loss_if_stop": round(risk_amount, 2)
    }


def calculate_portfolio_risk(
    positions: List[Dict],
    total_capital: float,
    correlation: float = 0.3
) -> Dict:
    """
    计算组合风险
    positions: [{"code": "000001", "shares": 1000, "avg_cost": 12.5, "stop_loss": 11.5}]
    correlation: 持仓间相关性（0-1）
    """
    if not positions:
        return {"total_risk_pct": 0, "var_95": 0, "max_drawdown_est": 0}
    
    individual_risks = []
    for pos in positions:
        if pos.get("avg_cost") and pos.get("stop_loss"):
            loss_pct = (pos["avg_cost"] - pos["stop_loss"]) / pos["avg_cost"]
            pos_value = pos["shares"] * pos["avg_cost"]
            risk = loss_pct * pos_value
            individual_risks.append(risk)
    
    # 组合VaR (简化版)
    total_exposure = sum(pos["shares"] * pos["avg_cost"] for pos in positions)
    
    # 单个持仓VaR的平方和
    var_sum = sum(r**2 for r in individual_risks)
    # 考虑相关性
    portfolio_var = (1 - correlation) * var_sum ** 0.5 + correlation * sum(individual_risks)
    
    return {
        "total_exposure": round(total_exposure, 2),
        "total_exposure_pct": round(total_exposure / total_capital * 100, 2),
        "estimated_var_1day": round(portfolio_var * 1.65, 2),  # 95% VaR
        "estimated_var_5day": round(portfolio_var * 1.65 * 5**0.5, 2),
        "positions_count": len(positions)
    }


def recommended_stop_loss(
    entry_price: float,
    strategy: str = "conservative",
    recent_volatility: float = None
) -> Dict:
    """
    推荐止损价
    strategy: "conservative"(保守) / "moderate"(中等) / "aggressive"(激进)
    """
    if strategy == "conservative":
        stop_pct = 0.05  # 5%
    elif strategy == "moderate":
        stop_pct = 0.08  # 8%
    else:
        stop_pct = 0.12  # 12%
    
    # 如果有波动率数据，调整止损
    if recent_volatility is not None:
        stop_pct = max(stop_pct, recent_volatility * 2)
    
    return {
        "entry_price": entry_price,
        "stop_loss_price": round(entry_price * (1 - stop_pct), 2),
        "stop_loss_pct": round(stop_pct * 100, 2),
        "max_loss_per_share": round(entry_price * stop_pct, 2),
        "strategy": strategy
    }


def risk_reward_ratio(entry: float, target: float, stop: float) -> Dict:
    """
    计算风险收益比
    """
    risk = abs(entry - stop)
    reward = abs(target - entry)
    
    if risk == 0:
        rr = 0
    else:
        rr = reward / risk
    
    return {
        "entry": entry,
        "target": target,
        "stop": stop,
        "risk": round(risk, 2),
        "reward": round(reward, 2),
        "risk_reward_ratio": round(rr, 2),
        "is_valid": rr >= 2,  # 至少2:1才考虑
        "recommendation": "建议操作" if rr >= 2 else "风险收益比不足，建议寻找更好的机会"
    }


def daily_risk_report(portfolio: Dict, market_regime: str = "震荡市") -> str:
    """
    生成每日风险报告
    """
    positions = portfolio.get("positions", {})
    total_value = portfolio.get("total_value", 0)
    cash = portfolio.get("cash", 0)
    
    if not positions:
        return "当前空仓，无风险暴露。"
    
    lines = ["=== 每日风险报告 ===\n"]
    
    # 仓位分析
    total_exposure = sum(pos["shares"] * pos["avg_cost"] for pos in positions.values())
    total_pct = total_exposure / total_value * 100 if total_value > 0 else 0
    
    lines.append(f"总仓位: {total_pct:.1f}%")
    lines.append(f"现金: {cash:.2f}元")
    lines.append(f"持仓市值: {total_exposure:.2f}元")
    
    # 根据市场状态调整建议
    if market_regime == "熊市":
        max_recommended = 30
        lines.append(f"\n⚠ 当前熊市，建议仓位≤{max_recommended}%")
    elif market_regime == "牛市":
        max_recommended = 80
        lines.append(f"\n✓ 当前牛市，可适当提高仓位至{max_recommended}%")
    else:
        max_recommended = 50
        lines.append(f"\n→ 当前震荡市，建议仓位≤{max_recommended}%")
    
    if total_pct > max_recommended:
        lines.append(f"⚠ 当前仓位超过建议上限，建议减仓至{max_recommended}%以下")
    
    # 检查止损
    lines.append("\n持仓止损检查:")
    for code, pos in positions.items():
        name = pos.get("name", code)
        cost = pos.get("avg_cost")
        stop = pos.get("stop_loss", 0)
        if stop and cost:
            loss_pct = (cost - stop) / cost * 100
            lines.append(f"  {code} {name}: 成本{cost}元, 止损{stop}元 ({loss_pct:.1f}%风险)")
    
    return "\n".join(lines)


if __name__ == "__main__":
    # 测试
    print("=== 仓位计算测试 ===")
    result = position_size(100000, 12.5, 0.10, 0.02)
    print(result)
    
    print("\n=== 风险收益比 ===")
    rr = risk_reward_ratio(entry=12.5, target=15.0, stop=11.5)
    print(rr)
