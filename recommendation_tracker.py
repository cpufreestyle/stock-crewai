"""
推荐追踪模块 - 记录每日推荐股票并追踪实际表现
"""
import json
import os
from datetime import datetime, timedelta
from typing import Dict, List, Optional
import data_fetcher as df


TRACKER_DIR = os.path.join(os.path.dirname(__file__), "recommendations")


def ensure_dirs():
    os.makedirs(TRACKER_DIR, exist_ok=True)


def save_recommendation(
    stocks: List[Dict],
    market_status: str = "",
    recommended_position: str = "",
    notes: str = ""
) -> str:
    """
    保存当日推荐股票
    
    stocks: [{"code": "000001", "name": "平安银行", "reason": "...", "entry_price": 12.5, "target": 13.5, "stop": 11.8}]
    """
    ensure_dirs()
    today = datetime.now().strftime("%Y-%m-%d")
    filepath = os.path.join(TRACKER_DIR, f"{today}.json")
    
    record = {
        "date": today,
        "datetime": datetime.now().isoformat(),
        "market_status": market_status,
        "recommended_position": recommended_position,
        "notes": notes,
        "stocks": stocks,
        "tracked": False  # 是否已追踪结果
    }
    
    with open(filepath, "w", encoding="utf-8") as f:
        json.dump(record, f, ensure_ascii=False, indent=2)
    
    return filepath


def track_performance(filepath: str, days: int = 5) -> Dict:
    """
    追踪推荐股票在N天后的表现
    """
    with open(filepath, "r", encoding="utf-8") as f:
        record = json.load(f)
    
    stocks = record.get("stocks", [])
    rec_date = datetime.fromisoformat(record["datetime"])
    track_date = rec_date + timedelta(days=days)
    
    results = []
    for stock in stocks:
        code = stock["code"]
        entry_price = stock.get("entry_price")
        
        if not entry_price:
            # 尝试从数据获取推荐时的价格
            try:
                price_df = df.get_stock_price(code)
                if not price_df.empty:
                    entry_price = price_df["收盘"].iloc[-1]
            except:
                entry_price = 0
        
        try:
            # 获取追踪日的价格
            end_str = track_date.strftime("%Y%m%d")
            start_str = (track_date - timedelta(days=5)).strftime("%Y%m%d")
            price_df = df.get_stock_price(code, start_date=start_str, end_date=end_str)
            
            if not price_df.empty:
                current_price = price_df["收盘"].iloc[-1]
                actual_return = (current_price - entry_price) / entry_price * 100 if entry_price else 0
                
                # 获取同期大盘涨跌
                index_df = df.get_stock_price("000001", start_date=start_str, end_date=end_str)  # 用平安银行代表大盘
                market_return = 0
                if not index_df.empty:
                    market_return = (index_df["收盘"].iloc[-1] - entry_price) / entry_price * 100 if entry_price else 0
                
                results.append({
                    "code": code,
                    "name": stock.get("name", code),
                    "entry_price": entry_price,
                    "current_price": round(current_price, 2),
                    "actual_return_pct": round(actual_return, 2),
                    "market_return_pct": round(market_return, 2),
                    "alpha": round(actual_return - market_return, 2),
                    "target": stock.get("target"),
                    "stop": stock.get("stop"),
                    "reason": stock.get("reason", ""),
                    "days_tracked": days
                })
        except Exception as e:
            results.append({
                "code": code,
                "name": stock.get("name", code),
                "entry_price": entry_price,
                "error": str(e)
            })
    
    # 更新记录
    record["tracked"] = True
    record["tracking_date"] = track_date.isoformat()
    record["tracking_days"] = days
    record["results"] = results
    
    with open(filepath, "w", encoding="utf-8") as f:
        json.dump(record, f, ensure_ascii=False, indent=2)
    
    return record


def get_all_recommendations() -> List[Dict]:
    """获取所有历史推荐"""
    ensure_dirs()
    files = sorted([f for f in os.listdir(TRACKER_DIR) if f.endswith(".json")])
    
    all_recs = []
    for f in files:
        try:
            with open(os.path.join(TRACKER_DIR, f), "r", encoding="utf-8") as fp:
                data = json.load(fp)
                all_recs.append(data)
        except:
            continue
    
    return all_recs


def get_performance_summary(days_list: List[int] = [5, 10, 20]) -> str:
    """获取整体表现摘要"""
    all_recs = get_all_recommendations()
    
    if not all_recs:
        return "暂无推荐记录"
    
    lines = [f"=== 推荐追踪汇总（共 {len(all_recs)} 天推荐） ===\n"]
    
    for days in days_list:
        total_return = 0
        total_alpha = 0
        count = 0
        
        for rec in all_recs:
            if rec.get("tracked") and rec.get("tracking_days") == days:
                for r in rec.get("results", []):
                    if "actual_return_pct" in r:
                        total_return += r["actual_return_pct"]
                        total_alpha += r.get("alpha", 0)
                        count += 1
        
        if count > 0:
            avg_return = total_return / count
            avg_alpha = total_alpha / count
            lines.append(f"{days}天平均收益: {avg_return:.2f}% (Alpha: {avg_alpha:.2f}%) [{count}只股票]")
        else:
            lines.append(f"{days}天: 暂无足够追踪数据")
    
    # 最新推荐
    if all_recs:
        latest = all_recs[-1]
        lines.append(f"\n最新推荐 {latest['date']}:")
        for s in latest.get("stocks", [])[:5]:
            lines.append(f"  {s.get('code','')} {s.get('name','')}: {s.get('reason','')}")
    
    return "\n".join(lines)


def parse_trading_result(result_text: str) -> List[Dict]:
    """
    从 CrewAI 输出中解析出推荐股票列表
    尝试从交易计划中提取股票代码和名称
    """
    import re
    
    stocks = []
    
    # 尝试匹配各种格式的股票代码
    # 格式1: 000001 平安银行
    # 格式2: 股票代码: 000001
    # 格式3: 代码: 000001, 名称: 平安银行
    
    lines = result_text.split("\n")
    for line in lines:
        # 匹配 6位数字 空格 汉字 的模式
        match = re.search(r'(\d{6})\s+([^\s,，。]+)', line)
        if match:
            code = match.group(1)
            name = match.group(2)
            
            # 验证是A股代码
            if code.startswith(("000", "001", "002", "300", "600", "601", "603", "605")):
                # 尝试提取目标价和止损价
                target_match = re.search(r'目标[价位]?[:：]?\s*(\d+\.?\d*)', line)
                stop_match = re.search(r'止损[价位]?[:：]?\s*(\d+\.?\d*)', line)
                
                stocks.append({
                    "code": code,
                    "name": name,
                    "target": float(target_match.group(1)) if target_match else None,
                    "stop": float(stop_match.group(1)) if stop_match else None,
                    "reason": line.strip()[:100]
                })
    
    return stocks


if __name__ == "__main__":
    print(get_performance_summary([5, 10]))
