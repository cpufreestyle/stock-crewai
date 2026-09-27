"""
LLM 配置 - 从根目录 agents.py 迁移而来

针对本地 Ollama（Qwen3.8 等推理模型）的优化：
1. reasoning_effort=none
   模型模板默认会先生成大量 thinking token 再给结论，content 容易为空且耗时翻倍。
   实测本机（RTX 4060 Ti）none 比 low 再快 2~3 倍（工具调用 1.1s vs 3.8s），且 finish 正常为 stop。
2. 模型必须选大上下文变体（见 .env 注释）
   多智能体任务会把前序输出与工具结果全部拼进 prompt，单次请求实测 12k~15k token；
   num_ctx 不足时 Ollama 返回 400 exceed_context_size_error，
   CrewAI 侧表现为 "Invalid response from LLM call - None or empty."，整条流水线中止。
3. timeout
   本地大模型偶发卡死时快速失败，避免整条流水线无限挂起。
4. 关键参数全部支持环境变量覆盖，方便在不同模型/机器间切换。

可用环境变量：
    LLM_TEMPERATURE       采样温度（默认 0.3）
    LLM_MAX_TOKENS        最大输出 token（默认 2048）
    LLM_TIMEOUT           单次调用超时秒数（默认 300）
    LLM_REASONING_EFFORT  推理强度 none/low/medium/xhigh，置空则不传该参数（默认 low）
    LLM_CACHE_TTL        响应缓存 TTL 秒数，0=关闭（默认）。开启后相同 prompt
                         在 TTL 内直接命中缓存，跳过本地模型推理（调试/重跑时省时间）
"""
from crewai import LLM
import os


def _env_str(name: str, default: str) -> str:
    return (os.getenv(name) or default).strip()


def _env_float(name: str, default: float) -> float:
    try:
        return float(os.getenv(name))
    except (TypeError, ValueError):
        return default


def _env_int(name: str, default: int) -> int:
    try:
        return int(os.getenv(name))
    except (TypeError, ValueError):
        return default


def _common_kwargs() -> dict:
    """各 provider 共用的参数"""
    return {
        "temperature": _env_float("LLM_TEMPERATURE", 0.3),
        "max_tokens": _env_int("LLM_MAX_TOKENS", 2048),
        "timeout": _env_float("LLM_TIMEOUT", 300.0),
    }


def _build_llm(model: str, api_key: str, base_url: str, kwargs: dict):
    """构建 LLM；设置了 LLM_CACHE_TTL 时包一层响应磁盘缓存。

    参照 ai-hedge-fund 的 PromptCache 模式：本地模型一轮管15~20 分钟，
    原封不动重跑（调试/连续运行）时相同 prompt 不该再花一遍等待。
    key 覆盖完整 messages，命中要求 prompt 完全一致；默认 TTL=0 关闭。
    """
    if _env_float("LLM_CACHE_TTL", 0) > 0:
        from llm_cache import make_cached_llm
        return make_cached_llm(model=model, api_key=api_key, base_url=base_url, **kwargs)
    return LLM(model=model, api_key=api_key, base_url=base_url, **kwargs)


def get_llm():
    """获取 LLM 实例"""
    provider = _env_str("LLM_PROVIDER", "default").lower()

    # MIMO v2.5（小米 API）
    if provider in ("mimo", "mimo-v2.5", "xiaomi"):
        api_key = os.getenv("MIMO_API_KEY", "")
        base_url = os.getenv("MIMO_BASE_URL", "https://api.mimo.ai/v1")
        model = os.getenv("MIMO_MODEL_NAME", "free/mimo-v2.5-pro-cn")
        if not api_key:
            print("[Agent] 警告: 设置了 LLM_PROVIDER=mimo 但未设置 MIMO_API_KEY")
            return None
        print(f"[Agent] 使用 MIMO v2.5: {model}")
        return _build_llm(f"openai/{model}", api_key, base_url, _common_kwargs())

    # 默认：OpenAI 兼容 API（Ollama / OpenRouter / DashScope / LM Studio）
    api_key = os.getenv("OPENAI_API_KEY") or os.getenv("DASHSCOPE_API_KEY") or ""
    base_url = os.getenv("OPENAI_BASE_URL", "https://openrouter.ai/api/v1")
    model = os.getenv("MODEL_NAME", "deepseek/deepseek-chat-v3-0324")

    if not api_key or api_key == "sk-your-key-here":
        print("[Agent] 警告: 未设置有效 API Key")
        return None

    kwargs = _common_kwargs()

    # 推理模型默认 xhigh 会生成大量 thinking token，拖慢本地推理。
    # 置空 LLM_REASONING_EFFORT 即可恢复模型默认行为（对接不支持该参数的云端 API 时有用）。
    reasoning_effort = os.getenv("LLM_REASONING_EFFORT", "low").strip()
    if reasoning_effort:
        kwargs["reasoning_effort"] = reasoning_effort
        # crewai 原生 OpenAI provider 只在 is_o1_model 为真时才下发 reasoning_effort
        # （llms/providers/openai/completion.py:1930），非 o1 模型会被静默丢弃，
        # 导致本地思考模型仍然开着 thinking 跑、content 返回空。
        # additional_params 是原样透传的，走这条路参数才真正进 HTTP 请求体。
        kwargs["additional_params"] = {"reasoning_effort": reasoning_effort}

    print(f"[Agent] 使用 LLM: {model} @ {base_url} (reasoning_effort={reasoning_effort or '默认'})")
    return _build_llm(f"openai/{model}", api_key, base_url, kwargs)
