"""真实模型验证脚本：跑三个关键用例。

用法： uv run python -u scripts/verify_real.py
"""

from __future__ import annotations

import asyncio
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.schemas.record import HealthRecord  # noqa: E402
from app.services.data_loader import find_student  # noqa: E402
from app.services.prescription_service import stream_prescription  # noqa: E402
from app.services.profile_service import analyze_profile  # noqa: E402


async def case_prescription(student_id: str) -> None:
    rec = HealthRecord.model_validate(find_student(student_id))
    tag = f"[{rec.name} 完整处方]"
    t0 = time.time()
    profile = await analyze_profile(rec)
    print(f"{tag} 画像完成 {time.time() - t0:.0f}s  "
          f"风险={profile.safety.risk_level} 可生成={profile.safety.can_generate_prescription}")
    print(f"{tag} 短板={[w.dimension for w in profile.overall.weaknesses]}")
    print(f"{tag} 禁用标签={profile.safety.blocked_exercise_tags}", flush=True)

    t1 = time.time()
    retries: list[str] = []
    result = None
    async for kind, payload in stream_prescription(rec, profile):
        if kind == "retry":
            retries.append(payload)
            print(f"{tag} 触发重生成: {payload}", flush=True)
        elif kind == "result":
            result = payload
        elif kind == "error":
            print(f"{tag} 失败: {payload}", flush=True)
            return
    print(f"{tag} 处方完成 {time.time() - t1:.0f}s  重试 {len(retries)} 次", flush=True)

    if result is None:
        return
    print(f"{tag} 周期: {result.cycle.total_weeks} 周 · {result.cycle.current_phase}")
    print(f"{tag} 心率区间: {result.intensity_control.target_hr_zone.lower}"
          f"-{result.intensity_control.target_hr_zone.upper}  RPE {result.intensity_control.rpe_range}")
    for key in ("frequency", "intensity", "time", "type", "volume", "progression"):
        item = getattr(result.fitt_vp, key)
        print(f"{tag}   {key:12} {item.value}")
    print(f"{tag} 周计划:")
    for day in result.weekly_plan:
        names = [
            f"{i.name}({i.exercise_id})"
            for b in day.blocks for i in b.items
        ]
        mark = "训练" if day.is_training_day else "休息"
        print(f"{tag}   {day.day} [{mark}] {day.theme} {day.total_minutes or 0}分  {' / '.join(names)}")
    print(f"{tag} 风险提示:")
    for note in result.risk_notes:
        print(f"{tag}   [{note.level}] {note.item} -> {note.action}")
    print(f"{tag} 禁止与限制:")
    for item in result.forbidden_or_limited:
        print(f"{tag}   [{item.restriction}/{item.source}] {item.target} — {item.reason}")
    print(f"{tag} 解释 {len(result.explanations)} 条:")
    for exp in result.explanations:
        print(f"{tag}   {exp.target} refs={exp.knowledge_refs}")
        print(f"{tag}     {exp.why}")
    print(f"{tag} 未知动作ID: {result.unknown_exercise_ids}", flush=True)


async def case_profile(student_id: str, label: str) -> None:
    rec = HealthRecord.model_validate(find_student(student_id))
    tag = f"[{rec.name} {label}]"
    t0 = time.time()
    profile = await analyze_profile(rec)
    safety = profile.safety
    print(f"{tag} 完成 {time.time() - t0:.0f}s")
    print(f"{tag} 风险={safety.risk_level}  可生成处方={safety.can_generate_prescription}")
    print(f"{tag} 禁用标签={safety.blocked_exercise_tags}")
    print(f"{tag} 强度上限=HRmax {safety.intensity_ceiling.hr_max_percent}% / RPE {safety.intensity_ceiling.rpe_max}")
    for advice in safety.referral_advice:
        print(f"{tag} 转介: {advice}")
    print(f"{tag} BMI {profile.basic.bmi} -> {profile.basic.bmi_evaluation}")
    print(f"{tag} 短板={[w.dimension for w in profile.overall.weaknesses]}")
    for conflict in profile.data_quality.conflicts:
        print(f"{tag} 矛盾: {conflict.fields} {conflict.description}")
        print(f"{tag}       建议: {conflict.suggestion}")
    print(f"{tag} 缺失={[m.field for m in profile.data_quality.missing_fields]}")
    for q in profile.data_quality.clarification_questions:
        print(f"{tag} 追问[{q.priority}/{q.audience}] {q.question}")
    print(flush=True)


CASES = {
    "rx": lambda: case_prescription("BJ2025090314"),        # 李沐阳：哮喘+踝伤+肥胖，完整处方
    "block": lambda: case_profile("BJ2025140258", "安全拦截用例"),  # 马天宇：血压145/92
    "conflict": lambda: case_profile("BJ2025170139", "矛盾检测用例"),  # 朱浩宇：身高142 vs 156
}


async def main() -> None:
    names = sys.argv[1:] or list(CASES)
    unknown = [n for n in names if n not in CASES]
    if unknown:
        print(f"未知用例 {unknown}，可选：{list(CASES)}")
        return
    # 串行执行：并发会让单次调用从 4 分钟拖到 14 分钟
    for name in names:
        await CASES[name]()


if __name__ == "__main__":
    asyncio.run(main())
