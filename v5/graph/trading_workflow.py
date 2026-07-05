"""
TradingAgents v5 - 四层 Agent 架构
分析层 → 研究层(多空辩论) → 交易层 → 风控层
基于 LangGraph StateGraph 编排
"""
import logging
from typing import TypedDict, Annotated, List, Dict, Optional
from langgraph.graph import StateGraph, END

logger = logging.getLogger("v5.graph")


# ── 状态定义 ──

class TradingState(TypedDict):
    # 输入
    stock_code: str
    stock_name: str
    # 数据层产出
    market_data: Dict          # 行情+技术指标
    news_data: List[Dict]      # 新闻
    social_data: Dict          # 社交情绪
    fundamentals: Dict         # 基本面
    # 分析层产出
    analysis_reports: List[Dict]  # 4个分析师报告
    # 研究层产出
    bull_argument: str         # 多头论点
    bear_argument: str         # 空头论点
    debate_round: int          # 当前辩论轮数
    debate_history: List[str]  # 辩论记录
    # 交易层产出
    trade_proposal: Dict       # 交易提案
    # 风控层产出
    risk_assessment: Dict      # 风控评估
    # 最终决策
    final_decision: Dict       # 最终决策
    # 记忆
    recalled_memories: List[Dict]  # 召回的历史决策


# ── 分析层节点 ──

def market_analyst_node(state: TradingState) -> dict:
    """市场分析师 - 技术指标分析"""
    from v5.agents.llm_client import get_llm
    from v5.data_adapters.ta_adapter import get_adapter

    llm = get_llm("analyst")
    adapter = get_adapter()
    code = state["stock_code"]

    logger.info(f"[MarketAnalyst] analyzing {code}...")

    # 获取技术指标
    indicators = adapter.get_technical_indicators(code)
    quote = adapter.get_realtime_quote(code)

    market_data = {
        "code": code,
        "name": state["stock_name"],
        "price": quote.get("price", 0),
        "change_pct": quote.get("change_pct", 0),
        "volume": quote.get("volume", 0),
        "indicators": indicators,
    }

    # LLM 分析
    system = "你是专业的A股技术分析师，擅长通过技术指标判断短期趋势。请简洁给出技术面分析。"
    user = f"""
股票: {state['stock_name']}({code})
现价: {market_data['price']}, 涨跌: {market_data['change_pct']}%
技术指标: {indicators}

请分析:
1. 趋势方向（多头/空头/震荡）
2. 关键支撑位和压力位
3. 技术信号（买入/卖出/观望）
请用JSON返回: {{"trend": "...", "support": ..., "resistance": ..., "signal": "BUY/SELL/HOLD", "confidence": 0-100, "reason": "..."}}
"""
    result = llm.chat_json(system, user)
    result["analyst"] = "market"
    result["data"] = market_data

    logger.info(f"[MarketAnalyst] {code}: signal={result.get('signal')}, confidence={result.get('confidence')}")
    return {"market_data": market_data, "analysis_reports": [result]}


def news_analyst_node(state: TradingState) -> dict:
    """新闻分析师 - 新闻事件分析"""
    from v5.agents.llm_client import get_llm
    from v5.data_adapters.ta_adapter import get_adapter

    llm = get_llm("analyst")
    adapter = get_adapter()
    code = state["stock_code"]

    logger.info(f"[NewsAnalyst] analyzing {code}...")

    news = adapter.get_news(code, limit=10)
    news_summary = "\n".join([f"- [{n['date']}] {n['title']}" for n in news])

    system = "你是专业的新闻分析师，擅长从新闻中提取对股价的影响。请简洁分析。"
    user = f"""
股票: {state['stock_name']}({code})
最新新闻:
{news_summary or '无新闻'}

请分析:
1. 重大利好/利空事件
2. 对短期股价的影响方向
请用JSON返回: {{"events": [...], "impact": "positive/negative/neutral", "signal": "BUY/SELL/HOLD", "confidence": 0-100, "reason": "..."}}
"""
    result = llm.chat_json(system, user)
    result["analyst"] = "news"
    result["data"] = {"news_count": len(news)}

    logger.info(f"[NewsAnalyst] {code}: impact={result.get('impact')}, confidence={result.get('confidence')}")
    return {"news_data": news, "analysis_reports": [result]}


def social_analyst_node(state: TradingState) -> dict:
    """社交情绪分析师"""
    from v5.agents.llm_client import get_llm
    from v5.data_adapters.ta_adapter import get_adapter

    llm = get_llm("analyst")
    adapter = get_adapter()
    code = state["stock_code"]

    logger.info(f"[SocialAnalyst] analyzing {code}...")

    sentiment = adapter.get_social_sentiment(code)

    system = "你是社交情绪分析师，通过社交媒体和新闻标题判断市场情绪。"
    user = f"""
股票: {state['stock_name']}({code})
情绪数据: {sentiment}

请用JSON返回: {{"sentiment": "positive/negative/neutral", "intensity": 0-100, "signal": "BUY/SELL/HOLD", "confidence": 0-100, "reason": "..."}}
"""
    result = llm.chat_json(system, user)
    result["analyst"] = "social"
    result["data"] = sentiment

    logger.info(f"[SocialAnalyst] {code}: sentiment={result.get('sentiment')}")
    return {"social_data": sentiment, "analysis_reports": [result]}


def fundamentals_analyst_node(state: TradingState) -> dict:
    """基本面分析师"""
    from v5.agents.llm_client import get_llm
    from v5.data_adapters.ta_adapter import get_adapter

    llm = get_llm("analyst")
    adapter = get_adapter()
    code = state["stock_code"]

    logger.info(f"[FundamentalsAnalyst] analyzing {code}...")

    fund = adapter.get_fundamentals(code)

    system = "你是基本面分析师，擅长通过PE/PB/ROE等指标评估股票价值。"
    user = f"""
股票: {state['stock_name']}({code})
基本面: PE={fund.get('pe')}, PB={fund.get('pb')}, ROE={fund.get('roe')}, 净利润增速={fund.get('profit_yoy')}%
总市值={fund.get('total_mv')}, 换手率={fund.get('turnover_rate')}%

请分析:
1. 估值水平（高估/合理/低估）
2. 成长性
3. 是否值得投资
请用JSON返回: {{"valuation": "overvalued/fair/undervalued", "growth": "high/medium/low", "signal": "BUY/SELL/HOLD", "confidence": 0-100, "reason": "..."}}
"""
    result = llm.chat_json(system, user)
    result["analyst"] = "fundamentals"
    result["data"] = fund

    logger.info(f"[FundamentalsAnalyst] {code}: valuation={result.get('valuation')}")
    return {"fundamentals": fund, "analysis_reports": [result]}


# ── 研究层节点（多空辩论）──

def bull_researcher_node(state: TradingState) -> dict:
    """多头研究员 - 寻找买入理由"""
    from v5.agents.llm_client import get_llm
    from v5.config import DEBATE_ROUNDS

    llm = get_llm("reasoner")
    reports = state.get("analysis_reports", [])
    round_num = state.get("debate_round", 0)
    prev_bear = state.get("bear_argument", "")

    logger.info(f"[BullResearcher] round {round_num} for {state['stock_code']}...")

    # 汇总分析师报告
    reports_text = "\n".join([
        f"- {r.get('analyst','')}: signal={r.get('signal','')}, confidence={r.get('confidence',0)}, reason={r.get('reason','')}"
        for r in reports
    ])

    system = """你是多头研究员，你的任务是找出这只股票值得买入的理由。
你要从分析师报告中寻找支持买入的证据，并反驳空头观点。保持客观，但立场是看多。"""

    user = f"""
股票: {state['stock_name']}({state['stock_code']})
分析报告:
{reports_text}

{'上一轮空头观点:' + prev_bear if prev_bear else '这是第一轮辩论'}

请给出你的多头论点（2-3个核心理由），并尝试反驳空头观点。输出纯文本。
"""
    argument = llm.chat(system, user)

    history = state.get("debate_history", [])
    history.append(f"[第{round_num+1}轮-多头]: {argument[:200]}")

    logger.info(f"[BullResearcher] argument: {argument[:100]}...")
    return {"bull_argument": argument, "debate_history": history}


def bear_researcher_node(state: TradingState) -> dict:
    """空头研究员 - 寻找卖出/不买理由"""
    from v5.agents.llm_client import get_llm

    llm = get_llm("reasoner")
    reports = state.get("analysis_reports", [])
    round_num = state.get("debate_round", 0)
    prev_bull = state.get("bull_argument", "")

    logger.info(f"[BearResearcher] round {round_num} for {state['stock_code']}...")

    reports_text = "\n".join([
        f"- {r.get('analyst','')}: signal={r.get('signal','')}, confidence={r.get('confidence',0)}, reason={r.get('reason','')}"
        for r in reports
    ])

    system = """你是空头研究员，你的任务是找出这只股票不该买入的理由。
你要从分析师报告中寻找风险和利空因素，并反驳多头观点。保持客观，但立场是看空。"""

    user = f"""
股票: {state['stock_name']}({state['stock_code']})
分析报告:
{reports_text}

{'上一轮多头观点:' + prev_bull if prev_bull else '这是第一轮辩论'}

请给出你的空头论点（2-3个核心风险），并尝试反驳多头观点。输出纯文本。
"""
    argument = llm.chat(system, user)

    history = state.get("debate_history", [])
    history.append(f"[第{round_num+1}轮-空头]: {argument[:200]}")

    logger.info(f"[BearResearcher] argument: {argument[:100]}...")
    return {"bear_argument": argument, "debate_history": history}


def debate_moderator_node(state: TradingState) -> dict:
    """辩论主持人 - 判断是否继续辩论"""
    from v5.config import DEBATE_ROUNDS

    round_num = state.get("debate_round", 0)
    next_round = round_num + 1

    logger.info(f"[DebateModerator] round {round_num} → {next_round} (max {DEBATE_ROUNDS})")

    return {"debate_round": next_round}


def should_continue_debate(state: TradingState) -> str:
    """条件边：判断是否继续辩论"""
    from v5.config import DEBATE_ROUNDS

    if state.get("debate_round", 0) < DEBATE_ROUNDS:
        return "continue"
    return "done"


# ── 交易层节点 ──

def trader_node(state: TradingState) -> dict:
    """交易员 - 综合辩论结果生成交易提案"""
    from v5.agents.llm_client import get_llm

    llm = get_llm("reasoner")

    reports = state.get("analysis_reports", [])
    bull = state.get("bull_argument", "")
    bear = state.get("bear_argument", "")

    # 综合信号
    signals = [r.get("signal", "HOLD") for r in reports]
    buy_count = signals.count("BUY")
    sell_count = signals.count("SELL")

    system = """你是交易员，需要综合分析师报告和多空辩论结果，做出最终交易提案。
你必须给出明确的决策：BUY / SELL / HOLD，以及具体的仓位建议。"""

    user = f"""
股票: {state['stock_name']}({state['stock_code']})
现价: {state.get('market_data', {}).get('price', 0)}

分析师信号汇总: {signals} (BUY:{buy_count}, SELL:{sell_count})

多头论点:
{bull}

空头论点:
{bear}

历史经验:
{[m['document'][:100] for m in state.get('recalled_memories', [])]}

请给出交易提案，用JSON返回:
{{"action": "BUY/SELL/HOLD", "confidence": 0-100, "volume": 股数, "reason": "决策理由", "stop_loss": 止损价, "take_profit": 止盈价}}
注意: 最大持仓5只，单只仓位不超过总资产20%。
"""
    proposal = llm.chat_json(system, user)

    logger.info(f"[Trader] {state['stock_code']}: action={proposal.get('action')}, confidence={proposal.get('confidence')}")
    return {"trade_proposal": proposal}


# ── 风控层节点 ──

def risk_manager_node(state: TradingState) -> dict:
    """风控经理 - 评估交易提案的风险"""
    from v5.agents.llm_client import get_llm

    llm = get_llm("reasoner")
    proposal = state.get("trade_proposal", {})

    if proposal.get("action") == "HOLD":
        return {"risk_assessment": {"approved": True, "reason": "HOLD无需风控"}}

    system = """你是风控经理，需要对交易提案进行独立风险评估。
你的原则：保住本金 > 追求收益。风险收益比低于2:1的操作予以否决。"""

    user = f"""
股票: {state['stock_name']}({state['stock_code']})
交易提案: {proposal}
基本面: {state.get('fundamentals', {})}

请评估并返回JSON:
{{"approved": true/false, "risk_score": 0-100, "risk_reward_ratio": x, "concerns": [...], "adjustments": "建议调整（如有）"}}
"""
    assessment = llm.chat_json(system, user)

    # 如果不批准，在 final_decision 中标记
    approved = assessment.get("approved", False)
    if not approved:
        proposal["action"] = "HOLD"
        proposal["reason"] = f"风控否决: {assessment.get('concerns', [])}"

    logger.info(f"[RiskManager] {state['stock_code']}: approved={approved}, risk_score={assessment.get('risk_score')}")
    return {"risk_assessment": assessment, "final_decision": proposal}


# ── 记忆节点 ──

def memory_writer_node(state: TradingState) -> dict:
    """写入交易记忆"""
    from v5.memory.chroma_store import get_memory

    memory = get_memory()
    decision = state.get("final_decision", {})

    market_ctx = f"价格{state.get('market_data', {}).get('price', 0)}, 涨跌{state.get('market_data', {}).get('change_pct', 0)}%"

    analysis_summary = "; ".join([
        f"{r.get('analyst','')}:{r.get('signal','')}"
        for r in state.get("analysis_reports", [])
    ])

    memory.store_decision(
        stock_code=state["stock_code"],
        stock_name=state["stock_name"],
        decision=decision.get("action", "HOLD"),
        market_context=market_ctx,
        analysis_summary=analysis_summary,
        risk_assessment=str(state.get("risk_assessment", {})),
        volume=decision.get("volume", 0),
        price=state.get("market_data", {}).get("price", 0),
    )

    logger.info(f"[MemoryWriter] stored decision for {state['stock_code']}")
    return {}


def memory_recall_node(state: TradingState) -> dict:
    """召回历史记忆"""
    from v5.memory.chroma_store import get_memory

    memory = get_memory()
    market_ctx = f"股票{state['stock_name']}，现价{state.get('market_data', {}).get('price', 0)}"
    recalled = memory.recall_similar(market_ctx, n_results=3)

    logger.info(f"[MemoryRecall] recalled {len(recalled)} memories for {state['stock_code']}")
    return {"recalled_memories": recalled}


# ── 构建工作流 ──

def build_trading_graph():
    """构建 LangGraph 交易决策工作流"""
    graph = StateGraph(TradingState)

    # 添加节点
    graph.add_node("market_analyst", market_analyst_node)
    graph.add_node("news_analyst", news_analyst_node)
    graph.add_node("social_analyst", social_analyst_node)
    graph.add_node("fundamentals_analyst", fundamentals_analyst_node)
    graph.add_node("memory_recall", memory_recall_node)
    graph.add_node("bull_researcher", bull_researcher_node)
    graph.add_node("bear_researcher", bear_researcher_node)
    graph.add_node("debate_moderator", debate_moderator_node)
    graph.add_node("trader", trader_node)
    graph.add_node("risk_manager", risk_manager_node)
    graph.add_node("memory_writer", memory_writer_node)

    # 入口：4个分析师并行
    graph.set_entry_point("market_analyst")

    # 分析师 → 记忆召回（并行收敛后）
    # LangGraph 不支持多入口并行，用 fan-out 模式
    graph.add_edge("market_analyst", "news_analyst")
    graph.add_edge("news_analyst", "social_analyst")
    graph.add_edge("social_analyst", "fundamentals_analyst")
    graph.add_edge("fundamentals_analyst", "memory_recall")

    # 记忆召回 → 多空辩论
    graph.add_edge("memory_recall", "bull_researcher")
    graph.add_edge("bull_researcher", "bear_researcher")
    graph.add_edge("bear_researcher", "debate_moderator")

    # 辩论循环
    graph.add_conditional_edges(
        "debate_moderator",
        should_continue_debate,
        {
            "continue": "bull_researcher",  # 继续辩论
            "done": "trader",                # 辩论结束 → 交易员
        }
    )

    # 交易 → 风控 → 记忆写入 → 结束
    graph.add_edge("trader", "risk_manager")
    graph.add_edge("risk_manager", "memory_writer")
    graph.add_edge("memory_writer", END)

    return graph.compile()
