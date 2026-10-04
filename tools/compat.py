# -*- coding: utf-8 -*-
"""CrewAI BaseTool 的再导出

crewai 是本项目的硬依赖（crew.py / tasks.py 在模块层无条件 import，
且 requirements.txt 已声明），原先这里的“未安装 crewai 时用 pydantic 兜底”
分支永远走不到，属于死代码，已删除。
"""
from crewai.tools import BaseTool

__all__ = ["BaseTool"]

