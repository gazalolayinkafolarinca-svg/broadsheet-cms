"""
============================================================
THE BROADSHEET CMS — Database Schema & Init (PostgreSQL)
============================================================
"""

import os
import hashlib
import secrets
import psycopg2
import psycopg2.extras
from datetime import datetime, timezone

DATABASE_URL = os.getenv("DATABASE_URL", "")


def get_db():
    """Return a psycopg2 connection with RealDictCursor."""
    conn = psycopg2.connect(DATABASE_URL, cursor_factory=psycopg2.extras.RealDictCursor)
    return conn


def now_iso():
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def hash_password(password: str) -> str:
    salt = secrets.token_hex(32)
    dk = hashlib.pbkdf2_hmac("sha256", password.encode(), salt.encode(), 390000)
    return f"pbkdf2:sha256:390000:{salt}:{dk.hex()}"


def verify_password(password: str, stored_hash: str) -> bool:
    try:
        _, algo, iterations, salt, dk_hex = stored_hash.split(":")
        iterations = int(iterations)
        dk = hashlib.pbkdf2_hmac(algo, password.encode(), salt.encode(), iterations)
        return secrets.compare_digest(dk.hex(), dk_hex)
    except Exception:
        return False


SCHEMA = """
CREATE TABLE IF NOT EXISTS admin_users (
    id            SERIAL PRIMARY KEY,
    email         TEXT    NOT NULL UNIQUE,
    password_hash TEXT    NOT NULL,
    name          TEXT    NOT NULL,
    role          TEXT    NOT NULL DEFAULT 'editor'
                          CHECK(role IN ('superadmin','admin','editor')),
    avatar_url    TEXT,
    is_active     INTEGER NOT NULL DEFAULT 1,
    last_login    TEXT,
    created_at    TEXT    NOT NULL DEFAULT (now()::text),
    updated_at    TEXT    NOT NULL DEFAULT (now()::text)
);

CREATE TABLE IF NOT EXISTS authors (
    id          SERIAL PRIMARY KEY,
    name        TEXT    NOT NULL,
    slug        TEXT    NOT NULL UNIQUE,
    bio         TEXT,
    email       TEXT    UNIQUE,
    avatar_url  TEXT,
    twitter     TEXT,
    linkedin    TEXT,
    is_active   INTEGER NOT NULL DEFAULT 1,
    created_at  TEXT    NOT NULL DEFAULT (now()::text),
    updated_at  TEXT    NOT NULL DEFAULT (now()::text)
);

CREATE TABLE IF NOT EXISTS categories (
    id          SERIAL PRIMARY KEY,
    name        TEXT    NOT NULL UNIQUE,
    slug        TEXT    NOT NULL UNIQUE,
    description TEXT,
    color       TEXT    NOT NULL DEFAULT '#0D0D0D',
    is_active   INTEGER NOT NULL DEFAULT 1,
    sort_order  INTEGER NOT NULL DEFAULT 0,
    created_at  TEXT    NOT NULL DEFAULT (now()::text)
);

CREATE TABLE IF NOT EXISTS tags (
    id         SERIAL PRIMARY KEY,
    name       TEXT NOT NULL UNIQUE,
    slug       TEXT NOT NULL UNIQUE,
    created_at TEXT NOT NULL DEFAULT (now()::text)
);

CREATE TABLE IF NOT EXISTS media (
    id            SERIAL PRIMARY KEY,
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
    created_at    TEXT    NOT NULL DEFAULT (now()::text)
);

CREATE TABLE IF NOT EXISTS articles (
    id               SERIAL PRIMARY KEY,
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
    created_at       TEXT    NOT NULL DEFAULT (now()::text),
    updated_at       TEXT    NOT NULL DEFAULT (now()::text)
);

CREATE TABLE IF NOT EXISTS article_tags (
    article_id INTEGER NOT NULL REFERENCES articles(id) ON DELETE CASCADE,
    tag_id     INTEGER NOT NULL REFERENCES tags(id)     ON DELETE CASCADE,
    PRIMARY KEY (article_id, tag_id)
);

CREATE INDEX IF NOT EXISTS idx_articles_status       ON articles(status);
CREATE INDEX IF NOT EXISTS idx_articles_category     ON articles(category_id);
CREATE INDEX IF NOT EXISTS idx_articles_author       ON articles(author_id);
CREATE INDEX IF NOT EXISTS idx_articles_slug         ON articles(slug);
CREATE INDEX IF NOT EXISTS idx_articles_featured     ON articles(featured);
"""


def init_db():
    conn = get_db()
    cur = conn.cursor()

    # Run each statement separately
    for statement in SCHEMA.strip().split(";"):
        statement = statement.strip()
        if statement:
            cur.execute(statement)

    conn.commit()
    print("[DB] Schema applied")

    _seed_categories(conn, cur)
    _seed_admin(conn, cur)
    _seed_authors(conn, cur)
    _seed_articles(conn, cur)

    conn.commit()
    conn.close()
    print("[DB] Database initialised successfully.")


def _seed_categories(conn, cur):
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
        cur.execute("""
            INSERT INTO categories (name, slug, description, color, sort_order)
            VALUES (%s, %s, %s, %s, %s)
            ON CONFLICT (slug) DO NOTHING
        """, (name, slug, desc, color, order))
    print("[DB] Categories seeded")


def _seed_admin(conn, cur):
    email    = os.getenv("ADMIN_EMAIL", "admin@broadsheet.com")
    password = os.getenv("ADMIN_PASSWORD", "Admin2026!SecurePassword")
    cur.execute("SELECT id FROM admin_users WHERE email=%s", (email,))
    if not cur.fetchone():
        cur.execute("""
            INSERT INTO admin_users (email, password_hash, name, role)
            VALUES (%s, %s, %s, %s)
        """, (email, hash_password(password), "Super Admin", "superadmin"))
        print(f"[DB] Admin user created → {email}")
    else:
        print(f"[DB] Admin user already exists → {email}")


def _seed_authors(conn, cur):
    authors = [
        ("Rebecca Osei",         "rebecca-osei",         "Senior Finance Editor",          "rebecca@broadsheet.com"),
        ("Dmitri Vaskov",        "dmitri-vaskov",         "Crypto & Markets Correspondent", "dmitri@broadsheet.com"),
        ("Lukas Brennan",        "lukas-brennan",         "Politics & Policy Editor",       "lukas@broadsheet.com"),
        ("Priya Mehta",          "priya-mehta",           "B2B Technology Reporter",        "priya@broadsheet.com"),
        ("Dr. Yemi Adeyemi",     "yemi-adeyemi",          "Education Correspondent",        "yemi@broadsheet.com"),
        ("Amara Blake",          "amara-blake",           "Lifestyle & Culture Writer",     "amara@broadsheet.com"),
        ("Gail Hutchins",        "gail-hutchins",         "Insurance Industry Analyst",     "gail@broadsheet.com"),
        ("Suresh Krishnamurthy", "suresh-krishnamurthy",  "World Affairs Correspondent",    "suresh@broadsheet.com"),
    ]
    for name, slug, bio, email in authors:
        cur.execute("""
            INSERT INTO authors (name, slug, bio, email)
            VALUES (%s, %s, %s, %s)
            ON CONFLICT (slug) DO NOTHING
        """, (name, slug, bio, email))
    print("[DB] Authors seeded")


def _seed_articles(conn, cur):
    cur.execute("SELECT COUNT(*) FROM articles")
    result = cur.fetchone()
    count = result["count"] if result else 0
    if count > 0:
        print("[DB] Articles already exist, skipping seed")
        return

    articles = [
        {
            "title": "Global Central Banks Begin Coordinated Pivot as Inflation Hits 1.8%",
            "slug": "global-central-banks-coordinated-pivot-inflation-2026",
            "excerpt": "The Fed, ECB, and Bank of England have all signalled simultaneous rate reductions for Q3 2026.",
            "body": "<p>In a move that surprised many analysts by its synchronicity, the Federal Reserve, European Central Bank, and Bank of England each telegraphed rate cuts within a 72-hour window this week.</p><p>The catalyst is a combination of cooling inflation — US CPI now at <strong>1.8%, its lowest reading since early 2022</strong> — and mounting concerns about growth in advanced economies.</p>",
            "category": "finance", "author": "rebecca-osei",
            "read_time": 6, "featured": 1, "status": "published"
        },
        {
            "title": "Bitcoin Crosses $185,000 as Spot ETF Holdings Surpass 1.2 Million BTC",
            "slug": "bitcoin-185000-spot-etf-1-2-million-btc-2026",
            "excerpt": "Institutional accumulation through BlackRock and Fidelity has absorbed nearly 6% of circulating supply.",
            "body": "<p>Bitcoin set a new all-time high above $185,000 on Tuesday, extending a rally that has now seen the asset more than double from its October 2025 lows.</p><p><strong>Spot ETF products now collectively hold over 1.2 million BTC</strong>, representing approximately 5.7% of the total circulating supply.</p>",
            "category": "finance", "author": "dmitri-vaskov",
            "read_time": 5, "featured": 0, "status": "published"
        },
        {
            "title": "UN Framework on AI Governance Adopted by 141 Nations",
            "slug": "un-ai-governance-framework-141-nations-2026",
            "excerpt": "The landmark resolution establishes a global AI Safety Council and binding transparency requirements.",
            "body": "<p>The United Nations General Assembly voted 141-0 on Thursday to adopt the Nairobi Framework on Artificial Intelligence Governance, with China, Russia, and Belarus abstaining.</p>",
            "category": "politics", "author": "lukas-brennan",
            "read_time": 7, "featured": 1, "status": "published"
        },
        {
            "title": "Salesforce Agentforce Reaches 500,000 Enterprise Deployments",
            "slug": "salesforce-agentforce-500000-enterprise-deployments-2026",
            "excerpt": "Autonomous AI agents that close deals without human intervention are the new baseline for enterprise CRM.",
            "body": "<p>Salesforce announced this week that its Agentforce platform has now been adopted by more than 500,000 enterprise customers.</p>",
            "category": "b2b", "author": "priya-mehta",
            "read_time": 4, "featured": 0, "status": "published"
        },
        {
            "title": "Oxford and MIT Launch Joint AI-Native Degree with No Lectures or Exams",
            "slug": "oxford-mit-ai-native-degree-no-lectures-exams-2026",
            "excerpt": "The three-year programme replaces lectures with AI tutor-guided projects and portfolio assessment.",
            "body": "<p>Oxford University and MIT announced a joint AI-native undergraduate programme that abandons lectures, written examinations, and traditional grading.</p>",
            "category": "education", "author": "yemi-adeyemi",
            "read_time": 7, "featured": 1, "status": "published"
        },
        {
            "title": "Digital Detox Residencies Are Fully Booked Through 2027",
            "slug": "digital-detox-residencies-booked-2027-ai-burnout",
            "excerpt": "Luxury connectivity-free retreats for AI-era burnout are charging $8,000 a week and have two-year waiting lists.",
            "body": "<p>In the Swiss Alps, a converted farmhouse operates under a strict protocol: no smartphones, no voice assistants, no ambient AI. Waldhaus Analog has a two-year waiting list.</p>",
            "category": "lifestyle", "author": "amara-blake",
            "read_time": 6, "featured": 0, "status": "published"
        },
        {
            "title": "AI Underwriting Cuts Motor Insurance Premiums by 30% While Raising Fairness Questions",
            "slug": "ai-underwriting-motor-insurance-30-percent-fairness-2026",
            "excerpt": "Real-time telematics AI prices risk to within metres — but critics warn of insurance redlining 2.0.",
            "body": "<p>For the first time since motor insurance became mandatory, some UK drivers are paying less than GBP 400 per year for comprehensive cover. The cause is AI underwriting using continuous telematics data.</p>",
            "category": "insurance", "author": "gail-hutchins",
            "read_time": 6, "featured": 0, "status": "published"
        },
        {
            "title": "India Surpasses China as World's Largest Economy by PPP",
            "slug": "india-surpasses-china-largest-economy-ppp-imf-2026",
            "excerpt": "India's GDP at purchasing power parity has overtaken China's for the first time in modern history.",
            "body": "<p>India has overtaken China to become the world's largest economy measured by purchasing power parity, the IMF confirmed in its June 2026 World Economic Outlook.</p>",
            "category": "world", "author": "suresh-krishnamurthy",
            "read_time": 5, "featured": 1, "status": "published"
        },
    ]

    cur.execute("SELECT id, slug FROM categories")
    cat_map = {r["slug"]: r["id"] for r in cur.fetchall()}
    cur.execute("SELECT id, slug FROM authors")
    auth_map = {r["slug"]: r["id"] for r in cur.fetchall()}

    for a in articles:
        cat_id  = cat_map.get(a["category"])
        auth_id = auth_map.get(a["author"])
        if not cat_id or not auth_id:
            continue
        cur.execute("""
            INSERT INTO articles
              (title, slug, excerpt, body, category_id, author_id,
               read_time, featured, status, published_at, created_at)
            VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,now()::text,now()::text)
            ON CONFLICT (slug) DO NOTHING
        """, (a["title"], a["slug"], a["excerpt"], a["body"],
              cat_id, auth_id, a["read_time"], a["featured"], a["status"]))
    print("[DB] Sample articles seeded")


if __name__ == "__main__":
    from dotenv import load_dotenv
    load_dotenv()
    init_db()
