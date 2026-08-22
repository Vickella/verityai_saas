class VerityAIWidget {
  constructor(config = {}) {
    this.tenantId = config.tenantId || this.getTenantFromScript();
    this.assistantName = config.assistantName || this.scriptConfig.assistantName || 'Verity AI';
    this.widgetTitle = config.widgetTitle || this.scriptConfig.widgetTitle || 'Client Support Assistant';
    this.greeting = config.greeting || this.scriptConfig.greeting || 'Welcome. I am here to help with product information, service questions, or anything else you need.';
    this.apiUrl = config.apiUrl || `${this.host}/api/method/verity_ai.api.chat.send_message`;
    this.settingsUrl = `${this.host}/api/method/verity_ai.api.chat.get_widget_settings`;
    this.sessionKey = `verity-ai-session-${this.tenantId}`;
    this.sessionId = this.getSavedSession();
    this.maxMessageChars = 4000;
    this.showBranding = true;
    this.isSending = false;
    this.isUnavailable = false;

    if (!this.tenantId) {
      console.error('Verity AI: Tenant ID is missing.');
      return;
    }

    this.cleanVisibleReferralSource();
    this.init();
  }


  cleanVisibleReferralSource() {
    try {
      const url = new URL(window.location.href);
      if (url.searchParams.get('utm_source') === 'chatgpt.com') {
        url.searchParams.delete('utm_source');
        const clean = `${url.pathname}${url.search}${url.hash}`;
        window.history.replaceState(window.history.state, document.title, clean);
      }
    } catch (error) {
      // Keep widget startup resilient on unusual URL environments.
    }
  }
  getTenantFromScript() {
    this.scriptConfig = {};
    const scripts = document.getElementsByTagName('script');
    for (let script of scripts) {
      if (script.src.includes('widget.js')) {
        try {
          const url = new URL(script.src);
          this.host = url.origin;
        } catch (e) {
          this.host = '';
        }
        this.scriptConfig.assistantName = script.getAttribute('data-assistant-name') || '';
        this.scriptConfig.widgetTitle = script.getAttribute('data-widget-title') || '';
        this.scriptConfig.greeting = script.getAttribute('data-greeting') || '';
        return script.getAttribute('data-tenant-id');
      }
    }
    this.host = '';
    return null;
  }

  getSavedSession() {
    try {
      return localStorage.getItem(this.sessionKey) || null;
    } catch (error) {
      return null;
    }
  }

  saveSession(sessionId) {
    this.sessionId = sessionId || this.sessionId;
    try {
      if (this.sessionId) localStorage.setItem(this.sessionKey, this.sessionId);
    } catch (error) {
      // Session persistence is best-effort only.
    }
  }

  init() {
    const link = document.createElement('link');
    link.rel = 'stylesheet';
    link.href = `${this.host}/assets/verity_ai/css/widget.css`;
    document.head.appendChild(link);

    this.container = document.createElement('div');
    this.container.id = 'verity-ai-widget';
    this.container.style.visibility = 'hidden';
    document.body.appendChild(this.container);

    this.render();
    this.attachEvents();
    this.loadSettings().finally(() => {
      this.container.style.visibility = '';
    });
  }

  async loadSettings() {
    try {
      const url = `${this.settingsUrl}?tenant_id=${encodeURIComponent(this.tenantId)}&_=${Date.now()}`;
      const response = await fetch(url, { cache: 'no-store', credentials: 'omit', headers: { 'Accept': 'application/json' } });
      if (!response.ok) {
        if ([403, 404].includes(response.status)) this.setUnavailable('This chat is not available from this website at the moment.');
        return;
      }
      const data = await response.json();
      const settings = data.message || data;
      if (!settings.success) {
        this.setUnavailable('This chat is not available from this website at the moment.');
        return;
      }

      this.assistantName = settings.assistant_name || this.assistantName;
      this.widgetTitle = settings.title || this.widgetTitle;
      this.greeting = settings.greeting || this.greeting;
      this.maxMessageChars = Number(settings.max_message_chars || this.maxMessageChars);
      this.showBranding = settings.show_branding !== false;
      this.updateBranding();
      this.applyTheme(settings);
      this.updateHeader();
      this.updateGreeting();
      this.updateInputLimits();
    } catch (error) {
      console.warn('Verity AI settings unavailable:', error);
    }
  }

  setUnavailable(message) {
    this.isUnavailable = true;
    const input = document.getElementById('verity-input');
    const sendBtn = document.getElementById('verity-send-btn');
    if (input) {
      input.value = '';
      input.placeholder = message;
      input.disabled = true;
      input.setAttribute('aria-disabled', 'true');
    }
    if (sendBtn) sendBtn.disabled = true;
    if (!document.querySelector('.verity-message.ai[data-status="unavailable"]')) {
      this.appendMessage('ai', message, { status: 'unavailable' });
    }
  }

  applyTheme(settings) {
    if (settings.primary_color) this.container.style.setProperty('--verity-primary', settings.primary_color);
    if (settings.primary_dark_color) this.container.style.setProperty('--verity-primary-dark', settings.primary_dark_color);
    if (settings.header_background) this.container.style.setProperty('--verity-header-bg', settings.header_background);
  }

  render() {
    this.container.innerHTML = `
      <div class="verity-chat-window" id="verity-chat-window" role="dialog" aria-label="Verity AI chat" aria-modal="false">
        <div class="verity-header">
          <div class="verity-avatar">
            <svg viewBox="0 0 24 24"><path d="M12 2C6.48 2 2 6.48 2 12s4.48 10 10 10 10-4.48 10-10S17.52 2 12 2zm0 3c1.66 0 3 1.34 3 3s-1.34 3-3 3-3-1.34-3-3 1.34-3 3-3zm0 14.2c-2.5 0-4.71-1.28-6-3.22.03-1.99 4-3.08 6-3.08 1.99 0 5.97 1.09 6 3.08-1.29 1.94-3.5 3.22-6 3.22z"/></svg>
          </div>
          <div class="verity-title-container">
            <h3 class="verity-title" id="verity-title"></h3>
            <span class="verity-subtitle" id="verity-subtitle"></span>
          </div>
        </div>
        <div class="verity-messages" id="verity-messages" aria-live="polite">
          <div class="verity-typing" id="verity-typing" aria-hidden="true">
            <div class="verity-dot"></div>
            <div class="verity-dot"></div>
            <div class="verity-dot"></div>
          </div>
        </div>
        <div class="verity-branding" id="verity-branding">Powered by VerityAI</div>
        <div class="verity-input-container">
          <input type="text" class="verity-input" id="verity-input" placeholder="Type your message..." autocomplete="off" aria-label="Message Verity AI">
          <button class="verity-send-btn" id="verity-send-btn" aria-label="Send message">
            <svg viewBox="0 0 24 24"><path d="M2.01 21L23 12 2.01 3 2 10l15 2-15 2z"/></svg>
          </button>
        </div>
      </div>
      <div class="verity-fab" id="verity-fab" role="button" tabindex="0" aria-label="Open chat" aria-expanded="false">
        <svg viewBox="0 0 24 24"><path d="M20 2H4c-1.1 0-2 .9-2 2v18l4-4h14c1.1 0 2-.9 2-2V4c0-1.1-.9-2-2-2z"/></svg>
      </div>
    `;
    this.updateHeader();
    this.updateInputLimits();
    this.appendMessage('ai', this.greeting, { greeting: true });
  }

  updateHeader() {
    const title = document.getElementById('verity-title');
    const subtitle = document.getElementById('verity-subtitle');
    if (title) title.textContent = this.assistantName;
    if (subtitle) subtitle.textContent = this.widgetTitle;
  }


  updateBranding() {
    const branding = document.getElementById('verity-branding');
    if (branding) branding.hidden = !this.showBranding;
  }  updateInputLimits() {
    const input = document.getElementById('verity-input');
    if (input && this.maxMessageChars) input.setAttribute('maxlength', String(this.maxMessageChars));
  }

  updateGreeting() {
    const greeting = document.querySelector('.verity-message.ai[data-greeting="true"]');
    if (greeting) greeting.textContent = this.cleanText(this.greeting);
  }

  attachEvents() {
    const fab = document.getElementById('verity-fab');
    const chatWindow = document.getElementById('verity-chat-window');
    const sendBtn = document.getElementById('verity-send-btn');
    const input = document.getElementById('verity-input');

    const toggleChat = () => {
      const isOpen = chatWindow.classList.toggle('active');
      fab.classList.toggle('open', isOpen);
      fab.setAttribute('aria-expanded', isOpen ? 'true' : 'false');
      fab.setAttribute('aria-label', isOpen ? 'Close chat' : 'Open chat');
      if (isOpen && !this.isUnavailable) setTimeout(() => input.focus(), 250);
    };

    fab.addEventListener('click', toggleChat);
    fab.addEventListener('keydown', (event) => {
      if (event.key === 'Enter' || event.key === ' ') {
        event.preventDefault();
        toggleChat();
      }
    });
    document.addEventListener('keydown', (event) => {
      if (event.key === 'Escape' && chatWindow.classList.contains('active')) toggleChat();
    });

    sendBtn.addEventListener('click', () => this.handleSend());
    input.addEventListener('keydown', (e) => {
      if (e.key === 'Enter') this.handleSend();
    });
  }

  async handleSend() {
    if (this.isSending || this.isUnavailable) return;

    const input = document.getElementById('verity-input');
    const sendBtn = document.getElementById('verity-send-btn');
    const typing = document.getElementById('verity-typing');
    const message = input.value.trim();
    if (!message) return;

    this.isSending = true;
    sendBtn.disabled = true;
    this.appendMessage('user', message);
    input.value = '';
    typing.classList.add('active');
    this.scrollToBottom();

    try {
      const body = new URLSearchParams();
      body.set('tenant_id', this.tenantId);
      body.set('message', message);
      if (this.sessionId) body.set('session_id', this.sessionId);

      const response = await fetch(this.apiUrl, { method: 'POST', headers: { 'Accept': 'application/json' }, body });
      if (!response.ok) {
        this.appendMessage('ai', 'This chat is not available from this website at the moment.');
        return;
      }

      const data = await response.json();
      if (data.message && data.message.success) {
        this.saveSession(data.message.session_id);
        this.appendMessage('ai', data.message.reply);
      } else {
        this.appendMessage('ai', 'I am unable to respond right now. Please try again shortly.');
        console.error('Verity AI Error:', data);
      }
    } catch (error) {
      this.appendMessage('ai', 'Connection issue. Please try again in a moment.');
      console.error('Verity AI Network Error:', error);
    } finally {
      typing.classList.remove('active');
      sendBtn.disabled = false;
      this.isSending = false;
      input.focus();
    }
  }

  cleanText(text) {
    return String(text || '')
      .replace(/\*\*(.*?)\*\*/g, '$1')
      .replace(/__(.*?)__/g, '$1')
      .replace(/(?!^)[ \t]+([-*][ \t]+)/gm, '\n\n$1')
      .replace(/^\s*[-*]\s+/gm, '- ')
      .replace(/\n(- )/g, '\n\n$1')
      .replace(/(?!^)[ \t]+(\d+\.\s+)/gm, '\n\n$1')
      .replace(/\n(\d+\.\s+)/g, '\n\n$1')
      .replace(/\n{3,}/g, '\n\n')
      .trim();
  }

  appendMessage(role, text, options = {}) {
    const messagesContainer = document.getElementById('verity-messages');
    const typing = document.getElementById('verity-typing');
    const msgDiv = document.createElement('div');

    msgDiv.className = `verity-message ${role}`;
    const content = this.cleanText(text);
    const filePattern = /(\/(?:private\/)?files\/[^\s,]+)/g;
    let lastIndex = 0;
    let match;

    while ((match = filePattern.exec(content)) !== null) {
      if (match.index > lastIndex) {
        msgDiv.appendChild(document.createTextNode(content.slice(lastIndex, match.index)));
      }
      const link = document.createElement('a');
      const filePath = match[1].replace(/[\]).,;:]+$/g, '');
      link.href = `${this.host}${filePath}`;
      link.className = 'verity-download-btn';
      link.textContent = `Download ${filePath.split('/').pop()}`;
      link.target = '_blank';
      link.rel = 'noopener';
      link.setAttribute('download', '');
      msgDiv.appendChild(link);
      lastIndex = match.index + filePath.length;
    }
    if (lastIndex < content.length) {
      msgDiv.appendChild(document.createTextNode(content.slice(lastIndex)));
    }
    if (!content) msgDiv.textContent = '';
    if (options.greeting) msgDiv.dataset.greeting = 'true';
    if (options.status) msgDiv.dataset.status = options.status;
    messagesContainer.insertBefore(msgDiv, typing);
    this.scrollToBottom();
  }

  scrollToBottom() {
    const messagesContainer = document.getElementById('verity-messages');
    messagesContainer.scrollTop = messagesContainer.scrollHeight;
  }
}

function initVerityAI() {
  const scripts = document.getElementsByTagName('script');
  for (let script of scripts) {
    if (script.src.includes('widget.js') && script.getAttribute('data-tenant-id')) {
      if (!window.verityAI) window.verityAI = new VerityAIWidget();
      break;
    }
  }
}

if (document.readyState === 'loading') {
  document.addEventListener('DOMContentLoaded', initVerityAI);
} else {
  initVerityAI();
}
