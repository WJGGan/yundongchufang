# 健康档案理解与一人一策运动处方

青少年运动健康模型的第一版实现，覆盖两项能力：

- **健康档案理解** — 读取体检与体质测试结果，输出体质画像、短板排序、健康关注点，并识别缺失与矛盾字段生成追问
- **一人一策运动处方** — 基于画像与个人条件生成 FITT-VP 结构化处方、周计划、饮食建议、风险提示与逐条引用的解释说明

前后端分离：后端提供 HTTP API，前端是一个单页应用，由后端一并托管。

---

## 快速开始

```bash
cd backend && uv sync
```

```bash
cd backend && uv run uvicorn app.main:app --reload --port 8077
```

打开 http://127.0.0.1:8077 即是运动处方报告页。顶部选择学生档案后有两种方式：

- **★ 载入已有结果**：读取预生成的画像与处方，**3 毫秒出结果**，不调用模型。
  下拉里带 ★ 的学生表示已有预生成结果（默认 5 份）。
- **重新生成**：实时调用模型。生成期间右侧滑出「AI 生成过程」面板，模型的思考过程
  按 Markdown 实时渲染（结构化 JSON 不展示原文，只显示写入进度），按钮同时变为
  「■ 停止生成」，可随时中断。耗时取决于 `LLM_THINKING`：关思考约 80 秒，
  开思考（当前默认，输出思考内容供展示）约数分钟。

除内置档案外，点工具条的 **「✎ 自行录入档案」** 可展开录入表单，填写基本信息、体测成绩、
健康状况与运动需求；点「保存档案并生成处方」后，档案会保存为
`backend/app/data/custom_students/{学号}.json`（学号由服务端生成，`CU` 前缀），
该学生随即出现在下拉列表中，并直接走画像 + 处方生成流程。

报告页是纯 HTML 流式页面：宽度跟随窗口（上限 1180px）、高度随内容增长，窄屏时分栏自动折行，
手机上也能通读。

| 路径 | 用途 |
|---|---|
| `/` 、`/report` | 运动处方报告（流式自适应页面） |
| `/workbench` | 调试工作台：分步查看画像、安全评估、处方原始结构与流式过程 |
| `/docs` | 接口文档 |

### 接入模型

当前接的是**智谱 Anthropic 兼容端点**，模型 `glm-5.3`。配置在 `backend/.env`（已 gitignore）：

```
LLM_PROVIDER=anthropic_compatible
ANTHROPIC_COMPAT_BASE_URL=https://open.bigmodel.cn/api/anthropic
ANTHROPIC_COMPAT_API_KEY=你的密钥
ANTHROPIC_COMPAT_MODEL=glm-5.3
```

四种 provider 可切，业务代码不感知：

| `LLM_PROVIDER` | 端点 |
|---|---|
| `anthropic_compatible` | 智谱 Anthropic 兼容端点 `/api/anthropic` |
| `zhipu` | 智谱 OpenAI 兼容端点 `/api/paas/v4/` |
| `openai_compatible` | 本地部署或其他 OpenAI 兼容服务，交付期用这个 |
| `mock` | 离线占位假数据，返回带 `[MOCK]` 标记，仅供前端联调 |

**GLM-5.3 是思考模型**，这一点对配置有实际影响：

- 开启思考时约 **80% 的输出 token 花在思考上**，而思考内容你永远看不到。实测同一份档案：

  | 阶段 | 思考开 | 思考关 |
  |---|---|---|
  | 画像 | 147.9s（出 10231 tok，思考 8260） | 28.8s（出 2021 tok） |
  | 处方 | 255.9s（出 15843 tok，思考 12389） | 55.2s（出 3404 tok） |
  | 合计 | 403.8s | 84.0s |

  两者生成速度相同（约 62-70 tok/s），差异全部来自 token 量。**默认 `LLM_THINKING=false`**，
  内容质量实测接近；需要更严谨推理时改为 `true`。
- `glm-5.3-flash` 反而更慢（画像 259.2s）：它产出更多思考且速度更低。flash 是便宜，不是快。
- thinking 消耗的 token 计入 `max_tokens`，默认 65536 为此预留余量。
- Anthropic 端点返回的 `content` 是块列表，provider 只取 `type: "text"` 的块；流式只透出 `text_delta`。
- anthropic SDK 2.6 起 `messages.create/stream` 不再接受顶层 `temperature`，provider 经 `extra_body` 透传。
- 单次调用耗时在分钟级，`LLM_TIMEOUT` 默认 300 秒。

## 工作流程

```
原始健康档案
     │
     ├─ [代码] 急症关键词熔断 ────────────► 命中即返回固定就医模板，不调用模型
     │
     ├─ ① LLM：档案理解
     │     输出 体质画像 + 数据质量 + 安全评估（含禁用动作标签与强度上限）
     │
     ├─ [代码] 闸门：safety.can_generate_prescription 为 false 则停止，只给转介建议
     │
     ├─ [代码] 动作候选集过滤：按禁用标签、器械、场地、年龄筛出可用动作
     │
     └─ ② LLM：处方生成（流式）
           输出 FITT-VP + 周计划 + 饮食 + 风险 + 解释引用
                │
                ├─ [代码] 校验：动作 ID 存在性、是否越出候选集、是否命中禁用标签、
                │          周计划完整性、训练日与时长是否超约束、解释条数
                │          ─► 不通过则带问题清单重生成一次
                │
                └─ [代码] 回填动作详情与替代方案（从动作库取，不由模型生成）
```

两次 LLM 调用，其余是代码。控制流由代码决定，不由模型决定。

### 代码约束只有三处

LLM 真正不可靠的地方才用代码兜住，其余交给模型：

1. **急症熔断** — 档案中出现胸痛、呼吸困难、晕厥等关键词时直接返回固定模板，不进模型
2. **动作 ID 绑定** — 处方只能引用动作库中存在的 `exercise_id`，不允许自由发明动作
3. **候选集过滤** — 器械、场地、年龄、禁用标签的筛选由代码完成，模型只在候选集内排期

体质评分等级、禁忌判断、风险分层都由模型给出，没有硬编码评分表与禁忌规则库。

---

## API

| 方法 | 路径 | 说明 |
|---|---|---|
| GET | `/api/v1/meta` | 版本、模型、资产规模 |
| GET | `/api/v1/students` | mock 档案列表（摘要） |
| GET | `/api/v1/students/{id}` | 单份完整档案 |
| GET | `/api/v1/pregenerated` | 已预生成结果的学生清单 |
| GET | `/api/v1/pregenerated/{id}` | 读取预生成的画像与处方（不调用模型） |
| GET | `/api/v1/exercises` | 动作库全量 |
| GET | `/api/v1/exercises/{id}` | 单个动作详情 |
| GET | `/api/v1/knowledge` | 知识卡片全量 |
| GET | `/api/v1/knowledge/{id}` | 单张卡片（处方引用溯源） |
| POST | `/api/v1/profile:analyze` | 档案 → 体质画像 + 安全评估 |
| POST | `/api/v1/prescription:generate` | 画像 + 请求参数 → 运动处方（SSE 流式） |

### 画像

```bash
curl -s -X POST http://127.0.0.1:8077/api/v1/profile:analyze \
  -H 'Content-Type: application/json' \
  -d "{\"record\": $(curl -s http://127.0.0.1:8077/api/v1/students/BJ2025090314)}"
```

返回 `{"emergency": null, "profile": {...}}`。命中急症熔断时 `profile` 为 null、`emergency` 有值。

### 处方

`POST /api/v1/prescription:generate`，请求体 `{record, profile}`（`profile` 可省略，省略时先自动生成一份）。以 SSE 返回：

| 事件 | 含义 |
|---|---|
| `status` | 进度说明 |
| `profile` | 自动生成的画像（请求未带 profile 时） |
| `token` | 模型原始输出片段，供前端显示进度 |
| `retry` | 触发了一次重生成，data 为问题清单 |
| `result` | 最终处方 JSON |
| `emergency` / `blocked` | 熔断或安全闸门拦截 |
| `error` | 生成失败 |
| `done` | 流结束 |

---

## 数据契约

档案分四层，前两层沿用现有系统的原字段名与字符串格式，便于对接；后两层是处方生成必需的扩展。

| 层 | 字段来源 | 说明 |
|---|---|---|
| `physical_exam` | 体检结果表 16 字段 | `SG` `TZ` `FHL` `ZYSL` `JZ` 等，全部字符串，允许空 |
| `fitness_test` | 体质结果表 16 字段 | `WSMCJ` `LDTYCJ` `ZWTQQCJ` `YQMCJ` `YTXSCJ` 等 |
| `health_profile` | **扩展** | 慢病、用药、伤病史、近期症状、家族史、生命体征、运动史、生活方式 |
| `prescription_request` | **扩展** | 目标、可用时间、场地、器械、偏好、监护人同意 |

扩展层是必须的：原两张表没有伤病史、禁忌相关信息、运动史与目标，而这些是处方个性化与安全判断的唯一输入。实际对接时这部分由前端问卷采集。

体测项目按学段设置不同（小学无立定跳远与中长跑、男生无 800 米与仰卧起坐等），因此相应字段为空属正常，prompt 中已说明，不会被误判为数据缺失。

---

## 数据资产

| 文件 | 内容 | 版本 |
|---|---|---|
| `app/data/exercises.json` | 66 个动作，含类型、器械、场地、冲击等级、最低年龄、风险标签、动作要领、常见错误、替代动作 | v1.0.0 |
| `app/data/knowledge.json` | 34 张知识卡片，带 ID 供处方引用溯源 | v1.0.0 |
| `app/data/mock_students.json` | 20 份模拟档案 | v1.0.0 |
| `app/data/emergency_keywords.json` | 24 个急症关键词与固定返回模板 | v1.0.0 |
| `app/data/pregenerated/*.json` | 5 份预生成的画像与处方，供前端秒开演示 | glm-5.3 |

动作库与知识卡片是**第一版通识内容，待首都体育学院专家审核替换**。替换时保留 ID，否则已生成的处方引用会失效。每份画像与处方都会带上所用资产的版本号。

### 动作库标签体系

`contraindication_tags` 是安全约束的对接点，词表固定为：憋气风险、高冲击、中等冲击、膝关节高负荷、踝关节负荷、腰椎高负荷、颈椎风险、肩关节高负荷、不对称负荷、最大力量、倒立体位、需保护与监护。

画像的 `safety.blocked_exercise_tags` 从这个词表取值，代码据此过滤候选集。扩充禁忌判断能力时改这个词表，不需要改代码。

器械字段中的瑜伽垫按舒适性器材处理（标为「无」并在要领中说明），否则没有垫子的学生会被筛掉全部核心与柔韧动作。

### 预生成结果

`app/data/pregenerated/` 下每个学生一个文件，含完整画像与处方、生成耗时、所用模型与思考开关。
重新生成：

```bash
cd backend && uv run python -u scripts/pregenerate.py
```

默认生成 5 份（李沐阳、陈若溪、王子轩、黄俊豪、刘星月），覆盖不同学段、性别、体能水平与约束类型。
`--all` 生成全部 20 份，也可指定学号。**串行执行**：并发会触发上游限流，单次调用会从 1 分钟拖到十几分钟。

模型或 prompt 改动后这些结果即过期，需重跑；文件里记录了 `model` 与 `generated_at` 便于判断。

### mock 档案覆盖面

20 份档案覆盖小学三年级到高三、男女、体能优秀到较差、不同目标组合，其中：

- **哮喘**（李沐阳、高敏）、**脊柱疑似侧弯**（林思彤）、**膝髌股疼痛恢复期**（刘星月）、**贫血**（徐梦琪）、**肩撞击**（赵一鸣）—— 验证禁忌识别与动作规避
- **血压 145/92 + 双亲高血压 + 运动后头晕**（马天宇）—— 预期由模型判定 `can_generate_prescription=false` 并给出转介建议
- **运动时胸闷、心前区压迫感、眼前发黑**（严子谦）—— 命中急症关键词熔断，不调用模型
- **体质表多项空缺**（杨林）、**体检身高 142 与体质身高 156 矛盾**（朱浩宇）—— 验证缺失识别与矛盾检测
- 肥胖（李沐阳、马天宇）、超重（孙浩然、彭语嫣）、偏瘦（郑凯文、徐梦琪）、优秀（黄俊豪、邓子豪）

---

## 已验证与未验证

离线占位模式下已跑通：三栏页面渲染、画像与处方全链路、SSE 流式、动作详情与知识卡片弹层、急症熔断（严子谦触发，命中「胸闷」「心前区」「压迫感」「眼前发黑」，处方按钮置灰）、动作 ID 校验（捕获了越出候选集的动作并触发重生成）、20 份档案的候选集覆盖检查。

**需接入真实模型后才能验证**：体质等级判断是否合理、短板排序是否符合专业判断、矛盾检测（朱浩宇身高差异）、`can_generate_prescription=false` 的判定（马天宇）、处方的科学性与解释质量。

---

## 本版不包含

按第一版范围约定，以下内容未实现：

- 风险分层规则库与禁忌症规则表（禁忌判断由模型承担，代码只做关键词熔断与标签过滤）
- 复测调整与处方版本对比
- 人工审核流转（处方生成后直接返回，无审核状态机）
- 指标评测集与自动评分
- 体质评分表硬编码（等级由模型判断，未落地《国家学生体质健康标准》完整查表）
- 向量检索 RAG（知识以卡片形式内嵌 prompt，知识量增长后再迁移）
- 数据库（mock 档案为 JSON 文件，处方结果不持久化）

---

## 目录结构

```
backend/
  pyproject.toml           uv 依赖
  .env.example / .env      运行配置
  app/
    main.py                服务入口，同时托管前端
    config.py              配置与版本号
    api/routes.py          全部端点
    llm/
      provider.py          供应商抽象 + JSON 提取
      mock_payload.py      离线占位返回
    prompts/
      profile.py           档案理解 prompt
      prescription.py      处方生成 prompt
    schemas/
      record.py            档案输入契约
      profile.py           画像输出契约
      prescription.py      处方输出契约
    services/
      data_loader.py       资产加载
      safety.py            急症熔断
      profile_service.py   画像生成
      prescription_service.py  候选集过滤、处方生成、校验、详情回填
    data/                  四份数据资产
frontend/
  index.html               三栏单页：档案 / 画像 / 处方
  app.js                   Vue 3（CDN，无构建步骤）
  style.css
```
