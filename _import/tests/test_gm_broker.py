"""
掘金仿真对接（gm_broker + gm_sync_worker）测试套件
运行: pytest tests/test_gm_broker.py -v
"""
import json
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

# 添加项目根目录到 path
sys.path.insert(0, str(Path(__file__).parent.parent))

import gm_broker
import gm_sync_worker as worker
from gm_broker import to_gm_symbol


@pytest.fixture(autouse=True)
def clean_env(monkeypatch, tmp_path):
    """每个测试隔离环境变量、模块状态、队列文件"""
    for k in ("GM_ENABLED", "GM_TOKEN", "GM_ACCOUNT_ID", "GM_ENDPOINT", "GM_PYTHON"):
        monkeypatch.delenv(k, raising=False)
    gm_broker.reset_for_tests()
    monkeypatch.setattr(gm_broker, "QUEUE_FILE", str(tmp_path / "gm_sync_queue.json"))
    monkeypatch.setattr(worker, "_QUEUE_FILE", str(tmp_path / "gm_sync_queue.json"))
    monkeypatch.setattr(worker, "_WORKER_LOCK", str(tmp_path / "gm_sync_queue.json.worker.lock"))
    yield
    gm_broker.reset_for_tests()


def enable_gm(monkeypatch):
    monkeypatch.setenv("GM_ENABLED", "true")
    monkeypatch.setenv("GM_TOKEN", "test-token")
    monkeypatch.setenv("GM_ACCOUNT_ID", "test-account")


class FakeGmApi:
    """gmtrade.api 的测试替身（记录调用，不发真实请求）"""

    OrderSide_Buy = 1
    OrderSide_Sell = 2
    OrderType_Limit = 3
    PositionEffect_Open = 4
    PositionEffect_Close = 5

    def __init__(self):
        self.calls = []

    def set_token(self, token): self.token = token
    def set_endpoint(self, endpoint): self.endpoint = endpoint
    def account(self, account_id="", account_alias=""): return SimpleNamespace(account_id=account_id)
    def login(self, acc): return 0

    def order_volume(self, **kw):
        self.calls.append(kw)
        return SimpleNamespace(cl_ord_id="fake-order-1", status=3)

    def get_cash(self):
        return SimpleNamespace(available=88888.0, total_value=95000.0)

    def get_positions(self):
        return [SimpleNamespace(symbol="SHSE.600519", volume=100, frozen=0)]


# ============ gm_broker ============

class TestToGmSymbol:
    """A股代码转掘金格式"""

    def test_shanghai(self):
        assert to_gm_symbol("600519") == "SHSE.600519"
        assert to_gm_symbol("688981") == "SHSE.688981"

    def test_shenzhen(self):
        assert to_gm_symbol("000001") == "SZSE.000001"
        assert to_gm_symbol("300750") == "SZSE.300750"

    def test_unsupported(self):
        assert to_gm_symbol("830799") is None  # 北交所
        assert to_gm_symbol("abc123") is None
        assert to_gm_symbol("12345") is None


class TestMirrorTrade:
    """镜像入口（portfolio_tracker 挂钩调用）"""

    def test_disabled_when_env_missing(self):
        r = gm_broker.mirror_trade("buy", "600519", 1700.0, 100)
        assert r["queued"] is False
        assert r["reason"] == "disabled"
        assert not Path(gm_broker.QUEUE_FILE).exists()

    def test_enqueues_and_dispatches(self, monkeypatch):
        enable_gm(monkeypatch)
        dispatched = []
        monkeypatch.setattr(gm_broker, "dispatch_worker", lambda: dispatched.append(1) or True)

        r = gm_broker.mirror_trade("buy", "600519", 1700.0, 200, "贵州茅台")
        assert r["queued"] is True

        q = json.loads(Path(gm_broker.QUEUE_FILE).read_text(encoding="utf-8"))
        assert len(q["pending"]) == 1
        item = q["pending"][0]
        assert item["action"] == "buy" and item["code"] == "600519"
        assert item["shares"] == 200 and item["price"] == 1700.0
        assert item["status"] == "pending"
        assert dispatched  # 已派发 worker

    def test_unsupported_code_skipped(self, monkeypatch):
        enable_gm(monkeypatch)
        r = gm_broker.mirror_trade("buy", "830799", 5.0, 100)
        assert r["queued"] is False
        assert not Path(gm_broker.QUEUE_FILE).exists()

    def test_exception_never_propagates(self, monkeypatch):
        enable_gm(monkeypatch)
        def boom(*a, **k): raise RuntimeError("boom")
        monkeypatch.setattr(gm_broker, "enqueue_trade", boom)
        r = gm_broker.mirror_trade("buy", "600519", 1700.0, 100)
        assert r["queued"] is False
        assert "boom" in r["error"]


class TestDispatchWorker:
    """worker 解释器定位与派发降级"""

    def test_no_python_returns_false_quietly(self, monkeypatch):
        monkeypatch.setattr(gm_broker, "find_worker_python", lambda: None)
        assert gm_broker.dispatch_worker() is False  # 只提示一次，不抛异常

    def test_spawn_failure_swallowed(self, monkeypatch):
        monkeypatch.setattr(gm_broker, "find_worker_python", lambda: ["C:/no/such/python.exe"])
        assert gm_broker.dispatch_worker() is False


class TestUpdatePositionHook:
    """本地成交 → 镜像挂钩"""

    def test_buy_mirrored_to_queue(self, monkeypatch, tmp_path):
        import portfolio_tracker as pt
        enable_gm(monkeypatch)
        queued = []
        monkeypatch.setattr(gm_broker, "dispatch_worker", lambda: queued.append(1) or True)
        monkeypatch.setattr(pt, "PORTFOLIO_FILE", str(tmp_path / "portfolio.json"))

        pt.save_portfolio({
            "positions": {}, "cash": 200000, "total_capital": 200000,
            "total_value": 200000, "total_return_pct": 0.0,
        })
        result = pt.update_position(
            "600519", "贵州茅台", "buy", 1700.0, 100,
            current_prices={"600519": 1700.0},
        )

        assert "error" not in result
        q = json.loads(Path(gm_broker.QUEUE_FILE).read_text(encoding="utf-8"))
        assert len(q["pending"]) == 1
        assert q["pending"][0]["name"] == "贵州茅台"

    def test_insufficient_cash_no_mirror(self, monkeypatch, tmp_path):
        import portfolio_tracker as pt
        enable_gm(monkeypatch)
        monkeypatch.setattr(pt, "PORTFOLIO_FILE", str(tmp_path / "portfolio.json"))

        pt.save_portfolio({
            "positions": {}, "cash": 1000, "total_capital": 200000,
            "total_value": 1000, "total_return_pct": -99.5,
        })
        result = pt.update_position("600519", "贵州茅台", "buy", 1700.0, 100)

        assert "error" in result  # 本地资金不足被拒
        assert not Path(gm_broker.QUEUE_FILE).exists()  # 不入队


# ============ gm_sync_worker ============

class TestWorkerQueue:
    """worker 队列状态机"""

    def _seed(self, items):
        Path(worker._QUEUE_FILE).parent.mkdir(parents=True, exist_ok=True)
        Path(worker._QUEUE_FILE).write_text(
            json.dumps({"pending": items, "done": []}, ensure_ascii=False), encoding="utf-8")

    def test_claim_marks_running(self):
        self._seed([
            {"id": "a", "action": "buy", "code": "600519", "price": 1700.0, "shares": 100, "status": "pending", "attempts": 0},
        ])
        claimed, _ = worker.claim_batch()
        assert len(claimed) == 1 and claimed[0]["id"] == "a"
        q = json.loads(Path(worker._QUEUE_FILE).read_text(encoding="utf-8"))
        assert q["pending"][0]["status"] == "running"
        assert q["pending"][0]["attempts"] == 1

    def test_stale_running_reclaimed(self):
        from datetime import datetime, timedelta
        stale = (datetime.now() - timedelta(seconds=600)).isoformat()
        self._seed([
            {"id": "b", "action": "sell", "code": "000001", "price": 11.0, "shares": 100,
             "status": "running", "attempts": 1, "claimed_at": stale},
        ])
        claimed, _ = worker.claim_batch()
        assert len(claimed) == 1 and claimed[0]["attempts"] == 2

    def test_fresh_running_not_reclaimed(self):
        from datetime import datetime, timedelta
        fresh = (datetime.now() - timedelta(seconds=10)).isoformat()
        self._seed([
            {"id": "c", "action": "buy", "code": "000001", "price": 11.0, "shares": 100,
             "status": "running", "attempts": 1, "claimed_at": fresh},
        ])
        claimed, _ = worker.claim_batch()
        assert claimed == []

    def test_finish_moves_to_done(self):
        self._seed([
            {"id": "d", "action": "buy", "code": "600519", "price": 1700.0, "shares": 100,
             "status": "running", "attempts": 1},
        ])
        worker.finish_batch([{
            "id": "d", "action": "buy", "code": "600519", "name": "贵州茅台",
            "price": 1700.0, "shares": 100, "attempts": 1, "status": "done", "result": "ok",
        }])
        q = json.loads(Path(worker._QUEUE_FILE).read_text(encoding="utf-8"))
        assert q["pending"] == []
        assert len(q["done"]) == 1 and q["done"][0]["status"] == "done"
        assert "finished_at" in q["done"][0]


class TestWorkerSubmit:
    """下单参数构造"""

    def test_buy_rounds_lot_and_opens(self):
        api = FakeGmApi()
        ok, msg = worker.submit_order(api, {"action": "buy", "code": "600519", "price": 1700.0, "shares": 250})
        assert ok
        assert api.calls[0]["symbol"] == "SHSE.600519"
        assert api.calls[0]["volume"] == 200
        assert api.calls[0]["position_effect"] == FakeGmApi.PositionEffect_Open

    def test_buy_below_lot_rejected(self):
        ok, msg = worker.submit_order(FakeGmApi(), {"action": "buy", "code": "600519", "price": 1700.0, "shares": 50})
        assert not ok and "一手" in msg

    def test_sell_closes_actual_shares(self):
        api = FakeGmApi()
        ok, msg = worker.submit_order(api, {"action": "sell", "code": "000001", "price": 11.5, "shares": 100})
        assert ok
        assert api.calls[0]["position_effect"] == FakeGmApi.PositionEffect_Close
        assert api.calls[0]["volume"] == 100

    def test_process_queue_end_to_end(self, monkeypatch):
        """认领 → 登录 → 提交 → 回写 全链路（gmtrade 替身）"""
        fake = FakeGmApi()
        monkeypatch.setattr(worker, "login_gm", lambda: fake)
        Path(worker._QUEUE_FILE).parent.mkdir(parents=True, exist_ok=True)
        Path(worker._QUEUE_FILE).write_text(json.dumps({
            "pending": [
                {"id": "e1", "action": "buy", "code": "600519", "price": 1700.0, "shares": 100, "status": "pending", "attempts": 0},
                {"id": "e2", "action": "sell", "code": "000001", "price": 11.5, "shares": 100, "status": "pending", "attempts": 0},
            ],
            "done": [],
        }, ensure_ascii=False), encoding="utf-8")

        rc = worker.process_queue()
        assert rc == 0
        assert len(fake.calls) == 2
        q = json.loads(Path(worker._QUEUE_FILE).read_text(encoding="utf-8"))
        assert q["pending"] == []
        assert [d["status"] for d in q["done"]] == ["done", "done"]

    def test_process_queue_login_failure_keeps_pending(self, monkeypatch):
        def boom(): raise RuntimeError("token invalid")
        monkeypatch.setattr(worker, "login_gm", boom)
        Path(worker._QUEUE_FILE).parent.mkdir(parents=True, exist_ok=True)
        Path(worker._QUEUE_FILE).write_text(json.dumps({
            "pending": [{"id": "f1", "action": "buy", "code": "600519", "price": 1700.0, "shares": 100, "status": "pending", "attempts": 0}],
            "done": [],
        }, ensure_ascii=False), encoding="utf-8")

        rc = worker.process_queue()
        assert rc == 1
        q = json.loads(Path(worker._QUEUE_FILE).read_text(encoding="utf-8"))
        assert len(q["pending"]) == 1          # 保留重试
        assert q["pending"][0]["status"] == "running"  # 已认领（超时后自动回收）
