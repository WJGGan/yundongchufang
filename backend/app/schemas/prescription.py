"""运动处方输出契约（一人一策能力的产物）。"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field

from app.schemas.profile import Versions


class FittItem(BaseModel):
    model_config = ConfigDict(extra="allow")

    value: str = ""
    detail: str = ""


class FittVp(BaseModel):
    model_config = ConfigDict(extra="allow")

    frequency: FittItem = Field(default_factory=FittItem)
    intensity: FittItem = Field(default_factory=FittItem)
    time: FittItem = Field(default_factory=FittItem)
    type: FittItem = Field(default_factory=FittItem)
    volume: FittItem = Field(default_factory=FittItem)
    progression: FittItem = Field(default_factory=FittItem)


class Cycle(BaseModel):
    model_config = ConfigDict(extra="allow")

    total_weeks: int | None = None
    current_phase: str = ""
    next_review: str = ""


class PlanItem(BaseModel):
    model_config = ConfigDict(extra="allow")

    exercise_id: str = ""
    name: str = ""
    dosage: str = ""
    notes: str = ""


class PlanBlock(BaseModel):
    model_config = ConfigDict(extra="allow")

    phase: str = ""
    minutes: int | None = None
    items: list[PlanItem] = Field(default_factory=list)


class DayPlan(BaseModel):
    model_config = ConfigDict(extra="allow")

    day: str = ""
    theme: str = ""
    total_minutes: int | None = None
    is_training_day: bool = True
    blocks: list[PlanBlock] = Field(default_factory=list)


class ExerciseAlternative(BaseModel):
    model_config = ConfigDict(extra="allow")

    id: str = ""
    name: str = ""
    why: str = ""


class ExerciseDetail(BaseModel):
    """从动作库回填，不由模型生成。"""

    model_config = ConfigDict(extra="allow")

    id: str = ""
    name: str = ""
    category: str = ""
    impact_level: str = ""
    equipment: list[str] = Field(default_factory=list)
    venue: list[str] = Field(default_factory=list)
    key_points: list[str] = Field(default_factory=list)
    common_errors: list[str] = Field(default_factory=list)
    dosage_hint: str = ""
    alternatives: list[ExerciseAlternative] = Field(default_factory=list)


class TargetHrZone(BaseModel):
    model_config = ConfigDict(extra="allow")

    lower: int | None = None
    upper: int | None = None
    formula_note: str = ""


class IntensityControl(BaseModel):
    model_config = ConfigDict(extra="allow")

    target_hr_zone: TargetHrZone = Field(default_factory=TargetHrZone)
    rpe_range: str = ""
    talk_test: str = ""
    stop_signals: list[str] = Field(default_factory=list)


class MacroGuidance(BaseModel):
    model_config = ConfigDict(extra="allow")

    carbohydrate: str = ""
    protein: str = ""
    fat: str = ""


class AroundTraining(BaseModel):
    model_config = ConfigDict(extra="allow")

    pre: str = ""
    post: str = ""


class Nutrition(BaseModel):
    model_config = ConfigDict(extra="allow")

    principles: list[str] = Field(default_factory=list)
    macro_guidance: MacroGuidance = Field(default_factory=MacroGuidance)
    around_training: AroundTraining = Field(default_factory=AroundTraining)
    hydration: str = ""
    cautions: list[str] = Field(default_factory=list)


class RiskNote(BaseModel):
    model_config = ConfigDict(extra="allow")

    level: str = ""
    item: str = ""
    reason: str = ""
    action: str = ""


class Restriction(BaseModel):
    model_config = ConfigDict(extra="allow")

    target: str = ""
    restriction: str = ""
    reason: str = ""
    source: str = ""


class Explanation(BaseModel):
    model_config = ConfigDict(extra="allow")

    target: str = ""
    why: str = ""
    knowledge_refs: list[str] = Field(default_factory=list)


class Homework(BaseModel):
    model_config = ConfigDict(extra="allow")

    title: str = ""
    tasks: list[str] = Field(default_factory=list)
    completion_standard: str = ""
    self_report: str = ""


class PrescriptionResult(BaseModel):
    """处方接口的完整返回体。"""

    model_config = ConfigDict(extra="allow")

    prescription_id: str = ""
    student_id: str = ""
    name: str = ""
    generated_at: str = ""
    versions: Versions = Field(default_factory=Versions)
    goals: list[str] = Field(default_factory=list)
    cycle: Cycle = Field(default_factory=Cycle)
    fitt_vp: FittVp = Field(default_factory=FittVp)
    weekly_plan: list[DayPlan] = Field(default_factory=list)
    exercise_details: list[ExerciseDetail] = Field(default_factory=list)
    intensity_control: IntensityControl = Field(default_factory=IntensityControl)
    nutrition: Nutrition = Field(default_factory=Nutrition)
    risk_notes: list[RiskNote] = Field(default_factory=list)
    forbidden_or_limited: list[Restriction] = Field(default_factory=list)
    explanations: list[Explanation] = Field(default_factory=list)
    homework: Homework = Field(default_factory=Homework)
    unknown_exercise_ids: list[str] = Field(default_factory=list)
    disclaimer: str = ""
