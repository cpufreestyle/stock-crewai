#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
虚拟盘自动交易系统 v4.0（综合优化版）
改进：
1. 进程互斥锁（防止多实例冲突）
2. 技术指标信号接入（MA/MACD/RSI/KDJ/布林带）
3. 动态止损（基于ATR）
4. 日志轮转（保留7天）
5. 完整企业微信通知（买入/卖出/持仓/错误）
6. 绩效指标（夏普比率、最大回撤）
7. 盘后策略适配
"""
import sys
sys.stdout.reconfigure(encoding='utf-8')
sys.stderr.reconfigure(encoding='utf-8')

from dotenv import load_dotenv
load_dotenv()

import requests
import json
import re
import os
import time
import socket
from datetime import datetime
from pathlib import Path

import portfolio_tracker as pt
from circuit_breaker import circuit_breaker
from signal_dedup import signal_dedup
import risk_manager as rm
import data_fetcher as df
import logging
from logging.handlers import RotatingFileHandler

from config import (
    MAX_POSITIONS, MAX_POSITION_RATIO, SINGLE_POSITION_RATIO,
    STOP_LOSS_RATIO, TAKE_PROFIT_RATIO, ATR_STOP_MULTIPLIER, ATR_PROFIT_MULTIPLIER,
    ATR_HOLDING_DAYS, MIN_CHANGE_PCT, MAX_CHANGE_PCT,
    GOOD_CHANGE_LOW, GOOD_CHANGE_HIGH, MIN_TECH_SCORE,
    NEAR_TAKE_PROFIT_PCT, ATR_STOP_LOSS_ENABLED,
    LOG_MAX_BYTES, LOG_BACKUP_COUNT, NET_VALUE_HISTORY_FILE,
)

# 尝试导入通知模块
try:
    import wechat_notifier as wn
    NOTIFIER_AVAILABLE = True
except:
    NOTIFIER_AVAILABLE = False
    print("[警告] 通知模块不可用")

# 尝试导入技术指标模块
try:
    import technical_indicators as ti
    TECH_AVAILABLE = True
except Exception as e:
    TECH_AVAILABLE = False
    print(f"[警告] 技术指标模块不可用: {e}")


# ========== 进程互斥锁 ==========
lock_socket = None

def check_single_instance():
    """检查是否已有实例运行"""
    global lock_socket
    try:
        lock_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        lock_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        lock_socket.bind(('127.0.0.1', 19999))
        lock_socket.listen(1)
        return True
    except socket.error:
        print("❌ 另一个实例正在运行，退出...")
        return False


# ========== 常量配置 ==========
STOCK_POOL = [
    "000001", "000063", "000100", "000333", "000651",
    "000858", "000895", "002415", "002475", "002594",
    "600016", "600019", "600028", "600030", "600036",
    "600048", "600050", "600104", "600276", "600309",
    "600519", "600887", "600900", "601006", "601012",
    "601088", "601166", "601186", "601318", "601398",
    "601628", "601857", "601888", "601899", "603259",
]

# 日志保留天数
LOG_KEEP_DAYS = 7
LOG_MAX_FILES = LOG_KEEP_DAYS * 24 * 6  # 每10分钟一次，约7天量


# ========== 日志管理 ==========
def setup_logging():
    """配置日志系统（使用 RotatingFileHandler）"""
    history_dir = Path(__file__).parent / "history"
    history_dir.mkdir(exist_ok=True)
    
    log_file = history_dir / "trading.log"
    handler = RotatingFileHandler(
        log_file,
        maxBytes=LOG_MAX_BYTES,
        backupCount=LOG_BACKUP_COUNT,
        encoding="utf-8"
    )
    fmt = "%(asctime)s [%(levelname)s] %(message)s"
    handler.setFormatter(logging.Formatter(fmt, datefmt="%Y-%m-%d %H:%M:%S"))
    
    logger = logging.getLogger("trading")
    logger.setLevel(logging.INFO)
    if not logger.handlers:
        logger.addHandler(handler)
        console = logging.StreamHandler()
        console.setFormatter(logging.Formatter("%(message)s"))
        logger.addHandler(console)
    
    return logger

def cleanup_old_logs():
    """清理过期的历史日志文件"""
    history_dir = Path(__file__).parent / "history"
    history_dir.mkdir(exist_ok=True)
    
    log_files = sorted(history_dir.glob("run_log_*.json"), key=lambda f: f.stat().st_mtime)
    if len(log_files) > 20:
        for f in log_files[:-20]:
            try:
                f.unlink()
            except:
                pass
    
    trade_files = sorted(history_dir.glob("trades_*.json"), key=lambda f: f.stat().st_mtime)
    if len(trade_files) > 30:
        for f in trade_files[:-30]:
            try:
                f.unlink()
            except:
                pass


# ========== 数据获取（统一使用 data_fetcher） ==========
# get_sina_realtime 和 get_market_regime 已迁移到 data_fetcher.py

# ========== 持仓风险管理 ==========
def check_portfolio_risk(portfolio_positions, realtime_data):
    """检查持仓风险（增强版：支持ATR动态止损）"""
    alerts = []
    
    for code, pos in portfolio_positions.items():
        if code not in realtime_data:
            current_price = pos.get("last_price", pos["avg_cost"])
        else:
            current_price = realtime_data[code]["current"]
        
        if current_price <= 0:
            continue
        
        cost = pos["avg_cost"]
        pnl_pct = (current_price - cost) / cost * 100
        
        # 尝试获取ATR计算动态止损
        dynamic_stop_loss = None
        if TECH_AVAILABLE:
            try:
                # 获取持仓天数
                buy_date = datetime.strptime(pos.get("buy_date", datetime.now().strftime("%Y-%m-%d")), "%Y-%m-%d")
                days_held = (datetime.now() - buy_date).days
                
                # 如果持仓超过3天，使用ATR止损
                if days_held >= 3 and code in realtime_data:
                    # 获取历史数据计算ATR
                    klines = ti.get_history_kline(code, days=20)
                    if len(klines) >= 14:
                        highs = [k["high"] for k in klines]
                        lows = [k["low"] for k in klines]
                        closes = [k["close"] for k in klines]
                        atr = ti.calculate_atr(highs, lows, closes)
                        if atr:
                            # ATR止损：价格 - 2倍ATR
                            dynamic_stop_loss = round(current_price - ATR_STOP_MULTIPLIER * atr, 2)
                            # 动态止损不能比固定止损更宽松
                            fixed_stop = round(current_price * STOP_LOSS_RATIO, 2)
                            if dynamic_stop_loss > fixed_stop:
                                dynamic_stop_loss = fixed_stop
            except:
                pass
        
        # 使用更严格的止损线
        stop_loss_price = pos.get("stop_loss", 0)
        if dynamic_stop_loss and dynamic_stop_loss > stop_loss_price:
            stop_loss_price = dynamic_stop_loss
        
        # 止损检查
        if stop_loss_price > 0 and current_price <= stop_loss_price:
            alerts.append({
                "code": code,
                "name": pos["name"],
                "action": "STOP_LOSS",
                "price": current_price,
                "pnl_pct": pnl_pct,
                "reason": f"触发止损线（{pnl_pct:.2f}%，止损{dynamic_stop_loss or stop_loss_price:.2f}）"
            })
        elif pnl_pct >= 20:
            alerts.append({
                "code": code,
                "name": pos["name"],
                "action": "TAKE_PROFIT",
                "price": current_price,
                "pnl_pct": pnl_pct,
                "reason": f"触发止盈线（+{pnl_pct:.2f}%）"
            })
        elif pnl_pct >= 15:
            alerts.append({
                "code": code,
                "name": pos["name"],
                "action": "WARNING",
                "price": current_price,
                "pnl_pct": pnl_pct,
                "reason": f"接近止盈线，注意回撤（+{pnl_pct:.2f}%）"
            })
    
    return alerts


def execute_sell(portfolio_positions, alerts, realtime_data):
    """执行卖出（含通知）"""
    sells = []
    
    for alert in alerts:
        if alert["action"] not in ["STOP_LOSS", "TAKE_PROFIT"]:
            continue
        
        code = alert["code"]
        if code not in portfolio_positions:
            continue
        
        pos = portfolio_positions[code]
        price = alert["price"]
        shares = pos["shares"]
        
        if price <= 0:
            continue
        
        result = pt.update_position(
            stock_code=code,
            stock_name=pos["name"],
            action="sell",
            price=price,
            shares=shares,
            reason=alert["reason"],
            current_prices={code: price}
        )
        
        if "error" not in result:
            pnl = (price - pos["avg_cost"]) * shares
            sells.append({
                "code": code,
                "name": pos["name"],
                "shares": shares,
                "price": price,
                "pnl": pnl,
                "reason": alert["reason"]
            })
            
            if NOTIFIER_AVAILABLE:
                try:
                    wn.notify_sell(code, pos["name"], shares, price, pnl, alert["reason"])
                except:
                    pass
    
    return sells


# ========== 持仓轮换逻辑（v4.1 新增）==========

def check_position_rotation(portfolio_positions, candidates, realtime_data):
    """
    检查持仓轮换机会：如果候选股评分远高于当前持仓，触发轮换
    返回: [{"sell_code", "sell_name", "buy_cand", "reason"}] 列表
    """
    rotations = []
    
    if not candidates:
        return rotations
    
    # 计算持仓评分（用盈亏百分比，越高越好）
    position_scores = {}
    for code, pos in portfolio_positions.items():
        current_price = realtime_data.get(code, {}).get("current", pos.get("last_price", pos["avg_cost"]))
        pnl_pct = (current_price - pos["avg_cost"]) / pos["avg_cost"] * 100
        position_scores[code] = pnl_pct  # 越高越好
    
    # 获取候选股前3名
    top_candidates = candidates[:3]
    
    for cand in top_candidates:
        # 如果候选股已在持仓中，跳过
        if cand["code"] in portfolio_positions:
            continue
        
        # 找到持仓中评分最低的（亏损最多的）
        if not position_scores:
            break
        
        worst_code = min(position_scores, key=position_scores.get)
        worst_pnl = position_scores[worst_code]
        worst_pos = portfolio_positions[worst_code]
        
        # 轮换条件（满足任一即可）：
        # 1. 候选评分 >= 8 且 持仓亏损 > 0.5%
        # 2. 候选评分 >= 7 且 持仓亏损 > 1%
        # 3. 候选评分 >= 6 且 持仓略亏（更激进）
        should_rotate = False
        reason = ""
        
        if cand["tech_score"] >= 8 and worst_pnl < -0.5:
            should_rotate = True
            reason = f"候选{cand['name']}评分{cand['tech_score']}分 且 持仓{worst_pos['name']}亏损{(-worst_pnl):.2f}%"
        elif cand["tech_score"] >= 7 and worst_pnl < -1:
            should_rotate = True
            reason = f"候选{cand['name']}评分{cand['tech_score']}分 且 持仓{worst_pos['name']}亏损{(-worst_pnl):.2f}%"
        elif cand["tech_score"] >= 6 and worst_pnl < 0:
            # 激进策略：候选评分>=6 且 持仓亏损，也轮换
            should_rotate = True
            reason = f"轮换：持仓{worst_pos['name']}亏损{(-worst_pnl):.2f}%, 候选{cand['name']}评分{cand['tech_score']}分"
        
        if should_rotate:
            rotations.append({
                "sell_code": worst_code,
                "sell_name": worst_pos["name"],
                "buy_cand": cand,
                "reason": reason
            })
            # 更新 position_scores（模拟已轮换）
            del position_scores[worst_code]
    
    return rotations


# ========== 高级筛选（技术指标增强） ==========
def advanced_filter(realtime_data, portfolio_positions, cash, total_capital):
    """高级筛选策略（技术指标增强版）"""
    candidates = []
    market_regime = df.get_simple_market_regime()
    
    for code, data in realtime_data.items():
        if code in portfolio_positions:
            continue
        
        if data["current"] <= 0:
            continue
        
        change_pct = data["change_pct"]
        
        # 盘后策略适配：使用昨日涨跌幅
        now = datetime.now()
        is_post_market = now.hour >= 15
        
        if is_post_market:
            # 盘后：放宽筛选条件，关注技术信号
            if change_pct <= MIN_CHANGE_PCT:
                continue
        else:
            # 盘中：正常筛选
            if not (MIN_CHANGE_PCT < change_pct <= MAX_CHANGE_PCT):
                continue
        
        if data["current"] > 200:
            continue
        
        if data["volume"] < 100000:
            continue
        
        # 计算技术评分
        tech_score = 0
        
        # 基础评分
        if data["current"] > data["open"]:
            tech_score += 1
        
        if GOOD_CHANGE_LOW < change_pct <= GOOD_CHANGE_HIGH:
            tech_score += 2
        elif GOOD_CHANGE_HIGH < change_pct <= MAX_CHANGE_PCT:
            tech_score += 1
        
        if data["volume"] > 500000:
            tech_score += 1
        
        if data["high"] > 0 and data["current"] < data["high"] * 0.98:
            tech_score += 1
        
        # 技术指标增强评分
        if TECH_AVAILABLE:
            try:
                analysis = ti.analyze_stock(code)
                if "error" not in analysis:
                    # 信号评分
                    signal = analysis.get("signal", "NEUTRAL")
                    if signal in ["STRONG_BUY", "BUY"]:
                        tech_score += 3
                    elif signal == "WEAK_SELL":
                        tech_score -= 1
                    elif signal == "SELL":
                        continue  # 强烈卖出信号不买入
                    
                    # RSI超卖加分
                    if analysis.get("rsi") and analysis["rsi"] < 30:
                        tech_score += 1
                    
                    # MACD金叉加分
                    if analysis.get("macd_hist") and analysis["macd_hist"] > 0:
                        tech_score += 1
                    
                    # 布林带下轨加分
                    if analysis.get("bollinger_lower") and data["current"] <= analysis["bollinger_lower"]:
                        tech_score += 2
            except:
                pass
        
        # 市场状态调整
        if market_regime == "熊市" and tech_score < 5:
            continue  # 熊市要求更高评分
        elif market_regime == "牛市" and tech_score >= 3:
            pass  # 牛市可降低要求
        
        max_position = total_capital * SINGLE_POSITION_RATIO
        shares = int(max_position / data["current"] / 100) * 100
        
        # A股最低100股限制
        if shares < 100:
            continue
        
        position_value = shares * data["current"]
        if position_value > cash:
            # 尝试减少股数
            shares = int(cash / data["current"] / 100) * 100
            position_value = shares * data["current"]
            if shares < 100:
                continue
        
        candidates.append({
            "code": code,
            "name": data["name"],
            "price": data["current"],
            "change_pct": change_pct,
            "volume": data["volume"],
            "tech_score": tech_score,
            "shares": shares,
            "position_value": position_value
        })
    
    candidates.sort(key=lambda x: (-x["tech_score"], -x["change_pct"]))
    return candidates


def execute_buy(candidates, portfolio_positions, cash, total_capital, realtime_data):
    """执行买入（含通知）"""
    buys = []
    
    position_count = len(portfolio_positions)
    max_positions = MAX_POSITIONS
    
    total_position_value = sum(
        realtime_data.get(code, {}).get("current", pos["avg_cost"]) * pos["shares"]
        for code, pos in portfolio_positions.items()
        if code in realtime_data or True
    )
    position_ratio = total_position_value / total_capital
    
    remaining_cash = cash
    buys_count = 0
    
    for cand in candidates[:3]:
        if position_count + buys_count >= max_positions:
            break
        
        if position_ratio > MAX_POSITION_RATIO:
            break
        
        if cand["position_value"] > remaining_cash:
            continue
        
        price = cand["price"]
        
        if price <= 0:
            continue
        
        # 计算动态止损止盈
        if TECH_AVAILABLE:
            try:
                analysis = ti.analyze_stock(cand["code"])
                if "error" not in analysis and analysis.get("atr"):
                    # ATR止损
                    atr = analysis["atr"]
                    stop_loss = round(price - ATR_STOP_MULTIPLIER * atr, 2)
                    take_profit = round(price + ATR_PROFIT_MULTIPLIER * atr, 2)
                else:
                    stop_loss = round(price * STOP_LOSS_RATIO, 2)
                    take_profit = round(price * TAKE_PROFIT_RATIO, 2)
            except:
                stop_loss = round(price * STOP_LOSS_RATIO, 2)
                take_profit = round(price * TAKE_PROFIT_RATIO, 2)
        else:
            stop_loss = round(price * STOP_LOSS_RATIO, 2)
            take_profit = round(price * TAKE_PROFIT_RATIO, 2)
        
        result = pt.update_position(
            stock_code=cand["code"],
            stock_name=cand["name"],
            action="buy",
            price=price,
            shares=cand["shares"],
            reason=f"技术评分{cand['tech_score']}分 涨幅{cand['change_pct']:.2f}%",
            current_prices={cand["code"]: price}
        )
        
        if "error" not in result:
            pt.set_stop_loss(cand["code"], stop_loss, take_profit)
            remaining_cash -= cand["position_value"]
            buys_count += 1
            
            buys.append({
                "code": cand["code"],
                "name": cand["name"],
                "shares": cand["shares"],
                "price": price,
                "stop_loss": stop_loss,
                "take_profit": take_profit,
                "tech_score": cand["tech_score"]
            })
            
            if NOTIFIER_AVAILABLE:
                try:
                    wn.notify_buy(
                        cand["code"], 
                        cand["name"], 
                        cand["shares"], 
                        price, 
                        f"止损{stop_loss} 目标{take_profit} 评分{cand['tech_score']}"
                    )
                except:
                    pass
    
    return buys


# ========== 绩效计算 ==========
def calculate_performance_metrics():
    """计算绩效指标（夏普比率、最大回撤等）"""
    history_dir = Path(__file__).parent / "history"
    
    # 读取最近30天的日志
    log_files = sorted(history_dir.glob("run_log_*.json"), key=lambda f: f.stat().st_mtime)[-720:]  # 约30天
    
    if len(log_files) < 10:
        return None
    
    values = []
    for f in log_files:
        try:
            with open(f, "r", encoding="utf-8") as fp:
                data = json.load(fp)
                values.append(data.get("portfolio", {}).get("total_value", 0))
        except:
            continue
    
    if len(values) < 10:
        return None
    
    # 计算收益率序列
    returns = []
    for i in range(1, len(values)):
        if values[i-1] > 0:
            ret = (values[i] - values[i-1]) / values[i-1]
            returns.append(ret)
    
    if not returns:
        return None
    
    # 计算指标
    mean_ret = sum(returns) / len(returns) * 100  # 转换为百分比
    std_ret = (sum((r*100 - mean_ret) ** 2 for r in returns) / (len(returns) - 1)) ** 0.5
    
    # 年化收益（每天6次采样，假设交易时段）
    annual_ret = mean_ret * 252 * 6
    annual_std = std_ret * (252 * 6) ** 0.5
    
    # 夏普比率（假设无风险利率3%）
    risk_free = 3.0
    sharpe = (annual_ret - risk_free) / annual_std if annual_std > 0 else 0
    
    # 最大回撤
    peak = values[0]
    max_dd = 0
    for v in values:
        if v > peak:
            peak = v
        dd = (peak - v) / peak * 100
        if dd > max_dd:
            max_dd = dd
    
    # 胜率
    win_count = sum(1 for r in returns if r > 0)
    win_rate = win_count / len(returns) * 100 if returns else 0
    
    return {
        "sharpe_ratio": round(sharpe, 2),
        "max_drawdown": round(max_dd, 2),
        "annual_return": round(annual_ret, 2),
        "annual_volatility": round(annual_std, 2),
        "win_rate": round(win_rate, 1),
        "total_days": len(values),
        "avg_return_per_trade": round(mean_ret, 4)
    }


# ========== 主运行函数 ==========
def run_once():
    """单次运行"""
    print("\n" + "=" * 60)
    print(f"  虚拟盘自动交易 v4.0 ({datetime.now().strftime('%Y-%m-%d %H:%M')})")
    print("=" * 60 + "\n")
    
    # 清理过期日志
    cleanup_old_logs()
    
    portfolio = pt.load_portfolio()
    positions = portfolio.get("positions", {})
    cash = portfolio.get("cash", 100000)
    total_capital = portfolio.get("total_capital", 100000)
    
    # 风控熔断检查
    cb_status = circuit_breaker.get_status()
    if cb_status["tripped"]:
        print(f"⚠️ 风控熔断中: {cb_status['reason']}，剩余冷却 {cb_status['remaining_minutes']}分钟")
        alert_circuit_breaker(cb_status['reason'], cb_status['remaining_minutes'] or 0)
        print("  本次跳过交易，仅刷新行情\n")
    
    # 市场状态
    market_regime = df.get_simple_market_regime()
    print(f"[市场] {market_regime}\n")
    
    # 获取实时行情
    print("=== 获取实时行情 ===")
    realtime_data = df.get_sina_realtime(STOCK_POOL)
    print(f"获取到 {len(realtime_data)} 只股票\n")
    
    # 检查持仓风险
    print("=== 检查持仓风险 ===")
    alerts = check_portfolio_risk(positions, realtime_data)
    
    sells = []
    buys = []
    
    if alerts:
        print(f"发现 {len(alerts)} 个风险信号:")
        for alert_item in alerts:
            icon = "🚨" if alert_item["action"] == "STOP_LOSS" else ("💰" if alert_item["action"] == "TAKE_PROFIT" else "⚠️")
            print(f"  {icon} {alert_item['name']}: {alert_item['reason']}")
            # 发送告警通知
            if alert_item["action"] == "STOP_LOSS":
                alert_stop_loss(alert_item.get("code",""), alert_item["name"], alert_item["current_price"], 0, alert_item.get("pnl_pct",0))
            elif alert_item["action"] == "TAKE_PROFIT":
                alert_take_profit(alert_item.get("code",""), alert_item["name"], alert_item["current_price"], 0, alert_item.get("pnl_pct",0))
        
        sells = execute_sell(positions, alerts, realtime_data)
        if sells:
            print(f"\n已卖出 {len(sells)} 只股票")
            for s in sells:
                icon = "📉" if s["pnl"] < 0 else "📈"
                print(f"  {icon} {s['name']}: {s['shares']}股 @ {s['price']:.2f}元 ({s['pnl']:+.2f}元)")
                # 记录到熔断器
                pnl_pct_val = s.get("pnl_pct", 0)
                pf = pt.load_portfolio()
                circuit_breaker.record_trade(pnl_pct_val, pf.get("total_value", 100000))
    else:
        print("  无风险信号\n")
    
    # 刷新持仓
    portfolio = pt.load_portfolio()
    positions = portfolio.get("positions", {})
    cash = portfolio.get("cash", 100000)
    
    # 筛选买入候选（熔断时跳过）
    print("\n=== 筛选买入候选 ===")
    candidates = []
    if not cb_status["tripped"]:
        candidates = advanced_filter(realtime_data, positions, cash, total_capital)
    
    if candidates:
        print(f"候选 {len(candidates)} 只，选取前 3 只:")
        for i, cand in enumerate(candidates[:3], 1):
            print(f"  {i}. {cand['name']}: {cand['price']:.2f}元 (+{cand['change_pct']:.2f}%) 评分{cand['tech_score']}")
        
        # 去重过滤：冷却期内不重复买入同一股票
        candidates = signal_dedup.filter_duplicate(candidates, code_key="code")
        if not candidates:
            print("  所有候选股票均在冷却期内，跳过买入\n")
        else:
            # === 持仓轮换检查 ===
            print("\n=== 检查持仓轮换 ===")
            rotations = check_position_rotation(positions, candidates, realtime_data)
            
            if rotations:
                print(f"发现 {len(rotations)} 个轮换机会:")
                for rot in rotations:
                    print(f"  🔄 {rot['reason']}")
                    
                    # 执行轮换：先卖后买
                    sell_price = realtime_data.get(rot["sell_code"], {}).get("current", 0)
                    if sell_price <= 0:
                        print(f"  ⚠️ {rot['sell_name']} 价格无效，跳过轮换")
                        continue
                    
                    sell_result = pt.update_position(
                        stock_code=rot["sell_code"],
                        stock_name=rot["sell_name"],
                        action="sell",
                        price=sell_price,
                        shares=positions[rot["sell_code"]]["shares"],
                        reason=rot["reason"],
                        current_prices=realtime_data
                    )
                    
                    if "error" not in sell_result:
                        print(f"  ✅ 已卖出 {rot['sell_name']}")
                        
                        # 更新现金和持仓
                        portfolio = pt.load_portfolio()
                        cash = portfolio.get("cash", cash)
                        positions = portfolio.get("positions", {})
                        
                        # 买入新股票
                        buy_cand = rot["buy_cand"]
                        buy_result = execute_buy([buy_cand], positions, cash, total_capital, realtime_data)
                        
                        if buy_result:
                            print(f"  ✅ 已买入 {buy_cand['name']}")
                        else:
                            print(f"  ⚠️ 买入 {buy_cand['name']} 失败")
            else:
                print("  无需轮换")
            
            # 正常买入逻辑（如果还有现金和仓位）
            print("\n=== 执行买入 ===")
            buys = execute_buy(candidates, positions, cash, total_capital, realtime_data)
        
        if buys:
            print(f"已买入 {len(buys)} 只股票:")
            for b in buys:
                print(f"  📈 {b['name']}: {b['shares']}股 @ {b['price']:.2f}元 止损{b['stop_loss']} 目标{b['take_profit']}")
        else:
            print("  无符合条件的股票")
    else:
        print("  无候选股票")
    
    # 刷新持仓
    portfolio = pt.load_portfolio()
    positions = portfolio.get("positions", {})
    cash = portfolio.get("cash", 100000)
    total_value = portfolio.get("total_value", total_capital)
    total_return_pct = portfolio.get("total_return_pct", 0)
    
    # 计算绩效指标
    metrics = calculate_performance_metrics()
    
    # 显示持仓
    print("\n" + "=" * 60)
    print(f"  持仓状态 ({datetime.now().strftime('%Y-%m-%d %H:%M')})")
    print("=" * 60 + "\n")
    
    print(f"当前持仓（总资产: {total_value:,.2f}元, 总收益: {total_return_pct:+.2f}%, 现金: {cash:,.2f}元）:")
    
    for code, pos in positions.items():
        current_price = realtime_data.get(code, {}).get("current", pos.get("last_price", pos["avg_cost"]))
        pnl_pct = (current_price - pos["avg_cost"]) / pos["avg_cost"] * 100
        icon = "📈" if pnl_pct > 0 else ("📉" if pnl_pct < 0 else "➡️")
        
        print(f"  {icon} {code} {pos['name']}: {pos['shares']}股 @ {pos['avg_cost']:.2f}元, "
              f"现价{current_price:.2f}元 ({pnl_pct:+.2f}%), "
              f"止损={pos.get('stop_loss', 'N/A')}, 止盈={pos.get('take_profit', 'N/A')}")
    
    # 显示绩效指标
    if metrics:
        print(f"\n📊 绩效指标（近{metrics['total_days']}条数据）:")
        print(f"   夏普比率: {metrics['sharpe_ratio']} | 最大回撤: {metrics['max_drawdown']}%")
        print(f"   年化收益: {metrics['annual_return']}% | 年化波动: {metrics['annual_volatility']}%")
        print(f"   胜率: {metrics['win_rate']}%")
    
    # 保存运行日志
    log_file = Path(__file__).parent / "history" / f"run_log_{datetime.now().strftime('%Y%m%d_%H%M')}.json"
    log_file.parent.mkdir(exist_ok=True)
    
    with open(log_file, "w", encoding="utf-8") as f:
        json.dump({
            "timestamp": datetime.now().isoformat(),
            "portfolio": portfolio,
            "candidates": candidates[:5] if candidates else [],
            "alerts": alerts,
            "buys": buys,
            "sells": sells,
            "metrics": metrics
        }, f, ensure_ascii=False, indent=2)
    
    print(f"\n运行日志已保存: {log_file}")
    
    # 记录净值历史
    try:
        nv_file = Path(__file__).parent / NET_VALUE_HISTORY_FILE
        history = []
        if nv_file.exists():
            with open(nv_file, "r", encoding="utf-8") as nvf:
                history = json.load(nvf)
        
        # 避免同一分钟重复记录
        ts = datetime.now().strftime("%Y-%m-%d %H:%M")
        if not history or history[-1].get("timestamp", "")[:16] != ts:
            history.append({
                "timestamp": datetime.now().isoformat(),
                "total_value": total_value,
                "cash": cash,
                "return_pct": total_return_pct,
                "positions": len(positions),
                "sharpe": metrics.get("sharpe_ratio", "N/A") if metrics else "N/A",
                "max_drawdown": metrics.get("max_drawdown", "N/A") if metrics else "N/A",
            })
            
            # 保留最近 1000 条记录
            if len(history) > 1000:
                history = history[-1000:]
            
            with open(nv_file, "w", encoding="utf-8") as nvf:
                json.dump(history, nvf, ensure_ascii=False, indent=2)
    except Exception as e:
        print(f"净值历史记录失败: {e}")
    
    return portfolio


# ========== 入口 ==========
def main():
    """主函数"""
    import argparse
    
    parser = argparse.ArgumentParser(description="虚拟盘自动交易系统 v4.0")
    parser.add_argument("--loop", action="store_true", help="循环运行模式")
    args = parser.parse_args()
    
    if args.loop:
        # 检查单实例
        if not check_single_instance():
            sys.exit(1)
        
        print("循环运行模式启动（交易时段内每10分钟执行一次）")
        print("按 Ctrl+C 停止\n")
        
        while True:
            now = datetime.now()
            hour = now.hour
            
            if (9 <= hour < 12) or (13 <= hour < 15):
                try:
                    run_once()
                except Exception as e:
                    print(f"运行出错: {e}")
                    import traceback
                    traceback.print_exc()
                    if NOTIFIER_AVAILABLE:
                        try:
                            wn.notify_error(str(e)[:500])
                        except:
                            pass
            else:
                print(f"[{now.strftime('%H:%M')}] 非交易时段，等待中...")
            
            if reload_config():
                print("⚙️ 配置已热重载")
            time.sleep(600)
    else:
        run_once()


if __name__ == "__main__":
    main()