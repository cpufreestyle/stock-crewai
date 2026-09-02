"""
通知模块双通道测试（企业微信群 + Server酱个人微信）
运行: pytest tests/test_wechat_notifier.py -v
"""
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

# 添加项目根目录到 path
sys.path.insert(0, str(Path(__file__).parent.parent))

import wechat_notifier as wn


@pytest.fixture(autouse=True)
def clean_env(monkeypatch):
    """每个测试隔离通知配置"""
    monkeypatch.delenv("WECHAT_WEBHOOK_URL", raising=False)
    monkeypatch.delenv("SERVERCHAN_SENDKEY", raising=False)
    yield


class TestServerChan:
    """Server酱 个人微信通道"""

    def test_skipped_when_no_key(self):
        assert wn._send_serverchan("标题", "内容") is False

    @patch("wechat_notifier.requests.post")
    def test_sends_with_key(self, mock_post, monkeypatch):
        monkeypatch.setenv("SERVERCHAN_SENDKEY", "SCT-test-key")
        mock_post.return_value = MagicMock(status_code=200, json=lambda: {"code": 0})
        assert wn._send_serverchan("标题", "内容") is True
        args, kwargs = mock_post.call_args
        assert "sctapi.ftqq.com/SCT-test-key.send" in args[0]
        assert kwargs["data"]["title"] == "标题"
        assert kwargs["data"]["desp"] == "内容"

    @patch("wechat_notifier.requests.post")
    def test_api_error_returns_false(self, mock_post, monkeypatch):
        monkeypatch.setenv("SERVERCHAN_SENDKEY", "SCT-bad-key")
        mock_post.return_value = MagicMock(status_code=200, json=lambda: {"code": 40001})
        assert wn._send_serverchan("标题", "内容") is False

    @patch("wechat_notifier.requests.post")
    def test_network_error_returns_false(self, mock_post, monkeypatch):
        monkeypatch.setenv("SERVERCHAN_SENDKEY", "SCT-key")
        mock_post.side_effect = ConnectionError("网络断开")
        assert wn._send_serverchan("标题", "内容") is False


class TestDualChannel:
    """send_markdown 双通道行为"""

    MD_CONTENT = "### 交易信号\n\n- 买入建议"

    def test_wechat_only(self, monkeypatch):
        monkeypatch.setenv("WECHAT_WEBHOOK_URL", "https://qyapi.example/webhook")
        with patch("wechat_notifier.requests.post") as mock_post:
            mock_post.return_value = MagicMock(status_code=200, json=lambda: {"errcode": 0})
            assert wn.send_markdown(self.MD_CONTENT) is True
        # 只调了一次（企业微信），Server酱无 key 不调
        assert mock_post.call_count == 1

    def test_serverchan_only(self, monkeypatch):
        monkeypatch.setenv("SERVERCHAN_SENDKEY", "SCT-key")
        with patch("wechat_notifier.requests.post") as mock_post:
            mock_post.return_value = MagicMock(status_code=200, json=lambda: {"code": 0})
            assert wn.send_markdown(self.MD_CONTENT) is True
        assert mock_post.call_count == 1

    def test_both_channels(self, monkeypatch):
        monkeypatch.setenv("WECHAT_WEBHOOK_URL", "https://qyapi.example/webhook")
        monkeypatch.setenv("SERVERCHAN_SENDKEY", "SCT-key")
        with patch("wechat_notifier.requests.post") as mock_post:
            # 企业微信 errcode=0 成功；Server酱 code=0 成功
            mock_post.side_effect = [
                MagicMock(status_code=200, json=lambda: {"errcode": 0}),
                MagicMock(status_code=200, json=lambda: {"code": 0}),
            ]
            assert wn.send_markdown(self.MD_CONTENT) is True
        assert mock_post.call_count == 2

    def test_none_configured_skips(self):
        # 双通道都未配置：不抛异常，返回 False
        assert wn.send_markdown(self.MD_CONTENT) is False

    def test_title_extracted_from_header(self, monkeypatch):
        """Server酱 title 应取 Markdown 首行并去除 # 前缀"""
        monkeypatch.setenv("SERVERCHAN_SENDKEY", "SCT-key")
        with patch("wechat_notifier.requests.post") as mock_post:
            mock_post.return_value = MagicMock(status_code=200, json=lambda: {"code": 0})
            wn.send_markdown(self.MD_CONTENT)
        assert mock_post.call_args.kwargs["data"]["title"] == "交易信号"


class TestSendText:
    def test_dual_channel_text(self, monkeypatch):
        monkeypatch.setenv("WECHAT_WEBHOOK_URL", "https://qyapi.example/webhook")
        monkeypatch.setenv("SERVERCHAN_SENDKEY", "SCT-key")
        with patch("wechat_notifier.requests.post") as mock_post:
            mock_post.side_effect = [
                MagicMock(status_code=200, json=lambda: {"errcode": 0}),
                MagicMock(status_code=200, json=lambda: {"code": 0}),
            ]
            assert wn.send_text("纯文本通知") is True
        assert mock_post.call_count == 2
        # text 通道的 Server酱 title 取首行
        assert mock_post.call_args.kwargs["data"]["title"] == "纯文本通知"
