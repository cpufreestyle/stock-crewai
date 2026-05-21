"""回测系统 - 验证策略历史表现"""
import sys; sys.stdout.reconfigure(encoding='utf-8')
import json
import os
from datetime import datetime, timedelta

import data_fetcher as df
import portfolio_tracker as pt
import risk_manager as rm


def backtest_strategy(
    strategy_name: str,
    stock_pool: list,
    start_date: str,
    end_date: str,
    initial_capital: float = 100000,
    commission: float = 0.0003,  # 万3手续费
    slippage: float = 0.001  # 千1滑点
):
    """
    回测策略
    
    参数：
    - strategy_name: 策略名称
    - stock_pool: 股票池
    - start_date: 开始日期 YYYY-MM-DD
    - end_date: 结束日期 YYYY-MM-DD
    - initial_capital: 初始资金
    - commission: 手续费率
    - slippage: 滑点
    
    返回：
    - 回测结果字典
    """
    print("\n" + "=" * 60)
    print(f"  回测: {strategy_name}")
    print(f"  时间: {start_date} ~ {end_date}")
    print(f"  初始资金: {initial_capital:,.2f}元")
    print("=" * 60 + "\n")

    # 初始化
    capital = initial_capital
    positions = {}  # {code: {"shares": int, "cost": float, "name": str}}
    trades = []
    daily_values = []

    # 生成交易日列表
    date_list = []
    current = datetime.strptime(start_date, "%Y-%m-%d")
    end = datetime.strptime(end_date, "%Y-%m-%d")

    while current <= end:
        if current.weekday() < 5:  # 周一到周五
            date_list.append(current.strftime("%Y-%m-%d"))
        current += timedelta(days=1)

    print(f"共 {len(date_list)} 个交易日\n")

    # 按日回测
    for i, date in enumerate(date_list):
        if i % 20 == 0:
            print(f"进度: {i}/{len(date_list)} ({i/len(date_list)*100:.1f}%)")

        # 获取所有股票当日数据（简化：用新浪行情模拟）
        daily_prices = {}

        # 模拟每日价格（用 realtime 替代历史）
        for code in stock_pool:
            try:
                # 这里简化处理，实际应获取历史价格
                daily_prices[code] = {"open": 0, "close": 0, "high": 0, "low": 0}
            except:
                pass

        # 检查止损止盈
        for code in list(positions.keys()):
            pos = positions[code]
            if code not in daily_prices:
                continue

            current_price = daily_prices[code]["close"]
            stop_loss = pos["cost"] * 0.92
            take_profit = pos["cost"] * 1.20

            # 止损
            if current_price <= stop_loss:
                sell_price = current_price * (1 - slippage)
                revenue = sell_price * pos["shares"] * (1 - commission)
                pnl = revenue - pos["cost"] * pos["shares"]

                capital += revenue
                trades.append({
                    "date": date,
                    "code": code,
                    "action": "sell",
                    "price": sell_price,
                    "shares": pos["shares"],
                    "pnl": pnl,
                    "reason": "止损"
                })
                del positions[code]

            # 止盈
            elif current_price >= take_profit:
                sell_price = current_price * (1 - slippage)
                revenue = sell_price * pos["shares"] * (1 - commission)
                pnl = revenue - pos["cost"] * pos["shares"]

                capital += revenue
                trades.append({
                    "date": date,
                    "code": code,
                    "action": "sell",
                    "price": sell_price,
                    "shares": pos["shares"],
                    "pnl": pnl,
                    "reason": "止盈"
                })
                del positions[code]

        # 买入信号（简化：每日选涨幅0~8%的）
        if len(positions) < 5 and capital > 20000:
            for code in stock_pool:
                if code in positions:
                    continue
                if code not in daily_prices:
                    continue

                current_price = daily_prices[code]["close"]
                change_pct = (current_price / daily_prices[code]["open"] - 1) * 100

                # 买入条件
                if 0 < change_pct <= 8:
                    max_pos_value = initial_capital * 0.20
                    shares = int(max_pos_value / current_price / 100) * 100

                    if shares > 0:
                        buy_price = current_price * (1 + slippage)
                        cost = buy_price * shares * (1 + commission)

                        if cost <= capital:
                            capital -= cost
                            positions[code] = {
                                "shares": shares,
                                "cost": buy_price,
                                "name": daily_prices[code].get("name", code)
                            }
                            trades.append({
                                "date": date,
                                "code": code,
                                "action": "buy",
                                "price": buy_price,
                                "shares": shares,
                                "reason": "买入信号"
                            })

        # 计算当日总资产
        total_value = capital
        for code, pos in positions.items():
            if code in daily_prices:
                total_value += daily_prices[code]["close"] * pos["shares"]

        daily_values.append({
            "date": date,
            "value": total_value
        })

    # 计算回测指标
    final_value = daily_values[-1]["value"] if daily_values else initial_capital
    total_return = (final_value - initial_capital) / initial_capital * 100

    # 最大回撤
    values = [dv["value"] for dv in daily_values]
    max_dd = calculate_max_drawdown(values)

    # 胜率
    sell_trades = [t for t in trades if t["action"] == "sell"]
    win_trades = [t for t in sell_trades if t.get("pnl", 0) > 0]
    win_rate = len(win_trades) / len(sell_trades) * 100 if sell_trades else 0

    # 夏普比率（简化）
    returns = []
    for i in range(1, len(daily_values)):
        ret = (daily_values[i]["value"] / daily_values[i - 1]["value"] - 1) * 100
        returns.append(ret)

    sharpe = calculate_sharpe(returns) if returns else 0

    # 输出报告
    print("\n" + "=" * 60)
    print("  回测结果")
    print("=" * 60)
    print(f"\n初始资金: {initial_capital:,.2f}元")
    print(f"最终资产: {final_value:,.2f}元")
    print(f"总收益: {total_return:+.2f}%")
    print(f"最大回撤: {max_dd:.2f}%")
    print(f"夏普比率: {sharpe:.2f}")
    print(f"交易次数: {len(trades)}")
    print(f"胜率: {win_rate:.1f}%")

    # 保存结果
    result = {
        "strategy": strategy_name,
        "start_date": start_date,
        "end_date": end_date,
        "initial_capital": initial_capital,
        "final_value": final_value,
        "total_return_pct": total_return,
        "max_drawdown_pct": max_dd,
        "sharpe_ratio": sharpe,
        "total_trades": len(trades),
        "win_rate": win_rate,
        "trades": trades,
        "daily_values": daily_values
    }

    output_file = os.path.join(
        os.path.dirname(__file__),
        "history",
        f"backtest_{strategy_name}_{datetime.now().strftime('%Y%m%d_%H%M')}.json"
    )
    os.makedirs(os.path.dirname(output_file), exist_ok=True)
    with open(output_file, "w", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False, indent=2)

    print(f"\n结果已保存: {output_file}")

    return result


def calculate_max_drawdown(values: list) -> float:
    """计算最大回撤"""
    if not values:
        return 0.0

    peak = values[0]
    max_dd = 0.0

    for v in values:
        if v > peak:
            peak = v
        dd = (peak - v) / peak * 100
        if dd > max_dd:
            max_dd = dd

    return max_dd


def calculate_sharpe(returns: list, risk_free: float = 0.0) -> float:
    """计算夏普比率"""
    if len(returns) < 2:
        return 0.0

    mean_ret = sum(returns) / len(returns)
    std_ret = (sum((r - mean_ret) ** 2 for r in returns) / (len(returns) - 1)) ** 0.5

    if std_ret == 0:
        return 0.0

    return (mean_ret - risk_free) / std_ret


def multi_strategy_backtest(code: str, days: int = 90) -> dict:
    """
    对单只股票运行多策略回测
    
    参数：
    - code: 股票代码
    - days: 回测天数（默认90天）
    
    返回：
    - {
        "strategies": {
            "策略名": {
                "收益率": str,
                "最大回撤": str,
                "胜率": str,
                "当前持仓": str
            }
        },
        "best_strategy": str,
        "best_return": str,
        "error": str (如果有错误)
    }
    """
    try:
        from datetime import datetime, timedelta
        import data_fetcher as df
        
        # 获取历史数据
        end_date = datetime.now().strftime("%Y-%m-%d")
        start_date = (datetime.now() - timedelta(days=days)).strftime("%Y-%m-%d")
        
        price_data = df.get_stock_price(code, start_date=start_date, end_date=end_date)
        
        if price_data.empty:
            return {"error": "无历史数据"}
        
        # 策略1: 均线策略（MA5 > MA20 买入，反之卖出）
        ma5 = price_data["收盘"].rolling(5).mean()
        ma20 = price_data["收盘"].rolling(20).mean()
        
        # 计算收益率
        initial_price = price_data["收盘"].iloc[0]
        final_price = price_data["收盘"].iloc[-1]
        buy_hold_return = (final_price - initial_price) / initial_price * 100
        
        # 均线策略收益（简化计算）
        position = 0
        cash = 100000
        shares = 0
        ma_strategy_value = 100000
        
        for i in range(20, len(price_data)):
            if ma5.iloc[i] > ma20.iloc[i] and position == 0:
                # 买入
                shares = cash / price_data["收盘"].iloc[i]
                cash = 0
                position = 1
            elif ma5.iloc[i] < ma20.iloc[i] and position == 1:
                # 卖出
                cash = shares * price_data["收盘"].iloc[i]
                shares = 0
                position = 0
        
        if position == 1:
            cash = shares * price_data["收盘"].iloc[-1]
        
        ma_return = (cash - 100000) / 100000 * 100
        
        # 策略2: RSI策略
        delta = price_data["收盘"].diff()
        gain = (delta.where(delta > 0, 0)).rolling(14).mean()
        loss = (-delta.where(delta < 0, 0)).rolling(14).mean()
        rs = gain / loss
        rsi = 100 - (100 / (1 + rs))
        
        # RSI策略（RSI<30买入，RSI>70卖出）
        cash = 100000
        shares = 0
        position = 0
        
        for i in range(14, len(price_data)):
            if rsi.iloc[i] < 30 and position == 0:
                shares = cash / price_data["收盘"].iloc[i]
                cash = 0
                position = 1
            elif rsi.iloc[i] > 70 and position == 1:
                cash = shares * price_data["收盘"].iloc[i]
                shares = 0
                position = 0
        
        if position == 1:
            cash = shares * price_data["收盘"].iloc[-1]
        
        rsi_return = (cash - 100000) / 100000 * 100
        
        # 构建结果
        strategies = {
            "买入持有": {
                "收益率": f"{buy_hold_return:.2f}%",
                "最大回撤": "N/A",
                "胜率": "N/A",
                "当前持仓": "是" if buy_hold_return > 0 else "否"
            },
            "均线策略": {
                "收益率": f"{ma_return:.2f}%",
                "最大回撤": "N/A",
                "胜率": "N/A",
                "当前持仓": "是" if ma_return > 0 else "否"
            },
            "RSI策略": {
                "收益率": f"{rsi_return:.2f}%",
                "最大回撤": "N/A",
                "胜率": "N/A",
                "当前持仓": "是" if rsi_return > 0 else "否"
            }
        }
        
        # 找出最佳策略
        returns = {
            "买入持有": buy_hold_return,
            "均线策略": ma_return,
            "RSI策略": rsi_return
        }
        
        best_strategy = max(returns, key=returns.get)
        best_return = f"{returns[best_strategy]:.2f}%"
        
        return {
            "strategies": strategies,
            "best_strategy": best_strategy,
            "best_return": best_return
        }
        
    except Exception as e:
        return {"error": str(e)}


if __name__ == "__main__":
    # 测试回测
    stock_pool = ["000001", "000333", "600519", "601318", "603259"]

    result = backtest_strategy(
        strategy_name="均线突破策略",
        stock_pool=stock_pool,
        start_date="2026-01-01",
        end_date="2026-05-20"
    )

    print("\n回测完成！")
