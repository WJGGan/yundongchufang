const { createApp } = Vue;

/* 运动目的候选项：模型 goals 命中则勾选，未命中的 goals 作为「其他目标」展示 */
const GOAL_OPTIONS = [
  { text: '提高心肺耐力', kw: ['心肺', '耐力', '有氧'] },
  { text: '增加肌肉力量', kw: ['肌肉', '力量', '抗阻'] },
  { text: '提高柔韧性', kw: ['柔韧', '拉伸', '体前屈'] },
  { text: '减少脂肪', kw: ['减脂', '脂肪', '体重', '减重', 'BMI', '肥胖'] },
  { text: '改善平衡与协调', kw: ['平衡', '协调', '稳定'] },
  { text: '提升速度灵敏', kw: ['速度', '灵敏', '敏捷'] },
  { text: '改善体态姿势', kw: ['体态', '姿势', '脊柱', '含胸'] },
  { text: '养成运动习惯', kw: ['习惯', '依从', '坚持', '兴趣'] },
];

const FITT_PRINCIPLE = [
  { k: 'F', cls: 'f', title: '频率 (Frequency)', desc: '每周运动次数' },
  { k: 'I', cls: 'i', title: '强度 (Intensity)', desc: '运动强度 / 靶心率 / RPE' },
  { k: 'T', cls: 't', title: '时间 (Time)', desc: '每次运动持续时间' },
  { k: 'T', cls: 't2', title: '类型 (Type)', desc: '有氧 / 抗阻 / 柔韧 / 平衡等' },
  { k: 'V', cls: 'v', title: '进阶量 (Volume)', desc: '运动总量 / 时长 / 组数' },
  { k: 'P', cls: 'p', title: '个体化 (Personalization)', desc: '结合个人健康状况与目标' },
];

/* 体质测试项目：key 对应档案 fitness_test 字段，kw 用于在画像 fitness_dimensions 里匹配等级 */
const FITNESS_ITEMS = [
  { key: 'FHLCJ', label: '肺活量', unit: 'ml', kw: ['肺活量'] },
  { key: 'WSMCJ', label: '50米跑', unit: '秒', kw: ['50米'], exclude: ['往返', '×8', 'x8'] },
  { key: 'LDTYCJ', label: '立定跳远', unit: 'cm', kw: ['立定跳远'] },
  { key: 'ZWTQQCJ', label: '坐位体前屈', unit: 'cm', kw: ['体前屈'] },
  { key: 'WSMWFPCJ', label: '50米×8往返跑', unit: '秒', kw: ['往返'] },
  { key: 'YFZTSCJ', label: '一分钟跳绳', unit: '个', kw: ['跳绳'] },
  { key: 'BBMCJ', label: '800米跑', unit: '', kw: ['800'] },
  { key: 'YQMCJ', label: '1000米跑', unit: '', kw: ['1000'] },
  { key: 'YWQZCJ', label: '一分钟仰卧起坐', unit: '个', kw: ['仰卧起坐'] },
  { key: 'YTXSCJ', label: '引体向上', unit: '个', kw: ['引体'] },
];

const GENERAL_TIPS = [
  '运动前充分热身，运动后做好拉伸。',
  '抗阻训练时避免憋气，保持均匀呼吸。',
  '关注主观感受（RPE），中等强度应微微出汗、能说话但不能唱歌。',
  '出现不适立即停止运动并告知家长或教师。',
];

/* 动作类别归属：按动作库 category / 编号前缀判断 */
const PREFIX_CATEGORY = {
  WUP: '热身', AER: '有氧', RES: '抗阻', COR: '核心',
  FLX: '柔韧', SPD: '速度灵敏', CLD: '放松',
};

/* 空骨架：没有数据时报告版式照常渲染，字段留白而非整页隐藏 */
const EMPTY_FITT_ITEM = { value: '', detail: '' };
const EMPTY_RX = {
  prescription_id: '',
  student_id: '',
  name: '',
  generated_at: '',
  versions: {},
  goals: [],
  cycle: { total_weeks: null, current_phase: '', next_review: '' },
  fitt_vp: {
    frequency: { ...EMPTY_FITT_ITEM }, intensity: { ...EMPTY_FITT_ITEM },
    time: { ...EMPTY_FITT_ITEM }, type: { ...EMPTY_FITT_ITEM },
    volume: { ...EMPTY_FITT_ITEM }, progression: { ...EMPTY_FITT_ITEM },
  },
  weekly_plan: [],
  exercise_details: [],
  intensity_control: {
    target_hr_zone: { lower: null, upper: null, formula_note: '' },
    rpe_range: '', talk_test: '', stop_signals: [],
  },
  nutrition: {
    principles: [], macro_guidance: { carbohydrate: '', protein: '', fat: '' },
    around_training: { pre: '', post: '' }, hydration: '', cautions: [],
  },
  risk_notes: [],
  forbidden_or_limited: [],
  explanations: [],
  homework: { title: '', tasks: [], completion_standard: '', self_report: '' },
  disclaimer: '',
};
const EMPTY_PROFILE = {
  basic: {}, fitness_dimensions: [], overall: { strengths: [], weaknesses: [] },
  health_focus: [],
  data_quality: { missing_fields: [], conflicts: [], clarification_questions: [] },
  safety: {
    risk_level: '', can_generate_prescription: true, blocked_exercise_tags: [],
    intensity_ceiling: {}, referral_advice: [], notes: [],
  },
};

const clone = (o) => JSON.parse(JSON.stringify(o));

/* 自行录入表单的默认值：预填李沐阳（BJ2025090314）的完整档案，
   不改任何字段直接提交也能走通保存与生成流程 */
const DEFAULT_FORM = {
  name: '李沐阳', gender: '男', age: '14', grade: '初二',
  height: '168.5', weight: '72.3', fhl: '2680',
  resting_hr: '', blood_pressure: '',
  wsm: '8.9', ldty: '185', zwtqq: '4.2', yfzts: '',
  yqm: '4分32秒', bbm: '', ytxs: '3', ywqz: '',
  chronic: '哮喘（轻度间歇性，近一年未急性发作）',
  medications: '沙丁胺醇气雾剂（按需使用）',
  injuries: '右踝韧带扭伤（2025-04，已恢复，剧烈变向时偶有酸胀）',
  symptoms: '', family: '父亲高血压',
  sleep: '7',
  weekly_frequency: '2', main_activities: '校内体育课、周末骑行', sedentary: '9',
  goals: '健康体重管理、心肺耐力提升、体测专项提升:1000米',
  days_per_week: '4', minutes_per_session: '45', preferred_slot: '放学后',
  venue: '家庭、小区空地、学校操场',
  equipment: '跳绳、弹力带、瑜伽垫、自行车、篮球',
  liked: '骑行、篮球', disliked: '长距离慢跑',
};

createApp({
  data() {
    return {
      rx: clone(EMPTY_RX),
      profile: clone(EMPTY_PROFILE),
      record: null,
      hasData: false,
      students: [],
      cached: {},
      source: '',
      selectedId: '',
      generating: false,
      stage: '',
      genError: '',
      emergency: null,
      blocked: null,
      exerciseMap: {},
      showForm: false,
      form: clone(DEFAULT_FORM),
      formSaving: false,
      formError: '',
      aiOpen: false,
      aiMessages: [],
      abortCtrl: null,
      fittPrinciple: FITT_PRINCIPLE,
      generalTips: GENERAL_TIPS,
    };
  },

  computed: {
    isCached() {
      return !!this.cached[this.selectedId];
    },
    basic() {
      return (this.profile && this.profile.basic) || {};
    },
    riskLevel() {
      return (this.profile && this.profile.safety && this.profile.safety.risk_level) || '中';
    },
    blockedTags() {
      return (this.profile && this.profile.safety && this.profile.safety.blocked_exercise_tags) || [];
    },
    healthFocus() {
      return (this.profile && this.profile.health_focus) || [];
    },
    weaknesses() {
      return (this.profile && this.profile.overall && this.profile.overall.weaknesses) || [];
    },

    /* ---------- 1 基本信息：原始档案（体检 / 体测 / 运动史 / 伤病史） ---------- */

    rawExam() {
      return (this.record && this.record.physical_exam) || {};
    },
    rawFitness() {
      return (this.record && this.record.fitness_test) || {};
    },
    rawHealth() {
      return (this.record && this.record.health_profile) || {};
    },

    /* 体检数据：血压、心率、肺活量、视力、脊柱筛查 */
    examRows() {
      const e = this.rawExam;
      const v = this.rawHealth.vitals || {};
      const pair = (l, r) => (l || r ? `左 ${l || '—'} / 右 ${r || '—'}` : '');
      const jz = (e.JZ || '').trim();
      return [
        { label: '血压', value: v.blood_pressure, unit: 'mmHg' },
        { label: '安静心率', value: v.resting_heart_rate, unit: '次/分' },
        { label: '肺活量', value: e.FHL, unit: 'ml' },
        { label: '远视力', value: pair(e.ZYSL, e.YYSL) },
        { label: '近视力', value: pair(e.ZYJSL, e.YYJSL) },
        { label: '视力评价', value: e.JSLPJ },
        { label: '脊柱筛查', value: jz, wide: true, warn: !!jz && !jz.includes('未见异常') },
      ];
    },

    /* 体测成绩：成绩取自档案 fitness_test，等级取自画像 fitness_dimensions */
    fitnessRows() {
      const ft = this.rawFitness;
      const rows = [];
      FITNESS_ITEMS.forEach((it) => {
        const raw = String(ft[it.key] ?? '').trim();
        if (!raw) return;
        rows.push({
          name: it.label,
          value: it.unit && /^[\d.]+$/.test(raw) ? `${raw} ${it.unit}` : raw,
          level: this.levelOf(it),
        });
      });
      return rows;
    },

    /* 运动史 */
    exerciseRows() {
      const h = this.rawHealth.exercise_history || {};
      const num = (n, suffix) => (n !== '' && n != null ? `${n} ${suffix}` : '');
      return [
        { label: '每周运动', value: num(h.weekly_frequency, '次') },
        { label: '每次时长', value: num(h.typical_duration_min, '分钟') },
        { label: '每日久坐', value: num(h.sedentary_hours_per_day, '小时') },
        { label: '训练经历', value: h.training_experience || '' },
        { label: '常做运动', value: (h.main_activities || []).join('、'), wide: true },
      ];
    },

    /* 伤病史：兼容结构化条目与纯文本录入 */
    injuryRows() {
      return (this.rawHealth.injury_history || [])
        .map((it) => {
          if (typeof it === 'string') return it;
          const head = `${it.site || ''}${it.type || ''}`;
          const meta = [it.date, it.status].filter(Boolean).join('，');
          return [head || it.note || '', meta && `（${meta}）`, head && it.note ? ` ${it.note}` : '']
            .filter(Boolean).join('').trim();
        })
        .filter(Boolean);
    },

    validFrom() {
      return this.dateOnly(this.rx.generated_at) || '—';
    },
    validTo() {
      const start = this.parseDate(this.rx.generated_at);
      const weeks = this.rx.cycle.total_weeks;
      if (!start || !weeks) return '—';
      const end = new Date(start.getTime() + weeks * 7 * 86400000);
      return this.fmtDate(end);
    },

    goalOptions() {
      const goals = this.rx.goals || [];
      return GOAL_OPTIONS.map((o) => ({
        text: o.text,
        on: goals.some((g) => o.kw.some((k) => g.includes(k))),
      }));
    },
    extraGoals() {
      const goals = this.rx.goals || [];
      return goals.filter((g) => !GOAL_OPTIONS.some((o) => o.kw.some((k) => g.includes(k))));
    },

    hrText() {
      const z = this.rx.intensity_control.target_hr_zone || {};
      if (z.lower && z.upper) return `${z.lower}–${z.upper} 次/分`;
      return this.rx.fitt_vp.intensity.value || '—';
    },
    stopSignals() {
      const s = this.rx.intensity_control.stop_signals || [];
      return s.length ? s.join('、') : '胸闷、胸痛、头晕、呼吸困难、关节锐痛';
    },

    /* 3 运动方案一览表 */
    planRows() {
      const f = this.rx.fitt_vp;
      const z = this.rx.intensity_control.target_hr_zone || {};
      const hrLine = z.lower && z.upper
        ? `靶心率 ${z.lower}–${z.upper} 次/分　RPE ${this.rx.intensity_control.rpe_range || '—'}`
        : `RPE ${this.rx.intensity_control.rpe_range || '—'}`;
      return [
        { label: '运动类型', k: 'T', cls: 't2', value: f.type.value, detail: f.type.detail },
        { label: '运动强度', k: 'I', cls: 'i', value: f.intensity.value, detail: `${hrLine}　${f.intensity.detail || ''}`.trim() },
        { label: '运动时间', k: 'T', cls: 't', value: f.time.value, detail: f.time.detail },
        { label: '运动频率', k: 'F', cls: 'f', value: f.frequency.value, detail: f.frequency.detail },
        { label: '周运动总量', k: 'V', cls: 'v', value: f.volume.value, detail: f.volume.detail },
        { label: '运动进阶', k: 'P', cls: 'p', value: f.progression.value, detail: `${f.progression.detail || ''}${this.rx.cycle.next_review ? '　复评：' + this.rx.cycle.next_review : ''}`.trim() },
      ];
    },

    /* 4.1 周计划表 */
    weekRows() {
      const z = this.rx.intensity_control.target_hr_zone || {};
      const hr = z.lower && z.upper ? `${z.lower}–${z.upper}` : (this.rx.intensity_control.rpe_range ? 'RPE ' + this.rx.intensity_control.rpe_range : '—');
      return (this.rx.weekly_plan || []).map((d) => {
        const items = [];
        const notes = [];
        (d.blocks || []).forEach((b) => {
          (b.items || []).forEach((it) => {
            items.push(it.name);
            if (it.notes) notes.push(it.notes);
          });
        });
        return {
          day: d.day,
          rest: !d.is_training_day,
          items: items.length ? items.join(' / ') : (d.theme || '休息'),
          hr: d.is_training_day ? hr : '—',
          minutes: d.total_minutes ? `${d.total_minutes}′` : '—',
          note: notes.length ? notes.join('；') : (d.theme || ''),
        };
      });
    },

    /* 所有动作条目扁平化（带类别） */
    allItems() {
      const out = [];
      (this.rx.weekly_plan || []).forEach((d) => {
        (d.blocks || []).forEach((b) => {
          (b.items || []).forEach((it) => {
            out.push({ ...it, day: d.day, phase: b.phase });
          });
        });
      });
      return out;
    },

    resistanceMoves() {
      return this.pickMoves(['抗阻'], 5);
    },
    flexMoves() {
      return this.pickMoves(['柔韧', '核心', '放松', '热身'], 5);
    },
    resistanceFreq() {
      const days = new Set(this.resistanceMoves.flatMap((m) => m.days));
      return days.size ? `每周 ${days.size} 次` : '';
    },
    muscleGroups() {
      const set = new Set();
      this.resistanceMoves.forEach((m) => {
        (this.detailOf(m.id).muscle_groups || []).forEach((g) => set.add(g));
      });
      return [...set].slice(0, 8);
    },

    /* 4.4 运动流程 */
    flowRows() {
      const agg = {};
      (this.rx.weekly_plan || []).forEach((d) => {
        if (!d.is_training_day) return;
        (d.blocks || []).forEach((b) => {
          if (!b.phase) return;
          if (!agg[b.phase]) agg[b.phase] = { total: 0, n: 0, names: new Set() };
          agg[b.phase].total += b.minutes || 0;
          agg[b.phase].n += 1;
          (b.items || []).forEach((it) => agg[b.phase].names.add(it.name));
        });
      });
      const order = ['热身', '主体', '柔韧', '放松', '整理'];
      const clsOf = (p) => (p.includes('热身') ? 'warm' : p.includes('放松') || p.includes('整理') || p.includes('柔韧') ? 'cool' : 'main');
      return Object.keys(agg)
        .sort((a, b) => {
          const ia = order.findIndex((o) => a.includes(o));
          const ib = order.findIndex((o) => b.includes(o));
          return (ia < 0 ? 99 : ia) - (ib < 0 ? 99 : ib);
        })
        .map((p) => ({
          name: p,
          cls: clsOf(p),
          minutes: agg[p].n ? Math.round(agg[p].total / agg[p].n) : 0,
          desc: [...agg[p].names].slice(0, 4).join(' / ') || '—',
        }));
    },

    /* 6 执行与随访 */
    followCards() {
      const venues = new Set();
      this.allItems.forEach((it) => {
        (this.detailOf(it.exercise_id).venue || []).forEach((v) => venues.add(v));
      });
      const adjust = (this.profile && this.profile.safety && this.profile.safety.notes) || [];
      return [
        {
          title: '健身场所', cls: 'home',
          lines: venues.size ? [...venues].slice(0, 4) : ['居家 / 校园 / 户外'],
        },
        {
          title: '复评周期', cls: 'cal',
          lines: [
            this.rx.cycle.total_weeks ? `处方周期 ${this.rx.cycle.total_weeks} 周` : '周期待定',
            this.rx.cycle.next_review ? `下次复评：${this.rx.cycle.next_review}` : '建议 4–8 周后复评',
          ],
        },
        {
          title: '复评指标', cls: 'chart',
          lines: this.weaknesses.length
            ? this.weaknesses.slice(0, 3).map((w) => w.dimension)
            : ['体重 / 体脂率', '心肺耐力', '柔韧与力量'],
        },
        {
          title: '处方调整建议', cls: 'loop',
          lines: adjust.length ? adjust.slice(0, 3) : ['根据复评结果、依从性与个人目标动态调整'],
        },
        {
          title: '依从性记录', cls: 'phone',
          lines: ['逐次填写下方运动记录表', '可通过 APP / 穿戴设备同步'],
        },
      ];
    },

    topExplanations() {
      return (this.rx.explanations || []).slice(0, 6);
    },
  },

  mounted() {
    // 动作库始终加载：生成前用于空态，生成后用于回填动作要点
    fetch('/api/v1/exercises')
      .then((r) => r.json())
      .then((d) => {
        (d.exercises || []).forEach((e) => {
          if (!this.exerciseMap[e.id]) this.exerciseMap[e.id] = e;
        });
      })
      .catch(() => {});

    fetch('/api/v1/students')
      .then((r) => r.json())
      .then((list) => {
        this.students = list;
        if (!this.selectedId && list.length) this.selectedId = list[0].student_id;
      })
      .catch(() => {});

    this.refreshCached();

    // 从工作台带数据跳转过来时直接渲染
    const raw = sessionStorage.getItem('rx_report');
    if (raw) {
      try {
        const data = JSON.parse(raw);
        if (data.record) this.record = data.record;
        if (data.rx) this.applyResult(data.rx, data.profile);
        if (!data.record && data.rx && data.rx.student_id) this.fetchRecord(data.rx.student_id);
      } catch (e) { /* 数据损坏则保持空态 */ }
    }
  },

  methods: {
    /* ---------- 预生成结果 ---------- */

    refreshCached() {
      return fetch('/api/v1/pregenerated')
        .then((r) => r.json())
        .then((d) => {
          const map = {};
          (d.items || []).forEach((it) => { map[it.student_id] = it; });
          this.cached = map;
        })
        .catch(() => {});
    },

    async loadCached() {
      if (!this.isCached || this.generating) return;
      this.resetState();
      // 原始档案单独拉取：报告头部的体检 / 体测 / 运动史 / 伤病史直接展示档案原文
      this.fetchRecord(this.selectedId);
      try {
        const res = await fetch(`/api/v1/pregenerated/${this.selectedId}`);
        if (!res.ok) {
          this.genError = `载入失败：${(await res.json()).detail || res.status}`;
          return;
        }
        const data = await res.json();

        if (data.emergency) { this.emergency = data.emergency; }
        if (data.blocked) { this.blocked = data.blocked; }
        if (data.profile) { this.profile = data.profile; }

        if (data.prescription) {
          this.applyResult(data.prescription, data.profile);
          const when = (data.generated_at || '').slice(0, 16).replace('T', ' ');
          this.source = `已有结果 · ${data.model || ''} · ${when}`;
        } else if (!data.emergency && !data.blocked) {
          this.genError = '该学生的预生成结果不含处方内容';
        }
      } catch (err) {
        this.genError = `载入失败：${err}`;
      }
    },

    /* ---------- 实时生成 ---------- */

    fetchRecord(studentId) {
      if (!studentId) return;
      fetch(`/api/v1/students/${studentId}`)
        .then((r) => (r.ok ? r.json() : null))
        .then((rec) => { if (rec) this.record = rec; })
        .catch(() => {});
    },

    applyResult(rx, profile) {
      this.rx = rx;
      if (profile) this.profile = profile;
      (rx.exercise_details || []).forEach((e) => { this.exerciseMap[e.id] = e; });
      this.hasData = true;
      document.title = `${rx.name || ''}运动处方报告`;
    },

    resetState() {
      this.rx = clone(EMPTY_RX);
      this.profile = clone(EMPTY_PROFILE);
      this.record = null;
      this.hasData = false;
      this.genError = '';
      this.emergency = null;
      this.blocked = null;
      this.source = '';
      this.aiMessages = [];
      document.title = '运动处方报告';
    },

    async generate() {
      if (!this.selectedId || this.generating) return;
      this.resetState();
      this.generating = true;
      this.stage = '正在读取健康档案…';
      try {
        const record = await (await fetch(`/api/v1/students/${this.selectedId}`)).json();
        this.record = record;
        await this.streamGenerate(record);
      } catch (err) {
        this.genError = `生成失败：${err}`;
        this.generating = false;
        this.stage = '';
      }
    },

    /* 把一份完整档案送入画像 + 处方生成流程（SSE） */
    async streamGenerate(record) {
      this.generating = true;
      this.aiOpen = true;
      this.stage = '正在生成体质画像…';
      this.abortCtrl = new AbortController();
      try {
        const res = await fetch('/api/v1/prescription:generate', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ record }),
          signal: this.abortCtrl.signal,
        });
        const reader = res.body.getReader();
        const decoder = new TextDecoder();
        let buffer = '';
        while (true) {
          const { value, done } = await reader.read();
          if (done) break;
          buffer += decoder.decode(value, { stream: true });
          const frames = buffer.split('\n\n');
          buffer = frames.pop();
          frames.forEach((f) => this.handleFrame(f));
        }
      } catch (err) {
        if (err && err.name === 'AbortError') {
          this.pushAiNote('已手动停止生成。');
        } else {
          this.genError = `生成失败：${err}`;
        }
      } finally {
        this.generating = false;
        this.stage = '';
        this.abortCtrl = null;
      }
    },

    stopGenerate() {
      if (this.abortCtrl) this.abortCtrl.abort();
    },

    /* ---------- 自行录入 ---------- */

    splitList(text) {
      return (text || '').split(/[,，、;；\n]/).map((s) => s.trim()).filter(Boolean);
    },

    toNum(text) {
      if (text === '' || text == null) return null;
      const n = Number(text);
      return Number.isFinite(n) ? n : null;
    },

    buildRecord() {
      const f = this.form;
      if (!f.name || !f.age || !f.height || !f.weight) {
        this.formError = '请至少填写姓名、年龄、身高、体重';
        return null;
      }
      if (!this.splitList(f.goals).length) {
        this.formError = '请至少填写一个运动目标';
        return null;
      }
      this.formError = '';
      const today = new Date().toISOString().slice(0, 10);
      return {
        student_id: '',
        name: f.name,
        school: '',
        physical_exam: {
          XB: f.gender, NL: f.age, SG: f.height, TZ: f.weight,
          FHL: f.fhl, SCHOOL_GRADE: f.grade, UP_TIME: today,
        },
        fitness_test: {
          NJ: f.grade, XB: f.gender, SGCJ: f.height, TZCJ: f.weight, FHLCJ: f.fhl,
          WSMCJ: f.wsm, LDTYCJ: f.ldty, ZWTQQCJ: f.zwtqq, YFZTSCJ: f.yfzts,
          YQMCJ: f.yqm, BBMCJ: f.bbm, YTXSCJ: f.ytxs, YWQZCJ: f.ywqz,
        },
        health_profile: {
          chronic_conditions: this.splitList(f.chronic),
          medications: this.splitList(f.medications),
          injury_history: this.splitList(f.injuries).map((t) => ({ note: t })),
          recent_symptoms: this.splitList(f.symptoms),
          family_history: this.splitList(f.family),
          vitals: { resting_heart_rate: f.resting_hr, blood_pressure: f.blood_pressure },
          exercise_history: {
            weekly_frequency: this.toNum(f.weekly_frequency),
            main_activities: this.splitList(f.main_activities),
            sedentary_hours_per_day: this.toNum(f.sedentary),
          },
          lifestyle: { sleep_hours: this.toNum(f.sleep) },
        },
        prescription_request: {
          goals: this.splitList(f.goals),
          available_time: {
            days_per_week: this.toNum(f.days_per_week),
            minutes_per_session: this.toNum(f.minutes_per_session),
            preferred_slot: f.preferred_slot,
          },
          venue: this.splitList(f.venue),
          equipment: this.splitList(f.equipment),
          preferences: { liked: this.splitList(f.liked), disliked: this.splitList(f.disliked) },
          guardian_consent: true,
        },
      };
    },

    async submitCustom() {
      if (this.formSaving || this.generating) return;
      const record = this.buildRecord();
      if (!record) return;

      this.formSaving = true;
      let saved;
      try {
        const res = await fetch('/api/v1/students', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify(record),
        });
        if (!res.ok) {
          let detail = `HTTP ${res.status}`;
          try { detail = (await res.json()).detail || detail; } catch (e) { /* 原样提示 */ }
          this.formError = `保存失败：${detail}`;
          return;
        }
        saved = await res.json();
      } catch (err) {
        this.formError = `保存失败：${err}`;
        return;
      } finally {
        this.formSaving = false;
      }

      // 新档案已落盘：刷新下拉列表并选中，再直接走生成流程
      fetch('/api/v1/students')
        .then((r) => r.json())
        .then((list) => { this.students = list; })
        .catch(() => {});
      this.selectedId = saved.student_id;
      this.showForm = false;
      this.resetState();
      this.record = saved;
      await this.streamGenerate(saved);
    },

    handleFrame(frame) {
      let event = 'message';
      let data = '';
      frame.split('\n').forEach((line) => {
        if (line.startsWith('event: ')) event = line.slice(7).trim();
        else if (line.startsWith('data: ')) data += line.slice(6);
      });
      if (!data) return;
      let payload;
      try { payload = JSON.parse(data); } catch { return; }

      switch (event) {
        case 'status':
          this.stage = payload.message + '…';
          this.pushAiNote(payload.message + '…');
          break;
        case 'profile':
          // 画像先到：报告上半部分（基本信息、目标、风险）可以先填上
          this.profile = payload;
          break;
        case 'thinking':
          this.stage = (payload.phase === 'profile')
            ? '模型正在分析体质画像…'
            : '模型正在设计运动处方…';
          this.appendThink(payload.phase || 'prescription', payload.text);
          break;
        case 'token':
          this.stage = (payload.phase === 'profile')
            ? '模型正在输出画像数据…'
            : '模型正在输出处方数据…';
          this.bumpProgress(payload.phase || 'prescription', payload.text.length);
          break;
        case 'retry':
          this.stage = '输出未通过校验，正在重新生成…';
          this.pushAiNote('输出未通过校验，正在重新生成…');
          break;
        case 'result':
          this.applyResult(payload, this.profile);
          this.pushAiNote('运动处方生成完成。');
          break;
        case 'emergency':
          this.emergency = payload;
          this.pushAiNote('命中急症关键词，已熔断，不再调用模型。');
          break;
        case 'blocked':
          this.blocked = payload;
          this.pushAiNote('安全评估判定当前不宜生成可执行处方。');
          break;
        case 'error':
          this.genError = payload.message;
          this.pushAiNote('生成失败：' + payload.message);
          break;
      }
    },

    /* ---------- 右侧 AI 输出抽屉 ---------- */

    aiTitle(phase) {
      return phase === 'profile' ? '体质画像 · 模型分析' : '运动处方 · 模型分析';
    },

    /* 把模型输出渲染成 Markdown；先转义尖括号，防止模型输出原始 HTML */
    md(text) {
      const safe = (text || '').replace(/</g, '&lt;');
      try { return marked.parse(safe); } catch (e) { return safe; }
    },

    pushAiNote(text) {
      this.aiMessages.push({ kind: 'note', text });
      this.scrollAi();
    },

    /* 思考过程：自然语言，按 Markdown 渲染 */
    appendThink(phase, text) {
      const last = this.aiMessages[this.aiMessages.length - 1];
      if (last && last.kind === 'think' && last.phase === phase) {
        last.text += text;
      } else {
        this.aiMessages.push({ kind: 'think', phase, title: this.aiTitle(phase), text });
      }
      this.scrollAi();
    },

    /* 结构化 JSON 不直接展示，只显示写入进度 */
    bumpProgress(phase, chars) {
      const last = this.aiMessages[this.aiMessages.length - 1];
      if (last && last.kind === 'progress' && last.phase === phase) {
        last.chars += chars;
      } else {
        this.aiMessages.push({ kind: 'progress', phase, chars });
      }
      this.scrollAi();
    },

    progressText(m) {
      const what = m.phase === 'profile' ? '画像' : '处方';
      return `正在写入结构化${what}数据… 已接收 ${m.chars} 字符`;
    },

    scrollAi() {
      this.$nextTick(() => {
        const box = this.$refs.aiBody;
        if (box) box.scrollTop = box.scrollHeight;
      });
    },

    /* ---------- 渲染辅助 ---------- */

    detailOf(id) { return this.exerciseMap[id] || {}; },

    categoryOf(it) {
      const d = this.detailOf(it.exercise_id);
      if (d.category) return d.category;
      const prefix = (it.exercise_id || '').split('-')[0];
      return PREFIX_CATEGORY[prefix] || '';
    },

    pickMoves(categories, limit = 6) {
      const byId = new Map();
      this.allItems.forEach((it) => {
        if (!categories.includes(this.categoryOf(it))) return;
        const key = it.exercise_id || it.name;
        if (byId.has(key)) { byId.get(key).days.push(it.day); return; }
        const d = this.detailOf(it.exercise_id);
        byId.set(key, {
          key,
          id: it.exercise_id,
          name: it.name,
          dosage: it.dosage || d.dosage_hint || '',
          point: (d.key_points || [])[0] || it.notes || '',
          error: (d.common_errors || [])[0] || '',
          days: [it.day],
        });
      });
      return [...byId.values()].slice(0, limit);
    },

    riskCls(level) { return { 高: 'high', 中: 'mid', 低: 'low' }[level] || 'mid'; },

    /* 在画像 fitness_dimensions 的指标里找某个体测项目的等级 */
    levelOf(item) {
      const dims = (this.profile && this.profile.fitness_dimensions) || [];
      for (const d of dims) {
        for (const ind of d.indicators || []) {
          const name = ind.name || '';
          if (item.kw.some((k) => name.includes(k))
              && !(item.exclude || []).some((k) => name.includes(k))) {
            return ind.level || '';
          }
        }
      }
      return '';
    },

    levelCls(level) {
      if (!level) return '';
      if (level.includes('优')) return 'lv-exc';
      if (level.includes('良')) return 'lv-good';
      if (level.includes('不及格')) return 'lv-fail';
      return 'lv-pass';
    },


    parseDate(s) {
      if (!s) return null;
      const d = new Date(s);
      return isNaN(d.getTime()) ? null : d;
    },
    fmtDate(d) {
      const p = (n) => String(n).padStart(2, '0');
      return `${d.getFullYear()}-${p(d.getMonth() + 1)}-${p(d.getDate())}`;
    },
    dateOnly(s) {
      const d = this.parseDate(s);
      return d ? this.fmtDate(d) : (s || '');
    },
  },
}).mount('#report');
