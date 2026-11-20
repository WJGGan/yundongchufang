const { createApp } = Vue;

const AI_TITLE = '运动处方 · 模型分析';

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

/* 体质测试项目：key 对应档案 fitness_test 字段 */
const FITNESS_ITEMS = [
  { key: 'FHLCJ', label: '肺活量', unit: 'ml' },
  { key: 'WSMCJ', label: '50米跑', unit: '秒' },
  { key: 'LDTYCJ', label: '立定跳远', unit: 'cm' },
  { key: 'ZWTQQCJ', label: '坐位体前屈', unit: 'cm' },
  { key: 'WSMWFPCJ', label: '50米×8往返跑', unit: '秒' },
  { key: 'YFZTSCJ', label: '一分钟跳绳', unit: '个' },
  { key: 'BBMCJ', label: '800米跑', unit: '' },
  { key: 'YQMCJ', label: '1000米跑', unit: '' },
  { key: 'YWQZCJ', label: '一分钟仰卧起坐', unit: '个' },
  { key: 'YTXSCJ', label: '引体向上', unit: '个' },
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
  student_id: '',
  name: '',
  generated_at: '',
  versions: {},
  goals: [],
  cycle: { current_phase: '', next_review: '' },
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
  risk_notes: [],
  forbidden_or_limited: [],
  disclaimer: '',
};
const clone = (o) => JSON.parse(JSON.stringify(o));

/* 自行录入表单的默认值：预填李沐阳（BJ2025090314）的完整档案，
   不改任何字段直接提交也能走通保存与生成流程 */
const DEFAULT_FORM = {
  name: '李沐阳', gender: '男', age: '14', grade: '初二',
  height: '168.5', weight: '72.3', fhl: '2680',
  resting_hr: '', blood_pressure: '',
  wsm: '8.9', ldty: '185', zwtqq: '4.2', yfzts: '', wsmwfp: '',
  yqm: '4分32秒', bbm: '', ytxs: '3', ywqz: '',
  chronic: '哮喘（轻度间歇性，近一年未急性发作）',
  medications: '沙丁胺醇气雾剂（按需使用）',
  injuries: '右踝韧带扭伤（2025-04，已恢复，剧烈变向时偶有酸胀）',
  symptoms: '',
};

createApp({
  mixins: [AiPanelMixin],

  data() {
    return {
      rx: clone(EMPTY_RX),
      record: null,
      hasData: false,
      students: [],
      cached: {},
      selectedId: '',
      generating: false,
      stage: '',
      genError: '',
      emergency: null,
      exerciseMap: {},
      weekLayout: 'horizontal',
      activeAction: null,
      activeActionKey: '',
      actionPopoverStyle: {},
      exportOpen: false,
      exportFormat: 'pdf',
      exportDetails: false,
      exportName: false,
      showForm: false,
      form: clone(DEFAULT_FORM),
      formSaving: false,
      formError: '',
      generalTips: GENERAL_TIPS,
    };
  },

  computed: {
    isCached() {
      return !!this.cached[this.selectedId];
    },
    /* ---------- 1 基本信息：原始档案（体检 / 体测 / 伤病史） ---------- */

    /* 基本信息直接取原始档案的体检字段 */
    basic() {
      const e = this.rawExam;
      return { gender: e.XB, age: e.NL, grade: e.SCHOOL_GRADE, height: e.SG, weight: e.TZ };
    },
    /* BMI 由档案身高体重现算，保留 1 位小数 */
    bmi() {
      const h = Number(this.rawExam.SG);
      const w = Number(this.rawExam.TZ);
      if (!h || !w) return '';
      return (w / ((h / 100) ** 2)).toFixed(1);
    },

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

    /* 体测成绩：取自档案 fitness_test，只展示成绩不评等级 */
    fitnessRows() {
      const ft = this.rawFitness;
      const rows = [];
      FITNESS_ITEMS.forEach((it) => {
        const raw = String(ft[it.key] ?? '').trim();
        if (!raw) return;
        rows.push({
          name: it.label,
          value: it.unit && /^[\d.]+$/.test(raw) ? `${raw} ${it.unit}` : raw,
        });
      });
      return rows;
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

    /* 慢性病：档案 chronic_conditions 字符串列表 */
    chronicRows() {
      return (this.rawHealth.chronic_conditions || [])
        .map((t) => String(t).trim())
        .filter(Boolean);
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
        { label: '(Type) 运动类型', k: 'T', cls: 't2', value: f.type.value, detail: f.type.detail },
        { label: '(Intensity) 运动强度', k: 'I', cls: 'i', value: f.intensity.value, detail: `${hrLine}　${f.intensity.detail || ''}`.trim() },
        { label: '(Time) 运动时间', k: 'T', cls: 't', value: f.time.value, detail: f.time.detail },
        { label: '(Frequency) 运动频率', k: 'F', cls: 'f', value: f.frequency.value, detail: f.frequency.detail },
        { label: '(Volume) 周运动总量', k: 'V', cls: 'v', value: f.volume.value, detail: f.volume.detail },
        { label: '(Progression) 运动进阶', k: 'P', cls: 'p', value: f.progression.value, detail: f.progression.detail || '' },
      ];
    },

    planDays() {
      return (this.rx.weekly_plan || []).map(day => ({
        ...day,
        actions: (day.blocks || []).flatMap(block => (block.items || []).map(item => {
          const detail = this.exerciseMap[item.exercise_id] || {};
          const phase = block.phase || '';
          const category = detail.category || '';
          const kind = /热身/.test(phase) ? 'warm' : /放松|整理|拉伸|柔韧/.test(phase) ? 'cool' : /柔韧|放松/.test(category) ? 'cool' : /抗阻|核心/.test(category) ? 'strength' : /热身/.test(category) ? 'warm' : /有氧|速度灵敏/.test(category) ? 'cardio' : /力量|核心/.test(phase) ? 'strength' : 'cardio';
          return { ...item, kind, points: (detail.key_points || []).join('；'), errors: (detail.common_errors || []).join('；') };
        })),
      }));
    },


  },

  watch: {
    /* 切换学生：有已生成结果就直接载入，没有就清空版面等待生成。
       录入新档案时 selectedId 由代码设置，由该流程处理，这里跳过 */
    selectedId(id) {
      if (!id || this.generating) return;
      if (this.hasData && this.rx.student_id === id) return;
      this.onStudentChange();
    },

  },

  mounted() {
    this._closeActionOnOutside = event => {
      if (!event.target.closest('.action-popover') && !event.target.closest('.wp-action')) this.closeActionDetail();
    };
    this._closeActionOnScroll = event => {
      if (!event.target.closest || !event.target.closest('.action-popover')) this.closeActionDetail();
    };
    this._closeActionOnEscape = event => { if (event.key === 'Escape') this.closeActionDetail(); };
    document.addEventListener('click', this._closeActionOnOutside);
    document.addEventListener('scroll', this._closeActionOnScroll, true);
    document.addEventListener('keydown', this._closeActionOnEscape);
    window.addEventListener('resize', this.closeActionDetail);

    // 动作库始终加载：生成前用于空态，生成后用于回填动作要点
    fetch('/api/v1/exercises')
      .then((r) => r.json())
      .then((d) => {
        (d.exercises || []).forEach((e) => {
          if (!this.exerciseMap[e.id]) this.exerciseMap[e.id] = e;
        });
      })
      .catch(() => {});

    // 学生列表与已有结果清单都到位后再定位默认学生，
    // 这样首个学生有已生成结果时能直接自动载入
    const studentsReady = fetch('/api/v1/students')
      .then((r) => r.json())
      .then((list) => { this.students = list; })
      .catch(() => {});

    Promise.all([studentsReady, this.refreshCached()]).then(() => {
      if (this.selectedId) return;
      // 优先认领 URL 携带的学生（如从档案理解报告页返回），无参再退回首个学生
      const wanted = new URLSearchParams(location.search).get('id');
      const hit = wanted && this.students.find((s) => s.student_id === wanted);
      this.selectedId = hit ? hit.student_id
        : (this.students[0] && this.students[0].student_id) || '';
    });
  },

  beforeUnmount() {
    document.removeEventListener('click', this._closeActionOnOutside);
    document.removeEventListener('scroll', this._closeActionOnScroll, true);
    document.removeEventListener('keydown', this._closeActionOnEscape);
    window.removeEventListener('resize', this.closeActionDetail);
  },

  methods: {
    closeActionDetail() { this.activeAction = null; this.activeActionKey = ''; },
    toggleActionDetail(item, key, event) {
      if (this.activeActionKey === key) { this.closeActionDetail(); return; }
      const rect = event.currentTarget.getBoundingClientRect();
      const width = Math.min(300, window.innerWidth - 24);
      let left = rect.right + 10;
      if (left + width > window.innerWidth - 12) left = rect.left - width - 10;
      if (left < 12) left = Math.max(12, Math.min(rect.left, window.innerWidth - width - 12));
      const top = Math.max(12, Math.min(rect.top, window.innerHeight - 150));
      this.actionPopoverStyle = { left: left + 'px', top: top + 'px', width: width + 'px', maxHeight: Math.max(100, window.innerHeight - top - 12) + 'px' };
      this.activeAction = item;
      this.activeActionKey = key;
    },

    async exportPlan() {
      const headers = ['星期', '安排', '时长（分钟）', '动作', '剂量'];
      if (this.exportDetails) headers.push('动作要点与注意事项');
      const rows = [];
      for (const day of this.planDays) {
        const actions = day.actions.length ? day.actions : [null];
        for (const item of actions) {
          const row = [day.day, day.theme || (item ? '训练' : '休息'), day.total_minutes ?? '', item ? (item.name || item.exercise_id) : '休息', item?.dosage || ''];
          if (this.exportDetails) row.push(item ? [item.notes, item.points && '动作要点：' + item.points, item.errors && '注意避免：' + item.errors].filter(Boolean).join('；') : '');
          rows.push(row);
        }
      }
      const name = this.exportName ? (this.rx.name || '') : '';
      if (this.exportFormat === 'xlsx') {
        try {
          const response = await fetch('/api/v1/export/weekly-plan.xlsx', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ days: this.planDays, include_details: this.exportDetails, name }) });
          if (!response.ok) throw new Error('服务返回 ' + response.status);
          const blob = await response.blob();
          const url = URL.createObjectURL(blob); const link = document.createElement('a'); link.href = url; link.download = '每周运动计划.xlsx'; link.click(); setTimeout(() => URL.revokeObjectURL(url), 1000);
        } catch (error) { alert('导出失败：' + error.message); return; }
      } else {
        const win = window.open('', '_blank');
        if (!win) { alert('浏览器阻止了打印窗口，请允许弹出窗口后重试。'); return; }
        const esc = value => String(value ?? '').replace(/[&<>"']/g, c => ({'&':'&amp;', '<':'&lt;', '>':'&gt;', '"':'&quot;', "'":'&#39;'}[c]));
        const detailMap = new Map();
        if (this.exportDetails) {
          for (const day of this.planDays) for (const item of day.actions) {
            const key = item.exercise_id || item.name;
            if (!key) continue;
            if (!detailMap.has(key)) detailMap.set(key, { name: item.name || item.exercise_id, points: new Set(), errors: new Set(), notes: new Map() });
            const detail = detailMap.get(key);
            if (item.points) detail.points.add(item.points);
            if (item.errors) detail.errors.add(item.errors);
            if (item.notes) { if (!detail.notes.has(item.notes)) detail.notes.set(item.notes, new Set()); detail.notes.get(item.notes).add(day.day); }
          }
        }
        const dayCards = this.planDays.map(day => {
          const actions = day.actions.map(item => {
            const kind = ['warm', 'cardio', 'strength', 'cool'].includes(item.kind) ? item.kind : 'cardio';
            return '<div class="action ' + kind + '"><strong>' + esc(item.name || item.exercise_id || '动作') + '</strong>' + (item.dosage ? '<span>' + esc(item.dosage) + '</span>' : '') + '</div>';
          }).join('');
          const dayTime = day.total_minutes != null ? esc(day.total_minutes) + ' 分钟' : '—';
          return '<div class="day' + (day.actions.length ? '' : ' rest') + '"><div class="day-label"><strong>' + esc(day.day) + '</strong><small>' + esc(day.theme || (day.actions.length ? '训练' : '休息')) + '</small></div><div class="actions">' + (actions || '<span class="rest-text">' + esc(day.theme || '休息') + '</span>') + '</div><div class="time">' + dayTime + '</div></div>';
        }).join('');
        const details = [...detailMap.values()].map(detail => {
          const lines = [...detail.points].map(x => '<p><b>要点：</b>' + esc(x) + '</p>')
            .concat([...detail.errors].map(x => '<p><b>注意避免：</b>' + esc(x) + '</p>'))
            .concat([...detail.notes].map(([note, days]) => '<p><b>' + esc([...days].join('、')) + '：</b>' + esc(note) + '</p>'));
          return lines.length ? '<article class="detail-item"><h3>' + esc(detail.name) + '</h3>' + lines.join('') + '</article>' : '';
        }).filter(Boolean).join('');
        const phase = this.rx.cycle.current_phase || '每周训练';
        const type = this.rx.fitt_vp.type.value || '';
        const review = this.rx.cycle.next_review || '';
        win.document.write(`<!doctype html><html lang="zh-CN"><head><meta charset="utf-8"><title>每周运动计划</title><style>
          *{box-sizing:border-box}body{font:14px/1.55 -apple-system,BlinkMacSystemFont,"PingFang SC","Microsoft YaHei",sans-serif;color:#23354e;margin:0;background:#f3f6fb;-webkit-print-color-adjust:exact;print-color-adjust:exact}.page{max-width:1000px;margin:28px auto;background:white;border:1px solid #dce5f0;border-radius:12px;overflow:hidden}.heading{background:#2468bd;color:white;padding:20px 26px}.heading h1{font-size:23px;margin:0}.heading p{margin:4px 0 0;color:#e6efff}.content{padding:20px 26px}.stage{background:#f3f7fc;padding:10px 13px;border-radius:7px;color:#586c88;margin-bottom:20px}.stage strong{color:#285994;margin-right:8px}.title{font-size:17px;margin:0 0 10px}.legend{display:flex;gap:16px;color:#61738a;font-size:12px;margin-bottom:12px;flex-wrap:wrap}.legend .warm{color:#ad6c23}.legend .cardio{color:#347ac9}.legend .strength{color:#8062bb}.legend .cool{color:#3d9478}.days{border:1px solid #e3eaf3;border-radius:9px;overflow:hidden}.day{display:grid;grid-template-columns:100px minmax(0,1fr) 70px;gap:12px;align-items:start;padding:12px 14px;border-top:1px solid #e3eaf3;break-inside:avoid;page-break-inside:avoid}.day:first-child{border-top:0}.day.rest{background:#fbfcfe}.day-label strong,.day-label small{display:block}.day-label small,.time,.rest-text{font-size:12px;color:#75859c}.time{text-align:right}.actions{display:flex;gap:7px;flex-wrap:wrap;min-width:0}.action{border:1px solid;border-left-width:3px;border-radius:6px;padding:6px 9px;max-width:100%;overflow-wrap:anywhere}.action strong{font-size:13px}.action span{margin-left:7px;font-size:12px}.action.warm{background:#fff5e8;border-color:#f2debd;border-left-color:#d49b46;color:#8d5b21}.action.cardio{background:#edf5ff;border-color:#dbeafa;border-left-color:#4c8ed7;color:#2864a8}.action.strength{background:#f4effc;border-color:#e8dff5;border-left-color:#9b7dca;color:#7353a5}.action.cool{background:#edf8f2;border-color:#dceee4;border-left-color:#62aa89;color:#347b60}.details{max-width:250px;margin-top:5px;color:#40536e;font-size:12px}.details p{margin:3px 0}.detail-section{margin-top:22px}.detail-list{columns:2;column-gap:22px}.detail-item{break-inside:avoid;page-break-inside:avoid;border-top:1px solid #e3eaf3;padding:8px 0;margin:0 0 5px}.detail-item h3{font-size:13px;color:#285994;margin:0 0 4px}.detail-item p{font-size:12px;line-height:1.5;color:#40536e;margin:2px 0;overflow-wrap:anywhere}.foot{font-size:12px;color:#75859c;margin:14px 0 0}@page{size:A4;margin:12mm}@media print{body{background:white}.page{margin:0;max-width:none;border:0;border-radius:0}.heading{padding:15px 20px}.content{padding:16px 0}.day{padding:9px 10px}}
        </style></head><body><main class="page"><header class="heading"><h1>每周运动计划</h1>${name ? '<p>姓名：' + esc(name) + '</p>' : ''}</header><div class="content"><div class="stage"><strong>${esc(phase)}</strong>${esc(type)}${review ? ' · 复评：' + esc(review) : ''}</div><h2 class="title">本周训练计划</h2><div class="legend"><span class="warm">● 热身</span><span class="cardio">● 有氧</span><span class="strength">● 力量／核心</span><span class="cool">● 拉伸／放松</span></div><div class="days">${dayCards}</div>${details ? '<section class="detail-section"><h2 class="title">动作要点与注意事项</h2><div class="detail-list">' + details + '</div></section>' : ''}<p class="foot">请按动作顺序执行，具体强度与时长以个人处方为准。</p></div></main></body></html>`);
        win.document.close(); win.focus(); win.print();
      }
      this.exportOpen = false;
    },

    /* ---------- 切换学生 / 预生成结果 ---------- */

    onStudentChange() {
      this.showForm = false;
      if (this.isCached) this.loadCached();
      else this.resetState();
    },

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
      // 报告版面挂在 v-if="!showForm" 下：先收起录入表单，结果才看得见
      this.showForm = false;
      this.resetState();
      // 原始档案单独拉取：报告头部的基本信息 / 体检 / 体测 / 伤病史直接展示档案原文
      this.fetchRecord(this.selectedId);
      try {
        const res = await fetch(`/api/v1/pregenerated/${this.selectedId}`);
        if (!res.ok) {
          this.genError = `载入失败：${(await res.json()).detail || res.status}`;
          return;
        }
        const data = await res.json();

        if (data.emergency) { this.emergency = data.emergency; }

        if (data.prescription) {
          this.applyResult(data.prescription);
        } else if (!data.emergency) {
          this.genError = '该学生的已有结果不含处方内容，可点「生成处方」生成';
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

    applyResult(rx) {
      this.rx = rx;
      this.rx.cycle = rx.cycle || { current_phase: '', next_review: '' };
      (rx.exercise_details || []).forEach((e) => { this.exerciseMap[e.id] = e; });
      this.hasData = true;
      document.title = `${rx.name || ''}运动处方报告`;
    },

    resetState() {
      this.rx = clone(EMPTY_RX);
      this.record = null;
      this.hasData = false;
      this.genError = '';
      this.emergency = null;
      this.aiMessages = [];
      this.closeActionDetail();
      document.title = '运动处方报告';
    },

    async generate() {
      if (!this.selectedId || this.generating) return;
      // 报告版面挂在 v-if="!showForm" 下：先收起录入表单，结果才看得见
      this.showForm = false;
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

    /* 把一份完整档案送入处方生成流程（SSE） */
    async streamGenerate(record) {
      this.generating = true;
      this.aiOpen = true;
      this.stage = '正在生成运动处方…';
      this.abortCtrl = new AbortController();
      try {
        await streamSSE('/api/v1/prescription:generate', { record }, {
          signal: this.abortCtrl.signal,
          onEvent: (event, payload) => this.handleFrame(event, payload),
        });
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
        // 生成结果已在后端落盘：刷新 ★ 标记与「载入已有结果」按钮状态
        this.refreshCached();
      }
    },

    stopGenerate() {
      if (this.abortCtrl) this.abortCtrl.abort();
    },

    /* 跳转到第一阶段（档案理解）的报告页，携带当前学生便于直接载入 */
    openProfile() {
      if (!this.selectedId) return;
      location.href = '/profile?id=' + encodeURIComponent(this.selectedId);
    },

    /* ---------- 自行录入 ---------- */

    splitList(text) {
      return (text || '').split(/[,，、;；\n]/).map((s) => s.trim()).filter(Boolean);
    },

    buildRecord() {
      const f = this.form;
      if (!f.name || !f.age || !f.height || !f.weight) {
        this.formError = '请至少填写姓名、年龄、身高、体重';
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
          WSMWFPCJ: f.wsmwfp,
          YQMCJ: f.yqm, BBMCJ: f.bbm, YTXSCJ: f.ytxs, YWQZCJ: f.ywqz,
        },
        health_profile: {
          chronic_conditions: this.splitList(f.chronic),
          medications: this.splitList(f.medications),
          injury_history: this.splitList(f.injuries).map((t) => ({ note: t })),
          recent_symptoms: this.splitList(f.symptoms),
          vitals: { resting_heart_rate: f.resting_hr, blood_pressure: f.blood_pressure },
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

    /* SSE 事件处理；未知事件（如旧后端的 profile）静默忽略 */
    handleFrame(event, payload) {
      switch (event) {
        case 'status':
          this.stage = payload.message + '…';
          this.pushAiNote(payload.message + '…');
          break;
        case 'thinking':
          this.stage = '模型正在设计运动处方…';
          this.appendThink(AI_TITLE, payload.text);
          break;
        case 'token':
          this.stage = '模型正在输出处方数据…';
          this.bumpProgress('处方', payload.text.length);
          break;
        case 'retry':
          this.stage = '输出未通过校验，正在重新生成…';
          this.pushAiNote('输出未通过校验，正在重新生成…');
          break;
        case 'result':
          this.applyResult(payload);
          this.pushAiNote('运动处方生成完成。');
          break;
        case 'emergency':
          this.emergency = payload;
          this.pushAiNote('命中急症关键词，已熔断，不再调用模型。');
          break;
        case 'error':
          this.genError = payload.message;
          this.pushAiNote('生成失败：' + payload.message);
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
  },
}).mount('#report');
