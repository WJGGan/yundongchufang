"""RAG 检索质量评测：准确率 / 召回率 / F1（仅处方阶段，画像阶段已不使用 RAG）。

用法：
    uv run python -u scripts/eval_rag.py

金标准由标注函数生成：按档案中的健康状况（哮喘、脊柱、视力、伤病、BMI）
与训练目标（体测专项等）映射到"理应被召回"的知识卡片（针对性卡片），
叠加按处方输出结构固定需要的"结构性卡片"白名单。

指标口径：
- 针对性召回率：检索结果覆盖了多少针对该生的卡片（核心指标，漏了就是真漏）
- 准确率：检索结果中有多少属于相关集合（针对性 ∪ 结构性）
- F1：上述两者对相关集合统一口径计算
对照组：词面降级（不用向量）、全量注入（召回率恒 100%，准确率即相关卡占全库比例）。
"""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.config import settings  # noqa: E402
from app.services import rag  # noqa: E402
from app.services.data_loader import all_students, knowledge_cards  # noqa: E402

# ---------------------------------------------------------------------------
# 金标准标注
# ---------------------------------------------------------------------------

# 目标关键词 → 卡片
_GOAL_CARDS = {
    "1000米": "GUIDE-26", "800米": "GUIDE-26", "50米": "GUIDE-27",
    "引体": "GUIDE-28", "体前屈": "GUIDE-29", "跳绳": "GUIDE-30",
    "立定跳远": "GUIDE-31", "身高": "GUIDE-07", "心肺": "GUIDE-08",
    "柔韧": "GUIDE-09", "体重": "GUIDE-12", "爆发力": "GUIDE-10", "灵敏": "GUIDE-10",
}

# 处方阶段结构性卡片：输出结构固定含框架/强度/营养/训练结构/安全/依从性
_RX_STRUCTURAL = {
    "GUIDE-01", "GUIDE-02", "GUIDE-04", "GUIDE-05", "GUIDE-06", "GUIDE-13",
    "GUIDE-14", "GUIDE-20", "GUIDE-21", "GUIDE-22", "GUIDE-23",
    "GUIDE-32", "GUIDE-33", "GUIDE-34",
}


def _bmi_flag(exam: dict[str, Any]) -> bool:
    try:
        height = float(exam.get("SG") or 0) / 100
        weight = float(exam.get("TZ") or 0)
        bmi = weight / (height * height)
    except (ValueError, ZeroDivisionError):
        return False
    return bmi >= 23.5 or bmi <= 15.5  # 近似界值，覆盖超重/肥胖与消瘦


def gold_condition_cards(student: dict[str, Any]) -> set[str]:
    """健康状况 → 理应召回的卡片。"""
    gold: set[str] = set()
    exam = student.get("physical_exam") or {}
    health = student.get("health_profile") or {}
    text = str(health.get("chronic_conditions") or []) + str(health.get("recent_symptoms") or [])
    if "哮喘" in text:
        gold.add("GUIDE-15")
    if "侧弯" in str(exam.get("JZ") or "") + text:
        gold.add("GUIDE-16")
    if "不良" in str(exam.get("JSLPJ") or "") or "近视" in text:
        gold.add("GUIDE-17")
    for injury in health.get("injury_history") or []:
        site = str(injury.get("site", "") if isinstance(injury, dict) else injury)
        if "踝" in site:
            gold.add("GUIDE-18")
        if "膝" in site:
            gold.add("GUIDE-19")
    if _bmi_flag(exam):
        gold.add("GUIDE-12")
    return gold


def gold_goal_cards(student: dict[str, Any]) -> set[str]:
    goals = (student.get("prescription_request") or {}).get("goals") or []
    gold: set[str] = set()
    for goal in goals:
        for keyword, card in _GOAL_CARDS.items():
            if keyword in str(goal):
                gold.add(card)
    return gold


# ---------------------------------------------------------------------------
# 指标计算
# ---------------------------------------------------------------------------


def prf(retrieved: set[str], specific: set[str], structural: set[str]) -> tuple[float, float, float, float]:
    """返回 (针对性召回率, 准确率, 统一口径召回率, F1)。specific 为空时针对性召回记 1。"""
    relevant = specific | structural
    spec_recall = len(retrieved & specific) / len(specific) if specific else 1.0
    precision = len(retrieved & relevant) / len(retrieved) if retrieved else 0.0
    recall = len(retrieved & relevant) / len(relevant) if relevant else 1.0
    f1 = 2 * precision * recall / (precision + recall) if precision + recall else 0.0
    return spec_recall, precision, recall, f1


def summarize(rows: list[tuple[float, float, float, float]]) -> str:
    n = len(rows)
    avg = [sum(r[i] for r in rows) / n for i in range(4)]
    return (
        f"针对性召回 {avg[0]:.0%} | 准确率 {avg[1]:.0%} | 召回率 {avg[2]:.0%} | F1 {avg[3]:.0%}"
    )


async def eval_rx_stage(label: str) -> None:
    import glob
    import json

    rows, misses = [], []
    latest: dict[str, str] = {}
    for path in sorted(glob.glob(str(Path(__file__).resolve().parent.parent / "app/data/profiles/*.json"))):
        latest[Path(path).name.split("_")[0]] = path  # 同一学生多份画像只取最新
    for path in latest.values():
        profile = json.load(open(path, encoding="utf-8"))
        if "[MOCK]" in json.dumps(profile, ensure_ascii=False):
            continue  # 离线占位画像不参与评测
        student = next(
            (s for s in all_students() if s["student_id"] == profile.get("student_id")), None
        )
        if student is None:
            continue
        request = student["prescription_request"]
        retrieved = {
            c["id"] for c in await rag.retrieve_knowledge_for_prescription(profile, request)
        }
        specific = gold_condition_cards(student) | gold_goal_cards(student)
        rows.append(prf(retrieved, specific, _RX_STRUCTURAL))
        for miss in specific - retrieved:
            misses.append(f"{student.get('name', '')}漏{miss}")
    print(f"  处方检索@{settings.rag_knowledge_top_k} [{label}] n={len(rows)}: {summarize(rows)}")
    if misses:
        print(f"    漏检明细: {'、'.join(misses)}")


async def main() -> None:
    total = len(knowledge_cards())
    print(f"知识库全量 {total} 张；相关集合=针对性卡片∪结构性白名单"
          f"（处方 {len(_RX_STRUCTURAL)} 张）\n")

    print("=== 混合检索（向量 + 词面）===")
    await eval_rx_stage("向量+词面")

    print("\n=== 消融：仅词面（离线降级路径）===")
    settings.embedding_api_key = ""
    rag._query_cache.clear()
    await eval_rx_stage("仅词面")

    print("\n=== 基线：全量注入（34 张全给模型）===")
    rx_rel = len(_RX_STRUCTURAL)
    print(f"  召回率恒 100%；准确率上限 ≈ 相关卡占比："
          f"处方约 ({rx_rel}+针对卡)/34 ≈ {rx_rel / total:.0%}+")


if __name__ == "__main__":
    asyncio.run(main())
