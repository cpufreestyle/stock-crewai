# -*- coding: utf-8 -*-
"""Structured trading-plan contract (pattern borrowed from TradingAgents schemas.py).

Why: the old pipeline scraped stock codes out of free-text reports with regex
(recommendation_tracker.parse_trading_result). Any format drift loses picks.
Here the trading/rebalance tasks must append one machine-readable JSON block to
their report; field descriptions live in the task prompt (TradingAgents'
"schema field descriptions double as instructions" approach), which the local
27B model can hit reliably.

Parsing mirrors TradingAgents' LLM-junk coercion (their issues #1058/#1288):
placeholder strings ("None", "N/A") become None; percentages cannot serve as
absolute prices and are dropped; formatted numbers ("$1,234.50") are cleaned.
parse_trading_plan returns None when nothing valid is found, so callers fall
back to the legacy free-text path unchanged.
"""
import json
import re
from typing import List, Optional

from pydantic import BaseModel, Field, field_validator


_VALID_ACTIONS = {"buy", "sell", "hold", "add", "reduce", "set_stop_loss", "watch"}

# Chinese action words the model tends to emit, mapped onto the enum.
_ACTION_ALIASES = {
    "买入": "buy", "加仓": "add", "买入/加仓": "buy",
    "卖出": "sell", "减仓": "reduce", "清仓": "sell",
    "持有": "hold", "持仓": "hold", "观期": "hold",
    "设置止损": "set_stop_loss", "止损": "sell",
    "观察": "watch", "不操作": "hold",
}

_CODE_RE = re.compile(r"^[036]\d{5}$")

_NULLISH = {"", "none", "n/a", "na", "null", "nil", "-", "tbd", "unknown", "无", "暂无"}


def _coerce_price(value) -> Optional[float]:
    """LLM-written price -> float, or None when unusable.

    Mirrors TradingAgents._coerce_optional_float: a percentage ("15%") cannot be
    salvaged into an absolute level, so it is dropped rather than misparsed.
    """
    if value is None:
        return None
    if isinstance(value, (int, float)):
        return float(value)
    text = str(value).strip()
    if text.lower() in _NULLISH or text.endswith("%"):
        return None
    cleaned = text.replace(",", "").lstrip("￥$€£").strip()
    try:
        return float(cleaned)
    except ValueError:
        return None


def _coerce_action(value) -> str:
    text = str(value or "").strip().lower()
    return _ACTION_ALIASES.get(text, _ACTION_ALIASES.get(str(value or "").strip(), text))


class TradeAction(BaseModel):
    """One row of the machine-readable plan: a decision for a single stock."""
    code: str = Field(description="6-digit A-share code, e.g. 000001")
    name: str = Field(default="", description="stock name")
    action: str = Field(description="one of buy/sell/hold/add/reduce/set_stop_loss/watch")
    price: Optional[float] = Field(default=None, description="entry or action price, number only")
    position_pct: Optional[float] = Field(default=None, description="position as percent, e.g. 10 for 10%")
    stop_loss: Optional[float] = Field(default=None, description="stop-loss price, number only")
    take_profit: Optional[float] = Field(default=None, description="take-profit price, number only")
    confidence: str = Field(default="medium", description="low/medium/high")
    reason: str = Field(default="", description="one-sentence rationale")

    @field_validator("code")
    @classmethod
    def _check_code(cls, v):
        v = str(v).strip()
        if not _CODE_RE.match(v):
            raise ValueError(f"not an A-share code: {v!r}")
        return v

    @field_validator("action", mode="before")
    @classmethod
    def _norm_action(cls, v):
        a = _coerce_action(v)
        return a if a in _VALID_ACTIONS else "hold"

    @field_validator("price", "stop_loss", "take_profit", mode="before")
    @classmethod
    def _norm_price(cls, v):
        c = _coerce_price(v)
        return c if (c is None or c > 0) else None

    @field_validator("position_pct", mode="before")
    @classmethod
    def _norm_pct(cls, v):
        c = _coerce_price(v)
        if c is None:
            return None
        if 0 < c <= 1:  # fraction written as 0.1 means 10%
            c *= 100
        return min(c, 100.0)


class TradingPlan(BaseModel):
    """The whole machine-readable block appended to the trading/rebalance report."""
    market_view: str = ""
    actions: List[TradeAction] = Field(default_factory=list)


def _iter_json_candidates(text: str):
    """Yield JSON-decodable candidates, fenced blocks first."""
    for m in re.finditer(r"```(?:json)?\s*(\{.*?\})\s*```", text, re.S | re.I):
        yield m.group(1)
    if '"actions"' in text:
        start = text.find('{"')
        while start != -1:
            try:
                obj, _ = json.JSONDecoder().raw_decode(text[start:])
                if isinstance(obj, dict):
                    yield json.dumps(obj, ensure_ascii=False)
            except ValueError:
                pass
            start = text.find('{"', start + 1)


def parse_trading_plan(text: str) -> Optional[TradingPlan]:
    """Parse the structured block from a report; None when absent/invalid."""
    if not text:
        return None
    for cand in _iter_json_candidates(text):
        try:
            data = json.loads(cand)
        except ValueError:
            continue
        if not isinstance(data, dict):
            continue
        rows = data.get("actions", [])
        if not isinstance(rows, list):
            continue
        actions = []
        for row in rows:
            if not isinstance(row, dict):
                continue
            try:
                actions.append(TradeAction(**row))
            except Exception:
                continue  # one bad row must not sink the whole plan
        if actions:
            return TradingPlan(
                market_view=str(data.get("market_view") or ""),
                actions=actions,
            )
        if not rows and "actions" in data:
            # 显式空 actions = 模型本轮决定不动，与“有行但全部解析失败”区分开
            return TradingPlan(
                market_view=str(data.get("market_view") or ""),
                actions=[],
            )
    return None


def plan_to_recommendations(plan: TradingPlan) -> List[dict]:
    """Convert to the shape recommendation_tracker.save_recommendation expects."""
    out = []
    for a in plan.actions:
        if a.action not in ("buy", "add"):
            continue  # 追踪系统只记待买入建议
        out.append({
            "code": a.code,
            "name": a.name,
            "reason": a.reason,
            "entry_price": a.price,
            "target": a.take_profit,
            "stop": a.stop_loss,
        })
    return out


def render_plan_summary(plan: TradingPlan) -> str:
    """Human-readable summary of the parsed plan for the report footer."""
    lines = ["## 结构化交易计划（机器解析）", ""]
    if plan.market_view:
        lines.append(f"市场判断：{plan.market_view}")
        lines.append("")
    if not plan.actions:
        lines.append("本轮无动作。")
    for a in plan.actions:
        bits = [f"{a.code} {a.name}", a.action]
        if a.price:
            bits.append(f"@ {a.price:.2f}")
        if a.position_pct:
            bits.append(f"仓位{a.position_pct:.0f}%")
        if a.stop_loss:
            bits.append(f"止损{a.stop_loss:.2f}")
        if a.take_profit:
            bits.append(f"止盈{a.take_profit:.2f}")
        lines.append("- " + " ".join(bits) + (f" | {a.reason}" if a.reason else ""))
    return "\n".join(lines)
