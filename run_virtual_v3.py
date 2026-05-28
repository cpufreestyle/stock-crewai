#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
虚拟盘自动交易系统 v3.0（Bug修复版）
修复：
1. 防止0价格止损（价格≤0时跳过或改用last_close）
2. 止损逻辑增加价格有效性验证
3. 卖出时验证价格>0
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
from datetime import datetime

import portfolio_tracker as pt

# Kronos 金融时序预测模块（可选）
try:
    from kronos_predictor import predict_kronos
    KRONOS_AVAILABLE = True
    print("[Kronos] Module loaded successfully")
except ImportError:
    KRONOS_AVAILABLE = False
    print("[Kronos] WARNING: kronos_predictor.py not found, skipping AI signals")
import risk_manager as rm

# 尝试导入通知模块
try:
    import wechat_notifier as wn
    NOTIFIER_AVAILABLE = True
except:
    NOTIFIER_AVAILABLE = False
    print("[警告] 通知模块不可用")

STOCK_POOL = [
    "000001", "000063", "000100", "000333", "000651",
    "000858", "000895", "002415", "002475", "002594",
    "600016", "600019", "600028", "600030", "600036",
    "600048", "600050", "600104", "600276", "600309",
    "600519", "600887", "600900", "601006", "601012",
    "601088", "601166", "601186", "601318", "601398",
    "601628", "601857", "601888", "601899", "603259",
]


def get_sina_realtime(codes):
    """新浪实时行情（修复版：防止0价格）"""
    sina_codes = []
    for c in codes:
        if c.startswith(("6", "9")):
            sina_codes.append("sh" + c)
        else:
            sina_codes.append("sz" + c)

    url = "https://hq.sinajs.cn/list=" + ",".join(sina_codes)
    
    # 重试机制
    for attempt in range(3):
        try:
            r = requests.get(url, headers={"Referer": "https://finance.sina.com.cn"}, timeout=20)
            break
        except Exception as e:
            if attempt < 2:
                print(f"[重试] 第{attempt+1}次失败: {e}")
                time.sleep(3)
            else:
                print(f"[行情] 获取失败: {e}")
                return {}

    result = {}
    for line in r.text.strip().split("\n"):
        if '"' not in line:
            continue
        eq_pos = line.find("=")
        if eq_pos < 0:
            continue
        var_part = line[:eq_pos]
        data_part = line[eq_pos + 1:].strip().strip('"')
        fields = data_part.split(",")
        if len(fields) < 32:
            continue

        m = re.search(r"hq_str_(sh|sz)(\d+)", var_part)
        if not m:
            continue
        code = m.group(2)

        try:
            name = fields[0]
            open_price = float(fields[1]) if fields[1] and float(fields[1]) > 0 else 0
            last_close = float(fields[2]) if fields[2] and float(fields[2]) > 0 else 0
            current = float(fields[3]) if fields[3] and float(fields[3]) > 0 else 0
            high = float(fields[4]) if fields[4] and float(fields[4]) > 0 else 0
            low = float(fields[5]) if fields[5] and float(fields[5]) > 0 else 0
            volume = int(float(fields[8])) if fields[8] and float(fields[8]) > 0 else 0
            amount = float(fields[9]) if fields[9] and float(fields[9]) > 0 else 0

            # 🔧 修复：如果current为0，使用last_close
            if current <= 0 and last_close > 0:
                current = last_close
                print(f"[修复] {code}({name}): current=0, 使用last_close={last_close}")

            # 计算涨跌幅
            if last_close > 0:
                change_pct = (current / last_close - 1) * 100
            else:
                change_pct = 0

            result[code] = {
                "name": name,
                "open": open_price,
                "last_close": last_close,
                "current": current,
                "high": high,
                "low": low,
                "volume": volume,
                "amount": amount,
                "change_pct": change_pct,
            }
        except Exception as e:
            print(f"[解析] {code} 失败: {e}")
            continue

    return result


def check_portfolio_risk(portfolio_positions, realtime_data):
    """检查持仓风险（修复版：跳过无效价格）"""
    alerts = []
    
    for code, pos in portfolio_positions.items():
        if code not in realtime_data:
            # 如果没有实时数据，使用last_price
            current_price = pos.get("last_price", pos["avg_cost"])
            print(f"[风险检查] {code} 无实时数据，使用last_price={current_price}")
        else:
            current_price = realtime_data[code]["current"]
        
        # 🔧 修复：价格无效时跳过
        if current_price <= 0:
            print(f"[风险检查] {code} 价格无效({current_price})，跳过")
            continue
        
        cost = pos["avg_cost"]
        pnl_pct = (current_price - cost) / cost * 100
        
        # 止损检查
        if pnl_pct <= -8:
            alerts.append({
                "code": code,
                "name": pos["name"],
                "action": "STOP_LOSS",
                "price": current_price,
                "pnl_pct": pnl_pct,
                "reason": f"触发止损线（{pnl_pct:.2f}%）"
            })
        
        # 止盈检查
        elif pnl_pct >= 20:
            alerts.append({
                "code": code,
                "name": pos["name"],
                "action": "TAKE_PROFIT",
                "price": current_price,
                "pnl_pct": pnl_pct,
                "reason": f"触发止盈线（+{pnl_pct:.2f}%）"
            })
        
        # 回撤警告
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
    """执行卖出（修复版：验证价格>0）"""
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
        
        # 🔧 修复：价格无效时不卖出
        if price <= 0:
            print(f"[卖出] {code} 价格无效({price})，跳过卖出！")
            continue
        
        # 执行卖出
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
            
            # 发送通知
            if NOTIFIER_AVAILABLE:
                try:
                    wn.notify_sell(code, pos["name"], shares, price, pnl, alert["reason"])
                except:
                    pass
    
    return sells


def advanced_filter(realtime_data, portfolio_positions, cash, total_capital):
    """高级筛选策略"""
    candidates = []
    
    for code, data in realtime_data.items():
        # 基础过滤
        if code in portfolio_positions:
            continue
        
        if data["current"] <= 0:
            continue
        
        # 涨跌幅筛选
        change_pct = data["change_pct"]
        if not (0 < change_pct <= 6):
            continue
        
        # 价格筛选
        if data["current"] > 200:
            continue
        
        # 成交量筛选
        if data["volume"] < 100000:
            continue
        
        # 计算技术评分
        tech_score = 0
        
        if data["current"] > data["open"]:
            tech_score += 1
        
        if 1 < change_pct <= 4:
            tech_score += 2
        elif 4 < change_pct <= 6:
            tech_score += 1
        
        if data["volume"] > 500000:
            tech_score += 1
        
        if data["high"] > 0 and data["current"] < data["high"] * 0.98:
            tech_score += 1
        
        # 计算可买数量
        max_position = total_capital * 0.20
        shares = int(max_position / data["current"] / 100) * 100
        if shares <= 0:
            continue
        
        position_value = shares * data["current"]
        if position_value > cash:
            continue
        
        # === Kronos AI 信号增强（可选）===
        kronos_bonus = 0
        kronos_signal = {}
        kronos_desc = ""
        if KRONOS_AVAILABLE:
            try:
                import data_fetcher as dfetcher
                kline_df = dfetcher.get_stock_price(code, period="daily")
                if kline_df is not None and len(kline_df) > 20:
                    bars = kline_df.tail(30).to_dict("records")
                    kronos_signal = predict_kronos(code, price=data["current"], bars=bars)
                    if kronos_signal.get("source") not in ("error", None):
                        conf = kronos_signal.get("confidence", 0)
                        action = kronos_signal.get("action", "HOLD")
                        if action == "BUY":
                            kronos_bonus = int(conf * 20)
                        elif action == "SELL":
                            kronos_bonus = -int(conf * 15)
                        kronos_desc = f" Kronos={action}({conf:.0%})"
                else:
                    kronos_desc = " Kronos=no_data"
            except Exception as e:
                kronos_desc = " Kronos=err"
        else:
            kronos_desc = ""

        # === 计算最终评分 ===
        final_score = tech_score + kronos_bonus

        candidates.append({
            "code": code,
            "name": data["name"],
            "price": data["current"],
            "change_pct": change_pct,
            "volume": data["volume"],
            "tech_score": tech_score,
            "kronos_bonus": kronos_bonus,
            "final_score": final_score,
            "kronos_signal": kronos_signal,
            "kronos_desc": kronos_desc,
            "shares": shares,
            "position_value": position_value
        })
    
    # 按技术评分排序
    candidates.sort(key=lambda x: (-x.get("final_score", x["tech_score"]), -x["change_pct"]))
    
    return candidates


def execute_buy(candidates, portfolio_positions, cash, total_capital, realtime_data):
    """执行买入"""
    buys = []
    
    position_count = len(portfolio_positions)
    max_positions = 5
    
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
        
        if position_ratio > 0.80:
            break
        
        if cand["position_value"] > remaining_cash:
            continue
        
        price = cand["price"]
        
        # 🔧 修复：价格无效时不买入
        if price <= 0:
            continue
        
        stop_loss = round(price * 0.92, 2)
        take_profit = round(price * 1.20, 2)
        
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


def run_once():
    """单次运行"""
    print("\n" + "=" * 60)
    print(f"  虚拟盘自动交易 v3.0 ({datetime.now().strftime('%Y-%m-%d %H:%M')})")
    print("=" * 60 + "\n")
    
    portfolio = pt.load_portfolio()
    positions = portfolio.get("positions", {})
    cash = portfolio.get("cash", 100000)
    total_capital = portfolio.get("total_capital", 100000)
    
    # 获取实时行情
    print("=== 获取实时行情 ===")
    realtime_data = get_sina_realtime(STOCK_POOL)
    print(f"获取到 {len(realtime_data)} 只股票\n")
    
    # 检查持仓风险
    print("=== 检查持仓风险 ===")
    alerts = check_portfolio_risk(positions, realtime_data)
    
    if alerts:
        print(f"发现 {len(alerts)} 个风险信号:")
        for alert in alerts:
            icon = "🚨" if alert["action"] == "STOP_LOSS" else ("💰" if alert["action"] == "TAKE_PROFIT" else "⚠️")
            print(f"  {icon} {alert['name']}: {alert['reason']}")
        
        sells = execute_sell(positions, alerts, realtime_data)
        if sells:
            print(f"\n已卖出 {len(sells)} 只股票")
            for s in sells:
                icon = "📉" if s["pnl"] < 0 else "📈"
                print(f"  {icon} {s['name']}: {s['shares']}股 @ {s['price']:.2f}元 ({s['pnl']:+.2f}元)")
    else:
        print("  无风险信号\n")
    
    # 刷新持仓
    portfolio = pt.load_portfolio()
    positions = portfolio.get("positions", {})
    cash = portfolio.get("cash", 100000)
    
    # 筛选买入候选
    print("\n=== 筛选买入候选 ===")
    candidates = advanced_filter(realtime_data, positions, cash, total_capital)
    
    if candidates:
        print(f"候选 {len(candidates)} 只，选取前 3 只:")
        for i, cand in enumerate(candidates[:3], 1):
            print(f"  {i}. {cand['name']}: {cand["price"]:.2f}元 (+{cand["change_pct"]:.2f}%) 评分{cand.get("final_score", cand["tech_score"])}(技术{cand["tech_score"]}{cand.get("kronos_desc","")}")
        
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
    
    # 保存运行日志
    log_file = os.path.join(
        os.path.dirname(__file__),
        "history",
        f"run_log_{datetime.now().strftime('%Y%m%d_%H%M')}.json"
    )
    os.makedirs(os.path.dirname(log_file), exist_ok=True)
    
    with open(log_file, "w", encoding="utf-8") as f:
        json.dump({
            "timestamp": datetime.now().isoformat(),
            "portfolio": portfolio,
            "candidates": candidates[:5] if candidates else [],
            "alerts": alerts,
            "buys": buys if 'buys' in dir() else [],
            "sells": sells if 'sells' in dir() else []
        }, f, ensure_ascii=False, indent=2)
    
    print(f"\n运行日志已保存: {log_file}")
    
    return portfolio


def main():
    """主函数"""
    import argparse
    
    parser = argparse.ArgumentParser(description="虚拟盘自动交易系统 v3.0")
    parser.add_argument("--loop", action="store_true", help="循环运行模式")
    args = parser.parse_args()
    
    if args.loop:
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
            else:
                print(f"[{now.strftime('%H:%M')}] 非交易时段，等待中...")
            
            time.sleep(600)
    else:
        run_once()


if __name__ == "__main__":
    main()
