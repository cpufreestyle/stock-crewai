#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""轻量冒烟测试：验证 CrewAI -> litellm -> Ollama(qwen3.8) 链路是否打通。"""
import os
import sys
sys.stdout.reconfigure(encoding="utf-8")
sys.stderr.reconfigure(encoding="utf-8")

from dotenv import load_dotenv
load_dotenv()

from agents.llm import get_llm
from crewai import Agent, Task, Crew, Process


def main():
    llm = get_llm()
    if llm is None:
        print("[FAIL] get_llm() 返回 None（API Key / 模型未配置）")
        return 1
    print(f"[OK] LLM 实例已创建: {getattr(llm, 'model', '?')} @ {getattr(llm, 'api_base', '?')}")

    agent = Agent(
        role="测试分析师",
        goal="用一句话回答用户问题",
        backstory="你是一个简洁的A股分析师，回答尽量简短。",
        llm=llm,
        verbose=True,
        allow_delegation=False,
    )
    task = Task(
        description="用一句话回答：今天A股大盘整体情绪偏多还是偏空？",
        expected_output="一句话结论",
        agent=agent,
    )
    crew = Crew(agents=[agent], tasks=[task], process=Process.sequential, verbose=True)
    print("\n=== 开始 kickoff（单次 LLM 调用，预期 10-40s）===\n")
    res = crew.kickoff()
    out = str(res)
    print(f"\n=== RESULT({len(out)}字符) ===\n{out}\n")
    print("[SMOKE TEST PASSED]" if out.strip() else "[SMOKE TEST FAILED: 空输出]")
    return 0


if __name__ == "__main__":
    sys.exit(main())
