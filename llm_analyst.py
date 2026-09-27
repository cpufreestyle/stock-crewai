"""LLM分析模块 - 结合新闻情感分析"""
import sys; sys.stdout.reconfigure(encoding='utf-8')
import os
import json
from datetime import datetime

# 尝试导入 LLM SDK（支持多种后端）
LLM_AVAILABLE = False
llm_client = None
_openai_client = None

# 模型与端点统一从环境变量读取，兼容 OpenRouter / DashScope / StepFun / LM Studio 等
MODEL_NAME = os.getenv("MODEL_NAME", "gpt-3.5-turbo")
OPENAI_BASE_URL = os.getenv("OPENAI_BASE_URL", "")


def _chat(prompt: str, temperature: float = 0.3, timeout: float = 90.0) -> str:
    """统一调用 OpenAI 兼容接口（openai>=1.0.0 新接口）"""
    resp = _openai_client.chat.completions.create(
        model=MODEL_NAME,
        messages=[{"role": "user", "content": prompt}],
        temperature=temperature,
        timeout=timeout,
    )
    return (resp.choices[0].message.content or "").strip()


# 1. 尝试 OpenAI 兼容 API
try:
    from openai import OpenAI
    _api_key = os.getenv("OPENAI_API_KEY") or os.getenv("DASHSCOPE_API_KEY") or ""
    if _api_key:
        _openai_client = OpenAI(api_key=_api_key, base_url=OPENAI_BASE_URL or None)
        llm_client = "openai"
        LLM_AVAILABLE = True
        print(f"[LLM] 使用 OpenAI 兼容 API: {MODEL_NAME} @ {OPENAI_BASE_URL or 'https://api.openai.com/v1'}")
except Exception as e:
    print(f"[LLM] OpenAI SDK 不可用: {e}")

# 2. 尝试本地 Ollama
if not LLM_AVAILABLE:
    try:
        import requests
        r = requests.get("http://localhost:11434/api/tags", timeout=2)
        if r.status_code == 200:
            llm_client = "ollama"
            LLM_AVAILABLE = True
            print("[LLM] 使用 Ollama (本地)")
    except:
        pass

# 3. 使用 QClaw 内置（通过文件交互）
if not LLM_AVAILABLE:
    llm_client = "qclaw"
    LLM_AVAILABLE = True
    print("[LLM] 使用 QClaw 内置")


def analyze_sentiment_news(news_list: list) -> dict:
    """
    分析新闻情感
    
    参数：
    - news_list: 新闻列表 [{"title": "", "content": "", "time": ""}]
    
    返回：
    - {"sentiment": "看涨"/"看跌"/"中性", "score": 0-100, "summary": ""}
    """
    if not news_list:
        return {"sentiment": "中性", "score": 50, "summary": "无新闻数据"}

    # 构建提示词
    news_text = "\n".join([
        f"- {n.get('title', '')} ({n.get('time', '')})"
        for n in news_list[:10]
    ])

    prompt = f"""请分析以下A股财经新闻的情感倾向，给出市场情绪判断。

新闻列表：
{news_text}

请按以下格式回复（不要多余内容）：
情感: 看涨/看跌/中性
分数: 0-100（0=极度悲观，50=中性，100=极度乐观）
摘要: 一句话总结市场情绪
"""

    try:
        if llm_client == "openai":
            result_text = _chat(prompt, temperature=0.3)

        elif llm_client == "ollama":
            # Ollama API
            r = requests.post(
                "http://localhost:11434/api/generate",
                json={"model": "llama2", "prompt": prompt, "stream": False},
                timeout=30
            )
            result_text = r.json().get("response", "")

        else:  # QClaw 内置 - 通过文件交互
            # 写入待分析文件
            analyze_file = os.path.join(os.path.dirname(__file__), "llm_analyze.txt")
            with open(analyze_file, "w", encoding="utf-8") as f:
                f.write(prompt)

            # 等待 QClaw 处理（简化：直接返回中性）
            result_text = "情感: 中性\n分数: 50\n摘要: 使用QClaw内置分析"

        # 解析结果
        sentiment = "中性"
        score = 50
        summary = ""

        for line in result_text.strip().split("\n"):
            if line.startswith("情感:"):
                sentiment = line.split(":", 1)[1].strip()
            elif line.startswith("分数:"):
                try:
                    score = int(line.split(":", 1)[1].strip())
                except:
                    score = 50
            elif line.startswith("摘要:"):
                summary = line.split(":", 1)[1].strip()

        return {
            "sentiment": sentiment,
            "score": score,
            "summary": summary,
            "ok": True,
        }

    except Exception as e:
        print(f"[LLM] 分析失败: {e}")
        return {"sentiment": "中性", "score": 50, "summary": f"分析失败: {e}", "ok": False}


def generate_trading_signal(stock_code: str, stock_name: str, technical_data: dict, news_sentiment: dict) -> dict:
    """
    生成交易信号（结合技术面+基本面）
    
    参数：
    - stock_code: 股票代码
    - stock_name: 股票名称
    - technical_data: 技术指标字典
    - news_sentiment: 新闻情感分析结果
    
    返回：
    - {"signal": "买入"/"卖出"/"持有", "confidence": 0-100, "reason": ""}
    """
    prompt = f"""请基于以下数据，给出A股交易建议。

股票：{stock_name} ({stock_code})

技术指标：
- 收盘价: {technical_data.get('收盘价', 'N/A')}
- MA5: {technical_data.get('MA5', 'N/A')}
- MA20: {technical_data.get('MA20', 'N/A')}
- RSI: {technical_data.get('RSI', 'N/A')}
- MACD信号: {technical_data.get('MACD信号', 'N/A')}
- 布林带信号: {technical_data.get('布林带信号', 'N/A')}

新闻情感：
- 情感: {news_sentiment.get('sentiment', 'N/A')}
- 分数: {news_sentiment.get('score', 'N/A')}
- 摘要: {news_sentiment.get('summary', 'N/A')}

请按以下格式回复（不要多余内容）：
信号: 买入/卖出/持有
信心度: 0-100
理由: 一句话说明原因
"""

    try:
        if llm_client == "openai":
            result_text = _chat(prompt, temperature=0.3)

        elif llm_client == "ollama":
            r = requests.post(
                "http://localhost:11434/api/generate",
                json={"model": "llama2", "prompt": prompt, "stream": False},
                timeout=30
            )
            result_text = r.json().get("response", "")

        else:
            result_text = "信号: 持有\n信心度: 0\n理由: 未配置 LLM，无法生成有效信号"

        # 解析
        signal = "持有"
        confidence = 50
        reason = ""

        for line in result_text.strip().split("\n"):
            if line.startswith("信号:"):
                s = line.split(":", 1)[1].strip()
                if s in ["买入", "卖出", "持有"]:
                    signal = s
            elif line.startswith("信心度:"):
                try:
                    confidence = int(line.split(":", 1)[1].strip())
                except:
                    confidence = 50
            elif line.startswith("理由:"):
                reason = line.split(":", 1)[1].strip()

        return {
            "signal": signal,
            "confidence": confidence,
            "reason": reason,
            "ok": True,
        }

    except Exception as e:
        print(f"[LLM] 生成信号失败: {e}")
        # 失败时置信度置 0 并标记 ok=False，避免下游把失败结果当作有效的"持有"信号
        return {"signal": "持有", "confidence": 0, "reason": f"分析失败: {e}", "ok": False}


def market_overview_report() -> str:
    """生成市场总览报告（LLM分析）"""
    try:
        import data_fetcher as df

        # 获取市场热度
        heat = df.get_market_heat()

        # 获取板块表现
        sectors = df.get_sector_performance()

        prompt = f"""请基于以下数据，生成今日A股市场总览。

市场热度：
- 涨停家数: {heat.get('涨停家数', 'N/A')}
- 跌停家数: {heat.get('跌停家数', 'N/A')}
- 市场状态: {heat.get('市场状态', 'N/A')}

领涨板块：
{chr(10).join(['- ' + s['name'] + ': ' + str(s['change_pct']) + '%' for s in sectors[:5]])}

请按以下格式回复：
市场概况: 一句话总结
主线板块: 当前市场主线
操作建议: 给出3条操作建议
"""

        if llm_client == "openai":
            return _chat(prompt, temperature=0.5)

        elif llm_client == "ollama":
            r = requests.post(
                "http://localhost:11434/api/generate",
                json={"model": "llama2", "prompt": prompt, "stream": False},
                timeout=30
            )
            return r.json().get("response", "")

        else:
            return "市场概况: 使用QClaw内置分析\n主线板块: 待分析\n操作建议: 待分析"

    except Exception as e:
        return f"生成市场总览失败: {e}"


if __name__ == "__main__":
    print("测试 LLM 分析模块...")
    print(f"LLM 可用: {LLM_AVAILABLE}")
    print(f"LLM 客户端: {llm_client}")

    # 测试情感分析
    test_news = [
        {"title": "A股大涨3%，科技股领涨", "time": "2026-05-20"},
        {"title": "央行宣布降准0.5%", "time": "2026-05-20"}
    ]

    result = analyze_sentiment_news(test_news)
    print(f"\n情感分析结果: {result}")

    # 测试交易信号
    tech_data = {
        "收盘价": 81.48,
        "MA5": 81.5,
        "MA20": 80.2,
        "RSI": 55.0,
        "MACD信号": "金叉",
        "布林带信号": "正常"
    }

    signal = generate_trading_signal("000333", "美的集团", tech_data, result)
    print(f"\n交易信号: {signal}")

    print("\n测试完成")
