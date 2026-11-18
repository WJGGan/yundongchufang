const { createApp } = Vue;

const AI_TITLE = '体质画像 · 模型分析';

/* 空骨架：无数据时版式照常渲染，字段留白而非整页隐藏 */
const EMPTY_PROFILE = {
  student_id: '',
  name: '',
  generated_at: '',
  versions: {},
  basic: {},
  fitness_dimensions: [],
  overall: { level: '', summary: '', strengths: [], weaknesses: [] },
  health_focus: [],
  disclaimer: '',
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
  symptoms: '',
};

createApp({
  mixins: [AiPanelMixin],

  data() {
    return {
      profile: clone(EMPTY_PROFILE),
      record: null,
      students: [],
      cached: {},
      selectedId: '',
      emergency: null,
      error: '',
      loading: false,
      generating: false,
      stage: '',
      genError: '',
      showForm: false,
      form: clone(DEFAULT_FORM),
      formSaving: false,
      formError: '',
    };
  },

  computed: {
    /* 只有画像真正就位才算有数据：急症熔断时空白版式照常降透明度，与处方报告页一致 */
    hasData() {
      return !!(this.profile && this.profile.generated_at);
    },
    /* 回到处方报告页时携带当前学生，对方页面据此自动选中并载入 */
    backHref() {
      return this.selectedId
        ? '/report?id=' + encodeURIComponent(this.selectedId)
        : '/report';
    },
    basic() { return this.profile.basic || {}; },
    dims() { return this.profile.fitness_dimensions || []; },
    overall() { return this.profile.overall || { strengths: [], weaknesses: [] }; },
    focus() { return this.profile.health_focus || []; },
  },

  watch: {
    /* 切换学生后自动尝试载入该学生的画像；生成中下拉已禁用，这里再兜底一次 */
    selectedId(id) {
      if (id && !this.generating) this.load();
    },
  },

  mounted() {
    const studentsReady = fetch('/api/v1/students')
      .then((r) => r.json())
      .then((list) => { this.students = list; })
      .catch(() => {});

    Promise.all([studentsReady, this.refreshCached()]).then(() => {
      // 从处方报告页带学生编号跳转过来：直接定位该学生并载入
      const id = new URLSearchParams(location.search).get('id');
      const initial = this.students.find((s) => s.student_id === id);
      if (initial) {
        this.selectedId = initial.student_id; // watch 触发载入
      } else if (!this.selectedId && this.students.length) {
        this.selectedId = this.students[0].student_id;
      }
    });
  },

  methods: {
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

    /* 载入某学生已生成的画像结果，不调用模型 */
    async load() {
      if (!this.selectedId || this.loading) return;
      this.loading = true;
      this.resetState();
      try {
        const res = await fetch(`/api/v1/pregenerated/${this.selectedId}`);
        if (!res.ok) {
          const body = await res.json().catch(() => ({}));
          this.error = body.detail
            || `该学生（${this.selectedId}）还没有生成过档案理解报告，点「生成档案理解报告」即可实时生成`;
          return;
        }
        const data = await res.json();

        if (data.emergency) this.emergency = data.emergency;
        if (data.profile) {
          this.profile = data.profile;
          document.title = `${data.profile.name || ''}健康档案理解报告`;
        } else if (!data.emergency) {
          this.error = '该学生的已有结果不含画像内容，点「生成档案理解报告」即可实时生成';
        }
      } catch (err) {
        this.error = `载入失败：${err}`;
      } finally {
        this.loading = false;
      }
    },

    /* ---------- 实时生成（SSE） ---------- */

    resetState() {
      this.profile = clone(EMPTY_PROFILE);
      this.record = null;
      this.error = '';
      this.genError = '';
      this.emergency = null;
      this.aiMessages = [];
      this.showForm = false;
      document.title = '健康档案理解报告';
    },

    async generate() {
      if (!this.selectedId || this.generating) return;
      this.resetState();
      this.generating = true;
      this.aiOpen = true;
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

    /* 把一份完整档案送入画像生成流程（SSE） */
    async streamGenerate(record) {
      this.generating = true;
      this.aiOpen = true;
      this.stage = '正在生成体质画像…';
      this.abortCtrl = new AbortController();
      try {
        await streamSSE('/api/v1/profile:analyze:stream', { record }, {
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
        // 生成结果已在后端落盘：刷新下拉里的 ★ 标记
        this.refreshCached();
      }
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

      // 新档案已落盘：刷新下拉列表并选中，再直接走画像生成流程。
      // selectedId 变更触发的 watch 会被 streamGenerate 同步置起的 generating 挡住，不会误载入
      fetch('/api/v1/students')
        .then((r) => r.json())
        .then((list) => { this.students = list; })
        .catch(() => {});
      this.resetState();
      this.selectedId = saved.student_id;
      this.record = saved;
      await this.streamGenerate(saved);
    },

    stopGenerate() {
      if (this.abortCtrl) this.abortCtrl.abort();
    },

    /* SSE 事件处理；未知事件静默忽略 */
    handleFrame(event, payload) {
      switch (event) {
        case 'status':
          this.stage = payload.message + '…';
          this.pushAiNote(payload.message + '…');
          break;
        case 'thinking':
          this.stage = '模型正在分析体质画像…';
          this.appendThink(AI_TITLE, payload.text);
          break;
        case 'token':
          this.stage = '模型正在输出画像数据…';
          this.bumpProgress('画像', payload.text.length);
          break;
        case 'retry':
          this.stage = '输出未通过校验，正在重新生成…';
          this.pushAiNote('输出未通过校验，正在重新生成…');
          break;
        case 'result':
          this.profile = payload;
          document.title = `${payload.name || ''}健康档案理解报告`;
          this.pushAiNote('体质画像生成完成。');
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

    /* 等级 → 徽标类名 + 进度条宽度 */
    levelMeta(level) {
      const s = level || '';
      if (s.includes('优')) return { cls: 'lv-exc bar-exc', width: '95%' };
      if (s.includes('良')) return { cls: 'lv-good bar-good', width: '78%' };
      if (s.includes('不及格') || s.includes('差') || s.includes('弱')) return { cls: 'lv-fail bar-fail', width: '35%' };
      if (s) return { cls: 'lv-pass bar-pass', width: '60%' };
      return { cls: '', width: '0%' };
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
}).mount('#profile');
