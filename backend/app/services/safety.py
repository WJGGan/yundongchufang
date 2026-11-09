"""急症熔断。

唯一的代码安全路径：命中症状关键词即不进入模型，直接返回固定模板。
"""

from __future__ import annotations

from typing import Any

from app.schemas.profile import EmergencyBlock
from app.services.data_loader import emergency_rules


def _collect_texts(record: dict[str, Any], extra_text: str = "") -> list[str]:
    profile = record.get("health_profile") or {}
    texts: list[str] = []
    texts.extend(str(item) for item in profile.get("recent_symptoms") or [])
    texts.extend(str(item) for item in profile.get("chronic_conditions") or [])
    for injury in profile.get("injury_history") or []:
        if isinstance(injury, dict):
            if str(injury.get("status", "")).strip() in {"急性期", "未恢复"}:
                texts.append(f"{injury.get('site', '')}{injury.get('type', '')}{injury.get('note', '')}")
        else:
            texts.append(str(injury))
    if extra_text:
        texts.append(extra_text)
    return [text for text in texts if text.strip()]


def check_emergency(record: dict[str, Any], extra_text: str = "") -> EmergencyBlock | None:
    """命中返回熔断结果，未命中返回 None。"""
    rules = emergency_rules()
    keywords: list[str] = rules["keywords"]
    texts = _collect_texts(record, extra_text)

    matched_keywords: list[str] = []
    matched_text: list[str] = []
    for text in texts:
        hits = [keyword for keyword in keywords if keyword in text]
        if hits:
            matched_text.append(text)
            matched_keywords.extend(hits)

    if not matched_keywords:
        return None

    template = rules["template"]
    return EmergencyBlock(
        blocked=True,
        level=template["level"],
        title=template["title"],
        message=template["message"],
        matched_keywords=sorted(set(matched_keywords)),
        matched_text=matched_text,
        immediate_advice=template["immediate_advice"],
        allowed_activity=template["allowed_activity"],
        next_step=template["next_step"],
        disclaimer=template["disclaimer"],
    )
