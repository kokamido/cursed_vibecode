const { createApp } = Vue;

// Configure marked with highlight.js
marked.setOptions({
  highlight(code, lang) {
    if (lang && hljs.getLanguage(lang)) {
      return hljs.highlight(code, { language: lang }).value;
    }
    return hljs.highlightAuto(code).value;
  },
  breaks: true,
});

createApp({
  data() {
    return {
      messages: [],
      inputText: '',
      attachedImages: [],
      selectedModel: 'google/gemini-3-pro-preview',
      isLoading: false,
      errorMessage: '',
      conversations: [],
      activeConversationId: null,
      lightboxSrc: null,
      systemPrompt: '',
      savedPrompts: [],
      showPromptPanel: false,
      _promptSaveTimer: null,
      // Endpoints
      endpoints: [],
      activeEndpointId: null,
      showEndpointPanel: false,
      newEndpoint: { name: '', base_url: '', api_key: '' },
    };
  },

  async mounted() {
    await this.loadEndpoints();
    this.loadActiveEndpointId();
    await this.loadSavedPrompts();
    await this.loadConversations();

    const hashId = this.getConversationIdFromHash();
    const hashConvExists = hashId && this.conversations.some(c => c.id === hashId);

    if (hashConvExists) {
      await this.switchConversation(hashId, { pushHistory: false });
    } else if (this.conversations.length > 0) {
      if (hashId) this.setHashForConversation(null);
      await this.switchConversation(this.conversations[0].id, { pushHistory: false });
    } else {
      await this.createConversation();
    }

    window.addEventListener('hashchange', async () => {
      const newId = this.getConversationIdFromHash();
      if (newId && newId !== this.activeConversationId && this.conversations.some(c => c.id === newId)) {
        await this.switchConversation(newId, { pushHistory: false });
      }
    });
  },

  computed: {
    canRetry() {
      if (this.isLoading || this.messages.length === 0) return false;
      const last = this.messages[this.messages.length - 1];
      return last.role === 'user' || last.role === 'assistant';
    },
  },

  methods: {
    // ── URL hash helpers ──
    getConversationIdFromHash() {
      const match = window.location.hash.match(/^#\/chat\/(\d+)$/);
      return match ? Number(match[1]) : null;
    },

    setHashForConversation(convId, replace = false) {
      if (convId) {
        const newHash = `#/chat/${convId}`;
        if (replace) {
          history.replaceState(null, '', newHash);
        } else {
          window.location.hash = newHash;
        }
      } else {
        history.replaceState(null, '', window.location.pathname);
      }
    },

    // ── Lightbox ──
    openLightbox(src) {
      this.lightboxSrc = src;
    },

    closeLightbox() {
      this.lightboxSrc = null;
    },

    // ── Endpoint persistence ──
    loadActiveEndpointId() {
      const stored = localStorage.getItem('activeEndpointId');
      const storedId = stored ? Number(stored) : null;
      if (storedId && this.endpoints.some(e => e.id === storedId)) {
        this.activeEndpointId = storedId;
      } else if (this.endpoints.length > 0) {
        this.activeEndpointId = this.endpoints[0].id;
      }
    },

    saveActiveEndpointId() {
      if (this.activeEndpointId) {
        localStorage.setItem('activeEndpointId', String(this.activeEndpointId));
      } else {
        localStorage.removeItem('activeEndpointId');
      }
    },

    // ── Conversation management ──
    async loadConversations() {
      const resp = await fetch('/api/conversations');
      this.conversations = await resp.json();
    },

    async createConversation() {
      const resp = await fetch('/api/conversations', { method: 'POST' });
      const conv = await resp.json();
      this.conversations.unshift(conv);
      await this.switchConversation(conv.id, { pushHistory: false });
    },

    async deleteConversation(convId) {
      await fetch(`/api/conversations/${convId}`, { method: 'DELETE' });
      this.conversations = this.conversations.filter(c => c.id !== convId);
      if (this.activeConversationId === convId) {
        if (this.conversations.length > 0) {
          await this.switchConversation(this.conversations[0].id);
        } else {
          this.setHashForConversation(null);
          await this.createConversation();
        }
      }
    },

    async switchConversation(convId, { pushHistory = true } = {}) {
      this.activeConversationId = convId;
      this.setHashForConversation(convId, !pushHistory);
      const conv = this.conversations.find(c => c.id === convId);
      this.systemPrompt = conv ? conv.system_prompt || '' : '';
      const resp = await fetch(`/api/conversations/${convId}/messages`);
      this.messages = await resp.json();
      this.errorMessage = '';
      this.scrollToBottom();
    },

    async saveMessage(role, text, images) {
      const resp = await fetch(`/api/conversations/${this.activeConversationId}/messages`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ role, text, images: images || [] }),
      });
      return await resp.json();
    },

    async refreshSidebar() {
      await this.loadConversations();
    },

    // ── System Prompts ──
    async loadSavedPrompts() {
      const resp = await fetch('/api/prompts');
      this.savedPrompts = await resp.json();
    },

    onSystemPromptInput() {
      clearTimeout(this._promptSaveTimer);
      this._promptSaveTimer = setTimeout(() => this.patchSystemPrompt(), 500);
    },

    async patchSystemPrompt() {
      if (!this.activeConversationId) return;
      await fetch(`/api/conversations/${this.activeConversationId}`, {
        method: 'PATCH',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ system_prompt: this.systemPrompt }),
      });
      const conv = this.conversations.find(c => c.id === this.activeConversationId);
      if (conv) conv.system_prompt = this.systemPrompt;
    },

    applySavedPrompt(event) {
      const id = Number(event.target.value);
      if (!id) return;
      const p = this.savedPrompts.find(sp => sp.id === id);
      if (p) {
        this.systemPrompt = p.text;
        this.patchSystemPrompt();
      }
      event.target.value = '';
    },

    async saveCurrentPrompt() {
      const text = this.systemPrompt.trim();
      if (!text) return;
      const name = prompt('Name for this prompt:');
      if (!name || !name.trim()) return;
      const resp = await fetch('/api/prompts', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ name: name.trim(), text }),
      });
      if (resp.ok) {
        await this.loadSavedPrompts();
      }
    },

    async deleteSavedPrompt(promptId) {
      await fetch(`/api/prompts/${promptId}`, { method: 'DELETE' });
      await this.loadSavedPrompts();
    },

    togglePromptPanel() {
      this.showPromptPanel = !this.showPromptPanel;
    },

    // ── Endpoints ──
    async loadEndpoints() {
      const resp = await fetch('/api/endpoints');
      this.endpoints = await resp.json();
    },

    async createEndpoint() {
      const { name, base_url, api_key } = this.newEndpoint;
      if (!name.trim() || !base_url.trim()) return;
      const resp = await fetch('/api/endpoints', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ name: name.trim(), base_url: base_url.trim(), api_key: api_key.trim() }),
      });
      if (resp.ok) {
        const ep = await resp.json();
        this.endpoints.push(ep);
        this.newEndpoint = { name: '', base_url: '', api_key: '' };
        if (!this.activeEndpointId) {
          this.activeEndpointId = ep.id;
          this.saveActiveEndpointId();
        }
      }
    },

    async deleteEndpoint(epId) {
      await fetch(`/api/endpoints/${epId}`, { method: 'DELETE' });
      this.endpoints = this.endpoints.filter(e => e.id !== epId);
      if (this.activeEndpointId === epId) {
        this.activeEndpointId = this.endpoints[0]?.id ?? null;
        this.saveActiveEndpointId();
      }
    },

    toggleEndpointPanel() {
      this.showEndpointPanel = !this.showEndpointPanel;
    },

    onEndpointChange(event) {
      this.activeEndpointId = Number(event.target.value);
      this.saveActiveEndpointId();
    },

    // ── Image attachment ──
    triggerFileInput() {
      this.$refs.fileInput.click();
    },

    onFileSelected(event) {
      const files = Array.from(event.target.files);
      files.forEach((file) => this.readAndResizeImage(file));
      event.target.value = '';
    },

    readAndResizeImage(file) {
      const reader = new FileReader();
      reader.onload = (e) => {
        const img = new Image();
        img.onload = () => {
          const MAX = 1024;
          let { width, height } = img;
          if (width > MAX || height > MAX) {
            if (width > height) {
              height = Math.round(height * MAX / width);
              width = MAX;
            } else {
              width = Math.round(width * MAX / height);
              height = MAX;
            }
          }
          const canvas = document.createElement('canvas');
          canvas.width = width;
          canvas.height = height;
          const ctx = canvas.getContext('2d');
          ctx.drawImage(img, 0, 0, width, height);
          const dataUrl = canvas.toDataURL('image/jpeg', 0.85);
          this.attachedImages.push(dataUrl);
        };
        img.src = e.target.result;
      };
      reader.readAsDataURL(file);
    },

    removeAttachment(idx) {
      this.attachedImages.splice(idx, 1);
    },

    // ── Markdown rendering ──
    renderMarkdown(text) {
      if (!text) return '';
      const html = marked.parse(text);
      return DOMPurify.sanitize(html);
    },

    // ── Auto-resize textarea ──
    autoResize() {
      const el = this.$refs.messageInput;
      el.style.height = 'auto';
      el.style.height = Math.min(el.scrollHeight, 120) + 'px';
    },

    // ── Scroll to bottom ──
    scrollToBottom() {
      this.$nextTick(() => {
        const area = this.$refs.chatArea;
        if (area) area.scrollTop = area.scrollHeight;
      });
    },

    // ── Check if current model is the image model ──
    isImageModel() {
      return this.selectedModel === 'google/gemini-3-pro-image-preview';
    },

    // ── Build request body (OpenAI Responses API for text, Chat Completions for image) ──
    buildRequestBody() {
      if (this.isImageModel()) {
        return this.buildChatCompletionsBody();
      }
      return this.buildResponsesBody();
    },

    buildResponsesBody() {
      const input = [];
      if (this.systemPrompt.trim()) {
        input.push({ role: 'developer', content: [{ type: 'input_text', text: this.systemPrompt.trim() }] });
      }
      for (const msg of this.messages) {
        const content = [];
        if (msg.role === 'user') {
          if (msg.text) {
            content.push({ type: 'input_text', text: msg.text });
          }
          if (msg.images && msg.images.length) {
            for (const dataUrl of msg.images) {
              content.push({ type: 'input_image', image_url: dataUrl });
            }
          }
        } else {
          if (msg.text) {
            content.push({ type: 'output_text', text: msg.text });
          }
        }
        if (content.length) {
          input.push({ role: msg.role, content });
        }
      }
      return { model: this.selectedModel, input };
    },

    buildChatCompletionsBody() {
      const messages = [];
      if (this.systemPrompt.trim()) {
        messages.push({ role: 'system', content: this.systemPrompt.trim() });
      }
      for (const msg of this.messages) {
        const content = [];
        if (msg.role === 'user') {
          if (msg.text) {
            content.push({ type: 'text', text: msg.text });
          }
          if (msg.images && msg.images.length) {
            for (const dataUrl of msg.images) {
              content.push({ type: 'image_url', image_url: { url: dataUrl } });
            }
          }
        } else {
          if (msg.text) {
            content.push({ type: 'text', text: msg.text });
          }
        }
        if (content.length) {
          messages.push({ role: msg.role, content });
        }
      }
      return {
        model: this.selectedModel,
        messages,
        extra_body: { modalities: ['image'] },
      };
    },

    // ── Get API endpoint based on model ──
    getApiEndpoint() {
      const path = this.isImageModel() ? '/api/v1/chat/completions' : '/api/v1/responses';
      return `${path}?endpoint_id=${this.activeEndpointId}`;
    },

    // ── Parse response ──
    parseResponse(data, isError) {
      if (this.isImageModel()) {
        return this.parseChatCompletionsResponse(data, isError);
      }
      return this.parseResponsesApiResponse(data);
    },

    parseResponsesApiResponse(data) {
      let text = '';
      const images = [];
      if (data.output && Array.isArray(data.output)) {
        for (const item of data.output) {
          if (item.type === 'message' && item.content) {
            for (const part of item.content) {
              if (part.type === 'output_text') {
                text += part.text;
              }
            }
          } else if (item.type === 'image_generation_call') {
            if (item.result) {
              images.push('data:image/png;base64,' + item.result);
            }
          }
        }
      }
      return { text, images };
    },

    parseChatCompletionsResponse(data, isError) {
      let text = '';
      const images = [];

      if (!isError && data.choices) {
        const msg = data.choices[0]?.message;
        if (msg) {
          if (msg.content) text = msg.content;
          if (msg.images) {
            for (const img of msg.images) {
              if (img.b64_json) {
                images.push('data:image/png;base64,' + img.b64_json);
              }
            }
          }
        }
        return { text, images };
      }

      const errMsg = data.error?.message || '';
      const b64Regex = /'b64_json':\s*'([A-Za-z0-9+/=]+)'/g;
      let match;
      while ((match = b64Regex.exec(errMsg)) !== null) {
        images.push('data:image/png;base64,' + match[1]);
      }

      const contentMatch = errMsg.match(/'content':\s*'([^']*)'/);
      if (contentMatch && contentMatch[1]) {
        text = contentMatch[1];
      }

      return { text, images };
    },

    // ── Call LLM API and handle response ──
    async callLlm() {
      if (!this.activeEndpointId) {
        this.errorMessage = 'Please add and select an API endpoint first.';
        return false;
      }

      this.isLoading = true;
      this.errorMessage = '';

      try {
        const body = this.buildRequestBody();
        const endpoint = this.getApiEndpoint();
        const resp = await fetch(endpoint, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify(body),
        });

        const data = await resp.json();

        if (!resp.ok) {
          if (this.isImageModel()) {
            const parsed = this.parseResponse(data, true);
            if (parsed.images.length > 0) {
              const assistantMsg = { role: 'assistant', text: parsed.text, images: parsed.images };
              this.messages.push(assistantMsg);
              const saved = await this.saveMessage('assistant', parsed.text, parsed.images);
              assistantMsg.id = saved.id;
              await this.refreshSidebar();
              return true;
            }
          }
          const errMsg = data.error?.message || data.error || JSON.stringify(data);
          this.errorMessage = `API error (${resp.status}): ${errMsg}`;
          return false;
        }

        const parsed = this.parseResponse(data, false);
        const assistantMsg = { role: 'assistant', text: parsed.text, images: parsed.images };
        this.messages.push(assistantMsg);
        const saved = await this.saveMessage('assistant', parsed.text, parsed.images);
        assistantMsg.id = saved.id;
        await this.refreshSidebar();
        return true;
      } catch (err) {
        this.errorMessage = 'Request failed: ' + err.message;
        return false;
      } finally {
        this.isLoading = false;
        this.scrollToBottom();
      }
    },

    // ── Send message ──
    async sendMessage() {
      const text = this.inputText.trim();
      const images = [...this.attachedImages];

      if (!text && !images.length) return;

      if (!this.activeEndpointId) {
        this.errorMessage = 'Please add and select an API endpoint first.';
        return;
      }

      // Add user message to UI
      const userMsg = { role: 'user', text, images };
      this.messages.push(userMsg);
      this.inputText = '';
      this.attachedImages = [];
      this.$nextTick(() => {
        const el = this.$refs.messageInput;
        if (el) {
          el.style.height = 'auto';
        }
      });
      this.scrollToBottom();

      // Save user message to backend
      await this.saveMessage('user', text, images);
      await this.refreshSidebar();

      await this.callLlm();
    },

    // ── Retry last message ──
    async retryMessage() {
      if (!this.canRetry) return;
      const last = this.messages[this.messages.length - 1];
      if (last.role === 'assistant') {
        this.messages.pop();
        const ok = await this.callLlm();
        if (ok && last.id) {
          await fetch(`/api/conversations/${this.activeConversationId}/messages/${last.id}`, { method: 'DELETE' });
        } else if (!ok) {
          this.messages.push(last);
        }
      } else {
        await this.callLlm();
      }
    },
  },
}).mount('#app');
