"""
LLM 配置 - 从根目录 agents.py 迁移而来
"""
from crewai import LLM
import os


def get_llm():
    """获取 LLM 实例"""
    provider = os.getenv("LLM_PROVIDER", "default").strip().lower()
    
    # MIMO v2.5（小米 API）
    if provider in ("mimo", "mimo-v2.5", "xiaomi"):
        api_key = os.getenv("MIMO_API_KEY", "")
        base_url = os.getenv("MIMO_BASE_URL", "https://api.mimo.ai/v1")
        model = os.getenv("MIMO_MODEL_NAME", "free/mimo-v2.5-pro-cn")
        if not api_key:
            print("[Agent] 警告: 设置了 LLM_PROVIDER=mimo 但未设置 MIMO_API_KEY")
            return None
        print(f"[Agent] 使用 MIMO v2.5: {model}")
        return LLM(
            model=f"openai/{model}",
            api_key=api_key,
            base_url=base_url,
            temperature=0.3,
            max_tokens=2048
        )
    
    # 默认：OpenAI 兼容 API（OpenRouter / DashScope / LM Studio）
    api_key = os.getenv("OPENAI_API_KEY") or os.getenv("DASHSCOPE_API_KEY") or ""
    base_url = os.getenv("OPENAI_BASE_URL", "https://openrouter.ai/api/v1")
    model = os.getenv("MODEL_NAME", "deepseek/deepseek-chat-v3-0324")
    
    if not api_key or api_key == "sk-your-key-here":
        print("[Agent] 警告: 未设置有效 API Key")
        return None
    
    print(f"[Agent] 使用 LLM: {model} @ {base_url}")
    return LLM(
        model=f"openai/{model}",
        api_key=api_key,
        base_url=base_url,
        temperature=0.3,
        max_tokens=2048
    )
