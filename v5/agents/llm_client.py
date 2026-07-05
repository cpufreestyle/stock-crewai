"""
DeepSeek → LM Studio LLM 客户端
通过 OpenAI 兼容 API 调用本地 LM Studio 服务
"""
import json
import logging
import requests
from openai import OpenAI
from v5.config import LLM_CONFIG

logger = logging.getLogger("v5.llm")


class LLMClient:
    """LLM 客户端 - 支持 LM Studio 本地模型"""

    def __init__(self, role: str = "analyst"):
        cfg = LLM_CONFIG[role]
        self.client = OpenAI(
            api_key=cfg["api_key"],
            base_url=cfg["base_url"],
        )
        self.temperature = cfg.get("temperature", 0.3)
        self.max_tokens = cfg.get("max_tokens", 2048)
        self.role = role
        # 自动获取 LM Studio 已加载的模型名
        self.model = self._detect_model()

    def _detect_model(self) -> str:
        """从 LM Studio 获取已加载的模型名"""
        try:
            resp = requests.get(f"{LLM_CONFIG[self.role]['base_url']}/models", timeout=3)
            if resp.status_code == 200:
                models = resp.json().get("data", [])
                if models:
                    return models[0]["id"]
        except Exception:
            pass
        # fallback to config
        return LLM_CONFIG[self.role]["model"]

    def chat(self, system: str, user: str) -> str:
        """普通对话，返回纯文本"""
        try:
            resp = self.client.chat.completions.create(
                model=self.model,
                messages=[
                    {"role": "system", "content": system},
                    {"role": "user", "content": user},
                ],
                temperature=self.temperature,
                max_tokens=self.max_tokens,
            )
            return resp.choices[0].message.content.strip()
        except Exception as e:
            logger.error(f"LLM chat 失败 [{self.role}]: {e}")
            return ""

    def chat_json(self, system: str, user: str) -> dict:
        """对话并解析 JSON 返回"""
        text = self.chat(system, user)
        if not text:
            return {}

        # 尝试直接解析
        try:
            return json.loads(text)
        except json.JSONDecodeError:
            pass

        # 尝试从 markdown code block 中提取
        if "```json" in text:
            start = text.index("```json") + 7
            end = text.index("```", start)
            try:
                return json.loads(text[start:end].strip())
            except json.JSONDecodeError:
                pass
        elif "```" in text:
            start = text.index("```") + 3
            end = text.index("```", start)
            try:
                return json.loads(text[start:end].strip())
            except json.JSONDecodeError:
                pass

        # 尝试找到第一个 { 和最后一个 }
        first = text.find("{")
        last = text.rfind("}")
        if first != -1 and last != -1 and last > first:
            try:
                return json.loads(text[first:last + 1])
            except json.JSONDecodeError:
                pass

        logger.warning(f"JSON 解析失败 [{self.role}], raw: {text[:200]}...")
        return {"raw_text": text}

    def is_available(self) -> bool:
        """检查 LM Studio 服务是否可用"""
        try:
            base_url = LLM_CONFIG[self.role]["base_url"]
            resp = requests.get(f"{base_url}/models", timeout=3)
            return resp.status_code == 200
        except Exception:
            return False


# 全局缓存
_clients: dict[str, LLMClient] = {}


def get_llm(role: str = "analyst") -> LLMClient:
    """获取 LLM 客户端（单例）"""
    if role not in _clients:
        _clients[role] = LLMClient(role)
    return _clients[role]


def check_lm_studio() -> bool:
    """检查 LM Studio 服务是否运行"""
    try:
        resp = requests.get("http://localhost:1234/v1/models", timeout=3)
        if resp.status_code == 200:
            models = resp.json().get("data", [])
            if models:
                logger.info(f"LM Studio 可用，已加载模型: {[m['id'] for m in models]}")
                return True
            else:
                logger.warning("LM Studio 运行中但未加载模型")
                return False
        return False
    except requests.ConnectionError:
        logger.error("LM Studio 未运行或端口不可达 (localhost:1234)")
        return False
