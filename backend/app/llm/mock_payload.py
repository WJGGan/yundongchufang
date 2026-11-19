"""离线联调用的占位返回。

仅在 LLM_PROVIDER=mock 时使用，用于前端在没有模型密钥的情况下打通页面渲染。
所有文案带 [MOCK] 前缀，避免被误认为真实模型输出。
"""

from __future__ import annotations

from typing import Any

_MOCK = "[MOCK]"


def _is_prescription_task(system: str) -> bool:
    return "运动处方" in system and "weekly_plan" in system


def build_mock_payload(system: str, user: str) -> dict[str, Any]:
    if _is_prescription_task(system):
        return _mock_prescription()
    return _mock_profile()


def _mock_profile() -> dict[str, Any]:
    return {
        "basic": {
            "grade": "初二",
            "age": 14,
            "gender": "男",
            "height_cm": 168.5,
            "weight_kg": 72.3,
            "bmi": 25.5,
            "bmi_evaluation": f"{_MOCK} 肥胖",
        },
        "fitness_dimensions": [
            {
                "dimension": "身体形态",
                "indicators": [{"name": "BMI", "raw": "25.5", "level": "较差"}],
                "level": "较差",
                "basis": f"{_MOCK} 离线占位",
            },
            {
                "dimension": "心肺耐力",
                "indicators": [{"name": "1000米", "raw": "4分32秒", "level": "及格"}],
                "level": "及格",
                "basis": f"{_MOCK} 离线占位",
            },
            {
                "dimension": "肌肉力量与耐力",
                "indicators": [{"name": "引体向上", "raw": "3", "level": "及格"}],
                "level": "及格",
                "basis": f"{_MOCK} 离线占位",
            },
            {
                "dimension": "速度与灵敏",
                "indicators": [{"name": "50米", "raw": "8.9", "level": "及格"}],
                "level": "及格",
                "basis": f"{_MOCK} 离线占位",
            },
            {
                "dimension": "爆发力",
                "indicators": [{"name": "立定跳远", "raw": "185", "level": "及格"}],
                "level": "及格",
                "basis": f"{_MOCK} 离线占位",
            },
            {
                "dimension": "柔韧性",
                "indicators": [{"name": "坐位体前屈", "raw": "4.2", "level": "较差"}],
                "level": "较差",
                "basis": f"{_MOCK} 离线占位",
            },
        ],
        "overall": {
            "level": "中等偏下",
            "summary": f"{_MOCK} 这是离线占位画像，请配置真实模型后重新生成",
            "strengths": [f"{_MOCK} 身高发育良好"],
            "weaknesses": [
                {"rank": 1, "dimension": "身体形态", "reason": f"{_MOCK} BMI 属肥胖，优先改善"},
                {"rank": 2, "dimension": "柔韧性", "reason": f"{_MOCK} 低于及格线"},
                {"rank": 3, "dimension": "心肺耐力", "reason": f"{_MOCK} 提升空间最大"},
            ],
        },
        "health_focus": [
            {
                "item": f"{_MOCK} 哮喘",
                "type": "慢性病",
                "impact": "冷空气高强度有氧可能诱发",
                "attention": "延长热身，低温转室内",
            }
        ],
    }


def _mock_prescription() -> dict[str, Any]:
    return {
        "goals": [f"{_MOCK} 健康体重管理", "心肺耐力提升", "体测专项提升:1000米"],
        "fitt_vp": {
            "frequency": {"value": "每周 4 次", "detail": f"{_MOCK} 有氧 3 次 + 抗阻 1 次"},
            "intensity": {"value": "最大心率 60%-70%，RPE 4-6", "detail": f"{_MOCK} 谈话测试控制"},
            "time": {"value": "单次 45 分钟", "detail": f"{_MOCK} 热身 8 + 主体 30 + 放松 7"},
            "type": {"value": "低冲击有氧为主", "detail": f"{_MOCK} 有氧 60% / 抗阻 25% / 柔韧 15%"},
            "volume": {"value": "每周 180 分钟", "detail": f"{_MOCK} 离线占位"},
            "progression": {"value": "每 2 周递增", "detail": f"{_MOCK} 先加时长再加强度"},
        },
        "weekly_plan": [
            {
                "day": "周一",
                "theme": f"{_MOCK} 低冲击有氧 + 柔韧",
                "total_minutes": 45,
                "is_training_day": True,
                "rationale": f"{_MOCK} 以低冲击有氧改善心肺与体重，占位示例文案",
                "blocks": [
                    {
                        "phase": "热身",
                        "minutes": 8,
                        "items": [
                            {"exercise_id": "WUP-001", "name": "关节活动组合", "dosage": "每个关节 8 次", "notes": ""},
                            {"exercise_id": "WUP-003", "name": "原地快走摆臂", "dosage": "3 分钟", "notes": ""},
                        ],
                    },
                    {
                        "phase": "主体",
                        "minutes": 30,
                        "items": [
                            {
                                "exercise_id": "AER-005",
                                "name": "快走慢跑交替",
                                "dosage": "快走 3 分钟 + 慢跑 2 分钟 × 6 组",
                                "notes": f"{_MOCK} 心率 120-140",
                            }
                        ],
                    },
                    {
                        "phase": "放松",
                        "minutes": 7,
                        "items": [
                            {"exercise_id": "FLX-002", "name": "腘绳肌静态拉伸", "dosage": "每侧 30 秒 × 2", "notes": ""},
                            {"exercise_id": "FLX-007", "name": "小腿拉伸", "dosage": "每侧 30 秒 × 2", "notes": ""},
                        ],
                    },
                ],
            },
            {"day": "周二", "theme": f"{_MOCK} 主动恢复", "total_minutes": 15, "is_training_day": False,
             "rationale": f"{_MOCK} 训练次日放松身体，保持柔韧练习",
             "blocks": [{"phase": "柔韧", "minutes": 15, "items": [
                 {"exercise_id": "FLX-001", "name": "坐位体前屈拉伸", "dosage": "30 秒 × 3", "notes": ""}]}]},
            {"day": "周三", "theme": f"{_MOCK} 徒手抗阻", "total_minutes": 45, "is_training_day": True,
             "rationale": f"{_MOCK} 隔日安排力量练习，发展肌肉力量",
             "blocks": [{"phase": "主体", "minutes": 30, "items": [
                 {"exercise_id": "RES-004", "name": "臀桥", "dosage": "15 次 × 3 组", "notes": ""},
                 {"exercise_id": "RES-011", "name": "跪姿俯卧撑", "dosage": "12 次 × 3 组", "notes": ""},
                 {"exercise_id": "COR-001", "name": "平板支撑", "dosage": "30 秒 × 3 组", "notes": ""}]}]},
            {"day": "周四", "theme": f"{_MOCK} 休息", "total_minutes": 0, "is_training_day": False, "blocks": []},
            {"day": "周五", "theme": f"{_MOCK} 低冲击有氧", "total_minutes": 45, "is_training_day": True,
             "blocks": [{"phase": "主体", "minutes": 30, "items": [
                 {"exercise_id": "AER-006", "name": "匀速慢跑", "dosage": "30 分钟", "notes": ""}]}]},
            {"day": "周六", "theme": f"{_MOCK} 趣味有氧", "total_minutes": 40, "is_training_day": True,
             "blocks": [{"phase": "主体", "minutes": 25, "items": [
                 {"exercise_id": "AER-001", "name": "基础跳绳", "dosage": "45 秒 × 5 组，组间休 60 秒", "notes": ""}]}]},
            {"day": "周日", "theme": f"{_MOCK} 休息 + 柔韧", "total_minutes": 15, "is_training_day": False,
             "blocks": [{"phase": "柔韧", "minutes": 15, "items": [
                 {"exercise_id": "FLX-004", "name": "髋屈肌拉伸", "dosage": "每侧 30 秒 × 2", "notes": ""}]}]},
        ],
        "intensity_control": {
            "target_hr_zone": {"lower": 120, "upper": 140, "formula_note": f"{_MOCK} 离线占位估算"},
            "rpe_range": "4-6",
            "talk_test": f"{_MOCK} 能说完整句子但不能唱歌",
            "stop_signals": ["胸闷胸痛", "呼吸困难", "头晕", "关节锐痛"],
        },
        "risk_notes": [
            {"level": "中", "item": f"{_MOCK} 离线占位风险项", "reason": "占位", "action": "配置真实模型后重新生成"}
        ],
        "forbidden_or_limited": [
            {"target": f"{_MOCK} 憋气类动作", "restriction": "禁止", "reason": "占位", "source": "安全"}
        ],
    }
