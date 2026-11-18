"""体质画像输出契约（档案理解能力的产物）。"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field


class Versions(BaseModel):
    model_config = ConfigDict(extra="allow")

    exercise_library: str = ""
    knowledge_base: str = ""
    prompt: str = ""
    model: str = ""


class BasicEvaluation(BaseModel):
    model_config = ConfigDict(extra="allow")

    grade: str = ""
    age: int | None = None
    gender: str = ""
    height_cm: float | None = None
    weight_kg: float | None = None
    bmi: float | None = None
    bmi_evaluation: str = ""
    bmi_basis: str = ""
    growth_note: str = ""


class DimensionIndicator(BaseModel):
    model_config = ConfigDict(extra="allow")

    name: str = ""
    raw: str = ""
    level: str = ""


class FitnessDimension(BaseModel):
    model_config = ConfigDict(extra="allow")

    dimension: str
    indicators: list[DimensionIndicator] = Field(default_factory=list)
    level: str = ""
    basis: str = ""
    knowledge_refs: list[str] = Field(default_factory=list)


class Weakness(BaseModel):
    model_config = ConfigDict(extra="allow")

    rank: int | None = None
    dimension: str = ""
    reason: str = ""


class OverallEvaluation(BaseModel):
    model_config = ConfigDict(extra="allow")

    level: str = ""
    summary: str = ""
    strengths: list[str] = Field(default_factory=list)
    weaknesses: list[Weakness] = Field(default_factory=list)


class HealthFocus(BaseModel):
    model_config = ConfigDict(extra="allow")

    item: str = ""
    type: str = ""
    impact: str = ""
    attention: str = ""


class IntensityCeiling(BaseModel):
    model_config = ConfigDict(extra="allow")

    hr_max_percent: int | None = None
    rpe_max: int | None = None
    basis: str = ""


class SafetyAssessment(BaseModel):
    model_config = ConfigDict(extra="allow")

    risk_level: str = "中"
    can_generate_prescription: bool = True
    blocked_exercise_tags: list[str] = Field(default_factory=list)
    intensity_ceiling: IntensityCeiling = Field(default_factory=IntensityCeiling)
    referral_advice: list[str] = Field(default_factory=list)
    notes: list[str] = Field(default_factory=list)


class ProfileResult(BaseModel):
    """画像接口的完整返回体。"""

    model_config = ConfigDict(extra="allow")

    student_id: str = ""
    name: str = ""
    generated_at: str = ""
    versions: Versions = Field(default_factory=Versions)
    basic: BasicEvaluation = Field(default_factory=BasicEvaluation)
    fitness_dimensions: list[FitnessDimension] = Field(default_factory=list)
    overall: OverallEvaluation = Field(default_factory=OverallEvaluation)
    health_focus: list[HealthFocus] = Field(default_factory=list)
    safety: SafetyAssessment = Field(default_factory=SafetyAssessment)
    disclaimer: str = ""


class EmergencyBlock(BaseModel):
    """急症熔断返回体，由代码规则触发，不经过模型。"""

    model_config = ConfigDict(extra="allow")

    blocked: bool = True
    level: str = "高"
    title: str = ""
    message: str = ""
    matched_keywords: list[str] = Field(default_factory=list)
    matched_text: list[str] = Field(default_factory=list)
    immediate_advice: list[str] = Field(default_factory=list)
    allowed_activity: list[str] = Field(default_factory=list)
    next_step: str = ""
    disclaimer: str = ""
