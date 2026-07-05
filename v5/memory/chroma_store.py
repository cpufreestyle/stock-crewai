"""
ChromaDB 交易记忆系统
存储每次交易决策的完整上下文，支持相似行情召回
"""
import logging
from typing import Dict, List, Optional
from datetime import datetime

logger = logging.getLogger("v5.memory")


class TradingMemory:
    """交易记忆 - 基于 ChromaDB"""

    def __init__(self, persist_dir: str = None):
        import chromadb
        from v5.config import MEMORY_DIR

        self.persist_dir = persist_dir or str(MEMORY_DIR)
        self.client = chromadb.PersistentClient(path=self.persist_dir)
        self.collection = self.client.get_or_create_collection(
            name="trading_decisions",
            metadata={"description": "stock-crewai v5 交易决策记忆"}
        )
        logger.info(f"[Memory] ChromaDB initialized at {self.persist_dir}")

    def store_decision(
        self,
        stock_code: str,
        stock_name: str,
        decision: str,           # BUY / SELL / HOLD
        market_context: str,     # 行情描述
        analysis_summary: str,   # 分析师+辩论摘要
        risk_assessment: str,    # 风控评估
        volume: int = 0,
        price: float = 0,
        outcome: Optional[str] = None,  # 30天后填入实际收益
    ) -> str:
        """存储一条交易决策"""
        doc_id = f"{stock_code}_{datetime.now().strftime('%Y%m%d_%H%M%S')}"

        document = (
            f"股票: {stock_name}({stock_code})\n"
            f"决策: {decision}\n"
            f"时间: {datetime.now().isoformat()}\n"
            f"行情: {market_context}\n"
            f"分析: {analysis_summary}\n"
            f"风控: {risk_assessment}\n"
            f"数量: {volume}, 价格: {price}\n"
            f"结果: {outcome or '待定'}"
        )

        self.collection.add(
            documents=[document],
            metadatas=[{
                "stock": stock_code,
                "name": stock_name,
                "decision": decision,
                "date": datetime.now().strftime("%Y-%m-%d"),
                "outcome": outcome or "pending",
            }],
            ids=[doc_id]
        )

        logger.info(f"[Memory] stored decision: {doc_id} ({decision} {stock_name})")
        return doc_id

    def recall_similar(self, current_context: str, n_results: int = 5) -> List[Dict]:
        """召回类似行情下的历史决策"""
        results = self.collection.query(
            query_texts=[current_context],
            n_results=n_results
        )

        memories = []
        for i, doc in enumerate(results.get("documents", [[]])[0]):
            meta = results["metadatas"][0][i] if results.get("metadatas") else {}
            memories.append({
                "document": doc,
                "metadata": meta,
                "distance": results["distances"][0][i] if results.get("distances") else 0,
            })

        logger.info(f"[Memory] recalled {len(memories)} similar decisions")
        return memories

    def update_outcome(self, doc_id: str, outcome: str):
        """更新决策结果（30天后填入实际收益）"""
        # ChromaDB 不支持直接更新 metadata，需要先删后加
        try:
            existing = self.collection.get(ids=[doc_id])
            if existing and existing["documents"]:
                doc = existing["documents"][0]
                meta = existing["metadatas"][0]
                meta["outcome"] = outcome
                doc = doc.replace("结果: 待定", f"结果: {outcome}")

                self.collection.delete(ids=[doc_id])
                self.collection.add(
                    documents=[doc],
                    metadatas=[meta],
                    ids=[doc_id]
                )
                logger.info(f"[Memory] updated outcome for {doc_id}: {outcome}")
        except Exception as e:
            logger.error(f"[Memory] update outcome error: {e}")


# 全局实例
_memory: Optional[TradingMemory] = None


def get_memory() -> TradingMemory:
    global _memory
    if _memory is None:
        _memory = TradingMemory()
    return _memory
