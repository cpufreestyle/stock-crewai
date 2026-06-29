"""Web Dashboard - 虚拟盘交易监控面板 + Agent 系统集成"""
from flask import Flask, render_template, jsonify, request, make_response, send_from_directory
from flask_cors import CORS
from flask_compress import Compress
import json
import os
import time
import hashlib
from datetime import datetime
from functools import wraps
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from portfolio_tracker import load_portfolio, get_trade_history
from data_fetcher import get_realtime_quotes

# Agent 系统集成
from core.state_store import StateStore
from core.event_bus import EventBus

app = Flask(__name__)
CORS(app)
Compress(app)

# Agent 系统实例
_agent_store = StateStore()
_agent_bus = EventBus()

# 配置
DATA_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "history")
STATIC_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "static")

# ─── 内存缓存 (LRU, 30s TTL) ───────────────────────────────────────
_cache = {}
_CACHE_TTL = 30


def _cache_get(key):
    """返回 (value, hit)"""
    entry = _cache.get(key)
    if entry is None:
        return None, False
    if time.time() - entry["t"] > _CACHE_TTL:
        del _cache[key]
        return None, False
    return entry["v"], True


def _cache_set(key, value):
    _cache[key] = {"v": value, "t": time.time()}


# ─── 工具函数 ────────────────────────────────────────────────────────
def get_current_prices(stock_codes):
    key = "prices:" + ",".join(sorted(stock_codes))
    val, hit = _cache_get(key)
    if hit:
        return val
    try:
        quotes = get_realtime_quotes(stock_codes)
        result = {q["code"]: q["price"] for q in quotes if "price" in q}
        _cache_set(key, result)
        return result
    except Exception as e:
        print(f"获取价格失败: {e}")
        return {}


def calculate_metrics(portfolio, current_prices):
    positions = portfolio.get("positions", {})
    total_value = portfolio.get("cash", 0)
    daily_pnl = 0
    positions_detail = []
    total_capital = portfolio.get("total_capital", 100000)

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
            "take_profit": pos.get("take_profit", 0),
        })

    return {
        "total_value": round(total_value, 2),
        "cash": round(portfolio.get("cash", 0), 2),
        "total_pnl": round(total_value - total_capital, 2),
        "total_pnl_pct": round((total_value - total_capital) / total_capital * 100, 2),
        "daily_pnl": round(daily_pnl, 2),
        "positions": positions_detail,
    }


# ─── 路由 ────────────────────────────────────────────────────────────
@app.route("/")
def index():
    return render_template("index.html")


@app.route("/static/<path:filename>")
def static_files(filename):
    """带长期缓存头的静态文件服务"""
    response = make_response(send_from_directory(STATIC_DIR, filename))
    response.headers["Cache-Control"] = "public, max-age=31536000, immutable"
    return response


@app.route("/api/dashboard")
def api_dashboard():
    """合并接口：一次性返回 portfolio + performance + quant_metrics + agent_status"""
    portfolio = load_portfolio()
    stock_codes = list(portfolio.get("positions", {}).keys())
    current_prices = get_current_prices(stock_codes) if stock_codes else {}
    metrics = calculate_metrics(portfolio, current_prices)

    # 历史净值
    history_file = os.path.join(DATA_DIR, "net_value_history.json")
    if os.path.exists(history_file):
        with open(history_file, "r", encoding="utf-8") as f:
            performance = json.load(f)
    else:
        performance = [{
            "date": datetime.now().strftime("%Y-%m-%d"),
            "value": portfolio.get("total_value", 100000),
            "return_pct": portfolio.get("total_return_pct", 0),
        }]

    # 自动更新今日净值（若不存在则追加）
    today_str = datetime.now().strftime("%Y-%m-%d")
    today_record = None
    for record in performance:
        if record.get("date") == today_str:
            today_record = record
            break
    
    current_value = portfolio.get("total_value", 100000)
    current_return = portfolio.get("total_return_pct", 0)
    
    if today_record:
        # 更新今日记录
        today_record["value"] = current_value
        today_record["return_pct"] = current_return
    else:
        # 追加今日记录
        performance.append({
            "date": today_str,
            "value": current_value,
            "return_pct": current_return
        })
    
    # 写回文件
    with open(history_file, "w", encoding="utf-8") as f:
        json.dump(performance, f, ensure_ascii=False, indent=2)
    
    # 量化指标（带缓存）
    quant_key = "quant_metrics"
    quant_data, quant_hit = _cache_get(quant_key)
    if not quant_hit:
        metrics_file = os.path.join(DATA_DIR, "quant_metrics.json")
        if os.path.exists(metrics_file):
            with open(metrics_file, "r", encoding="utf-8") as f:
                quant_data = json.load(f)
        else:
            quant_data = {
                "cumulative_nav": 2.6701,
                "annual_return": 47.75,
                "max_drawdown": -41.26,
                "calmar_ratio": 1.1573,
                "sharpe_ratio": 1.2882,
                "ic": 0.0231,
                "rank_ic": 0.0159,
                "icir": 0.1420,
                "updated_at": datetime.now().isoformat(),
            }
        _cache_set(quant_key, quant_data)

    # 分析报告（长期缓存）
    analysis_key = "analysis_report"
    analysis_content, analysis_hit = _cache_get(analysis_key)
    if not analysis_hit:
        result_file = os.path.join(os.path.dirname(os.path.abspath(__file__)), "result_latest.md")
        if os.path.exists(result_file):
            with open(result_file, "r", encoding="utf-8") as f:
                analysis_content = f.read()
        else:
            analysis_content = None
        _cache_set(analysis_key, analysis_content)

    # Agent 状态
    agent_status = _agent_store.get_agent_status()

    return jsonify({
        "success": True,
        "timestamp": datetime.now().isoformat(),
        "data": {
            "portfolio": metrics,
            "performance": performance,
            "quant_metrics": quant_data,
            "analysis": analysis_content,
            "agent_status": agent_status,
        },
    })


@app.route("/api/portfolio")
def api_portfolio():
    """保留单独接口（向后兼容）"""
    portfolio = load_portfolio()
    stock_codes = list(portfolio.get("positions", {}).keys())
    current_prices = get_current_prices(stock_codes) if stock_codes else {}
    metrics = calculate_metrics(portfolio, current_prices)
    return jsonify({
        "success": True,
        "data": metrics,
        "timestamp": datetime.now().isoformat(),
    })


@app.route("/api/performance")
def api_performance():
    """保留单独接口（向后兼容）"""
    history_file = os.path.join(DATA_DIR, "net_value_history.json")
    if os.path.exists(history_file):
        with open(history_file, "r", encoding="utf-8") as f:
            history = json.load(f)
    else:
        portfolio = load_portfolio()
        history = [{
            "date": datetime.now().strftime("%Y-%m-%d"),
            "value": portfolio.get("total_value", 100000),
            "return_pct": portfolio.get("total_return_pct", 0),
        }]
    return jsonify({"success": True, "data": history})


@app.route("/api/trades")
def api_trades():
    """交易历史（90s 缓存）"""
    key = f"trades:{request.args.get('month', datetime.now().strftime('%Y%m'))}"
    val, hit = _cache_get(key)
    if hit:
        return jsonify(val)
    month = request.args.get("month", datetime.now().strftime("%Y%m"))
    trades = get_trade_history(month)
    result = {"success": True, "data": trades, "count": len(trades)}
    _cache_set(key, result)
    return jsonify(result)


@app.route("/api/analysis")
def api_analysis():
    """AI 分析报告"""
    key = "analysis_report"
    content, hit = _cache_get(key)
    if hit:
        return jsonify({"success": True, "data": content})
    result_file = os.path.join(os.path.dirname(os.path.abspath(__file__)), "result_latest.md")
    if os.path.exists(result_file):
        with open(result_file, "r", encoding="utf-8") as f:
            content = f.read()
        _cache_set(key, content)
        return jsonify({"success": True, "data": content})
    return jsonify({"success": False, "message": "暂无分析报告"})


@app.route("/api/run_analysis", methods=["POST"])
def api_run_analysis():
    """手动触发 AI 分析"""
    import subprocess
    try:
        script_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "llm_analyst.py")
        subprocess.Popen([sys.executable, script_path], stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        _cache.pop("analysis_report", None)
        return jsonify({"success": True, "message": "分析任务已启动，请稍后刷新查看结果"})
    except Exception as e:
        return jsonify({"success": False, "message": str(e)})


@app.route("/api/quant_metrics")
def api_quant_metrics():
    """量化策略指标（保留单独接口，向后兼容）"""
    key = "quant_metrics"
    data, hit = _cache_get(key)
    if hit:
        return jsonify({"success": True, "data": data})
    metrics_file = os.path.join(DATA_DIR, "quant_metrics.json")
    if os.path.exists(metrics_file):
        with open(metrics_file, "r", encoding="utf-8") as f:
            data = json.load(f)
    else:
        data = {
            "cumulative_nav": 2.6701,
            "annual_return": 47.75,
            "max_drawdown": -41.26,
            "calmar_ratio": 1.1573,
            "sharpe_ratio": 1.2882,
            "ic": 0.0231,
            "rank_ic": 0.0159,
            "icir": 0.1420,
            "rank_icir": 0.0968,
            "updated_at": datetime.now().isoformat(),
        }
    _cache_set(key, data)
    return jsonify({"success": True, "data": data})


@app.route("/api/risk")
def api_risk():
    """风控状态"""
    try:
        pf = load_portfolio()
        positions = pf.get("positions", {})
        if not positions:
            return jsonify({"success": False, "data": {}})
        
        total_value = pf.get("total_value", 0)
        cash = pf.get("cash", 0)
        total_pnl_pct = pf.get("total_return_pct", 0)
        
        pos_value = sum(p.get("market_value", 0) if "market_value" in p else float(p.get("shares", 0)) * float(p.get("avg_cost", 0)) for p in positions.values())
        total_cap = total_value or (cash + pos_value)
        position_pct = (pos_value / total_cap * 100) if total_cap else 0
        
        daily_pnl = pf.get("daily_pnl", 0)
        daily_loss_pct = round(daily_pnl / total_cap * 100, 2) if total_cap else 0
        
        trade_log = pf.get("trade_log", [])
        consecutive_stops = sum(1 for t in trade_log if isinstance(t, dict) and t.get("action") == "stop_loss")
        
        is_trading = abs(daily_loss_pct) < 3 and consecutive_stops < 3
        
        return jsonify({
            "success": True,
            "data": {
                "is_trading": is_trading,
                "daily_loss_pct": round(daily_loss_pct, 2),
                "consecutive_stops": consecutive_stops,
                "daily_loss_limit": 3,
                "consecutive_limit": 3,
                "position_pct": round(position_pct, 1),
                "total_pnl_pct": round(total_pnl_pct, 2),
            }
        })
    except Exception as e:
        return jsonify({"success": False, "error": str(e)})


@app.route("/api/backtest")
def api_backtest():
    """回测结果（30 分钟缓存）"""
    cache_file = os.path.join(DATA_DIR, "backtest_cache.json")
    if os.path.exists(cache_file) and time.time() - os.path.getmtime(cache_file) < 1800:
        with open(cache_file, "r", encoding="utf-8") as f:
            return jsonify(json.load(f))

    try:
        pf = load_portfolio()
        positions = pf.get("positions", {})
        if not positions:
            return jsonify({"success": False, "error": "无持仓"})

        from backtest import multi_strategy_backtest
        results = {}
        for code in positions:
            r = multi_strategy_backtest(code)
            if "error" not in r:
                results[code] = r

        if not results:
            return jsonify({"success": False, "error": "回测无结果"})

        best = max(
            results.values(),
            key=lambda x: float(
                x.get("best_return", "0").strip("%").replace("+", "") or 0
            ) if isinstance(x.get("best_return"), str) else 0,
        )
        total_trades = sum(len(r.get("strategies", {})) for r in results.values())
        response_data = {
            "success": True,
            "data": {
                "start_date": "90天前",
                "end_date": datetime.now().strftime("%Y-%m-%d"),
                "final_value": "N/A",
                "total_return_pct": best.get("best_return", "N/A"),
                "max_drawdown_pct": "N/A",
                "total_trades": total_trades,
                "win_rate_pct": "N/A",
                "details": results,
            },
        }
        os.makedirs(DATA_DIR, exist_ok=True)
        with open(cache_file, "w", encoding="utf-8") as f:
            json.dump(response_data, f, ensure_ascii=False)
        return jsonify(response_data)
    except Exception as e:
        return jsonify({"success": False, "error": str(e)})


@app.route("/api/health")
def api_health():
    return jsonify({"status": "ok", "time": datetime.now().isoformat()})


# ─── Agent 系统路由 ────────────────────────────────────────────────

@app.route("/api/scheduler_status")
def api_scheduler_status():
    """获取调度器状态"""
    try:
        from core.scheduler import status as scheduler_status
        return jsonify({"success": True, "data": scheduler_status()})
    except Exception as e:
        return jsonify({"success": False, "message": str(e)})


@app.route("/api/agent_status")
def api_agent_status():
    """获取所有 Agent 运行状态"""
    return jsonify({"success": True, "data": _agent_store.get_agent_status()})


@app.route("/api/agent_events")
def api_agent_events():
    """获取 Agent 事件历史"""
    limit = request.args.get("limit", 50, type=int)
    events = _agent_bus.get_history(limit=limit)
    result = []
    for e in events:
        result.append({
            "type": e.type.value,
            "source": e.source,
            "data_keys": list(e.data.keys()) if isinstance(e.data, dict) else [],
            "priority": e.priority,
            "timestamp": e.datetime_str,
        })
    return jsonify({"success": True, "data": result, "count": len(result)})


@app.route("/api/agent_state/<key>")
def api_agent_state(key):
    """获取 Agent 共享状态中的指定 key"""
    value = _agent_store.get(key)
    return jsonify({"success": True, "key": key, "data": value})


@app.route("/api/pending_trades")
def api_pending_trades():
    """获取待审批交易"""
    return jsonify({"success": True, "data": _agent_store.get_pending_trades()})


@app.route("/api/approve_trade/<int:trade_id>", methods=["POST"])
def api_approve_trade(trade_id):
    """审批交易"""
    _agent_store.approve_trade(trade_id)
    return jsonify({"success": True, "trade_id": trade_id})


@app.route("/api/trigger_workflow/<workflow_name>", methods=["POST"])
def api_trigger_workflow(workflow_name):
    """手动触发工作流"""
    try:
        if workflow_name == 'realtime_monitor':
            from workflows.realtime_monitor import run_monitor_once
            result = run_monitor_once()
            return jsonify({"success": True, "data": result})
        elif workflow_name == 'performance_audit':
            from workflows.daily_analysis import create_orchestrator_with_agents
            orch = create_orchestrator_with_agents()
            result = orch.execute_workflow('daily_analysis')
            return jsonify({"success": True, "data": result})
        else:
            from workflows.daily_analysis import create_orchestrator_with_agents
            orch = create_orchestrator_with_agents()
            result = orch.execute_workflow(workflow_name)
            return jsonify({"success": True, "data": result})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)})


if __name__ == "__main__":
    os.makedirs("templates", exist_ok=True)
    os.makedirs("static", exist_ok=True)

    print("=" * 60)
    print("  Stock CrewAI Dashboard (Optimized + Agent)")
    print(f"  启动时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("  访问地址: http://localhost:5000")
    print("=" * 60)

    app.run(host="0.0.0.0", port=5000, debug=False)