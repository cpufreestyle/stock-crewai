"""
Supermemory 集成模块 — 为 OpenClaw / hermes-agent 提供跨会话记忆

三种使用方式:
1. hermes-agent 插件（已内置）: 配置 SUPERMEMORY_API_KEY 即可启用
2. OpenClaw MCP server: 通过 MCP 协议接入
3. 直接 Python SDK: 用于自定义集成（如 stock-crewai 决策记忆）

本文档同时作为 hermes-agent 和 OpenClaw 的配置指南。
"""

# ── 方式1: hermes-agent 插件配置 ──

HERMES_CONFIG = {
    "步骤": [
        "1. 获取 API key: 访问 https://console.supermemory.ai",
        "2. 配置: hermes config set memory.provider supermemory",
        "3. 设置 key: echo 'SUPERMEMORY_API_KEY=your_key' >> ~/.hermes/.env",
        "4. 重启 hermes-agent",
    ],
    "插件路径": "plugins/memory/supermemory/",
    "功能": [
        "自动召回: 每轮对话前注入相关记忆",
        "自动捕获: 每轮对话后存储清理过的内容",
        "显式工具: supermemory_store / supermemory_search / supermemory_forget",
        "会话结束: 完整对话摄入到 Supermemory 图谱",
        "用户画像: 自动维护用户长期偏好和近期活动",
    ],
}

# ── 方式2: OpenClaw MCP 接入 ──

OPENCLAW_MCP_CONFIG = {
    "name": "supermemory",
    "transport": {
        "type": "stdio",
        "command": "npx",
        "args": ["-y", "@supermemory/mcp-server"],
    },
    "env": {
        "SUPERMEMORY_API_KEY": "your_api_key_here",
    },
    "安装命令": "openclaw mcp add supermemory --stdio npx -y @supermemory/mcp-server --env SUPERMEMORY_API_KEY=xxx",
}

# ── 方式3: 直接 SDK 使用（stock-crewai 决策记忆）──

import os
import logging
from typing import Dict, List, Optional

logger = logging.getLogger("v5.supermemory")

_sm_client = None


def get_supermemory():
    """获取 Supermemory 客户端"""
    global _sm_client
    if _sm_client is None:
        api_key = os.environ.get("SUPERMEMORY_API_KEY")
        if not api_key:
            logger.warning("[Supermemory] no API key found, memory features disabled")
            return None
        from supermemory import Supermemory
        _sm_client = Supermemory(api_key=api_key)
        logger.info("[Supermemory] client initialized")
    return _sm_client


def store_trading_decision(decision: Dict, context: str = ""):
    """将 v5 交易决策存储到 Supermemory"""
    sm = get_supermemory()
    if not sm:
        return
    
    try:
        content = f"""
股票交易决策: {decision.get('stock_code', '')}
操作: {decision.get('action', 'HOLD')}
价格: {decision.get('price', 'N/A')}
置信度: {decision.get('confidence', 0)}
理由: {decision.get('reason', '')}
止损: {decision.get('stop_loss', 'N/A')}
止盈: {decision.get('take_profit', 'N/A')}
上下文: {context}
时间: {__import__('datetime').datetime.now().isoformat()}
"""
        sm.documents.add(
            content=content,
            metadata={
                "type": "trading_decision",
                "stock_code": decision.get("stock_code", ""),
                "action": decision.get("action", ""),
                "container": "stock-crewai",
            }
        )
        logger.info(f"[Supermemory] stored decision for {decision.get('stock_code')}")
    except Exception as e:
        logger.error(f"[Supermemory] store failed: {e}")


def recall_similar_decisions(query: str, limit: int = 5) -> List[Dict]:
    """从 Supermemory 召回相似的历史决策"""
    sm = get_supermemory()
    if not sm:
        return []
    
    try:
        results = sm.search.execute(
            q=query,
            limit=limit,
            container="stock-crewai",
        )
        logger.info(f"[Supermemory] recalled {len(results)} memories for: {query[:50]}")
        return results
    except Exception as e:
        logger.error(f"[Supermemory] recall failed: {e}")
        return []
