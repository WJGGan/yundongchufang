#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
SFT 训练数据生成 pipeline
=========================

为两个数据集各生成样本（共用同一批 mock 学生档案，与现有 20 条样本同构）：
  - finetune/generated/profile_sft_generated.json       体质画像理解（档案 -> 自然语言理解）
  - finetune/generated/prescription_sft_generated.json  运动处方生成（档案+请求 -> 自然语言处方）

设计要点：
  1. 案例规格（学段x性别x体成分x体能五维x健康标签x数据质量场景x难例类型）由代码按固定
     随机种子排布，多样性与覆盖率由构造保证；拦截案例（应拒绝开方）占比 >= 10%。
  2. 档案骨架（年级/年龄/身高/体重/BMI 带）由代码预计算，LLM 只填体测成绩与健康叙事；
     两表一致性、学段空值规则、确定性字段由代码强制与校验（失败带错误信息重试）。
  3. 画像/处方回答沿用样本文件原 system prompt，few-shot 从现有 20 条样本中按
     学段/性别/拦截场景挑选，保证风格与分布对齐。
  4. 三层质检：代码硬校验 -> 启发式检查 -> LLM 评审打分（不过线自动重生成一次，
     仍不过则标记 needs_review 保留人工复核）。

用法：
  python3 generate.py plan                      # 查看前 20 个案例规格
  python3 generate.py run --start 0 --end 3     # 生成第 0..2 号案例
  python3 generate.py run --start 3 --end 23    # 继续生成
  python3 generate.py assemble                  # 汇总 output/cases/ -> finetune/generated/
  python3 generate.py stats                     # 已生成案例统计

API key 读取顺序：环境变量 GLM_API_KEY > 本目录 api_key.txt
"""
import argparse
import json
import os
import random
import re
import sys
import time
import urllib.error
import urllib.request
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

ROOT = Path(__file__).resolve().parent
FINETUNE = ROOT.parent
OUT_DIR = ROOT / "output"
CASE_DIR = OUT_DIR / "cases"
GEN_DIR = FINETUNE / "generated"

API_BASE = os.environ.get("GLM_API_BASE", "https://api-gateway.glm.ai/v1")
DEFAULT_MODEL = os.environ.get("GLM_MODEL", "glm-5.3")
SEED = 20261116
PLAN_SIZE = 100

PROFILE_SAMPLE = FINETUNE / "profile_sft_sample.json"
RX_SAMPLE = FINETUNE / "prescription_sft_sample.json"

# ---------------------------------------------------------------- 基础设施

def log(msg):
    print(msg, file=sys.stderr, flush=True)


def api_key():
    k = os.environ.get("GLM_API_KEY", "").strip()
    if k:
        return k
    f = ROOT / "api_key.txt"
    if f.exists():
        return f.read_text().strip()
    sys.exit("未找到 API key：请设置环境变量 GLM_API_KEY 或创建 finetune/datagen/api_key.txt")


_KEY = None

def chat(messages, model, temperature=0.7, max_tokens=16000, retries=3):
    """调用 chat/completions，返回 content 字符串。
    glm-5.3 是推理模型，思考部分也计入 completion tokens；若被截断则翻倍 max_tokens 重试。"""
    global _KEY
    if _KEY is None:
        _KEY = api_key()
    last_err = None
    for attempt in range(retries):
        payload = json.dumps({
            "model": model,
            "messages": messages,
            "temperature": temperature,
            "max_tokens": max_tokens,
        }).encode("utf-8")
        try:
            req = urllib.request.Request(
                API_BASE + "/chat/completions",
                data=payload,
                headers={"Content-Type": "application/json",
                         "Authorization": "Bearer " + _KEY},
            )
            with urllib.request.urlopen(req, timeout=600) as resp:
                data = json.loads(resp.read().decode("utf-8"))
            choice = data["choices"][0]
            content = (choice["message"].get("content") or "").strip()
            if choice.get("finish_reason") == "length":
                max_tokens = min(max_tokens * 2, 65536)
                raise RuntimeError(f"输出被 max_tokens 截断，下次放宽到 {max_tokens}")
            if not content:
                raise RuntimeError("返回 content 为空")
            return content
        except Exception as e:  # noqa: BLE001
            last_err = e
            wait = 5 * (attempt + 1)
            if "429" in str(e):
                wait = 45 * (attempt + 1)  # 限流需要更长退避
            log(f"    API 调用失败({attempt + 1}/{retries}): {e}；{wait}s 后重试")
            time.sleep(wait)
    raise RuntimeError(f"API 连续失败: {last_err}")


def strip_fences(text):
    text = text.strip()
    m = re.search(r"```(?:json)?\s*(.*?)```", text, re.S)
    if m:
        text = m.group(1).strip()
    # 兜底：截取第一个 { 到最后一个 }
    if not text.startswith("{"):
        i, j = text.find("{"), text.rfind("}")
        if i >= 0 and j > i:
            text = text[i:j + 1]
    return text


# ---------------------------------------------------------------- 领域常量

PE_KEYS = ["YEARSTART", "YEAREND", "XB", "NL", "SG", "TZ", "FHL", "ZYSL", "YYSL",
           "ZYJSL", "YYJSL", "JSLPJ", "JZ", "UP_TIME", "SCHOOL_GRADE"]
FT_KEYS = ["NJ", "XB", "SGCJ", "TZCJ", "FHLCJ", "WSMCJ", "LDTYCJ", "ZWTQQCJ",
           "WSMWFPCJ", "YFZTSCJ", "BBMCJ", "YWQZCJ", "YQMCJ", "YTXSCJ"]
HP_KEYS = ["chronic_conditions", "medications", "injury_history", "recent_symptoms",
           "family_history", "vitals", "exercise_history", "lifestyle"]
EH_KEYS = ["weekly_frequency", "typical_duration_min", "main_activities",
           "training_experience", "sedentary_hours_per_day"]
LS_KEYS = ["sleep_hours", "screen_time_hours", "breakfast_regular"]
INJ_KEYS = ["site", "type", "date", "status", "note"]
ITEM_KEYS = ["FHLCJ", "WSMCJ", "LDTYCJ", "ZWTQQCJ", "WSMWFPCJ", "YFZTSCJ",
             "BBMCJ", "YWQZCJ", "YQMCJ", "YTXSCJ"]

FIELD_SEMANTICS = (
    "physical_exam（体检表）字段：YEARSTART/YEAREND=学年起止年份；XB=性别；NL=年龄(岁)；"
    "SG=身高(cm)；TZ=体重(kg)；FHL=肺活量(ml)；ZYSL/YYSL=左/右眼裸眼视力(5分记录法，4.0-5.3)；"
    "ZYJSL/YYJSL=左/右眼矫正视力；JSLPJ=视力评价(正常/轻度近视/中度近视/高度近视)；"
    "JZ=脊柱检查结论(未见异常/具体异常描述/空)；UP_TIME=录入日期；SCHOOL_GRADE=年级。\n"
    "fitness_test（体测表）字段：NJ=年级；XB=性别；SGCJ=身高；TZCJ=体重；FHLCJ=肺活量(ml)；"
    "WSMCJ=50米跑(秒,如\"8.9\")；LDTYCJ=立定跳远(cm,整数)；ZWTQQCJ=坐位体前屈(cm,一位小数)；"
    "WSMWFPCJ=50米×8往返跑(秒,如\"110.0\")；YFZTSCJ=一分钟跳绳(个,整数)；"
    "BBMCJ=800米跑(格式\"X分XX秒\")；YWQZCJ=一分钟仰卧起坐(个,整数)；"
    "YQMCJ=1000米跑(格式\"X分XX秒\")；YTXSCJ=引体向上(个,整数)。\n"
    "所有体检/体测字段的值一律为字符串；该年级不开展的项目填空字符串\"\"。"
)

GRADES = [  # (年级, 学段, 最小年龄)
    ("小学二年级", "小学低年级", 7),
    ("小学三年级", "小学中年级", 8),
    ("小学四年级", "小学中年级", 9),
    ("小学五年级", "小学高年级", 10),
    ("小学六年级", "小学高年级", 11),
    ("初一", "初中", 12), ("初二", "初中", 13), ("初三", "初中", 14),
    ("高一", "高中", 15), ("高二", "高中", 16), ("高三", "高中", 17),
]
GRADE_AGE = {g: a for g, _, a in GRADES}
GRADE_SEG = {g: s for g, s, _ in GRADES}

# 每百例学段配额（小学 36 / 初中 32 / 高中 32，内部按年级轮转）
SEG_QUOTA = [("小学低年级", 10), ("小学中年级", 12), ("小学高年级", 14),
             ("初中", 32), ("高中", 32)]

HEIGHT_MEAN = {  # age -> (男, 女) 平均身高 cm
    7: (122, 121), 8: (128, 127), 9: (134, 133), 10: (140, 139), 11: (146, 146),
    12: (153, 152), 13: (160, 156), 14: (166, 158), 15: (170, 160), 16: (172, 161),
    17: (174, 161), 18: (175, 162),
}

# BMI 分类锚点（近似 WGOC/国标口径，线性插值）
_OW = {"男": {7: 17.4, 10: 19.6, 12: 21.0, 14: 22.6, 16: 23.5, 18: 24.0},
       "女": {7: 17.2, 10: 19.5, 12: 21.1, 14: 22.8, 16: 23.6, 18: 24.0}}
_OB = {"男": {7: 19.2, 10: 22.5, 12: 24.7, 14: 26.4, 16: 27.4, 18: 28.0},
       "女": {7: 18.9, 10: 22.1, 12: 24.5, 14: 26.3, 16: 27.2, 18: 28.0}}
_TH = {"男": {7: 13.4, 10: 14.2, 12: 14.9, 14: 15.7, 16: 16.5, 18: 17.2},
       "女": {7: 13.2, 10: 14.0, 12: 14.7, 14: 15.8, 16: 16.6, 18: 17.3}}


def _interp(anchors, age):
    ks = sorted(anchors)
    age = min(max(age, ks[0]), ks[-1])
    for a, b in zip(ks, ks[1:]):
        if a <= age <= b:
            t = (age - a) / (b - a)
            return anchors[a] + t * (anchors[b] - anchors[a])
    return anchors[ks[-1]]


def bmi_band(age, sex, label):
    ow, ob, th = _interp(_OW[sex], age), _interp(_OB[sex], age), _interp(_TH[sex], age)
    return {
        "消瘦": (max(th - 1.2, 12.5), th - 0.2),
        "正常": (th + 0.5, ow - 0.6),
        "超重": (ow + 0.2, ob - 0.3),
        "肥胖": (ob + 0.3, ob + 4.0),
        "重度肥胖": (ob + 4.0, ob + 7.0),
    }[label]


def tested_items(grade, sex):
    base = ["FHLCJ", "WSMCJ", "ZWTQQCJ"]
    if grade.startswith("小学"):
        base.append("YFZTSCJ")
        if grade[2] in "三四五六":
            base.append("YWQZCJ")
        if grade[2] in "五六":
            base.append("WSMWFPCJ")
    else:
        base.append("LDTYCJ")
        if sex == "男":
            base += ["YQMCJ", "YTXSCJ"]
        else:
            base += ["BBMCJ", "YWQZCJ"]
    return base


LEVELS = ["较差", "及格", "中等", "良好", "优秀"]
DIMS = ["心肺耐力", "肌肉力量", "柔韧性", "速度", "爆发力"]

HEALTH_POOL = [  # (标签, 档案生成要求, 校验函数名)
    ("哮喘控制良好", "chronic_conditions 含轻度哮喘（注明近一年未急性发作），medications 含沙丁胺醇气雾剂（按需使用）"),
    ("高血压家族史", "family_history 含父亲或母亲高血压；本人血压正常"),
    ("疑似脊柱侧弯", "physical_exam.JZ 填写类似\"疑似胸段侧弯，建议专科复查\"的结论；recent_symptoms 可含久坐后肩背酸痛"),
    ("陈旧踝伤", "injury_history 含一条踝关节扭伤记录（数月前，已基本恢复，剧烈变向偶有不适）"),
    ("膝伤恢复期", "injury_history 含一条膝部损伤（恢复期，医生嘱避免深蹲/跳跃类动作）"),
    ("肩部不适", "injury_history 含一条肩部不适（过顶动作疼痛，偶有撞击感）"),
    ("缺铁性贫血恢复期", "chronic_conditions 含缺铁性贫血（已就诊、补铁治疗中），recent_symptoms 可含轻度乏力"),
    ("睡眠不足", "lifestyle.sleep_hours 不超过 7"),
    ("久坐", "exercise_history.sedentary_hours_per_day 不低于 9"),
    ("田径特长", "exercise_history 含校田径队规律训练经历，体测成绩整体偏好"),
    ("游泳习惯", "main_activities 含游泳，每周规律进行"),
    ("近视", "JSLPJ 为轻度或中度近视，裸眼视力 4.3-4.8，矫正视力 5.0"),
]

BLOCKED_POOL = [  # (类型, 档案生成要求)
    ("未控高血压", "chronic_conditions 含血压偏高（校医多次复测超标、未经专科确诊控制），vitals.blood_pressure 填 140/90 以上的具体数值，recent_symptoms 可含运动后头晕"),
    ("心血管警示症状", "recent_symptoms 含运动中胸闷/心前区压迫感，以及一次眼前发黑或晕厥经历；family_history 可含早发心血管病"),
    ("急性损伤未恢复", "injury_history 含一条 1 个月内的急性损伤（如踝关节扭伤 II 度），status 为未恢复，note 注明仍有肿胀疼痛、尚未复查"),
    ("哮喘近期急性发作", "chronic_conditions 含哮喘且近 1 个月内有急性发作/急诊经历，medications 含控制与缓解药物"),
    ("重度贫血未纠正", "chronic_conditions 含中重度缺铁性贫血（未纠正），recent_symptoms 含活动后心悸、乏力、面色苍白"),
]

BLOCKED_CHECK = {  # 类型 -> 档案需命中的关键词（任一字段文本中）
    "未控高血压": ["血压"],
    "心血管警示症状": ["胸闷", "晕厥", "眼前发黑"],
    "急性损伤未恢复": ["未恢复"],
    "哮喘近期急性发作": ["哮喘"],
    "重度贫血未纠正": ["贫血"],
}

LIKED_POOL = ["篮球", "足球", "羽毛球", "乒乓球", "骑行", "游泳", "跳舞", "轮滑",
              "跳绳", "慢跑", "爬山", "滑板"]
DISLIKED_POOL = ["长跑", "跳绳", "器械训练", "对抗性球类", "游泳", "跑步"]
VENUE_POOL = ["家庭", "小区空地", "学校操场", "公园", "健身房", "游泳馆"]
EQUIP_POOL = ["跳绳", "弹力带", "瑜伽垫", "哑铃", "单杠", "自行车", "篮球", "足球", "羽毛球拍"]
SLOT_POOL = ["放学后", "晚饭后", "清晨", "周末上午", "晚自习前"]


# ---------------------------------------------------------------- 案例规划

def build_plan(n=PLAN_SIZE):
    """生成 n 个案例规格。固定种子，结果可复现；按维度配额保证覆盖。"""
    rng = random.Random(SEED)

    # 学段序列
    seg_list = []
    for seg, q in SEG_QUOTA:
        seg_list += [seg] * q
    seg_list = (seg_list * ((n // 100) + 1))[:n]
    rng.shuffle(seg_list)

    # 体成分 / 数据质量 / 拦截 配额
    body_list = (["消瘦"] * 10 + ["正常"] * 55 + ["超重"] * 20 + ["肥胖"] * 15)
    body_list = (body_list * ((n // 100) + 1))[:n]
    rng.shuffle(body_list)
    scen_list = (["clean"] * 70 + ["missing"] * 10 + ["conflict"] * 7 + ["exemption"] * 13)
    scen_list = (scen_list * ((n // 100) + 1))[:n]
    rng.shuffle(scen_list)
    blocked_idx = set(rng.sample(range(n), max(1, round(n * 0.12))))
    blocked_type = {bi: BLOCKED_POOL[j % len(BLOCKED_POOL)]
                    for j, bi in enumerate(sorted(blocked_idx))}
    # 难例（互斥，只给非拦截案例）
    hard_pool = [i for i in range(n) if i not in blocked_idx]
    rng.shuffle(hard_pool)
    hard_map = {}
    for kind, cnt in [("时间紧张", n // 10), ("器械匮乏", n // 8), ("偏好冲突", n // 10)]:
        for i in hard_pool[:cnt]:
            hard_map[i] = kind
        hard_pool = hard_pool[cnt:]

    grade_cycle = {seg: [g for g, s, _ in GRADES if s == seg] for seg, _ in SEG_QUOTA}
    seg_count = {}

    specs = []
    for i in range(n):
        r = random.Random(SEED * 1000 + i)  # 每案例独立种子，切片运行结果稳定
        seg = seg_list[i]
        gs = grade_cycle[seg]
        grade = gs[seg_count.get(seg, 0) % len(gs)]
        seg_count[seg] = seg_count.get(seg, 0) + 1
        sex = "男" if i % 2 == 0 else "女"
        age = GRADE_AGE[grade] + r.choice([0, 1, 1, 2])

        body = body_list[i]
        blocked = None
        if i in blocked_idx:
            btype, breq = blocked_type[i]
            if btype == "未控高血压" and body in ("消瘦", "正常"):
                body = r.choice(["超重", "肥胖"])  # 未控高血压配超重/肥胖更真实
            blocked = {"type": btype, "req": breq}

        hm, hw = HEIGHT_MEAN[min(max(age, 7), 18)]
        height = round((hm if sex == "男" else hw) + r.uniform(-6, 6) + (age - GRADE_AGE[grade]) * 2, 1)
        lo, hi = bmi_band(age, sex, body)
        bmi = round(r.uniform(lo, hi), 1)
        weight = round(bmi * (height / 100) ** 2, 1)

        # 体能五维：体成分影响心肺/速度，整体随机
        def pick_level(shift=0):
            w = [15, 25, 30, 20, 10]
            idx = r.choices(range(5), weights=w)[0] + shift
            return LEVELS[min(max(idx, 0), 4)]
        shift_cv = -1 if body in ("超重", "肥胖") else 0
        levels = {
            "心肺耐力": pick_level(shift_cv),
            "肌肉力量": pick_level(-1 if body == "肥胖" else 0),
            "柔韧性": pick_level(),
            "速度": pick_level(shift_cv),
            "爆发力": pick_level(shift_cv),
        }

        # 健康标签
        health = []
        if not blocked:
            k = r.choices([0, 1, 2], weights=[30, 45, 25])[0]
            pool = HEALTH_POOL[:]
            r.shuffle(pool)
            for tag, req in pool:
                if len(health) >= k:
                    break
                if tag == "田径特长" and (body in ("超重", "肥胖") or min(levels.values()) == "较差"):
                    continue
                if tag in [h[0] for h in health]:
                    continue
                health.append((tag, req))

        # 数据质量场景细节
        scen = scen_list[i]
        detail = {}
        items = tested_items(grade, sex)
        if scen == "missing":
            pool = [["FHL"], ["JZ"], ["vitals"], ["training_experience"]]
            cand_items = [x for x in items if x not in ("FHLCJ",)]
            pool.append([r.choice(cand_items)])
            r.shuffle(pool)
            detail["blank"] = sorted({x for grp in pool[:r.choice([2, 3])] for x in grp})
        elif scen == "conflict":
            f, d = r.choice([("SGCJ", r.choice([6, 8, 10, 12])), ("TZCJ", r.choice([5, 6, 8]))])
            detail["field"] = f
            detail["delta"] = d * r.choice([1, -1])
        elif scen == "exemption":
            cand = [x for x in items if x in ("BBMCJ", "YQMCJ", "WSMWFPCJ", "YFZTSCJ", "LDTYCJ", "WSMCJ")]
            detail["item"] = r.choice(cand)
            detail["reason"] = r.choice(["膝部伤病恢复期", "踝部伤病恢复期", "病假缺席补测未安排", "哮喘发作后医嘱暂缓剧烈跑步"])

        # 处方请求
        rx = build_rx(r, grade, sex, body, levels, hard_map.get(i), blocked)

        specs.append({
            "idx": i,
            "student_id": f"BJ2026{i:03d}{r.randint(100, 999)}",
            "grade": grade, "segment": seg, "sex": sex, "age": age,
            "height": height, "weight": weight, "bmi": bmi, "body": body,
            "levels": levels, "health": health, "blocked": blocked,
            "scenario": scen, "scenario_detail": detail,
            "hard_case": hard_map.get(i), "rx": rx,
        })
    return specs


def build_rx(r, grade, sex, body, levels, hard_case, blocked):
    is_primary = grade.startswith("小学")
    weak = min(levels, key=lambda d: LEVELS.index(levels[d]))

    def special_item(dim):
        """弱项 -> 该年级该性别实际开展的体测专项；无对应项目返回 None。"""
        if dim == "心肺耐力":
            if is_primary:
                return "50米×8往返跑" if grade[2] in "五六" else "一分钟跳绳"
            return "1000米" if sex == "男" else "800米"
        if dim == "肌肉力量":
            if is_primary:
                return "仰卧起坐" if grade[2] in "三四五六" else None
            return "引体向上" if sex == "男" else "仰卧起坐"
        if dim == "柔韧性":
            return "坐位体前屈"
        if dim == "速度":
            return "50米"
        if dim == "爆发力":
            return "一分钟跳绳" if is_primary else "立定跳远"
        return None

    goals = []
    if body in ("超重", "肥胖"):
        goals.append("健康体重管理")
    if LEVELS.index(levels["心肺耐力"]) <= 1 and "心肺耐力提升" not in goals:
        goals.append("心肺耐力提升")
    sp = special_item(weak)
    if sp:
        goals.append(f"体测专项提升:{sp}")
    if is_primary and r.random() < 0.4:
        goals.append(r.choice(["身高促进与骨骼发育", "爆发力与灵敏协调"]))
    if not is_primary and len(goals) < 2 and r.random() < 0.5:
        goals.append(r.choice(["肌肉力量与耐力", "体态改善", "柔韧性改善"]))
    goals = list(dict.fromkeys(goals))[:3] or ["心肺耐力提升"]

    days = 2 if hard_case == "时间紧张" else r.choice([3, 3, 4, 4, 5])
    minutes = 30 if hard_case == "时间紧张" else r.choice([30, 35, 40, 45, 60])

    if hard_case == "器械匮乏":
        venue = ["家庭"]
        equipment = r.choice([["瑜伽垫"], []])
    else:
        venue = r.sample(VENUE_POOL[:4], r.choice([2, 3]))
        if not is_primary and r.random() < 0.25:
            venue.append("健身房")
        equipment = r.sample(EQUIP_POOL, r.choice([2, 3, 4]))
        if "单杠" in equipment and "学校操场" not in venue and "健身房" not in venue:
            equipment.remove("单杠")

    liked = r.sample(LIKED_POOL, r.choice([1, 2]))
    disliked = []
    if hard_case == "偏好冲突":
        # 不喜欢的项目恰是目标的主流手段
        if any("1000米" in g or "800米" in g or "心肺" in g for g in goals):
            disliked = [r.choice(["长跑", "跑步"])]
        elif any("跳绳" in g for g in goals):
            disliked = ["跳绳"]
        else:
            disliked = ["器械训练"]
    elif r.random() < 0.5:
        d = r.choice(DISLIKED_POOL)
        if d not in liked:
            disliked = [d]
    liked = [x for x in liked if x not in disliked]

    slot = r.choice(SLOT_POOL if not is_primary else SLOT_POOL[:4])
    return {
        "goals": goals,
        "available_time": {"days_per_week": days, "minutes_per_session": minutes,
                           "preferred_slot": slot},
        "venue": venue, "equipment": equipment,
        "preferences": {"liked": liked, "disliked": disliked},
        "guardian_consent": True,
    }


# ---------------------------------------------------------------- 档案生成（Stage A）

def archive_example():
    """取现有样本第 1 条的档案 JSON 作为格式示例。"""
    data = json.loads(PROFILE_SAMPLE.read_text())
    return data["samples"][0]["messages"][1]["content"]


def spec_to_prompt(spec):
    items = tested_items(spec["grade"], spec["sex"])
    lines = [
        f"- 年级：{spec['grade']}（SCHOOL_GRADE 与 NJ 均填 \"{spec['grade']}\"）；性别：{spec['sex']}；年龄：{spec['age']}",
        f"- 身高 {spec['height']} cm、体重 {spec['weight']} kg（SG/TZ 与 SGCJ/TZCJ 必须恰好等于这两个值；对应 BMI 约 {spec['bmi']}，属\"{spec['body']}\"，其他数据不得与之矛盾）",
        "- YEARSTART=\"2025\"，YEAREND=\"2026\"，UP_TIME 为 2025-09 或 2025-10 的某一天",
        f"- 需要填写成绩的体测项目：{', '.join(items)}；其余体测项目一律填 \"\"",
        f"- 体能水平（请按《国家学生体质健康标准》中{spec['grade']}{spec['sex']}生的评分档位设定成绩，宁可保守）："
        + "，".join(f"{d}={v}" for d, v in spec["levels"].items()),
    ]
    if spec["blocked"]:
        lines.append(f"- 【安全关键设定·必须体现】{spec['blocked']['type']}：{spec['blocked']['req']}")
    for tag, req in spec["health"]:
        lines.append(f"- 健康设定「{tag}」：{req}")
    if not spec["health"] and not spec["blocked"]:
        lines.append("- 无特殊疾病与伤病：chronic_conditions/medications/injury_history/recent_symptoms 为空列表")
    sd = spec["scenario_detail"]
    if spec["scenario"] == "exemption":
        lines.append(f"- 免测设定：体测项目 {sd['item']} 的值填 \"免测\"，原因是「{sd['reason']}」，"
                     "健康扩展信息中要有与之呼应的记录（如伤病史或近期症状）")
    rx = spec["rx"]
    lines.append(f"- 学生平时的运动偏好：喜欢 {rx['preferences']['liked'] or ['无特别喜好']}，"
                 f"不喜欢 {rx['preferences']['disliked'] or ['无']}；exercise_history 的内容要与偏好、"
                 f"体能水平自然呼应（运动少的学生体能应偏弱，特长生反之）")
    lines.append("- vitals 可填常见合理值或留空；视力与 JSLPJ 一致；叙事字段（伤病 note、training_experience 等）"
                 "写具体自然的中文，避免套话")
    return "\n".join(lines)


ARCHIVE_SYSTEM = (
    "你是青少年运动健康领域的数据构造专家，为模型微调构造中国中小学生的 mock 健康档案。"
    "你会收到一份案例规格，请严格按规格生成一份档案 JSON。\n\n"
    "输出要求：只输出一个 JSON 对象，不要任何解释、注释或 markdown 代码块。"
    "顶层键为 physical_exam、fitness_test、health_profile 三个，内部字段名、层级与下面的示例完全一致"
    "（一个键不多、一个键不少）。\n\n" + FIELD_SEMANTICS + "\n\n示例档案（仅供格式参考，内容按规格重新生成）：\n"
)


def gen_archive(spec, model):
    sys_prompt = ARCHIVE_SYSTEM + archive_example()
    user = "案例规格：\n" + spec_to_prompt(spec)
    messages = [{"role": "system", "content": sys_prompt},
                {"role": "user", "content": user}]
    errors_prev = None
    for attempt in range(3):
        if errors_prev:
            messages = messages[:2] + [{
                "role": "user",
                "content": "上一次输出存在以下问题，请全部修正后重新输出完整 JSON（仍只输出 JSON）：\n- "
                           + "\n- ".join(errors_prev) + "\n\n上一次输出：\n" + raw,
            }]
        raw = chat(messages, model, temperature=0.8, max_tokens=24000)
        try:
            arch = json.loads(strip_fences(raw))
        except json.JSONDecodeError as e:
            errors_prev = [f"JSON 解析失败: {e}"]
            continue
        arch = force_skeleton(arch, spec)
        errors = validate_archive(arch, spec)
        if not errors:
            return apply_scenario(arch, spec), attempt + 1
        errors_prev = errors
        log(f"    档案校验未通过(尝试{attempt + 1}): {errors[:4]}")
    raise RuntimeError(f"档案生成 3 次均未通过校验: {errors_prev[:5]}")


def force_skeleton(arch, spec):
    """确定性字段由代码直接覆写，消除一类失败。"""
    pe = arch.get("physical_exam", {})
    ft = arch.get("fitness_test", {})
    pe.update({"YEARSTART": "2025", "YEAREND": "2026", "XB": spec["sex"],
               "NL": str(spec["age"]), "SG": str(spec["height"]), "TZ": str(spec["weight"]),
               "SCHOOL_GRADE": spec["grade"]})
    ft.update({"NJ": spec["grade"], "XB": spec["sex"],
               "SGCJ": str(spec["height"]), "TZCJ": str(spec["weight"])})
    if str(pe.get("FHL", "")).strip():
        ft["FHLCJ"] = str(pe["FHL"])
    return arch


def validate_archive(arch, spec):
    errors = []
    if set(arch) != {"physical_exam", "fitness_test", "health_profile"}:
        return [f"顶层键应为 physical_exam/fitness_test/health_profile，实际: {sorted(arch)}"]
    pe, ft, hp = arch["physical_exam"], arch["fitness_test"], arch["health_profile"]
    if set(pe) != set(PE_KEYS):
        errors.append(f"physical_exam 键不符，多: {set(pe) - set(PE_KEYS)}，少: {set(PE_KEYS) - set(pe)}")
    if set(ft) != set(FT_KEYS):
        errors.append(f"fitness_test 键不符，多: {set(ft) - set(FT_KEYS)}，少: {set(FT_KEYS) - set(ft)}")
    if set(hp) != set(HP_KEYS):
        errors.append(f"health_profile 键不符，多: {set(hp) - set(HP_KEYS)}，少: {set(HP_KEYS) - set(hp)}")
    if errors:
        return errors

    for k, v in list(pe.items()) + list(ft.items()):
        if not isinstance(v, str):
            errors.append(f"{k} 的值必须是字符串，当前是 {type(v).__name__}")
    if not re.match(r"^2025-(09|10)-\d{2}$", pe.get("UP_TIME", "")):
        errors.append("UP_TIME 需为 2025-09-XX 或 2025-10-XX")
    # 学段空值规则
    items = tested_items(spec["grade"], spec["sex"])
    exemption_item = spec["scenario_detail"].get("item") if spec["scenario"] == "exemption" else None
    for k in ITEM_KEYS:
        v = str(ft.get(k, "")).strip()
        if k in items:
            if k == exemption_item:
                if v != "免测":
                    errors.append(f"{k} 按规格应填 \"免测\"，当前 \"{v}\"")
            elif not v:
                errors.append(f"{k} 是{spec['grade']}{spec['sex']}生的应测项目，不应为空")
        elif v:
            errors.append(f"{k} 不是{spec['grade']}{spec['sex']}生的项目，应为空字符串，当前 \"{v}\"")
    # 格式
    for k in ("YQMCJ", "BBMCJ"):
        v = str(ft.get(k, "")).strip()
        if v and v != "免测" and not re.match(r"^\d分[0-5]\d秒$", v):
            errors.append(f"{k} 格式应为 \"X分XX秒\"，当前 \"{v}\"")
    for k in ("WSMCJ", "ZWTQQCJ", "WSMWFPCJ"):
        v = str(ft.get(k, "")).strip()
        if v and v != "免测":
            try:
                float(v)
            except ValueError:
                errors.append(f"{k} 应为数字字符串，当前 \"{v}\"")
    for k in ("LDTYCJ", "YFZTSCJ", "YWQZCJ", "YTXSCJ", "FHLCJ"):
        v = str(ft.get(k, "")).strip()
        if v and v != "免测" and not v.isdigit():
            errors.append(f"{k} 应为整数字符串，当前 \"{v}\"")
    # 合理范围粗检
    rng_check = [("FHLCJ", 600, 7000), ("WSMCJ", 6.0, 16.0), ("LDTYCJ", 50, 320),
                 ("ZWTQQCJ", -10, 30), ("WSMWFPCJ", 80, 160), ("YFZTSCJ", 10, 230),
                 ("YWQZCJ", 5, 75), ("YTXSCJ", 0, 30)]
    for k, lo, hi in rng_check:
        v = str(ft.get(k, "")).strip()
        if v and v != "免测":
            try:
                x = float(v)
                if not (lo <= x <= hi):
                    errors.append(f"{k}={v} 超出合理范围 [{lo},{hi}]")
            except ValueError:
                pass
    bp = str(hp.get("vitals", {}).get("blood_pressure", "")).strip()
    if bp and not re.match(r"^\d{2,3}/\d{2,3}(\s*mmHg)?$", bp):
        errors.append(f"blood_pressure 格式应为 \"收缩压/舒张压\"，当前 \"{bp}\"")
    # health_profile 结构
    eh, ls = hp.get("exercise_history", {}), hp.get("lifestyle", {})
    if set(eh) != set(EH_KEYS):
        errors.append(f"exercise_history 键不符: {sorted(eh)}")
    if set(ls) != set(LS_KEYS):
        errors.append(f"lifestyle 键不符: {sorted(ls)}")
    for inj in hp.get("injury_history", []):
        if not isinstance(inj, dict) or set(inj) != set(INJ_KEYS):
            errors.append(f"injury_history 条目键应为 {INJ_KEYS}")
    # 拦截案例红旗核验
    if spec["blocked"]:
        blob = json.dumps(hp, ensure_ascii=False) + json.dumps(pe, ensure_ascii=False)
        kws = BLOCKED_CHECK[spec["blocked"]["type"]]
        if not any(k in blob for k in kws):
            errors.append(f"拦截案例「{spec['blocked']['type']}」要求档案含关键信息（{'/'.join(kws)}），未找到")
        if spec["blocked"]["type"] == "未控高血压":
            m = re.match(r"^(\d{2,3})/(\d{2,3})", bp)
            if not m or int(m.group(1)) < 140:
                errors.append("未控高血压案例 vitals.blood_pressure 需 >= 140/90 的实测值")
    # 健康标签核验（抽查可机检项）
    for tag, _ in spec["health"]:
        blob = json.dumps(hp, ensure_ascii=False)
        if tag == "哮喘控制良好" and "哮喘" not in blob:
            errors.append("健康设定「哮喘控制良好」未体现在 chronic_conditions")
        if tag == "疑似脊柱侧弯" and "侧弯" not in str(pe.get("JZ", "")):
            errors.append("健康设定「疑似脊柱侧弯」未体现在 JZ")
        if tag == "睡眠不足" and float(ls.get("sleep_hours", 9) or 9) > 7.5:
            errors.append("健康设定「睡眠不足」要求 sleep_hours <= 7")
        if tag == "久坐" and float(eh.get("sedentary_hours_per_day", 0) or 0) < 9:
            errors.append("健康设定「久坐」要求 sedentary_hours_per_day >= 9")
        if tag in ("陈旧踝伤", "膝伤恢复期", "肩部不适") and not hp.get("injury_history"):
            errors.append(f"健康设定「{tag}」要求 injury_history 非空")
    return errors


def apply_scenario(arch, spec):
    """clean 之外的数据质量场景由代码落地，保证可控。"""
    sd = spec["scenario_detail"]
    pe, ft, hp = arch["physical_exam"], arch["fitness_test"], arch["health_profile"]
    if spec["scenario"] == "missing":
        for f in sd["blank"]:
            if f == "FHL":
                pe["FHL"] = ""
                ft["FHLCJ"] = ""
            elif f == "JZ":
                pe["JZ"] = ""
            elif f == "vitals":
                hp["vitals"] = {"resting_heart_rate": "", "blood_pressure": ""}
            elif f == "training_experience":
                hp["exercise_history"]["training_experience"] = ""
            elif f in FT_KEYS:
                ft[f] = ""
    elif spec["scenario"] == "conflict":
        f, d = sd["field"], sd["delta"]
        base = float(spec["height"] if f == "SGCJ" else spec["weight"])
        ft[f] = str(round(base + d, 1))
    return arch


def canonical_user_json(arch, rx=None):
    """按样本文件的键序重排并序列化为 user content。"""
    pe = {k: arch["physical_exam"][k] for k in PE_KEYS}
    ft = {k: arch["fitness_test"][k] for k in FT_KEYS}
    hp_src = arch["health_profile"]
    hp = {
        "chronic_conditions": hp_src["chronic_conditions"],
        "medications": hp_src["medications"],
        "injury_history": [{k: inj[k] for k in INJ_KEYS} for inj in hp_src["injury_history"]],
        "recent_symptoms": hp_src["recent_symptoms"],
        "family_history": hp_src["family_history"],
        "vitals": {"resting_heart_rate": hp_src["vitals"]["resting_heart_rate"],
                   "blood_pressure": hp_src["vitals"]["blood_pressure"]},
        "exercise_history": {k: hp_src["exercise_history"][k] for k in EH_KEYS},
        "lifestyle": {k: hp_src["lifestyle"][k] for k in LS_KEYS},
    }
    obj = {"physical_exam": pe, "fitness_test": ft, "health_profile": hp}
    if rx is not None:
        obj["prescription_request"] = rx
    return json.dumps(obj, ensure_ascii=False, indent=2)


# ---------------------------------------------------------------- 回答生成（Stage B/C）

def load_exemplars(path):
    data = json.loads(Path(path).read_text())
    sys_prompt = data["samples"][0]["messages"][0]["content"]
    return sys_prompt, data["samples"], data.get("purpose", ""), data.get("version", "")


def pick_exemplars(samples, spec, blocked_tags, k=2):
    def score(s):
        tags = s["meta"]["case_tags"]
        seg = "小学" if spec["grade"].startswith("小学") else ("初中" if spec["grade"].startswith("初") else "高中")
        sc = 0
        if seg in tags:
            sc += 2
        if spec["sex"] in tags:
            sc += 1
        is_blocked_ex = any(t in tags for t in blocked_tags)
        if bool(spec["blocked"]) == is_blocked_ex:
            sc += 4
        return sc
    ranked = sorted(samples, key=score, reverse=True)
    return ranked[:k]


def gen_answer(kind, spec, user_content, model, sys_prompt, exemplars, feedback=None, temp=0.6):
    messages = [{"role": "system", "content": sys_prompt}]
    for ex in exemplars:
        messages.append({"role": "user", "content": ex["messages"][1]["content"]})
        messages.append({"role": "assistant", "content": ex["messages"][2]["content"]})
    messages.append({"role": "user", "content": user_content})
    if feedback:
        messages.append({"role": "assistant", "content": feedback["answer"]})
        messages.append({"role": "user", "content": "你上一条回答存在以下问题，请重写一条修正后的完整回答"
                                                    "（仍为单段自然中文，不要解释修改过程）：\n- "
                                                    + "\n- ".join(feedback["issues"])})
    return chat(messages, model, temperature=temp, max_tokens=24000)


def heuristic_check(kind, text, spec):
    """返回 (硬错误列表, 警告列表)。"""
    errors, warns = [], []
    t = text.strip()
    if "\n" in t:
        errors.append("回答必须是单段文字，不能有换行")
    if re.search(r"[#*`]|(^|\s)[-•]\s", t):
        errors.append("回答不能包含 markdown 标记或列表符号")
    if "{" in t or "}" in t:
        errors.append("回答不能包含 JSON 大括号")
    lo, hi = (330, 850) if kind == "profile" else (350, 1150)
    if not (lo <= len(t) <= hi):
        errors.append(f"回答长度 {len(t)} 字，应在 {lo}-{hi} 字之间")
    if kind == "profile":
        if "BMI" not in t:
            errors.append("体质画像应给出 BMI 判断")
        dims_hit = sum(bool(re.search(p, t)) for p in
                       [r"肺活量|心肺", r"力量|引体|仰卧起坐", r"柔韧|体前屈", r"速度|50米", r"爆发|跳远|跳绳"])
        if dims_hit < 3:
            errors.append(f"五维体质仅覆盖 {dims_hit} 个维度，至少应涉及 3 个")
        if str(spec["height"]) not in t and str(int(spec["height"])) not in t:
            warns.append("回答未引用身高原始值")
    else:
        rx = spec["rx"]
        if "每周" not in t:
            errors.append("处方应明确每周训练安排")
        if str(rx["available_time"]["days_per_week"]) not in t:
            warns.append("未提及每周可用天数数值")
        if "分钟" not in t:
            warns.append("未出现时长（分钟）描述")
        for d in rx["preferences"]["disliked"]:
            if d in t and not re.search(d + r".{0,12}(不|讨厌|回避|避开|替|换)", t) \
               and not re.search(r"(不喜欢|讨厌|排斥|回避|不安排|避开|不用|替代|代替|换成)[^。]{0,16}" + d, t):
                warns.append(f"疑似把学生不喜欢的「{d}」直接排进计划，请人工确认")
    if spec["blocked"]:
        if not re.search(r"就医|转介|专科|复查|心内科|急诊|门诊", t):
            errors.append("拦截案例的回答必须包含就医/转介建议")
        if kind == "rx" and not re.search(r"暂不|不开|暂缓|先行|之前不|不宜开", t):
            warns.append("拦截案例的处方未明确表达暂缓开方，请人工确认")
    return errors, warns


JUDGE_SYSTEM = ("你是青少年运动健康训练数据的质检专家，熟悉《国家学生体质健康标准》与青少年运动安全规范。"
                "你的职责是对候选训练样本严格打分，发现数据不忠实与安全问题。只输出 JSON。")


def judge(kind, user_content, answer, spec, model):
    task = "体质画像理解（读档案，输出对学生体质状况的自然语言理解）" if kind == "profile" \
        else "运动处方生成（读档案与处方请求，输出自然语言运动处方）"
    extra = ""
    if spec["blocked"]:
        extra = f"\n注意：该案例为安全拦截案例（{spec['blocked']['type']}），合格的回答必须以就医/转介为先，不得照常给出完整训练计划。"
    user = (f"任务类型：{task}{extra}\n\n【学生档案（模型输入）】\n{user_content}\n\n"
            f"【候选回答（模型输出）】\n{answer}\n\n"
            "请从三个维度打分（1-5 整数）：\n"
            "1. grounding 数据忠实性：回答中引用的每个数值/事实是否与档案一致；是否编造档案中不存在的数据；"
            "等级判断是否与成绩大致相符；对空缺项目的解释是否正确（学段不设项 vs 缺测/免测）。\n"
            "2. safety 专业安全性：伤病/慢病/红旗症状是否被正确对待；禁忌与强度控制是否合理；"
            "是否越过医疗边界（下诊断、改药）。\n"
            "3. style 表达质量：单段自然流畅的中文，信息有组织而非机械罗列，无明显套话堆砌。\n"
            "4-5 分=可直接用于训练（专家只需小改）；3 分=有明显问题需修改；1-2 分=不可用。\n"
            '只输出 JSON：{"grounding":N,"safety":N,"style":N,"pass":true/false,"issues":["具体问题，无则空数组"]}'
            "，其中 pass 当且仅当三项均>=4。")
    raw = chat([{"role": "system", "content": JUDGE_SYSTEM}, {"role": "user", "content": user}],
               model, temperature=0.2, max_tokens=16000)
    try:
        v = json.loads(strip_fences(raw))
        assert all(k in v for k in ("grounding", "safety", "style", "pass"))
        v["issues"] = v.get("issues") or []
        return v
    except Exception:  # noqa: BLE001
        return {"grounding": 0, "safety": 0, "style": 0, "pass": False,
                "issues": [f"评审输出解析失败: {raw[:200]}"]}


# ---------------------------------------------------------------- 单案例流水线

def make_answer_with_qc(kind, spec, user_content, model, sys_prompt, exemplars, use_judge):
    """生成 -> 启发式校验（硬错误带反馈重试2次）-> judge（不过线重生成1次）。"""
    feedback = None
    answer, warns = None, []
    for attempt in range(3):
        answer = gen_answer(kind, spec, user_content, model, sys_prompt, exemplars,
                            feedback=feedback, temp=0.6 + 0.1 * attempt)
        errors, warns = heuristic_check(kind, answer, spec)
        if not errors:
            break
        log(f"    [{kind}] 启发式校验未通过(尝试{attempt + 1}): {errors[:3]}")
        feedback = {"answer": answer, "issues": errors}
    else:
        raise RuntimeError(f"{kind} 回答 3 次未过启发式校验: {errors}")

    verdict = None
    needs_review = False
    if use_judge:
        verdict = judge(kind, user_content, answer, spec, model)
        if not verdict["pass"]:
            log(f"    [{kind}] 评审未通过({verdict['grounding']}/{verdict['safety']}/{verdict['style']})，重生成: {verdict['issues'][:2]}")
            feedback = {"answer": answer, "issues": verdict["issues"] or ["评审认为质量不足，请更严谨地对照档案重写"]}
            answer2 = gen_answer(kind, spec, user_content, model, sys_prompt, exemplars,
                                 feedback=feedback, temp=0.7)
            errors2, warns2 = heuristic_check(kind, answer2, spec)
            if not errors2:
                verdict2 = judge(kind, user_content, answer2, spec, model)
                if (verdict2["grounding"] + verdict2["safety"] + verdict2["style"]) >= \
                   (verdict["grounding"] + verdict["safety"] + verdict["style"]):
                    answer, warns, verdict = answer2, warns2, verdict2
            needs_review = not verdict["pass"]
    return answer, {"warns": warns, "judge": verdict, "needs_review": needs_review}


def case_tags(spec):
    seg = "小学" if spec["grade"].startswith("小学") else ("初中" if spec["grade"].startswith("初") else "高中")
    tags = [seg, spec["sex"]]
    if spec["body"] != "正常":
        tags.append(spec["body"])
    tags += [t for t, _ in spec["health"]]
    if spec["blocked"]:
        tags += [spec["blocked"]["type"], "需转介"]
    scen_tag = {"missing": "数据缺失", "conflict": "两表矛盾", "exemption": "免测"}.get(spec["scenario"])
    if scen_tag:
        tags.append(scen_tag)
    if spec["hard_case"]:
        tags.append(spec["hard_case"])
    return tags


def run_case(spec, model, use_judge, profile_ctx, rx_ctx):
    idx = spec["idx"]
    out_file = CASE_DIR / f"case_{idx:03d}.json"
    if out_file.exists():
        log(f"[case {idx:03d}] 已存在，跳过")
        return json.loads(out_file.read_text())
    t0 = time.time()
    log(f"[case {idx:03d}] {spec['grade']} {spec['sex']} {spec['body']} "
        f"场景={spec['scenario']} 拦截={bool(spec['blocked'])} 难例={spec['hard_case']}")

    arch, attempts = gen_archive(spec, model)
    profile_user = canonical_user_json(arch)
    rx_user = canonical_user_json(arch, rx=spec["rx"])

    p_sys, p_samples, _, _ = profile_ctx
    r_sys, r_samples, _, _ = rx_ctx
    p_ex = pick_exemplars(p_samples, spec, blocked_tags=("需转介",))
    r_ex = pick_exemplars(r_samples, spec, blocked_tags=("拒绝开方", "转介就医", "需转介"))

    p_answer, p_qc = make_answer_with_qc("profile", spec, profile_user, model, p_sys, p_ex, use_judge)
    r_answer, r_qc = make_answer_with_qc("rx", spec, rx_user, model, r_sys, r_ex, use_judge)

    tags = case_tags(spec)
    result = {
        "idx": idx, "spec": spec, "archive_attempts": attempts,
        "profile_sample": {
            "messages": [{"role": "system", "content": p_sys},
                         {"role": "user", "content": profile_user},
                         {"role": "assistant", "content": p_answer}],
            "meta": {"student_id": spec["student_id"], "case_tags": tags,
                     "source": f"pregenerated({model})+待专家修订"},
        },
        "prescription_sample": {
            "messages": [{"role": "system", "content": r_sys},
                         {"role": "user", "content": rx_user},
                         {"role": "assistant", "content": r_answer}],
            "meta": {"student_id": spec["student_id"], "case_tags": tags,
                     "source": f"pregenerated({model})+待专家修订"},
        },
        "qc": {"profile": p_qc, "rx": r_qc},
        "elapsed_s": round(time.time() - t0, 1),
        "model": model,
    }
    for kind in ("profile", "rx"):
        if result["qc"][kind]["needs_review"]:
            key = "profile_sample" if kind == "profile" else "prescription_sample"
            result[key]["meta"]["needs_review"] = True
    CASE_DIR.mkdir(parents=True, exist_ok=True)
    out_file.write_text(json.dumps(result, ensure_ascii=False, indent=2))
    log(f"[case {idx:03d}] 完成，用时 {result['elapsed_s']}s"
        + ("（标记 needs_review）" if (p_qc["needs_review"] or r_qc["needs_review"]) else ""))
    return result


# ---------------------------------------------------------------- 命令

def cmd_plan(args):
    specs = build_plan()
    for s in specs[args.start:args.end]:
        print(f"{s['idx']:03d} {s['student_id']} {s['grade']}/{s['sex']}/{s['age']}岁 "
              f"{s['body']}(BMI {s['bmi']}) 场景={s['scenario']} "
              f"健康={[t for t, _ in s['health']] or '无'} 拦截={s['blocked']['type'] if s['blocked'] else '-'} "
              f"难例={s['hard_case'] or '-'} 目标={s['rx']['goals']}")


def cmd_run(args):
    specs = build_plan()[args.start:args.end]
    profile_ctx = load_exemplars(PROFILE_SAMPLE)
    rx_ctx = load_exemplars(RX_SAMPLE)
    model = args.model
    ok, fail = 0, 0
    with ThreadPoolExecutor(max_workers=args.workers) as pool:
        futs = {pool.submit(run_case, s, model, not args.no_judge, profile_ctx, rx_ctx): s for s in specs}
        for fut in as_completed(futs):
            s = futs[fut]
            try:
                fut.result()
                ok += 1
            except Exception as e:  # noqa: BLE001
                fail += 1
                log(f"[case {s['idx']:03d}] 失败: {e}")
    log(f"\n完成 {ok} 例，失败 {fail} 例。汇总请运行: python3 generate.py assemble")


def cmd_assemble(args):
    files = sorted(CASE_DIR.glob("case_*.json"))
    if not files:
        sys.exit("output/cases/ 下没有已生成的案例")
    _, _, p_purpose, p_ver = load_exemplars(PROFILE_SAMPLE)
    _, _, r_purpose, r_ver = load_exemplars(RX_SAMPLE)
    profiles, rxs, archives = [], [], []
    for f in files:
        c = json.loads(f.read_text())
        profiles.append(c["profile_sample"])
        rxs.append(c["prescription_sample"])
        archives.append({
            "student_id": c["spec"]["student_id"],
            "case_tags": c["profile_sample"]["meta"]["case_tags"],
            **json.loads(c["prescription_sample"]["messages"][1]["content"]),
        })
    GEN_DIR.mkdir(parents=True, exist_ok=True)
    arch_out = {"purpose": "生成的 mock 学生健康档案库（含处方请求），可复用于批量预生成与评测",
                "count": len(archives), "archives": archives}
    (GEN_DIR / "mock_archives.json").write_text(json.dumps(arch_out, ensure_ascii=False, indent=2))
    print(f"写入 {GEN_DIR / 'mock_archives.json'}（{len(archives)} 份档案）")
    for name, purpose, ver, samples in [
        ("profile_sft_generated.json", p_purpose, p_ver, profiles),
        ("prescription_sft_generated.json", r_purpose, r_ver, rxs),
    ]:
        out = {"version": ver + "+gen", "purpose": purpose,
               "generator": "finetune/datagen/generate.py",
               "sample_count": len(samples), "samples": samples}
        (GEN_DIR / name).write_text(json.dumps(out, ensure_ascii=False, indent=2))
        print(f"写入 {GEN_DIR / name}（{len(samples)} 条）")
    flagged = [c.stem for c in files
               if json.loads(c.read_text())["qc"]["profile"]["needs_review"]
               or json.loads(c.read_text())["qc"]["rx"]["needs_review"]]
    if flagged:
        print(f"其中 {len(flagged)} 例被评审标记 needs_review，建议优先人工复核: {flagged}")


def cmd_stats(args):
    files = sorted(CASE_DIR.glob("case_*.json"))
    from collections import Counter
    seg, body, scen, blocked, review = Counter(), Counter(), Counter(), 0, 0
    judge_scores = []
    for f in files:
        c = json.loads(f.read_text())
        s = c["spec"]
        seg[s["segment"]] += 1
        body[s["body"]] += 1
        scen[s["scenario"]] += 1
        blocked += bool(s["blocked"])
        review += c["qc"]["profile"]["needs_review"] or c["qc"]["rx"]["needs_review"]
        for kind in ("profile", "rx"):
            v = c["qc"][kind]["judge"]
            if v:
                judge_scores.append((v["grounding"], v["safety"], v["style"]))
    print(f"已生成 {len(files)} 例；拦截案例 {blocked}；needs_review {review}")
    print("学段:", dict(seg))
    print("体成分:", dict(body))
    print("数据质量场景:", dict(scen))
    if judge_scores:
        n = len(judge_scores)
        g, sa, st = (sum(x[i] for x in judge_scores) / n for i in range(3))
        print(f"评审均分 grounding={g:.2f} safety={sa:.2f} style={st:.2f}（{n} 条回答）")


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("plan", help="查看案例规格")
    p.add_argument("--start", type=int, default=0)
    p.add_argument("--end", type=int, default=20)
    p.set_defaults(fn=cmd_plan)
    p = sub.add_parser("run", help="生成案例")
    p.add_argument("--start", type=int, default=0)
    p.add_argument("--end", type=int, default=3)
    p.add_argument("--model", default=DEFAULT_MODEL)
    p.add_argument("--workers", type=int, default=3)
    p.add_argument("--no-judge", action="store_true", help="跳过 LLM 评审")
    p.set_defaults(fn=cmd_run)
    p = sub.add_parser("assemble", help="汇总为数据集文件")
    p.set_defaults(fn=cmd_assemble)
    p = sub.add_parser("stats", help="统计")
    p.set_defaults(fn=cmd_stats)
    args = ap.parse_args()
    args.fn(args)


if __name__ == "__main__":
    main()
