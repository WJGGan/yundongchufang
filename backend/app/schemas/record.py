"""健康档案输入契约。

physical_exam / fitness_test 沿用体检结果表与体质结果表的原字段名与字符串格式，
字段全部可选且允许空串，以容纳真实系统中的缺考、免测与缺采情况。
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class PhysicalExam(BaseModel):
    """体检结果表。"""

    model_config = ConfigDict(extra="allow")

    YEARSTART: str = ""
    YEAREND: str = ""
    XB: str = ""
    NL: str = ""
    SG: str = ""
    TZ: str = ""
    FHL: str = ""
    ZYSL: str = ""
    YYSL: str = ""
    ZYJSL: str = ""
    YYJSL: str = ""
    JSLPJ: str = ""
    JZ: str = ""
    UP_TIME: str = ""
    SCHOOL_GRADE: str = ""
    TOWN_ID: str = ""


class FitnessTest(BaseModel):
    """体质结果表。"""

    model_config = ConfigDict(extra="allow")

    YEARSTART: str = ""
    YEAREND: str = ""
    NJ: str = ""
    XB: str = ""
    SGCJ: str = ""
    TZCJ: str = ""
    FHLCJ: str = ""
    WSMCJ: str = ""
    LDTYCJ: str = ""
    ZWTQQCJ: str = ""
    WSMWFPCJ: str = ""
    YFZTSCJ: str = ""
    BBMCJ: str = ""
    YWQZCJ: str = ""
    YQMCJ: str = ""
    YTXSCJ: str = ""


class InjuryRecord(BaseModel):
    model_config = ConfigDict(extra="allow")

    site: str = ""
    type: str = ""
    date: str = ""
    status: str = ""
    note: str = ""


class Vitals(BaseModel):
    model_config = ConfigDict(extra="allow")

    resting_heart_rate: str = ""
    blood_pressure: str = ""


class ExerciseHistory(BaseModel):
    model_config = ConfigDict(extra="allow")

    weekly_frequency: int | None = None
    typical_duration_min: int | None = None
    main_activities: list[str] = Field(default_factory=list)
    training_experience: str = ""
    sedentary_hours_per_day: float | None = None


class HealthProfile(BaseModel):
    """健康扩展层：体检与体质表未覆盖、但处方生成必需的信息。"""

    model_config = ConfigDict(extra="allow")

    chronic_conditions: list[str] = Field(default_factory=list)
    medications: list[str] = Field(default_factory=list)
    injury_history: list[InjuryRecord] = Field(default_factory=list)
    recent_symptoms: list[str] = Field(default_factory=list)
    family_history: list[str] = Field(default_factory=list)
    vitals: Vitals = Field(default_factory=Vitals)
    exercise_history: ExerciseHistory = Field(default_factory=ExerciseHistory)


class AvailableTime(BaseModel):
    model_config = ConfigDict(extra="allow")

    days_per_week: int | None = None
    minutes_per_session: int | None = None
    preferred_slot: str = ""


class Preferences(BaseModel):
    model_config = ConfigDict(extra="allow")

    liked: list[str] = Field(default_factory=list)
    disliked: list[str] = Field(default_factory=list)


class PrescriptionRequest(BaseModel):
    """处方请求参数：目标、约束条件与偏好。"""

    model_config = ConfigDict(extra="allow")

    goals: list[str] = Field(default_factory=list)
    available_time: AvailableTime = Field(default_factory=AvailableTime)
    venue: list[str] = Field(default_factory=list)
    equipment: list[str] = Field(default_factory=list)
    preferences: Preferences = Field(default_factory=Preferences)
    guardian_consent: bool | None = None


class HealthRecord(BaseModel):
    """完整健康档案。"""

    model_config = ConfigDict(extra="allow")

    student_id: str = ""
    name: str = ""
    school: str = ""
    physical_exam: PhysicalExam = Field(default_factory=PhysicalExam)
    fitness_test: FitnessTest = Field(default_factory=FitnessTest)
    health_profile: HealthProfile = Field(default_factory=HealthProfile)
    prescription_request: PrescriptionRequest = Field(default_factory=PrescriptionRequest)

    def to_prompt_dict(self) -> dict[str, Any]:
        """送入模型的档案视图，去掉姓名与学校以减少无关个人信息。"""
        data = self.model_dump()
        data.pop("name", None)
        data.pop("school", None)
        return data
