/**
 * Safari Magic Hub — Frontend Application Logic
 */

// Global state
let allExtensions = [];
let activeTag = 'all';
let searchQuery = '';

// DOM Elements
const cardsGrid = document.getElementById('cards-grid');
const catalogStatus = document.getElementById('catalog-status');
const searchInput = document.getElementById('search-input');
const clearSearchBtn = document.getElementById('clear-search-btn');
const filterTags = document.getElementById('filter-tags');
const toastEl = document.getElementById('toast');
const submitModal = document.getElementById('submit-modal');
const openSubmitModalBtn = document.getElementById('open-submit-modal-btn');
const closeModalBtn = document.getElementById('close-modal-btn');
const copyCliHelpBtn = document.getElementById('copy-cli-help-btn');

// Symbol emoji mapper for web presentation
const symbolMap = {
  'moon.stars.fill': '🌙',
  'leaf.fill': '🌿',
  'bubble.left.and.bubble.right.fill': '💬',
  'newspaper.fill': '📰',
  'sparkles': '✨',
  'puzzlepiece.extension': '🧩',
  'star.fill': '⭐'
};

/**
 * Fetch registry JSON
 */
async function loadCatalog() {
  const sources = [
    'community_registry.json',
    '../community_registry.json'
  ];

  let data = null;
  for (const src of sources) {
    try {
      const res = await fetch(src);
      if (res.ok) {
        data = await res.json();
        break;
      }
    } catch (e) {
      // Continue to next source
    }
  }

  // Fallback embedded data if file:// protocol blocks local fetch
  if (!data) {
    data = {
      extensions: [
        {
          id: "nightlife-wild",
          name: "Nightlife in the Wild",
          author: "vatsal",
          version: "1.0",
          description: "Transforms your Safari new tab into an ambient, interactive day/night cycle with animations.",
          prompt: "Create Nightlife 24B7; make it day time; revert",
          selected_symbol: "moon.stars.fill",
          symbol_color_name: "purple",
          tags: ["ambient", "newtab", "design"],
          download_url: "../packages/Nightlife_in_the_Wild.magicext"
        },
        {
          id: "night-meadow",
          name: "Night Meadow New Tab",
          author: "vatsal",
          version: "1.0",
          description: "A beautiful, premium 2D illustrated night ecosystem that feels calm, natural, and alive on the new tab page.",
          prompt: "Build a beautiful, premium 2D illustrated night ecosystem that feels calm, natural, and alive on the new tab page.",
          selected_symbol: "moon.stars.fill",
          symbol_color_name: "blue",
          tags: ["nature", "ambient", "art", "newtab"],
          download_url: "../packages/Night_Meadow_New_Tab.magicext"
        },
        {
          id: "night-garden",
          name: "Night Garden Tab",
          author: "vatsal",
          version: "1.0",
          description: "Procedurally draws a different botanical flower silhouette every time you open a new tab under drifting stars.",
          prompt: "Every time I open a new tab, draw me a different flower; there shoydl be trees and all as well. and it sholud be night time, so stars and moon and all. ; no green trees. or grass. it should be liek a shadow. and the stars and moon should be moving at their own speed. and make the trees and flowers look natural.",
          selected_symbol: "leaf.fill",
          symbol_color_name: "blue",
          tags: ["botany", "generative", "stars", "minimalist"],
          download_url: "../packages/Night_Garden_Tab.magicext"
        },
        {
          id: "hackernews-minimal",
          name: "Hacker News Minimal",
          author: "community",
          version: "1.0",
          description: "Clean, ultra-fast Hacker News top stories reader directly in your Safari new tab.",
          prompt: "Create a modern minimalist Hacker News top stories reader for new tab with dark mode, score badges, and direct discussion links.",
          selected_symbol: "newspaper.fill",
          symbol_color_name: "orange",
          tags: ["news", "tech", "minimalist"],
          download_url: "https://raw.githubusercontent.com/vatsal/safari-magic-extensions-hub/main/packages/hackernews-minimal.magicext"
        },
        {
          id: "zen-focus-tab",
          name: "Zen Focus & Timer",
          author: "community",
          version: "1.1",
          description: "Distraction-free Pomodoro timer and daily intentions board with ambient lo-fi soundscapes.",
          prompt: "Create a peaceful Zen focus new tab page with a customizable 25-minute Pomodoro timer, minimal daily intention list, and calming background gradients.",
          selected_symbol: "sparkles",
          symbol_color_name: "blue",
          tags: ["focus", "pomodoro", "productivity"],
          download_url: "https://raw.githubusercontent.com/vatsal/safari-magic-extensions-hub/main/packages/zen-focus-tab.magicext"
        }
      ]
    };
  }

  allExtensions = data.extensions || [];
  renderCatalog();
}

/**
 * Filter & Render Cards
 */
function renderCatalog() {
  const query = searchQuery.toLowerCase().trim();

  const filtered = allExtensions.filter(ext => {
    // Tag filter
    if (activeTag !== 'all') {
      const tags = (ext.tags || []).map(t => t.toLowerCase());
      if (!tags.includes(activeTag)) return false;
    }

    // Text search
    if (query) {
      const haystack = [
        ext.name,
        ext.description,
        ext.prompt,
        ext.author,
        ...(ext.tags || [])
      ].join(' ').toLowerCase();
      if (!haystack.includes(query)) return false;
    }

    return true;
  });

  catalogStatus.textContent = `Showing ${filtered.length} extension${filtered.length === 1 ? '' : 's'}`;

  if (filtered.length === 0) {
    cardsGrid.innerHTML = `
      <div class="empty-state" style="grid-column: 1/-1; text-align: center; padding: 48px 0; color: var(--text-muted);">
        <p style="font-size: 18px; margin-bottom: 8px;">No extensions found matching your filter.</p>
        <button class="btn btn-ghost" onclick="resetFilters()">Reset Filters</button>
      </div>
    `;
    return;
  }

  cardsGrid.innerHTML = filtered.map(ext => createCardHTML(ext)).join('');

  // Attach card event listeners
  document.querySelectorAll('.btn-copy-prompt').forEach(btn => {
    btn.addEventListener('click', (e) => {
      const promptText = e.currentTarget.getAttribute('data-prompt');
      copyToClipboard(promptText, 'Prompt copied! Paste it in Safari to remix.');
    });
  });

  document.querySelectorAll('.btn-copy-cli').forEach(btn => {
    btn.addEventListener('click', (e) => {
      const cmd = e.currentTarget.getAttribute('data-cmd');
      copyToClipboard(cmd, 'CLI command copied!');
    });
  });
}

/**
 * Generate Card HTML
 */
function createCardHTML(ext) {
  const emoji = symbolMap[ext.selected_symbol] || '🧩';
  const color = ext.symbol_color_name || 'blue';
  const tagsHTML = (ext.tags || []).slice(0, 2).map(t => `<span class="badge-tag">#${escapeHTML(t)}</span>`).join(' ');
  const cliCmd = `safari-magic-ext install ${ext.id}`;

  return `
    <div class="ext-card" id="ext-${escapeHTML(ext.id)}">
      <div class="card-top">
        <div class="card-identity">
          <div class="symbol-badge ${escapeHTML(color)}" title="${escapeHTML(ext.selected_symbol)}">
            ${emoji}
          </div>
          <div class="card-title-group">
            <h3>${escapeHTML(ext.name)}</h3>
            <div class="card-author">by <strong>@${escapeHTML(ext.author || 'community')}</strong></div>
          </div>
        </div>
        <div>${tagsHTML}</div>
      </div>

      <p class="card-desc">${escapeHTML(ext.description || '')}</p>

      <div class="card-prompt-box">
        <div class="prompt-header">
          <span>AI Generation Prompt</span>
          <button class="btn-copy-mini btn-copy-prompt" data-prompt="${escapeAttr(ext.prompt || '')}">
            <span>Copy</span>
          </button>
        </div>
        <p class="prompt-text">"${escapeHTML(ext.prompt || '')}"</p>
      </div>

      <div class="card-actions">
        <a href="${escapeAttr(ext.download_url || '#')}" download class="btn-card btn-card-install">
          <span>⬇ Download .magicext</span>
        </a>
        <button class="btn-card btn-card-prompt btn-copy-cli" data-cmd="${escapeAttr(cliCmd)}" title="Copy install command for terminal">
          <span>Terminal</span>
        </button>
      </div>
    </div>
  `;
}

/**
 * Clipboard Toast Helper
 */
function copyToClipboard(text, message) {
  if (navigator.clipboard) {
    navigator.clipboard.writeText(text).then(() => showToast(message));
  } else {
    const input = document.createElement('textarea');
    input.value = text;
    document.body.appendChild(input);
    input.select();
    document.execCommand('copy');
    document.body.removeChild(input);
    showToast(message);
  }
}

function showToast(msg) {
  toastEl.textContent = msg;
  toastEl.classList.remove('hidden');
  setTimeout(() => toastEl.classList.add('hidden'), 2800);
}

function resetFilters() {
  searchInput.value = '';
  searchQuery = '';
  clearSearchBtn.classList.add('hidden');
  activeTag = 'all';
  document.querySelectorAll('.tag-chip').forEach(c => c.classList.remove('active'));
  document.querySelector('.tag-chip[data-tag="all"]').classList.add('active');
  renderCatalog();
}

function escapeHTML(str) {
  return String(str || '').replace(/[&<>'"]/g, 
    tag => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', "'": '&#39;', '"': '&quot;' }[tag] || tag)
  );
}

function escapeAttr(str) {
  return String(str || '').replace(/"/g, '&quot;');
}

// Event Listeners
searchInput.addEventListener('input', (e) => {
  searchQuery = e.target.value;
  clearSearchBtn.classList.toggle('hidden', !searchQuery);
  renderCatalog();
});

clearSearchBtn.addEventListener('click', () => {
  searchInput.value = '';
  searchQuery = '';
  clearSearchBtn.classList.add('hidden');
  renderCatalog();
});

filterTags.addEventListener('click', (e) => {
  const chip = e.target.closest('.tag-chip');
  if (!chip) return;
  document.querySelectorAll('.tag-chip').forEach(c => c.classList.remove('active'));
  chip.classList.add('active');
  activeTag = chip.getAttribute('data-tag');
  renderCatalog();
});

copyCliHelpBtn.addEventListener('click', () => {
  copyToClipboard('safari-magic-ext install <extension-id>', 'CLI syntax copied to clipboard!');
});

// Modal Logic
openSubmitModalBtn.addEventListener('click', () => submitModal.classList.remove('hidden'));
closeModalBtn.addEventListener('click', () => submitModal.classList.add('hidden'));
submitModal.addEventListener('click', (e) => {
  if (e.target === submitModal) submitModal.classList.add('hidden');
});

// Modal Tabs
document.querySelectorAll('.modal-tab').forEach(tab => {
  tab.addEventListener('click', (e) => {
    document.querySelectorAll('.modal-tab').forEach(t => t.classList.remove('active'));
    document.querySelectorAll('.tab-pane').forEach(p => p.classList.add('hidden'));
    tab.classList.add('active');
    const paneId = `pane-${tab.getAttribute('data-tab')}`;
    document.getElementById(paneId).classList.remove('hidden');
  });
});

// Initialize
window.addEventListener('DOMContentLoaded', loadCatalog);
