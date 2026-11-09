const { createApp } = Vue;

const FIELD_LABELS = {
  YEARSTART: '学年开始', YEAREND: '学年结束', XB: '性别', NL: '年龄',
  SG: '身高(cm)', TZ: '体重(kg)', FHL: '肺活量(ml)',
  ZYSL: '左眼视力', YYSL: '右眼视力', ZYJSL: '左眼近视力', YYJSL: '右眼近视力',
  JSLPJ: '近视力评价', JZ: '脊柱筛查', UP_TIME: '上传时间',
  SCHOOL_GRADE: '年级', TOWN_ID: '区id', NJ: '年级',
  SGCJ: '身高成绩', TZCJ: '体重成绩', FHLCJ: '肺活量成绩',
  WSMCJ: '50米(秒)', LDTYCJ: '立定跳远(cm)', ZWTQQCJ: '坐位体前屈(cm)',
  WSMWFPCJ: '50米×8往返(秒)', YFZTSCJ: '一分钟跳绳(次)',
  BBMCJ: '800米(女)', YWQZCJ: '仰卧起坐(次)', YQMCJ: '1000米(男)',
  YTXSCJ: '引体向上(男)',
};

const LEVEL_MAP = {
  '优秀': { cls: 'excellent', width: '100%' },
  '良好': { cls: 'good', width: '78%' },
  '及格': { cls: 'pass', width: '56%' },
  '较差': { cls: 'poor', width: '32%' },
  '数据不足': { cls: 'unknown', width: '8%' },
};

createApp({
  data() {
    return {
      meta: null,
      students: [],
      selectedId: null,
      record: null,
      profile: null,
      emergency: null,
      loadingProfile: false,
      rx: null,
      rxBlocked: null,
      rxError: '',
      rxStream: '',
      rxStatus: '',
      rxRetry: '',
      loadingRx: false,
      modal: null,
      openExplain: null,
      exerciseCache: {},
      knowledgeCache: {},
      fittLabels: {
        '频率 F': 'frequency', '强度 I': 'intensity', '时间 T': 'time',
        '类型 T': 'type', '总量 V': 'volume', '进阶 P': 'progression',
      },
    };
  },

  computed: {
    canPrescribe() {
      return this.profile && this.profile.safety.can_generate_prescription;
    },
    hasDataIssues() {
      const q = this.profile && this.profile.data_quality;
      if (!q) return false;
      return q.missing_fields.length || q.conflicts.length || q.clarification_questions.length;
    },
  },

  async mounted() {
    this.meta = await this.get('/api/v1/meta');
    this.students = await this.get('/api/v1/students');
    const ex = await this.get('/api/v1/exercises');
    ex.exercises.forEach((e) => { this.exerciseCache[e.id] = e; });
    const kb = await this.get('/api/v1/knowledge');
    kb.cards.forEach((c) => { this.knowledgeCache[c.id] = c; });
    if (this.students.length) this.selectStudent(this.students[0].student_id);
  },

  methods: {
    async get(url) {
      const res = await fetch(url);
      if (!res.ok) throw new Error(`${url} -> ${res.status}`);
      return res.json();
    },

    fieldLabel(key) { return FIELD_LABELS[key] || key; },
    pretty(obj) { return JSON.stringify(obj, null, 2); },
    levelClass(level) { return (LEVEL_MAP[level] || LEVEL_MAP['数据不足']).cls; },
    levelWidth(level) { return (LEVEL_MAP[level] || LEVEL_MAP['数据不足']).width; },
    riskClass(level) { return { '高': 'high', '中': 'mid', '低': 'low' }[level] || 'mid'; },
    priClass(p) { return { '高': 'high', '中': 'mid', '低': 'low' }[p] || 'mid'; },

    async selectStudent(id) {
      this.selectedId = id;
      this.resetResults();
      this.record = await this.get(`/api/v1/students/${id}`);
    },

    resetResults() {
      this.profile = null;
      this.emergency = null;
      this.rx = null;
      this.rxBlocked = null;
      this.rxError = '';
      this.rxStream = '';
      this.rxRetry = '';
      this.openExplain = null;
    },

    async runProfile() {
      this.resetResults();
      this.loadingProfile = true;
      try {
        const res = await fetch('/api/v1/profile:analyze', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ record: this.record }),
        });
        const body = await res.json();
        if (!res.ok) {
          this.rxError = body.detail || '画像生成失败';
          return;
        }
        if (body.emergency) this.emergency = body.emergency;
        else this.profile = body.profile;
      } catch (err) {
        this.rxError = String(err);
      } finally {
        this.loadingProfile = false;
      }
    },

    async runPrescription() {
      this.rx = null;
      this.rxBlocked = null;
      this.rxError = '';
      this.rxStream = '';
      this.rxRetry = '';
      this.rxStatus = '正在连接模型…';
      this.loadingRx = true;

      try {
        const res = await fetch('/api/v1/prescription:generate', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ record: this.record, profile: this.profile }),
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
          for (const frame of frames) this.handleFrame(frame);
        }
      } catch (err) {
        this.rxError = String(err);
      } finally {
        this.loadingRx = false;
      }
    },

    handleFrame(frame) {
      let event = 'message';
      let data = '';
      for (const line of frame.split('\n')) {
        if (line.startsWith('event: ')) event = line.slice(7).trim();
        else if (line.startsWith('data: ')) data += line.slice(6);
      }
      if (!data) return;
      let payload;
      try { payload = JSON.parse(data); } catch { return; }

      switch (event) {
        case 'status':
          this.rxStatus = payload.message;
          break;
        case 'profile':
          this.profile = payload;
          break;
        case 'token':
          this.rxStream += payload.text;
          this.$nextTick(() => {
            const box = this.$refs.streamBox;
            if (box) box.scrollTop = box.scrollHeight;
          });
          break;
        case 'retry':
          this.rxRetry = payload.problems;
          this.rxStream = '';
          break;
        case 'result':
          this.rx = payload;
          break;
        case 'blocked':
          this.rxBlocked = payload;
          break;
        case 'emergency':
          this.emergency = payload;
          break;
        case 'error':
          this.rxError = payload.message;
          break;
      }
    },

    explainFor(target) {
      if (!this.rx) return null;
      return this.rx.explanations.find((e) => e.target === target) || null;
    },

    toggleExplain(target) {
      this.openExplain = this.openExplain === target ? null : target;
    },

    showExercise(id) {
      const data = this.exerciseCache[id];
      if (data) this.modal = { kind: 'exercise', data };
    },

    showCard(id) {
      const data = this.knowledgeCache[id];
      if (data) this.modal = { kind: 'knowledge', data };
    },

    openReport() {
      if (!this.rx) return;
      sessionStorage.setItem('rx_report', JSON.stringify({
        rx: this.rx,
        profile: this.profile,
        record: this.record,
      }));
      window.open('/report', '_blank');
    },
  },
}).mount('#app');
