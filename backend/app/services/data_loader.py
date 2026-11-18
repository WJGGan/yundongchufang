"""数据资产加载：动作库、知识卡片、mock 档案、急症词表。

启动时一次性读入内存，v1 不引入数据库。
"""

from __future__ import annotations

import json
import re
import secrets
import time
from datetime import datetime, timedelta, timezone
from functools import lru_cache
from pathlib import Path
from typing import Any

from app.config import DATA_DIR, settings


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


PROFILE_DIR = DATA_DIR / "profiles"
PRESCRIPTION_DIR = DATA_DIR / "prescriptions"

_UNSAFE_ID_RE = re.compile(r"[^A-Za-z0-9_-]")

_CST = timezone(timedelta(hours=8))


def _now_iso() -> str:
    return datetime.now(_CST).isoformat(timespec="seconds")


def _archive_result(directory: Path, payload: dict[str, Any]) -> Path:
    """留档一份生成结果，同一学号仅保留最新一份，重复生成直接覆盖。

    学号来自请求体，先清洗为安全字符集，避免用户输入拼进文件路径。
    """
    directory.mkdir(parents=True, exist_ok=True)
    student_id = _UNSAFE_ID_RE.sub("", str(payload.get("student_id", ""))) or "unknown"
    path = directory / f"{student_id}.json"
    with path.open("w", encoding="utf-8") as handle:
        json.dump(payload, handle, ensure_ascii=False, indent=2)
    return path


def save_profile_result(profile: dict[str, Any]) -> Path:
    """把档案理解生成的画像 JSON 落盘到 data/profiles，同一学生仅保留最新一份。"""
    return _archive_result(PROFILE_DIR, profile)


def save_prescription_result(prescription: dict[str, Any]) -> Path:
    """把生成的处方 JSON 落盘到 data/prescriptions，同一学生仅保留最新一份。"""
    return _archive_result(PRESCRIPTION_DIR, prescription)


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


GENERATED_DIR = DATA_DIR / "generated"


def load_generated(student_id: str) -> dict[str, Any] | None:
    """线上生成后保存的最新快照，结构与预生成文件一致。"""
    safe_id = _safe_student_id(student_id)
    if safe_id is None:
        return None
    path = GENERATED_DIR / f"{safe_id}.json"
    if not path.is_file():
        return None
    try:
        with path.open(encoding="utf-8") as handle:
            return json.load(handle)
    except (OSError, json.JSONDecodeError):
        return None


def record_generated_result(
    student_id: str | None,
    *,
    name: str = "",
    profile: dict[str, Any] | None = None,
    prescription: dict[str, Any] | None = None,
    emergency: dict[str, Any] | None = None,
) -> None:
    """把一次线上生成的结果并入 generated/<学号>.json 快照，供「载入已有结果」读取。

    只接受档案库中真实存在的学号；落盘是旁路留档，磁盘问题不中断生成流程。
    合并规则按安全优先：
      - 急症熔断：旧画像与处方不再可信，整份重置为急症快照
      - 新画像判定不宜开处方：保留画像并记录 blocked，清掉旧处方
      - 仅重新生成画像：更新画像，保留上一次的处方
      - 生成出处方：画像与处方成对更新
    """
    safe_id = _safe_student_id(str(student_id or ""))
    if safe_id is None:
        return

    snapshot = load_generated(safe_id) or {
        "student_id": safe_id,
        "profile": None,
        "prescription": None,
        "emergency": None,
        "blocked": None,
    }
    snapshot.update(
        {
            "name": name or snapshot.get("name", ""),
            "generated_at": _now_iso(),
            "model": settings.active_model,
            "thinking": settings.thinking_enabled,
        }
    )

    if emergency is not None:
        snapshot.update(
            {"emergency": emergency, "profile": None, "prescription": None, "blocked": None}
        )
    else:
        snapshot["emergency"] = None
        if profile is not None:
            snapshot["profile"] = profile
            safety = profile.get("safety") or {}
            if safety.get("can_generate_prescription", True):
                snapshot["blocked"] = None
            else:
                snapshot["blocked"] = {
                    "risk_level": safety.get("risk_level", ""),
                    "referral_advice": safety.get("referral_advice") or [],
                    "notes": safety.get("notes") or [],
                }
                snapshot["prescription"] = None
        if prescription is not None:
            snapshot["prescription"] = prescription
            snapshot["blocked"] = None

    try:
        GENERATED_DIR.mkdir(parents=True, exist_ok=True)
        path = GENERATED_DIR / f"{safe_id}.json"
        with path.open("w", encoding="utf-8") as handle:
            json.dump(snapshot, handle, ensure_ascii=False, indent=2)
    except OSError:
        pass


def saved_result_ids() -> list[str]:
    """所有有已生成结果可加载的学号：线上生成的快照 ∪ 脚本预生成。"""
    ids = set(pregenerated_ids())
    if GENERATED_DIR.is_dir():
        for path in GENERATED_DIR.glob("*.json"):
            if _safe_student_id(path.stem):
                ids.add(path.stem)
    return sorted(ids)


def load_saved_result(student_id: str) -> dict[str, Any] | None:
    """读取某学生可加载的生成结果；线上快照与预生成同时存在时取较新的一份。"""
    generated = load_generated(student_id)
    pregenerated = load_pregenerated(student_id)
    if generated and pregenerated:
        return max(
            generated, pregenerated, key=lambda item: str(item.get("generated_at") or "")
        )
    return generated or pregenerated
