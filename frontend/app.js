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
      aiOpen: false,
      aiMessages: [],
      abortCtrl: null,
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
      this.aiMessages = [];
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

    stopStream() {
      if (this.abortCtrl) this.abortCtrl.abort();
    },

    scrollAi() {
      this.$nextTick(() => {
        const box = this.$refs.aiBody;
        if (box) box.scrollTop = box.scrollHeight;
      });
    },

    async runProfile() {
      this.resetResults();
      this.loadingProfile = true;
      this.aiOpen = true;
      this.abortCtrl = new AbortController();
      try {
        const res = await fetch('/api/v1/profile:analyze:stream', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ record: this.record }),
          signal: this.abortCtrl.signal,
        });
        if (!res.ok) {
          this.rxError = `画像生成失败：HTTP ${res.status}`;
          return;
        }
        const reader = res.body.getReader();
        const decoder = new TextDecoder();
        let buffer = '';
        while (true) {
          const { value, done } = await reader.read();
          if (done) break;
          buffer += decoder.decode(value, { stream: true });
          const frames = buffer.split('\n\n');
          buffer = frames.pop();
          for (const frame of frames) this.handleProfileFrame(frame);
        }
      } catch (err) {
        if (err && err.name === 'AbortError') this.pushAiNote('已手动停止生成。');
        else this.rxError = String(err);
      } finally {
        this.loadingProfile = false;
        this.abortCtrl = null;
      }
    },

    handleProfileFrame(frame) {
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
          this.pushAiNote(payload.message + '…');
          break;
        case 'thinking':
          this.appendThink(payload.phase || 'profile', payload.text);
          break;
        case 'token':
          this.bumpProgress(payload.phase || 'profile', payload.text.length);
          break;
        case 'retry':
          this.pushAiNote('输出未通过结构校验，正在重新生成…');
          break;
        case 'emergency':
          this.emergency = payload;
          this.pushAiNote('命中急症关键词，已熔断，不再调用模型。');
          break;
        case 'result':
          this.profile = payload;
          this.pushAiNote('体质画像生成完成。');
          break;
        case 'error':
          this.rxError = payload.message;
          this.pushAiNote('生成失败：' + payload.message);
          break;
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
      this.aiOpen = true;
      this.abortCtrl = new AbortController();

      try {
        const res = await fetch('/api/v1/prescription:generate', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ record: this.record, profile: this.profile }),
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
          for (const frame of frames) this.handleFrame(frame);
        }
      } catch (err) {
        if (err && err.name === 'AbortError') this.pushAiNote('已手动停止生成。');
        else this.rxError = String(err);
      } finally {
        this.loadingRx = false;
        this.abortCtrl = null;
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
          this.pushAiNote(payload.message + '…');
          break;
        case 'profile':
          this.profile = payload;
          break;
        case 'thinking':
          this.appendThink(payload.phase || 'prescription', payload.text);
          break;
        case 'token':
          this.bumpProgress(payload.phase || 'prescription', payload.text.length);
          break;
        case 'retry':
          this.rxRetry = payload.problems;
          this.pushAiNote('输出未通过校验，正在重新生成…');
          break;
        case 'result':
          this.rx = payload;
          this.pushAiNote('运动处方生成完成。');
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
      window.open("/report", "_blank");
    },
  },
}).mount('#app');
