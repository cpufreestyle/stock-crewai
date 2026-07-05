"""
LLM 客户端 - DeepSeek 封装
支持 analyst (chat) 和 reasoner 两种模型
"""
import os
import json
import logging
from typing import Optional
from openai import OpenAI

logger = logging.getLogger("v5.llm")


class LLMClient:
    """DeepSeek LLM 客户端"""

    def __init__(self, role: str = "analyst"):
        """
        role: "analyst" (deepseek-chat) 或 "reasoner" (deepseek-reasoner)
        """
        from v5.config import LLM_CONFIG

        cfg = LLM_CONFIG[role]
        self.model = cfg["model"]
        self.client = OpenAI(
            api_key=cfg["api_key"],
            base_url=cfg["base_url"],
        )
        self.temperature = cfg["temperature"]
        self.max_tokens = cfg["max_tokens"]
        self.role = role

        logger.info(f"[LLM] initialized {role}: {self.model}")

    def chat(self, system_prompt: str, user_prompt: str, temperature: Optional[float] = None) -> str:
        """单轮对话"""
        try:
            resp = self.client.chat.completions.create(
                model=self.model,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt},
                ],
                temperature=temperature or self.temperature,
                max_tokens=self.max_tokens,
            )
            return resp.choices[0].message.content
        except Exception as e:
            logger.error(f"[LLM] chat error: {e}")
            return ""

    def chat_json(self, system_prompt: str, user_prompt: str, temperature: Optional[float] = None) -> dict:
        """单轮对话，返回 JSON"""
        text = self.chat(system_prompt, user_prompt, temperature)
        if not text:
            return {}

        # 尝试提取 JSON
        try:
            # 去掉可能的 markdown 代码块
            if "```json" in text:
                text = text.split("```json")[1].split("```")[0]
            elif "```" in text:
                text = text.split("```")[1].split("```")[0]
            return json.loads(text.strip())
        except (json.JSONDecodeError, IndexError) as e:
            logger.warning(f"[LLM] JSON parse failed: {e}, raw: {text[:200]}")
            return {"raw_response": text}


# ── 全局实例（延迟初始化）──
_instances: dict[str, LLMClient] = {}


def get_llm(role: str = "analyst") -> LLMClient:
    """获取 LLM 实例（单例）"""
    if role not in _instances:
        _instances[role] = LLMClient(role)
    return _instances[role]
