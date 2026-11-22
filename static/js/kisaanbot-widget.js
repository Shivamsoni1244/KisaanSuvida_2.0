/**
 * static/js/kisaanbot-widget.js - Standalone & Embeddable KisaanBot AI Assistant
 * Compatible with in-app floating usage and external website embed scripts.
 */

(function () {
  // Read script configuration attributes
  const currentScript = document.currentScript || (function () {
    const scripts = document.getElementsByTagName('script');
    return scripts[scripts.length - 1];
  })();

  const apiUrl = (currentScript && currentScript.getAttribute('data-api-url')) || '/api/kisaanbot/chat';
  let widgetLanguage = (currentScript && currentScript.getAttribute('data-language')) || 'en';

  // Inject DOM elements if not already present on page (for external embeds)
  function ensureWidgetDOM() {
    if (document.getElementById('ksBotLauncher')) {
      return; // Already present in DOM
    }

    // Floating launcher button
    const launcher = document.createElement('div');
    launcher.id = 'ksBotLauncher';
    launcher.className = 'ks-bot-launcher';
    launcher.title = 'Ask KisaanBot AI';
    launcher.onclick = toggleKisaanBot;
    launcher.innerHTML = `
      <div class="ks-bot-launcher-pulse"></div>
      <svg width="28" height="28" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
        <path d="M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2z"></path>
        <circle cx="9" cy="10" r="1" fill="currentColor"></circle>
        <circle cx="15" cy="10" r="1" fill="currentColor"></circle>
      </svg>
      <div class="ks-bot-tooltip">Ask KisaanBot AI</div>
    `;

    // Chat Window
    const win = document.createElement('div');
    win.id = 'ksBotWindow';
    win.className = 'ks-bot-window';
    win.innerHTML = `
      <div class="ks-bot-header">
        <div class="ks-bot-header-info">
          <div class="ks-bot-avatar">🌾</div>
          <div class="ks-bot-title-group">
            <h3>KisaanBot</h3>
            <span>Online • AI Assistant</span>
          </div>
        </div>
        <div class="ks-bot-actions">
          <select class="ks-bot-lang-select" id="widgetLangSelect" onchange="changeWidgetLanguage(this.value)">
            <option value="en">English</option>
            <option value="hi">हिन्दी</option>
            <option value="hinglish">Hinglish</option>
          </select>
          <button class="ks-bot-close-btn" onclick="toggleKisaanBot()" aria-label="Close chat">×</button>
        </div>
      </div>
      <div class="ks-bot-messages" id="widgetMessages">
        <div class="msg-wrapper bot">
          <div class="msg-bubble">
            Namaste! I am KisaanBot, your agricultural AI assistant. How can I help your farm today?
          </div>
          <span class="msg-time">Just now</span>
        </div>
      </div>
      <div class="ks-bot-chips" id="widgetChips">
        <button class="ks-bot-chip" onclick="sendWidgetChip('Why was rice recommended for my farm?')">Why rice?</button>
        <button class="ks-bot-chip" onclick="sendWidgetChip('How much water does rice need?')">Water needs</button>
        <button class="ks-bot-chip" onclick="sendWidgetChip('What does my soil pH mean?')">Soil pH</button>
        <button class="ks-bot-chip" onclick="sendWidgetChip('Which schemes can help me?')">Govt Schemes</button>
      </div>
      <div class="ks-bot-input-bar">
        <input type="text" class="ks-bot-input" id="widgetInput" placeholder="Ask about crops, soil, pests..." onkeydown="handleWidgetKeyDown(event)">
        <button class="ks-bot-icon-btn" id="widgetMicBtn" onclick="toggleSpeechRecognition()" title="Voice input">
          <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M12 1a3 3 0 0 0-3 3v8a3 3 0 0 0 6 0V4a3 3 0 0 0-3-3z"></path><path d="M19 10v2a7 7 0 0 1-14 0v-2"></path><line x1="12" y1="19" x2="12" y2="23"></line><line x1="8" y1="23" x2="16" y2="23"></line></svg>
        </button>
        <button class="ks-bot-send-btn" onclick="sendWidgetMessage()" title="Send">
          <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5"><line x1="22" y1="2" x2="11" y2="13"></line><polygon points="22 2 15 22 11 13 2 9 22 2"></polygon></svg>
        </button>
      </div>
    `;

    document.body.appendChild(launcher);
    document.body.appendChild(win);
  }

  // Toggle Chat Window
  window.toggleKisaanBot = function () {
    const win = document.getElementById('ksBotWindow');
    if (win) {
      win.classList.toggle('active');
      if (win.classList.contains('active')) {
        const inp = document.getElementById('widgetInput');
        if (inp) inp.focus();
      }
    }
  };

  // Change language in floating assistant
  window.changeWidgetLanguage = function (lang) {
    widgetLanguage = lang;
    const chipsContainer = document.getElementById('widgetChips');
    if (!chipsContainer) return;

    if (lang === 'hi') {
      chipsContainer.innerHTML = `
        <button class="ks-bot-chip" onclick="sendWidgetChip('धान के लिए पानी की कितनी आवश्यकता है?')">पानी की आवश्यकता</button>
        <button class="ks-bot-chip" onclick="sendWidgetChip('मेरी मिट्टी का pH क्या दर्शाता है?')">मिट्टी का pH</button>
        <button class="ks-bot-chip" onclick="sendWidgetChip('कौन सी सरकारी योजनाएं मेरे लिए हैं?')">सरकारी योजनाएं</button>
        <button class="ks-bot-chip" onclick="sendWidgetChip('झुलसा रोग से धान को कैसे बचाएं?')">रोग उपचार</button>
      `;
    } else if (lang === 'hinglish') {
      chipsContainer.innerHTML = `
        <button class="ks-bot-chip" onclick="sendWidgetChip('Rice ke liye kitna pani chahiye?')">Water needs</button>
        <button class="ks-bot-chip" onclick="sendWidgetChip('Mera soil pH kaisa hai?')">Soil pH</button>
        <button class="ks-bot-chip" onclick="sendWidgetChip('Konsi schemes mere kaam ki hain?')">Govt Schemes</button>
        <button class="ks-bot-chip" onclick="sendWidgetChip('Paddy mein blast disease ka spray batao')">Spray Dawai</button>
      `;
    } else {
      chipsContainer.innerHTML = `
        <button class="ks-bot-chip" onclick="sendWidgetChip('Why was rice recommended for my farm?')">Why rice?</button>
        <button class="ks-bot-chip" onclick="sendWidgetChip('How much water does rice need?')">Water needs</button>
        <button class="ks-bot-chip" onclick="sendWidgetChip('What does my soil pH mean?')">Soil pH</button>
        <button class="ks-bot-chip" onclick="sendWidgetChip('Which schemes can help me?')">Govt Schemes</button>
      `;
    }
  };

  window.handleWidgetKeyDown = function (event) {
    if (event.key === 'Enter') {
      sendWidgetMessage();
    }
  };

  window.sendWidgetChip = function (promptText) {
    const input = document.getElementById('widgetInput');
    if (input) {
      input.value = promptText;
      sendWidgetMessage();
    }
  };

  window.sendWidgetMessage = function () {
    const input = document.getElementById('widgetInput');
    const msg = input ? input.value.trim() : '';
    if (!msg) return;

    const messages = document.getElementById('widgetMessages');
    if (!messages) return;

    // Append user bubble
    const userDiv = document.createElement('div');
    userDiv.className = 'msg-wrapper user';
    userDiv.innerHTML = `
      <div class="msg-bubble">${escapeHtml(msg)}</div>
      <span class="msg-time">Just now</span>
    `;
    messages.appendChild(userDiv);
    input.value = '';
    messages.scrollTop = messages.scrollHeight;

    // Loading status
    const botLoading = document.createElement('div');
    botLoading.className = 'msg-wrapper bot';
    botLoading.id = 'widgetLoadingBubble';
    botLoading.innerHTML = `
      <div class="msg-bubble" style="color: var(--color-text-light);">Thinking...</div>
    `;
    messages.appendChild(botLoading);
    messages.scrollTop = messages.scrollHeight;

    // Request to Flask backend
    fetch(apiUrl, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ message: msg, language: widgetLanguage })
    })
      .then(res => res.json())
      .then(data => {
        const loading = document.getElementById('widgetLoadingBubble');
        if (loading) loading.remove();

        if (data.success) {
          const botDiv = document.createElement('div');
          botDiv.className = 'msg-wrapper bot';
          botDiv.innerHTML = `
            <div class="msg-bubble">${formatBotMarkdown(data.reply)}</div>
            <span class="msg-time">Just now</span>
          `;
          messages.appendChild(botDiv);
          messages.scrollTop = messages.scrollHeight;
        }
      })
      .catch(err => {
        const loading = document.getElementById('widgetLoadingBubble');
        if (loading) loading.remove();
        console.error('KisaanBot chat error:', err);
      });
  };

  // Web Speech API Voice Recognition
  window.toggleSpeechRecognition = function () {
    if (!('webkitSpeechRecognition' in window) && !('SpeechRecognition' in window)) {
      alert('Speech recognition is not supported in this browser. Please type your message.');
      return;
    }
    const SpeechRecognition = window.SpeechRecognition || window.webkitSpeechRecognition;
    const recognition = new SpeechRecognition();
    recognition.lang = widgetLanguage === 'hi' ? 'hi-IN' : 'en-IN';

    const micBtn = document.getElementById('widgetMicBtn');
    if (micBtn) micBtn.classList.add('recording');

    recognition.onresult = (event) => {
      const transcript = event.results[0][0].transcript;
      const input = document.getElementById('widgetInput');
      if (input) input.value = transcript;
      if (micBtn) micBtn.classList.remove('recording');
      sendWidgetMessage();
    };

    recognition.onerror = () => {
      if (micBtn) micBtn.classList.remove('recording');
    };

    recognition.onend = () => {
      if (micBtn) micBtn.classList.remove('recording');
    };

    recognition.start();
  };

  function formatBotMarkdown(text) {
    return text
      .replace(/\*\*(.*?)\*\*/g, '<strong>$1</strong>')
      .replace(/\*(.*?)\*/g, '<em>$1</em>')
      .replace(/\n\n/g, '<br><br>')
      .replace(/\n/g, '<br>');
  }

  function escapeHtml(str) {
    return str.replace(/[&<>'"]/g, tag => ({
      '&': '&amp;', '<': '&lt;', '>': '&gt;', "'": '&#39;', '"': '&quot;'
    }[tag] || tag));
  }

  // Ensure DOM is ready and initialized
  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', ensureWidgetDOM);
  } else {
    ensureWidgetDOM();
  }

  // Global developer API
  window.KisaanBotWidget = {
    open: function () {
      const win = document.getElementById('ksBotWindow');
      if (win) win.classList.add('active');
    },
    close: function () {
      const win = document.getElementById('ksBotWindow');
      if (win) win.classList.remove('active');
    },
    toggle: toggleKisaanBot,
    sendMessage: function (msg, lang) {
      if (lang) widgetLanguage = lang;
      const input = document.getElementById('widgetInput');
      if (input) input.value = msg;
      sendWidgetMessage();
    }
  };
})();
