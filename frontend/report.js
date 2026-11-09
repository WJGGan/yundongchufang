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

createApp({
  data() {
    return {
      rx: clone(EMPTY_RX),
      profile: clone(EMPTY_PROFILE),
      hasData: false,
      students: [],
      selectedId: '',
      generating: false,
      stage: '',
      genError: '',
      emergency: null,
      blocked: null,
      exerciseMap: {},
      zoom: 1,
      fittPrinciple: FITT_PRINCIPLE,
      generalTips: GENERAL_TIPS,
    };
  },

  computed: {
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
        { label: '运动类型', value: f.type.value, detail: f.type.detail },
        { label: '运动强度', value: f.intensity.value, detail: `${hrLine}　${f.intensity.detail || ''}`.trim() },
        { label: '运动时间', value: f.time.value, detail: f.time.detail },
        { label: '运动频率', value: f.frequency.value, detail: f.frequency.detail },
        { label: '周运动总量', value: f.volume.value, detail: f.volume.detail },
        { label: '运动进阶', value: f.progression.value, detail: `${f.progression.detail || ''}${this.rx.cycle.next_review ? '　复评：' + this.rx.cycle.next_review : ''}`.trim() },
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

    // 从工作台带数据跳转过来时直接渲染
    const raw = sessionStorage.getItem('rx_report');
    if (raw) {
      try {
        const data = JSON.parse(raw);
        if (data.rx) this.applyResult(data.rx, data.profile);
      } catch (e) { /* 数据损坏则保持空态 */ }
    }

    window.addEventListener('beforeprint', () => this.fitSheets());
    window.addEventListener('resize', () => this.scheduleFit());
    if (document.fonts && document.fonts.ready) {
      document.fonts.ready.then(() => this.scheduleFit());
    }
    this.scheduleFit();
  },

  methods: {
    /* ---------- 生成流程 ---------- */

    applyResult(rx, profile) {
      this.rx = rx;
      if (profile) this.profile = profile;
      (rx.exercise_details || []).forEach((e) => { this.exerciseMap[e.id] = e; });
      this.hasData = true;
      document.title = `${rx.name || ''}运动处方报告`;
      this.scheduleFit();
      if (document.fonts && document.fonts.ready) {
        document.fonts.ready.then(() => this.scheduleFit());
      }
    },

    resetState() {
      this.rx = clone(EMPTY_RX);
      this.profile = clone(EMPTY_PROFILE);
      this.hasData = false;
      this.genError = '';
      this.emergency = null;
      this.blocked = null;
      document.title = '运动处方报告';
    },

    async generate() {
      if (!this.selectedId || this.generating) return;
      this.resetState();
      this.generating = true;
      this.stage = '正在读取健康档案…';

      try {
        const record = await (await fetch(`/api/v1/students/${this.selectedId}`)).json();
        this.stage = '正在生成体质画像…';

        const res = await fetch('/api/v1/prescription:generate', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ record }),
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
        this.genError = `生成失败：${err}`;
      } finally {
        this.generating = false;
        this.stage = '';
      }
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
          break;
        case 'profile':
          // 画像先到：报告上半部分（基本信息、目标、风险）可以先填上
          this.profile = payload;
          break;
        case 'token':
          this.stage = '模型正在编写处方…';
          break;
        case 'retry':
          this.stage = '输出未通过校验，正在重新生成…';
          break;
        case 'result':
          this.applyResult(payload, this.profile);
          break;
        case 'emergency':
          this.emergency = payload;
          break;
        case 'blocked':
          this.blocked = payload;
          break;
        case 'error':
          this.genError = payload.message;
          break;
      }
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

    zoomIn() { this.zoom = Math.min(1.6, +(this.zoom + 0.1).toFixed(2)); },
    zoomOut() { this.zoom = Math.max(0.5, +(this.zoom - 0.1).toFixed(2)); },
    print() { window.print(); },

    /* ------------------------------------------------------------------
       自适应排版：模型输出长度不固定，这里把每页内容等比缩放到正好一张 A4。
       做法是先把内容层按 1/s 加宽，再整体 scale(s) 还原到纸张宽度，
       等价于「缩小字号 + 同步放宽行宽」，版式比例不变。
       ------------------------------------------------------------------ */
    fitSheets() {
      document.querySelectorAll('.sheet').forEach((sheet) => {
        const inner = sheet.querySelector('.sheet-inner');
        if (!inner) return;

        const cs = getComputedStyle(sheet);
        const padX = parseFloat(cs.paddingLeft) + parseFloat(cs.paddingRight);
        const padY = parseFloat(cs.paddingTop) + parseFloat(cs.paddingBottom);
        const availW = sheet.clientWidth - padX;
        const availH = sheet.clientHeight - padY;
        if (availW <= 0 || availH <= 0) return;

        const apply = (s) => {
          inner.style.width = `${availW / s}px`;
          inner.style.minHeight = `${availH / s}px`;
          inner.style.transform = s === 1 ? 'none' : `scale(${s})`;
        };

        let s = 1;
        apply(1);
        // 迭代逼近：加宽后高度会变化，两三轮即可收敛
        for (let i = 0; i < 4; i++) {
          const h = inner.scrollHeight;
          const next = Math.min(1, availH / h);
          if (Math.abs(next - s) < 0.005) { s = next; break; }
          s = next;
          apply(s);
        }
        // 兜底：仍溢出就继续收一点，避免打印被裁切
        let guard = 0;
        while (inner.scrollHeight * s > availH + 1 && guard < 12) {
          s *= 0.97;
          apply(s);
          guard += 1;
        }
        inner.dataset.fit = s.toFixed(3);
      });
    },

    scheduleFit() {
      this.$nextTick(() => {
        // 等字体与异步回填的动作库数据就绪后再测量
        requestAnimationFrame(() => this.fitSheets());
      });
    },
  },
}).mount('#report');
