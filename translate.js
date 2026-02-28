/**
 * translate.js — shared translation helper for API Ninjas Hub
 *
 * Usage in any page:
 *   1. Include <script src="../js/translate.js"></script>
 *   2. Call renderTranslateBar(onTranslate) — renders the language pill bar
 *   3. onTranslate(lang) will be called with "en"|"es"|"it"|"fr" when user picks a language
 *   4. Use await translateTexts(texts, lang) to translate an array of strings
 */

const API = 'http://localhost:8000';

const LANG_LABELS = {
  en: '🇬🇧 English',
  es: '🇪🇸 Español',
  it: '🇮🇹 Italiano',
  fr: '🇫🇷 Français',
};

/**
 * Translate an array of strings via the backend.
 * Returns the same array untouched if lang === "en".
 */
async function translateTexts(texts, lang) {
  if (lang === 'en') return texts;
  const r = await fetch(`${API}/api/translate`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ texts, target: lang }),
  });
  const data = await r.json();
  return data.translations;
}

/**
 * Inject the translate bar into a container element.
 * @param {string} containerId  — id of the element where the bar will be inserted
 * @param {function} onTranslate — callback(lang: string) called on language change
 * @param {string} [activeLang] — default active language (default: "en")
 */
function renderTranslateBar(containerId, onTranslate, activeLang = 'en') {
  const el = document.getElementById(containerId);
  if (!el) return;

  el.innerHTML = `
    <div class="translate-bar">
      <span class="translate-label">🌐 Idioma</span>
      ${Object.entries(LANG_LABELS).map(([code, label]) => `
        <button
          class="lang-btn ${code === activeLang ? 'active' : ''}"
          data-lang="${code}"
          onclick="handleLangClick(this)"
        >${label}</button>
      `).join('')}
      <span class="translate-status" id="translate-status"></span>
    </div>
  `;

  // Store callback globally so onclick can reach it
  window._onTranslate = onTranslate;
}

function handleLangClick(btn) {
  document.querySelectorAll('.lang-btn').forEach(b => b.classList.remove('active'));
  btn.classList.add('active');
  const status = document.getElementById('translate-status');
  if (btn.dataset.lang !== 'en' && status) {
    status.textContent = 'Traduciendo...';
    status.style.opacity = '1';
  }
  window._onTranslate && window._onTranslate(btn.dataset.lang);
  setTimeout(() => { if (status) status.style.opacity = '0'; }, 1800);
}

/**
 * CSS for the translate bar — injected once automatically.
 */
(function injectTranslateStyles() {
  if (document.getElementById('translate-bar-styles')) return;
  const style = document.createElement('style');
  style.id = 'translate-bar-styles';
  style.textContent = `
    .translate-bar {
      display: flex;
      align-items: center;
      gap: 8px;
      flex-wrap: wrap;
      padding: 14px 20px;
      background: rgba(255,255,255,0.03);
      border: 1px solid rgba(255,255,255,0.08);
      border-radius: 100px;
      margin: 20px auto 0;
      width: fit-content;
      max-width: 100%;
    }
    .translate-label {
      font-size: 0.75rem;
      letter-spacing: 0.12em;
      text-transform: uppercase;
      opacity: 0.4;
      margin-right: 4px;
      white-space: nowrap;
    }
    .lang-btn {
      padding: 6px 16px;
      border-radius: 100px;
      border: 1px solid rgba(255,255,255,0.1);
      background: transparent;
      color: rgba(255,255,255,0.45);
      font-size: 0.8rem;
      cursor: pointer;
      transition: all 0.2s;
      white-space: nowrap;
      font-family: inherit;
    }
    .lang-btn:hover {
      border-color: rgba(255,255,255,0.3);
      color: rgba(255,255,255,0.8);
    }
    .lang-btn.active {
      background: rgba(255,255,255,0.12);
      border-color: rgba(255,255,255,0.35);
      color: #fff;
    }
    .translate-status {
      font-size: 0.75rem;
      opacity: 0;
      transition: opacity 0.3s;
      color: rgba(255,255,255,0.4);
      font-style: italic;
      margin-left: 4px;
    }
  `;
  document.head.appendChild(style);
})();
