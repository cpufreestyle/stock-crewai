# -*- coding: utf-8 -*-
"""web_dashboard 路由冒烟测试

用 Flask test_client 打本地路由，不起服务、不碰网络。
这些用例只验证“路由可达、返回合法 JSON、结构符合约定”，给后续重构兜底。
"""
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))

web_dashboard = pytest.importorskip("web_dashboard")


@pytest.fixture
def client():
    web_dashboard.app.config.update({"TESTING": True})
    with web_dashboard.app.test_client() as c:
        yield c


def _ok_json(resp):
    assert resp.status_code == 200, resp.data[:300]
    return resp.get_json()


class TestHealthRoute:
    def test_health(self, client):
        body = _ok_json(client.get("/api/health"))
        assert body["status"] == "ok"
        assert "time" in body


class TestAgentRoutes:
    def test_scheduler_status_shape(self, client):
        """成功时 success=True 且带 data；失败也不能 500"""
        resp = client.get("/api/scheduler_status")
        assert resp.status_code == 200
        body = resp.get_json()
        assert body["success"] in (True, False)
        if body["success"]:
            assert "data" in body

    def test_agent_status_shape(self, client):
        body = _ok_json(client.get("/api/agent_status"))
        assert body["success"] is True
        assert "data" in body

    def test_agent_events_shape(self, client):
        body = _ok_json(client.get("/api/agent_events"))
        assert body["success"] is True

    def test_agent_state_unknown_key(self, client):
        """不存在的 key 不能 500"""
        resp = client.get("/api/agent_state/does-not-exist")
        assert resp.status_code == 200
        assert "success" in resp.get_json()


class TestStaticAndIndex:
    def test_index_renders(self, client):
        resp = client.get("/")
        assert resp.status_code == 200
        assert resp.data  # 有 HTML 内容


class TestCacheHelper:
    def test_miss_then_hit(self):
        v, hit = web_dashboard._cache_get("unit-test-key")
        assert v is None and hit is False
        web_dashboard._cache_set("unit-test-key", {"x": 1})
        v, hit = web_dashboard._cache_get("unit-test-key")
        assert v == {"x": 1} and hit is True
        web_dashboard._cache.clear()

