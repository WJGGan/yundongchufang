"""处方生成服务：画像 + 请求参数 → 一人一策运动处方。

动作候选集由代码按安全标签、器械、场地、年龄过滤后交给模型，模型只负责在候选集内
选择与排期；动作详情从动作库回填，不由模型生成。
"""

from __future__ import annotations

import uuid
from collections.abc import AsyncIterator
from typing import Any

from pydantic import ValidationError

from app.llm.provider import LLMError, LLMTruncatedError, extract_json, get_provider
from app.prompts import prescription as prompt
from app.schemas.prescription import (
    ExerciseAlternative,
    ExerciseDetail,
    PrescriptionResult,
    RiskNote,
)
from app.schemas.profile import ProfileResult
from app.schemas.record import HealthRecord
from app.services import rag
from app.services.data_loader import (
    exercise_index,
    exercise_library,
    knowledge_cards,
    save_prescription_result,
)
from app.services.profile_service import current_versions, now_iso

DISCLAIMER = (
    "本运动处方由 AI 生成，仅供参考，不作为医疗诊断依据。"
    "执行中出现不适请立即停止并咨询专业人员。"
)

WEEKDAYS = ["周一", "周二", "周三", "周四", "周五", "周六", "周日"]

_MIN_CANDIDATES = 20


def _loose_match(a: str, b: str) -> bool:
    return a in b or b in a


def _equipment_ok(exercise: dict[str, Any], available: list[str]) -> bool:
    required = exercise.get("equipment") or ["无"]
    if any(item == "无" for item in required):
        return True
    if not available:
        return False
    return any(_loose_match(item, owned) for item in required for owned in available)


def _venue_ok(exercise: dict[str, Any], allowed: list[str]) -> bool:
    if not allowed:
        return True
    places = exercise.get("venue") or []
    if not places:
        return True
    return any(_loose_match(place, target) for place in places for target in allowed)


def filter_candidates(
    *,
    age: int | None,
    blocked_tags: list[str],
    equipment: list[str],
    venue: list[str],
) -> list[dict[str, Any]]:
    """按安全标签、器械、场地、年龄过滤出可用动作。"""
    blocked = set(blocked_tags)
    picked: list[dict[str, Any]] = []
    fallback: list[dict[str, Any]] = []

    for exercise in exercise_library()["exercises"]:
        if blocked & set(exercise.get("contraindication_tags") or []):
            continue
        if age is not None and exercise.get("min_age") and age < exercise["min_age"]:
            continue

        if _equipment_ok(exercise, equipment) and _venue_ok(exercise, venue):
            picked.append(exercise)
        elif not (exercise.get("equipment") or ["无"]) or "无" in (exercise.get("equipment") or []):
            fallback.append(exercise)

    # 过滤过严时补入无器械动作，保证模型有足够素材可排期
    if len(picked) < _MIN_CANDIDATES:
        existing = {item["id"] for item in picked}
        for exercise in fallback:
            if exercise["id"] not in existing:
                picked.append(exercise)

    return picked


def _used_exercise_ids(payload: dict[str, Any]) -> list[str]:
    ids: list[str] = []
    for day in payload.get("weekly_plan") or []:
        for block in day.get("blocks") or []:
            for item in block.get("items") or []:
                exercise_id = str(item.get("exercise_id") or "").strip()
                if exercise_id:
                    ids.append(exercise_id)
    return ids


def validate_payload(
    payload: dict[str, Any],
    *,
    candidate_ids: set[str],
    blocked_tags: list[str],
    request: dict[str, Any],
) -> list[str]:
    """返回问题清单；为空表示通过。用于触发一次重生成。"""
    problems: list[str] = []
    index = exercise_index()
    blocked = set(blocked_tags)

    used = _used_exercise_ids(payload)
    unknown = sorted({item for item in used if item not in index})
    if unknown:
        problems.append(f"以下 exercise_id 不存在于动作库：{'、'.join(unknown)}")

    off_list = sorted({item for item in used if item in index and item not in candidate_ids})
    if off_list:
        problems.append(f"以下动作不在可用候选集内：{'、'.join(off_list)}")

    violating = sorted(
        {
            item
            for item in used
            if item in index and blocked & set(index[item].get("contraindication_tags") or [])
        }
    )
    if violating:
        problems.append(f"以下动作命中了被禁用的风险标签：{'、'.join(violating)}")

    days = [str(day.get("day", "")) for day in payload.get("weekly_plan") or []]
    missing_days = [day for day in WEEKDAYS if day not in days]
    if missing_days:
        problems.append(f"weekly_plan 缺少以下日期：{'、'.join(missing_days)}")

    available = request.get("available_time") or {}
    max_days = available.get("days_per_week")
    if isinstance(max_days, int) and max_days > 0:
        training_days = sum(
            1 for day in payload.get("weekly_plan") or [] if day.get("is_training_day")
        )
        if training_days > max_days:
            problems.append(
                f"训练日 {training_days} 天超过了学生可用的 {max_days} 天"
            )

    max_minutes = available.get("minutes_per_session")
    if isinstance(max_minutes, int) and max_minutes > 0:
        for day in payload.get("weekly_plan") or []:
            minutes = day.get("total_minutes")
            if isinstance(minutes, int) and minutes > max_minutes and day.get("is_training_day"):
                problems.append(
                    f"{day.get('day', '')} 安排了 {minutes} 分钟，超过单次上限 {max_minutes} 分钟"
                )

    if len(payload.get("explanations") or []) < 4:
        problems.append("explanations 少于 4 条")

    return problems


def build_exercise_details(payload: dict[str, Any]) -> tuple[list[ExerciseDetail], list[str]]:
    """从动作库回填被引用动作的完整信息。"""
    index = exercise_index()
    details: list[ExerciseDetail] = []
    unknown: list[str] = []

    for exercise_id in dict.fromkeys(_used_exercise_ids(payload)):
        exercise = index.get(exercise_id)
        if exercise is None:
            unknown.append(exercise_id)
            continue
        alternatives = [
            ExerciseAlternative(
                id=alt_id,
                name=index[alt_id]["name"],
                why=f"{index[alt_id].get('impact_level', '')}冲击的同类替代动作",
            )
            for alt_id in exercise.get("alternatives") or []
            if alt_id in index
        ]
        details.append(
            ExerciseDetail(
                id=exercise["id"],
                name=exercise["name"],
                category=exercise.get("category", ""),
                impact_level=exercise.get("impact_level", ""),
                equipment=exercise.get("equipment", []),
                venue=exercise.get("venue", []),
                key_points=exercise.get("key_points", []),
                common_errors=exercise.get("common_errors", []),
                dosage_hint=exercise.get("dosage_hint", ""),
                alternatives=alternatives,
            )
        )

    return details, unknown


def _strip_unknown_refs(payload: dict[str, Any]) -> list[str]:
    valid = {card["id"] for card in knowledge_cards()}
    dropped: list[str] = []
    for explanation in payload.get("explanations") or []:
        refs = explanation.get("knowledge_refs") or []
        explanation["knowledge_refs"] = [ref for ref in refs if ref in valid]
        dropped.extend(ref for ref in refs if ref not in valid)
    return sorted(set(dropped))


def _assemble(
    payload: dict[str, Any],
    *,
    record: HealthRecord,
    profile: ProfileResult,
) -> PrescriptionResult:
    details, unknown = build_exercise_details(payload)
    dropped_refs = _strip_unknown_refs(payload)

    payload.update(
        {
            "prescription_id": f"RX-{now_iso()[:10].replace('-', '')}-{record.student_id or 'NA'}-{uuid.uuid4().hex[:4]}",
            "student_id": record.student_id,
            "name": record.name,
            "generated_at": now_iso(),
            "versions": current_versions().model_dump(),
            "goals": record.prescription_request.goals,
            "exercise_details": [item.model_dump() for item in details],
            "unknown_exercise_ids": unknown,
            "disclaimer": DISCLAIMER,
        }
    )

    result = PrescriptionResult.model_validate(payload)
    if dropped_refs:
        result.risk_notes.append(
            RiskNote(
                level="低",
                item="知识引用缺失",
                reason="模型引用了不存在的知识卡片：" + "、".join(dropped_refs),
                action="该引用已移除，处方内容不受影响",
            )
        )
    return result


async def stream_prescription(
    record: HealthRecord,
    profile: ProfileResult,
) -> AsyncIterator[tuple[str, Any]]:
    """流式生成处方。

    产出 ("thinking", 片段) / ("token", 片段) 供前端展示进度，最后产出
    ("result", PrescriptionResult) 或 ("error", 说明)。
    """
    provider = get_provider()
    request = record.prescription_request.model_dump()
    profile_dict = profile.model_dump()
    age = profile.basic.age

    candidates = filter_candidates(
        age=age,
        blocked_tags=profile.safety.blocked_exercise_tags,
        equipment=record.prescription_request.equipment,
        venue=record.prescription_request.venue,
    )
    # 校验边界用安全硬过滤后的全集：候选截断只是 prompt 瘦身，
    # 模型只要用了安全集合内的动作就不算违规
    candidate_ids = {item["id"] for item in candidates}

    # RAG：候选动作按短板/目标/偏好排序截断，知识卡片检索相关子集
    candidates = await rag.rank_exercises(candidates, profile_dict, request)
    cards = await rag.retrieve_knowledge_for_prescription(profile_dict, request)

    base_prompt = prompt.build_user_prompt(
        profile=profile_dict,
        request=request,
        age=age,
        candidates=candidates,
        knowledge_cards=cards,
    )

    user_prompt = base_prompt
    last_problems: list[str] = []
    truncated = False

    for attempt in range(2):
        if attempt == 1:
            yield ("retry", "；".join(last_problems))
            # 截断与"内容不合规"是两类问题：截断要压缩表述，不合规要带问题清单重做
            user_prompt = (
                prompt.build_concise_prompt(base_prompt)
                if truncated
                else prompt.build_repair_prompt(base_prompt, "\n".join(last_problems))
            )

        buffer: list[str] = []
        truncated = False
        try:
            async for kind, chunk in provider.stream(prompt.SYSTEM, user_prompt):
                if kind == "thinking":
                    yield ("thinking", chunk)
                    continue
                buffer.append(chunk)
                yield ("token", chunk)
        except LLMTruncatedError as exc:
            truncated = True
            last_problems = [str(exc)]
            if attempt == 0:
                continue
            yield ("error", f"处方生成失败：{exc}")
            return

        raw = "".join(buffer)
        try:
            payload = extract_json(raw)
        except LLMTruncatedError as exc:
            # 上游未报 max_tokens，但 JSON 没写完：同样按"太长"处理，重试要求精简
            truncated = True
            last_problems = [str(exc)]
            if attempt == 0:
                continue
            yield ("error", f"处方生成失败：{exc}")
            return
        except LLMError as exc:
            last_problems = [str(exc)]
            continue

        problems = validate_payload(
            payload,
            candidate_ids=candidate_ids,
            blocked_tags=profile.safety.blocked_exercise_tags,
            request=request,
        )
        if problems and attempt == 0:
            last_problems = problems
            continue

        try:
            result = _assemble(payload, record=record, profile=profile)
        except ValidationError as exc:
            last_problems = [exc.json()]
            if attempt == 0:
                continue
            yield ("error", f"处方结构校验失败：{exc.errors()[:3]}")
            return

        if problems:
            result.risk_notes.append(
                RiskNote(
                    level="低",
                    item="自动校验提示",
                    reason="重生成后仍存在以下问题：" + "；".join(problems),
                    action="建议由专业人员复核相关条目",
                )
            )

        try:
            save_prescription_result(result.model_dump())
        except OSError:
            # 落盘只是旁路留档，磁盘问题不应中断处方返回
            pass

        yield ("result", result)
        return

    yield ("error", "处方生成两次均未通过校验：" + "；".join(last_problems))
