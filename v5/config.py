"""
stock-crewai v5.0 配置文件
基于 LM Studio 本地模型 (Gemma 4 12B Coder)
"""

# ── LM Studio 本地模型配置 ──
LM_STUDIO_BASE_URL = "http://localhost:1234/v1"
LM_STUDIO_API_KEY = "lm-studio"  # 占位符，LM Studio 不校验

# 模型配置 - 分析师用 chat 模式，推理用 reasoner 模式
# LM Studio 只加载一个模型，两个角色共用
LLM_CONFIG = {
    "analyst": {
        "model": "gemma-4-12b-coder",  # LM Studio 中加载的模型名
        "base_url": LM_STUDIO_BASE_URL,
        "api_key": LM_STUDIO_API_KEY,
        "temperature": 0.3,   # 分析需要确定性
        "max_tokens": 2048,
    },
    "reasoner": {
        "model": "gemma-4-12b-coder",
        "base_url": LM_STUDIO_BASE_URL,
        "api_key": LM_STUDIO_API_KEY,
        "temperature": 0.6,   # 辩论需要一些创造性
        "max_tokens": 4096,
    },
}

# ── 辩论配置 ──
DEBATE_ROUNDS = 2  # 多空辩论轮数

# ── 股票池 ──
STOCK_POOL = [
    # 科技
    "000333",  # 美的集团
    "000725",  # 京东方A
    "002415",  # 海康威视
    "002475",  # 立讯精密
    "300059",  # 东方财富
    "300750",  # 宁德时代
    "300760",  # 迈瑞医疗
    "603259",  # 药明康德
    "603986",  # 兆易创新
    "688981",  # 中芯国际
    # 消费
    "000858",  # 五粮液
    "600519",  # 贵州茅台
    "600887",  # 伊利股份
    "603288",  # 海天味业
    # 金融
    "601318",  # 中国平安
    "601398",  # 工商银行
    "601628",  # 中国人寿
    "601939",  # 建设银行
    # 新能源
    "002594",  # 比亚迪
    "601012",  # 隆基绿能
    # 医药
    "000538",  # 云南白药
    "600276",  # 恒瑞医药
    # 军工
    "000768",  # 中航西飞
    "600036",  # 招商银行
    "600104",  # 上汽集团
    # 半导体
    "002049",  # 紫光国微
    "300223",  # 北京君正
    "300661",  # 圣邦股份
    "688012",  # 中微公司
    "688041",  # 海光信息
    # AI/算力
    "002230",  # 科大讯飞
    "300474",  # 景嘉微
    "688256",  # 寒武纪
    # 更多
    "000001",  # 平安银行
    "000063",  # 中兴通讯
    "000100",  # TCL科技
    "000338",  # 潍柴动力
    "000402",  # 金融街
    "000568",  # 泸州老窖
    "000651",  # 格力电器
    "002007",  # 华兰生物
    "002027",  # 分众传媒
    "002230",  # 科大讯飞
    "002241",  # 歌尔股份
    "002304",  # 洋河股份
    "002466",  # 天齐锂业
    "002493",  # 荣盛石化
    "300015",  # 爱尔眼科
    "300124",  # 汇川技术
    "600009",  # 上海机场
]

# ── 扫描间隔 ──
SCAN_INTERVAL_MINUTES = 10  # 循环模式间隔

# ── ChromaDB 配置 ──
CHROMA_DB_PATH = "./v5/chroma_db"
CHROMA_COLLECTION = "trading_decisions"

# ── 风控参数 ──
MAX_POSITION_RATIO = 0.20    # 单只最大仓位 20%
MAX_TOTAL_POSITIONS = 5      # 最大持仓 5 只
MIN_RISK_REWARD = 2.0        # 最低风险收益比
STOP_LOSS_PCT = 0.05         # 默认止损 5%
