"""
CrewAI Tasks - 任务定义 v2.0
新增市场状态和仓位管理提示
"""
from crewai import Task


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
        description=f"""从下方候选股票池中筛选出3-5只最值得买入的股票。

【市场分析】
{market_analysis}

【候选股票数据】
{stock_data}

【数据使用约定】
上方候选股票数据已含现价、MA5/MA20、RSI、5日涨跌、PE、PB、总市值与板块归属，
足以完成本任务。请直接输出 Final Answer，不要逐只股票调用工具；
确需补充时最多调用 1 次 fundamental_analysis，并在一次调用里用逗号传入多只代码。
标记为"暂缺"的字段一律写"数据缺失"，不得凭印象补数字；催化剂只可引用上方新闻摘要，
摘要里没有就写"无"。

每只股票输出：
1. 股票代码和名称
2. 入选理由（估值/趋势/板块轮动，须引用上方数据中的具体数字）
3. 目标买入价区间（建议现价的-5%~0%范围内）
4. 预期持有周期（短线1-2周/中线1个月/长线3个月+）
5. 潜在上涨空间（目标价相比现价）
6. 适合的策略（均线/MACD/RSI/布林带等）

优先选择：
- 技术面健康的股票（MA5>MA20、RSI 不高不低）
- 属于上方强势板块的股票
- 估值合理的股票（PE/PB 在同池中偏低）
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

【工具使用纪律】
- 每只股票：stop_loss_advice、risk_reward 各最多调用一次，接受工具返回值，
  不要为了凑"风险收益比>1:2"反复微调目标价重复调用 risk_reward
  （9/26 实测反复微调 target 重算，8 轮就烧光迭代，最后只能回显框架收尾提示语）。
- 所有股票评估完成后直接输出报告，不要再调用任何工具。
""",
        agent=risk_agent,
        expected_output="风控报告，包含每只股票的仓位、止损、止盈和风险评级"
    )


def create_trading_task(trading_agent, research: str, risk: str, market: str) -> Task:
    """最终交易决策任务（简化版，减少 token 消耗）"""
    return Task(
        description=f"""综合以下分析，输出简洁的交易计划：

【研究员推荐】
{research}

【风控建议】
{risk}

【市场状态】
{market}

请输出：

## 今日交易计划

### 市场判断 + 建议仓位
（一句话简述）

### 推荐股票（按优先级，最多3只）

| 代码 | 名称 | 买入价 | 仓位% | 止损价 | 止盈价 | 周期 | 核心逻辑 |
|------|------|--------|-------|--------|--------|------|----------|

### 风险提示（1-2条）

### 操作纪律
- 严格执行止损
- 分批买入
- 达到止盈分批卖出

【工具使用纪律】
- position_size 每只股票最多调用一次，接受返回的股数（已按整百股取整），
  不要反复微调 stop_loss_pct / risk_per_trade 去凑心仪的股数
  （9/26 实测把 risk_per_trade 从 0.008 改成 0.009 再改 0.0085，24 次调用烧光迭代）。
- 止损止盈价用风控建议里的数字或 stop_loss_advice 的结果。
- 本任务**只输出计划，不执行任何交易**：没有下单类工具可用，
  止损止盈写进表格即可，不要试图"设置"或"提交"它们。
- 表格与纪律写完后直接输出终稿，不要再调用任何工具。

【输出格式要求——抬底前必须附上机器可读摘要】
在报告最末尾追加一个 ```json 代码块（除此块外，不要再写任何代码块）：
{{"market_view": "一句话市场判断", "actions": [{{"code": "000001", "name": "平安银行", "action": "buy", "price": 11.3, "position_pct": 10, "stop_loss": 10.4, "take_profit": 12.5, "confidence": "medium", "reason": "一句话核心理由"}}]}}
- action 只能是 buy / sell / hold / add / reduce / set_stop_loss / watch；本轮无操作就输出空数组 []
- price/stop_loss/take_profit/position_pct 只写数字，不要带元、百分号、千分位
- code 必须是 6 位 A 股代码；没有的字段写 null，不要省略键名
""",
        agent=trading_agent,
        expected_output="最终交易计划（Markdown表格格式）"
    )


def create_sentiment_task(sentiment_agent, stock_picks: str) -> Task:
    """情绪分析任务"""
    return Task(
        description=f"""对研究员选出的股票做情绪判断：
候选股票：{stock_picks}

【数据来源说明——重要】
本任务的三个工具（news_sentiment / social_sentiment / sentiment_score）背后是同一条新闻接口，
该接口当前故障，只会返回"未获取到新闻数据"。因此**不要调用任何工具**，
改用上下文中已有的量价数据判断情绪：RSI（>70 超买 / <30 超卖）、5日涨跌、
涨停/跌停家数、所属板块当日涨跌幅。
不得编造新闻、政策或"资金涌入"等上下文中没有的事实。

请输出：
1. 每只股票：情绪评分（0-100，50 为中性）+ 判据（引用上面哪个具体数字）+ 一句交易建议
2. 情绪极值（最恐慌与最亢奋的各一只）对应的机会与风险
3. 一句话小结：当前情绪对建仓时点的指示""",
        agent=sentiment_agent,
        expected_output="情绪分析报告，包含每只股票的情绪评分、判据和交易建议"
    )


def create_backtest_task(backtest_agent, stock_picks: str) -> Task:
    """回测验证任务"""
    return Task(
        description=f"""对研究员选出的股票做历史回测验证：
候选股票：{stock_picks}

backtest 工具支持一次查询多只：请把全部候选代码用逗号拼成一个参数**调用 1 次**
（如 code="000333,000858"），不要逐只调用；拿到结果后直接输出 Final Answer。

请输出：每只股票三种策略（买入持有/均线/RSI）的收益率、最大回撤、胜率对比，
指出最佳策略及其回撤是否可接受，并给风控一句话结论（该股票历史波动是否配得上拟定的止损幅度）。""",
        agent=backtest_agent,
        expected_output="回测验证报告，包含每只股票的回测评分和策略表现"
    )


def create_rebalance_task(rebalancer_agent, trade_plan: str, market_state: str) -> Task:
    """动态调仓任务"""
    return Task(
        description=f"""根据市场变化和持仓表现，给出动态调仓**建议**：
        交易计划：{trade_plan}
        市场状态：{market_state}
        请分析每只持仓是否需要止损、止盈或加减仓，并说明理由。

【只出建议，不执行】
本任务没有下单类工具，任何"已执行"的表述都是编造。请对每只持仓输出：
建议动作（buy/sell/add/reduce/hold/watch）+ 触发条件（具体价位或涨跌幅）+ 建议股数 + 一句话理由。

【工具使用纪律】
- 先用 view_portfolio 看一次持仓，之后同一数据不要重复查询。
- 需要止损价参考时，每只持仓至多调一次 stop_loss_advice，接受返回值。
- 建议写完后直接输出终稿，不要再调用任何工具。

【输出格式要求——抬底前必须附上机器可读摘要】
在报告最末尾追加一个 ```json 代码块（除此块外，不要再写任何代码块）：
{{"market_view": "一句话市场判断", "actions": [{{"code": "000001", "name": "平安银行", "action": "buy", "price": 11.3, "position_pct": 10, "stop_loss": 10.4, "take_profit": 12.5, "confidence": "medium", "reason": "一句话核心理由"}}]}}
- action 只能是 buy / sell / hold / add / reduce / set_stop_loss / watch；本轮无操作就输出空数组 []
- price/stop_loss/take_profit/position_pct 只写数字，不要带元、百分号、千分位
- code 必须是 6 位 A 股代码；没有的字段写 null，不要省略键名
""",
        agent=rebalancer_agent,
        expected_output="动态调仓建议报告，逐只持仓给出建议动作、触发条件和建议股数（不含任何已执行操作）"
    )
