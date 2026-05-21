"""企业微信通知模块"""
import sys; sys.stdout.reconfigure(encoding='utf-8')
import requests
import json
from datetime import datetime

# 企业微信 webhook 地址（需替换）
# 获取方式：企业微信后台 → 应用管理 → 自建应用 → 查看 Secret → 接收消息 → Webhook
WEBHOOK_URL = "https://qyapi.weixin.qq.com/cgi-bin/webhook/send?key=YOUR_KEY_HERE"


def send_text(content: str):
    """发送文本消息"""
    if WEBHOOK_URL == "https://qyapi.weixin.qq.com/cgi-bin/webhook/send?key=YOUR_KEY_HERE":
        print("[通知] Webhook未配置，跳过")
        return False

    data = {
        "msgtype": "text",
        "text": {
            "content": content
        }
    }

    try:
        r = requests.post(WEBHOOK_URL, json=data, timeout=5)
        result = r.json()
        if result.get("errcode") == 0:
            print("[通知] 发送成功")
            return True
        else:
            print("[通知] 发送失败: " + str(result))
            return False
    except Exception as e:
        print("[通知] 异常: " + str(e))
        return False


def send_markdown(content: str):
    """发送Markdown消息"""
    if WEBHOOK_URL == "https://qyapi.weixin.qq.com/cgi-bin/webhook/send?key=YOUR_KEY_HERE":
        print("[通知] Webhook未配置，跳过")
        return False

    data = {
        "msgtype": "markdown",
        "markdown": {
            "content": content
        }
    }

    try:
        r = requests.post(WEBHOOK_URL, json=data, timeout=5)
        result = r.json()
        if result.get("errcode") == 0:
            print("[通知] 发送成功")
            return True
        else:
            print("[通知] 发送失败: " + str(result))
            return False
    except Exception as e:
        print("[通知] 异常: " + str(e))
        return False


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
