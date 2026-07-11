#!/bin/bash
# ── stock-crewai v5.0.0 发布脚本 ──
# 用法: bash release.sh
set -e

REPO_DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$REPO_DIR"

VERSION="v5.0.0"
REMOTE="origin"
BRANCH="v5-integration"

echo "══════════════════════════════════════════"
echo "  stock-crewai $VERSION 发布"
echo "══════════════════════════════════════════"

# 1. 检查 git 状态
echo ""
echo "[1/6] 检查 git 状态..."
git status --short

# 2. 暂存所有变更
echo ""
echo "[2/6] 暂存变更..."
git add -A

# 3. 提交
echo ""
echo "[3/6] 提交..."
git commit -m "fix(v5): 修复6个关键bug + 精简代码

Bug 修复:
- config.py: 添加 CIRCUIT_BREAKER_* 常量，修复 circuit_breaker.py ImportError
- portfolio_tracker.py: set_stop_loss 返回 dict 而非 None，修复 TypeError
- data_fetcher.py: get_market_regime 兼容中文列名'收盘'和英文'close'
- tools/stock_tools.py: StockSearchTool key 从'5日涨跌'改为'5日涨跌%'
- tools/risk_tools.py: 添加中文 key (止损价/买入股数/是否可行) 匹配 agent 读取
- tools/stock_tools.py: TechnicalAnalysisTool 返回中文 key (趋势/RSI) 匹配 researcher

代码精简:
- data_fetcher.py: _STOCK_NAME 从手动50行字典改为自动生成
- 删除根目录 agents.py (死代码，与 agents/ 包重复)
- 删除 agents_pkg/ 目录 (agents/ 的旧副本，无引用)" || true

# 4. 推送到远程
echo ""
echo "[4/6] 推送到 $REMOTE/$BRANCH..."
git push -u "$REMOTE" "$BRANCH"

# 5. 创建标签
echo ""
echo "[5/6] 创建标签 $VERSION..."
git tag -a "$VERSION" -m "v5.0.0 - 多Agent协作系统 + Bug修复

## 新特性
- v5 多 Agent 协作架构 (EventBus + StateStore + Orchestrator)
- 5个专业 Agent: MarketWatcher/Researcher/RiskManager/Trader/PerformanceAuditor
- 实时监控工作流 + 定时调度器
- Web Dashboard

## Bug 修复
- circuit_breaker 导入失败 (ImportError)
- set_stop_loss 返回 None 导致 TypeError
- get_market_regime 列名不匹配 (KeyError)
- StockSearchTool 涨跌幅 key 错误导致筛选失效
- risk_tools/stock_tools 返回英文 key 但 agent 读中文 key
- TechnicalAnalysisTool trend 返回英文但 researcher 期望中文

## 代码精简
- 删除 _STOCK_NAME 重复字典 (50行 → 1行)
- 删除根目录 agents.py (死代码)
- 删除 agents_pkg/ 目录 (废弃副本)"

git push "$REMOTE" "$VERSION"

# 6. 创建 GitHub Release
echo ""
echo "[6/6] 创建 GitHub Release..."
if command -v gh &> /dev/null; then
    gh release create "$VERSION" \
        --title "stock-crewai v5.0.0" \
        --notes "## 🐛 Bug 修复 (6个)

| # | 文件 | 问题 | 修复 |
|---|------|------|------|
| 1 | \`config.py\` | \`circuit_breaker.py\` 导入不存在的常量 → \`ImportError\` | 添加 \`CIRCUIT_BREAKER_*\` 常量 |
| 2 | \`portfolio_tracker.py\` | \`set_stop_loss\` 返回 \`None\` → \`TypeError\` | 改为返回 \`dict\` |
| 3 | \`data_fetcher.py\` | \`get_market_regime\` 用 \`\"close\"\` 但数据源返回 \`\"收盘\"\` → \`KeyError\` | 自动检测列名 |
| 4 | \`tools/stock_tools.py\` | \`StockSearchTool\` 用 \`\"5日涨跌\"\` 但实际 key 是 \`\"5日涨跌%\"\` → 筛选失效 | 修正 key 名 |
| 5 | \`tools/risk_tools.py\` | 返回英文 key 但 \`risk_manager_agent\` 读中文 key → 风控数据全空 | 添加中文 key |
| 6 | \`tools/stock_tools.py\` | \`TechnicalAnalysisTool\` 返回 \`\"bullish\"\` 但 researcher 期望 \`\"多头\"\` → 评分失效 | 改为中文 key |

## 🧹 代码精简 (3项)

- **\`data_fetcher.py\`**: 删除 50 行手动维护的 \`_STOCK_NAME\` 字典，改为 \`{s[\"code\"]: s[\"name\"] for s in A_SHARE_POOL}\` 一行自动生成
- **删除 \`agents.py\`**: 根目录死代码，Python 包 \`agents/\` 优先级更高，此文件从未被导入
- **删除 \`agents_pkg/\`**: \`agents/\` 的旧版副本（6个文件），无任何代码引用" \
        --target v5-integration
    echo "✅ GitHub Release 创建成功！"
else
    echo "⚠️  gh CLI 未安装，请手动创建 Release:"
    echo "   https://github.com/cpufreestyle/stock-crewai/releases/new?tag=$VERSION"
fi

echo ""
echo "══════════════════════════════════════════"
echo "  ✅ $VERSION 发布完成！"
echo "══════════════════════════════════════════"
