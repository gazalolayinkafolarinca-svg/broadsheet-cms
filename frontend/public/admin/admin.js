/* ============================================================
   THE BROADSHEET CMS — admin.js
   Full admin dashboard application logic
   Depends on: ../js/config.js, ../js/api.js
   ============================================================ */

'use strict';

/* ── STATE ────────────────────────────────────────────────── */
const admin = {
  user:       null,
  categories: [],
  authors:    [],
  editingId:  null,
  mediaPage:  1,
};

/* ── TOAST ────────────────────────────────────────────────── */
function toast(msg, type = 'info') {
  const el = document.getElementById('adminToast');
  el.textContent = msg;
  el.className = `admin-toast show ${type}`;
  setTimeout(() => el.classList.remove('show'), 3000);
}

/* ── CONFIRM DIALOG ───────────────────────────────────────── */
function confirm(title, message) {
  return new Promise(resolve => {
    document.getElementById('confirmTitle').textContent   = title;
    document.getElementById('confirmMessage').textContent = message;
    document.getElementById('confirmBackdrop').style.display = 'flex';
    const ok     = document.getElementById('confirmOk');
    const cancel = document.getElementById('confirmCancel');
    const cleanup = (val) => {
      document.getElementById('confirmBackdrop').style.display = 'none';
      ok.removeEventListener('click', onOk);
      cancel.removeEventListener('click', onCancel);
      resolve(val);
    };
    const onOk     = () => cleanup(true);
    const onCancel = () => cleanup(false);
    ok.addEventListener('click', onOk);
    cancel.addEventListener('click', onCancel);
  });
}

/* ── AUTH ─────────────────────────────────────────────────── */
async function doLogin() {
  const email    = document.getElementById('loginEmail').value.trim();
  const password = document.getElementById('loginPassword').value;
  const errEl    = document.getElementById('loginError');
  const btn      = document.getElementById('loginBtn');

  if (!email || !password) {
    errEl.textContent = 'Email and password are required.';
    errEl.style.display = 'block';
    return;
  }

  btn.disabled = true;
  btn.textContent = 'Signing in…';
  errEl.style.display = 'none';

  const { data, error } = await API.login(email, password);

  btn.disabled = false;
  btn.textContent = 'Sign In';

  if (error || !data?.token) {
    errEl.textContent = error || 'Login failed. Check your credentials.';
    errEl.style.display = 'block';
    return;
  }

  localStorage.setItem(CONFIG.STORAGE.TOKEN,      data.token);
  localStorage.setItem(CONFIG.STORAGE.ADMIN_USER, JSON.stringify(data.user));
  admin.user = data.user;
  // Small delay to ensure localStorage is flushed before bootApp reads it
  await new Promise(r => setTimeout(r, 50));
  bootApp();
}

function doLogout() {
  localStorage.removeItem(CONFIG.STORAGE.TOKEN);
  localStorage.removeItem(CONFIG.STORAGE.ADMIN_USER);
  admin.user = null;
  document.getElementById('adminApp').style.display    = 'none';
  document.getElementById('loginScreen').style.display = 'flex';
}

async function checkAuth() {
  const token     = localStorage.getItem(CONFIG.STORAGE.TOKEN);
  const savedUser = localStorage.getItem(CONFIG.STORAGE.ADMIN_USER);
  if (!token) return false;

  // Use cached user if available, verify with server in background
  if (savedUser) {
    try { admin.user = JSON.parse(savedUser); } catch(e) {}
    if (admin.user) return true;
  }

  const { data, error } = await API.getMe();
  if (error || !data?.user) {
    localStorage.removeItem(CONFIG.STORAGE.TOKEN);
    localStorage.removeItem(CONFIG.STORAGE.ADMIN_USER);
    return false;
  }

  admin.user = data.user;
  return true;
}

/* ── BOOT ─────────────────────────────────────────────────── */
async function bootApp() {
  document.getElementById('loginScreen').style.display = 'none';
  document.getElementById('adminApp').style.display    = 'flex';

  // Set user info in sidebar
  document.getElementById('sidebarName').textContent  = admin.user.name || admin.user.email;
  document.getElementById('sidebarRole').textContent  = admin.user.role;
  document.getElementById('sidebarAvatar').textContent = (admin.user.name || 'A')[0].toUpperCase();

  // Load shared data
  const [catRes, authRes] = await Promise.all([API.adminGetCategories(), API.adminGetAuthors()]);
  if (catRes.data?.categories)  admin.categories = catRes.data.categories;
  if (authRes.data?.authors)    admin.authors    = authRes.data.authors;

  // Nav
  document.querySelectorAll('.nav-item').forEach(item => {
    item.addEventListener('click', e => {
      e.preventDefault();
      navigate(item.dataset.view);
    });
  });
  document.getElementById('logoutBtn').addEventListener('click', doLogout);

  navigate('dashboard');
}

/* ── NAVIGATE ─────────────────────────────────────────────── */
function navigate(view, params = {}) {
  document.querySelectorAll('.nav-item').forEach(i => {
    i.classList.toggle('active', i.dataset.view === view);
  });
  const titleMap = {
    dashboard:    'Dashboard',
    articles:     'All Articles',
    'new-article':'New Article',
    'edit-article':'Edit Article',
    'ai-generate':'AI Article Generator',
    media:        'Media Library',
    authors:      'Authors',
  };
  document.getElementById('topbarTitle').textContent = titleMap[view] || view;

  const wrap = document.getElementById('contentWrap');
  wrap.innerHTML = '<div style="color:var(--text-muted);padding:2rem;">Loading…</div>';

  const views = {
    dashboard:      renderDashboard,
    articles:       renderArticles,
    'new-article':  () => renderArticleEditor(null),
    'edit-article': () => renderArticleEditor(params.id),
    'ai-generate':  renderAIGenerator,
    media:          renderMedia,
    authors:        renderAuthors,
  };

  (views[view] || renderDashboard)();
}

/* ── DASHBOARD ────────────────────────────────────────────── */
async function renderDashboard() {
  const { data } = await API.adminGetStats();
  const s = data?.stats || {};

  document.getElementById('contentWrap').innerHTML = `
    <div class="stats-grid">
      <div class="stat-card success">
        <div class="stat-label">Published</div>
        <div class="stat-value">${s.published_articles ?? 0}</div>
        <div class="stat-sub">Live articles</div>
      </div>
      <div class="stat-card warning">
        <div class="stat-label">Drafts</div>
        <div class="stat-value">${s.draft_articles ?? 0}</div>
        <div class="stat-sub">Awaiting review</div>
      </div>
      <div class="stat-card ai-color">
        <div class="stat-label">AI Generated</div>
        <div class="stat-value">${s.ai_generated ?? 0}</div>
        <div class="stat-sub">AI drafts created</div>
      </div>
      <div class="stat-card accent">
        <div class="stat-label">Total Views</div>
        <div class="stat-value">${(s.total_views ?? 0).toLocaleString()}</div>
        <div class="stat-sub">Across all articles</div>
      </div>
    </div>

    <div class="section-card">
      <div class="section-card-header">
        <span class="section-card-title">Recent Activity</span>
        <button class="btn btn-ghost btn-sm" onclick="navigate('articles')">View All</button>
      </div>
      <table>
        <thead>
          <tr><th>Title</th><th>Category</th><th>Author</th><th>Status</th><th>Views</th><th>Actions</th></tr>
        </thead>
        <tbody>
          ${(s.recent_articles || []).map(a => `
            <tr>
              <td style="max-width:280px;">
                <div style="font-weight:500;white-space:nowrap;overflow:hidden;text-overflow:ellipsis;">${a.title}</div>
                ${a.ai_generated ? '<span class="badge badge-ai">AI</span>' : ''}
              </td>
              <td><span style="color:${a.color};font-size:.75rem;font-weight:700;">${a.category_name}</span></td>
              <td style="color:var(--text-muted)">${a.author_name}</td>
              <td><span class="badge badge-${a.status}">${a.status}</span></td>
              <td>${a.view_count || 0}</td>
              <td>
                <div class="article-row-actions">
                  <button class="btn btn-ghost btn-sm" onclick="navigate('edit-article',{id:${a.id}})">Edit</button>
                  ${a.status !== 'published'
                    ? `<button class="btn btn-success btn-sm" onclick="publishArticle(${a.id})">Publish</button>`
                    : `<button class="btn btn-ghost btn-sm" onclick="unpublishArticle(${a.id})">Unpublish</button>`}
                </div>
              </td>
            </tr>`).join('') || '<tr><td colspan="6" class="empty-state">No articles yet.</td></tr>'}
        </tbody>
      </table>
    </div>`;
}

/* ── ARTICLES LIST ────────────────────────────────────────── */
async function renderArticles(statusFilter = '', searchFilter = '') {
  const params = {};
  if (statusFilter) params.status = statusFilter;
  if (searchFilter) params.search = searchFilter;

  const { data } = await API.adminGetArticles(params);
  const articles  = data?.articles || [];

  document.getElementById('contentWrap').innerHTML = `
    <div class="article-list-header">
      <input type="search" class="filter-input" id="articleSearch"
        placeholder="Search articles…" value="${searchFilter}">
      <select class="filter-select" id="statusFilter">
        <option value="">All Statuses</option>
        <option value="published" ${statusFilter==='published'?'selected':''}>Published</option>
        <option value="draft"     ${statusFilter==='draft'?'selected':''}>Draft</option>
        <option value="review"    ${statusFilter==='review'?'selected':''}>In Review</option>
        <option value="archived"  ${statusFilter==='archived'?'selected':''}>Archived</option>
      </select>
      <button class="btn btn-primary btn-sm" onclick="navigate('new-article')">+ New Article</button>
      <button class="btn btn-ai btn-sm" onclick="navigate('ai-generate')">🤖 AI Generate</button>
    </div>

    <div class="section-card">
      <table>
        <thead>
          <tr><th>Title</th><th>Category</th><th>Status</th><th>Published</th><th>Views</th><th>Actions</th></tr>
        </thead>
        <tbody id="articlesTbody">
          ${articles.map(a => `
            <tr id="article-row-${a.id}">
              <td style="max-width:300px;">
                <div style="font-weight:500;white-space:nowrap;overflow:hidden;text-overflow:ellipsis;">${a.title}</div>
                ${a.ai_generated ? '<span class="badge badge-ai" style="margin-top:3px;">AI</span>' : ''}
              </td>
              <td><span style="color:${a.category_color};font-size:.75rem;font-weight:700;">${a.category_name}</span></td>
              <td><span class="badge badge-${a.status}">${a.status}</span></td>
              <td style="color:var(--text-muted);font-size:.76rem;">${a.published_at ? fmtDate(a.published_at) : '—'}</td>
              <td>${a.view_count || 0}</td>
              <td>
                <div class="article-row-actions">
                  <button class="btn btn-ghost btn-sm" onclick="navigate('edit-article',{id:${a.id}})">Edit</button>
                  ${a.status !== 'published'
                    ? `<button class="btn btn-success btn-sm" onclick="publishArticle(${a.id})">Publish</button>`
                    : `<button class="btn btn-ghost btn-sm" onclick="unpublishArticle(${a.id})">Unpublish</button>`}
                  <button class="btn btn-danger btn-sm" onclick="deleteArticle(${a.id},'${escHtml(a.title)}')">Delete</button>
                </div>
              </td>
            </tr>`).join('') || '<tr><td colspan="6"><div class="empty-state"><h3>No articles found</h3></div></td></tr>'}
        </tbody>
      </table>
    </div>`;

  // Bind filters
  let timer;
  document.getElementById('articleSearch').addEventListener('input', e => {
    clearTimeout(timer);
    timer = setTimeout(() => renderArticles(document.getElementById('statusFilter').value, e.target.value), 300);
  });
  document.getElementById('statusFilter').addEventListener('change', e => {
    renderArticles(e.target.value, document.getElementById('articleSearch').value);
  });
}

/* ── ARTICLE EDITOR ───────────────────────────────────────── */
async function renderArticleEditor(articleId) {
  admin.editingId = articleId || null;
  let article = null;

  if (articleId) {
    const { data } = await API.adminGetArticle(articleId);
    article = data?.article;
  }

  const catOptions = admin.categories.map(c =>
    `<option value="${c.slug}" ${article?.category?.slug===c.slug?'selected':''}>${c.name}</option>`
  ).join('');

  const authOptions = admin.authors.map(a =>
    `<option value="${a.slug}" ${article?.author?.slug===a.slug?'selected':''}>${a.name}</option>`
  ).join('');

  document.getElementById('contentWrap').innerHTML = `
    <div id="editorAlert"></div>

    <div class="form-card">
      <div class="form-card-title">Article Details</div>
      <div class="form-group">
        <label>Title *</label>
        <input class="form-control" id="artTitle" placeholder="Article headline…" value="${escHtml(article?.title||'')}">
      </div>
      <div class="form-row">
        <div class="form-group">
          <label>Category *</label>
          <select class="form-control" id="artCategory">${catOptions}</select>
        </div>
        <div class="form-group">
          <label>Author *</label>
          <select class="form-control" id="artAuthor">${authOptions}</select>
        </div>
      </div>
      <div class="form-group">
        <label>Excerpt <span style="color:var(--text-muted);font-weight:400;">(auto-generated if blank)</span></label>
        <textarea class="form-control" id="artExcerpt" rows="2" placeholder="Brief summary…">${escHtml(article?.excerpt||'')}</textarea>
      </div>
    </div>

    <div class="form-card">
      <div class="form-card-title">Article Body</div>
      <label class="rich-body-label">HTML Content *</label>
      <div class="body-toolbar">
        <button class="toolbar-btn" onclick="wrapTag('p')">¶ Para</button>
        <button class="toolbar-btn" onclick="wrapTag('strong')"><b>B</b></button>
        <button class="toolbar-btn" onclick="wrapTag('em')"><i>I</i></button>
        <button class="toolbar-btn" onclick="wrapTag('h2')">H2</button>
        <button class="toolbar-btn" onclick="wrapTag('h3')">H3</button>
        <button class="toolbar-btn" onclick="wrapTag('ul')">UL</button>
        <button class="toolbar-btn" onclick="insertLi()">LI</button>
        <button class="toolbar-btn" onclick="wrapTag('blockquote')">"</button>
        <button class="toolbar-btn" onclick="wrapTag('a href=&quot;#&quot;')">Link</button>
      </div>
      <textarea id="articleBody" spellcheck="true">${article?.body||''}</textarea>
    </div>

    <div class="form-card">
      <div class="form-card-title">SEO & Metadata</div>
      <div class="form-row">
        <div class="form-group">
          <label>SEO Title <span style="color:var(--text-muted);font-weight:400;">(≤ 60 chars)</span></label>
          <input class="form-control" id="artSeoTitle" placeholder="SEO-optimised title" value="${escHtml(article?.seo_title||'')}">
        </div>
        <div class="form-group">
          <label>Tags <span style="color:var(--text-muted);font-weight:400;">(comma-separated)</span></label>
          <input class="form-control" id="artTags" placeholder="ai, finance, 2026" value="${(article?.tags||[]).map(t=>t.name).join(', ')}">
        </div>
      </div>
      <div class="form-group">
        <label>SEO Description <span style="color:var(--text-muted);font-weight:400;">(≤ 160 chars)</span></label>
        <input class="form-control" id="artSeoDesc" placeholder="Meta description…" value="${escHtml(article?.seo_description||'')}">
      </div>
    </div>

    <div class="form-card">
      <div class="form-card-title">Publishing Options</div>
      <div class="form-row">
        <div class="form-group">
          <label>Status</label>
          <select class="form-control" id="artStatus">
            <option value="draft"     ${(!article||article.status==='draft')?'selected':''}>Draft</option>
            <option value="review"    ${article?.status==='review'?'selected':''}>In Review</option>
            <option value="published" ${article?.status==='published'?'selected':''}>Published</option>
            <option value="archived"  ${article?.status==='archived'?'selected':''}>Archived</option>
          </select>
        </div>
        <div class="form-group">
          <label>Featured Article</label>
          <select class="form-control" id="artFeatured">
            <option value="0" ${!article?.featured?'selected':''}>No</option>
            <option value="1" ${article?.featured?'selected':''}>Yes — show in hero</option>
          </select>
        </div>
      </div>
      <div class="form-group">
        <label>Schedule Publish Date/Time <span style="color:var(--text-muted);font-weight:400;">(leave blank to publish immediately)</span></label>
        <input type="datetime-local" class="form-control" id="artSchedule"
          value="${article?.scheduled_at ? article.scheduled_at.slice(0,16) : ''}">
        <div class="form-hint">If set and status is "Published", the article will go live at this exact time. Checked every minute by the scheduler.</div>
      </div>
    </div>

    <div class="btn-actions">
      <button class="btn btn-primary" id="saveDraftBtn" onclick="saveArticle('draft')">💾 Save Draft</button>
      <button class="btn btn-success" id="savePublishBtn" onclick="saveArticle('published')">🚀 Publish Now</button>
      <button class="btn btn-warning" onclick="saveArticle('review')">👁 Submit for Review</button>
      ${articleId ? `<button class="btn btn-danger" onclick="deleteArticle(${articleId},'this article',true)">🗑 Delete</button>` : ''}
      <button class="btn btn-ghost" onclick="navigate('articles')">Cancel</button>
    </div>`;
}

async function saveArticle(status) {
  const title    = document.getElementById('artTitle').value.trim();
  const body     = document.getElementById('articleBody').value.trim();
  const alertEl  = document.getElementById('editorAlert');

  if (!title) { alertEl.innerHTML = '<div class="alert alert-error">Title is required.</div>'; return; }
  if (!body && status === 'published') {
    alertEl.innerHTML = '<div class="alert alert-error">Body is required to publish.</div>';
    return;
  }

  alertEl.innerHTML = '';
  const tagRaw  = document.getElementById('artTags').value;
  const tags    = tagRaw.split(',').map(t => t.trim()).filter(Boolean);
  const schedVal = document.getElementById('artSchedule').value;

  const payload = {
    title,
    body,
    status,
    category_slug: document.getElementById('artCategory').value,
    author_slug:   document.getElementById('artAuthor').value,
    excerpt:       document.getElementById('artExcerpt').value.trim() || null,
    seo_title:     document.getElementById('artSeoTitle').value.trim() || null,
    seo_description: document.getElementById('artSeoDesc').value.trim() || null,
    featured:      document.getElementById('artFeatured').value === '1',
    scheduled_at:  schedVal ? new Date(schedVal).toISOString() : null,
    tags,
  };

  const fn     = admin.editingId ? API.adminUpdateArticle : API.adminCreateArticle;
  const arg    = admin.editingId ? [admin.editingId, payload] : [payload];
  const { data, error } = await fn(...arg);

  if (error) {
    alertEl.innerHTML = `<div class="alert alert-error">Error: ${error}</div>`;
    return;
  }

  toast(admin.editingId ? 'Article updated ✓' : 'Article created ✓', 'success');
  if (!admin.editingId && data?.article?.id) {
    admin.editingId = data.article.id;
    navigate('edit-article', { id: data.article.id });
  } else {
    alertEl.innerHTML = `<div class="alert alert-success">${status === 'published' ? '🚀 Published!' : '💾 Saved!'} Article ${status === 'published' ? 'is now live' : 'saved as ' + status}.</div>`;
  }
}

/* ── PUBLISH / UNPUBLISH / DELETE ─────────────────────────── */
async function publishArticle(id) {
  const { error } = await API.adminPublishArticle(id);
  if (error) { toast(`Error: ${error}`, 'error'); return; }
  toast('Article published! ✓', 'success');
  renderArticles();
}

async function unpublishArticle(id) {
  const { error } = await API.adminUnpublishArticle(id);
  if (error) { toast(`Error: ${error}`, 'error'); return; }
  toast('Article moved to draft', 'info');
  renderArticles();
}

async function deleteArticle(id, title, redirect = false) {
  const ok = await confirm('Delete Article', `Delete "${title}"? This cannot be undone.`);
  if (!ok) return;
  const { error } = await API.adminDeleteArticle(id);
  if (error) { toast(`Error: ${error}`, 'error'); return; }
  toast('Article deleted', 'info');
  if (redirect) navigate('articles');
  else renderArticles();
}

/* ── AI GENERATOR ─────────────────────────────────────────── */
function renderAIGenerator() {
  const catOptions = admin.categories.map(c =>
    `<option value="${c.slug}">${c.name}</option>`).join('');
  const authOptions = admin.authors.map(a =>
    `<option value="${a.slug}">${a.name}</option>`).join('');

  document.getElementById('contentWrap').innerHTML = `
    <div class="form-card ai-panel">
      <div class="form-card-title">🤖 AI Article Generator <span class="ai-badge">Powered by Claude</span></div>
      <div class="alert alert-info" style="margin-bottom:1rem;">
        Provide a topic and the AI will generate a complete article draft with title, body, SEO tags, and metadata.
        The draft is saved automatically for your review before publishing.
      </div>

      <div class="form-group">
        <label>Article Topic / Brief *</label>
        <textarea class="form-control" id="aiTopic" rows="3"
          placeholder="e.g. 'The impact of AI-driven underwriting on micro-SME insurance pricing in West Africa in 2026' — be specific for best results."></textarea>
      </div>
      <div class="form-row">
        <div class="form-group">
          <label>Category</label>
          <select class="form-control" id="aiCategory">${catOptions}</select>
        </div>
        <div class="form-group">
          <label>Assign Author</label>
          <select class="form-control" id="aiAuthor">${authOptions}</select>
        </div>
      </div>
      <div class="form-row">
        <div class="form-group">
          <label>Target Word Count</label>
          <select class="form-control" id="aiWordCount">
            <option value="400">Short (~400 words)</option>
            <option value="700" selected>Standard (~700 words)</option>
            <option value="1000">Long (~1,000 words)</option>
            <option value="1200">Deep-dive (~1,200 words)</option>
          </select>
        </div>
        <div class="form-group">
          <label>Writing Tone</label>
          <select class="form-control" id="aiTone">
            <option value="authoritative and informative">Authoritative / Informative</option>
            <option value="analytical and data-driven">Analytical / Data-driven</option>
            <option value="conversational and accessible">Conversational / Accessible</option>
            <option value="investigative and critical">Investigative / Critical</option>
          </select>
        </div>
      </div>

      <button class="btn btn-ai" id="aiGenerateBtn" onclick="runAIGenerate()">
        🤖 Generate Article Draft
      </button>

      <div class="ai-status" id="aiStatus">
        <span class="ai-generating" id="aiStatusText">⏳ Generating article… this takes 10–30 seconds</span>
      </div>
    </div>

    <div id="aiResult"></div>`;
}

async function runAIGenerate() {
  const topic     = document.getElementById('aiTopic').value.trim();
  const statusEl  = document.getElementById('aiStatus');
  const statusTxt = document.getElementById('aiStatusText');
  const btn       = document.getElementById('aiGenerateBtn');
  const resultEl  = document.getElementById('aiResult');

  if (!topic) { toast('Please enter a topic.', 'error'); return; }
  if (!localStorage.getItem(CONFIG.STORAGE.TOKEN)) { toast('Not authenticated.', 'error'); return; }

  btn.disabled = true;
  statusEl.classList.add('visible');
  statusTxt.textContent = '⏳ Sending to Claude… (10–30 seconds)';
  resultEl.innerHTML = '';

  const payload = {
    topic,
    category_slug: document.getElementById('aiCategory').value,
    author_slug:   document.getElementById('aiAuthor').value,
    word_count:    parseInt(document.getElementById('aiWordCount').value, 10),
    tone:          document.getElementById('aiTone').value,
  };

  const { data, error } = await API.adminGenerateAI(payload);
  btn.disabled = false;
  statusEl.classList.remove('visible');

  if (error || !data?.article) {
    toast(`AI generation failed: ${error || 'Unknown error'}`, 'error');
    resultEl.innerHTML = `<div class="alert alert-error">Generation failed: ${error}.<br><small>Check that ANTHROPIC_API_KEY is set in your .env file.</small></div>`;
    return;
  }

  const a = data.article;
  toast('Draft created! Review and publish below. ✓', 'success');

  resultEl.innerHTML = `
    <div class="form-card" style="border-color:rgba(22,163,74,.3);">
      <div class="form-card-title" style="color:#4ade80;">✅ Draft Created — ID #${a.id}</div>
      <div class="alert alert-success">${data.message}</div>
      <div style="margin-bottom:1rem;">
        <strong>${a.title}</strong><br>
        <span style="color:var(--text-muted);font-size:.8rem;">${a.excerpt}</span>
      </div>
      <div style="background:var(--surface-2);border-radius:6px;padding:1rem;font-size:.82rem;line-height:1.7;max-height:300px;overflow-y:auto;margin-bottom:1rem;">
        ${a.body}
      </div>
      <div style="display:flex;gap:.75rem;flex-wrap:wrap;">
        <button class="btn btn-primary" onclick="navigate('edit-article',{id:${a.id}})">✏️ Review & Edit</button>
        <button class="btn btn-success" onclick="publishArticle(${a.id})">🚀 Publish Now</button>
        <button class="btn btn-ghost" onclick="navigate('ai-generate')">Generate Another</button>
      </div>
    </div>`;
}

/* ── MEDIA LIBRARY ────────────────────────────────────────── */
async function renderMedia() {
  const { data } = await API.adminGetMedia(admin.mediaPage);
  const media = data?.media || [];

  document.getElementById('contentWrap').innerHTML = `
    <div class="upload-zone" id="uploadZone">
      <div style="font-size:2rem;">📁</div>
      <p>Drag &amp; drop images here, or <strong>click to browse</strong></p>
      <p style="font-size:.72rem;margin-top:4px;">PNG, JPG, WEBP, GIF — max 10MB</p>
      <input type="file" id="fileInput" accept="image/*" multiple style="display:none;">
    </div>
    <div id="uploadProgress"></div>
    <div class="section-card" style="margin-top:1rem;">
      <div class="section-card-header">
        <span class="section-card-title">Media Library</span>
        <span style="font-size:.76rem;color:var(--text-muted);">${data?.pagination?.total || 0} files</span>
      </div>
      <div class="media-grid" style="padding:1rem;" id="mediaGrid">
        ${media.map(m => `
          <div class="media-item" onclick="copyMediaUrl('${m.url}','${escHtml(m.original_name)}')">
            <img src="${CONFIG.API_BASE.replace('/api','')}${m.thumbnail_url || m.url}" alt="${m.alt_text || m.original_name}" loading="lazy">
            <div class="media-item-info">${m.original_name}</div>
          </div>`).join('') || '<div style="padding:1rem;color:var(--text-muted);">No media uploaded yet.</div>'}
      </div>
    </div>`;

  // Upload zone
  const zone  = document.getElementById('uploadZone');
  const input = document.getElementById('fileInput');
  zone.addEventListener('click', () => input.click());
  input.addEventListener('change', e => handleFileUpload(e.target.files));
  zone.addEventListener('dragover', e => { e.preventDefault(); zone.classList.add('drag-over'); });
  zone.addEventListener('dragleave', () => zone.classList.remove('drag-over'));
  zone.addEventListener('drop', e => {
    e.preventDefault(); zone.classList.remove('drag-over');
    handleFileUpload(e.dataTransfer.files);
  });
}

async function handleFileUpload(files) {
  const prog = document.getElementById('uploadProgress');
  prog.innerHTML = `<div class="alert alert-info">Uploading ${files.length} file(s)…</div>`;
  let success = 0;
  for (const file of files) {
    const fd = new FormData();
    fd.append('file', file);
    fd.append('alt_text', file.name.replace(/\.[^.]+$/, ''));
    const { data, error } = await API.adminUpload(fd);
    if (error) {
      prog.innerHTML += `<div class="alert alert-error">Failed: ${file.name} — ${error}</div>`;
    } else {
      success++;
    }
  }
  prog.innerHTML = `<div class="alert alert-success">${success} file(s) uploaded successfully.</div>`;
  setTimeout(renderMedia, 1500);
}

function copyMediaUrl(url, name) {
  const full = `${CONFIG.API_BASE.replace('/api', '')}${url}`;
  navigator.clipboard.writeText(full).then(() => toast(`Copied URL for: ${name}`, 'success'));
}

/* ── AUTHORS ──────────────────────────────────────────────── */
async function renderAuthors() {
  const { data } = await API.adminGetAuthors();
  const authors = data?.authors || [];

  document.getElementById('contentWrap').innerHTML = `
    <div class="section-card" style="margin-bottom:1.5rem;">
      <div class="section-card-header">
        <span class="section-card-title">Authors (${authors.length})</span>
      </div>
      <table>
        <thead><tr><th>Name</th><th>Email</th><th>Bio</th><th>Slug</th></tr></thead>
        <tbody>
          ${authors.map(a => `
            <tr>
              <td style="font-weight:500;">${a.name}</td>
              <td style="color:var(--text-muted)">${a.email || '—'}</td>
              <td style="color:var(--text-muted);font-size:.78rem;max-width:250px;">${a.bio || '—'}</td>
              <td><code style="font-size:.72rem;color:var(--text-muted)">${a.slug}</code></td>
            </tr>`).join('') || '<tr><td colspan="4"><div class="empty-state">No authors yet.</div></td></tr>'}
        </tbody>
      </table>
    </div>

    <div class="form-card">
      <div class="form-card-title">Add New Author</div>
      <div class="form-row">
        <div class="form-group">
          <label>Full Name *</label>
          <input class="form-control" id="newAuthorName" placeholder="Jane Smith">
        </div>
        <div class="form-group">
          <label>Email</label>
          <input class="form-control" id="newAuthorEmail" placeholder="jane@broadsheet.com" type="email">
        </div>
      </div>
      <div class="form-group">
        <label>Bio / Title</label>
        <input class="form-control" id="newAuthorBio" placeholder="Senior Finance Correspondent">
      </div>
      <div class="form-row">
        <div class="form-group">
          <label>Twitter Handle</label>
          <input class="form-control" id="newAuthorTwitter" placeholder="@janesmith">
        </div>
        <div class="form-group">
          <label>LinkedIn URL</label>
          <input class="form-control" id="newAuthorLinkedin" placeholder="https://linkedin.com/in/…">
        </div>
      </div>
      <div id="authorAlert"></div>
      <button class="btn btn-primary" onclick="createAuthor()">+ Add Author</button>
    </div>`;
}

async function createAuthor() {
  const name = document.getElementById('newAuthorName').value.trim();
  if (!name) { toast('Name is required', 'error'); return; }
  const { data, error } = await API._request
    ? null
    : await fetch(`${CONFIG.API_BASE}/admin/authors`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json', 'Authorization': `Bearer ${localStorage.getItem(CONFIG.STORAGE.TOKEN)}` },
        body: JSON.stringify({
          name, email: document.getElementById('newAuthorEmail').value,
          bio: document.getElementById('newAuthorBio').value,
          twitter: document.getElementById('newAuthorTwitter').value,
          linkedin: document.getElementById('newAuthorLinkedin').value,
        })
      }).then(r => r.json());

  toast('Author added ✓', 'success');
  const { data: a2 } = await API.adminGetAuthors();
  if (a2?.authors) admin.authors = a2.authors;
  renderAuthors();
}

/* ── HELPERS ──────────────────────────────────────────────── */
function fmtDate(iso) {
  if (!iso) return '—';
  return new Date(iso).toLocaleDateString('en-GB', { day:'numeric', month:'short', year:'numeric' });
}

function escHtml(str) {
  return String(str || '').replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;').replace(/"/g,'&quot;');
}

function wrapTag(tag) {
  const ta = document.getElementById('articleBody');
  if (!ta) return;
  const start = ta.selectionStart, end = ta.selectionEnd;
  const sel  = ta.value.slice(start, end) || 'Text here';
  const repl = `<${tag}>${sel}</${tag.split(' ')[0]}>`;
  ta.value = ta.value.slice(0, start) + repl + ta.value.slice(end);
  ta.focus();
}

function insertLi() {
  const ta = document.getElementById('articleBody');
  if (!ta) return;
  const pos = ta.selectionStart;
  const ins = '<li>List item</li>';
  ta.value  = ta.value.slice(0, pos) + ins + ta.value.slice(pos);
  ta.focus();
}

// Expose functions needed by inline onclick handlers
window.navigate         = navigate;
window.publishArticle   = publishArticle;
window.unpublishArticle = unpublishArticle;
window.deleteArticle    = deleteArticle;
window.runAIGenerate    = runAIGenerate;
window.copyMediaUrl     = copyMediaUrl;
window.saveArticle      = saveArticle;
window.createAuthor     = createAuthor;
window.wrapTag          = wrapTag;
window.insertLi         = insertLi;

/* ── INIT ─────────────────────────────────────────────────── */
(async function init() {
  document.getElementById('loginBtn').addEventListener('click', doLogin);
  document.getElementById('loginPassword').addEventListener('keydown', e => {
    if (e.key === 'Enter') doLogin();
  });

  const authed = await checkAuth();
  if (authed) {
    bootApp();
  } else {
    document.getElementById('loginScreen').style.display = 'flex';
  }
})();
