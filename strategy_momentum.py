#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
行业轮动 + 动量策略 v3.0（快速版）
核心：基于新浪实时行情，不依赖akshare历史数据
"""
import sys
sys.stdout.reconfigure(encoding='utf-8')
sys.stderr.reconfigure(encoding='utf-8')

import json
import os
import requests
import re
import time
from datetime import datetime
from typing import Dict, List

import portfolio_tracker as pt

# 行业分类
SECTOR_MAP = {
    "银行": ["000001", "600016", "600036", "601166", "601398"],
    "白酒食品": ["000858", "600519", "000895", "603288", "600887"],
    "医药": ["600276", "603259", "002001"],
    "新能源": ["002594", "601012", "603799"],
    "科技": ["000063", "002415", "002475", "000938", "603501", "603986"],
    "基建周期": ["600019", "601186", "000425", "601088", "600028", "601857"],
    "消费": ["000333", "000651", "600104"],
    "金融保险": ["600030", "601318", "601628"],
    "化工": ["600309", "000100"],
    "电力公用": ["600900", "600050", "601006"],
    "地产": ["000002", "600048"],
    "其他": ["000876", "600009", "601888", "601118"],
}

# 所有股票代码
ALL_CODES = []
for codes in SECTOR_MAP.values():
    ALL_CODES.extend(codes)


def get_sina_realtime(codes=None):
    """获取新浪实时行情"""
    if codes is None:
        codes = ALL_CODES

    sina_codes = []
    for c in codes:
        prefix = "sh" if c.startswith(("6", "9")) else "sz"
        sina_codes.append(prefix + c)

    url = "https://hq.sinajs.cn/list=" + ",".join(sina_codes)

    for attempt in range(3):
        try:
            r = requests.get(url, headers={"Referer": "https://finance.sina.com.cn"}, timeout=20)
            break
        except Exception as e:
            if attempt < 2:
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
            result[code] = {
                "name": fields[0],
                "open": float(fields[1]) if fields[1] else 0,
                "last_close": float(fields[2]) if fields[2] else 0,
                "current": float(fields[3]) if fields[3] else 0,
                "high": float(fields[4]) if fields[4] else 0,
                "low": float(fields[5]) if fields[5] else 0,
                "volume": int(float(fields[8])) if fields[8] else 0,
                "amount": float(fields[9]) if fields[9] else 0,
                "change_pct": (float(fields[3]) / float(fields[2]) - 1) * 100 if float(fields[2]) > 0 else 0,
            }
        except:
            continue

    return result


def score_stock(code, data):
    """个股动量评分（基于实时行情，0-100分）"""
    score = 0
    signals = []

    name = data.get("name", code)
    price = data.get("current", 0)
    change_pct = data.get("change_pct", 0)
    volume = data.get("volume", 0)
    open_price = data.get("open", 0)
    high = data.get("high", 0)
    low = data.get("low", 0)
    last_close = data.get("last_close", 0)

    if price <= 0:
        return {"code": code, "name": name, "score": 0, "signals": ["无报价"]}

    # 1. 涨幅评分（25分）
    if 1 <= change_pct <= 4:
        score += 25
        signals.append(f"涨幅{change_pct:.1f}%适中 ✓")
    elif 0 < change_pct < 1:
        score += 18
        signals.append(f"涨幅{change_pct:.1f}%微涨")
    elif 4 < change_pct <= 7:
        score += 15
        signals.append(f"涨幅{change_pct:.1f}%偏强")
    elif 7 < change_pct <= 10:
        score += 5
        signals.append(f"涨幅{change_pct:.1f}%追高风险 ✗")
    elif -2 < change_pct < 0:
        score += 10
        signals.append(f"涨幅{change_pct:.1f}%微跌")
    elif -5 < change_pct <= -2:
        score += 5
        signals.append(f"涨幅{change_pct:.1f}%下跌")
    else:
        score += 2
        signals.append(f"涨幅{change_pct:.1f}% ✗")

    # 2. 成交量评分（20分）
    if volume > 1000000:
        score += 20
        signals.append("放量 ✓")
    elif volume > 300000:
        score += 15
        signals.append("量能正常")
    elif volume > 100000:
        score += 8
        signals.append("量能偏低")
    else:
        score += 3
        signals.append("缩量 ✗")

    # 3. 日内位置评分（20分）
    if high > low:
        day_pos = (price - low) / (high - low) * 100
        if 70 <= day_pos <= 90:
            score += 20
            signals.append("日内强势 ✓")
        elif 50 <= day_pos < 70:
            score += 15
            signals.append("日内在中位")
        elif day_pos >= 90:
            score += 10
            signals.append("日内极高(谨慎)")
        else:
            score += 5
            signals.append("日内偏弱")

    # 4. 开盘情况（15分）
    if open_price > 0 and last_close > 0:
        open_gap = (open_price / last_close - 1) * 100
        if 0 < open_gap <= 2:
            score += 15
            signals.append("小幅高开 ✓")
        elif -1 < open_gap <= 0:
            score += 10
            signals.append("平开或微低开")
        elif 2 < open_gap <= 5:
            score += 8
            signals.append("大幅高开(谨慎)")
        elif open_gap > 5:
            score += 3
            signals.append("跳空高开(风险大) ✗")
        elif -3 < open_gap <= -1:
            score += 5
            signals.append("低开")
        else:
            score += 3
            signals.append("大幅低开 ✗")

    # 5. 振幅评分（10分）
    if last_close > 0:
        amplitude = (high - low) / last_close * 100
        if 2 <= amplitude <= 5:
            score += 10
            signals.append("振幅适中 ✓")
        elif amplitude < 2:
            score += 5
            signals.append("振幅小")
        elif amplitude <= 8:
            score += 7
            signals.append("振幅偏大")
        else:
            score += 3
            signals.append("振幅过大 ✗")

    # 6. 金额评分（10分）
    amount = data.get("amount", 0)
    if amount > 500000000:  # 5亿
        score += 10
        signals.append("成交额大 ✓")
    elif amount > 100000000:  # 1亿
        score += 7
        signals.append("成交额正常")
    elif amount > 30000000:  # 3千万
        score += 4
        signals.append("成交额偏小")
    else:
        score += 2
        signals.append("成交额小 ✗")

    # 评级
    if score >= 75:
        rating = "强烈推荐"
    elif score >= 60:
        rating = "推荐"
    elif score >= 45:
        rating = "观望"
    elif score >= 30:
        rating = "偏弱"
    else:
        rating = "回避"

    return {
        "code": code,
        "name": name,
        "score": score,
        "rating": rating,
        "signals": signals,
        "price": price,
        "change_pct": change_pct,
        "volume": volume
    }


def sector_rotation(realtime_data):
    """行业轮动排名"""
    sector_scores = []

    for sector, codes in SECTOR_MAP.items():
        total_score = 0
        count = 0
        stocks = []

        for code in codes:
            if code in realtime_data:
                result = score_stock(code, realtime_data[code])
                total_score += result["score"]
                count += 1
                stocks.append(result)

        if count > 0:
            avg_score = total_score / count
            top_stock = max(stocks, key=lambda x: x["score"]) if stocks else None
            sector_scores.append({
                "sector": sector,
                "avg_score": round(avg_score, 1),
                "count": count,
                "top_stock": top_stock,
                "stocks": stocks
            })

    sector_scores.sort(key=lambda x: -x["avg_score"])
    return sector_scores


def generate_trade_plan(realtime_data=None, portfolio_positions=None, cash=100000, total_capital=100000):
    """
    生成交易计划
    返回：{"buy": [...], "sell": [...], "hold": [...], "sectors": [...]}
    """
    if realtime_data is None:
        realtime_data = get_sina_realtime()

    if portfolio_positions is None:
        portfolio = pt.load_portfolio()
        portfolio_positions = portfolio.get("positions", {})
        cash = portfolio.get("cash", 100000)
        total_capital = portfolio.get("total_capital", 100000)

    # 1. 行业排名
    sectors = sector_rotation(realtime_data)

    # 2. 对所有股票评分
    all_scores = []
    for code, data in realtime_data.items():
        result = score_stock(code, data)
        # 找到所属行业
        for sector, codes in SECTOR_MAP.items():
            if code in codes:
                result["sector"] = sector
                break
        all_scores.append(result)

    all_scores.sort(key=lambda x: -x["score"])

    # 3. 生成计划
    plan = {"buy": [], "sell": [], "hold": [], "sectors": sectors}

    # 持仓评估
    for code, pos in portfolio_positions.items():
        if code in realtime_data:
            result = score_stock(code, realtime_data[code])
        else:
            result = {"code": code, "name": pos["name"], "score": 50}

        if result["score"] < 25:
            plan["sell"].append({
                "code": code,
                "name": pos["name"],
                "score": result["score"],
                "reason": f"动量评分过低({result['score']}分)"
            })
        elif result["score"] < 45:
            plan["hold"].append({
                "code": code,
                "name": pos["name"],
                "score": result["score"],
                "reason": f"动量一般({result['score']}分)，观察"
            })
        else:
            plan["hold"].append({
                "code": code,
                "name": pos["name"],
                "score": result["score"],
                "reason": f"动量良好({result['score']}分)"
            })

    # 新买入
    held_codes = set(portfolio_positions.keys())
    max_positions = 5
    current_count = len(portfolio_positions) - len(plan["sell"])

    for rec in all_scores:
        if rec["code"] in held_codes:
            continue
        if current_count + len(plan["buy"]) >= max_positions:
            break
        if rec["score"] < 50:
            continue
        if rec["price"] > 200 or rec["price"] <= 0:
            continue

        shares = int(total_capital * 0.20 / rec["price"] / 100) * 100
        if shares <= 0:
            continue

        position_value = shares * rec["price"]
        if position_value > cash:
            continue

        plan["buy"].append({
            "code": rec["code"],
            "name": rec["name"],
            "price": rec["price"],
            "shares": shares,
            "position_value": position_value,
            "score": rec["score"],
            "rating": rec["rating"],
            "sector": rec.get("sector", ""),
            "reason": f"动量{rec['score']}分 行业:{rec.get('sector', '')} {rec['rating']}"
        })

    return plan


if __name__ == "__main__":
    print("=" * 60)
    print("  行业轮动 + 动量策略 v3.0（快速版）")
    print("=" * 60 + "\n")

    # 获取实时行情
    print("获取实时行情...")
    realtime_data = get_sina_realtime()
    print(f"获取到 {len(realtime_data)} 只股票\n")

    # 行业排名
    print("=== 行业动量排名 ===\n")
    sectors = sector_rotation(realtime_data)

    for i, s in enumerate(sectors, 1):
        top = s["top_stock"]
        top_name = top["name"] if top else "N/A"
        top_score = top["score"] if top else 0
        print(f"  {i}. {s['sector']}: 均分{s['avg_score']} | 领涨: {top_name}({top_score}分)")

    # 生成交易计划
    print("\n=== 交易计划 ===\n")
    plan = generate_trade_plan(realtime_data)

    if plan["sell"]:
        print("🔴 建议卖出：")
        for s in plan["sell"]:
            print(f"  - {s['name']}({s['code']}): {s['reason']}")

    if plan["buy"]:
        print("\n🟢 建议买入：")
        for b in plan["buy"]:
            print(f"  - {b['name']}({b['code']}): {b['shares']}股 @ {b['price']:.2f}元 ({b['reason']})")

    if plan["hold"]:
        print("\n🟡 继续持有：")
        for h in plan["hold"]:
            print(f"  - {h['name']}({h['code']}): {h['reason']}")

    # 保存结果
    output_file = os.path.join(
        os.path.dirname(__file__),
        "history",
        f"strategy_{datetime.now().strftime('%Y%m%d_%H%M')}.json"
    )
    os.makedirs(os.path.dirname(output_file), exist_ok=True)

    # 序列化时去掉不可序列化的字段
    save_data = {
        "timestamp": datetime.now().isoformat(),
        "sectors": [{
            "sector": s["sector"],
            "avg_score": s["avg_score"],
            "top_stock_name": s["top_stock"]["name"] if s["top_stock"] else None,
            "top_stock_score": s["top_stock"]["score"] if s["top_stock"] else None,
        } for s in sectors],
        "plan": {
            "buy": plan["buy"],
            "sell": plan["sell"],
            "hold": plan["hold"]
        }
    }

    with open(output_file, "w", encoding="utf-8") as f:
        json.dump(save_data, f, ensure_ascii=False, indent=2)

    print(f"\n结果已保存: {output_file}")
    print("\n测试完成！")
