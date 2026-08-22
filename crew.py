"""
简化版炒股分析 - 单次 LLM 调用（无 CrewAI）
适用：本地小模型（Gemma-12B 等）或任何 OpenAI 兼容 API
"""
from dotenv import load_dotenv
load_dotenv()
import os
import sys
import json
import requests
from datetime import datetime
import data_fetcher as df
import portfolio_tracker as pt
import recommendation_tracker as rt
import risk_manager as rm
from retry_utils import api_retry


def get_llm_config():
    """获取 LLM 配置（支持多种提供商）"""
    provider = os.getenv("LLM_PROVIDER", "lms-local").strip().lower()
    
    if provider in ("mimo", "mimo-v2.5", "xiaomi"):
        return {
            "api_key": os.getenv("MIMO_API_KEY", ""),
            "base_url": os.getenv("MIMO_BASE_URL", "https://api.mimo.ai/v1"),
            "model": os.getenv("MIMO_MODEL_NAME", "free/mimo-v2.5-pro-cn"),
        }
    
    if provider == "lms-local":
        port_file = os.path.join(os.path.dirname(__file__), ".lm-studio-port.txt")
        if os.path.exists(port_file):
            port = open(port_file).read().strip()
            base_url = f"http://localhost:{port}/v1"
        else:
            base_url = os.getenv("OPENAI_BASE_URL", "http://localhost:12340/v1")
        return {
            "api_key": os.getenv("OPENAI_API_KEY", "lm-studio"),
            "base_url": base_url,
            "model": os.getenv("MODEL_NAME", "gemma-4-12B-it-Q4_K_M"),
        }
    
    # 默认：OpenAI 兼容
    return {
        "api_key": os.getenv("OPENAI_API_KEY") or os.getenv("DASHSCOPE_API_KEY") or "",
        "base_url": os.getenv("OPENAI_BASE_URL", "https://openrouter.ai/api/v1"),
        "model": os.getenv("MODEL_NAME", "deepseek/deepseek-chat-v3-0324"),
    }


@api_retry
def _post_llm(base_url: str, headers: dict, payload: dict) -> dict:
    """POST /chat/completions，网络异常时由 tenacity 自动重试（3 次指数退避）"""
    resp = requests.post(
        f"{base_url}/chat/completions",
        headers=headers,
        json=payload,
        timeout=600
    )
    resp.raise_for_status()
    return resp.json()


def call_llm(prompt: str, max_tokens: int = 800) -> str:
    """调用 LLM（OpenAI 兼容格式）"""
    config = get_llm_config()
    
    headers = {
        "Authorization": f"Bearer {config['api_key']}",
        "Content-Type": "application/json"
    }
    
    payload = {
        "model": config["model"],
        "messages": [
            {"role": "user", "content": prompt}
        ],
        "temperature": 0.1,
        "max_tokens": max_tokens,
    }
    
    try:
        data = _post_llm(config['base_url'], headers, payload)["choices"][0]["message"]
        content = data.get("content", "") or ""
        reasoning = data.get("reasoning_content", "") or ""
        full = content + reasoning
        if not full:
            print(f"[LLM 警告] 返回内容为空")
        return full
    except Exception as e:
        print(f"[LLM 调用失败] {e}")
        return ""


def prepare_market_data() -> str:
    """准备市场数据（精简版，供 LLM 分析）"""
    from concurrent.futures import ThreadPoolExecutor

    lines = ["# A股市场数据分析\n"]

    # 并行获取市场情绪/趋势/板块（三个独立 API 调用，串行约 3×耗时）
    with ThreadPoolExecutor(max_workers=3) as pool:
        heat_future = pool.submit(df.get_market_heat)
        regime_future = pool.submit(df.get_market_regime)
        sectors_future = pool.submit(df.get_sector_performance)
        heat = heat_future.result()
        regime = regime_future.result()
        sectors = sectors_future.result()

    # 1. 市场情绪
    try:
        if heat:
            lines.append(f"## 市场情绪")
            lines.append(f"- 涨停: {heat.get('涨停家数', 'N/A')}家")
            lines.append(f"- 跌停: {heat.get('跌停家数', 'N/A')}家")
            lines.append(f"- 市场状态: {heat.get('市场状态', 'N/A')}")
    except Exception:
        lines.append("## 市场情绪: (数据不可用)")

    # 2. 市场趋势
    try:
        if regime and regime.get("regime") != "未知":
            lines.append(f"\n## 市场趋势: 【{regime.get('regime')}】置信度{regime.get('confidence', 0)}%")
            for sig in regime.get("signals", [])[:3]:
                lines.append(f"- {sig}")
    except Exception as e:
        print(f"[数据] 市场趋势获取失败: {e}")

    # 3. 板块轮动
    try:
        if sectors:
            lines.append(f"\n## 强势板块 TOP5")
            for s in sectors[:5]:
                lines.append(f"- {s['name']}: {s['change_pct']:+.2f}%")
    except Exception as e:
        print(f"[数据] 板块表现获取失败: {e}")
    
    # 4. 当前持仓
    lines.append(f"\n## 当前持仓")
    lines.append(pt.get_portfolio_summary())
    
    # 5. 候选股票（精简到 10 只）
    lines.append(f"\n## 候选股票行情（抽样10只）")
    pool = df.get_index_components()["code"].tolist()[:10]
    prices_map = df.get_batch_stock_prices(pool)
    
    for code in pool:
        try:
            price_data = prices_map.get(code)
            name = code
            sector = ""
            for s in df.A_SHARE_POOL:
                if s["code"] == code:
                    name = s["name"]
                    sector = s["sector"]
                    break
            
            if price_data is not None and not price_data.empty:
                tech = df.calculate_technical(price_data)
                rsi = tech.get("RSI", 50)
                ret = tech.get("5日涨跌%", 0)
                trend = "↑" if ret > 2 else ("↓" if ret < -2 else "→")
                
                lines.append(
                    f"- {code} {name}({sector}): "
                    f"现价={tech.get('收盘价','N/A')}元 "
                    f"RSI={rsi:.0f} "
                    f"{trend}5日{ret:+.1f}%"
                )
        except Exception as e:
            print(f"[数据] 个股 {code} 数据获取失败: {e}")

    return "\n".join(lines)


def generate_trading_plan(market_data: str) -> dict:
    """调用 LLM 生成交易计划，返回结构化 dict"""
    
    prompt = f"""基于以下A股市场数据，输出今日交易计划。

数据：
{market_data}

---
现在输出最终答案（中文）：
市场判断：
推荐买入：
持仓操作：
风险提示：
"""
    
    print("\n[LLM] 正在调用大模型生成交易计划...")
    result = call_llm(prompt, max_tokens=2048)
    
    if not result:
        return {"error": "LLM 调用失败，请检查配置"}
    
    return {"raw": result}


def format_wechat_message(result: dict) -> str:
    """将 LLM 输出格式化为微信消息（提取最终答案部分）"""
    if "error" in result:
        return f"📊 炒股分析 {datetime.now().strftime('%m-%d %H:%M')}\n\n{result['error']}"
    
    raw = result.get("raw", "")
    if not raw:
        return f"📊 炒股分析 {datetime.now().strftime('%m-%d %H:%M')}\n\n结果为空"
    
    # 找"最终答案"后面的内容
    import re
    idx = raw.find("最终答案")
    if idx >= 0:
        raw = raw[idx:]
    
    # 只取中文相关的行
    useful = []
    for line in raw.split("\n"):
        s = line.strip()
        if not s:
            continue
        # 跳过纯英文行
        if re.match(r'^[a-zA-Z*\s.,:;!?()"\'\[\]{}]+$', s):
            continue
        # 跳过太短的行
        if len(s) < 4:
            continue
        useful.append(s)
    
    # 最多10行
    tail = useful[:10] if len(useful) > 10 else useful
    
    msg = f"📊 炒股分析 {datetime.now().strftime('%m-%d %H:%M')}\n"
    if tail:
        msg += "\n" + "\n".join(tail)
    return msg


def send_wechat(message: str, target: str = "315113118"):
    """发送微信消息（使用 openclaw message 工具）"""
    import shutil
    exe = shutil.which("openclaw") or shutil.which("openclaw.cmd")
    if not exe:
        print("[微信] openclaw 不在 PATH，跳过发送（cron delivery 兜底）")
        return False
    try:
        import subprocess
        result = subprocess.run(
            [exe, "message", "send",
             "--channel", "wechat-access",
             "--target", target,
             "--message", message[:2000]],
            capture_output=True, text=True, timeout=30
        )
        if result.returncode == 0:
            print(f"[微信] 发送成功")
            return True
        else:
            print(f"[微信] 发送失败: {result.stderr}")
            return False
    except Exception as e:
        print(f"[微信] 发送异常: {e}")
        return False


def run_simple_analysis(target: str = "315113118") -> str:
    """运行简化分析（单次 LLM 调用）"""
    print(f"\n{'='*60}")
    print(f"  简化版炒股分析 - {datetime.now().strftime('%Y-%m-%d %H:%M')}")
    print(f"{'='*60}\n")
    
    # 1. 准备市场数据
    print("[1/4] 准备市场数据...")
    market_data = prepare_market_data()
    print("[完成]\n")
    
    # 2. 检查止损止盈
    print("[2/4] 检查持仓止损止盈...")
    try:
        triggered = pt.check_stop_loss()
        if triggered:
            for t in triggered:
                msg = f"⚠ {t['name']}: {t['action']} @ {t['current_price']}元"
                print(msg)
    except Exception as e:
        print(f"止损检查失败: {e}")
    print("[完成]\n")
    
    # 3. 调用 LLM 生成交易计划
    print("[3/4] 调用 LLM 生成交易计划...")
    trading_plan = generate_trading_plan(market_data)
    print("[完成]\n")
    
    # 4. 保存结果
    print("[4/4] 保存结果...")
    report = f"# 简化版炒股分析报告 - {datetime.now().strftime('%Y-%m-%d %H:%M')}\n\n"
    report += f"## 市场数据\n\n{market_data}\n\n"
    llm_raw = trading_plan.get("raw", str(trading_plan))
    report += f"## 交易计划（LLM输出）\n\n{llm_raw}\n\n"
    
    # 风险报告
    try:
        pf = pt.load_portfolio()
        regime = df.get_market_regime()
        risk_report = rm.daily_risk_report(pf, regime.get("regime", "震荡市"))
        report += f"\n---\n{risk_report}\n"
    except Exception as e:
        print(f"[数据] 风险报告生成失败: {e}")
    
    report += f"\n---\n{pt.get_portfolio_summary()}"
    
    with open("result_latest.md", "w", encoding="utf-8") as f:
        f.write(report)
    pt.save_daily_report(report)
    print("[已保存] result_latest.md + history/\n")
    
    # 5. 准备微信消息（cron delivery会自动发送）
    wechat_msg = format_wechat_message(trading_plan)
    print(f"\n---[Trading Plan Start]---")
    print(wechat_msg)
    print(f"---[Trading Plan End]---")
    
    # 尝试发送（失败不阻塞，cron delivery兜底）
    try:
        send_wechat(wechat_msg, target)
    except Exception as e:
        print(f"[通知] 微信发送失败（cron delivery 兜底）: {e}")
    
    return wechat_msg


if __name__ == "__main__":
    # 设置 UTF-8 输出
    if sys.stdout.encoding != 'utf-8':
        sys.stdout.reconfigure(encoding='utf-8')
    if sys.stderr.encoding != 'utf-8':
        sys.stderr.reconfigure(encoding='utf-8')
    
    # 命令行参数：目标微信ID
    target = sys.argv[1] if len(sys.argv) > 1 else "315113118"
    
    result = run_simple_analysis(target)
    print(f"\n{'='*60}")
    print(f"  分析完成 - {datetime.now().strftime('%H:%M')}")
    print(f"{'='*60}")
