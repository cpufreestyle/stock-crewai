#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""验证 litellm ollama provider (原生 /api/chat) + think:false 能否正常做工具调用。"""
import sys
sys.stdout.reconfigure(encoding="utf-8")
sys.stderr.reconfigure(encoding="utf-8")

from crewai import Agent, Task, Crew, Process, LLM
from crewai.tools import tool


@tool("get_price")
def get_price(symbol: str) -> str:
    """查询某只股票的最新价格。输入为股票代码。"""
    return f"{symbol}: 100.00 元"


def main():
    # 用 litellm 的 ollama provider，直连原生 /api/chat，think=False 关思考
    llm = LLM(
        model="ollama/qwen3.8:q2",
        api_key="ollama",
        base_url="http://127.0.0.1:11434",
        temperature=0.3,
        max_tokens=800,
        think=False,
    )
    print(f"[LLM] {getattr(llm, 'model', '?')} @ {getattr(llm, 'api_base', '?')}")
    agent = Agent(
        role="测试分析师",
        goal="用一句话回答",
        backstory="你是一个简洁的A股分析师。",
        llm=llm,
        tools=[get_price],
        verbose=True,
        allow_delegation=False,
    )
    task = Task(
        description="先调用 get_price 工具查询 000001 的价格，然后一句话总结。",
        expected_output="一句话结论",
        agent=agent,
    )
    crew = Crew(agents=[agent], tasks=[task], process=Process.sequential, verbose=True)
    res = crew.kickoff()
    out = str(res)
    print(f"\n=== RESULT({len(out)}字符) ===\n{out}\n")
    print("[SMOKE ollama PASSED]" if out.strip() else "[SMOKE ollama FAILED]")


if __name__ == "__main__":
    main()
