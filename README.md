# Stock CrewAI - 多智能体量化交易系统

基于 CrewAI 框架的 A股智能交易系统，集成 8 个专业 Agent 协同工作，实现从市场分析到交易执行的全自动化流程。

## ✨ 核心特性

### 🤖 8 智能体协同架构 (v4.2.0)
- **MarketWatcher** - 市场观察员：判断牛熊市、识别热门板块
- **SentimentAgent** - 情绪分析师：市场情绪评分、拐点检测
- **StockResearchAgent** - 研究员：选股、基本面+技术面分析
- **RiskAgent** - 风控专家：风险评估、仓位管理
- **PortfolioManagerAgent** - 组合经理：持仓再平衡、行业配置优化
- **TradingAgent** - 交易员：最终交易决策
- **BacktestAgent** - 回测分析师：策略历史验证、指标评分
- **ReviewAgent** - 审核专家：合规审核、最终放行

### 功能亮点
- 📊 **全自动化流程**：市场分析 → 选股 → 风控 → 交易 → 审核
- 🧠 **LLM 驱动**：集成 LM Studio 本地推理 (Qwen3.6-27B)
- 📈 **回测验证**：夏普比率、最大回撤、胜率等多维度评分
- 🛡️ **风险控制**：行业集中度 ≤40%、现金保留 10-20%
- 📱 **微信通知**：交易信号实时推送（可选）
- 🔄 **持仓管理**：动态再平衡、止损止盈

## 🚀 快速开始

### 1. 安装依赖
```bash
pip install -r requirements.txt
```

### 2. 配置环境
创建 `.env` 文件：
```env
# LM Studio (本地推理)
LM_STUDIO_BASE_URL=http://172.16.20.242:1234/v1
LM_STUDIO_MODEL=qwen3.6-27b-tachibana-agent-i1

# 策场 API (交易执行)
CEMARKET_API_KEY=your_api_key_here

# 微信通知 (可选)
WECHAT_WEBHOOK_URL=your_webhook_url_here
```

### 3. 运行系统
```bash
# 单次运行
python crew.py

# 带回测
python crew.py --backtest
```

**预期执行时间**: 4-6 分钟（8 个 Agent 顺序执行）

## 📋 工作流程

```
┌─────────────────┐
│  MarketWatcher  │ 市场观察员：牛熊判断、板块轮动
└────────┬────────┘
         │
         ▼
┌─────────────────┐
│ SentimentAgent  │ 情绪分析师：情绪评分(0-100)、拐点检测
└────────┬────────┘
         │
         ▼
┌─────────────────┐
│  StockResearch  │ 研究员：选股、基本面+技术面
└────────┬────────┘
         │
         ▼
┌─────────────────┐
│   RiskAgent     │ 风控专家：风险评估、仓位建议
└────────┬────────┘
         │
         ▼
┌─────────────────┐
│ PortfolioMgr    │ 组合经理：持仓再平衡、行业配置
└────────┬────────┘
         │
         ▼
┌─────────────────┐
│  TradingAgent   │ 交易员：最终交易决策
└────────┬────────┘
         │
         ▼
┌─────────────────┐
│  BacktestAgent  │ 回测分析师：策略验证、指标评分
└────────┬────────┘
         │
         ▼
┌─────────────────┐
│   ReviewAgent   │ 审核专家：合规审核、最终放行
└─────────────────┘
```

## 📁 项目结构

```
stock-crewai/
├── crew.py                 # 主编排（8 Agent 工作流）
├── agents.py               # Agent 定义（8 个 Agent）
├── tasks.py                # 任务定义（8 个任务）
├── config.py               # 配置文件
├── portfolio_tracker.py    # 持仓管理
├── data_fetcher.py         # 数据获取（新浪+腾讯）
├── backtest.py             # 回测框架
├── recommendation_tracker.py # 推荐追踪
├── risk_manager.py         # 风险管理
├── wechat_notifier.py     # 微信通知
└── requirements.txt       # 依赖清单
```

## ⚙️ 配置说明

### 交易参数（config.py）
```python
# 风险控制
MAX_POSITION_RATIO = 0.20      # 单只股票最大仓位 20%
INDUSTRY_LIMIT = 0.40          # 单行业最大占比 40%
CASH_RESERVE = 0.15            # 现金保留比例 10-20%

# 止损止盈
STOP_LOSS = -0.08              # 止损 -8%
TAKE_PROFIT = 0.20             # 止盈 +20%

# 回测标准
MIN_SHARPE_RATIO = 1.0         # 最低夏普比率
MAX_DRAWDOWN = 0.20            # 最大回撤容忍度
MIN_WIN_RATE = 0.40            # 最低胜率
```

## 📊 回测评分系统

BacktestAgent 使用 0-10 分评分系统：

| 指标 | 权重 | 评分标准 |
|------|------|---------|
| 夏普比率 | 30% | ≥1.5: 满分 / <1.0: 0分 |
| 最大回撤 | 25% | ≤15%: 满分 / >30%: 0分 |
| 胜率 | 20% | ≥50%: 满分 / <30%: 0分 |
| 盈亏比 | 15% | ≥2:1: 满分 / <1:1: 0分 |
| 年化收益 | 10% | ≥20%: 满分 / <5%: 0分 |

**执行标准**：
- ✅ **通过**：评分 ≥ 7 分，建议执行
- ⚠️ **谨慎**：评分 5-6 分，需要调整参数
- ❌ **拒绝**：评分 < 5 分，策略不可行

## 🛡️ 风险管理原则

### ReviewAgent 审核标准（5 条）
1. **仓位检查**：单只 ≤20%、单行业 ≤40%
2. **止损设置**：必须设置止损价
3. **市场适配**：策略是否适应当前市场状态
4. **理由充分**：是否有合理的研究支持
5. **风险收益比**：潜在收益是否覆盖风险

**审核结果**：
- ✅ 通过 → 执行交易
- ❌ 拒绝 → 保存 `result_rejected.md` + 微信通知

## 📈 使用场景

### 场景 1：单次分析（测试策略）
```bash
python crew.py
```

### 场景 2：定时运行（cron/任务计划）
```bash
# Linux/Mac
crontab -e
# 添加：0 9,13 * * 1-5 cd /path/to/stock-crewai && python crew.py

# Windows
# 使用任务计划程序，每日 09:00 和 13:00 执行
```

### 场景 3：回测验证
```bash
python crew.py --backtest
```

### 场景 4：查看持仓
```bash
python performance_report.py
```

## 📝 更新日志

### v4.2.0 (2026-06-10) - Complete Quantitative Trading System
- ✅ **重大升级**：5 Agent → 8 Agent
- ✅ **新增 SentimentAgent**：情绪评分、拐点检测
- ✅ **新增 PortfolioManagerAgent**：持仓再平衡、行业配置
- ✅ **新增 BacktestAgent**：策略回测验证、指标评分
- ✅ **新增 ReviewAgent**：合规审核、否决权
- ✅ **12 步骤工作流**：全自动化交易流程
- ✅ **322 行新代码**：agents.py +136, tasks.py +120, crew.py +76

### v4.1.1 (2026-06-09)
- ✅ 切换 LM Studio 直连
- ✅ 清理临时文件
- ✅ 添加自启脚本

### v4.0.0 (2026-06-08)
- ✅ 集成 CrewAI 框架
- ✅ 5 Agent 基础架构
- ✅ 市场分析 + 选股 + 风控 + 交易 + 审核

### v3.0.0 (2026-06-05)
- ✅ 策场 API 集成
- ✅ A股/美股交易验证
- ✅ 微信告警解耦架构

### v2.0.0 (2026-06-01)
- ✅ 虚拟盘系统
- ✅ 技术指标分析
- ✅ 风险管理

### v1.0.0 (2026-05-21)
- ✅ 初始版本
- ✅ 基础选股策略

## 🤝 贡献

欢迎提交 Issue 和 Pull Request！

**开发指南**：
1. Fork 本仓库
2. 创建特性分支 (`git checkout -b feature/AmazingFeature`)
3. 提交更改 (`git commit -m 'Add some AmazingFeature'`)
4. 推送到分支 (`git push origin feature/AmazingFeature`)
5. 开启 Pull Request

## 📄 License

MIT License

## 🙏 致谢

- [CrewAI](https://github.com/crewAIInc/crewAI) - 多智能体框架
- [LM Studio](https://lmstudio.ai/) - 本地 LLM 推理
- 新浪财经 API - 实时行情
- 腾讯财经 API - 历史数据

---

## ⚠️ 风险警告

**重要声明**：
- 本项目为 **研究与学习目的**，不构成投资建议
- 股市有风险，投资需谨慎
- 实际交易前请充分验证策略有效性
- 过去业绩不代表未来表现
- 使用者需自行承担所有风险

---

**⭐ 如果这个项目对你有帮助，请给个 Star！**

**🚀 v4.2.0 - 完整的量化交易系统，8 智能体协同工作！**
