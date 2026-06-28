# Stock CrewAI → 多 Agent 协作系统架构设计

> 版本: v5.0 | 日期: 2026-06-15 | 作者: 前端开发者

---

## 一、现状分析

### 当前架构（v3.0）

```
┌─────────────────────────────────────────────────────┐
│ crew.py: run_daily_analysis()                        │
│   ┌─────────────┐                                    │
│   │ MarketWatcher│→ market_task                       │
│   └─────────────│                                    │
│   ┌─────────────┐                                    │
│   │ Researcher   │→ research_task (依赖 market_task) │
│   └─────────────│                                    │
│   ┌─────────────┐                                    │
│   │ RiskAgent    │→ risk_task (依赖 research_task)   │
│   └─────────────│                                    │
│   ┌─────────────┐                                    │
│   │ TradingAgent │→ trading_task (依赖 risk_task)    │
│   └─────────────│                                    │
│                                                       │
│ Process.sequential → 纯线性流水线                      │
│ kickoff() → 一次性执行 → 无状态 → 无反馈循环           │
└─────────────────────────────────────────────────────┘
```

**问题清单**：

| # | 问题 | 严重程度 | 说明 |
|---|------|----------|------|
| 1 | **线性流水线无反馈** | 🔴 严重 | Researcher 输出后直接进入 Risk，Risk 无法质疑 Researcher 的选股逻辑 |
| 2 | **Agent 无工具能力** | 🔴 严重 | 所有 Agent 都是纯 LLM 文字推理，不能调用数据接口、计算指标 |
| 3 | **一次性执行** | 🟡 中等 | `kickoff()` 后结束，没有循环迭代和自我修正 |
| 4 | **无共享记忆** | 🟡 中等 | Agent 之间只通过 task output 传递文本，无结构化共享状态 |
| 5 | **数据准备冗余** | 🟡 中等 | `prepare_market_data()` 独立模块，未与 Agent 工具集成 |
| 6 | **双系统割裂** | 🔴 严重 | CrewAI(v3 日常分析) 和 run_virtual_v4.py(v4 自动交易) 是两套独立逻辑，互不通信 |
| 7 | **无实时事件驱动** | 🟡 中等 | v4 定时扫描（10min），v3 手动触发，都无法响应突发事件 |
| 8 | **Dashboard 只读** | 🟢 低 | 前端只能看数据，不能干预 Agent 决策 |

---

## 二、目标架构

### 核心原则

1. **Agent = 工具 + 推理**：每个 Agent 不仅是 LLM，还拥有可调用的工具集
2. **事件驱动**：市场异动 → 触发 Agent 协作 → 决策 → 执行 → 通知
3. **双向反馈**：下游 Agent 可以质疑上游结论，触发重新分析
4. **统一编排**：合并 v3(CrewAI) 和 v4(virtual_v4)，一个系统同时支持分析+交易
5. **Dashboard 可干预**：前端可以查看 Agent 状态、手动触发任务、审批交易

### 架构图

```
┌─────────────────────────────────────────────────────────────────┐
│                     Orchestrator (编排中枢)                       │
│  ┌───────────┐ ┌───────────┐ ┌─────────────┐ ┌──────────────┐ │
│  │ EventBus  │ │ TaskQueue │ │ StateStore  │ │ AgentRegistry│ │
│  └───────────┘ └───────────┘ └──────────────┘ └──────────────┘ │
│                                                                  │
│  ┌─ 事件驱动循环 ──────────────────────────────────────────────┐ │
│  │ on_market_open   → 触发 MarketWatcher                      │ │
│  │ on_price_alert   → 触发 RiskAgent (止损止盈检查)            │ │
│  │ on_daily_trigger → 触发完整分析流水线                        │ │
│  │ on_manual_trigger→ Dashboard 手动触发                       │ │
│  │ on_agent_complete→ 下游 Agent 自动接续                      │ │
│  │ on_rejection     → 上游 Agent 重新分析                      │ │
│  └─────────────────────────────────────────────────────────────┘ │
│                                                                  │
│  ┌─ Agent 集群 ────────────────────────────────────────────────┐ │
│  │                                                              │ │
│  │  🏛️ MarketWatcher                                           │ │
│  │     Tools: market_heat(), market_regime(), sector_rotation()│ │
│  │     Output: MarketState → StateStore                        │ │
│  │                                                              │ │
│  │  🔬 Researcher                                              │ │
│  │     Tools: stock_search(), technical_analysis(),             │ │
│  │            backtest(), news_sentiment(), financial_data()    │ │
│  │     Output: StockPicks[] → StateStore                       │ │
│  │                                                              │ │
│  │  🛡️ RiskManager                                             │ │
│  │     Tools: kelly_position(), risk_reward(), portfolio_risk(),│ │
│  │            circuit_breaker_check()                           │ │
│  │     Output: RiskAssessment → StateStore                     │ │
│  │     ⚡ 可 REJECT → 退回 Researcher 重新选股                  │ │
│  │                                                              │ │
│  │  💹 Trader                                                   │ │
│  │     Tools: execute_buy(), execute_sell(), set_stop_loss(),   │ │
│  │            notify_wechat()                                   │ │
│  │     Output: TradeAction[] → EventBus → 实际执行              │ │
│  │     ⚡ 可 HOLD → 等待更好时机                                │ │
│  │                                                              │ │
│  │  📊 PerformanceAuditor (新增)                                │ │
│  │     Tools: calculate_metrics(), compare_strategies(),        │ │
│  │            generate_report()                                 │ │
│  │     Output: PerformanceReport → StateStore                  │ │
│  │     ⚡ 独立运行，每日收盘后自动评估                           │ │
│  │                                                              │ │
│  └──────────────────────────────────────────────────────────────┘ │
│                                                                  │
│  ┌─ 通信层 ────────────────────────────────────────────────────┐ │
│  │ StateStore (Redis/SQLite) ← 所有 Agent 读/写共享状态        │ │
│  │ EventBus   (async queue)  ← 事件广播                        │ │
│  │ Dashboard  (Flask + WS)   ← 前端干预 + 实时状态推送          │ │
│  └──────────────────────────────────────────────────────────────┘ │
└─────────────────────────────────────────────────────────────────┘
```

---

## 三、文件结构设计

```
stock-crewai/
├── core/                          # 新增：核心框架
│   ├── orchestrator.py            # 编排中枢（EventBus + TaskQueue + 循环）
│   ├── event_bus.py               # 事件总线（发布/订阅）
│   ├── state_store.py             # 共享状态（SQLite，替代纯文件）
│   ├── agent_base.py              # Agent 基类（统一接口）
│   └── tool_registry.py           # 工具注册表（动态发现）
│
├── agents/                        # 重构：从 agents.py 拆分
│   ├── market_watcher.py          # 市场观察员（+ 工具）
│   ├── researcher.py              # 选股研究员（+ 工具）
│   ├── risk_manager.py            # 风控专家（+ 工具 + REJECT 能力）
│   ├── trader.py                  # 交易员（+ 工具 + HOLD 能力）
│   ├── performance_auditor.py     # 新增：绩效审计员
│   └── __init__.py
│
├── tools/                         # 新增：Agent 可调用的工具集
│   ├── market_tools.py            # 市场数据工具（heat/regime/sector）
│   ├── stock_tools.py             # 股票搜索与分析工具
│   ├── risk_tools.py              # 风控计算工具（Kelly/VaR/回撤）
│   ├── trade_tools.py             # 交易执行工具（买卖/止损止盈）
│   ├── notify_tools.py            # 通知工具（微信/Dashboard）
│   └── __init__.py
│
├── workflows/                     # 新增：预定义工作流
│   ├── daily_analysis.py          # 每日分析完整流水线
│   ├── realtime_monitor.py        # 实时监控+止损触发
│   ├── manual_trigger.py          # Dashboard 手动触发
│   └── __init__.py
│
├── data/                          # 保留（数据层）
│   ├── data_fetcher.py            # 保持不变，但工具层引用它
│   ├── technical_indicators.py    # 保持不变
│   ├── portfolio_tracker.py       # 保持不变
│   ├── api_cache.py               # 保持不变
│   └── backtest.py                # 保持不变
│
├── web/                           # 重构：Dashboard 独立目录
│   ├── app.py                     # Flask app（原 web_dashboard.py）
│   ├── websocket.py               # 新增：实时推送（Socket.IO）
│   ├── templates/
│   │   └── index.html             # 已优化，增加 Agent 状态面板
│   └── static/
│
├── config.py                      # 保留+扩展（新增编排参数）
├── .env                           # 保留
├── requirements.txt               # 更新
└── main.py                        # 新增：统一入口
```

---

## 四、核心模块详细设计

### 4.1 Agent 基类 (`core/agent_base.py`)

```python
class AgentBase:
    """所有 Agent 的统一基类"""
    
    name: str                    # Agent 名称
    role: str                    # 角色
    tools: List[BaseTool]        # 可用工具列表
    llm: Any                     # LLM 配置
    
    # ── 状态 ──
    status: AgentStatus          # idle / running / waiting / error
    
    # ── 生命周期 ──
    def on_activate(self, context: dict) -> None:
        """被编排器激活时"""
    
    def on_complete(self, output: dict) -> dict:
        """任务完成，返回结果 + 事件"""
    
    def on_reject(self, reason: str, from_agent: str) -> dict:
        """被下游 Agent 退回时，重新分析"""
    
    # ── 执行 ──
    def run(self, task: Task, state: StateStore) -> AgentOutput:
        """核心执行方法"""
        # 1. 从 StateStore 读取上下文
        # 2. 组装 CrewAI Agent（带工具）
        # 3. 执行 LLM 推理
        # 4. 写入 StateStore
        # 5. 发布事件到 EventBus
    
    # ── 工具调用 ──
    def call_tool(self, tool_name: str, **kwargs) -> Any:
        """安全调用工具（权限检查 + 日志）"""
```

### 4.2 编排中枢 (`core/orchestrator.py`)

```python
class Orchestrator:
    """多 Agent 编排中枢"""
    
    def __init__(self):
        self.event_bus = EventBus()
        self.state_store = StateStore()
        self.agent_registry = AgentRegistry()
        self.task_queue = TaskQueue()
    
    # ── 注册 ──
    def register_agent(self, agent: AgentBase) -> None:
        """注册 Agent + 订阅其关心的事件"""
    
    def register_workflow(self, workflow: Workflow) -> None:
        """注册预定义工作流"""
    
    # ── 事件驱动 ──
    def on_event(self, event: Event) -> None:
        """事件触发 → 查找对应 Agent → 创建 Task → 推入队列"""
    
    # ── 反馈循环 ──
    def on_rejection(self, rejection: RejectionEvent) -> None:
        """下游退回 → 通知上游 Agent → 重新执行"""
    
    # ── 执行 ──
    def execute_task(self, task: Task) -> AgentOutput:
        """执行单个任务"""
    
    def execute_workflow(self, workflow_name: str, params: dict) -> WorkflowResult:
        """执行完整工作流"""
    
    # ── 循环模式 ──
    def run_loop(self) -> None:
        """主循环：监听事件 → 分发 → 执行 → 记录"""
```

### 4.3 事件总线 (`core/event_bus.py`)

```python
# 事件类型
class EventType:
    MARKET_OPEN     = "market_open"       # 开盘
    MARKET_CLOSE    = "market_close"       # 收盘
    PRICE_ALERT     = "price_alert"        # 异动（涨跌>3%）
    DAILY_TRIGGER   = "daily_trigger"      # 定时触发（每日9:30）
    MANUAL_TRIGGER  = "manual_trigger"     # Dashboard 手动触发
    AGENT_COMPLETE  = "agent_complete"     # Agent 完成
    AGENT_REJECT    = "agent_reject"       # Agent 退回
    TRADE_EXECUTED  = "trade_executed"     # 交易执行
    CIRCUIT_BREAKER = "circuit_breaker"    # 熔断触发
```

### 4.4 共享状态 (`core/state_store.py`)

```python
class StateStore:
    """所有 Agent 的共享状态（SQLite-backed）"""
    
    # ── 读 ──
    def get_market_state(self) -> MarketState
    def get_stock_picks(self) -> List[StockPick]
    def get_risk_assessment(self) -> RiskAssessment
    def get_portfolio(self) -> Portfolio
    def get_agent_status(self) -> Dict[str, AgentStatus]
    
    # ── 写 ──
    def set_market_state(self, state: MarketState) -> None
    def set_stock_picks(self, picks: List[StockPick]) -> None
    def set_risk_assessment(self, assessment: RiskAssessment) -> None
    def update_agent_status(self, agent: str, status: AgentStatus) -> None
    
    # ── 历史 ──
    def get_history(self, key: str, limit: int = 10) -> List[dict]
```

---

## 五、工作流设计

### 5.1 每日分析流水线 (`workflows/daily_analysis.py`)

```
时间: 每日 09:25 (开盘前5分钟)

09:25  MarketWatcher.on_market_open
       ↓ MarketState → StateStore
       ↓ Event: MARKET_OPEN

09:30  Researcher.on_activate(context=MarketState)
       ↓ 调用 stock_search_tool → 技术筛选
       ↓ 调用 news_sentiment_tool → 新闻情感
       ↓ 调用 backtest_tool → 历史回测
       ↓ StockPicks[] → StateStore
       ↓ Event: AGENT_COMPLETE(researcher)

09:35  RiskManager.on_activate(context=MarketState+StockPicks)
       ↓ 调用 kelly_position_tool → 仓位计算
       ↓ 调用 risk_reward_tool → 风险收益比
       ↓ 调用 circuit_breaker_check → 熔断检查
       ↓ 
       ↓ 如果风险收益比 < 2:1 → REJECT → Event: AGENT_REJECT
       ↓   → Orchestrator 通知 Researcher 重新选股（最多3次）
       ↓ 如果通过 → RiskAssessment → StateStore
       ↓ Event: AGENT_COMPLETE(risk_manager)

09:40  Trader.on_activate(context=All)
       ↓ 综合分析 → 生成 TradeAction[]
       ↓ 如果市场不适合 → HOLD → 等待
       ↓ Event: AGENT_COMPLETE(trader)

09:45  交易执行（v4 的 execute_buy/execute_sell）
       ↓ Event: TRADE_EXECUTED

15:00  PerformanceAuditor.on_market_close
       ↓ 计算绩效指标 → 生成日报
       ↓ Event: MARKET_CLOSE
```

### 5.2 实时监控 (`workflows/realtime_monitor.py`)

```
循环: 每10分钟（交易时段内）

1. 获取实时行情 → 与 StateStore 中的止损价比较
2. 如果触发止损 → Event: PRICE_ALERT
3. RiskManager.on_price_alert
   ↓ 调用 circuit_breaker_check → 熔断检查
   ↓ 如果需要卖出 → Trader.on_activate(紧急卖出)
   ↓ Event: TRADE_EXECUTED
4. Dashboard 实时推送（WebSocket）
```

---

## 六、工具集设计

### 6.1 MarketWatcher 的工具 (`tools/market_tools.py`)

```python
class MarketHeatTool(BaseTool):
    """获取市场热度（涨停家数、跌停家数）"""
    name = "market_heat"
    description = "获取A股市场热度指标"

class MarketRegimeTool(BaseTool):
    """判断市场牛熊状态"""
    name = "market_regime"
    description = "判断当前A股市场趋势（牛市/熊市/震荡）"

class SectorRotationTool(BaseTool):
    """行业轮动排名"""
    name = "sector_rotation"
    description = "获取行业板块动量排名"
```

### 6.2 Researcher 的工具 (`tools/stock_tools.py`)

```python
class StockSearchTool(BaseTool):
    """从候选池筛选股票"""
    name = "stock_search"
    description = "根据技术指标从候选池筛选股票"

class TechnicalAnalysisTool(BaseTool):
    """计算技术指标（MA/MACD/RSI/KDJ/布林带）"""
    name = "technical_analysis"
    description = "计算单只股票的技术指标和信号"

class BacktestTool(BaseTool):
    """运行策略回测"""
    name = "backtest"
    description = "对指定股票运行多策略回测"

class NewsSentimentTool(BaseTool):
    """获取财经新闻情感"""
    name = "news_sentiment"
    description = "获取近期财经新闻和情感分析"

class FinancialDataTool(BaseTool):
    """获取基本面数据（PE/PB/净利润增速）"""
    name = "financial_data"
    description = "获取股票基本面财务指标"
```

### 6.3 RiskManager 的工具 (`tools/risk_tools.py`)

```python
class KellyPositionTool(BaseTool):
    """Kelly公式计算最优仓位"""
    name = "kelly_position"
    description = "根据胜率和盈亏比计算最优仓位"

class RiskRewardTool(BaseTool):
    """风险收益比计算"""
    name = "risk_reward"
    description = "计算风险收益比，判断是否值得操作"

class PortfolioRiskTool(BaseTool):
    """组合风险评估"""
    name = "portfolio_risk"
    description = "评估组合整体风险暴露"

class CircuitBreakerCheckTool(BaseTool):
    """熔断器检查"""
    name = "circuit_breaker_check"
    description = "检查是否触发熔断条件"
```

### 6.4 Trader 的工具 (`tools/trade_tools.py`)

```python
class ExecuteBuyTool(BaseTool):
    """执行买入"""
    name = "execute_buy"
    description = "执行买入操作（模拟盘/实盘）"

class ExecuteSellTool(BaseTool):
    """执行卖出"""
    name = "execute_sell"
    description = "执行卖出操作（模拟盘/实盘）"

class SetStopLossTool(BaseTool):
    """设置止损止盈"""
    name = "set_stop_loss"
    description = "设置股票止损止盈价格"

class NotifyTool(BaseTool):
    """通知（微信/Dashboard）"""
    name = "notify"
    description = "发送交易通知"
```

---

## 七、Dashboard 增强

### 新增功能

| 功能 | 说明 | 技术 |
|------|------|------|
| **Agent 状态面板** | 显示每个 Agent 的运行状态、最后输出 | WebSocket |
| **手动触发按钮** | 一键触发分析/回测/紧急卖出 | REST API |
| **交易审批** | Trader 决策需人工确认后执行 | REST API + UI |
| **实时推送** | Agent 完成时实时通知前端 | Socket.IO |
| **Agent 日志** | 查看 Agent 间的对话历史 | REST API |

### WebSocket API

```python
# 新增路由
@app.route('/ws/agent_status')
def agent_status_ws():
    """实时推送 Agent 状态变化"""
    
@app.route('/api/trigger/<workflow>', methods=['POST'])
def trigger_workflow(workflow):
    """手动触发工作流"""
    
@app.route('/api/approve/<trade_id>', methods=['POST'])
def approve_trade(trade_id):
    """审批交易决策"""
```

---

## 八、实施路线图

### Phase 1：框架搭建（Week 1）

| 任务 | 文件 | 依赖 |
|------|------|------|
| 创建 Agent 基类 | `core/agent_base.py` | crewai |
| 创建事件总线 | `core/event_bus.py` | asyncio |
| 创建状态存储 | `core/state_store.py` | sqlite3 |
| 创建工具注册表 | `core/tool_registry.py` | crewai-tools |
| 创建编排器骨架 | `core/orchestrator.py` | 上述全部 |

### Phase 2：工具封装（Week 1-2）

| 任务 | 文件 | 数据源 |
|------|------|--------|
| 市场数据工具 | `tools/market_tools.py` | data_fetcher.py |
| 股票搜索工具 | `tools/stock_tools.py` | data_fetcher.py + ti.py |
| 风控计算工具 | `tools/risk_tools.py` | risk_manager.py |
| 交易执行工具 | `tools/trade_tools.py` | portfolio_tracker.py |
| 通知工具 | `tools/notify_tools.py` | wechat_notifier.py |

### Phase 3：Agent 重构（Week 2）

| 任务 | 文件 | 工具 |
|------|------|------|
| MarketWatcher | `agents/market_watcher.py` | market_tools |
| Researcher | `agents/researcher.py` | stock_tools |
| RiskManager | `agents/risk_manager.py` | risk_tools + REJECT |
| Trader | `agents/trader.py` | trade_tools + HOLD |
| PerformanceAuditor | `agents/performance_auditor.py` | 新增 |

### Phase 4：工作流集成（Week 2-3）

| 任务 | 文件 | 说明 |
|------|------|------|
| 每日分析流 | `workflows/daily_analysis.py` | 替代 crew.py |
| 实时监控流 | `workflows/realtime_monitor.py` | 替代 run_virtual_v4.py |
| 手动触发流 | `workflows/manual_trigger.py` | Dashboard 介入 |

### Phase 5：Dashboard 增强（Week 3）

| 任务 | 文件 | 说明 |
|------|------|------|
| WebSocket 推送 | `web/websocket.py` | Socket.IO |
| Agent 状态面板 | `templates/index.html` | 前端改造 |
| 交易审批 UI | `templates/index.html` | 交互组件 |
| 统一入口 | `main.py` | 合并所有启动模式 |

---

## 九、关键设计决策

### Q: 为什么不直接用 CrewAI 的 hierarchical 模式？

**A**: CrewAI 的 `Process.hierarchical` 使用一个 Manager Agent 来分配任务，但它：
1. Manager 本身消耗大量 token（每次都要理解全部上下文）
2. 无法支持 REJECT/HOLD 等自定义反馈循环
3. 无法与外部事件系统集成
4. 不支持工具调用结果的持久化

我们保留 CrewAI 作为 **单 Agent 执行引擎**（每个 Agent 用 CrewAI Agent + Tools），但用自建的 Orchestrator 来编排多 Agent 协作。

### Q: 为什么用 SQLite 而不是 Redis？

**A**: 
1. 项目已经用 JSON 文件存储，SQLite 是最自然的升级路径
2. 单机部署，不需要 Redis 的分布式特性
3. SQLite 支持 WAL 模式，读写并发足够
4. 未来如果需要多机部署，可以替换为 Redis

### Q: 为什么不选 AutoGen？

**A**: 
1. 项目已经依赖 CrewAI，重写成本高
2. AutoGen 的对话式编排更适合研究/探索，不适合生产级的定时任务
3. CrewAI 的 Tool 系统更成熟，与 LangChain生态集成更好
4. 我们需要的核心能力（反馈循环、事件驱动）是编排层的需求，不是 Agent 框架的需求

### Q: v3(CrewAI) 和 v4(virtual_v4) 如何合并？

**A**: 
- v3 的 `crew.py:run_daily_analysis()` → `workflows/daily_analysis.py`
- v4 的 `run_virtual_v4.py:run_once()` → `workflows/realtime_monitor.py`
- 两者的共同数据层（portfolio_tracker, data_fetcher, risk_manager）保持不变
- 编排器统一调度两个工作流，根据时间/事件触发

---

## 十、风险与缓解

| 风险 | 缓解 |
|------|------|
| CrewAI 版本兼容性 | 锁定 `crewai>=1.0.0`，基类封装隔离 |
| LLM API 调用成本 | 工具先执行计算 → 只把结果给 LLM → 减少 token |
| 编排器复杂度 | 先实现最简版（线性+REJECT），再逐步增加 |
| 交易执行安全 | Trader 默认只生成建议 → 人工审批 → 可配置自动执行 |
| 状态存储一致性 | SQLite WAL + 事务 + 写入锁 |

---

## 附录：dependencies 更新

```txt
# requirements.txt 新增
crewai>=1.0.0
crewai-tools>=1.0.0
flask-socketio>=5.3.0      # WebSocket
python-socketio>=5.10.0    # Socket.IO client
eventlet>=0.36.0           # async server
```