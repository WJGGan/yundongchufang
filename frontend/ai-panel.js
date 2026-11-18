/* 右侧 AI 输出抽屉公共 mixin：aiOpen/aiMessages/abortCtrl 状态与消息渲染方法。
   页面用 createApp({ mixins: [AiPanelMixin], ... })，模板需含 ai-drawer DOM（ref="aiBody"） */
window.AiPanelMixin = {
  data() {
    return {
      aiOpen: false,
      aiMessages: [],
      abortCtrl: null,
    };
  },

  methods: {
    /* 把模型输出渲染成 Markdown；先转义尖括号，防止模型输出原始 HTML */
    md(text) {
      const safe = (text || '').replace(/</g, '&lt;');
      try { return marked.parse(safe); } catch (e) { return safe; }
    },

    pushAiNote(text) {
      this.aiMessages.push({ kind: 'note', text });
      this.scrollAi();
    },

    /* 思考过程：自然语言，按 Markdown 渲染；title 由调用方传展示常量 */
    appendThink(title, text) {
      const last = this.aiMessages[this.aiMessages.length - 1];
      if (last && last.kind === 'think' && last.title === title) {
        last.text += text;
      } else {
        this.aiMessages.push({ kind: 'think', title, text });
      }
      this.scrollAi();
    },

    /* 结构化 JSON 不直接展示，只显示写入进度；what 为「画像」「处方」等展示常量 */
    bumpProgress(what, chars) {
      const last = this.aiMessages[this.aiMessages.length - 1];
      if (last && last.kind === 'progress' && last.what === what) {
        last.chars += chars;
      } else {
        this.aiMessages.push({ kind: 'progress', what, chars });
      }
      this.scrollAi();
    },

    progressText(m) {
      return `正在写入结构化${m.what}数据… 已接收 ${m.chars} 字符`;
    },

    scrollAi() {
      this.$nextTick(() => {
        const box = this.$refs.aiBody;
        if (box) box.scrollTop = box.scrollHeight;
      });
    },
  },
};
