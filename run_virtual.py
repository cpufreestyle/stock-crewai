import sys
sys.stdout.reconfigure(encoding='utf-8')
sys.stderr.reconfigure(encoding='utf-8')

from dotenv import load_dotenv
load_dotenv()

import requests
import json
import re
import os
from datetime import datetime

import portfolio_tracker as pt
import risk_manager as rm

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
    """新浪实时行情"""
    sina_codes = []
    for c in codes:
        if c.startswith(("6", "9")):
            sina_codes.append("sh" + c)
        else:
            sina_codes.append("sz" + c)

    url = "https://hq.sinajs.cn/list=" + ",".join(sina_codes)
    r = requests.get(url, headers={"Referer": "https://finance.sina.com.cn"}, timeout=10)

    result = {}
    for line in r.text.strip().split("\n"):
        if '"' not in line:
            continue
        # 解析 var hq_str_sh600519="贵州茅台,...""
        eq_pos = line.find("=")
        if eq_pos < 0:
            continue
        var_part = line[:eq_pos]
        data_part = line[eq_pos + 1:].strip().strip('"')

        # 提取代码
        import re as re2
        m = re2.search(r"hq_str_(sh|sz)(\d+)", var_part)
        if not m:
            continue
        code = m.group(2)
        fields = data_part.split(",")
        if len(fields) < 32:
            continue
        result[code] = {
            "name": fields[0],
            "open": float(fields[1]),
            "last_close": float(fields[2]),
            "current": float(fields[3]),
            "high": float(fields[4]),
            "low": float(fields[5]),
            "volume": int(fields[8]),
        }
    return result


def main():
    print("")
    print("=" * 60)
    print("  虚拟盘自动交易 (" + datetime.now().strftime("%Y-%m-%d %H:%M") + ")")
    print("=" * 60)
    print("")

    # 1. 获取实时行情
    print("=== 获取实时行情 ===")
    realtime = get_sina_realtime(STOCK_POOL)
    print("获取到 " + str(len(realtime)) + " 只股票")
    print("")

    # 构建现价dict
    current_prices = {}
    for code, d in realtime.items():
        current_prices[code] = d["current"]

    # 2. 检查止损止盈（自动卖出）
    print("=== 检查止损止盈 ===")
    triggered = pt.check_stop_loss(current_prices)
    if triggered:
        print("触发 " + str(len(triggered)) + " 个信号:")
        for t in triggered:
            print("  " + t["name"] + " (" + t["code"] + "): " + t["action"] + " @ " + str(round(t["current_price"], 2)) + "元 (" + str(round(t["pnl_pct"], 2)) + "%)")

        # 自动卖出
        sold = pt.auto_sell_triggered(triggered, current_prices)
        if sold:
            print("")
            print("自动卖出 " + str(len(sold)) + " 只:")
            for s in sold:
                print("  " + s["name"] + ": " + s["action"] + " " + str(s["shares"]) + "股 @" + str(round(s["price"], 2)) + "元 (" + str(round(s["pnl_pct"], 2)) + "%)")
        else:
            print("  自动卖出失败")
    else:
        print("  无触发信号")

    # 3. 筛选候选买入
    print("")
    print("=" * 60)
    print("=== 筛选候选（今日温和上涨） ===")

    candidates = []
    for code in STOCK_POOL:
        if code not in realtime:
            continue
        rt = realtime[code]

        current = rt["current"]
        last_close = rt["last_close"]
        if last_close <= 0:
            continue
        change_pct = (current / last_close - 1) * 100

        # 今日上涨（0~8%之间）
        if change_pct <= 0 or change_pct > 8:
            continue

        # 有成交量
        if rt["volume"] <= 0:
            continue

        # 买得起100股（单只20%=2万）
        if current * 100 > 20000:
            continue

        candidates.append({
            "code": code,
            "name": rt["name"],
            "price": current,
            "change_pct": change_pct,
        })

    # 按涨幅接近3%排序
    candidates.sort(key=lambda x: abs(x["change_pct"] - 3))
    buy_list = candidates[:5]

    print("候选 " + str(len(candidates)) + " 只，选取前 " + str(len(buy_list)) + " 只:")
    for c in candidates[:10]:
        print("  " + c["code"] + " " + c["name"] + ": " + str(round(c["price"], 2)) + "元 " + str(round(c["change_pct"], 2)) + "%")

    # 4. 执行买入
    print("")
    print("=" * 60)
    print("=== 执行买入 ===")

    portfolio = pt.load_portfolio()
    total_capital = portfolio["total_capital"]
    cash = portfolio["cash"]

    market_regime = "牛市"
    max_total_pct = 0.80

    bought = []
    for stock in buy_list:
        code = stock["code"]
        name = stock["name"]
        price = stock["price"]

        if code in portfolio["positions"]:
            print("  - " + code + " " + name + ": 已持有，跳过")
            continue

        stop = round(price * 0.92, 2)
        target = round(price * 1.20, 2)

        # 仓位计算
        risk_per_share = price * 0.08
        shares_by_risk = int(2000 / risk_per_share / 100) * 100 if risk_per_share > 0 else 0
        shares_by_cap = int(20000 / price / 100) * 100 if price > 0 else 0
        shares = min(shares_by_risk, shares_by_cap)

        if shares <= 0:
            print("  - " + code + " " + name + ": 太贵买不起")
            continue

        position_value = shares * price

        if position_value > cash:
            shares = int(cash / price / 100) * 100
            if shares <= 0:
                continue
            position_value = shares * price

        # 检查总仓位
        if (total_capital - cash + position_value) / total_capital > max_total_pct:
            print("  - " + code + " " + name + ": 总仓位将超限")
            continue

        # 买入
        result = pt.update_position(
            code, name, "buy", price, shares,
            reason="自动买入 止损" + str(stop) + " 目标" + str(target),
            current_prices=current_prices
        )

        if "error" not in result:
            pt.set_stop_loss(code, stop, target)
            cash -= position_value
            bought.append(stock)

            rr = rm.risk_reward_ratio(price, target, stop)
            print("  >> 买入 " + code + " " + name + ": " + str(shares) + "股 @" + str(round(price, 2)) + "元 =" + str(int(position_value)) + "元 止损" + str(stop) + " 目标" + str(target) + " RR=" + str(round(rr["risk_reward_ratio"], 2)) + ":1")
        else:
            print("  - " + code + " " + name + ": 买入失败 " + result["error"])

        portfolio = pt.load_portfolio()

    # 5. 最终状态
    print("")
    print("=" * 60)
    print("  持仓状态 (" + datetime.now().strftime("%Y-%m-%d %H:%M") + ")")
    print("=" * 60)

    portfolio = pt.load_portfolio()
    summary = pt.get_portfolio_summary(current_prices)
    print("")
    print(summary)

    # 保存运行日志
    log = {
        "time": datetime.now().isoformat(),
        "triggered": triggered,
        "bought": [{"code": s["code"], "name": s["name"], "price": s["price"]} for s in bought],
        "portfolio": portfolio
    }
    log_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "history")
    os.makedirs(log_dir, exist_ok=True)
    log_path = os.path.join(log_dir, "run_log_" + datetime.now().strftime("%Y%m%d_%H%M") + ".json")
    with open(log_path, "w", encoding="utf-8") as f:
        json.dump(log, f, ensure_ascii=False, indent=2)

    print("")
    print("运行日志已保存: " + log_path)


if __name__ == "__main__":
    import sys
    if len(sys.argv) > 1 and sys.argv[1] == "--loop":
        # 循环模式：交易时段内每10分钟运行一次
        print("循环模式：交易时段内每10分钟运行一次")
        print("按 Ctrl+C 停止")
        try:
            while True:
                now = datetime.now()
                hour = now.hour
                minute = now.minute
                # 交易时段：9:30-11:30, 13:00-15:00
                in_morning = (hour == 9 and minute >= 30) or (hour == 10) or (hour == 11 and minute <= 30)
                in_afternoon = (hour >= 13 and hour < 15) or (hour == 15 and minute == 0)
                
                if in_morning or in_afternoon:
                    print("\n" + "="*60)
                    print("执行时间: " + now.strftime("%Y-%m-%d %H:%M"))
                    print("="*60)
                    main()
                else:
                    print("[" + now.strftime("%H:%M") + "] 非交易时段，等待...")
                
                # 等待10分钟
                import time
                time.sleep(600)
        except KeyboardInterrupt:
            print("\n用户中断，退出")
    else:
        main()
