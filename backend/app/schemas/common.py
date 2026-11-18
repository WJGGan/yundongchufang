"""跨模块共享的基础 schema。"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict


class Versions(BaseModel):
    model_config = ConfigDict(extra="allow")

    exercise_library: str = ""
    knowledge_base: str = ""
    prompt: str = ""
    model: str = ""
