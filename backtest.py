"""回测系统 - 验证策略历史表现"""
import sys; sys.stdout.reconfigure(encoding='utf-8')
import json
import os
from datetime import datetime, timedelta

import data_fetcher as df
from quant_metrics import calculate_max_drawdown, calculate_sharpe



def _trading_dates(start_date: str, end_date: str) -> list:
    """生成起止日期之间的工作日列表（周一到周五，含两端）。"""
    date_list = []
    current = datetime.strptime(start_date, "%Y-%m-%d")
    end = datetime.strptime(end_date, "%Y-%m-%d")
    while current <= end:
        if current.weekday() < 5:
            date_list.append(current.strftime("%Y-%m-%d"))
        current += timedelta(days=1)
    return date_list


def _fetch_daily_prices(date: str, stock_pool: list) -> dict:
    """取当日股票池行情。当前为占位实现（全 0），实际应取历史价格。"""
    daily_prices = {}
    for code in stock_pool:
        try:
            # 这里简化处理，实际应获取历史价格
            daily_prices[code] = {"open": 0, "close": 0, "high": 0, "low": 0}
        except Exception:
            pass
    return daily_prices


def _check_exit_signals(positions: dict, daily_prices: dict, date: str,
                        capital: float, trades: list, commission: float,
                        slippage: float) -> float:
    """逐持仓检查止损(0.92)/止盈(1.20)，平仓并记录成交，返回更新后的资金。"""
    for code in list(positions.keys()):
        pos = positions[code]
        if code not in daily_prices:
            continue

        current_price = daily_prices[code]["close"]
        stop_loss = pos["cost"] * 0.92
        take_profit = pos["cost"] * 1.20

        if current_price > stop_loss and current_price < take_profit:
            continue

        reason = "止损" if current_price <= stop_loss else "止盈"
        sell_price = current_price * (1 - slippage)
        revenue = sell_price * pos["shares"] * (1 - commission)
        capital += revenue
        trades.append({
            "date": date,
            "code": code,
            "action": "sell",
            "price": sell_price,
            "shares": pos["shares"],
            "pnl": revenue - pos["cost"] * pos["shares"],
            "reason": reason
        })
        del positions[code]
    return capital


def _check_entry_signals(positions: dict, daily_prices: dict, date: str,
                         capital: float, initial_capital: float, trades: list,
                         commission: float, slippage: float) -> float:
    """仓位未满且有资金时按涨幅 0~8% 信号买入（每次 20% 仓位，整百股）。"""
    if len(positions) >= 5 or capital <= 20000:
        return capital

    for code, price in daily_prices.items():
        if code in positions:
            continue

        current_price = price["close"]
        change_pct = (current_price / price["open"] - 1) * 100

        # 买入条件
        if not 0 < change_pct <= 8:
            continue

        max_pos_value = initial_capital * 0.20
        shares = int(max_pos_value / current_price / 100) * 100
        if shares <= 0:
            continue

        buy_price = current_price * (1 + slippage)
        cost = buy_price * shares * (1 + commission)
        if cost > capital:
            continue

        capital -= cost
        positions[code] = {
            "shares": shares,
            "cost": buy_price,
            "name": price.get("name", code)
        }
        trades.append({
            "date": date,
            "code": code,
            "action": "buy",
            "price": buy_price,
            "shares": shares,
            "reason": "买入信号"
        })
    return capital


def _daily_value(capital: float, positions: dict, daily_prices: dict) -> float:
    """按当日收盘价计算总资产。"""
    total_value = capital
    for code, pos in positions.items():
        if code in daily_prices:
            total_value += daily_prices[code]["close"] * pos["shares"]
    return total_value


def _compute_metrics(daily_values: list, trades: list,
                    initial_capital: float) -> dict:
    """计算回测指标：总收益/最大回撤/胜率/夏普。"""
    final_value = daily_values[-1]["value"] if daily_values else initial_capital

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

    return {
        "final_value": final_value,
        "total_return": (final_value - initial_capital) / initial_capital * 100,
        "max_dd": max_dd,
        "win_rate": win_rate,
        "sharpe": calculate_sharpe(returns) if returns else 0,
    }


def _save_backtest_result(result: dict, strategy_name: str) -> str:
    """把回测结果写入 history/backtest_<策略>_<时间戳>.json，返回文件路径。"""
    output_file = os.path.join(
        os.path.dirname(__file__),
        "history",
        f"backtest_{strategy_name}_{datetime.now().strftime('%Y%m%d_%H%M')}.json"
    )
    os.makedirs(os.path.dirname(output_file), exist_ok=True)
    with open(output_file, "w", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False, indent=2)
    return output_file


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
    date_list = _trading_dates(start_date, end_date)
    print(f"共 {len(date_list)} 个交易日\n")

    # 按日回测
    for i, date in enumerate(date_list):
        if i % 20 == 0:
            print(f"进度: {i}/{len(date_list)} ({i/len(date_list)*100:.1f}%)")

        daily_prices = _fetch_daily_prices(date, stock_pool)
        capital = _check_exit_signals(positions, daily_prices, date, capital, trades, commission, slippage)
        capital = _check_entry_signals(positions, daily_prices, date, capital, initial_capital, trades, commission, slippage)

        daily_values.append({
            "date": date,
            "value": _daily_value(capital, positions, daily_prices)
        })

    # 计算回测指标
    metrics = _compute_metrics(daily_values, trades, initial_capital)
    final_value = metrics["final_value"]
    total_return = metrics["total_return"]
    max_dd = metrics["max_dd"]
    win_rate = metrics["win_rate"]
    sharpe = metrics["sharpe"]

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

    output_file = _save_backtest_result(result, strategy_name)
    print(f"\n结果已保存: {output_file}")

    return result




def _ma_strategy(price_data, ma5, ma20) -> dict:
    """均线策略：MA5 上穿 MA20 买入、下穿卖出，返回收益/权益曲线/成交/末日持仓。"""
    cash = 100000
    shares = 0
    position = 0
    ma_values = [100000.0] * 20
    ma_trades = []
    ma_entry = 0.0

    for i in range(20, len(price_data)):
        close = price_data["收盘"].iloc[i]
        if ma5.iloc[i] > ma20.iloc[i] and position == 0:
            # 买入
            shares = cash / close
            ma_entry = close
            cash = 0
            position = 1
        elif ma5.iloc[i] < ma20.iloc[i] and position == 1:
            # 卖出
            cash = shares * close
            ma_trades.append(cash > ma_entry * shares)
            shares = 0
            position = 0
        ma_values.append(cash + shares * close)

    if position == 1:
        cash = shares * price_data["收盘"].iloc[-1]

    return {
        "total_return": (cash - 100000) / 100000 * 100,
        "values": ma_values,
        "trades": ma_trades,
        "position_end": position,
    }


def _rsi_strategy(price_data, rsi) -> dict:
    """RSI 策略：RSI<30 买入、RSI>70 卖出，返回收益/权益曲线/成交/末日持仓。"""
    cash = 100000
    shares = 0
    position = 0
    rsi_values = [100000.0] * 14
    rsi_trades = []
    rsi_entry = 0.0

    for i in range(14, len(price_data)):
        close = price_data["收盘"].iloc[i]
        if rsi.iloc[i] < 30 and position == 0:
            shares = cash / close
            rsi_entry = close
            cash = 0
            position = 1
        elif rsi.iloc[i] > 70 and position == 1:
            cash = shares * close
            rsi_trades.append(cash > rsi_entry * shares)
            shares = 0
            position = 0
        rsi_values.append(cash + shares * close)

    if position == 1:
        cash = shares * price_data["收盘"].iloc[-1]

    return {
        "total_return": (cash - 100000) / 100000 * 100,
        "values": rsi_values,
        "trades": rsi_trades,
        "position_end": position,
    }


def _compute_rsi(price_data):
    """按 14 日窗口计算 RSI 序列。"""
    delta = price_data["收盘"].diff()
    gain = (delta.where(delta > 0, 0)).rolling(14).mean()
    loss = (-delta.where(delta < 0, 0)).rolling(14).mean()
    rs = gain / loss
    return 100 - (100 / (1 + rs))


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
        bh_values = price_data["收盘"].tolist()

        # 均线策略收益（简化计算）
        ma = _ma_strategy(price_data, ma5, ma20)

        # 策略2: RSI策略
        rsi = _compute_rsi(price_data)
        rsi_res = _rsi_strategy(price_data, rsi)

        # 构建结果：回撤/胜率由各自权益曲线与成交记录算出
        def _metric(values, trades):
            dd = calculate_max_drawdown(values)
            wr = (sum(1 for w in trades if w) / len(trades) * 100) if trades else None
            return (f"{dd:.2f}%", f"{wr:.1f}%" if wr is not None else "无平仓交易")

        bh_dd, _ = _metric(bh_values, [])
        ma_dd, ma_wr = _metric(ma["values"], ma["trades"])
        rsi_dd, rsi_wr = _metric(rsi_res["values"], rsi_res["trades"])

        strategies = {
            "买入持有": {
                "收益率": f"{buy_hold_return:.2f}%",
                "最大回撤": bh_dd,
                "胜率": "不适用",
                "当前持仓": "是"
            },
            "均线策略": {
                "收益率": f"{ma['total_return']:.2f}%",
                "最大回撤": ma_dd,
                "胜率": ma_wr,
                "当前持仓": "是" if ma["position_end"] == 1 else "否"
            },
            "RSI策略": {
                "收益率": f"{rsi_res['total_return']:.2f}%",
                "最大回撤": rsi_dd,
                "胜率": rsi_wr,
                "当前持仓": "是" if rsi_res["position_end"] == 1 else "否"
            },
        }
        
        # 找出最佳策略
        returns = {
            "买入持有": buy_hold_return,
            "均线策略": ma["total_return"],
            "RSI策略": rsi_res["total_return"],
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


