"""
CrewAI Tasks - 任务定义 v2.0
新增市场状态和仓位管理提示
"""
from crewai import Task
from typing import Dict, Any, List


def create_market_analysis_task(watcher_agent, market_data: str) -> Task:
    """市场分析任务"""
    return Task(
        description=f"""分析当前A股市场整体状态：

{market_data}

请输出：
1. 市场整体热度（高/中/低）
2. 建议仓位（空仓/轻仓/半仓/重仓/满仓）
3. 当前适合买股票吗？（是/否，原因）
4. 热门板块方向（如果有）
5. 适合哪些策略（趋势跟踪/均值回归/突破交易）

注意：如果市场状态是"熊市"或"低迷"，建议仓位不应超过3成。
""",
        agent=watcher_agent,
        expected_output="市场分析报告，包含热度、建议仓位、是否适合交易、热门板块、推荐策略"
    )


def create_research_task(research_agent, market_analysis: str, stock_data: str) -> Task:
    """选股研究任务"""
    return Task(
        description=f"""基于以下市场分析和股票数据，进行选股研究：

【市场分析】
{market_analysis}

【候选股票数据】
{stock_data}

请从候选股票中筛选出3-5只最值得买入的股票，
每只股票输出：
1. 股票代码和名称
2. 入选理由（估值/趋势/基本面/板块轮动）
3. 目标买入价区间（建议现价的-5%~0%范围内）
4. 预期持有周期（短线1-2周/中线1个月/长线3个月+）
5. 潜在上涨空间（目标价相比现价）
6. 适合的策略（均线/MACD/RSI/布林带等）

优先选择：
- 在强势板块中的股票
- 技术面健康的股票（MA多头排列、RSI不高不低）
- 有催化剂的股票（业绩超预期、政策利好等）
""",
        agent=research_agent,
        expected_output="选股报告，包含3-5只推荐股票及详细理由"
    )


def create_risk_task(risk_agent, stock_picks: str, market_analysis: str) -> Task:
    """风险评估任务"""
    return Task(
        description=f"""对以下选股进行独立风险评估：

【研究员选股】
{stock_picks}

【市场状态】
{market_analysis}

请对每只股票评估：
1. 主要风险（下跌空间，正常应控制在-10%以内）
2. 建议仓位（单只股票仓位不超过总资金20%）
3. 止损价（建议设在买入价下方-8%~-15%）
4. 止盈价（建议设在买入价上方+15%~+30%）
5. 风险收益比（止损空间vs止盈空间，应>1:2）
6. 整体组合风险评级（低/中/高）
7. 如果当前市场是熊市或震荡市，仓位应比牛市更低

组合仓位建议：
- 牛市：总仓位可达8成，单只可达2成
- 震荡市：总仓位5成，单只1成
- 熊市：总仓位3成，单只1成
""",
        agent=risk_agent,
        expected_output="风控报告，包含每只股票的仓位、止损、止盈和风险评级"
    )


def create_trading_task(trading_agent, research: str, risk: str, market: str) -> Task:
    """最终交易决策任务"""
    return Task(
        description=f"""综合所有分析，做出最终交易决策：

【研究员意见】
{research}

【风控意见】
{risk}

【市场状态】
{market}

请给出最终交易计划，格式如下：

## 今日交易计划

### 市场判断
（简述当前市场状态和建议仓位）

### 推荐股票（按优先级排序）
对于每只股票：
1. **代码和名称**
2. **买入价**：xxx元（现价或以下）
3. **仓位**：xxx%（总资金的百分比）
4. **止损价**：xxx元（跌破必须卖出）
5. **止盈价**：xxx元（达到目标可卖出）
6. **持有周期**：短线/中线/长线
7. **核心逻辑**：一句话说明为什么买这只

### 风险提示
（任何需要注意的风险）

### 操作纪律
- 严格执行止损，不扛单
- 分批买入，不要一次满仓
- 达到止盈可以分批卖出
""",
        agent=trading_agent,
        expected_output="最终交易计划，包含具体股票代码、买入价、仓位、止损止盈"
    )
