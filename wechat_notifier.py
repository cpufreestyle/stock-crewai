"""企业微信 + 个人微信通知模块（统一通知入口）

双通道：
1. 企业微信群机器人：.env 的 WECHAT_WEBHOOK_URL
2. Server酱（个人微信）：.env 的 SERVERCHAN_SENDKEY，消息直达个人微信
   （sct.ftqq.com 用目标微信扫码登录获取 SendKey）

任一通道未配置自动跳过；两通道独立失败互不影响。
alert.py 的 Server酱/Webhook 渠道也委托到此处。
"""
import sys; sys.stdout.reconfigure(encoding='utf-8')
import os
import requests
import json
import logging
from datetime import datetime

logger = logging.getLogger(__name__)

# 企业微信 webhook 地址（从 .env 读取）
WEBHOOK_URL = os.getenv("WECHAT_WEBHOOK_URL", "")
# Server酱 SendKey（从 .env 读取，推送到个人微信）
SERVERCHAN_SENDKEY = os.getenv("SERVERCHAN_SENDKEY", "")


def _get_webhook() -> str:
    """延迟读取环境变量（支持运行时通过 .env 热加载）"""
    return os.getenv("WECHAT_WEBHOOK_URL", WEBHOOK_URL)


def _get_serverchan_key() -> str:
    """延迟读取 Server酱 SendKey"""
    return os.getenv("SERVERCHAN_SENDKEY", SERVERCHAN_SENDKEY)


def _send_serverchan(title: str, content: str) -> bool:
    """Server酱推送（直达个人微信），content 支持 Markdown"""
    key = _get_serverchan_key()
    if not key:
        return False
    try:
        r = requests.post(
            f"https://sctapi.ftqq.com/{key}.send",
            data={"title": title[:32], "desp": content[:3000]},
            timeout=10,
        )
        if r.status_code == 200 and r.json().get("code") == 0:
            logger.info("[通知] Server酱推送成功")
            return True
        logger.warning("[通知] Server酱推送失败: %s", r.text[:200])
        return False
    except Exception as e:
        logger.warning("[通知] Server酱异常: %s", e)
        return False


def send_text(content: str):
    """发送文本消息（双通道：企业微信群 + 个人微信）"""
    sent = False
    url = _get_webhook()
    if url:
        data = {"msgtype": "text", "text": {"content": content}}
        try:
            r = requests.post(url, json=data, timeout=5)
            result = r.json()
            if result.get("errcode") == 0:
                print("[通知] 企业微信发送成功")
                sent = True
            else:
                print("[通知] 企业微信发送失败: " + str(result))
        except Exception as e:
            print("[通知] 企业微信异常: " + str(e))
    title = content.splitlines()[0][:32] if content else "通知"
    if _send_serverchan(title, content):
        sent = True
    if not sent:
        logger.info("[通知] 所有通道未配置或发送失败")
    return sent


def send_markdown(content: str):
    """发送Markdown消息（双通道：企业微信群 + 个人微信）"""
    sent = False
    url = _get_webhook()
    if url:
        data = {"msgtype": "markdown", "markdown": {"content": content}}
        try:
            r = requests.post(url, json=data, timeout=5)
            result = r.json()
            if result.get("errcode") == 0:
                print("[通知] 企业微信发送成功")
                sent = True
            else:
                print("[通知] 企业微信发送失败: " + str(result))
        except Exception as e:
            print("[通知] 企业微信异常: " + str(e))
    title = content.splitlines()[0].lstrip("#").strip()[:32] if content else "通知"
    if _send_serverchan(title, content):
        sent = True
    if not sent:
        logger.info("[通知] 所有通道未配置或发送失败")
    return sent


def notify_buy(stock_code: str, stock_name: str, shares: int, price: float, reason: str = ""):
    """买入通知"""
    content = """### 📈 买入通知

**股票**: {name} ({code})
**数量**: {shares}股
**价格**: {price:.2f}元
**金额**: {amount:,.2f}元
**原因**: {reason}
**时间**: {time}""".format(
        name=stock_name,
        code=stock_code,
        shares=shares,
        price=price,
        amount=shares * price,
        reason=reason if reason else "自动买入",
        time=datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    )

    return send_markdown(content)


def notify_sell(stock_code: str, stock_name: str, shares: int, price: float, pnl: float, reason: str = ""):
    """卖出通知"""
    icon = "📈" if pnl > 0 else "📉"
    pnl_str = "{:+.2f}".format(pnl)

    content = """### {icon} 卖出通知

**股票**: {name} ({code})
**数量**: {shares}股
**价格**: {price:.2f}元
**盈亏**: {pnl_str}元
**原因**: {reason}
**时间**: {time}""".format(
        icon=icon,
        name=stock_name,
        code=stock_code,
        shares=shares,
        price=price,
        pnl=pnl,
        pnl_str=pnl_str,
        reason=reason if reason else "自动卖出",
        time=datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    )

    return send_markdown(content)


def notify_portfolio(portfolio: dict):
    """持仓日报"""
    positions = portfolio.get("positions", {})
    if not positions:
        content = "### 📊 持仓日报\n\n当前**空仓**，现金: {:.2f}元".format(portfolio.get("cash", 0))
    else:
        lines = ["### 📊 持仓日报\n"]
        lines.append("**总资产**: {:.2f}元".format(portfolio.get("total_value", 0)))
        lines.append("**总收益**: {:+.2f}%\n".format(portfolio.get("total_return_pct", 0)))
        lines.append("**持仓明细**:")

        for code, pos in positions.items():
            last_price = pos.get("last_price", pos["avg_cost"])
            pnl_pct = (last_price - pos["avg_cost"]) / pos["avg_cost"] * 100
            icon = "📈" if pnl_pct > 0 else "📉" if pnl_pct < 0 else "➡️"
            lines.append("{} {} {}: {}股 @ {:.2f}元 ({:+.2f}%)".format(
                icon, code, pos["name"], pos["shares"], last_price, pnl_pct
            ))

        content = "\n".join(lines)

    return send_markdown(content)


def notify_error(error_msg: str):
    """错误通知"""
    content = """### ⚠️ 系统错误

**时间**: {time}
**错误**: {msg}""".format(
        time=datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        msg=error_msg[:500]  # 限制长度
    )

    return send_markdown(content)


if __name__ == "__main__":
    # 测试
    print("测试通知功能...")

    # 测试买入通知
    notify_buy("000333", "美的集团", 200, 81.86, "自动买入 止损75.31 目标98.23")

    # 测试卖出通知
    notify_sell("601012", "隆基绿能", 1200, 15.34, -108.00, "止损触发")

    # 测试持仓日报
    import portfolio_tracker as pt
    portfolio = pt.load_portfolio()
    notify_portfolio(portfolio)

    print("测试完成")
