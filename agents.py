"""
CrewAI Agents - 多智能体炒股系统
"""
from crewai import Agent
from langchain_openai import ChatOpenAI
import os

# 默认用 Qwen（便宜+中文好）作为 LLM
def get_llm():
    api_key = os.getenv("OPENAI_API_KEY") or os.getenv("DASHSCOPE_API_KEY") or ""
    base_url = os.getenv("OPENAI_BASE_URL", "https://openrouter.ai/api/v1")
    model = os.getenv("MODEL_NAME", "deepseek/deepseek-chat-v3-0324")
    
    if not api_key or api_key == "sk-your-key-here":
        print("[Agent] 警告: 未设置有效 API Key")
        return None
    
    # LM Studio（本地）不需要 openai/ 前缀
    if "host.docker.internal" in base_url or "localhost" in base_url or "127.0.0.1" in base_url:
        model_str = model  # 直接用模型名，无前缀
        print(f"[Agent] 使用本地 LLM: {model}")
    else:
        model_str = f"openai/{model}"  # OpenRouter/云端 API 需要前缀
    
    # CrewAI v1.14+ 需要 LLM 对象而非 ChatOpenAI
    from crewai import LLM
    return LLM(
        model=model_str,
        api_key=api_key,
        base_url=base_url,
        temperature=0.3,
        max_tokens=2048  # 优化：从 4096 减少到 2048，加快响应
    )


class StockResearchAgent:
    """研究员 Agent - 负责选股研究"""
    
    role = "A股研究员"
    goal = "从沪深300成分股中，通过多因子筛选找出3-5只最有投资价值的股票，给出详细分析报告"
    backstory = """你是资深A股研究员，擅长基本面+技术面结合选股。
    你关注：估值（PE/PB）、成长性（净利润增速）、趋势（均线多头排列）、市场情绪。
    你使用数据驱动的方法，从多个维度评估股票。"""
    
    def __init__(self):
        self.llm = get_llm()
    
    def create(self):
        return Agent(
            role=self.role,
            goal=self.goal,
            backstory=self.backstory,
            llm=self.llm,
            verbose=True,
            allow_delegation=False
        )


class RiskAgent:
    """风控 Agent - 负责风险评估和仓位管理"""
    
    role = "风控专家"
    goal = "对研究员的选股进行独立风险评估，确定每只股票的仓位、止损价、最大回撤容忍度"
    backstory = """你是资深风控专家，曾在公募基金负责风险管理工作。
    你擅长：VaR分析、仓位管理、止损策略、相关性风险控制。
    你的原则是：保住本金 > 追求收益。"""
    
    def __init__(self):
        self.llm = get_llm()
    
    def create(self):
        return Agent(
            role=self.role,
            goal=self.goal,
            backstory=self.backstory,
            llm=self.llm,
            verbose=True,
            allow_delegation=False
        )


class TradingAgent:
    """交易 Agent - 负责最终交易决策和执行"""
    
    role = "交易员"
    goal = "综合研究员和风控意见，做出最终买入/卖出/持有决策，给出具体交易计划"
    backstory = """你是经验丰富的A股交易员，擅长择时和执行。
    你理解市场情绪、技术形态、消息面对股价的影响。
    你只在高确定性机会出手，避免频繁交易。"""
    
    def __init__(self):
        self.llm = get_llm()
    
    def create(self):
        return Agent(
            role=self.role,
            goal=self.goal,
            backstory=self.backstory,
            llm=self.llm,
            verbose=True,
            allow_delegation=False
        )


class MarketWatcher:
    """市场观察 Agent - 负责市场整体状态"""
    
    role = "市场观察员"
    goal = "评估当前市场整体热度、牛熊状态、热门板块，帮助判断是否适合开仓"
    backstory = """你专注于A股整体市场情绪分析，
    通过换手率、北向资金、涨跌家数等指标判断市场状态。
    熊市轻仓或空仓，牛市积极布局。"""
    
    def __init__(self):
        self.llm = get_llm()
    
    def create(self):
        return Agent(
            role=self.role,
            goal=self.goal,
            backstory=self.backstory,
            llm=self.llm,
            verbose=True,
            allow_delegation=False
        )
