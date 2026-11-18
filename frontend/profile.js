const { createApp } = Vue;

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
  safety: {
    risk_level: '', can_generate_prescription: true, blocked_exercise_tags: [],
    intensity_ceiling: {}, referral_advice: [], notes: [],
  },
  disclaimer: '',
};

const clone = (o) => JSON.parse(JSON.stringify(o));

createApp({
  data() {
    return {
      profile: clone(EMPTY_PROFILE),
      students: [],
      cached: {},
      selectedId: '',
      emergency: null,
      blocked: null,
      error: '',
      loading: false,
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
    safety() { return this.profile.safety || {}; },
  },

  watch: {
    /* 切换学生后自动尝试载入该学生的画像 */
    selectedId(id) {
      if (id) this.load();
    },
  },

  mounted() {
    const studentsReady = fetch('/api/v1/students')
      .then((r) => r.json())
      .then((list) => { this.students = list; })
      .catch(() => {});

    const cachedReady = fetch('/api/v1/pregenerated')
      .then((r) => r.json())
      .then((d) => {
        const map = {};
        (d.items || []).forEach((it) => { map[it.student_id] = it; });
        this.cached = map;
      })
      .catch(() => {});

    Promise.all([studentsReady, cachedReady]).then(() => {
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
    /* 载入某学生第一阶段（档案理解）的画像结果，不调用模型 */
    async load() {
      if (!this.selectedId || this.loading) return;
      this.loading = true;
      this.error = '';
      this.emergency = null;
      this.blocked = null;
      this.profile = clone(EMPTY_PROFILE);
      document.title = '健康档案理解报告';
      try {
        const res = await fetch(`/api/v1/pregenerated/${this.selectedId}`);
        if (!res.ok) {
          const body = await res.json().catch(() => ({}));
          this.error = body.detail
            || `该学生（${this.selectedId}）还没有生成过画像，请先到「处方报告」页生成`;
          return;
        }
        const data = await res.json();

        if (data.emergency) this.emergency = data.emergency;
        if (data.blocked) this.blocked = data.blocked;
        if (data.profile) {
          this.profile = data.profile;
          document.title = `${data.profile.name || ''}健康档案理解报告`;
        } else if (!data.emergency) {
          this.error = '该学生的已有结果不含画像内容';
        }
      } catch (err) {
        this.error = `载入失败：${err}`;
      } finally {
        this.loading = false;
      }
    },

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
