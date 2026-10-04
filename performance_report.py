"""虚拟盘绩效报告 - 计算收益率、回撤、夏普比率等"""
import sys; sys.stdout.reconfigure(encoding='utf-8')

import json
import os
from datetime import datetime
import portfolio_tracker as pt
from quant_metrics import calculate_max_drawdown, calculate_sharpe


def generate_report():
    """生成绩效报告"""
    portfolio = pt.load_portfolio()
    
    print("\n" + "=" * 60)
    print("  虚拟盘绩效报告")
    print("=" * 60 + "\n")
    
    # 基础信息
    total_value = portfolio.get("total_value", 0)
    total_capital = portfolio.get("total_capital", 100000)
    total_return = portfolio.get("total_return_pct", 0)
    cash = portfolio.get("cash", 0)
    
    print(f"本金: {total_capital:,.2f} 元")
    print(f"总资产: {total_value:,.2f} 元")
    print(f"总收益: {total_return:+.2f}%")
    print(f"现金: {cash:,.2f} 元")
    
    # 持仓信息
    positions = portfolio.get("positions", {})
    if positions:
        print(f"\n持仓数量: {len(positions)} 只")
        total_profit = 0
        for code, pos in positions.items():
            cost = pos["avg_cost"] * pos["shares"]
            # 使用最新价（从portfolio获取）
            current = pos.get("last_price", pos["avg_cost"])
            profit = (current - pos["avg_cost"]) * pos["shares"]
            total_profit += profit
            
            icon = "📈" if profit > 0 else "📉" if profit < 0 else "➡️"
            print(f"  {icon} {code} {pos['name']}: {pos['shares']}股 "
                  f"成本{pos['avg_cost']:.2f} 现值{current:.2f} "
                  f"盈亏{profit:+,.2f}元")
        
        print(f"\n持仓盈亏: {total_profit:+,.2f}元")
    else:
        print("\n当前空仓")
    
    # 交易历史
    print("\n" + "=" * 60)
    print("  交易历史")
    print("=" * 60)
    
    history_dir = os.path.join(os.path.dirname(__file__), "history")
    if os.path.exists(history_dir):
        trade_files = [f for f in os.listdir(history_dir) if f.startswith("trades_") and f.endswith(".json")]
        trade_files.sort(reverse=True)
        
        all_trades = []
        for tf in trade_files[:3]:  # 最近3个月
            with open(os.path.join(history_dir, tf), "r", encoding="utf-8") as f:
                trades = json.load(f)
                all_trades.extend(trades)
        
        if all_trades:
            # 按日期排序
            all_trades.sort(key=lambda x: x.get("date", ""))
            
            total_trades = len(all_trades)
            sell_trades = [t for t in all_trades if t.get("action") == "sell"]
            total_profit = sum(t.get("pnl", 0) for t in sell_trades)
            
            print(f"\n总交易次数: {total_trades}")
            print(f"卖出次数: {len(sell_trades)}")
            print(f"已实现盈亏: {total_profit:+,.2f}元")
            
            if sell_trades:
                win_trades = [t for t in sell_trades if t.get("pnl", 0) > 0]
                win_rate = len(win_trades) / len(sell_trades) * 100
                print(f"胜率: {win_rate:.1f}%")
                
                avg_profit = total_profit / len(sell_trades)
                print(f"平均盈亏: {avg_profit:+,.2f}元/笔")
            
            print(f"\n最近交易:")
            for t in all_trades[-10:]:
                date = t.get("date", "")[:10]
                action = t.get("action", "")
                code = t.get("code", "")
                name = t.get("name", "")
                price = t.get("price", 0)
                shares = t.get("shares", 0)
                pnl = t.get("pnl", 0)
                
                icon = "📈" if pnl > 0 else "📉" if pnl < 0 else "➡️"
                print(f"  {date} {action} {code} {name}: "
                      f"{shares}股 @{price:.2f} "
                      f"{icon}{pnl:+,.2f}元")
        else:
            print("\n暂无交易记录")
    else:
        print("\n暂无交易记录")
    
    # 与大盘对比（简化）
    print("\n" + "=" * 60)
    print("  风险提示")
    print("=" * 60)
    print("\n⚠️  本系统为虚拟盘模拟，不构成投资建议")
    print("⚠️  实际交易需考虑手续费、滑点、流动性等因素")
    print("⚠️  历史表现不代表未来收益")
    
    print("\n报告生成时间: " + datetime.now().strftime("%Y-%m-%d %H:%M:%S"))


if __name__ == "__main__":
    generate_report()
