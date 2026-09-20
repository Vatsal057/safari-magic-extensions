/**
 * Safari Magic Gallery — Retro Pixel Art Application Logic
 */

// State
let extensions = [];
let activeCategory = 'all';
let featuredExtension = null;

// DOM Elements
const heroBox = document.getElementById('hero-box');
const heroArt = document.getElementById('hero-art');
const bentoGrid = document.getElementById('bento-cards-grid');
const ribbonButtons = document.querySelectorAll('.ribbon-icon-btn');
const toastEl = document.getElementById('toast');

// Featured Card Elements
const featuredImg = document.getElementById('featured-img');
const featuredCreator = document.getElementById('featured-creator');
const featuredTitle = document.getElementById('featured-title');
const featuredSaveBtn = document.getElementById('featured-save-btn');
const featuredInspectBtn = document.getElementById('featured-inspect-btn');
const featuredHeartBtn = document.getElementById('featured-heart-btn');

// Inspector Modal Elements
const inspectorModal = document.getElementById('inspector-modal');
const closeInspectorBtn = document.getElementById('close-inspector-btn');
const modalTitle = document.getElementById('modal-title');
const modalAuthor = document.getElementById('modal-author');
const modalCategory = document.getElementById('modal-category');
const modalImg = document.getElementById('modal-img');
const modalDescription = document.getElementById('modal-description');
const modalPrompt = document.getElementById('modal-prompt');
const modalCliCmd = document.getElementById('modal-cli-cmd');
const modalDownloadPkgBtn = document.getElementById('modal-download-pkg-btn');
const copyModalPromptBtn = document.getElementById('copy-modal-prompt-btn');
const copyModalCliBtn = document.getElementById('copy-modal-cli-btn');

// Submit Modal Elements
const submitModal = document.getElementById('submit-modal');
const openSubmitModalBtn = document.getElementById('open-submit-modal-btn');
const heroBecomeAuthorBtn = document.getElementById('hero-become-author-btn');
const closeSubmitBtn = document.getElementById('close-submit-btn');

// Copy Quick CLI Command
const copyCliCommandBtn = document.getElementById('copy-cli-command-btn');

/**
 * Fallback static data if fetching local file fails
 */
const fallbackData = [
  {
    id: "night-meadow",
    name: "Night Meadow New Tab",
    author: "vatsal",
    category: "nature",
    art_image: "assets/night_meadow.jpg",
    description: "A beautiful, premium 2D illustrated night ecosystem that feels calm, natural, and alive on the new tab page.",
    prompt: "Build a beautiful, premium 2D illustrated night ecosystem that feels calm, natural, and alive on the new tab page.",
    download_url: "packages/Night_Meadow_New_Tab.magicext",
    likes: 342
  },
  {
    id: "zen-focus",
    name: "Zen Focus & Timer",
    author: "community",
    category: "focus",
    art_image: "assets/zen_pagoda.jpg",
    description: "Distraction-free Pomodoro timer and daily intentions board with ambient lo-fi soundscapes.",
    prompt: "Create a peaceful Zen focus new tab page with a customizable 25-minute Pomodoro timer, minimal daily intention list, and calming background gradients.",
    download_url: "packages/Zen_Focus_Timer.magicext",
    likes: 289
  },
  {
    id: "nightlife-wild",
    name: "Nightlife in the Wild",
    author: "vatsal",
    category: "ambient",
    art_image: "assets/hero_cyberpunk.jpg",
    description: "Transforms your Safari new tab into an ambient, interactive day/night cycle with rain and neon animations.",
    prompt: "Create Nightlife 24B7; make it day time; revert",
    download_url: "packages/Nightlife_in_the_Wild.magicext",
    likes: 418
  },
  {
    id: "night-garden",
    name: "Night Garden Tab",
    author: "vatsal",
    category: "nature",
    art_image: "assets/art_night_garden.svg",
    description: "Draws a different flower and starry night silhouette every time you open a new tab.",
    prompt: "Every time I open a new tab, draw me a different flower; there shoydl be trees and all as well. and it sholud be night time, so stars and moon and all. ; no green trees. or grass. it should be liek a shadow. and the stars and moon should be moving at their own speed. and make the trees and flowers look natural.",
    download_url: "packages/Night_Garden_Tab.magicext",
    likes: 194
  },
  {
    id: "hackernews-minimal",
    name: "Hacker News Minimal",
    author: "community",
    category: "tech",
    art_image: "assets/art_hackernews.svg",
    description: "Clean, ultra-fast Hacker News top stories reader directly in your Safari new tab.",
    prompt: "Create a modern minimalist Hacker News top stories reader for new tab with dark mode, score badges, and direct discussion links.",
    download_url: "packages/Hacker_News_Minimal.magicext",
    likes: 256
  },
  {
    id: "chitchat-automator",
    name: "Chitchat.gg Automator",
    author: "vatsal",
    category: "tech",
    art_image: "assets/art_chitchat.svg",
    description: "Automated chat interactions and assistant for web discussions.",
    prompt: "Build an automated companion helper for chitchat with keyboard triggers and dark styling.",
    download_url: "packages/Night_Meadow_New_Tab.magicext",
    likes: 173
  }
];

/**
 * Initialize Gallery
 */
async function initGallery() {
  try {
    const res = await fetch('community_registry.json');
    if (res.ok) {
      const data = await res.json();
      extensions = (data.extensions && data.extensions.length > 0) ? data.extensions : fallbackData;
    } else {
      extensions = fallbackData;
    }
  } catch (e) {
    extensions = fallbackData;
  }

  // Ensure each extension has an art image & category
  extensions = extensions.map((item, idx) => {
    let art = item.art_image;
    let cat = "ambient";
    const nameLow = item.name.toLowerCase();

    if (nameLow.includes('meadow')) {
      art = "assets/night_meadow.jpg";
      cat = "nature";
    } else if (nameLow.includes('zen') || nameLow.includes('timer')) {
      art = "assets/zen_pagoda.jpg";
      cat = "focus";
    } else if (nameLow.includes('garden')) {
      art = "assets/art_night_garden.svg";
      cat = "nature";
    } else if (nameLow.includes('hacker')) {
      art = "assets/art_hackernews.svg";
      cat = "tech";
    } else if (nameLow.includes('chit') || nameLow.includes('auto')) {
      art = "assets/art_chitchat.svg";
      cat = "tech";
    } else {
      art = "assets/hero_cyberpunk.jpg";
      cat = "ambient";
    }

    return {
      ...item,
      art_image: art,
      category: cat,
      likes: item.likes || (180 + (idx * 37))
    };
  });

  // Pick first or Night Meadow as featured
  featuredExtension = extensions.find(e => e.name.toLowerCase().includes('meadow')) || extensions[0];
  setupFeaturedCard(featuredExtension);

  renderBentoGrid();
  setupEventListeners();
}

/**
 * Setup Featured Card
 */
function setupFeaturedCard(ext) {
  if (!ext) return;
  featuredExtension = ext;
  featuredImg.src = ext.art_image;
  featuredImg.alt = ext.name;
  featuredCreator.textContent = ext.author ? `@${ext.author}` : "community";
  featuredTitle.textContent = ext.name;
  featuredSaveBtn.href = ext.download_url;

  featuredInspectBtn.onclick = () => openInspector(ext);
  featuredImg.onclick = () => openInspector(ext);
  featuredImg.style.cursor = 'pointer';
}

/**
 * Render Bento Grid
 */
function renderBentoGrid() {
  const filtered = extensions.filter(ext => {
    if (activeCategory === 'all') return true;
    if (activeCategory === 'nature') return ext.category === 'nature' || (ext.tags || []).includes('ambient');
    if (activeCategory === 'focus') return ext.category === 'focus';
    if (activeCategory === 'newtab') return (ext.tags || []).includes('newtab');
    if (activeCategory === 'tech') return ext.category === 'tech';
    return true;
  });

  // Display up to 6 cards in the right grid
  bentoGrid.innerHTML = filtered.slice(0, 6).map(ext => `
    <div class="grid-card-item" data-id="${ext.id}">
      <img src="${ext.art_image}" alt="${escapeHTML(ext.name)}" class="grid-card-thumb" loading="lazy">
      <div class="grid-card-overlay">
        <div class="grid-card-title">${escapeHTML(ext.name)}</div>
        <div class="grid-card-author">by @${escapeHTML(ext.author || 'community')}</div>
      </div>
    </div>
  `).join('');

  // Attach card click handlers
  bentoGrid.querySelectorAll('.grid-card-item').forEach(card => {
    card.addEventListener('click', () => {
      const id = card.getAttribute('data-id');
      const item = extensions.find(e => e.id === id);
      if (item) openInspector(item);
    });
  });
}

/**
 * Open Inspector Modal
 */
function openInspector(ext) {
  modalTitle.textContent = ext.name;
  modalAuthor.textContent = `crafted by @${ext.author || 'community'}`;
  modalCategory.textContent = (ext.category || 'EXTENSION').toUpperCase();
  modalImg.src = ext.art_image;
  modalImg.alt = ext.name;
  modalDescription.textContent = ext.description || "Safari AI Magic Extension";
  modalPrompt.textContent = ext.prompt ? `"${ext.prompt}"` : '"No AI prompt provided."';

  const cleanId = ext.id.toLowerCase().replace(/[^a-z0-9_-]/g, '');
  const cliCommand = `safari-magic-ext install ${cleanId}`;
  modalCliCmd.textContent = cliCommand;

  modalDownloadPkgBtn.href = ext.download_url;
  modalDownloadPkgBtn.download = ext.download_url.split('/').pop() || `${ext.name}.magicext`;

  copyModalPromptBtn.onclick = () => copyText(ext.prompt, "AI Prompt copied! Paste in Safari to remix.");
  copyModalCliBtn.onclick = () => copyText(cliCommand, "CLI install command copied!");

  inspectorModal.classList.remove('hidden');
}

/**
 * Event Listeners
 */
function setupEventListeners() {
  // Category Ribbon filtering
  ribbonButtons.forEach(btn => {
    btn.addEventListener('click', () => {
      ribbonButtons.forEach(b => b.classList.remove('active'));
      btn.classList.add('active');
      activeCategory = btn.getAttribute('data-filter') || 'all';
      renderBentoGrid();
    });
  });

  // Heart toggle
  if (featuredHeartBtn) {
    featuredHeartBtn.addEventListener('click', () => {
      featuredHeartBtn.classList.toggle('liked');
      if (featuredHeartBtn.classList.contains('liked')) {
        showToast("Added to favorites! ❤️");
      }
    });
  }

  // Quick CLI command copy
  if (copyCliCommandBtn) {
    copyCliCommandBtn.addEventListener('click', () => {
      copyText('safari-magic-ext install night-meadow', 'Terminal command copied!');
    });
  }

  // Modals
  closeInspectorBtn.addEventListener('click', () => inspectorModal.classList.add('hidden'));
  inspectorModal.addEventListener('click', (e) => {
    if (e.target === inspectorModal) inspectorModal.classList.add('hidden');
  });

  const openSubmit = () => submitModal.classList.remove('hidden');
  const closeSubmit = () => submitModal.classList.add('hidden');

  if (openSubmitModalBtn) openSubmitModalBtn.addEventListener('click', openSubmit);
  if (heroBecomeAuthorBtn) heroBecomeAuthorBtn.addEventListener('click', openSubmit);
  if (closeSubmitBtn) closeSubmitBtn.addEventListener('click', closeSubmit);
  submitModal.addEventListener('click', (e) => {
    if (e.target === submitModal) closeSubmit();
  });

  document.addEventListener('keydown', (e) => {
    if (e.key === 'Escape') {
      inspectorModal.classList.add('hidden');
      submitModal.classList.add('hidden');
    }
  });
}

/**
 * Copy Helper & Toast
 */
function copyText(text, successMsg) {
  if (!text) return;
  navigator.clipboard.writeText(text).then(() => {
    showToast(successMsg || "Copied to clipboard!");
  }).catch(() => {
    // Fallback
    const ta = document.createElement('textarea');
    ta.value = text;
    document.body.appendChild(ta);
    ta.select();
    document.execCommand('copy');
    document.body.removeChild(ta);
    showToast(successMsg || "Copied to clipboard!");
  });
}

function showToast(msg) {
  toastEl.textContent = msg;
  toastEl.classList.remove('hidden');
  setTimeout(() => {
    toastEl.classList.add('hidden');
  }, 2200);
}

function escapeHTML(str) {
  if (!str) return '';
  return str.replace(/&/g, '&amp;')
            .replace(/</g, '&lt;')
            .replace(/>/g, '&gt;')
            .replace(/"/g, '&quot;');
}

// Bootstrap
document.addEventListener('DOMContentLoaded', initGallery);
