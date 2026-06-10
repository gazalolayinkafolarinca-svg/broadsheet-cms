/* ============================================================
   THE BROADSHEET — js/app.js
   Main application — all data loaded from backend API.
   Depends on: config.js, api.js, ticker.js
   ============================================================ */

'use strict';

/* ── STATE ────────────────────────────────────────────────── */
const state = {
  categories:     [],
  articles:       [],
  pagination:     { page: 1, total_pages: 1, has_next: false },
  activeCategory: 'all',
  searchQuery:    '',
  currentPage:    1,
  bookmarks:      JSON.parse(localStorage.getItem(CONFIG.STORAGE.BOOKMARKS) || '[]'),
  darkMode:       localStorage.getItem(CONFIG.STORAGE.DARK_MODE) === 'true',
};

/* ── UTILS ────────────────────────────────────────────────── */

function catColor(cat) {
  if (!cat) return '#888';
  return cat.color || CONFIG.CAT_COLORS[cat.slug] || '#888';
}

function imgSrc(article, type = 'card') {
  const fi = article.featured_image;
  if (fi && typeof fi === 'object') {
    if (type === 'hero'  && fi.url)           return fi.url;
    if (type === 'card'  && fi.thumbnail_url) return fi.thumbnail_url;
    if (type === 'modal' && fi.url)           return fi.url;
    if (fi.url) return fi.url;
  }
  const seed = (article.id || 1) * (type === 'hero' ? CONFIG.IMG_SEED_HERO : type === 'modal' ? CONFIG.IMG_SEED_MODAL : CONFIG.IMG_SEED_CARD);
  const [w, h] = type === 'hero' ? [1000, 600] : type === 'modal' ? [1200, 630] : [600, 380];
  return `https://picsum.photos/seed/${seed}/${w}/${h}`;
}

function badge(article, light = true) {
  const cat = article.category;
  if (!cat) return '';
  const color = catColor(cat);
  if (light) {
    return `<span class="card-category" style="color:${color}">
      <span style="width:7px;height:7px;border-radius:50%;background:${color};display:inline-block;flex-shrink:0;"></span>
      ${cat.name}
    </span>`;
  }
  return `<span class="hero-badge" style="background:${color}">${cat.name}</span>`;
}

function isBookmarked(id) {
  return state.bookmarks.includes(id);
}

function toggleBookmark(id) {
  if (isBookmarked(id)) {
    state.bookmarks = state.bookmarks.filter(b => b !== id);
    showToast('Bookmark removed');
  } else {
    state.bookmarks.push(id);
    showToast('Article bookmarked ✓');
  }
  localStorage.setItem(CONFIG.STORAGE.BOOKMARKS, JSON.stringify(state.bookmarks));
  renderBookmarks();
  document.querySelectorAll('.bookmark-btn').forEach(btn => {
    const bid = parseInt(btn.dataset.id, 10);
    const saved = isBookmarked(bid);
    btn.classList.toggle('saved', saved);
    btn.textContent = saved ? '🔖' : '🏷️';
  });
}

function showToast(msg) {
  const t = document.getElementById('toast');
  t.textContent = msg;
  t.classList.add('show');
  setTimeout(() => t.classList.remove('show'), 2500);
}

function updateSEO(title, description, image = '') {
  document.getElementById('metaTitle').textContent  = title + ' — The Broadsheet';
  document.getElementById('metaDesc').content       = description;
  document.getElementById('ogTitle').content        = title;
  document.getElementById('ogDesc').content         = description;
  if (image) document.getElementById('ogImage').content = image;
}

/* ── SKELETON LOADER ──────────────────────────────────────── */
function skeletonCards(n = 6) {
  return Array.from({length: n}, () => `
    <div class="card card-skeleton">
      <div class="card-img"><div class="skeleton-block"></div></div>
      <div class="card-body">
        <div class="skeleton-line w-30"></div>
        <div class="skeleton-line w-90"></div>
        <div class="skeleton-line w-70"></div>
        <div class="skeleton-line w-50"></div>
      </div>
    </div>`).join('');
}

/* ── RENDER: CATEGORY NAV ─────────────────────────────────── */
function renderNav() {
  const bar = document.getElementById('catBar');
  const all = { id: 0, name: 'All', slug: 'all', color: '#0D0D0D' };
  const cats = [all, ...state.categories];

  bar.innerHTML = cats.map(c => {
    const active = c.slug === state.activeCategory;
    const color  = catColor(c);
    return `<button class="cat-pill ${active ? 'active' : ''}" data-slug="${c.slug}"
      style="${active ? `border-bottom-color:${color};color:${color}` : ''}"
      aria-pressed="${active}">
      ${c.slug !== 'all' ? `<span class="cat-dot" style="background:${color}"></span>` : ''}
      ${c.name}
    </button>`;
  }).join('');

  bar.onclick = (e) => {
    const btn = e.target.closest('.cat-pill');
    if (!btn) return;
    state.activeCategory = btn.dataset.slug;
    state.currentPage    = 1;
    state.searchQuery    = '';
    document.getElementById('searchInput').value = '';
    renderNav();
    loadAndRenderArticles();
  };
}

/* ── RENDER: FOOTER CATEGORIES ────────────────────────────── */
function renderFooterCategories() {
  const el = document.getElementById('footerCategories');
  if (!el) return;
  el.innerHTML = '<h4>Categories</h4>' +
    state.categories.map(c =>
      `<a href="#" onclick="window.setCategory('${c.slug}');return false;">${c.name}</a>`
    ).join('');
}

/* ── RENDER: TAG CLOUD ────────────────────────────────────── */
function renderTags() {
  document.getElementById('tagCloud').innerHTML =
    state.categories.map(c =>
      `<span class="tag" role="button" tabindex="0"
        onclick="setCategory('${c.slug}')"
        onkeydown="if(event.key==='Enter')setCategory('${c.slug}')">${c.name}</span>`
    ).join('');
}

/* ── RENDER: HERO ─────────────────────────────────────────── */
function renderHero(articles) {
  const hero = document.getElementById('heroSection');
  if (!articles.length) { hero.innerHTML = ''; return; }

  const main = articles[0];
  const subs = articles.slice(1, 4);

  hero.innerHTML = `
    <div class="hero-primary" data-slug="${main.slug}" tabindex="0" role="article">
      <div class="hero-img">
        <img src="${imgSrc(main, 'hero')}" alt="${main.title}" loading="eager">
      </div>
      <div class="hero-gradient"></div>
      <div class="hero-content">
        ${badge(main, false)}
        <h2 class="hero-title">${main.title}</h2>
        <div class="hero-meta">
          <span>${main.author?.name || ''}</span>
          <span>${formatDate(main.published_at)}</span>
          <span>${main.read_time} min read</span>
        </div>
      </div>
    </div>
    <div class="hero-secondary">
      ${subs.map(a => `
        <div class="hero-sub-card" data-slug="${a.slug}" tabindex="0" role="article">
          <div class="hero-sub-img">
            <img src="${imgSrc(a, 'card')}" alt="${a.title}" loading="lazy">
          </div>
          <div class="hero-sub-body">
            ${badge(a)}
            <div class="hero-sub-title">${a.title}</div>
            <div class="hero-sub-meta">${a.author?.name || ''} · ${a.read_time} min read</div>
          </div>
        </div>`).join('')}
    </div>`;

  hero.onclick = (e) => {
    const el = e.target.closest('[data-slug]');
    if (el) openArticle(el.dataset.slug);
  };
}

/* ── RENDER: ARTICLE GRID ─────────────────────────────────── */
function renderGrid(articles) {
  const grid = document.getElementById('articleGrid');
  const lmw  = document.getElementById('loadMoreWrap');

  if (!articles.length) {
    grid.innerHTML = `<div class="no-results">
      <h3>No stories found</h3>
      <p>Try a different search term or category.</p>
    </div>`;
    lmw.style.display = 'none';
    return;
  }

  grid.innerHTML = articles.map(a => `
    <article class="card" data-slug="${a.slug}" tabindex="0" aria-label="${a.title}">
      <div class="card-img">
        <img src="${imgSrc(a, 'card')}" alt="${a.title}" loading="lazy">
      </div>
      <div class="card-body">
        ${badge(a)}
        <h3 class="card-title">${a.title}</h3>
        <p class="card-excerpt">${a.excerpt || ''}</p>
        <div class="card-footer">
          <div class="card-meta">
            <span>${a.author?.name || ''}</span>
            <span>${formatDate(a.published_at)}</span>
            <span>${a.read_time} min read</span>
          </div>
          <button class="bookmark-btn ${isBookmarked(a.id) ? 'saved' : ''}"
            data-id="${a.id}" aria-label="Bookmark">${isBookmarked(a.id) ? '🔖' : '🏷️'}</button>
        </div>
      </div>
    </article>`).join('');

  grid.onclick = (e) => {
    if (e.target.closest('.bookmark-btn')) return;
    const card = e.target.closest('.card');
    if (card) openArticle(card.dataset.slug);
  };
  grid.querySelectorAll('.bookmark-btn').forEach(btn => {
    btn.addEventListener('click', e => {
      e.stopPropagation();
      toggleBookmark(parseInt(btn.dataset.id, 10));
    });
  });

  lmw.style.display = state.pagination.has_next ? '' : 'none';
}

/* ── RENDER: SECTION HEADING ──────────────────────────────── */
function renderSectionHeading(total) {
  const cat   = state.activeCategory;
  const catObj = state.categories.find(c => c.slug === cat);
  const label = cat === 'all' ? 'Latest Stories' : `${catObj?.name || cat} Stories`;
  const color = cat === 'all' ? 'var(--accent)' : catColor(catObj || {});

  document.getElementById('sectionTitle').textContent = label;
  document.getElementById('sectionCount').textContent = `${total} article${total !== 1 ? 's' : ''}`;
  document.getElementById('sectionAccent').style.background = color;
}

/* ── RENDER: TRENDING ─────────────────────────────────────── */
function renderTrending(articles) {
  const el = document.getElementById('trendingList');
  if (!articles.length) {
    el.innerHTML = '<p style="font-size:.78rem;color:var(--muted);padding:14px 0;">No trending articles yet.</p>';
    return;
  }
  el.innerHTML = articles.slice(0, CONFIG.TRENDING_COUNT).map((a, i) => `
    <div class="compact-card" data-slug="${a.slug}" tabindex="0">
      <div class="compact-rank">${i + 1}</div>
      <div class="compact-body">
        <div class="compact-cat" style="color:${catColor(a.category)}">${a.category?.name || ''}</div>
        <div class="compact-title">${a.title}</div>
        <div class="compact-meta">${a.author?.name || ''} · ${a.read_time} min read</div>
      </div>
      <div class="compact-thumb">
        <img src="${imgSrc(a, 'card')}" alt="${a.title}" loading="lazy">
      </div>
    </div>`).join('');

  el.onclick = (e) => {
    const c = e.target.closest('.compact-card');
    if (c) openArticle(c.dataset.slug);
  };
}

/* ── RENDER: BOOKMARKS ────────────────────────────────────── */
function renderBookmarks() {
  const el = document.getElementById('bookmarksList');
  const bm = state.articles.filter(a => state.bookmarks.includes(a.id));
  if (!bm.length) {
    el.innerHTML = `<p style="font-size:.76rem;color:var(--muted);padding:14px 0;line-height:1.5;">
      No bookmarks yet.<br>Tap 🏷️ on any article.
    </p>`;
    return;
  }
  el.innerHTML = bm.map(a => `
    <div class="compact-card" data-slug="${a.slug}" tabindex="0">
      <div class="compact-body">
        <div class="compact-cat" style="color:${catColor(a.category)}">${a.category?.name || ''}</div>
        <div class="compact-title">${a.title}</div>
        <div class="compact-meta">${formatDate(a.published_at)}</div>
      </div>
    </div>`).join('');

  el.onclick = (e) => {
    const c = e.target.closest('.compact-card');
    if (c) openArticle(c.dataset.slug);
  };
}

/* ── LOAD ARTICLES FROM API ───────────────────────────────── */
async function loadAndRenderArticles(append = false) {
  const grid = document.getElementById('articleGrid');
  if (!append) grid.innerHTML = skeletonCards(CONFIG.ARTICLES_PER_PAGE);

  const params = {
    page:     state.currentPage,
    per_page: CONFIG.ARTICLES_PER_PAGE,
    sort:     'newest',
  };
  if (state.activeCategory !== 'all') params.category = state.activeCategory;
  if (state.searchQuery)              params.search    = state.searchQuery;

  const { data, error } = await API.getArticles(params);

  if (error || !data) {
    grid.innerHTML = `<div class="no-results"><h3>Could not load articles</h3>
      <p>Make sure the backend server is running on <code>${CONFIG.API_BASE}</code></p></div>`;
    document.getElementById('loadMoreWrap').style.display = 'none';
    return;
  }

  const articles = data.articles || [];
  state.pagination = data.pagination;

  if (append) {
    state.articles = [...state.articles, ...articles];
  } else {
    state.articles = articles;
    renderHero(articles);
    renderTrending(articles);
    renderBookmarks();
  }

  renderGrid(state.articles);
  renderSectionHeading(data.pagination.total);
}

/* ── OPEN ARTICLE MODAL ───────────────────────────────────── */
let _articleLoading = false;

async function openArticle(slug) {
  if (_articleLoading) return;
  _articleLoading = true;

  const overlay = document.getElementById('modalOverlay');
  document.getElementById('modalImg').src                = '';
  document.getElementById('modalCat').innerHTML          = '';
  document.getElementById('modalTitle').textContent      = 'Loading…';
  document.getElementById('modalMeta').innerHTML         = '';
  document.getElementById('modalContent').innerHTML      = skeletonCards(1);
  document.getElementById('modalRelated').innerHTML      = '';
  overlay.classList.add('open');
  document.body.style.overflow = 'hidden';

  const { data, error } = await API.getArticle(slug);
  _articleLoading = false;

  if (error || !data?.article) {
    document.getElementById('modalTitle').textContent    = 'Article not found';
    document.getElementById('modalContent').innerHTML   = `<p>Could not load this article. ${error || ''}</p>`;
    return;
  }

  const a = data.article;

  document.getElementById('modalImg').src                = imgSrc(a, 'modal');
  document.getElementById('modalImg').alt                = a.title;
  document.getElementById('modalCat').innerHTML          = badge(a);
  document.getElementById('modalTitle').textContent      = a.title;
  document.getElementById('modalMeta').innerHTML =
    `<span>By <strong>${a.author?.name || 'Staff Writer'}</strong></span>
     <span>${formatDate(a.published_at)}</span>
     <span>${a.read_time} min read</span>`;
  document.getElementById('modalContent').innerHTML      = a.body || '';

  updateSEO(
    a.seo_title || a.title,
    a.seo_description || a.excerpt || '',
    imgSrc(a, 'hero')
  );

  if (a.related?.length) {
    document.getElementById('modalRelated').innerHTML = `
      <div class="related-section">
        <h4 class="related-title">Related Stories</h4>
        <div class="related-grid">
          ${a.related.map(r => `
            <div class="related-card" data-slug="${r.slug}">
              <img src="${imgSrc(r, 'card')}" alt="${r.title}" loading="lazy">
              <div class="related-body">
                <div class="compact-cat" style="color:${catColor(r.category)}">${r.category?.name || ''}</div>
                <div class="related-card-title">${r.title}</div>
              </div>
            </div>`).join('')}
        </div>
      </div>`;
    document.getElementById('modalRelated').onclick = (e) => {
      const c = e.target.closest('.related-card');
      if (c) openArticle(c.dataset.slug);
    };
  }
}

/* ── CLOSE MODAL ──────────────────────────────────────────── */
function closeModal() {
  document.getElementById('modalOverlay').classList.remove('open');
  document.body.style.overflow = '';
  updateSEO('The Broadsheet — Latest News 2026', 'Authoritative independent journalism for the modern reader.');
}

/* ── DARK MODE ────────────────────────────────────────────── */
function applyTheme() {
  document.documentElement.setAttribute('data-theme', state.darkMode ? 'dark' : 'light');
  document.getElementById('themeBtn').textContent = state.darkMode ? '☀️' : '🌙';
  localStorage.setItem(CONFIG.STORAGE.DARK_MODE, state.darkMode);
}

/* ── DATE FORMAT ──────────────────────────────────────────── */
function formatDate(iso) {
  if (!iso) return '';
  try {
    return new Date(iso).toLocaleDateString('en-GB', { day: 'numeric', month: 'short', year: 'numeric' });
  } catch { return iso; }
}

/* ── GLOBAL HELPERS ───────────────────────────────────────── */
window.setCategory = function(slug) {
  state.activeCategory = slug;
  state.currentPage    = 1;
  state.searchQuery    = '';
  document.getElementById('searchInput').value = '';
  renderNav();
  loadAndRenderArticles();
  window.scrollTo({ top: 0, behavior: 'smooth' });
};

/* ── EVENT BINDING ────────────────────────────────────────── */
function bindEvents() {
  document.getElementById('modalClose').onclick = closeModal;
  document.getElementById('modalOverlay').onclick = e => {
    if (e.target.id === 'modalOverlay') closeModal();
  };
  document.addEventListener('keydown', e => { if (e.key === 'Escape') closeModal(); });

  document.getElementById('themeBtn').addEventListener('click', () => {
    state.darkMode = !state.darkMode;
    applyTheme();
  });

  let searchTimer;
  document.getElementById('searchInput').addEventListener('input', e => {
    clearTimeout(searchTimer);
    searchTimer = setTimeout(() => {
      state.searchQuery    = e.target.value.trim();
      state.activeCategory = 'all';
      state.currentPage    = 1;
      renderNav();
      loadAndRenderArticles();
    }, 350);
  });

  document.getElementById('loadMoreBtn').addEventListener('click', () => {
    state.currentPage++;
    loadAndRenderArticles(true);
  });

  document.getElementById('nlBtn').addEventListener('click', () => {
    const val = document.getElementById('nlInput').value.trim();
    if (!val || !val.includes('@')) { showToast('Please enter a valid email.'); return; }
    document.getElementById('nlInput').value = '';
    showToast('Subscribed! Welcome to The Broadsheet. ✉️');
  });
}

/* ── INIT ─────────────────────────────────────────────────── */
(async function init() {
  applyTheme();
  TICKER.init();
  bindEvents();

  const { data: catData } = await API.getCategories();
  if (catData?.categories) {
    state.categories = catData.categories;
    renderNav();
    renderTags();
    renderFooterCategories();
  }

  await loadAndRenderArticles();
})();
