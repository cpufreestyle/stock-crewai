# 贡献指南

感谢你考虑为 Stock CrewAI 做出贡献！本文档将帮助你开始。

## 📋 目录

- [行为准则](#行为准则)
- [快速开始](#快速开始)
- [开发环境](#开发环境)
- [开发流程](#开发流程)
- [代码规范](#代码规范)
- [提交规范](#提交规范)
- [测试](#测试)
- [文档](#文档)
- [问题反馈](#问题反馈)

## 行为准则

我们期望所有贡献者遵守以下原则：

- **尊重**：尊重他人的观点和贡献
- **包容**：欢迎不同背景的开发者
- **专业**：保持专业和友好的交流
- **开放**：接受建设性的批评和建议

## 快速开始

### 1. Fork 项目

点击 GitHub 页面右上角的 "Fork" 按钮。

### 2. 克隆你的 Fork

```bash
git clone https://github.com/YOUR_USERNAME/stock-crewai.git
cd stock-crewai
```

### 3. 添加上游仓库

```bash
git remote add upstream https://github.com/cpufreestyle/stock-crewai.git
```

### 4. 创建开发分支

```bash
git checkout -b feature/your-feature-name
```

## 开发环境

### 环境要求

- Python 3.10+
- Git
- SQLite3（内置于 Python）

### 安装依赖

```bash
# 创建虚拟环境（推荐）
python -m venv venv

# 激活虚拟环境
# Windows:
venv\Scripts\activate
# macOS/Linux:
source venv/bin/activate

# 安装依赖
pip install -r requirements.txt
```

### 配置环境变量

```bash
cp .env.example .env
# 编辑 .env 文件，配置你的 API Key
```

## 开发流程

### 1. 保持本地分支最新

```bash
git fetch upstream
git checkout main
git merge upstream/main
```

### 2. 创建功能分支

```bash
git checkout -b feature/your-feature-name
```

### 3. 开发与测试

```bash
# 开发代码
# ...

# 运行测试
pytest tests/

# 运行特定测试
pytest tests/test_indicators.py -v
```

### 4. 提交代码

```bash
git add .
git commit -m "feat: 添加新功能"
```

### 5. 推送分支

```bash
git push origin feature/your-feature-name
```

### 6. 创建 Pull Request

1. 打开你的 Fork 仓库
2. 点击 "Compare & pull request"
3. 填写 PR 描述
4. 提交 PR

## 代码规范

### Python 代码风格

- 遵循 **PEP 8** 规范
- 使用 **Black** 格式化代码
- 使用 **isort** 整理 import

```bash
# 安装格式化工具
pip install black isort

# 格式化代码
black .
isort .
```

### 命名规范

| 类型 | 规范 | 示例 |
|------|------|------|
| 变量 | snake_case | `stock_code`, `profit_loss` |
| 函数 | snake_case | `get_positions()`, `calculate_rsi()` |
| 类 | PascalCase | `PortfolioTracker`, `DataFetcher` |
| 常量 | UPPER_SNAKE | `MAX_POSITION`, `STOP_LOSS` |
| 模块 | snake_case | `data_fetcher.py`, `technical_indicators.py` |

### 文档字符串

所有公共函数和类必须包含文档字符串：

```python
def calculate_rsi(prices: list, period: int = 14) -> float:
    """
    计算相对强弱指数 (RSI)
    
    Args:
        prices: 价格列表
        period: 计算周期，默认14天
    
    Returns:
        RSI 值 (0-100)
    
    Example:
        >>> prices = [100, 102, 101, 103, 105]
        >>> calculate_rsi(prices, 14)
        65.5
    """
    pass
```

## 提交规范

### 提交信息格式

```
<type>(<scope>): <subject>

<body>

<footer>
```

### Type 类型

| Type | 说明 |
|------|------|
| feat | 新功能 |
| fix | Bug 修复 |
| docs | 文档更新 |
| style | 代码格式（不影响功能） |
| refactor | 重构（不是新功能或修复） |
| perf | 性能优化 |
| test | 测试相关 |
| chore | 构建/工具相关 |

### 示例

```bash
# 新功能
git commit -m "feat(strategy): 添加动量策略支持"

# Bug 修复
git commit -m "fix(trader): 修复止损逻辑错误"

# 文档更新
git commit -m "docs(readme): 更新安装说明"
```

## 测试

### 运行测试

```bash
# 运行所有测试
pytest

# 运行特定测试
pytest tests/test_indicators.py -v

# 查看详细输出
pytest -vv

# 生成覆盖率报告
pytest --cov=. --cov-report=html
```

### 编写测试

```python
# tests/test_indicators.py
import pytest
from technical_indicators import calculate_rsi, calculate_macd

def test_rsi_normal():
    """测试 RSI 正常计算"""
    prices = [100, 102, 101, 103, 105, 104, 106]
    rsi = calculate_rsi(prices)
    assert 0 <= rsi <= 100

def test_macd_signal():
    """测试 MACD 信号"""
    prices = [100] * 50
    macd, signal, histogram = calculate_macd(prices)
    assert macd is not None
    assert signal is not None
```

## 文档

### 更新文档

- 公共 API 必须有文档字符串
- 重要更改必须更新 README.md
- 新功能必须添加使用示例

### 构建文档

（如果项目有文档构建系统）

```bash
# 安装文档工具
pip install mkdocs

# 本地预览
mkdocs serve

# 构建 HTML
mkdocs build
```

## 问题反馈

### 创建 Issue

在创建 Issue 时，请包含：

1. **问题描述**：清晰描述问题
2. **复现步骤**：如何复现问题
3. **预期行为**：期望的行为
4. **实际行为**：实际的行为
5. **环境信息**：
   - 操作系统
   - Python 版本
   - 相关依赖版本

### Issue 模板

```markdown
## 问题描述


## 复现步骤


## 预期行为


## 实际行为


## 环境信息

- OS: 
- Python: 
- 相关依赖: 
```

## 许可证

通过贡献代码，你同意你的贡献将在 MIT 许可证下发布。

## 联系方式

- GitHub Issues: https://github.com/cpufreestyle/stock-crewai/issues
- 邮箱: (在你的 GitHub 资料中查看)

---

**再次感谢你的贡献！** 🎉
