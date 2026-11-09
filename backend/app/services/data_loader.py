"""数据资产加载：动作库、知识卡片、mock 档案、急症词表。

启动时一次性读入内存，v1 不引入数据库。
"""

from __future__ import annotations

import json
from functools import lru_cache
from typing import Any

from app.config import DATA_DIR


def _load(filename: str) -> dict[str, Any]:
    with (DATA_DIR / filename).open(encoding="utf-8") as handle:
        return json.load(handle)


@lru_cache(maxsize=1)
def exercise_library() -> dict[str, Any]:
    return _load("exercises.json")


@lru_cache(maxsize=1)
def exercise_index() -> dict[str, dict[str, Any]]:
    return {item["id"]: item for item in exercise_library()["exercises"]}


@lru_cache(maxsize=1)
def knowledge_base() -> dict[str, Any]:
    return _load("knowledge.json")


@lru_cache(maxsize=1)
def knowledge_cards() -> list[dict[str, Any]]:
    return knowledge_base()["cards"]


@lru_cache(maxsize=1)
def mock_students() -> list[dict[str, Any]]:
    return _load("mock_students.json")["students"]


@lru_cache(maxsize=1)
def emergency_rules() -> dict[str, Any]:
    return _load("emergency_keywords.json")


def find_student(student_id: str) -> dict[str, Any] | None:
    for student in mock_students():
        if student["student_id"] == student_id:
            return student
    return None
