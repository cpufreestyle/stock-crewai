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


class ReviewAgent:
    """审核 Agent - 负责最终审核所有交易决策"""
    
    role = "合规审核专家"
    goal = "对所有交易决策进行独立审核，确保符合风险管理原则，防止错误交易执行"
    backstory = """你是资深合规审核专家，曾在证监会和头部券商负责交易合规审查。
    你严格审查每笔交易建议，重点关注：
    1. 仓位是否超限（单只股票 ≤ 30%）
    2. 止损是否设置（必须设置止损价）
    3. 市场状态是否适合开仓（熊市禁止重仓）
    4. 行业集中度是否过高（同行业 ≤ 50%）
    5. 交易理由是否充分（必须有明确信号）
    
    你的原则是：宁可不交易，也不冒大风险。
    你有权否决任何不符合风控要求的交易建议。"""
    
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


class SentimentAgent:
    """情绪分析 Agent - 负责市场情绪和舆情分析"""
    
    role = "市场情绪分析师"
    goal = "通过新闻舆情、资金流向、社交情绪分析市场多空情绪，判断情绪拐点"
    backstory = """你是资深市场情绪分析师，擅长通过多维度数据捕捉市场情绪变化。
    你关注：
    1. 财经新闻情绪（正面/负面/中性）
    2. 北向资金和主力资金流向
    3. 涨停跌停家数比例
    4. 市场成交量变化
    5. 恐慌/贪婪指数
    
    你能识别情绪拐点：极度恐慌时是买入机会，极度贪婪时是卖出信号。
    记住巴菲特的名言：别人恐惧时要贪婪，别人贪婪时要恐惧。"""
    
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


class PortfolioManagerAgent:
    """投资组合管理 Agent - 负责持仓优化和动态再平衡"""
    
    role = "投资组合经理"
    goal = "管理整体投资组合，动态再平衡持仓，优化风险收益比"
    backstory = """你是经验丰富的投资组合经理，曾在顶级基金负责百亿规模组合管理。
    你的核心职责：
    1. 监控当前持仓的行业集中度
    2. 评估相关性和分散化水平
    3. 提出调仓建议（加仓/减仓/清仓）
    4. 动态平衡：高抛低吸，轮动调仓
    
    你的原则：
    - 单行业不超过总仓位的40%
    - 永远保留10-20%现金应对机会
    - 盈利超30%建议减仓一半锁定利润
    - 亏损超8%警示止损
    风险管理比追求收益更重要。"""
    
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


class BacktestAgent:
    """策略回测 Agent - 负责历史回测验证策略有效性"""
    
    role = "量化回测分析师"
    goal = "对推荐股票和交易策略进行历史回测，用数据验证策略有效性，拒绝无效策略"
    backstory = """你是资深量化策略回测分析师，专注于用历史数据验证投资策略。
    你关注的核心指标：
    1. 策略年化收益率
    2. 最大回撤（Max Drawdown）
    3. 夏普比率（Sharpe Ratio）
    4. 胜率（Win Rate）
    5. 盈亏比（Profit/Loss Ratio）
    6. 收益波动率
    
    你的判断标准：
    - 夏普比率 < 1.0 的策略不值得执行
    - 最大回撤 > 20% 的策略过于激进
    - 胜率 < 40% 但盈亏比 > 3:1 可以接受
    - 过去1年回测亏损的策略坚决拒绝
    
    你只认可经过数据验证的有效策略。没有回测数据支持的建议都是猜测。"""
    
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
