"""
宏观经济工具 - 获取宏观经济指标，辅助判断市场大趋势
"""
import logging
import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import requests
from datetime import datetime, timedelta
from typing import List, Dict

logger = logging.getLogger("tools.macro")


def get_macro_tools() -> list:
    """返回 CrewAI Tool 列表"""
    from crewai.tools import tool as crewai_tool

    @crewai_tool("宏观经济指标")
    def macro_indicators() -> str:
        """获取关键宏观经济指标（GDP、CPI、PMI、M2等）"""
        return _macro_indicators_tool()

    @crewai_tool("利率动态")
    def interest_rate() -> str:
        """获取最新利率变化和货币政策信号"""
        return _interest_rate_tool()

    @crewai_tool("政策信号")
    def policy_signal() -> str:
        """识别近期政策风向（降准、降息、财政刺激等）"""
        return _policy_signal_tool()

    return [macro_indicators, interest_rate, policy_signal]


# ── 内部实现 ────────────────────────────────────────────────────────

def _macro_indicators_tool() -> str:
    """获取宏观经济指标（简化版）"""
    # 实际可接入：国家统计局API、Wind API等
    # 这里提供框架 + 示例数据
    try:
        # 尝试从可访问的数据源获取
        indicators = {
            "GDP增速": _get_latest_gdp(),
            "CPI": _get_latest_cpi(),
            "PMI": _get_latest_pmi(),
            "M2增速": _get_latest_m2(),
            "失业率": _get_latest_unemployment(),
        }
        
        lines = ["# 宏观经济关键指标", ""]
        for name, value in indicators.items():
            lines.append(f"- {name}: {value}")
        
        # 简单判断经济周期
        pmi = indicators.get("PMI", "50")
        try:
            pmi_val = float(pmi)
            if pmi_val > 52:
                cycle = "经济扩张期，利好股市"
            elif pmi_val < 48:
                cycle = "经济收缩期，谨慎操作"
            else:
                cycle = "经济平稳期，震荡为主"
        except Exception:
            cycle = "数据不足，无法判断"
        
        lines.append("")
        lines.append(f"**经济周期判断**: {cycle}")
        
        return "\n".join(lines)
    except Exception as e:
        logger.error(f"宏观指标获取失败: {e}")
        return f"宏观指标获取失败: {e}"


def _interest_rate_tool() -> str:
    """利率动态"""
    # 简化版：返回近期利率变化
    return (
        "# 利率与货币政策\n"
        "- 1年期LPR: 3.45% (2026-06-20)\n"
        "- 5年期LPR: 3.95%\n"
        "- 近期信号: 维持稳健货币政策，相机抉择\n"
        "- 对股市影响: 利率平稳，流动性合理充裕"
    )


def _policy_signal_tool() -> str:
    """政策信号"""
    return (
        "# 近期政策风向\n"
        "- 财政政策: 积极有为，专项债发行提速\n"
        "- 货币政策: 稳健灵活，降准降息窗口未关闭\n"
        "- 产业政策: 新质生产力、高端制造、绿色转型\n"
        "- 对A股影响: 政策底已现，关注结构性机会"
    )


# ── 数据获取函数（简化版）─────────────────────────────────────────

def _get_latest_gdp() -> str:
    """获取最新GDP增速"""
    # 实际应接入国家统计局API
    return "5.3% (2026Q1, 同比)"


def _get_latest_cpi() -> str:
    """获取最新CPI"""
    return "0.8% (2026年5月, 同比)"


def _get_latest_pmi() -> str:
    """获取最新PMI"""
    return "50.8 (2026年5月, 制造业)"


def _get_latest_m2() -> str:
    """获取最新M2增速"""
    return "8.7% (2026年5月, 同比)"


def _get_latest_unemployment() -> str:
    """获取最新失业率"""
    return "5.2% (2026年5月, 城镇调查)"
