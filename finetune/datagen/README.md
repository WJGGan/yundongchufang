# SFT 训练数据生成 pipeline

为 `finetune/profile_sft_sample.json`（体质画像理解）与 `finetune/prescription_sft_sample.json`（运动处方生成）两个数据集批量生成同构训练样本。两个数据集**共用同一批 mock 学生档案**（与现有 20 条样本的组织方式一致），每个案例产出一条画像样本 + 一条处方样本。

## Pipeline 结构

```
build_plan()  代码按固定种子(SEED=20261116)排布 100 个案例规格
   │   学段×性别×体成分×体能五维×健康标签×数据质量场景×难例类型 全部由配额保证覆盖：
   │   - 学段：小学低/中/高年级 10/12/14，初中 32，高中 32；男女 1:1
   │   - 体成分：消瘦 10 / 正常 55 / 超重 20 / 肥胖 15
   │   - 数据质量：干净 70 / 字段缺失 10 / 两表矛盾 7 / 免测 13
   │   - 拦截案例（应拒绝开方并转介）12%：未控高血压、心血管警示症状、
   │     急性损伤未恢复、哮喘近期发作、重度贫血
   │   - 处方难例：时间紧张(2天×30分钟)、器械匮乏(仅家庭徒手)、偏好冲突
   │   档案骨架（年龄/年级/身高/体重）由代码按 BMI 分类带预计算
   ▼
Stage A  LLM 生成档案（体测成绩 + 健康叙事）
   │   确定性字段代码覆写；键集/学段空值规则/格式/数值范围/红旗信息 硬校验，
   │   失败带错误清单重试（≤3 次）；缺失/矛盾场景由代码落地
   ▼
Stage B  画像理解回答（沿用原 system prompt + 从现有 20 条样本按学段/拦截场景挑 2 条 few-shot）
Stage C  处方回答（同上，拦截案例配「拒绝开方」范例）
   │   启发式校验：单段/无 markdown/长度带/BMI 与五维覆盖/拦截案例必须转介…
   │   失败带反馈重写（≤3 次）
   ▼
Judge    LLM 评审打分（grounding/safety/style 各 1-5，均 ≥4 才通过）
   │   不过线自动重生成一次取较优；仍不过 → meta.needs_review=true 留人工复核
   ▼
output/cases/case_XXX.json（断点续跑：已存在的案例自动跳过）
   ▼
assemble → finetune/generated/profile_sft_generated.json
           finetune/generated/prescription_sft_generated.json
```

## 使用

```bash
cd /Users/apple/workspace/yundongchufang

# 查看案例规格（不调 API）
python3 finetune/datagen/generate.py plan --start 0 --end 100

# 生成第 23~100 号案例（0~22 已生成；中断后重跑同一命令即可续跑）
python3 finetune/datagen/generate.py run --start 23 --end 100 --workers 3

# 汇总到 finetune/generated/（会列出 needs_review 案例清单）
python3 finetune/datagen/generate.py assemble

# 覆盖率与评审分数统计
python3 finetune/datagen/generate.py stats
```

- API key：读环境变量 `GLM_API_KEY`，否则读本目录 `api_key.txt`（已 gitignore）。
- 模型：默认 `glm-5.3`（与方案文档底座一致），`--model` 可换；评审与生成同模型。
- `--no-judge` 跳过 LLM 评审（省一半调用量，不建议）。
- 每案例约 5~7 次 API 调用（档案 1-3 + 回答 2 + 评审 2+），3 并发下约 1.5~3 分钟/案例。
- 案例规格确定性生成：`--start/--end` 切片任意组合跑出的结果一致，重复运行不会产生重复样本。

## 质检结论的使用方式

- 所有样本 `meta.source = "pregenerated(模型名)+待专家修订"`，定位是专家修订前的初稿（数据飞轮）。
- `meta.needs_review = true` 的样本评审未过线，专家应优先复核；`output/cases/*.json` 的
  `qc` 字段保留了评审分数、问题清单与启发式警告，供修订时参考。
- 警告（如"未提及每周天数"）不拦截样本，只记录在案例文件中。
