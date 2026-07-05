"""
TradingAgents v5 配置
DeepSeek LLM + 2轮多空辩论 + ChromaDB 记忆
"""
import os
from pathlib import Path

# ── 路径 ──
V5_ROOT = Path(__file__).parent
PROJECT_ROOT = V5_ROOT.parent
DATA_DIR = V5_ROOT / "data"
MEMORY_DIR = DATA_DIR / "trading_memory"

# ── LLM 配置 (DeepSeek) ──
LLM_CONFIG = {
    # 分析层用 chat 模型（便宜、快）
    "analyst": {
        "model": "deepseek-chat",
        "api_key": os.getenv("DEEPSEEK_API_KEY", ""),
        "base_url": "https://api.deepseek.com/v1",
        "temperature": 0.3,
        "max_tokens": 2048,
    },
    # 决策层用 reasoner 模型（推理强）
    "reasoner": {
        "model": "deepseek-reasoner",
        "api_key": os.getenv("DEEPSEEK_API_KEY", ""),
        "base_url": "https://api.deepseek.com/v1",
        "temperature": 0.1,
        "max_tokens": 4096,
    },
}

# ── 辩论配置 ──
DEBATE_ROUNDS = 2  # 多空辩论轮数

# ── 数据源 ──
DATA_SOURCES = {
    # 保留原有新浪API（行情）
    "sina": {
        "realtime_url": "http://hq.sinajs.cn/",
        "enabled": True,
    },
    # 新增 Tushare（基本面+新闻）
    "tushare": {
        "token": os.getenv("TUSHARE_TOKEN", ""),
        "enabled": True,
    },
    # AkShare 备用
    "akshare": {
        "enabled": True,
    },
}

# ── 候选股票池 ──
STOCK_POOL = [
    # 沪深300成分股（子集，与v4保持一致）
    "000333", "000425", "000651", "000858", "002415",
    "002594", "002714", "300015", "300033", "300059",
    "300433", "300750", "600009", "600016", "600028",
    "600030", "600036", "600048", "600050", "600089",
    "600104", "600196", "600276", "600406", "600438",
    "600519", "600585", "600588", "600690", "600745",
    "600837", "600887", "601006", "601012", "601318",
    "601398", "601601", "601628", "601668", "601728",
    "601766", "601800", "601818", "601857", "601888",
    "601919", "603259", "603288", "603501", "603799",
]

# ── 运行参数 ──
SCAN_INTERVAL_MINUTES = 10  # 扫描间隔
MAX_POSITIONS = 5           # 最大持仓
MAX_DEBATE_TOKENS = 4096   # 辩论最大 token

# ── 兼容 v4 的配置映射 ──
# 导入原有配置
import sys
sys.path.insert(0, str(PROJECT_ROOT))
