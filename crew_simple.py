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
            {"role": "system", "content": "你是专业A股投资顾问，输出简洁明确。"},
            {"role": "user", "content": prompt}
        ],
        "temperature": 0.3,
        "max_tokens": max_tokens,
    }
    
    try:
        resp = requests.post(
            f"{config['base_url']}/chat/completions",
            headers=headers,
            json=payload,
            timeout=120
        )
        resp.raise_for_status()
        return resp.json()["choices"][0]["message"]["content"]
    except Exception as e:
        print(f"[LLM 调用失败] {e}")
        return ""


def prepare_market_data() -> str:
    """准备市场数据（精简版，供 LLM 分析）"""
    lines = ["# A股市场数据分析\n"]
    
    # 1. 市场情绪
    try:
        heat = df.get_market_heat()
        lines.append(f"## 市场情绪")
        lines.append(f"- 涨停: {heat.get('涨停家数', 'N/A')}家")
        lines.append(f"- 跌停: {heat.get('跌停家数', 'N/A')}家")
        lines.append(f"- 市场状态: {heat.get('市场状态', 'N/A')}")
    except:
        lines.append("## 市场情绪: (数据不可用)")
    
    # 2. 市场趋势
    try:
        regime = df.get_market_regime()
        if regime.get("regime") != "未知":
            lines.append(f"\n## 市场趋势: 【{regime.get('regime')}】置信度{regime.get('confidence', 0)}%")
            for sig in regime.get("signals", [])[:3]:
                lines.append(f"- {sig}")
    except:
        pass
    
    # 3. 板块轮动
    try:
        sectors = df.get_sector_performance()
        if sectors:
            lines.append(f"\n## 强势板块 TOP5")
            for s in sectors[:5]:
                lines.append(f"- {s['name']}: {s['change_pct']:+.2f}%")
    except:
        pass
    
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
        except:
            pass
    
    return "\n".join(lines)


def generate_trading_plan(market_data: str) -> str:
    """调用 LLM 生成交易计划"""
    
    prompt = f"""基于以下A股市场数据，生成今日交易计划。

{market_data}

---

请输出严格的JSON格式（只输出JSON，不要其他内容）：

```json
{{
  "市场判断": "简短判断（20字内）",
  "推荐股票": [
    {{
      "代码": "000001",
      "名称": "平安银行",
      "建议仓位": "20%",
      "理由": "简短理由（30字内）"
    }}
  ],
  "持仓操作": [
    {{
      "代码": "现有持仓代码",
      "操作": "持有/加仓/减仓/止损",
      "理由": "简短理由"
    }}
  ],
  "风险提示": "简短风险提示（50字内）"
}}
```

要求：
1. 推荐股票不超过5只
2. 总仓位不超过80%
3. 如果市场风险高，推荐空仓或轻仓
4. 输出必须是合法JSON
"""
    
    print("\n[LLM] 正在调用大模型生成交易计划...")
    result = call_llm(prompt, max_tokens=1000)
    
    if not result:
        return "LLM 调用失败，请检查配置"
    
    # 尝试提取 JSON
    try:
        # 查找 JSON 块
        import re
        json_match = re.search(r'```json\s*(\{.*?\})\s*```', result, re.DOTALL)
        if json_match:
            json_str = json_match.group(1)
        else:
            # 直接找 { 开头 } 结尾
            json_match = re.search(r'(\{.*\})', result, re.DOTALL)
            if json_match:
                json_str = json_match.group(1)
            else:
                return result  # 返回原始输出
        
        # 验证 JSON
        parsed = json.loads(json_str)
        return json.dumps(parsed, ensure_ascii=False, indent=2)
    except:
        # JSON 解析失败，返回原始输出
        return result


def format_wechat_message(trading_plan: str) -> str:
    """将交易计划格式化为微信消息（5句以内）"""
    try:
        parsed = json.loads(trading_plan)
        
        lines = [f"📊 炒股分析 {datetime.now().strftime('%m-%d %H:%M')}\n"]
        
        # 市场判断
        if "市场判断" in parsed:
            lines.append(f"市场: {parsed['市场判断']}\n")
        
        # 推荐股票
        if "推荐股票" in parsed and parsed["推荐股票"]:
            lines.append("推荐买入:")
            for stock in parsed["推荐股票"][:5]:
                lines.append(f"  {stock['代码']} {stock['名称']} | 仓位{stock['建议仓位']} | {stock.get('理由', '')}")
        
        # 持仓操作
        if "持仓操作" in parsed and parsed["持仓操作"]:
            lines.append("\n持仓操作:")
            for op in parsed["持仓操作"][:3]:
                lines.append(f"  {op['代码']}: {op['操作']} ({op.get('理由', '')})")
        
        # 风险提示
        if "风险提示" in parsed:
            lines.append(f"\n⚠️ {parsed['风险提示']}")
        
        return "\n".join(lines)
    except:
        # JSON 解析失败，返回精简的原始输出
        lines = [f"📊 炒股分析 {datetime.now().strftime('%m-%d %H:%M')}\n"]
        lines.append(trading_plan[:500])
        return "\n".join(lines)


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
    report += f"## 交易计划（LLM输出）\n\n{trading_plan}\n\n"
    
    # 风险报告
    try:
        pf = pt.load_portfolio()
        regime = df.get_market_regime()
        risk_report = rm.daily_risk_report(pf, regime.get("regime", "震荡市"))
        report += f"\n---\n{risk_report}\n"
    except:
        pass
    
    report += f"\n---\n{pt.get_portfolio_summary()}"
    
    with open("result_latest.md", "w", encoding="utf-8") as f:
        f.write(report)
    pt.save_daily_report(report)
    print("[已保存] result_latest.md + history/\n")
    
    # 5. 发送到微信
    wechat_msg = format_wechat_message(trading_plan)
    print("\n[微信消息预览]")
    print(wechat_msg)
    print()
    send_wechat(wechat_msg, target)
    
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
    print("  分析完成")
    print(f"{'='*60}\n")
    print(result)
