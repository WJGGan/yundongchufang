"""数据资产加载：动作库、知识卡片、mock 档案、急症词表。

启动时一次性读入内存，v1 不引入数据库。
"""

from __future__ import annotations

import json
import secrets
import time
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


CUSTOM_DIR = DATA_DIR / "custom_students"


def custom_students() -> list[dict[str, Any]]:
    """用户在前端录入并保存的档案。不做缓存，提交后立即可见。"""
    if not CUSTOM_DIR.is_dir():
        return []
    students = []
    for path in sorted(CUSTOM_DIR.glob("*.json")):
        try:
            with path.open(encoding="utf-8") as handle:
                students.append(json.load(handle))
        except (OSError, json.JSONDecodeError):
            continue
    return students


def all_students() -> list[dict[str, Any]]:
    return mock_students() + custom_students()


def save_custom_student(record: dict[str, Any]) -> dict[str, Any]:
    """把用户录入的档案保存为一份新的 JSON 文件，并返回带学号的完整档案。

    学号始终由服务端生成，不采用用户输入，避免覆盖已有档案或拼出路径。
    """
    CUSTOM_DIR.mkdir(parents=True, exist_ok=True)
    student_id = f"CU{time.strftime('%Y%m%d%H%M%S')}{secrets.token_hex(2).upper()}"
    record["student_id"] = student_id
    path = CUSTOM_DIR / f"{student_id}.json"
    with path.open("w", encoding="utf-8") as handle:
        json.dump(record, handle, ensure_ascii=False, indent=2)
    return record


def find_student(student_id: str) -> dict[str, Any] | None:
    for student in all_students():
        if student["student_id"] == student_id:
            return student
    return None


PREGENERATED_DIR = DATA_DIR / "pregenerated"


def _safe_student_id(student_id: str) -> str | None:
    """只接受档案库中真实存在的学号，避免用户输入拼进文件路径。"""
    return student_id if find_student(student_id) is not None else None


def pregenerated_ids() -> list[str]:
    """已预生成结果的学号列表。不做缓存，脚本随时可能写入新文件。"""
    if not PREGENERATED_DIR.is_dir():
        return []
    ids = []
    for path in PREGENERATED_DIR.glob("*.json"):
        if _safe_student_id(path.stem):
            ids.append(path.stem)
    return sorted(ids)


def load_pregenerated(student_id: str) -> dict[str, Any] | None:
    safe_id = _safe_student_id(student_id)
    if safe_id is None:
        return None
    path = PREGENERATED_DIR / f"{safe_id}.json"
    if not path.is_file():
        return None
    with path.open(encoding="utf-8") as handle:
        return json.load(handle)
