"""档案理解服务：原始档案 → 体质画像 + 安全评估。"""

from __future__ import annotations

from collections.abc import AsyncIterator
from datetime import datetime, timedelta, timezone
from typing import Any

from pydantic import ValidationError

from app.config import settings
from app.llm.provider import LLMError, extract_json, get_provider
from app.prompts import profile as prompt
from app.schemas.profile import ProfileResult, Versions
from app.schemas.record import HealthRecord
from app.services.data_loader import knowledge_cards

CST = timezone(timedelta(hours=8))

DISCLAIMER = "本画像由 AI 基于所提供档案生成，仅供参考，不作为医疗诊断依据。"


def now_iso() -> str:
    return datetime.now(CST).isoformat(timespec="seconds")


def current_versions() -> Versions:
    return Versions(
        exercise_library=settings.exercise_library_version,
        knowledge_base=settings.knowledge_base_version,
        prompt=settings.prompt_version,
        model=settings.active_model,
    )


def _valid_card_ids() -> set[str]:
    return {card["id"] for card in knowledge_cards()}


def _strip_unknown_refs(payload: dict[str, Any]) -> list[str]:
    """移除不存在的知识卡片引用，返回被移除的 ID，避免前端溯源点击失效。"""
    valid = _valid_card_ids()
    dropped: list[str] = []

    for dimension in payload.get("fitness_dimensions") or []:
        refs = dimension.get("knowledge_refs") or []
        kept = [ref for ref in refs if ref in valid]
        dropped.extend(ref for ref in refs if ref not in valid)
        dimension["knowledge_refs"] = kept

    return sorted(set(dropped))


async def stream_profile(record: HealthRecord) -> AsyncIterator[tuple[str, Any]]:
    """流式生成画像。

    产出 ("token", 片段) 供前端实时展示模型输出，("retry", 原因) 表示触发了一次
    重生成，最后产出 ("result", ProfileResult) 或 ("error", 说明)。
    """
    provider = get_provider()
    cards = knowledge_cards()
    record_view = record.to_prompt_dict()

    user_prompt = prompt.build_user_prompt(record_view, cards)
    last_error = ""

    for attempt in range(2):
        if attempt == 1:
            yield ("retry", last_error)
            user_prompt = prompt.build_repair_prompt(record_view, cards, last_error)

        buffer: list[str] = []
        try:
            async for chunk in provider.stream(prompt.SYSTEM, user_prompt):
                buffer.append(chunk)
                yield ("token", chunk)
            payload = extract_json("".join(buffer))
        except LLMError as exc:
            last_error = str(exc)
            continue

        dropped = _strip_unknown_refs(payload)
        payload.update(
            {
                "student_id": record.student_id,
                "name": record.name,
                "generated_at": now_iso(),
                "versions": current_versions().model_dump(),
                "disclaimer": DISCLAIMER,
            }
        )

        try:
            result = ProfileResult.model_validate(payload)
        except ValidationError as exc:
            last_error = exc.json(indent=2)
            continue

        if dropped:
            result.safety.notes.append(
                "以下知识卡片引用不存在，已移除：" + "、".join(dropped)
            )
        yield ("result", result)
        return

    yield ("error", f"画像生成两次均未通过结构校验：{last_error}")


async def analyze_profile(record: HealthRecord) -> ProfileResult:
    """非流式入口：消费 stream_profile，供同步端点与脚本使用。"""
    error = "画像生成失败"
    async for kind, payload in stream_profile(record):
        if kind == "result":
            return payload
        if kind == "error":
            error = str(payload)
    raise LLMError(error)
