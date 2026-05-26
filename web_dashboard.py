"""Web Dashboard - 虚拟盘交易监控面板"""
from flask import Flask, render_template, jsonify, request
from flask_cors import CORS
import json
import os
from datetime import datetime, timedelta
import sys

# 添加项目根目录到路径
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from portfolio_tracker import load_portfolio, get_trade_history
from data_fetcher import get_realtime_quotes
from circuit_breaker import circuit_breaker
from backtest import BacktestEngine, load_historical_data, get_date_range, simple_strategy

app = Flask(__name__)
CORS(app)

# 数据目录
DATA_DIR = os.path.join(os.path.dirname(__file__), "history")
PORTFOLIO_FILE = os.path.join(os.path.dirname(__file__), "portfolio.json")


def get_current_prices(stock_codes):
    """获取当前价格"""
    try:
        quotes = get_realtime_quotes(stock_codes)
        return {q["code"]: q["price"] for q in quotes if "price" in q}
    except Exception as e:
        print(f"获取价格失败: {e}")
        return {}


def calculate_metrics(portfolio, current_prices):
    """计算绩效指标"""
    positions = portfolio.get("positions", {})
    total_value = portfolio.get("cash", 0)
    daily_pnl = 0
    positions_detail = []

    for code, pos in positions.items():
        current_price = current_prices.get(code, pos.get("last_price", pos["avg_cost"]))
        market_value = current_price * pos["shares"]
        pnl = (current_price - pos["avg_cost"]) * pos["shares"]
        pnl_pct = (current_price - pos["avg_cost"]) / pos["avg_cost"] * 100

        total_value += market_value
        daily_pnl += pnl

        positions_detail.append({
            "code": code,
            "name": pos["name"],
            "shares": pos["shares"],
            "avg_cost": round(pos["avg_cost"], 2),
            "current_price": round(current_price, 2),
            "market_value": round(market_value, 2),
            "pnl": round(pnl, 2),
            "pnl_pct": round(pnl_pct, 2),
            "stop_loss": pos.get("stop_loss", 0),
            "take_profit": pos.get("take_profit", 0)
        })

    return {
        "total_value": round(total_value, 2),
        "cash": round(portfolio.get("cash", 0), 2),
        "total_pnl": round(total_value - portfolio.get("total_capital", 100000), 2),
        "total_pnl_pct": round((total_value - portfolio.get("total_capital", 100000)) / portfolio.get("total_capital", 100000) * 100, 2),
        "daily_pnl": round(daily_pnl, 2),
        "positions": positions_detail
    }


@app.route("/")
def index():
    """主页"""
    return render_template("index.html")


@app.route("/api/portfolio")
def api_portfolio():
    """获取持仓数据"""
    portfolio = load_portfolio()
    stock_codes = list(portfolio.get("positions", {}).keys())

    current_prices = {}
    if stock_codes:
        current_prices = get_current_prices(stock_codes)

    metrics = calculate_metrics(portfolio, current_prices)
    return jsonify({
        "success": True,
        "data": metrics,
        "timestamp": datetime.now().isoformat()
    })


@app.route("/api/trades")
def api_trades():
    """获取交易历史"""
    month = request.args.get("month", datetime.now().strftime("%Y%m"))
    trades = get_trade_history(month)
    return jsonify({
        "success": True,
        "data": trades,
        "count": len(trades)
    })


@app.route("/api/performance")
def api_performance():
    """获取绩效数据（用于图表）"""
    # 读取历史净值数据
    history_file = os.path.join(DATA_DIR, "net_value_history.json")

    if os.path.exists(history_file):
        with open(history_file, "r", encoding="utf-8") as f:
            history = json.load(f)
    else:
        # 如果没有历史数据，返回当前数据
        portfolio = load_portfolio()
        history = [{
            "date": datetime.now().strftime("%Y-%m-%d"),
            "value": portfolio.get("total_value", 100000),
            "return_pct": portfolio.get("total_return_pct", 0)
        }]

    return jsonify({
        "success": True,
        "data": history
    })


@app.route("/api/analysis")
def api_analysis():
    """获取最新的 AI 分析报告"""
    result_file = os.path.join(os.path.dirname(__file__), "result_latest.md")

    if os.path.exists(result_file):
        with open(result_file, "r", encoding="utf-8") as f:
            content = f.read()
        return jsonify({
            "success": True,
            "data": content
        })
    else:
        return jsonify({
            "success": False,
            "message": "暂无分析报告"
        })


@app.route("/api/run_analysis", methods=["POST"])
def api_run_analysis():
    """手动触发 AI 分析"""
    import subprocess

    try:
        # 在后台运行分析
        script_path = os.path.join(os.path.dirname(__file__), "llm_analyst.py")
        subprocess.Popen([sys.executable, script_path], stdout=subprocess.PIPE, stderr=subprocess.PIPE)

        return jsonify({
            "success": True,
            "message": "分析任务已启动，请稍后刷新查看结果"
        })
    except Exception as e:
        return jsonify({
            "success": False,
            "message": str(e)
        })


@app.route("/api/market")
def api_market():
    """获取市场行情"""
    # 主要指数
    indices = ["000001", "399001", "399006"]  # 上证、深证、创业板
    try:
        quotes = get_realtime_quotes(indices)
        return jsonify({
            "success": True,
            "data": quotes
        })
    except Exception as e:
        return jsonify({
            "success": False,
            "message": str(e)
        })


@app.route("/api/health")
def api_health():
    """健康检查"""
    return jsonify({
        "status": "ok",
        "time": datetime.now().isoformat()
    })


@app.route("/api/risk-status")
def api_risk_status():
    """风控状态"""
    try:
        cb = circuit_breaker.status()
        from config import CIRCUIT_BREAKER_DAILY_LOSS_PCT, CIRCUIT_BREAKER_CONSECUTIVE_STOPS
        return jsonify({
            "success": True,
            "data": {
                "is_trading": cb["is_trading"],
                "daily_loss_pct": cb.get("daily_loss_pct", 0),
                "consecutive_stops": cb.get("consecutive_stops", 0),
                "daily_loss_limit": CIRCUIT_BREAKER_DAILY_LOSS_PCT,
                "consecutive_limit": CIRCUIT_BREAKER_CONSECUTIVE_STOPS,
                "remaining_minutes": cb.get("remaining_minutes", 0),
                "reason": cb.get("reason", ""),
            }
        })
    except Exception as e:
        return jsonify({"success": False, "error": str(e)})


@app.route("/api/backtest")
def api_backtest():
    """运行回测"""
    try:
        from datetime import datetime as dt
        end_date = dt.now().strftime("%Y%m%d")
        start_dt = dt.now() - timedelta(days=30)
        start_date = start_dt.strftime("%Y%m%d")

        dates = get_date_range(start_date, end_date)
        historical_data = load_historical_data(dates)

        engine = BacktestEngine(capital=100000)
        engine.run(historical_data, dates, strategy_fn=simple_strategy)
        report = engine.get_report()

        return jsonify({"success": True, "data": report})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)})


if __name__ == "__main__":
    # 创建模板目录
    os.makedirs("templates", exist_ok=True)
    os.makedirs("static", exist_ok=True)

    print("=" * 60)
    print("  Stock CrewAI Dashboard")
    print("  启动时间:", datetime.now().strftime("%Y-%m-%d %H:%M:%S"))
    print("  访问地址: http://localhost:5000")
    print("=" * 60)

    app.run(host="0.0.0.0", port=5000, debug=False)
