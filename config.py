"""
策略参数集中管理配置文件
所有策略相关参数统一在此定义，方便调整和回测
"""

# ========================
# 持仓管理
# ========================
MAX_POSITIONS = 5              # 最大持仓数量
MAX_POSITION_RATIO = 0.80      # 最大仓位比例（占总资产）
SINGLE_POSITION_RATIO = 0.20   # 单只股票最大仓位比例

# ========================
# 止损止盈
# ========================
STOP_LOSS_RATIO = 0.92         # 固定止损线（买入价 * 0.92 = -8%）
TAKE_PROFIT_RATIO = 1.20       # 固定止盈线（买入价 * 1.20 = +20%）
ATR_STOP_MULTIPLIER = 2        # ATR 止损倍数（价格 - 2*ATR）
ATR_PROFIT_MULTIPLIER = 3      # ATR 止盈倍数（价格 + 3*ATR）
ATR_HOLDING_DAYS = 3           # 持仓超过此天数启用 ATR 动态止损

# ========================
# 涨幅筛选
# ========================
MIN_CHANGE_PCT = 0             # 最低涨幅（%），0 表示不跌即可
MAX_CHANGE_PCT = 6             # 最高涨幅（%），超过视为追高风险大
GOOD_CHANGE_LOW = 1            # 温和涨幅区间下限（%）
GOOD_CHANGE_HIGH = 4           # 温和涨幅区间上限（%）

# ========================
# 技术评分权重
# ========================
TECH_SCORE_WEIGHTS = {
    "trend": 30,               # 趋势得分权重
    "volume": 20,              # 成交量得分权重
    "change": 20,              # 涨幅得分权重
    "ma_support": 15,          # 均线支撑权重
    "momentum": 15,            # 动量权重
}

MIN_TECH_SCORE = 60            # 最低技术评分（低于此分数不买入）

# ========================
# 风险控制
# ========================
NEAR_TAKE_PROFIT_PCT = 0.90    # 接近止盈线的阈值（止盈利润的 90%）
STOP_LOSS_CHECK_ENABLED = True # 是否启用止损检查
ATR_STOP_LOSS_ENABLED = True   # 是否启用 ATR 动态止损

# ========================
# API 缓存 TTL（秒）
# ========================
CACHE_TTL_REALTIME = 10        # 实时行情缓存
CACHE_TTL_MARKET = 300         # 市场状态缓存
CACHE_TTL_KLINE = 60           # K线数据缓存

# ========================
# 运行周期
# ========================
SCAN_INTERVAL_MINUTES = 10     # 虚拟盘扫描间隔（分钟）
DASHBOARD_REFRESH_SECONDS = 30 # Dashboard 刷新间隔（秒）

# ========================
# 日志
# ========================
LOG_MAX_BYTES = 10 * 1024 * 1024   # 日志文件最大 10MB
LOG_BACKUP_COUNT = 5                # 保留 5 个备份

# ========================
# 文件路径
# ========================
PORTFOLIO_FILE = "portfolio.json"
TRADE_LOG_FILE = "trade_log.json"
NET_VALUE_HISTORY_FILE = "net_value_history.json"

# ========================
# API Key
# ========================
import os
API_KEY = os.getenv("OPENAI_API_KEY") or os.getenv("DASHSCOPE_API_KEY") or ""
API_BASE_URL = os.getenv("OPENAI_BASE_URL", "https://openrouter.ai/api/v1")
