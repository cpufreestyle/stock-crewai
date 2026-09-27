"""券商交易接口 - 支持模拟盘和实盘

支持券商:
- 华泰证券 (模拟盘/实盘)
- 东方财富 (模拟盘/实盘)
- 同花顺 (模拟盘/实盘)
- 通用接口 (efinance)

使用方式:
1. 模拟盘: 直接使用，无需真实账户
2. 实盘: 需配置券商账户信息
"""
import json
import os
import time
from datetime import datetime
from typing import Dict, List, Optional
import sys

# 尝试导入 efinance（东方财富开源库）
try:
    import efinance as ef
    HAS_EFINANCE = True
except ImportError:
    HAS_EFINANCE = False
    print("[警告] efinance 未安装，模拟盘功能受限。安装: pip install efinance")


class MockTrader:
    """模拟盘交易接口（使用本地 portfolio.json）"""

    def __init__(self, portfolio_file="portfolio.json"):
        self.portfolio_file = portfolio_file
        self.trade_log_file = "history/trades_real.json"
        os.makedirs("history", exist_ok=True)

    def get_balance(self) -> Dict:
        """获取资金余额"""
        if os.path.exists(self.portfolio_file):
            with open(self.portfolio_file, "r", encoding="utf-8") as f:
                portfolio = json.load(f)
            return {
                "total_asset": portfolio.get("total_value", 0),
                "available_cash": portfolio.get("cash", 0),
                "market_value": portfolio.get("total_value", 0) - portfolio.get("cash", 0)
            }
        return {"total_asset": 100000, "available_cash": 100000, "market_value": 0}

    def get_positions(self) -> List[Dict]:
        """获取持仓"""
        if os.path.exists(self.portfolio_file):
            with open(self.portfolio_file, "r", encoding="utf-8") as f:
                portfolio = json.load(f)

            positions = []
            for code, pos in portfolio.get("positions", {}).items():
                positions.append({
                    "code": code,
                    "name": pos["name"],
                    "shares": pos["shares"],
                    "avg_cost": pos["avg_cost"],
                    "current_price": pos.get("last_price", pos["avg_cost"])
                })
            return positions
        return []

    def buy(self, stock_code: str, price: float, shares: int) -> Dict:
        """买入"""
        from portfolio_tracker import update_position
        from data_fetcher import get_realtime_quotes

        # 获取股票名称
        try:
            quotes = get_realtime_quotes([stock_code])
            stock_name = quotes[0]["name"] if quotes else stock_code
        except:
            stock_name = stock_code

        result = update_position(stock_code, stock_name, "buy", price, shares, current_prices={stock_code: price})

        if "error" not in result:
            self._log_trade("buy", stock_code, stock_name, price, shares)
            return {"success": True, "message": f"买入成功: {stock_name} {shares}股 @ {price:.2f}"}
        else:
            return {"success": False, "message": result["error"]}

    def sell(self, stock_code: str, price: float, shares: int) -> Dict:
        """卖出"""
        from portfolio_tracker import update_position, load_portfolio
        from data_fetcher import get_realtime_quotes

        portfolio = load_portfolio()
        if stock_code not in portfolio.get("positions", {}):
            return {"success": False, "message": f"未持有 {stock_code}"}

        pos = portfolio["positions"][stock_code]
        stock_name = pos["name"]

        result = update_position(stock_code, stock_name, "sell", price, shares, current_prices={stock_code: price})

        if "error" not in result:
            pnl = (price - pos["avg_cost"]) * shares
            self._log_trade("sell", stock_code, stock_name, price, shares, pnl)
            return {
                "success": True,
                "message": f"卖出成功: {stock_name} {shares}股 @ {price:.2f}, 盈亏: {pnl:+.2f}"
            }
        else:
            return {"success": False, "message": result["error"]}

    def _log_trade(self, action: str, code: str, name: str, price: float, shares: int, pnl: float = 0):
        """记录交易"""
        trades = []
        if os.path.exists(self.trade_log_file):
            with open(self.trade_log_file, "r", encoding="utf-8") as f:
                trades = json.load(f)

        trades.append({
            "datetime": datetime.now().isoformat(),
            "action": action,
            "code": code,
            "name": name,
            "price": price,
            "shares": shares,
            "pnl": round(pnl, 2)
        })

        with open(self.trade_log_file, "w", encoding="utf-8") as f:
            json.dump(trades, f, ensure_ascii=False, indent=2)


class EFinanceTrader:
    """东方财富模拟盘接口（基于 efinance）"""

    def __init__(self):
        if not HAS_EFINANCE:
            raise ImportError("efinance 未安装")

        # 模拟盘账户
        self.initial_capital = 100000
        self.positions = {}
        self.cash = self.initial_capital

    def get_balance(self) -> Dict:
        """获取资金余额"""
        total_market = sum(p["shares"] * p.get("last_price", p["cost"]) for p in self.positions.values())
        return {
            "total_asset": self.cash + total_market,
            "available_cash": self.cash,
            "market_value": total_market
        }

    def get_positions(self) -> List[Dict]:
        """获取持仓"""
        result = []
        for code, pos in self.positions.items():
            result.append({
                "code": code,
                "name": pos.get("name", code),
                "shares": pos["shares"],
                "avg_cost": pos["cost"],
                "current_price": pos.get("last_price", pos["cost"])
            })
        return result

    def buy(self, stock_code: str, price: float, shares: int) -> Dict:
        """买入"""
        cost = price * shares
        if cost > self.cash:
            return {"success": False, "message": f"资金不足: 需要 {cost:.2f}, 可用 {self.cash:.2f}"}

        # 获取股票名称
        try:
            stock_name = ef.stock.get_base_info(stock_code)["股票简称"]
        except:
            stock_name = stock_code

        if stock_code in self.positions:
            pos = self.positions[stock_code]
            total_shares = pos["shares"] + shares
            avg_cost = (pos["cost"] * pos["shares"] + cost) / total_shares
            pos["shares"] = total_shares
            pos["cost"] = avg_cost
        else:
            self.positions[stock_code] = {
                "name": stock_name,
                "shares": shares,
                "cost": price,
                "last_price": price
            }

        self.cash -= cost
        return {"success": True, "message": f"买入成功: {stock_name} {shares}股 @ {price:.2f}"}

    def sell(self, stock_code: str, price: float, shares: int) -> Dict:
        """卖出"""
        if stock_code not in self.positions:
            return {"success": False, "message": f"未持有 {stock_code}"}

        pos = self.positions[stock_code]
        if shares > pos["shares"]:
            shares = pos["shares"]

        revenue = price * shares
        pnl = (price - pos["cost"]) * shares

        pos["shares"] -= shares
        if pos["shares"] <= 0:
            del self.positions[stock_code]

        self.cash += revenue
        return {
            "success": True,
            "message": f"卖出成功: {pos['name']} {shares}股 @ {price:.2f}, 盈亏: {pnl:+.2f}"
        }

    def update_prices(self):
        """更新持仓价格"""
        if not self.positions:
            return

        codes = list(self.positions.keys())
        try:
            for code in codes:
                df = ef.stock.get_realtime_quotes(codes)
                if not df.empty:
                    for _, row in df.iterrows():
                        c = row["股票代码"]
                        if c in self.positions:
                            self.positions[c]["last_price"] = float(row["最新价"])
        except Exception as e:
            print(f"更新价格失败: {e}")


class RealTrader:
    """实盘交易接口（需配置券商账户）

    支持:
    - 华泰证券: easytrader
    - 东方财富: easytrader
    - 同花顺: easytrader

    注意:
    - 实盘交易有风险，请谨慎使用
    - 建议先在模拟盘测试策略
    """

    def __init__(self, broker="ht", account_config=None):
        """初始化实盘接口

        Args:
            broker: 券商代码 (ht=华泰, dfcf=东方财富, ths=同花顺)
            account_config: 账户配置 {
                "account": "账号",
                "password": "密码",
                "exe_path": "客户端路径"
            }
        """
        try:
            import easytrader
            self.trader = easytrader.use(broker)

            if account_config:
                self.trader.prepare(account_config)
            else:
                # 尝试读取配置文件
                config_file = f"{broker}_config.json"
                if os.path.exists(config_file):
                    self.trader.prepare(config_file)

            self.ready = True
            print(f"[实盘] {broker} 接口已初始化")

        except ImportError:
            self.ready = False
            print("[警告] easytrader 未安装，实盘功能不可用。安装: pip install easytrader")
        except Exception as e:
            self.ready = False
            print(f"[错误] 实盘接口初始化失败: {e}")

    def get_balance(self) -> Dict:
        """获取资金余额"""
        if not self.ready:
            return {"error": "接口未初始化"}

        try:
            balance = self.trader.balance
            return {
                "total_asset": balance.get("总资产", 0),
                "available_cash": balance.get("可用金额", 0),
                "market_value": balance.get("股票市值", 0)
            }
        except Exception as e:
            return {"error": str(e)}

    def get_positions(self) -> List[Dict]:
        """获取持仓"""
        if not self.ready:
            return []

        try:
            positions = self.trader.position
            result = []
            for pos in positions:
                result.append({
                    "code": pos.get("证券代码", ""),
                    "name": pos.get("证券名称", ""),
                    "shares": pos.get("股票余额", 0),
                    "avg_cost": pos.get("成本价", 0),
                    "current_price": pos.get("当前价", 0)
                })
            return result
        except Exception as e:
            print(f"[错误] 获取持仓失败: {e}")
            return []

    def buy(self, stock_code: str, price: float, shares: int) -> Dict:
        """买入"""
        if not self.ready:
            return {"success": False, "message": "接口未初始化"}

        try:
            result = self.trader.buy(stock_code, price=price, amount=shares)
            return {"success": True, "message": f"买入委托成功", "data": result}
        except Exception as e:
            return {"success": False, "message": str(e)}

    def sell(self, stock_code: str, price: float, shares: int) -> Dict:
        """卖出"""
        if not self.ready:
            return {"success": False, "message": "接口未初始化"}

        try:
            result = self.trader.sell(stock_code, price=price, amount=shares)
            return {"success": True, "message": f"卖出委托成功", "data": result}
        except Exception as e:
            return {"success": False, "message": str(e)}


# 交易接口工厂
def create_trader(mode="mock", **kwargs):
    """创建交易接口

    Args:
        mode: 交易模式
            - mock: 本地模拟盘（默认）
            - efinance: 东方财富模拟盘
            - real: 实盘（需配置券商账户）

        **kwargs: 实盘配置参数
            - broker: 券商代码
            - account_config: 账户配置
    """
    if mode == "mock":
        return MockTrader()
    elif mode == "efinance":
        return EFinanceTrader()
    elif mode == "real":
        return RealTrader(
            broker=kwargs.get("broker", "ht"),
            account_config=kwargs.get("account_config")
        )
    else:
        raise ValueError(f"未知的交易模式: {mode}")


# 测试
if __name__ == "__main__":
    print("=" * 60)
    print("  交易接口测试")
    print("=" * 60)

    # 测试模拟盘
    trader = create_trader("mock")

    print("\n[余额]")
    print(json.dumps(trader.get_balance(), ensure_ascii=False, indent=2))

    print("\n[持仓]")
    print(json.dumps(trader.get_positions(), ensure_ascii=False, indent=2))

    # 测试买入
    print("\n[买入测试]")
    result = trader.buy("000333", 81.86, 100)
    print(json.dumps(result, ensure_ascii=False, indent=2))

    # 刷新持仓
    print("\n[更新后持仓]")
    print(json.dumps(trader.get_positions(), ensure_ascii=False, indent=2))

    # 测试卖出
    print("\n[卖出测试]")
    result = trader.sell("000333", 82.50, 100)
    print(json.dumps(result, ensure_ascii=False, indent=2))
