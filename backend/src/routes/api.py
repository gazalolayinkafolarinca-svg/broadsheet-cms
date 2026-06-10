"""
============================================================
THE BROADSHEET CMS — API Routes
File: backend/src/routes/api.py

Public endpoints:
  GET  /api/articles              — paginated published articles
  GET  /api/articles/:slug        — single article by slug
  GET  /api/categories            — all active categories
  GET  /api/authors/:slug         — author profile + articles

Admin endpoints (require JWT):
  POST   /api/admin/login
  GET    /api/admin/me
  GET    /api/admin/articles       — all articles (any status)
  POST   /api/admin/articles       — create article
  GET    /api/admin/articles/:id   — single article (admin view)
  PUT    /api/admin/articles/:id   — update article
  DELETE /api/admin/articles/:id   — delete article
  POST   /api/admin/articles/:id/publish
  POST   /api/admin/articles/:id/unpublish
  POST   /api/admin/upload         — image upload
  GET    /api/admin/media          — media library
  POST   /api/admin/ai/generate    — AI draft generation
  GET    /api/admin/stats          — dashboard stats
============================================================
"""

import os
import json
from datetime import datetime, timezone
from flask import Blueprint, request, jsonify, g, after_this_request
from src.database import get_db, hash_password, verify_password
from src.middleware.auth import require_auth, require_role, generate_token
from src.utils.helpers import slugify, estimate_read_time, make_excerpt, paginate, allowed_file

api = Blueprint("api", __name__, url_prefix="/api")


# ════════════════════════════════════════════════════════════
# HELPERS
# ════════════════════════════════════════════════════════════

def row_to_dict(row):
    return dict(row) if row else None


def now_iso():
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def build_article_response(article, db, include_body=True):
    """Enrich an article row with category, author, tags, and media URLs."""
    a = row_to_dict(article)
    if not a:
        return None

    # Category
    cat = db.execute("SELECT id, name, slug, color FROM categories WHERE id=?",
                     (a["category_id"],)).fetchone()
    a["category"] = row_to_dict(cat)

    # Author
    author = db.execute(
        "SELECT id, name, slug, bio, avatar_url, twitter, linkedin FROM authors WHERE id=?",
        (a["author_id"],)
    ).fetchone()
    a["author"] = row_to_dict(author)

    # Tags
    tags = db.execute("""
        SELECT t.id, t.name, t.slug FROM tags t
        JOIN article_tags at ON at.tag_id = t.id
        WHERE at.article_id = ?
    """, (a["id"],)).fetchall()
    a["tags"] = [row_to_dict(t) for t in tags]

    # Featured image
    if a.get("featured_image"):
        img = db.execute("SELECT id, url, thumbnail_url, alt_text, width, height FROM media WHERE id=?",
                         (a["featured_image"],)).fetchone()
        a["featured_image"] = row_to_dict(img)
    else:
        # Fall back to a deterministic picsum image for seeded articles
        seed = a["id"] * 7
        a["featured_image"] = {
            "url": f"https://picsum.photos/seed/{seed}/1200/630",
            "thumbnail_url": f"https://picsum.photos/seed/{seed}/600/400",
            "alt_text": a["title"]
        }

    if not include_body:
        a.pop("body", None)

    return a


# ════════════════════════════════════════════════════════════
# PUBLIC — AUTH
# ════════════════════════════════════════════════════════════

@api.post("/admin/login")
def admin_login():
    data = request.get_json(silent=True) or {}
    email = (data.get("email") or "").strip().lower()
    password = data.get("password") or ""

    if not email or not password:
        return jsonify({"error": "Email and password required"}), 400

    db = get_db()
    user = db.execute(
        "SELECT * FROM admin_users WHERE email=? AND is_active=1",
        (email,)
    ).fetchone()
    db.close()

    if not user or not verify_password(password, user["password_hash"]):
        return jsonify({"error": "Invalid credentials"}), 401

    # Update last login
    db2 = get_db()
    db2.execute("UPDATE admin_users SET last_login=? WHERE id=?", (now_iso(), user["id"]))
    db2.commit()
    db2.close()

    token = generate_token(user["id"], user["email"], user["role"])
    return jsonify({
        "token": token,
        "user": {
            "id": user["id"],
            "email": user["email"],
            "name": user["name"],
            "role": user["role"],
            "avatar_url": user["avatar_url"],
        }
    })


@api.get("/admin/me")
@require_auth
def admin_me():
    return jsonify({"user": g.user})


# ════════════════════════════════════════════════════════════
# PUBLIC — ARTICLES
# ════════════════════════════════════════════════════════════

@api.get("/articles")
def get_articles():
    """Paginated published articles with optional category/search filters."""
    page     = max(1, int(request.args.get("page", 1)))
    per_page = min(50, max(1, int(request.args.get("per_page", 12))))
    category = request.args.get("category", "").strip().lower()
    search   = request.args.get("search",   "").strip()
    featured = request.args.get("featured", "").strip()
    sort     = request.args.get("sort", "newest")  # newest | oldest | popular

    db = get_db()

    sql = """
        SELECT a.* FROM articles a
        JOIN categories c ON c.id = a.category_id
        WHERE a.status = 'published'
          AND (a.scheduled_at IS NULL OR a.scheduled_at <= datetime('now'))
    """
    params = []

    if category:
        sql += " AND c.slug = ?"
        params.append(category)

    if search:
        sql += " AND (a.title LIKE ? OR a.excerpt LIKE ?)"
        params += [f"%{search}%", f"%{search}%"]

    if featured == "1":
        sql += " AND a.featured = 1"

    order_map = {
        "newest":  "a.published_at DESC",
        "oldest":  "a.published_at ASC",
        "popular": "a.view_count DESC",
    }
    sql += f" ORDER BY {order_map.get(sort, 'a.published_at DESC')}"

    rows = db.execute(sql, params).fetchall()
    total = len(rows)

    # Manual pagination on enriched results
    offset = (page - 1) * per_page
    page_rows = rows[offset: offset + per_page]
    articles = [build_article_response(r, db, include_body=False) for r in page_rows]
    db.close()

    import math
    return jsonify({
        "articles": articles,
        "pagination": {
            "page": page,
            "per_page": per_page,
            "total": total,
            "total_pages": math.ceil(total / per_page) if total else 1,
            "has_next": (page * per_page) < total,
            "has_prev": page > 1,
        }
    })


@api.get("/articles/<slug>")
def get_article(slug):
    db = get_db()
    row = db.execute(
        "SELECT * FROM articles WHERE slug=? AND status='published'", (slug,)
    ).fetchone()
    if not row:
        db.close()
        return jsonify({"error": "Article not found"}), 404

    article = build_article_response(row, db, include_body=True)

    # Related articles (same category, exclude self)
    related_rows = db.execute("""
        SELECT * FROM articles
        WHERE category_id=? AND id!=? AND status='published'
        ORDER BY published_at DESC LIMIT 3
    """, (row["category_id"], row["id"])).fetchall()
    article["related"] = [build_article_response(r, db, include_body=False) for r in related_rows]

    db.close()

    # Increment view count AFTER response is sent so the DB write
    # does not trigger VS Code Live Server to refresh the browser
    article_id = row["id"]

    @after_this_request
    def bump_view_count(response):
        try:
            _db = get_db()
            _db.execute("UPDATE articles SET view_count = view_count + 1 WHERE id=?", (article_id,))
            _db.commit()
            _db.close()
        except Exception:
            pass
        return response

    return jsonify({"article": article})


# ════════════════════════════════════════════════════════════
# PUBLIC — CATEGORIES & AUTHORS
# ════════════════════════════════════════════════════════════

@api.get("/categories")
def get_categories():
    db = get_db()
    rows = db.execute(
        "SELECT * FROM categories WHERE is_active=1 ORDER BY sort_order"
    ).fetchall()
    db.close()
    return jsonify({"categories": [row_to_dict(r) for r in rows]})


@api.get("/authors/<slug>")
def get_author(slug):
    db = get_db()
    author = db.execute("SELECT * FROM authors WHERE slug=?", (slug,)).fetchone()
    if not author:
        db.close()
        return jsonify({"error": "Author not found"}), 404
    articles = db.execute("""
        SELECT a.id, a.title, a.slug, a.excerpt, a.published_at, a.read_time,
               a.featured_image, c.name as category_name, c.slug as category_slug, c.color
        FROM articles a JOIN categories c ON c.id = a.category_id
        WHERE a.author_id=? AND a.status='published'
        ORDER BY a.published_at DESC LIMIT 10
    """, (author["id"],)).fetchall()
    db.close()
    return jsonify({
        "author": row_to_dict(author),
        "articles": [row_to_dict(r) for r in articles]
    })


# ════════════════════════════════════════════════════════════
# ADMIN — ARTICLE CRUD
# ════════════════════════════════════════════════════════════

@api.get("/admin/articles")
@require_auth
def admin_list_articles():
    page     = max(1, int(request.args.get("page", 1)))
    per_page = min(50, max(1, int(request.args.get("per_page", 20))))
    status   = request.args.get("status", "")
    category = request.args.get("category", "")
    search   = request.args.get("search", "")

    db = get_db()
    sql = """
        SELECT a.id, a.title, a.slug, a.status, a.featured, a.read_time,
               a.view_count, a.ai_generated, a.published_at, a.scheduled_at,
               a.created_at, a.updated_at,
               au.name as author_name, c.name as category_name, c.slug as category_slug,
               c.color as category_color
        FROM articles a
        JOIN authors au ON au.id = a.author_id
        JOIN categories c ON c.id = a.category_id
        WHERE 1=1
    """
    params = []
    if status:
        sql += " AND a.status=?"
        params.append(status)
    if category:
        sql += " AND c.slug=?"
        params.append(category)
    if search:
        sql += " AND (a.title LIKE ? OR a.excerpt LIKE ?)"
        params += [f"%{search}%", f"%{search}%"]

    sql += " ORDER BY a.updated_at DESC"

    import math
    rows = db.execute(sql, params).fetchall()
    total = len(rows)
    offset = (page - 1) * per_page
    page_rows = rows[offset: offset + per_page]
    db.close()

    return jsonify({
        "articles": [row_to_dict(r) for r in page_rows],
        "pagination": {
            "page": page, "per_page": per_page, "total": total,
            "total_pages": math.ceil(total / per_page) if total else 1,
        }
    })


@api.get("/admin/articles/<int:article_id>")
@require_auth
def admin_get_article(article_id):
    db = get_db()
    row = db.execute("SELECT * FROM articles WHERE id=?", (article_id,)).fetchone()
    if not row:
        db.close()
        return jsonify({"error": "Not found"}), 404
    article = build_article_response(row, db, include_body=True)
    db.close()
    return jsonify({"article": article})


@api.post("/admin/articles")
@require_auth
def admin_create_article():
    data = request.get_json(silent=True) or {}

    title   = (data.get("title") or "").strip()
    body    = (data.get("body") or "").strip()
    status  = data.get("status", "draft")

    if not title:
        return jsonify({"error": "Title is required"}), 400
    if status not in ("draft", "review", "published", "archived"):
        return jsonify({"error": "Invalid status"}), 400

    db = get_db()

    # Resolve category
    cat_slug = data.get("category_slug", "world")
    cat = db.execute("SELECT id FROM categories WHERE slug=?", (cat_slug,)).fetchone()
    if not cat:
        db.close()
        return jsonify({"error": f"Category '{cat_slug}' not found"}), 400

    # Resolve author
    author_slug = data.get("author_slug", "")
    author = db.execute("SELECT id FROM authors WHERE slug=?", (author_slug,)).fetchone() if author_slug else None
    if not author:
        author = db.execute("SELECT id FROM authors LIMIT 1").fetchone()
    if not author:
        db.close()
        return jsonify({"error": "No authors found — seed the database first"}), 400

    # Build slug (ensure uniqueness)
    base_slug = slugify(title)
    final_slug = base_slug
    counter = 1
    while db.execute("SELECT id FROM articles WHERE slug=?", (final_slug,)).fetchone():
        final_slug = f"{base_slug}-{counter}"
        counter += 1

    excerpt    = data.get("excerpt") or make_excerpt(body)
    read_time  = estimate_read_time(body) if body else 1
    featured   = 1 if data.get("featured") else 0
    published_at = now_iso() if status == "published" else None
    scheduled_at = data.get("scheduled_at")

    cursor = db.execute("""
        INSERT INTO articles
          (title, slug, excerpt, body, status, author_id, category_id,
           featured, read_time, seo_title, seo_description,
           ai_generated, ai_topic_prompt,
           scheduled_at, published_at, created_by, updated_by)
        VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
    """, (
        title, final_slug, excerpt, body, status,
        author["id"], cat["id"], featured, read_time,
        data.get("seo_title") or title,
        data.get("seo_description") or excerpt,
        1 if data.get("ai_generated") else 0,
        data.get("ai_topic_prompt"),
        scheduled_at, published_at,
        g.user["id"], g.user["id"]
    ))

    article_id = cursor.lastrowid

    # Tags
    tags = data.get("tags", [])
    _sync_tags(db, article_id, tags)

    db.commit()
    row = db.execute("SELECT * FROM articles WHERE id=?", (article_id,)).fetchone()
    article = build_article_response(row, db, include_body=True)
    db.close()

    return jsonify({"article": article, "message": "Article created"}), 201


@api.put("/admin/articles/<int:article_id>")
@require_auth
def admin_update_article(article_id):
    db = get_db()
    row = db.execute("SELECT * FROM articles WHERE id=?", (article_id,)).fetchone()
    if not row:
        db.close()
        return jsonify({"error": "Not found"}), 404

    data   = request.get_json(silent=True) or {}
    fields = {}

    if "title" in data and data["title"].strip():
        fields["title"] = data["title"].strip()

    if "body" in data:
        fields["body"] = data["body"]
        fields["read_time"] = estimate_read_time(data["body"])

    if "excerpt" in data:
        fields["excerpt"] = data["excerpt"]
    elif "body" in data and not data.get("excerpt"):
        fields["excerpt"] = make_excerpt(data["body"])

    if "status" in data and data["status"] in ("draft","review","published","archived"):
        fields["status"] = data["status"]
        if data["status"] == "published" and not row["published_at"]:
            fields["published_at"] = now_iso()

    if "scheduled_at" in data:
        fields["scheduled_at"] = data["scheduled_at"]

    if "featured" in data:
        fields["featured"] = 1 if data["featured"] else 0

    if "category_slug" in data:
        cat = db.execute("SELECT id FROM categories WHERE slug=?", (data["category_slug"],)).fetchone()
        if cat:
            fields["category_id"] = cat["id"]

    if "author_slug" in data:
        author = db.execute("SELECT id FROM authors WHERE slug=?", (data["author_slug"],)).fetchone()
        if author:
            fields["author_id"] = author["id"]

    for seo_field in ("seo_title","seo_description","og_title","og_description"):
        if seo_field in data:
            fields[seo_field] = data[seo_field]

    if "featured_image_id" in data:
        fields["featured_image"] = data["featured_image_id"]

    fields["updated_by"] = g.user["id"]

    if fields:
        set_clause = ", ".join(f"{k}=?" for k in fields)
        db.execute(f"UPDATE articles SET {set_clause} WHERE id=?",
                   list(fields.values()) + [article_id])

    if "tags" in data:
        _sync_tags(db, article_id, data["tags"])

    db.commit()
    updated = db.execute("SELECT * FROM articles WHERE id=?", (article_id,)).fetchone()
    article = build_article_response(updated, db, include_body=True)
    db.close()

    return jsonify({"article": article, "message": "Article updated"})


@api.delete("/admin/articles/<int:article_id>")
@require_role("admin", "superadmin")
def admin_delete_article(article_id):
    db = get_db()
    row = db.execute("SELECT id, title FROM articles WHERE id=?", (article_id,)).fetchone()
    if not row:
        db.close()
        return jsonify({"error": "Not found"}), 404
    db.execute("DELETE FROM article_tags WHERE article_id=?", (article_id,))
    db.execute("DELETE FROM articles WHERE id=?", (article_id,))
    db.commit()
    db.close()
    return jsonify({"message": f"Article '{row['title']}' deleted"})


@api.post("/admin/articles/<int:article_id>/publish")
@require_auth
def admin_publish_article(article_id):
    db = get_db()
    row = db.execute("SELECT * FROM articles WHERE id=?", (article_id,)).fetchone()
    if not row:
        db.close()
        return jsonify({"error": "Not found"}), 404
    db.execute(
        "UPDATE articles SET status='published', published_at=?, updated_by=? WHERE id=?",
        (now_iso(), g.user["id"], article_id)
    )
    db.commit()
    db.close()
    return jsonify({"message": "Article published"})


@api.post("/admin/articles/<int:article_id>/unpublish")
@require_auth
def admin_unpublish_article(article_id):
    db = get_db()
    db.execute(
        "UPDATE articles SET status='draft', updated_by=? WHERE id=?",
        (g.user["id"], article_id)
    )
    db.commit()
    db.close()
    return jsonify({"message": "Article moved back to draft"})


# ════════════════════════════════════════════════════════════
# ADMIN — MEDIA UPLOAD
# ════════════════════════════════════════════════════════════

@api.post("/admin/upload")
@require_auth
def admin_upload():
    if "file" not in request.files:
        return jsonify({"error": "No file provided"}), 400

    file = request.files["file"]
    if not file.filename or not allowed_file(file.filename):
        return jsonify({"error": "Invalid file type. Allowed: png, jpg, jpeg, webp, gif"}), 400

    import uuid, os
    from PIL import Image
    import io

    max_mb = int(os.getenv("MAX_IMAGE_SIZE_MB", "10"))
    file_bytes = file.read()
    if len(file_bytes) > max_mb * 1024 * 1024:
        return jsonify({"error": f"File too large (max {max_mb}MB)"}), 400

    ext = file.filename.rsplit(".", 1)[1].lower()
    unique_name = f"{uuid.uuid4().hex}.{ext}"
    thumb_name  = f"thumb_{unique_name}"

    upload_dir = os.path.join(os.getcwd(), os.getenv("UPLOAD_FOLDER", "uploads"), "images")
    thumb_dir  = os.path.join(os.getcwd(), os.getenv("UPLOAD_FOLDER", "uploads"), "thumbnails")
    os.makedirs(upload_dir, exist_ok=True)
    os.makedirs(thumb_dir,  exist_ok=True)

    # Save original
    filepath = os.path.join(upload_dir, unique_name)
    with open(filepath, "wb") as f:
        f.write(file_bytes)

    # Create thumbnail + get dimensions
    try:
        img = Image.open(io.BytesIO(file_bytes))
        width, height = img.size
        img.thumbnail((600, 400))
        img.save(os.path.join(thumb_dir, thumb_name))
    except Exception:
        width, height = None, None
        thumb_name = unique_name

    url       = f"/uploads/images/{unique_name}"
    thumb_url = f"/uploads/thumbnails/{thumb_name}"

    db = get_db()
    cursor = db.execute("""
        INSERT INTO media (filename, original_name, mime_type, size_bytes, width, height,
                           url, thumbnail_url, alt_text, uploaded_by)
        VALUES (?,?,?,?,?,?,?,?,?,?)
    """, (unique_name, file.filename, file.content_type or "image/jpeg",
          len(file_bytes), width, height, url, thumb_url,
          request.form.get("alt_text", ""), g.user["id"]))
    db.commit()

    media_id = cursor.lastrowid
    row = db.execute("SELECT * FROM media WHERE id=?", (media_id,)).fetchone()
    db.close()

    return jsonify({"media": row_to_dict(row), "message": "Upload successful"}), 201


@api.get("/admin/media")
@require_auth
def admin_media_library():
    page     = max(1, int(request.args.get("page", 1)))
    per_page = 24
    db = get_db()
    rows = db.execute(
        "SELECT * FROM media ORDER BY created_at DESC"
    ).fetchall()
    db.close()
    total  = len(rows)
    offset = (page - 1) * per_page
    import math
    return jsonify({
        "media": [row_to_dict(r) for r in rows[offset:offset+per_page]],
        "pagination": {
            "page": page, "per_page": per_page, "total": total,
            "total_pages": math.ceil(total / per_page) if total else 1
        }
    })


# ════════════════════════════════════════════════════════════
# ADMIN — AI GENERATION
# ════════════════════════════════════════════════════════════

@api.post("/admin/ai/generate")
@require_auth
def admin_ai_generate():
    """
    Generate an article draft using Claude (Anthropic API).
    Body: { topic, category_slug, author_slug, tone?, word_count? }
    """
    data        = request.get_json(silent=True) or {}
    topic       = (data.get("topic") or "").strip()
    cat_slug    = data.get("category_slug", "world")
    author_slug = data.get("author_slug", "")
    tone        = data.get("tone", "authoritative and informative")
    word_count  = min(1200, max(300, int(data.get("word_count", 700))))

    if not topic:
        return jsonify({"error": "topic is required"}), 400

    api_key = os.getenv("GROQ_API_KEY", "") or os.getenv("ANTHROPIC_API_KEY", "")
    if not api_key or api_key == "your-anthropic-api-key-here":
        return jsonify({"error": "AI API key not configured in .env"}), 503

    import urllib.request
    import urllib.error

    # Get category context
    db = get_db()
    cat = db.execute("SELECT * FROM categories WHERE slug=?", (cat_slug,)).fetchone()
    db.close()
    cat_name = cat["name"] if cat else cat_slug

    system_prompt = f"""You are a senior journalist at The Broadsheet, a prestigious news publication.
Write authoritative, well-researched articles in 2026 context.
Tone: {tone}.
Always write in HTML using <p>, <strong>, <em> tags only.
Do not include <html>, <head>, <body>, or <h1> tags — body paragraphs only.
Start directly with the first paragraph. No introductory phrases like "Here is..." or "Certainly...".
Return ONLY valid JSON with this exact structure (no markdown, no backticks):
{{
  "title": "Article headline here",
  "excerpt": "One-sentence summary under 200 characters",
  "body": "<p>Full article HTML body here...</p>",
  "seo_title": "SEO-optimised title",
  "seo_description": "Meta description under 160 characters",
  "tags": ["tag1", "tag2", "tag3"]
}}"""

    user_prompt = f"""Write a {word_count}-word news article for the {cat_name} section about:

{topic}

The article should feel current (published June 2026), cite realistic statistics and named sources,
and include 3-5 substantial paragraphs. Make it compelling and professionally written."""

    # Use Groq API (OpenAI-compatible)
    payload = json.dumps({
        "model": "llama-3.3-70b-versatile",
        "max_tokens": 2000,
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt}
        ]
    }).encode()

    req = urllib.request.Request(
        "https://api.groq.com/openai/v1/chat/completions",
        data=payload,
        headers={
            "Authorization": f"Bearer {api_key}",
            "content-type": "application/json"
        },
        method="POST"
    )

    try:
        with urllib.request.urlopen(req, timeout=60) as resp:
            response_data = json.loads(resp.read().decode())
    except urllib.error.HTTPError as e:
        err_body = e.read().decode()
        return jsonify({"error": f"Groq API error: {e.code}", "detail": err_body}), 502
    except Exception as e:
        return jsonify({"error": f"Request failed: {str(e)}"}), 502

    # Extract text from Groq response (OpenAI format)
    raw_text = ""
    try:
        raw_text = response_data["choices"][0]["message"]["content"]
    except (KeyError, IndexError):
        return jsonify({"error": "Empty response from AI"}), 502

    # Parse JSON from AI response
    raw_text = raw_text.strip()
    if raw_text.startswith("```"):
        raw_text = re.sub(r"^```[a-z]*\n?", "", raw_text)
        raw_text = re.sub(r"\n?```$", "", raw_text)

    try:
        import re
        generated = json.loads(raw_text)
    except json.JSONDecodeError:
        return jsonify({
            "error": "AI returned malformed JSON",
            "raw": raw_text[:500]
        }), 502

    # Save as draft article
    db = get_db()
    cat_row = db.execute("SELECT id FROM categories WHERE slug=?", (cat_slug,)).fetchone()
    if not cat_row:
        db.close()
        return jsonify({"error": f"Category '{cat_slug}' not found"}), 400

    author = db.execute("SELECT id FROM authors WHERE slug=?", (author_slug,)).fetchone() if author_slug else None
    if not author:
        author = db.execute("SELECT id FROM authors LIMIT 1").fetchone()

    title      = generated.get("title", topic)
    base_slug  = slugify(title)
    final_slug = base_slug
    counter    = 1
    while db.execute("SELECT id FROM articles WHERE slug=?", (final_slug,)).fetchone():
        final_slug = f"{base_slug}-{counter}"
        counter   += 1

    body      = generated.get("body", "")
    read_time = estimate_read_time(body)

    cursor = db.execute("""
        INSERT INTO articles
          (title, slug, excerpt, body, status, author_id, category_id,
           read_time, seo_title, seo_description,
           ai_generated, ai_topic_prompt, created_by, updated_by)
        VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)
    """, (
        title, final_slug,
        generated.get("excerpt", make_excerpt(body)),
        body, "draft",
        author["id"], cat_row["id"], read_time,
        generated.get("seo_title", title),
        generated.get("seo_description", ""),
        1, topic,
        g.user["id"], g.user["id"]
    ))

    article_id = cursor.lastrowid
    _sync_tags(db, article_id, generated.get("tags", []))

    db.commit()
    row = db.execute("SELECT * FROM articles WHERE id=?", (article_id,)).fetchone()
    article = build_article_response(row, db, include_body=True)
    db.close()

    return jsonify({
        "article": article,
        "message": "AI draft created — review and publish when ready"
    }), 201


# ════════════════════════════════════════════════════════════
# ADMIN — DASHBOARD STATS
# ════════════════════════════════════════════════════════════

@api.get("/admin/stats")
@require_auth
def admin_stats():
    db = get_db()
    stats = {
        "total_articles":     db.execute("SELECT COUNT(*) FROM articles").fetchone()[0],
        "published_articles": db.execute("SELECT COUNT(*) FROM articles WHERE status='published'").fetchone()[0],
        "draft_articles":     db.execute("SELECT COUNT(*) FROM articles WHERE status='draft'").fetchone()[0],
        "review_articles":    db.execute("SELECT COUNT(*) FROM articles WHERE status='review'").fetchone()[0],
        "scheduled_articles": db.execute("SELECT COUNT(*) FROM articles WHERE status='published' AND scheduled_at > datetime('now')").fetchone()[0],
        "ai_generated":       db.execute("SELECT COUNT(*) FROM articles WHERE ai_generated=1").fetchone()[0],
        "total_authors":      db.execute("SELECT COUNT(*) FROM authors WHERE is_active=1").fetchone()[0],
        "total_categories":   db.execute("SELECT COUNT(*) FROM categories WHERE is_active=1").fetchone()[0],
        "total_views":        db.execute("SELECT COALESCE(SUM(view_count),0) FROM articles WHERE status='published'").fetchone()[0],
        "recent_articles": [
            row_to_dict(r) for r in db.execute("""
                SELECT a.id, a.title, a.slug, a.status, a.ai_generated,
                       a.published_at, a.view_count, c.name as category_name, c.color,
                       au.name as author_name
                FROM articles a
                JOIN categories c ON c.id=a.category_id
                JOIN authors au ON au.id=a.author_id
                ORDER BY a.updated_at DESC LIMIT 8
            """).fetchall()
        ]
    }
    db.close()
    return jsonify({"stats": stats})


# ════════════════════════════════════════════════════════════
# ADMIN — AUTHORS & CATEGORIES MANAGEMENT
# ════════════════════════════════════════════════════════════

@api.get("/admin/authors")
@require_auth
def admin_list_authors():
    db = get_db()
    rows = db.execute("SELECT * FROM authors ORDER BY name").fetchall()
    db.close()
    return jsonify({"authors": [row_to_dict(r) for r in rows]})


@api.post("/admin/authors")
@require_role("admin", "superadmin")
def admin_create_author():
    data = request.get_json(silent=True) or {}
    name = (data.get("name") or "").strip()
    if not name:
        return jsonify({"error": "Name required"}), 400
    slug = slugify(name)
    db = get_db()
    try:
        cursor = db.execute(
            "INSERT INTO authors (name, slug, bio, email, twitter, linkedin) VALUES (?,?,?,?,?,?)",
            (name, slug, data.get("bio",""), data.get("email",""),
             data.get("twitter",""), data.get("linkedin",""))
        )
        db.commit()
        row = db.execute("SELECT * FROM authors WHERE id=?", (cursor.lastrowid,)).fetchone()
        db.close()
        return jsonify({"author": row_to_dict(row)}), 201
    except Exception as e:
        db.close()
        return jsonify({"error": str(e)}), 400


@api.get("/admin/categories")
@require_auth
def admin_list_categories():
    db = get_db()
    rows = db.execute("SELECT * FROM categories ORDER BY sort_order").fetchall()
    db.close()
    return jsonify({"categories": [row_to_dict(r) for r in rows]})


# ════════════════════════════════════════════════════════════
# HELPERS
# ════════════════════════════════════════════════════════════

def _sync_tags(db, article_id: int, tag_names: list):
    """Create tags if needed, sync article_tags join table."""
    db.execute("DELETE FROM article_tags WHERE article_id=?", (article_id,))
    for name in tag_names:
        name = str(name).strip()
        if not name:
            continue
        slug = slugify(name)
        existing = db.execute("SELECT id FROM tags WHERE slug=?", (slug,)).fetchone()
        if existing:
            tag_id = existing["id"]
        else:
            cur = db.execute("INSERT OR IGNORE INTO tags (name, slug) VALUES (?,?)", (name, slug))
            tag_id = cur.lastrowid or db.execute("SELECT id FROM tags WHERE slug=?", (slug,)).fetchone()["id"]
        db.execute("INSERT OR IGNORE INTO article_tags (article_id, tag_id) VALUES (?,?)",
                   (article_id, tag_id))
