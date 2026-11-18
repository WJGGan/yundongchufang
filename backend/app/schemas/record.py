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


class HealthProfile(BaseModel):
    """健康扩展层：体检与体质表未覆盖、但处方生成必需的信息。"""

    model_config = ConfigDict(extra="allow")

    chronic_conditions: list[str] = Field(default_factory=list)
    medications: list[str] = Field(default_factory=list)
    injury_history: list[InjuryRecord] = Field(default_factory=list)
    recent_symptoms: list[str] = Field(default_factory=list)
    vitals: Vitals = Field(default_factory=Vitals)


class HealthRecord(BaseModel):
    """完整健康档案。"""

    model_config = ConfigDict(extra="allow")

    student_id: str = ""
    name: str = ""
    school: str = ""
    physical_exam: PhysicalExam = Field(default_factory=PhysicalExam)
    fitness_test: FitnessTest = Field(default_factory=FitnessTest)
    health_profile: HealthProfile = Field(default_factory=HealthProfile)

    def to_prompt_dict(self) -> dict[str, Any]:
        """送入模型的档案视图，去掉姓名与学校以减少无关个人信息。"""
        data = self.model_dump()
        data.pop("name", None)
        data.pop("school", None)
        # 兼容旧档案：extra="allow" 会把历史数据中的处方需求残留键带出来
        data.pop("prescription_request", None)
        # 兼容旧档案：已删除的家族病史与运动史字段不再送入模型
        profile = data.get("health_profile")
        if isinstance(profile, dict):
            profile.pop("family_history", None)
            profile.pop("exercise_history", None)
        return data
