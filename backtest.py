"""回测框架 - 基于历史数据验证策略效果

用法:
    python backtest.py --start 20260501 --end 20260525 --capital 100000
"""
import argparse
import json
import os
import sys
from datetime import datetime, timedelta
from typing import Dict, List, Optional

import pandas as pd

# 回测结果输出目录
BACKTEST_DIR = "backtest_results"


def get_date_range(start_str: str, end_str: str) -> list:
    """生成交易日列表（简化版：跳过周末）"""
    start = datetime.strptime(start_str, "%Y%m%d")
    end = datetime.strptime(end_str, "%Y%m%d")
    dates = []
    d = start
    while d <= end:
        if d.weekday() < 5:  # 跳过周末
            dates.append(d.strftime("%Y%m%d"))
        d += timedelta(days=1)
    return dates


def load_historical_data(dates: list) -> Dict[str, List[Dict]]:
    """加载历史行情数据（简化版）

    实际使用时需要对接 data_fetcher 或本地缓存数据
    这里提供模拟数据用于框架测试
    """
    # 尝试从本地缓存加载
    cache_file = os.path.join(BACKTEST_DIR, "historical_cache.json")
    if os.path.exists(cache_file):
        with open(cache_file, "r", encoding="utf-8") as f:
            return json.load(f)

    # 如果无缓存，使用模拟数据
    print("⚠️ 无历史缓存数据，使用模拟数据")
    return generate_mock_data(dates)


def generate_mock_data(dates: list) -> Dict[str, List[Dict]]:
    """生成模拟历史数据"""
    import random
    random.seed(42)

    stocks = [
        {"code": "sh600519", "name": "贵州茅台", "base_price": 1680},
        {"code": "sz000858", "name": "五粮液", "base_price": 148},
        {"code": "sh601318", "name": "中国平安", "base_price": 45},
        {"code": "sz000333", "name": "美的集团", "base_price": 62},
        {"code": "sh600036", "name": "招商银行", "base_price": 33},
        {"code": "sz002594", "name": "比亚迪", "base_price": 265},
        {"code": "sh601012", "name": "隆基绿能", "base_price": 28},
        {"code": "sz300750", "name": "宁德时代", "base_price": 195},
        {"code": "sh600900", "name": "长江电力", "base_price": 29},
        {"code": "sz002475", "name": "立讯精密", "base_price": 35},
    ]

    data = {}
    for stock in stocks:
        history = []
        price = stock["base_price"]
        for date_str in dates:
            change = random.uniform(-0.05, 0.05)
            price = round(price * (1 + change), 2)
            history.append({
                "date": date_str,
                "code": stock["code"],
                "name": stock["name"],
                "price": price,
                "open": round(price * (1 - random.uniform(0, 0.02)), 2),
                "high": round(price * (1 + random.uniform(0, 0.03)), 2),
                "low": round(price * (1 - random.uniform(0, 0.03)), 2),
                "volume": random.randint(50000, 500000),
                "change_pct": round(change * 100, 2),
            })
        data[stock["code"]] = history

    return data


class BacktestEngine:
    """回测引擎"""

    def __init__(self, capital: float = 100000):
        self.initial_capital = capital
        self.cash = capital
        self.positions: Dict[str, Dict] = {}
        self.trades: List[Dict] = []
        self.daily_values: List[Dict] = []
        self.total_trades = 0
        self.wins = 0
        self.losses = 0

    def buy(self, code: str, name: str, price: float, shares: int, date: str):
        cost = price * shares
        if cost > self.cash:
            shares = int(self.cash / price / 100) * 100  # 整手
            cost = price * shares
            if shares <= 0:
                return

        self.cash -= cost
        if code not in self.positions:
            self.positions[code] = {"name": name, "shares": 0, "cost": 0}
        self.positions[code]["shares"] += shares
        self.positions[code]["cost"] += cost
        self.total_trades += 1
        self.trades.append({
            "date": date, "code": code, "name": name,
            "action": "buy", "price": price, "shares": shares,
        })

    def sell(self, code: str, price: float, date: str):
        if code not in self.positions:
            return
        pos = self.positions[code]
        shares = pos["shares"]
        revenue = price * shares
        pnl = revenue - pos["cost"]
        pnl_pct = (pnl / pos["cost"] * 100) if pos["cost"] > 0 else 0

        self.cash += revenue
        self.total_trades += 1
        if pnl > 0:
            self.wins += 1
        else:
            self.losses += 1
        self.trades.append({
            "date": date, "code": code, "name": pos["name"],
            "action": "sell", "price": price, "shares": shares,
            "pnl": round(pnl, 2), "pnl_pct": round(pnl_pct, 2),
        })
        del self.positions[code]

    def get_portfolio_value(self, prices: Dict[str, float]) -> float:
        total = self.cash
        for code, pos in self.positions.items():
            total += pos["shares"] * prices.get(code, 0)
        return round(total, 2)

    def run(self, historical_data: Dict[str, List[Dict]], dates: list,
            strategy_fn=None):
        """
        运行回测
        strategy_fn: 自定义策略函数 (engine, date_data, day_index) -> None
        """
        from config import (
            STOP_LOSS_RATIO, TAKE_PROFIT_RATIO,
            MAX_POSITIONS, MAX_POSITION_RATIO,
        )

        for day_idx, date_str in enumerate(dates):
            # 获取当天行情
            day_data = {}
            prices = {}
            for code, history in historical_data.items():
                # 找到对应日期的数据
                for h in history:
                    if h["date"] == date_str:
                        day_data[code] = h
                        prices[code] = h["price"]
                        break

            if not day_data:
                continue

            # 先检查止损止盈
            to_sell = []
            for code, pos in list(self.positions.items()):
                if code not in prices:
                    continue
                cost_price = pos["cost"] / pos["shares"]
                pnl_pct = (prices[code] - cost_price) / cost_price

                if pnl_pct <= -STOP_LOSS_RATIO:
                    to_sell.append(code)
                elif pnl_pct >= TAKE_PROFIT_RATIO:
                    to_sell.append(code)

            for code in to_sell:
                self.sell(code, prices[code], date_str)

            # 调用自定义策略（买入逻辑）
            if strategy_fn:
                strategy_fn(self, day_data, day_idx)

            # 记录每日净值
            value = self.get_portfolio_value(prices)
            self.daily_values.append({
                "date": date_str,
                "total_value": value,
                "cash": round(self.cash, 2),
                "position_value": round(value - self.cash, 2),
                "return_pct": round((value - self.initial_capital) / self.initial_capital * 100, 2),
                "positions_count": len(self.positions),
            })

    def get_report(self) -> Dict:
        """生成回测报告"""
        if not self.daily_values:
            return {"error": "no data"}

        final = self.daily_values[-1]
        total_return = final["return_pct"]

        # 计算最大回撤
        peak = 0
        max_drawdown = 0
        for dv in self.daily_values:
            if dv["total_value"] > peak:
                peak = dv["total_value"]
            dd = (peak - dv["total_value"]) / peak if peak > 0 else 0
            if dd > max_drawdown:
                max_drawdown = dd

        win_rate = (self.wins / self.total_trades * 100) if self.total_trades > 0 else 0

        return {
            "initial_capital": self.initial_capital,
            "final_value": final["total_value"],
            "total_return_pct": round(total_return, 2),
            "max_drawdown_pct": round(max_drawdown * 100, 2),
            "total_trades": self.total_trades,
            "wins": self.wins,
            "losses": self.losses,
            "win_rate_pct": round(win_rate, 2),
            "trading_days": len(self.daily_values),
            "start_date": self.daily_values[0]["date"],
            "end_date": self.daily_values[-1]["date"],
        }


def simple_strategy(engine: BacktestEngine, day_data: dict, day_idx: int):
    """简单策略：买入涨幅在2-5%的股票"""
    from config import MAX_POSITIONS, MAX_POSITION_RATIO

    if len(engine.positions) >= MAX_POSITIONS:
        return

    candidates = []
    for code, info in day_data.items():
        if code in engine.positions:
            continue
        if 2 <= info.get("change_pct", 0) <= 5:
            candidates.append(info)

    candidates.sort(key=lambda x: x["change_pct"], reverse=True)

    for cand in candidates[:2]:
        if len(engine.positions) >= MAX_POSITIONS:
            break
        price = cand["price"]
        max_amount = engine.initial_capital * MAX_POSITION_RATIO
        shares = int(min(max_amount, engine.cash * 0.5) / price / 100) * 100
        if shares > 0:
            engine.buy(cand["code"], cand["name"], price, shares, cand["date"])


def main():
    parser = argparse.ArgumentParser(description="stock-crewai 回测引擎")
    parser.add_argument("--start", default="20260501", help="开始日期 YYYYMMDD")
    parser.add_argument("--end", default="20260525", help="结束日期 YYYYMMDD")
    parser.add_argument("--capital", type=float, default=100000, help="初始资金")
    args = parser.parse_args()

    dates = get_date_range(args.start, args.end)
    print(f"📅 回测区间: {args.start} ~ {args.end} ({len(dates)} 个交易日)")
    print(f"💰 初始资金: ¥{args.capital:,.0f}")

    historical_data = load_historical_data(dates)
    print(f"📊 加载 {len(historical_data)} 只股票数据")

    engine = BacktestEngine(capital=args.capital)
    engine.run(historical_data, dates, strategy_fn=simple_strategy)

    report = engine.get_report()
    print(f"\n{'='*50}")
    print(f"📈 回测报告")
    print(f"{'='*50}")
    print(f"  初始资金:  ¥{report['initial_capital']:,.0f}")
    print(f"  最终资产:  ¥{report['final_value']:,.2f}")
    print(f"  总收益率:  {report['total_return_pct']:+.2f}%")
    print(f"  最大回撤:  {report['max_drawdown_pct']:.2f}%")
    print(f"  交易次数:  {report['total_trades']}")
    print(f"  胜率:      {report['win_rate_pct']:.1f}%")
    print(f"  交易天数:  {report['trading_days']}")

    # 保存结果
    os.makedirs(BACKTEST_DIR, exist_ok=True)
    result_file = os.path.join(BACKTEST_DIR, f"backtest_{args.start}_{args.end}.json")
    with open(result_file, "w", encoding="utf-8") as f:
        json.dump({
            "report": report,
            "daily_values": engine.daily_values,
            "trades": engine.trades,
        }, f, ensure_ascii=False, indent=2)
    print(f"\n💾 结果已保存: {result_file}")


if __name__ == "__main__":
    main()
