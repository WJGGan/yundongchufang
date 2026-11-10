"""耗时拆解基准：把一次画像/处方调用的时间花在哪里量出来。

用法： uv run python -u scripts/benchmark.py
"""

from __future__ import annotations

import asyncio
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from anthropic import AsyncAnthropic  # noqa: E402

from app.config import settings  # noqa: E402
from app.prompts import prescription as rx_prompt  # noqa: E402
from app.prompts import profile as pf_prompt  # noqa: E402
from app.schemas.record import HealthRecord  # noqa: E402
from app.services import rag  # noqa: E402
from app.services.data_loader import find_student  # noqa: E402
from app.services.prescription_service import filter_candidates  # noqa: E402

STUDENT_ID = "BJ2025090314"

# 要对比的 (模型, 是否开思考)。关思考是最大的延迟杠杆，优先保证这两格有数。
MATRIX = [
    ("glm-5.3", True),
    ("glm-5.3", False),
]


async def build_profile_prompt() -> tuple[str, str]:
    record = HealthRecord.model_validate(find_student(STUDENT_ID))
    record_view = record.to_prompt_dict()
    # 与 profile_service 保持一致：知识卡片走 RAG 检索，基准才能反映真实输入量
    cards = await rag.retrieve_knowledge_for_profile(record_view)
    return pf_prompt.SYSTEM, pf_prompt.build_user_prompt(record_view, cards)


async def build_prescription_prompt() -> tuple[str, str]:
    """用一份固定的最小画像构造处方 prompt，避免每次基准都先跑一遍画像。"""
    record = HealthRecord.model_validate(find_student(STUDENT_ID))
    stub_profile = {
        "basic": {"age": 14, "gender": "男", "bmi": 25.5, "bmi_evaluation": "肥胖"},
        "overall": {
            "level": "中等偏下",
            "weaknesses": [
                {"rank": 1, "dimension": "身体成分", "reason": "BMI 25.5 属肥胖"},
                {"rank": 2, "dimension": "心肺耐力", "reason": "1000米接近及格下限"},
                {"rank": 3, "dimension": "肌肉力量", "reason": "引体向上 3 个"},
            ],
        },
        "safety": {
            "risk_level": "中",
            "can_generate_prescription": True,
            "blocked_exercise_tags": ["高冲击", "踝关节负荷", "憋气风险", "最大力量"],
            "intensity_ceiling": {"hr_max_percent": 70, "rpe_max": 6, "basis": "初学者"},
        },
    }
    request = record.prescription_request.model_dump()
    candidates = filter_candidates(
        age=14,
        blocked_tags=stub_profile["safety"]["blocked_exercise_tags"],
        equipment=record.prescription_request.equipment,
        venue=record.prescription_request.venue,
    )
    # 与 prescription_service 保持一致：候选排序截断 + 知识卡片检索
    candidates = await rag.rank_exercises(candidates, stub_profile, request)
    cards = await rag.retrieve_knowledge_for_prescription(stub_profile, request)
    return rx_prompt.SYSTEM, rx_prompt.build_user_prompt(
        profile=stub_profile,
        request=request,
        age=14,
        candidates=candidates,
        knowledge_cards=cards,
    )


async def run(client: AsyncAnthropic, model: str, system: str, user: str,
              thinking: bool, label: str) -> None:
    kwargs: dict = {
        "model": model,
        "system": system,
        "messages": [{"role": "user", "content": user}],
        "max_tokens": settings.max_tokens,
    }
    if not thinking:
        kwargs["thinking"] = {"type": "disabled"}
        kwargs["extra_body"] = {"temperature": settings.temperature}

    first_token_at = None
    text_chars = 0
    think_chars = 0
    t0 = time.time()
    try:
        async with client.messages.stream(**kwargs) as stream:
            async for event in stream:
                if event.type != "content_block_delta":
                    continue
                kind = getattr(event.delta, "type", "")
                if kind == "thinking_delta":
                    if first_token_at is None:
                        first_token_at = time.time()
                    think_chars += len(getattr(event.delta, "thinking", "") or "")
                elif kind == "text_delta":
                    if first_token_at is None:
                        first_token_at = time.time()
                    text_chars += len(event.delta.text)
            final = await stream.get_final_message()
    except Exception as exc:  # noqa: BLE001
        print(f"  {label:34} 失败: {type(exc).__name__}: {str(exc)[:80]}", flush=True)
        return

    total = time.time() - t0
    ttft = (first_token_at - t0) if first_token_at else total
    usage = final.usage
    out = usage.output_tokens
    think_est = round(out * think_chars / max(think_chars + text_chars, 1))
    speed = out / total if total else 0

    print(
        f"  {label:34} {total:6.1f}s  首字 {ttft:5.1f}s  "
        f"入 {usage.input_tokens:6}  出 {out:6}"
        f"（思考约 {think_est:5} / 正文约 {out - think_est:5}）"
        f"  {speed:5.1f} tok/s  stop={final.stop_reason}",
        flush=True,
    )


async def main() -> None:
    client = AsyncAnthropic(
        base_url=settings.anthropic_base_url,
        api_key=settings.anthropic_api_key,
        timeout=settings.timeout,
    )

    pf_sys, pf_user = await build_profile_prompt()
    rx_sys, rx_user = await build_prescription_prompt()
    print(f"画像 prompt 约 {len(pf_sys) + len(pf_user)} 字符；"
          f"处方 prompt 约 {len(rx_sys) + len(rx_user)} 字符\n")

    for stage, (s, u) in (("画像", (pf_sys, pf_user)), ("处方", (rx_sys, rx_user))):
        print(f"=== {stage} ===")
        for model, thinking in MATRIX:
            tag = f"{model} {'思考开' if thinking else '思考关'}"
            await run(client, model, s, u, thinking, tag)
        print()


if __name__ == "__main__":
    asyncio.run(main())
