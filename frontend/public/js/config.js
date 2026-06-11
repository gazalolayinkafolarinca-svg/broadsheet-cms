/* ============================================================
   THE BROADSHEET — js/config.js
   Centralised configuration — change API_BASE to your
   deployed backend URL when going to production.
   ============================================================ */

const CONFIG = {
  // Backend API base URL — change for production
  API_BASE: 'https://broadsheet-cms-api.onrender.com/api',

  // Pagination
  ARTICLES_PER_PAGE: 9,
  TRENDING_COUNT: 5,

  // Local storage keys
  STORAGE: {
    BOOKMARKS:  'bs_bookmarks',
    DARK_MODE:  'bs_dark',
    TOKEN:      'bs_admin_token',
    ADMIN_USER: 'bs_admin_user',
  },

  // Category color map (fallback if API is slow)
  CAT_COLORS: {
    b2b:       '#2563EB',
    insurance: '#16A34A',
    education: '#D97706',
    lifestyle: '#DB2777',
    politics:  '#DC2626',
    finance:   '#059669',
    world:     '#7C3AED',
  },

  // Picsum fallback seeds (id * multiplier)
  IMG_SEED_HERO:    7,
  IMG_SEED_CARD:    13,
  IMG_SEED_THUMB:   5,
  IMG_SEED_MODAL:   3,
};
