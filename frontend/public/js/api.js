/* ============================================================
   THE BROADSHEET — js/api.js
   All API communication with the Flask backend.
   Every function returns { data, error }.
   ============================================================ */

'use strict';

const API = (() => {

  async function _request(path, options = {}) {
    const url = `${CONFIG.API_BASE}${path}`;
    const headers = { 'Content-Type': 'application/json', ...(options.headers || {}) };

    // Attach JWT if present
    const token = localStorage.getItem(CONFIG.STORAGE.TOKEN);
    if (token) headers['Authorization'] = `Bearer ${token}`;

    try {
      const res = await fetch(url, {
        ...options,
        headers,
        body: options.body ? JSON.stringify(options.body) : undefined,
      });
      const data = await res.json();
      if (!res.ok) return { data: null, error: data.error || `HTTP ${res.status}` };
      return { data, error: null };
    } catch (err) {
      return { data: null, error: err.message };
    }
  }

  // ── Public ────────────────────────────────────────────────

  async function getArticles(params = {}) {
    const qs = new URLSearchParams(params).toString();
    return _request(`/articles${qs ? '?' + qs : ''}`);
  }

  async function getArticle(slug) {
    return _request(`/articles/${slug}`);
  }

  async function getCategories() {
    return _request('/categories');
  }

  async function getAuthor(slug) {
    return _request(`/authors/${slug}`);
  }

  // ── Admin Auth ────────────────────────────────────────────

  async function login(email, password) {
    return _request('/admin/login', { method: 'POST', body: { email, password } });
  }

  async function getMe() {
    return _request('/admin/me');
  }

  // ── Admin Articles ────────────────────────────────────────

  async function adminGetArticles(params = {}) {
    const qs = new URLSearchParams(params).toString();
    return _request(`/admin/articles${qs ? '?' + qs : ''}`);
  }

  async function adminGetArticle(id) {
    return _request(`/admin/articles/${id}`);
  }

  async function adminCreateArticle(payload) {
    return _request('/admin/articles', { method: 'POST', body: payload });
  }

  async function adminUpdateArticle(id, payload) {
    return _request(`/admin/articles/${id}`, { method: 'PUT', body: payload });
  }

  async function adminDeleteArticle(id) {
    return _request(`/admin/articles/${id}`, { method: 'DELETE' });
  }

  async function adminPublishArticle(id) {
    return _request(`/admin/articles/${id}/publish`, { method: 'POST' });
  }

  async function adminUnpublishArticle(id) {
    return _request(`/admin/articles/${id}/unpublish`, { method: 'POST' });
  }

  // ── Admin Media ───────────────────────────────────────────

  async function adminUpload(formData) {
    const token = localStorage.getItem(CONFIG.STORAGE.TOKEN);
    const headers = {};
    if (token) headers['Authorization'] = `Bearer ${token}`;
    try {
      const res = await fetch(`${CONFIG.API_BASE}/admin/upload`, {
        method: 'POST', headers, body: formData,
      });
      const data = await res.json();
      if (!res.ok) return { data: null, error: data.error || `HTTP ${res.status}` };
      return { data, error: null };
    } catch (err) {
      return { data: null, error: err.message };
    }
  }

  async function adminGetMedia(page = 1) {
    return _request(`/admin/media?page=${page}`);
  }

  // ── Admin AI ──────────────────────────────────────────────

  async function adminGenerateAI(payload) {
    return _request('/admin/ai/generate', { method: 'POST', body: payload });
  }

  // ── Admin Stats ───────────────────────────────────────────

  async function adminGetStats() {
    return _request('/admin/stats');
  }

  async function adminGetAuthors() {
    return _request('/admin/authors');
  }

  async function adminGetCategories() {
    return _request('/admin/categories');
  }

  return {
    getArticles, getArticle, getCategories, getAuthor,
    login, getMe,
    adminGetArticles, adminGetArticle, adminCreateArticle,
    adminUpdateArticle, adminDeleteArticle,
    adminPublishArticle, adminUnpublishArticle,
    adminUpload, adminGetMedia,
    adminGenerateAI, adminGetStats,
    adminGetAuthors, adminGetCategories,
  };
})();
