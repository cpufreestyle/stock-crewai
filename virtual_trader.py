"""
虚拟盘自动交易器 - 基于分析结果自动模拟交易
"""
import json
import os
import re
import time
from datetime import datetime
from typing import Dict, List, Optional

import data_fetcher as df
import portfolio_tracker as pt
import risk_manager as rm
from backtest import multi_strategy_backtest


INITIAL_CAPITAL = 100000
PORTFOLIO_FILE = os.path.join(os.path.dirname(__file__), "portfolio.json")


def init_virtual_account():
    """初始化虚拟账户"""
    portfolio = {
        "positions": {},
        "cash": INITIAL_CAPITAL,
        "total_capital": INITIAL_CAPITAL,
        "created": datetime.now().isoformat(),
        "total_value": INITIAL_CAPITAL,
        "total_return_pct": 0.0,
        "trade_log": []
    }
    with open(PORTFOLIO_FILE, "w", encoding="utf-8") as f:
        json.dump(portfolio, f, ensure_ascii=False, indent=2)
    print(f"[虚拟盘] 初始化完成，本金: {INITIAL_CAPITAL:,.0f}元")
    return portfolio


def get_current_prices(codes: List[str]) -> Dict[str, float]:
    """获取当前价格"""
    prices = {}
    for code in codes:
        try:
            df_price = df.get_stock_price(code)
            if not df_price.empty:
                prices[code] = float(df_price["收盘"].iloc[-1])
            time.sleep(0.5)
        except:
            pass
    return prices


def auto_trade_from_result(result_text: str) -> Dict:
    """
    从分析结果中提取交易信号并自动执行
    
    交易规则：
    1. 单只股票仓位不超过总资金20%
    2. 必须有止损价
    3. 风险收益比 >= 2:1
    4. 根据市场状态控制总仓位
    5. 回测确认策略有效（正收益）才买入
    """
    portfolio = pt.load_portfolio()
    
    # 解析推荐股票
    stocks = []
    lines = result_text.split("\n")
    
    for line in lines:
        # 匹配股票代码
        code_match = re.search(r'(\d{6})', line)
        if not code_match:
            continue
        code = code_match.group(1)
        if not code.startswith(("000", "002", "300", "600", "601", "603", "605")):
            continue
        
        # 提取买入价
        buy_match = re.search(r'买入[价位]?[:：]?\s*(\d+\.?\d*)', line)
        buy_price = float(buy_match.group(1)) if buy_match else None
        
        # 提取止损价
        stop_match = re.search(r'止损[价位]?[:：]?\s*(\d+\.?\d*)', line)
        stop_price = float(stop_match.group(1)) if stop_match else None
        
        # 提取止盈价/目标价
        target_match = re.search(r'(?:止盈|目标)[价位]?[:：]?\s*(\d+\.?\d*)', line)
        target_price = float(target_match.group(1)) if target_match else None
        
        # 提取仓位
        pos_match = re.search(r'仓位[:：]?\s*(\d+)%?', line)
        position_pct = float(pos_match.group(1)) / 100 if pos_match else None
        
        # 股票名称
        name_match = re.search(r'\d{6}\s+(\S+)', line)
        name = name_match.group(1) if name_match else code
        
        # 避免重复
        if not any(s["code"] == code for s in stocks):
            stocks.append({
                "code": code,
                "name": name,
                "buy_price": buy_price,
                "stop_price": stop_price,
                "target_price": target_price,
                "position_pct": position_pct
            })
    
    if not stocks:
        return {"error": "未从分析结果中提取到交易信号", "trades": []}
    
    # 获取当前价格
    codes = [s["code"] for s in stocks]
    prices = get_current_prices(codes)
    
    # 获取市场状态
    regime = df.get_market_regime()
    market_regime = regime.get("regime", "震荡市")
    
    # 根据市场状态决定最大总仓位
    if market_regime == "牛市":
        max_total_pct = 0.80
    elif market_regime == "熊市":
        max_total_pct = 0.30
    else:
        max_total_pct = 0.50
    
    # 当前已有仓位
    current_exposure = sum(
        pos["shares"] * pos["avg_cost"] 
        for pos in portfolio["positions"].values()
    )
    current_pct = current_exposure / portfolio["total_capital"] if portfolio["total_capital"] > 0 else 0
    remaining_pct = max_total_pct - current_pct
    
    trades = []
    
    for stock in stocks[:5]:  # 最多买5只
        code = stock["code"]
        name = stock["name"]
        current_price = prices.get(code)
        
        if not current_price:
            trades.append({"code": code, "action": "SKIP", "reason": "无法获取价格"})
            continue
        
        # 如果已持有，跳过
        if code in portfolio["positions"]:
            trades.append({"code": code, "action": "SKIP", "reason": "已持有"})
            continue
        
        # 止损价：没给的话按8%
        stop_price = stock["stop_price"] or current_price * 0.92
        target_price = stock["target_price"] or current_price * 1.20
        
        # 风险收益比检查
        rr = rm.risk_reward_ratio(current_price, target_price, stop_price)
        if not rr["is_valid"]:
            trades.append({"code": code, "action": "SKIP", "reason": f"风险收益比{rr['risk_reward_ratio']:.1f}:1不足2:1"})
            continue
        
        # 仓位计算
        stop_loss_pct = abs(current_price - stop_price) / current_price
        pos = rm.position_size(
            portfolio["cash"],
            current_price,
            stop_loss_pct,
            risk_per_trade=0.02
        )
        
        # 单只股票不超过20%
        single_max = portfolio["total_capital"] * 0.20
        if pos["position_value"] > single_max:
            shares = int(single_max / current_price / 100) * 100
            pos["position_value"] = shares * current_price
            pos["shares"] = shares
            pos["position_pct"] = round(pos["position_value"] / portfolio["total_capital"] * 100, 2)
        
        # 检查剩余可买仓位
        if pos["position_pct"] / 100 > remaining_pct:
            adj_shares = int(remaining_pct * portfolio["total_capital"] / current_price / 100) * 100
            if adj_shares <= 0:
                trades.append({"code": code, "action": "SKIP", "reason": "总仓位已达上限"})
                continue
            pos["shares"] = adj_shares
            pos["position_value"] = adj_shares * current_price
            pos["position_pct"] = round(pos["position_value"] / portfolio["total_capital"] * 100, 2)
        
        # 检查资金
        if pos["position_value"] > portfolio["cash"]:
            trades.append({"code": code, "action": "SKIP", "reason": "资金不足"})
            continue
        
        # 执行买入
        if pos["shares"] > 0:
            pt.update_position(code, name, "buy", current_price, pos["shares"],
                              reason=f"虚拟盘自动买入 止损{stop_price:.2f} 目标{target_price:.2f}")
            pt.set_stop_loss(code, stop_price, target_price)
            
            remaining_pct -= pos["position_pct"] / 100
            
            trades.append({
                "code": code,
                "name": name,
                "action": "BUY",
                "price": current_price,
                "shares": pos["shares"],
                "value": round(pos["position_value"], 2),
                "stop_loss": stop_price,
                "target": target_price,
                "risk_reward": rr["risk_reward_ratio"],
                "reason": "虚拟盘自动交易"
            })
            
            time.sleep(1)  # 避免限流
    
    # 检查止损
    triggered = pt.check_stop_loss()
    for t in triggered:
        code = t["code"]
        name = t["name"]
        current_price = t["current_price"]
        pos_info = portfolio["positions"].get(code, {})
        shares = pos_info.get("shares", 0)
        if shares > 0:
            pt.update_position(code, name, "sell", current_price, shares,
                              reason=f"触发{t['action']}")
            trades.append({
                "code": code,
                "name": name,
                "action": "SELL",
                "price": current_price,
                "shares": shares,
                "reason": t["action"]
            })
    
    return {
        "trades": trades,
        "market_regime": market_regime,
        "max_total_position": f"{max_total_pct*100:.0f}%",
        "timestamp": datetime.now().isoformat()
    }


def update_portfolio_value():
    """更新持仓市值"""
    portfolio = pt.load_portfolio()
    total_value = portfolio["cash"]
    
    for code, pos in portfolio["positions"].items():
        try:
            df_price = df.get_stock_price(code)
            if not df_price.empty:
                current = float(df_price["收盘"].iloc[-1])
                total_value += current * pos["shares"]
                pos["current_price"] = current
                pos["pnl_pct"] = round((current - pos["avg_cost"]) / pos["avg_cost"] * 100, 2)
            else:
                total_value += pos["avg_cost"] * pos["shares"]
            time.sleep(0.5)
        except:
            total_value += pos["avg_cost"] * pos["shares"]
    
    portfolio["total_value"] = round(total_value, 2)
    portfolio["total_return_pct"] = round(
        (total_value - portfolio["total_capital"]) / portfolio["total_capital"] * 100, 2
    )
    
    with open(PORTFOLIO_FILE, "w", encoding="utf-8") as f:
        json.dump(portfolio, f, ensure_ascii=False, indent=2)
    
    return portfolio


def portfolio_status() -> str:
    """获取虚拟盘状态"""
    portfolio = update_portfolio_value()
    
    lines = [f"💰 虚拟盘状态 ({datetime.now().strftime('%Y-%m-%d %H:%M')})"]
    lines.append(f"总资产: {portfolio['total_value']:,.2f}元")
    lines.append(f"总收益: {portfolio['total_return_pct']:+.2f}%")
    lines.append(f"现金: {portfolio['cash']:,.2f}元")
    
    if portfolio["positions"]:
        lines.append(f"\n持仓:")
        for code, pos in portfolio["positions"].items():
            current = pos.get("current_price", pos["avg_cost"])
            pnl = pos.get("pnl_pct", 0)
            pnl_emoji = "📈" if pnl > 0 else "📉" if pnl < 0 else "➡️"
            lines.append(
                f"  {code} {pos['name']}: {pos['shares']}股 "
                f"@{pos['avg_cost']:.2f} → {current:.2f} "
                f"{pnl_emoji}{pnl:+.2f}% "
                f"止损={pos.get('stop_loss', '未设')} "
                f"止盈={pos.get('take_profit', '未设')}"
            )
    else:
        lines.append("\n空仓中")
    
    return "\n".join(lines)


if __name__ == "__main__":
    import sys
    if len(sys.argv) > 1 and sys.argv[1] == "init":
        init_virtual_account()
    elif len(sys.argv) > 1 and sys.argv[1] == "status":
        print(portfolio_status())
    else:
        print(portfolio_status())
