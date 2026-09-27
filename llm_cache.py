# -*- coding: utf-8 -*-
"""Disk-backed LLM response cache (pattern borrowed from ai-hedge-fund PromptCache).

Why: a full local-model pipeline pass costs 15-20 minutes. Re-running with an
unchanged prompt (debugging, back-to-back runs) pays the whole cost again.
CachedLLM wraps crewai.LLM and memoises responses keyed by
(model, messages, tools) with a TTL, so identical prompts are free.

Safety gates:
- Disabled by default. Set LLM_CACHE_TTL=<seconds> to enable.
- The key covers the full message list, so a hit means every token of the
  prompt matched -- yesterday's market data cannot serve today's decision.
- Only plain string responses are cached; tool-call payloads and non-string
  returns pass through untouched.
"""
import hashlib
import json
import os
import time

CACHE_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "cache", "llm")

_stats = {"hits": 0, "misses": 0}


def _ttl() -> float:
    try:
        return float(os.getenv("LLM_CACHE_TTL", "0") or 0)
    except ValueError:
        return 0.0


def _key(model: str, messages, tools) -> str:
    payload = json.dumps(
        {"model": model, "messages": _jsonable(messages), "tools": _jsonable(tools)},
        ensure_ascii=False, sort_keys=True, default=str,
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _jsonable(value):
    """Best-effort conversion of LiteLLM message/tool objects into JSON-able data."""
    if isinstance(value, (str, int, float, bool)) or value is None:
        return value
    if isinstance(value, dict):
        return {str(k): _jsonable(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [_jsonable(v) for v in value]
    for attr in ("model_dump", "dict"):
        fn = getattr(value, attr, None)
        if callable(fn):
            try:
                return _jsonable(fn())
            except Exception:
                pass
    return str(value)


def _path(key: str) -> str:
    return os.path.join(CACHE_DIR, key[:2], key + ".json")


def get(key: str, ttl: float):
    if ttl <= 0:
        return None
    try:
        with open(_path(key), "r", encoding="utf-8") as f:
            rec = json.load(f)
    except (OSError, ValueError):
        return None
    if time.time() - rec.get("ts", 0) > ttl:
        return None
    return rec.get("response")


def put(key: str, response: str) -> None:
    try:
        path = _path(key)
        os.makedirs(os.path.dirname(path), exist_ok=True)
        tmp = path + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump({"ts": time.time(), "response": response}, f, ensure_ascii=False)
        os.replace(tmp, path)
    except OSError:
        pass


def stats() -> dict:
    return dict(_stats)


def make_cached_llm(**kwargs):
    """Build a crewai LLM, wrapped with the response cache when TTL > 0.

    crewai.LLM is a factory: LLM(model=...) returns a provider-specific
    instance (e.g. OpenAICompletion for the openai/ prefix we use against
    Ollama). Subclassing LLM itself is bypassed by its __new__ dispatch, so we
    build the real object once, then subclass its concrete class.

    The subclass is re-initialised from the normalised field values of the
    factory-built object (public pydantic fields only). This is not just an
    optimisation: the factory normalises kwargs -- e.g. for
    model="openai/qwen3..." with a custom base_url it strips the "openai/"
    prefix, sets provider="openai" and custom_openai=True. Re-passing the raw
    kwargs to the subclass would resurrect un-normalised values
    (model="openai/..." sent to Ollama answers 404 model not found), while a
    __new__/__dict__ copy breaks pydantic private state (__pydantic_private__
    missing -> '_CachedProviderLLM' object has no attribute). Copying fields
    and re-running __init__ preserves every factory decision AND keeps
    pydantic internals intact.
    """
    from crewai import LLM

    base = LLM(**kwargs)
    provider_cls = type(base)

    class _CachedProviderLLM(provider_cls):  # type: ignore[misc, valid-type]
        def call(self, messages, tools=None, callbacks=None,
                 available_functions=None, from_task=None, from_agent=None,
                 response_model=None):
            ttl = _ttl()
            if ttl <= 0:
                return super().call(
                    messages, tools, callbacks, available_functions,
                    from_task, from_agent, response_model,
                )
            key = _key(str(self.model), messages, tools)
            cached = get(key, ttl)
            if cached is not None:
                _stats["hits"] += 1
                print(f"[LLM cache] hit {key[:8]} (hits={_stats['hits']})")
                return cached
            _stats["misses"] += 1
            out = super().call(
                messages, tools, callbacks, available_functions,
                from_task, from_agent, response_model,
            )
            if isinstance(out, str):
                put(key, out)
            return out

    field_names = set(getattr(provider_cls, "model_fields", {}))
    init_kwargs = {k: v for k, v in base.__dict__.items() if k in field_names}
    return _CachedProviderLLM(**init_kwargs)
