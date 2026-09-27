# -*- coding: utf-8 -*-
"""trading_plan / llm_cache 模块测试
运行: pytest tests/ -v
"""
import json
import time

import pytest

import llm_cache
from trading_plan import (
    TradeAction,
    TradingPlan,
    parse_trading_plan,
    plan_to_recommendations,
    render_plan_summary,
)


# ---------- TradeAction 字段校验 ----------

class TestTradeAction:

    def test_valid_minimal_row(self):
        a = TradeAction(code="000001", action="buy")
        assert a.code == "000001"
        assert a.action == "buy"
        assert a.name == "" and a.price is None and a.confidence == "medium"

    def test_invalid_code_rejected(self):
        with pytest.raises(Exception):
            TradeAction(code="12345", action="buy")   # 5 位
        with pytest.raises(Exception):
            TradeAction(code="AAPL", action="buy")    # 非数字
        with pytest.raises(Exception):
            TradeAction(code="900001", action="buy")  # 非 0/3/6 开头

    def test_chinese_action_aliases(self):
        assert TradeAction(code="600519", action="买入").action == "buy"
        assert TradeAction(code="600519", action="加仓").action == "add"
        assert TradeAction(code="600519", action="减仓").action == "reduce"
        assert TradeAction(code="600519", action="清仓").action == "sell"
        assert TradeAction(code="600519", action="持有").action == "hold"
        assert TradeAction(code="600519", action="观察").action == "watch"

    def test_unknown_action_falls_back_to_hold(self):
        assert TradeAction(code="600519", action="moon_soon").action == "hold"
        assert TradeAction(code="600519", action="梭哈").action == "hold"

    def test_price_cleaning(self):
        assert TradeAction(code="600519", action="buy", price="$1,234.50").price == 1234.5
        assert TradeAction(code="600519", action="buy", price="￥23.5").price == 23.5

    def test_percentage_price_dropped(self):
        assert TradeAction(code="600519", action="buy", price="15%").price is None

    def test_nullish_price_dropped(self):
        for v in ("None", "N/A", "无", "", "-", 0, -3):
            assert TradeAction(code="600519", action="buy", price=v).price is None, v

    def test_position_pct_scaling_and_clamp(self):
        assert TradeAction(code="600519", action="buy", position_pct=0.1).position_pct == pytest.approx(10.0)
        assert TradeAction(code="600519", action="buy", position_pct=150).position_pct == 100.0
        assert TradeAction(code="600519", action="buy", position_pct="10").position_pct == pytest.approx(10.0)
        assert TradeAction(code="600519", action="buy", position_pct=None).position_pct is None


# ---------- parse_trading_plan ----------

class TestParseTradingPlan:

    def test_empty_and_none_input(self):
        assert parse_trading_plan("") is None
        assert parse_trading_plan(None) is None
        assert parse_trading_plan("没有 JSON 的普通报告") is None

    def test_fenced_json_block(self):
        text = '''分析如下：
```json
{"market_view": "震荡上行", "actions": [{"code": "000001", "name": "平安银行", "action": "买入", "price": "12.5", "position_pct": 10}]}
```
完。'''
        plan = parse_trading_plan(text)
        assert plan is not None
        assert plan.market_view == "震荡上行"
        assert len(plan.actions) == 1
        a = plan.actions[0]
        assert (a.code, a.action, a.price, a.position_pct) == ("000001", "buy", 12.5, 10.0)

    def test_bare_json_without_fence(self):
        text = '前言 {"actions": [{"code": "300750", "action": "watch"}]} 后记'
        plan = parse_trading_plan(text)
        assert plan is not None
        assert plan.actions[0].code == "300750"
        assert plan.actions[0].action == "watch"

    def test_empty_actions_still_returns_plan(self):
        plan = parse_trading_plan('{"market_view": "空仓观望", "actions": []}')
        assert plan is not None
        assert plan.actions == []
        assert plan.market_view == "空仓观望"

    def test_no_actions_key_returns_none(self):
        assert parse_trading_plan('{"market_view": "only view"}') is None

    def test_bad_rows_skipped_not_fatal(self):
        text = '{"actions": [{"code": "XX", "action": "buy"}, {"code": "600519", "action": "sell"}]}'
        plan = parse_trading_plan(text)
        assert plan is not None and len(plan.actions) == 1
        assert plan.actions[0].code == "600519"

    def test_all_rows_invalid_returns_none(self):
        text = '{"actions": [{"code": "XX", "action": "buy"}]}'
        assert parse_trading_plan(text) is None

    def test_first_valid_candidate_wins(self):
        text = '{"actions": [{"code": "600519", "action": "hold"}]}'
        plan = parse_trading_plan(text)
        assert plan.actions[0].code == "600519"


# ---------- plan_to_recommendations ----------

class TestPlanToRecommendations:

    def test_only_buy_and_add_tracked(self):
        plan = parse_trading_plan(json.dumps({"actions": [
            {"code": "600519", "name": "A", "action": "buy", "price": 10, "stop_loss": 9, "reason": "r"},
            {"code": "000001", "name": "B", "action": "add"},
            {"code": "300750", "name": "C", "action": "sell"},
            {"code": "002594", "name": "D", "action": "hold"},
        ]}, ensure_ascii=False))
        recs = plan_to_recommendations(plan)
        assert [r["code"] for r in recs] == ["600519", "000001"]
        assert recs[0]["entry_price"] == 10.0
        assert recs[0]["stop"] == 9.0
        assert recs[0]["target"] is None
        assert recs[0]["reason"] == "r"


# ---------- render_plan_summary ----------

class TestRenderPlanSummary:

    def test_summary_contains_fields(self):
        plan = parse_trading_plan(json.dumps({
            "market_view": "看多", "actions": [
                {"code": "600519", "name": "茅台", "action": "buy", "price": 1500.5,
                 "position_pct": 10, "stop_loss": 1450, "take_profit": 1600, "reason": "业绩超预期"}
            ]}, ensure_ascii=False))
        s = render_plan_summary(plan)
        assert "看多" in s
        assert "600519 茅台" in s and "buy" in s
        assert "@ 1500.50" in s and "仓位10%" in s
        assert "止损1450.00" in s and "止盈1600.00" in s
        assert "业绩超预期" in s

    def test_empty_plan_summary(self):
        s = render_plan_summary(TradingPlan())
        assert "本轮无动作" in s


# ---------- llm_cache ----------

@pytest.fixture
def cache_dir(tmp_path, monkeypatch):
    d = tmp_path / "llmcache"
    monkeypatch.setattr(llm_cache, "CACHE_DIR", str(d))
    llm_cache._stats.update({"hits": 0, "misses": 0})
    return d


class TestLLMCacheKey:

    def test_key_stable_for_same_input(self):
        msgs = [{"role": "user", "content": "hi"}]
        assert llm_cache._key("m", msgs, None) == llm_cache._key("m", msgs, None)

    def test_key_differs_by_model_and_messages(self):
        msgs = [{"role": "user", "content": "hi"}]
        k1 = llm_cache._key("m1", msgs, None)
        k2 = llm_cache._key("m2", msgs, None)
        k3 = llm_cache._key("m1", [{"role": "user", "content": "ho"}], None)
        assert len({k1, k2, k3}) == 3

    def test_jsonable_handles_objects_and_values(self):
        class Obj:
            def model_dump(self):
                return {"a": 1}
        class Dicty:
            def dict(self):
                return {"b": 2}
        class Opaque:
            def __str__(self):
                return "opaque"
        out = llm_cache._jsonable({"t": (Obj(), Dicty(), Opaque(), None)})
        assert out["t"] == [{"a": 1}, {"b": 2}, "opaque", None]


class TestLLMCachePutGet:

    def test_roundtrip(self, cache_dir):
        k = llm_cache._key("m", [{"role": "user", "content": "q"}], None)
        assert llm_cache.get(k, 3600) is None
        llm_cache.put(k, "resp")
        assert llm_cache.get(k, 3600) == "resp"
        # 落盘结构正确
        rec = json.loads((cache_dir / k[:2] / (k + ".json")).read_text(encoding="utf-8"))
        assert rec["response"] == "resp" and rec["ts"] > 0

    def test_expired_entry_returns_none(self, cache_dir):
        k = llm_cache._key("m", [{"role": "user", "content": "q"}], None)
        llm_cache.put(k, "resp")
        # 手工把时间戳改老，模拟 TTL 过期
        path = cache_dir / k[:2] / (k + ".json")
        rec = json.loads(path.read_text(encoding="utf-8"))
        rec["ts"] = time.time() - 7200
        path.write_text(json.dumps(rec), encoding="utf-8")
        assert llm_cache.get(k, 3600) is None

    def test_ttl_zero_disables_cache(self, cache_dir):
        k = llm_cache._key("m", [{"role": "user", "content": "q"}], None)
        llm_cache.put(k, "resp")
        assert llm_cache.get(k, 0) is None

    def test_corrupt_file_returns_none(self, cache_dir):
        k = llm_cache._key("m", [{"role": "user", "content": "q"}], None)
        path = cache_dir / k[:2] / (k + ".json")
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("not json", encoding="utf-8")
        assert llm_cache.get(k, 3600) is None


class TestMakeCachedLLM:

    def _patch_llm(self, monkeypatch):
        import crewai

        class FakeProvider:
            model_fields = {"model": None}
            calls = 0

            def __init__(self, **kwargs):
                self.__dict__.update(kwargs)

            def call(self, messages, tools=None, callbacks=None,
                     available_functions=None, from_task=None,
                     from_agent=None, response_model=None):
                FakeProvider.calls += 1
                return f"resp-{len(messages)}"

        monkeypatch.setattr(crewai, "LLM", lambda **kw: FakeProvider(**kw))
        FakeProvider.calls = 0
        return FakeProvider

    def test_hit_avoids_second_call(self, monkeypatch, cache_dir):
        FakeProvider = self._patch_llm(monkeypatch)
        monkeypatch.setenv("LLM_CACHE_TTL", "3600")
        llm = llm_cache.make_cached_llm(model="openai/test", base_url="http://x")
        assert isinstance(llm, FakeProvider)
        r1 = llm.call([{"role": "user", "content": "q"}])
        r2 = llm.call([{"role": "user", "content": "q"}])
        assert r1 == r2 == "resp-1"
        assert FakeProvider.calls == 1          # 第二次命中缓存，未真正调用
        assert llm_cache.stats()["hits"] == 1
        assert llm_cache.stats()["misses"] == 1

    def test_ttl_zero_passes_through(self, monkeypatch, cache_dir):
        FakeProvider = self._patch_llm(monkeypatch)
        monkeypatch.setenv("LLM_CACHE_TTL", "0")
        llm = llm_cache.make_cached_llm(model="openai/test")
        llm.call([{"role": "user", "content": "q"}])
        llm.call([{"role": "user", "content": "q"}])
        assert FakeProvider.calls == 2          # 未启用缓存，每次直连
        assert llm_cache.stats()["hits"] == 0

    def test_ttl_env_helper_invalid_value(self, monkeypatch):
        monkeypatch.setenv("LLM_CACHE_TTL", "abc")
        assert llm_cache._ttl() == 0.0
        monkeypatch.delenv("LLM_CACHE_TTL", raising=False)
        assert llm_cache._ttl() == 0.0
        monkeypatch.setenv("LLM_CACHE_TTL", "60")
        assert llm_cache._ttl() == 60.0
