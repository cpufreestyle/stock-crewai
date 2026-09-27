"""
tools package initialization
"""
from tools.market_tools import get_market_tools
from tools.stock_tools import get_stock_tools
from tools.risk_tools import get_risk_tools
from tools.trade_tools import get_trade_tools
from tools.notify_tools import get_notify_tools
from tools.sentiment_tools import get_sentiment_tools
from tools.macro_tools import get_macro_tools


def get_all_tools() -> list:
    """Return all tools combined"""
    return (
        get_market_tools() +
        get_stock_tools() +
        get_risk_tools() +
        get_trade_tools() +
        get_notify_tools() +
        get_sentiment_tools() +
        get_macro_tools()
    )


__all__ = [
    "get_market_tools", "get_stock_tools", "get_risk_tools",
    "get_trade_tools", "get_notify_tools",
    "get_sentiment_tools", "get_macro_tools",
    "get_all_tools",
]
