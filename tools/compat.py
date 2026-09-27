"""
CrewAI 兼容层 - 无需安装 crewai 也能运行 Agent 工具

如果 crewai 可用，使用原生 BaseTool；
否则，提供基于 pydantic BaseModel 的最小兼容实现。
"""

try:
    from crewai.tools import BaseTool
except ImportError:
    from pydantic import BaseModel

    class BaseTool(BaseModel):
        """最小 BaseTool 兼容实现（无需 crewai）"""
        name: str = ""
        description: str = ""

        class Config:
            arbitrary_types_allowed = True

        def _run(self, **kwargs) -> str:
            raise NotImplementedError

        def run(self, **kwargs) -> str:
            return self._run(**kwargs)

        def __call__(self, **kwargs) -> str:
            return self.run(**kwargs)
