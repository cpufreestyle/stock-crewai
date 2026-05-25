"""监控告警模块 - 关键事件推送通知

支持 Server酱（WeChat）、自定义 Webhook
"""
import json
import os
import requests
from datetime import datetime
from typing import Optional

from safe_io import safe_load_json, safe_save_json


# 告警配置
ALERT_CONFIG_FILE = "alert_config.json"


def _load_alert_config() -> dict:
    return safe_load_json(ALERT_CONFIG_FILE, default={
        "enabled": False,
        "server_chan_key": "",       # Server酱 SendKey
        "webhook_url": "",           # 自定义 Webhook URL
        "alert_types": {
            "stop_loss": True,       # 止损触发
            "take_profit": True,     # 止盈触发
            "circuit_breaker": True, # 风控熔断
            "buy": False,            # 买入（默认关，太频繁）
            "sell": False,           # 卖出
            "error": True,           # 异常错误
        },
    })


def _save_alert_config(config: dict):
    safe_save_json(ALERT_CONFIG_FILE, config)


def configure_alert(server_chan_key: str = "", webhook_url: str = "", enabled: bool = True):
    """配置告警推送"""
    config = _load_alert_config()
    if server_chan_key:
        config["server_chan_key"] = server_chan_key
    if webhook_url:
        config["webhook_url"] = webhook_url
    config["enabled"] = enabled
    _save_alert_config(config)


def send_alert(title: str, content: str, alert_type: str = "error"):
    """发送告警通知
    
    Args:
        title: 告警标题
        content: 告警内容
        alert_type: 告警类型 (stop_loss/take_profit/circuit_breaker/buy/sell/error)
    """
    config = _load_alert_config()
    
    if not config.get("enabled"):
        return False
    
    # 检查该类型是否启用
    if not config.get("alert_types", {}).get(alert_type, False):
        return False
    
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    full_content = f"**{timestamp}**\n\n{content}"
    
    sent = False
    
    # Server酱推送
    key = config.get("server_chan_key", "")
    if key:
        try:
            r = requests.post(
                f"https://sctapi.ftqq.com/{key}.send",
                data={"title": title, "desp": full_content},
                timeout=10,
            )
            if r.status_code == 200:
                sent = True
        except Exception:
            pass
    
    # 自定义 Webhook
    url = config.get("webhook_url", "")
    if url:
        try:
            r = requests.post(
                url,
                json={"title": title, "content": full_content, "type": alert_type},
                timeout=10,
            )
            if r.status_code < 300:
                sent = True
        except Exception:
            pass
    
    return sent


# ============= 便捷函数 =============

def alert_stop_loss(code: str, name: str, price: float, stop_loss: float, pnl_pct: float):
    """止损告警"""
    send_alert(
        f"🚨 止损触发: {name}",
        f"- 股票: {code} {name}\n- 现价: {price:.2f}\n- 止损线: {stop_loss:.2f}\n- 亏损: {pnl_pct:+.2f}%",
        alert_type="stop_loss",
    )


def alert_take_profit(code: str, name: str, price: float, take_profit: float, pnl_pct: float):
    """止盈告警"""
    send_alert(
        f"💰 止盈触发: {name}",
        f"- 股票: {code} {name}\n- 现价: {price:.2f}\n- 止盈线: {take_profit:.2f}\n- 收益: {pnl_pct:+.2f}%",
        alert_type="take_profit",
    )


def alert_circuit_breaker(reason: str, remaining_minutes: int):
    """熔断告警"""
    send_alert(
        f"⛔ 风控熔断",
        f"- 原因: {reason}\n- 冷却: {remaining_minutes}分钟",
        alert_type="circuit_breaker",
    )


def alert_error(error_msg: str):
    """异常告警"""
    send_alert(
        f"❌ 交易异常",
        f"- 错误: {error_msg}",
        alert_type="error",
    )
