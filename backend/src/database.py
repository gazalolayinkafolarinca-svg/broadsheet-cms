"""
============================================================
THE BROADSHEET CMS — Database Schema & Init
File: backend/src/database.py

Tables:
  authors      — writer profiles
  categories   — article categories
  tags         — freeform tags
  articles     — main content table
  article_tags — many-to-many join
  media        — uploaded images/files
  admin_users  — CMS admin accounts
  sessions     — invalidated JWT tracking
============================================================
"""

import sqlite3
import os
import hashlib
import secrets
import json
from datetime import datetime

DB_PATH = os.getenv("DATABASE_PATH", "instance/broadsheet.db")

SCHEMA = """
PRAGMA journal_mode=WAL;
PRAGMA foreign_keys=ON;

-- ── ADMIN USERS ───────────────────────────────────────────
CREATE TABLE IF NOT EXISTS admin_users (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    email         TEXT    NOT NULL UNIQUE COLLATE NOCASE,
    password_hash TEXT    NOT NULL,
    name          TEXT    NOT NULL,
    role          TEXT    NOT NULL DEFAULT 'editor'
                          CHECK(role IN ('superadmin','admin','editor')),
    avatar_url    TEXT,
    is_active     INTEGER NOT NULL DEFAULT 1,
    last_login    TEXT,
    created_at    TEXT    NOT NULL DEFAULT (datetime('now')),
    updated_at    TEXT    NOT NULL DEFAULT (datetime('now'))
);

-- ── AUTHORS ───────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS authors (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    name        TEXT    NOT NULL,
    slug        TEXT    NOT NULL UNIQUE,
    bio         TEXT,
    email       TEXT    UNIQUE COLLATE NOCASE,
    avatar_url  TEXT,
    twitter     TEXT,
    linkedin    TEXT,
    is_active   INTEGER NOT NULL DEFAULT 1,
    created_at  TEXT    NOT NULL DEFAULT (datetime('now')),
    updated_at  TEXT    NOT NULL DEFAULT (datetime('now'))
);

-- ── CATEGORIES ────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS categories (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    name        TEXT    NOT NULL UNIQUE,
    slug        TEXT    NOT NULL UNIQUE,
    description TEXT,
    color       TEXT    NOT NULL DEFAULT '#0D0D0D',
    is_active   INTEGER NOT NULL DEFAULT 1,
    sort_order  INTEGER NOT NULL DEFAULT 0,
    created_at  TEXT    NOT NULL DEFAULT (datetime('now'))
);

-- ── TAGS ──────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS tags (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    name       TEXT NOT NULL UNIQUE COLLATE NOCASE,
    slug       TEXT NOT NULL UNIQUE,
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
);

-- ── MEDIA ─────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS media (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    filename      TEXT    NOT NULL,
    original_name TEXT    NOT NULL,
    mime_type     TEXT    NOT NULL,
    size_bytes    INTEGER NOT NULL,
    width         INTEGER,
    height        INTEGER,
    url           TEXT    NOT NULL,
    thumbnail_url TEXT,
    alt_text      TEXT,
    uploaded_by   INTEGER REFERENCES admin_users(id),
    created_at    TEXT    NOT NULL DEFAULT (datetime('now'))
);

-- ── ARTICLES ──────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS articles (
    id               INTEGER PRIMARY KEY AUTOINCREMENT,
    title            TEXT    NOT NULL,
    slug             TEXT    NOT NULL UNIQUE,
    excerpt          TEXT,
    body             TEXT    NOT NULL DEFAULT '',
    status           TEXT    NOT NULL DEFAULT 'draft'
                             CHECK(status IN ('draft','review','published','archived')),
    author_id        INTEGER NOT NULL REFERENCES authors(id),
    category_id      INTEGER NOT NULL REFERENCES categories(id),
    featured_image   INTEGER REFERENCES media(id),
    featured         INTEGER NOT NULL DEFAULT 0,
    read_time        INTEGER NOT NULL DEFAULT 0,
    view_count       INTEGER NOT NULL DEFAULT 0,
    seo_title        TEXT,
    seo_description  TEXT,
    og_title         TEXT,
    og_description   TEXT,
    og_image         INTEGER REFERENCES media(id),
    ai_generated     INTEGER NOT NULL DEFAULT 0,
    ai_topic_prompt  TEXT,
    scheduled_at     TEXT,
    published_at     TEXT,
    created_by       INTEGER REFERENCES admin_users(id),
    updated_by       INTEGER REFERENCES admin_users(id),
    created_at       TEXT    NOT NULL DEFAULT (datetime('now')),
    updated_at       TEXT    NOT NULL DEFAULT (datetime('now'))
);

-- ── ARTICLE TAGS (join table) ──────────────────────────────
CREATE TABLE IF NOT EXISTS article_tags (
    article_id INTEGER NOT NULL REFERENCES articles(id) ON DELETE CASCADE,
    tag_id     INTEGER NOT NULL REFERENCES tags(id)     ON DELETE CASCADE,
    PRIMARY KEY (article_id, tag_id)
);

-- ── INDEXES ───────────────────────────────────────────────
CREATE INDEX IF NOT EXISTS idx_articles_status       ON articles(status);
CREATE INDEX IF NOT EXISTS idx_articles_category     ON articles(category_id);
CREATE INDEX IF NOT EXISTS idx_articles_author       ON articles(author_id);
CREATE INDEX IF NOT EXISTS idx_articles_published_at ON articles(published_at DESC);
CREATE INDEX IF NOT EXISTS idx_articles_slug         ON articles(slug);
CREATE INDEX IF NOT EXISTS idx_articles_featured     ON articles(featured);
CREATE INDEX IF NOT EXISTS idx_articles_scheduled    ON articles(scheduled_at);

-- ── TRIGGERS (auto-update updated_at) ──────────────────────
CREATE TRIGGER IF NOT EXISTS articles_updated_at
    AFTER UPDATE ON articles
    BEGIN
        UPDATE articles SET updated_at = datetime('now') WHERE id = NEW.id;
    END;

CREATE TRIGGER IF NOT EXISTS authors_updated_at
    AFTER UPDATE ON authors
    BEGIN
        UPDATE authors SET updated_at = datetime('now') WHERE id = NEW.id;
    END;

CREATE TRIGGER IF NOT EXISTS admin_users_updated_at
    AFTER UPDATE ON admin_users
    BEGIN
        UPDATE admin_users SET updated_at = datetime('now') WHERE id = NEW.id;
    END;
"""


def get_db():
    """Return a database connection with row_factory set."""
    os.makedirs(os.path.dirname(DB_PATH) if os.path.dirname(DB_PATH) else ".", exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys=ON")
    conn.execute("PRAGMA journal_mode=WAL")
    return conn


def hash_password(password: str) -> str:
    """PBKDF2-HMAC-SHA256 password hashing (no bcrypt needed)."""
    salt = secrets.token_hex(32)
    dk = hashlib.pbkdf2_hmac("sha256", password.encode(), salt.encode(), 390000)
    return f"pbkdf2:sha256:390000:{salt}:{dk.hex()}"


def verify_password(password: str, stored_hash: str) -> bool:
    """Verify a password against a stored PBKDF2 hash."""
    try:
        _, algo, iterations, salt, dk_hex = stored_hash.split(":")
        iterations = int(iterations)
        dk = hashlib.pbkdf2_hmac(algo, password.encode(), salt.encode(), iterations)
        return secrets.compare_digest(dk.hex(), dk_hex)
    except Exception:
        return False


def init_db():
    """Create all tables and seed initial data."""
    conn = get_db()
    conn.executescript(SCHEMA)
    conn.commit()
    print(f"[DB] Schema applied → {DB_PATH}")

    _seed_categories(conn)
    _seed_admin(conn)
    _seed_authors(conn)
    _seed_articles(conn)

    conn.commit()
    conn.close()
    print("[DB] Database initialised successfully.")


def _seed_categories(conn):
    cats = [
        ("B2B",        "b2b",       "Business-to-business news and strategy",  "#2563EB", 1),
        ("Insurance",  "insurance", "Insurance industry news and analysis",    "#16A34A", 2),
        ("Education",  "education", "Education policy, edtech and learning",   "#D97706", 3),
        ("Lifestyle",  "lifestyle", "Culture, travel, wellness and living",    "#DB2777", 4),
        ("Politics",   "politics",  "Global political news and analysis",      "#DC2626", 5),
        ("Finance",    "finance",   "Markets, economics and personal finance", "#059669", 6),
        ("World News", "world",     "International news and current affairs",  "#7C3AED", 7),
    ]
    for name, slug, desc, color, order in cats:
        conn.execute("""
            INSERT OR IGNORE INTO categories (name, slug, description, color, sort_order)
            VALUES (?, ?, ?, ?, ?)
        """, (name, slug, desc, color, order))
    print("[DB] Categories seeded")


def _seed_admin(conn):
    email = os.getenv("ADMIN_EMAIL", "admin@broadsheet.com")
    password = os.getenv("ADMIN_PASSWORD", "Admin2026!SecurePassword")
    existing = conn.execute("SELECT id FROM admin_users WHERE email=?", (email,)).fetchone()
    if not existing:
        conn.execute("""
            INSERT INTO admin_users (email, password_hash, name, role)
            VALUES (?, ?, ?, ?)
        """, (email, hash_password(password), "Super Admin", "superadmin"))
        print(f"[DB] Admin user created → {email}")
    else:
        print(f"[DB] Admin user already exists → {email}")


def _seed_authors(conn):
    authors = [
        ("Rebecca Osei",        "rebecca-osei",        "Senior Finance Editor",         "rebecca@broadsheet.com"),
        ("Dmitri Vaskov",       "dmitri-vaskov",       "Crypto & Markets Correspondent", "dmitri@broadsheet.com"),
        ("Lukas Brennan",       "lukas-brennan",       "Politics & Policy Editor",       "lukas@broadsheet.com"),
        ("Priya Mehta",         "priya-mehta",         "B2B Technology Reporter",        "priya@broadsheet.com"),
        ("Dr. Yemi Adeyemi",    "yemi-adeyemi",        "Education Correspondent",        "yemi@broadsheet.com"),
        ("Amara Blake",         "amara-blake",         "Lifestyle & Culture Writer",     "amara@broadsheet.com"),
        ("Gail Hutchins",       "gail-hutchins",       "Insurance Industry Analyst",     "gail@broadsheet.com"),
        ("Suresh Krishnamurthy","suresh-krishnamurthy","World Affairs Correspondent",    "suresh@broadsheet.com"),
    ]
    for name, slug, bio, email in authors:
        conn.execute("""
            INSERT OR IGNORE INTO authors (name, slug, bio, email)
            VALUES (?, ?, ?, ?)
        """, (name, slug, bio, email))
    print("[DB] Authors seeded")


def _seed_articles(conn):
    """Seed the 14 current 2026 articles."""
    existing = conn.execute("SELECT COUNT(*) FROM articles").fetchone()[0]
    if existing > 0:
        print("[DB] Articles already exist, skipping seed")
        return

    articles = [
        {
            "title": "Global Central Banks Begin Coordinated Pivot as Inflation Hits 1.8%",
            "slug": "global-central-banks-coordinated-pivot-inflation-2026",
            "excerpt": "The Fed, ECB, and Bank of England have all signalled simultaneous rate reductions for Q3 2026.",
            "body": "<p>In a move that surprised many analysts by its synchronicity, the Federal Reserve, European Central Bank, and Bank of England each telegraphed rate cuts within a 72-hour window this week.</p><p>The catalyst is a combination of cooling inflation — US CPI now at <strong>1.8%, its lowest reading since early 2022</strong> — and mounting concerns about growth in advanced economies as AI-driven productivity gains reshape labour markets faster than policymakers anticipated.</p><p>Futures markets are now pricing in three cuts apiece from the Fed and ECB before year-end, with the first expected at the July meetings.</p>",
            "category": "finance", "author": "rebecca-osei",
            "read_time": 6, "featured": 1, "status": "published"
        },
        {
            "title": "Bitcoin Crosses $185,000 as Spot ETF Holdings Surpass 1.2 Million BTC",
            "slug": "bitcoin-185000-spot-etf-1-2-million-btc-2026",
            "excerpt": "Institutional accumulation through BlackRock and Fidelity has absorbed nearly 6% of circulating supply.",
            "body": "<p>Bitcoin set a new all-time high above $185,000 on Tuesday, extending a rally that has now seen the asset more than double from its October 2025 lows.</p><p>The structural shift is stark: <strong>spot ETF products now collectively hold over 1.2 million BTC</strong>, representing approximately 5.7% of the total circulating supply.</p>",
            "category": "finance", "author": "dmitri-vaskov",
            "read_time": 5, "featured": 0, "status": "published"
        },
        {
            "title": "UN Framework on AI Governance Adopted by 141 Nations",
            "slug": "un-ai-governance-framework-141-nations-2026",
            "excerpt": "The landmark resolution establishes a global AI Safety Council and binding transparency requirements.",
            "body": "<p>The United Nations General Assembly voted 141-0 on Thursday to adopt the Nairobi Framework on Artificial Intelligence Governance, with China, Russia, and Belarus abstaining.</p><p>\"Nairobi is to AI what the Paris Agreement was to climate,\" said UN Secretary-General Antonio Guterres. \"Imperfect, contested — but real.\"</p>",
            "category": "politics", "author": "lukas-brennan",
            "read_time": 7, "featured": 1, "status": "published"
        },
        {
            "title": "Salesforce Agentforce Reaches 500,000 Enterprise Deployments",
            "slug": "salesforce-agentforce-500000-enterprise-deployments-2026",
            "excerpt": "Autonomous AI agents that close deals without human intervention are the new baseline for enterprise CRM.",
            "body": "<p>Salesforce announced this week that its Agentforce platform has now been adopted by more than 500,000 enterprise customers.</p><p>\"Two years ago, AI-assisted selling meant autocomplete on email,\" said Chief Revenue Officer Brian Landsman. \"Today our customers are running <strong>fully autonomous sales cycles</strong> with zero human touch.\"</p>",
            "category": "b2b", "author": "priya-mehta",
            "read_time": 4, "featured": 0, "status": "published"
        },
        {
            "title": "Oxford and MIT Launch Joint AI-Native Degree with No Lectures or Exams",
            "slug": "oxford-mit-ai-native-degree-no-lectures-exams-2026",
            "excerpt": "The three-year programme replaces lectures with AI tutor-guided projects and portfolio assessment.",
            "body": "<p>Oxford University and MIT announced a joint AI-native undergraduate programme that abandons lectures, written examinations, and traditional grading in favour of continuous-assessment built around AI tutors and real-world projects.</p><p>\"The lecture was an efficient technology for transmitting information in a world where books were expensive,\" said Oxford Vice-Chancellor Irene Tracey. \"Neither of those conditions holds today.\"</p>",
            "category": "education", "author": "yemi-adeyemi",
            "read_time": 7, "featured": 1, "status": "published"
        },
        {
            "title": "Digital Detox Residencies Are Fully Booked Through 2027",
            "slug": "digital-detox-residencies-booked-2027-ai-burnout",
            "excerpt": "Luxury connectivity-free retreats for AI-era burnout are charging $8,000 a week and have two-year waiting lists.",
            "body": "<p>In the Swiss Alps, a converted farmhouse operates under a strict protocol: no smartphones, no voice assistants, no ambient AI. Waldhaus Analog has a two-year waiting list and charges EUR 7,400 for seven nights.</p><p>Psychologists call the underlying condition agentic dependency fatigue — <strong>the exhaustion of never being alone with your own thoughts.</strong></p>",
            "category": "lifestyle", "author": "amara-blake",
            "read_time": 6, "featured": 0, "status": "published"
        },
        {
            "title": "AI Underwriting Cuts Motor Insurance Premiums by 30% While Raising Fairness Questions",
            "slug": "ai-underwriting-motor-insurance-30-percent-fairness-2026",
            "excerpt": "Real-time telematics AI prices risk to within metres — but critics warn of insurance redlining 2.0.",
            "body": "<p>For the first time since motor insurance became mandatory, some UK drivers are paying less than GBP 400 per year for comprehensive cover. The cause is AI underwriting using continuous telematics data.</p><p>\"The AI has found proxies for protected characteristics that the law was designed to prohibit — and it can do so <strong>with mathematical precision</strong>,\" said Alice Dearing of the Fair Insurance Network.</p>",
            "category": "insurance", "author": "gail-hutchins",
            "read_time": 6, "featured": 0, "status": "published"
        },
        {
            "title": "India Surpasses China as World's Largest Economy by PPP",
            "slug": "india-surpasses-china-largest-economy-ppp-imf-2026",
            "excerpt": "India's GDP at purchasing power parity has overtaken China's for the first time in modern history.",
            "body": "<p>India has overtaken China to become the world's largest economy measured by purchasing power parity, the IMF confirmed in its June 2026 World Economic Outlook.</p><p>\"India did not inherit this position — <strong>it built it,</strong>\" said IMF Chief Economist Pierre-Olivier Gourinchas.</p>",
            "category": "world", "author": "suresh-krishnamurthy",
            "read_time": 5, "featured": 1, "status": "published"
        },
    ]

    cat_map = {row["slug"]: row["id"] for row in conn.execute("SELECT id, slug FROM categories")}
    auth_map = {row["slug"]: row["id"] for row in conn.execute("SELECT id, slug FROM authors")}

    for a in articles:
        cat_id  = cat_map.get(a["category"])
        auth_id = auth_map.get(a["author"])
        if not cat_id or not auth_id:
            continue
        conn.execute("""
            INSERT OR IGNORE INTO articles
              (title, slug, excerpt, body, category_id, author_id,
               read_time, featured, status, published_at, created_at)
            VALUES (?,?,?,?,?,?,?,?,?,datetime('now'),datetime('now'))
        """, (a["title"], a["slug"], a["excerpt"], a["body"],
              cat_id, auth_id, a["read_time"], a["featured"], a["status"]))
    print("[DB] Sample articles seeded")


if __name__ == "__main__":
    from dotenv import load_dotenv
    load_dotenv()
    init_db()
