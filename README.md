# Stock CrewAI - 股票虚拟盘自动交易系统

一个基于技术分析和风险管理的 A股虚拟盘自动交易系统，支持自动化运行、技术指标分析、止损止盈管理。

## ✨ 功能特性

### 核心功能
- 🤖 **全自动交易**：循环模式，每10分钟自动执行（交易时段）
- 📊 **技术分析**：MACD、布林带、RSI、KDJ 等多种技术指标
- 🎯 **智能选股**：基于技术评分 + 市场状态（牛熊市识别）
- 🛡️ **风险管理**：止损-8%、止盈+20%、仓位控制（单只≤20%）
- 📈 **回测框架**：支持历史数据回测验证策略
- 🤖 **LLM分析**：集成 AI 情感分析（可选）
- 📱 **微信通知**：交易信号实时推送到微信（可选）

### 数据源
- 📡 **实时行情**：新浪财经 API（快速可靠）
- � historical **历史数据**：腾讯财经 API（支持A股完整历史）
- 🚫 **已弃用**：akshare（限流严重）

## 🚀 快速开始

### 1. 安装依赖
```bash
pip install -r requirements.txt
```

### 2. 运行虚拟盘
```bash
# 单次运行
python run_virtual_v3.py

# 循环模式（交易时段每10分钟自动执行）
python run_virtual_v3.py --loop
```

### 3. 查看持仓
```bash
python performance_report.py
```

## 📁 项目结构

```
stock-crewai/
├── run_virtual_v3.py          # 主程序（推荐使用）
├── portfolio_tracker.py       # 持仓管理（买卖/止损止盈）
├── data_fetcher.py            # 数据获取（新浪+腾讯）
├── technical_indicators.py    # 技术指标计算+信号生成
├── strategy_momentum.py       # 行业轮动+动量策略
├── backtest.py                # 回测框架
├── llm_analyst.py            # LLM分析模块
├── wechat_notifier.py        # 微信通知
├── performance_report.py      # 绩效报告
├── recommendation_tracker.py  # 推荐追踪
├── config.py                  # 配置文件
├── portfolio.json             # 持仓数据（不提交到git）
└── history/                  # 运行日志（不提交到git）
```

## ⚙️ 配置说明

### 交易参数（可在代码中修改）
```python
# run_virtual_v3.py
STOP_LOSS = -0.08        # 止损 -8%
TAKE_PROFIT = 0.20       # 止盈 +20%
MAX_POSITION_RATIO = 0.20 # 单只股票最大仓位 20%
INITIAL_CASH = 100000     # 初始资金 10万元
```

### A股候选池
默认35只沪深大盘蓝筹股（可在 `run_virtual_v3.py` 的 `STOCK_POOL` 中修改）

## 📊 使用场景

### 场景1：单次运行（测试策略）
```bash
python run_virtual_v3.py
```

### 场景2：循环模式（自动化交易）
```bash
python run_virtual_v3.py --loop
```
- 交易时段（09:30-11:30, 13:00-15:00）每10分钟自动执行
- 非交易时段自动等待
- 按 `Ctrl+C` 停止

### 场景3：Windows 任务计划（后台运行）
1. 编辑 `launch_virtual.bat`（设置项目路径）
2. 以管理员运行 `install_task.ps1` 安装任务计划
3. 每天交易时段自动启动

### 场景4：回测验证
```bash
python backtest.py --stock 600519 --start 20240101 --end 20241231
```

## 🛡️ 风险警告

⚠️ **重要声明**：
- 本项目为 **虚拟盘模拟**，不涉及真实资金
- 策略仅供参考，**不构成投资建议**
- 股市有风险，投资需谨慎
- 实际交易前请充分验证策略有效性

## 📝 更新日志

### v1.0.0 (2026-05-21)
- ✅ 初始版本发布
- ✅ 修复0元止损 Bug（新浪API数据质量问题）
- ✅ 支持新浪实时行情 + 腾讯历史数据
- ✅ 技术指标分析（MACD/布林带/RSI/KDJ）
- ✅ 风险管理（止损止盈/仓位控制）
- ✅ 自动化交易（循环模式）
- ✅ 微信通知（可选）
- ✅ LLM分析（可选）

## 🤝 贡献

欢迎提交 Issue 和 Pull Request！

## 📄 License

MIT License

## 🙏 致谢

- 新浪财经 API（实时行情）
- 腾讯财经 API（历史数据）
- akshare（已弃用，感谢曾经的付出）

---

**⭐ 如果这个项目对你有帮助，请给个 Star！**
