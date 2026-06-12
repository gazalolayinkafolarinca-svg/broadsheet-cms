"""
============================================================
THE BROADSHEET CMS — API Routes (PostgreSQL version)
============================================================
"""

import os
import re
import json
import math
from datetime import datetime, timezone
from flask import Blueprint, request, jsonify, g, after_this_request
from src.database import get_db, hash_password, verify_password, now_iso
from src.middleware.auth import require_auth, require_role, generate_token
from src.utils.helpers import slugify, estimate_read_time, make_excerpt, paginate, allowed_file

api = Blueprint("api", __name__, url_prefix="/api")


# ════════════════════════════════════════════════════════════
# HELPERS
# ════════════════════════════════════════════════════════════

def row_to_dict(row):
    return dict(row) if row else None


def fetchone(conn, sql, params=()):
    cur = conn.cursor()
    cur.execute(sql, params)
    return cur.fetchone()


def fetchall(conn, sql, params=()):
    cur = conn.cursor()
    cur.execute(sql, params)
    return cur.fetchall()


def execute(conn, sql, params=()):
    cur = conn.cursor()
    cur.execute(sql, params)
    return cur


def build_article_response(article, conn, include_body=True):
    a = row_to_dict(article)
    if not a:
        return None

    cat = fetchone(conn, "SELECT id, name, slug, color FROM categories WHERE id=%s", (a["category_id"],))
    a["category"] = row_to_dict(cat)

    author = fetchone(conn,
        "SELECT id, name, slug, bio, avatar_url, twitter, linkedin FROM authors WHERE id=%s",
        (a["author_id"],))
    a["author"] = row_to_dict(author)

    tags = fetchall(conn, """
        SELECT t.id, t.name, t.slug FROM tags t
        JOIN article_tags at2 ON at2.tag_id = t.id
        WHERE at2.article_id = %s
    """, (a["id"],))
    a["tags"] = [row_to_dict(t) for t in tags]

    if a.get("featured_image"):
        img = fetchone(conn,
            "SELECT id, url, thumbnail_url, alt_text, width, height FROM media WHERE id=%s",
            (a["featured_image"],))
        a["featured_image"] = row_to_dict(img)
    else:
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
    email    = (data.get("email") or "").strip().lower()
    password = data.get("password") or ""

    if not email or not password:
        return jsonify({"error": "Email and password required"}), 400

    conn = get_db()
    user = fetchone(conn,
        "SELECT * FROM admin_users WHERE LOWER(email)=%s AND is_active=1", (email,))
    if not user or not verify_password(password, user["password_hash"]):
        conn.close()
        return jsonify({"error": "Invalid credentials"}), 401

    execute(conn, "UPDATE admin_users SET last_login=%s WHERE id=%s", (now_iso(), user["id"]))
    conn.commit()
    conn.close()

    token = generate_token(user["id"], user["email"], user["role"])
    return jsonify({
        "token": token,
        "user": {
            "id": user["id"], "email": user["email"],
            "name": user["name"], "role": user["role"],
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
    page     = max(1, int(request.args.get("page", 1)))
    per_page = min(50, max(1, int(request.args.get("per_page", 12))))
    category = request.args.get("category", "").strip().lower()
    search   = request.args.get("search",   "").strip()
    featured = request.args.get("featured", "").strip()
    sort     = request.args.get("sort", "newest")

    conn = get_db()

    sql = """
        SELECT a.* FROM articles a
        JOIN categories c ON c.id = a.category_id
        WHERE a.status = 'published'
    """
    params = []

    if category:
        sql += " AND c.slug = %s"
        params.append(category)

    if search:
        sql += " AND (a.title ILIKE %s OR a.excerpt ILIKE %s)"
        params += [f"%{search}%", f"%{search}%"]

    if featured == "1":
        sql += " AND a.featured = 1"

    order_map = {
        "newest":  "a.published_at DESC",
        "oldest":  "a.published_at ASC",
        "popular": "a.view_count DESC",
    }
    sql += f" ORDER BY {order_map.get(sort, 'a.published_at DESC')}"

    rows = fetchall(conn, sql, params)
    total = len(rows)

    offset    = (page - 1) * per_page
    page_rows = rows[offset: offset + per_page]
    articles  = [build_article_response(r, conn, include_body=False) for r in page_rows]
    conn.close()

    return jsonify({
        "articles": articles,
        "pagination": {
            "page": page, "per_page": per_page, "total": total,
            "total_pages": math.ceil(total / per_page) if total else 1,
            "has_next": (page * per_page) < total,
            "has_prev": page > 1,
        }
    })


@api.get("/articles/<slug>")
def get_article(slug):
    conn = get_db()
    row = fetchone(conn,
        "SELECT * FROM articles WHERE slug=%s AND status='published'", (slug,))
    if not row:
        conn.close()
        return jsonify({"error": "Article not found"}), 404

    article = build_article_response(row, conn, include_body=True)

    related_rows = fetchall(conn, """
        SELECT * FROM articles
        WHERE category_id=%s AND id!=%s AND status='published'
        ORDER BY published_at DESC LIMIT 3
    """, (row["category_id"], row["id"]))
    article["related"] = [build_article_response(r, conn, include_body=False) for r in related_rows]

    conn.close()

    article_id = row["id"]

    @after_this_request
    def bump_view_count(response):
        try:
            _conn = get_db()
            execute(_conn, "UPDATE articles SET view_count = view_count + 1 WHERE id=%s", (article_id,))
            _conn.commit()
            _conn.close()
        except Exception:
            pass
        return response

    return jsonify({"article": article})


# ════════════════════════════════════════════════════════════
# PUBLIC — CATEGORIES & AUTHORS
# ════════════════════════════════════════════════════════════

@api.get("/categories")
def get_categories():
    conn = get_db()
    rows = fetchall(conn, "SELECT * FROM categories WHERE is_active=1 ORDER BY sort_order")
    conn.close()
    return jsonify({"categories": [row_to_dict(r) for r in rows]})


@api.get("/authors/<slug>")
def get_author(slug):
    conn = get_db()
    author = fetchone(conn, "SELECT * FROM authors WHERE slug=%s", (slug,))
    if not author:
        conn.close()
        return jsonify({"error": "Author not found"}), 404
    articles = fetchall(conn, """
        SELECT a.id, a.title, a.slug, a.excerpt, a.published_at, a.read_time,
               a.featured_image, c.name as category_name, c.slug as category_slug, c.color
        FROM articles a JOIN categories c ON c.id = a.category_id
        WHERE a.author_id=%s AND a.status='published'
        ORDER BY a.published_at DESC LIMIT 10
    """, (author["id"],))
    conn.close()
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

    conn = get_db()
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
        sql += " AND a.status=%s"
        params.append(status)
    if category:
        sql += " AND c.slug=%s"
        params.append(category)
    if search:
        sql += " AND (a.title ILIKE %s OR a.excerpt ILIKE %s)"
        params += [f"%{search}%", f"%{search}%"]

    sql += " ORDER BY a.updated_at DESC"

    rows  = fetchall(conn, sql, params)
    total = len(rows)
    offset    = (page - 1) * per_page
    page_rows = rows[offset: offset + per_page]
    conn.close()

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
    conn = get_db()
    row = fetchone(conn, "SELECT * FROM articles WHERE id=%s", (article_id,))
    if not row:
        conn.close()
        return jsonify({"error": "Not found"}), 404
    article = build_article_response(row, conn, include_body=True)
    conn.close()
    return jsonify({"article": article})


@api.post("/admin/articles")
@require_auth
def admin_create_article():
    data   = request.get_json(silent=True) or {}
    title  = (data.get("title") or "").strip()
    body   = (data.get("body") or "").strip()
    status = data.get("status", "draft")

    if not title:
        return jsonify({"error": "Title is required"}), 400
    if status not in ("draft", "review", "published", "archived"):
        return jsonify({"error": "Invalid status"}), 400

    conn = get_db()

    cat_slug = data.get("category_slug", "world")
    cat = fetchone(conn, "SELECT id FROM categories WHERE slug=%s", (cat_slug,))
    if not cat:
        conn.close()
        return jsonify({"error": f"Category '{cat_slug}' not found"}), 400

    author_slug = data.get("author_slug", "")
    author = fetchone(conn, "SELECT id FROM authors WHERE slug=%s", (author_slug,)) if author_slug else None
    if not author:
        author = fetchone(conn, "SELECT id FROM authors LIMIT 1")
    if not author:
        conn.close()
        return jsonify({"error": "No authors found"}), 400

    base_slug  = slugify(title)
    final_slug = base_slug
    counter    = 1
    while fetchone(conn, "SELECT id FROM articles WHERE slug=%s", (final_slug,)):
        final_slug = f"{base_slug}-{counter}"
        counter += 1

    excerpt      = data.get("excerpt") or make_excerpt(body)
    read_time    = estimate_read_time(body) if body else 1
    featured     = 1 if data.get("featured") else 0
    published_at = now_iso() if status == "published" else None
    scheduled_at = data.get("scheduled_at")

    cur = execute(conn, """
        INSERT INTO articles
          (title, slug, excerpt, body, status, author_id, category_id,
           featured, read_time, seo_title, seo_description,
           ai_generated, ai_topic_prompt,
           scheduled_at, published_at, created_by, updated_by)
        VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
        RETURNING id
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

    article_id = cur.fetchone()["id"]
    _sync_tags(conn, article_id, data.get("tags", []))
    conn.commit()

    row     = fetchone(conn, "SELECT * FROM articles WHERE id=%s", (article_id,))
    article = build_article_response(row, conn, include_body=True)
    conn.close()

    return jsonify({"article": article, "message": "Article created"}), 201


@api.put("/admin/articles/<int:article_id>")
@require_auth
def admin_update_article(article_id):
    conn = get_db()
    row  = fetchone(conn, "SELECT * FROM articles WHERE id=%s", (article_id,))
    if not row:
        conn.close()
        return jsonify({"error": "Not found"}), 404

    data   = request.get_json(silent=True) or {}
    fields = {}

    if "title" in data and data["title"].strip():
        fields["title"] = data["title"].strip()
    if "body" in data:
        fields["body"]      = data["body"]
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
        cat = fetchone(conn, "SELECT id FROM categories WHERE slug=%s", (data["category_slug"],))
        if cat:
            fields["category_id"] = cat["id"]
    if "author_slug" in data:
        author = fetchone(conn, "SELECT id FROM authors WHERE slug=%s", (data["author_slug"],))
        if author:
            fields["author_id"] = author["id"]
    for seo_field in ("seo_title","seo_description","og_title","og_description"):
        if seo_field in data:
            fields[seo_field] = data[seo_field]
    if "featured_image_id" in data:
        fields["featured_image"] = data["featured_image_id"]

    fields["updated_by"] = g.user["id"]

    if fields:
        set_clause = ", ".join(f"{k}=%s" for k in fields)
        execute(conn, f"UPDATE articles SET {set_clause} WHERE id=%s",
                list(fields.values()) + [article_id])

    if "tags" in data:
        _sync_tags(conn, article_id, data["tags"])

    conn.commit()
    updated = fetchone(conn, "SELECT * FROM articles WHERE id=%s", (article_id,))
    article = build_article_response(updated, conn, include_body=True)
    conn.close()

    return jsonify({"article": article, "message": "Article updated"})


@api.delete("/admin/articles/<int:article_id>")
@require_role("admin", "superadmin")
def admin_delete_article(article_id):
    conn = get_db()
    row  = fetchone(conn, "SELECT id, title FROM articles WHERE id=%s", (article_id,))
    if not row:
        conn.close()
        return jsonify({"error": "Not found"}), 404
    execute(conn, "DELETE FROM article_tags WHERE article_id=%s", (article_id,))
    execute(conn, "DELETE FROM articles WHERE id=%s", (article_id,))
    conn.commit()
    conn.close()
    return jsonify({"message": f"Article '{row['title']}' deleted"})


@api.post("/admin/articles/<int:article_id>/publish")
@require_auth
def admin_publish_article(article_id):
    conn = get_db()
    row  = fetchone(conn, "SELECT * FROM articles WHERE id=%s", (article_id,))
    if not row:
        conn.close()
        return jsonify({"error": "Not found"}), 404
    execute(conn,
        "UPDATE articles SET status='published', published_at=%s, updated_by=%s WHERE id=%s",
        (now_iso(), g.user["id"], article_id))
    conn.commit()
    conn.close()
    return jsonify({"message": "Article published"})


@api.post("/admin/articles/<int:article_id>/unpublish")
@require_auth
def admin_unpublish_article(article_id):
    conn = get_db()
    execute(conn,
        "UPDATE articles SET status='draft', updated_by=%s WHERE id=%s",
        (g.user["id"], article_id))
    conn.commit()
    conn.close()
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

    import uuid
    from PIL import Image
    import io

    max_mb     = int(os.getenv("MAX_IMAGE_SIZE_MB", "10"))
    file_bytes = file.read()
    if len(file_bytes) > max_mb * 1024 * 1024:
        return jsonify({"error": f"File too large (max {max_mb}MB)"}), 400

    ext         = file.filename.rsplit(".", 1)[1].lower()
    unique_name = f"{uuid.uuid4().hex}.{ext}"
    thumb_name  = f"thumb_{unique_name}"

    upload_dir = os.path.join(os.getcwd(), os.getenv("UPLOAD_FOLDER", "uploads"), "images")
    thumb_dir  = os.path.join(os.getcwd(), os.getenv("UPLOAD_FOLDER", "uploads"), "thumbnails")
    os.makedirs(upload_dir, exist_ok=True)
    os.makedirs(thumb_dir,  exist_ok=True)

    filepath = os.path.join(upload_dir, unique_name)
    with open(filepath, "wb") as f:
        f.write(file_bytes)

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

    conn = get_db()
    cur  = execute(conn, """
        INSERT INTO media (filename, original_name, mime_type, size_bytes, width, height,
                           url, thumbnail_url, alt_text, uploaded_by)
        VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
        RETURNING id
    """, (unique_name, file.filename, file.content_type or "image/jpeg",
          len(file_bytes), width, height, url, thumb_url,
          request.form.get("alt_text", ""), g.user["id"]))

    media_id = cur.fetchone()["id"]
    conn.commit()

    row = fetchone(conn, "SELECT * FROM media WHERE id=%s", (media_id,))
    conn.close()

    return jsonify({"media": row_to_dict(row), "message": "Upload successful"}), 201


@api.get("/admin/media")
@require_auth
def admin_media_library():
    page     = max(1, int(request.args.get("page", 1)))
    per_page = 24
    conn     = get_db()
    rows     = fetchall(conn, "SELECT * FROM media ORDER BY created_at DESC")
    conn.close()
    total  = len(rows)
    offset = (page - 1) * per_page
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
        return jsonify({"error": "AI API key not configured"}), 503

    import urllib.request, urllib.error

    conn     = get_db()
    cat      = fetchone(conn, "SELECT * FROM categories WHERE slug=%s", (cat_slug,))
    conn.close()
    cat_name = cat["name"] if cat else cat_slug

    system_prompt = f"""You are a senior journalist at The Broadsheet.
Tone: {tone}.
Write in HTML using <p>, <strong>, <em> tags only.
Return ONLY valid JSON (no markdown):
{{
  "title": "Article headline",
  "excerpt": "One-sentence summary under 200 chars",
  "body": "<p>Full article HTML...</p>",
  "seo_title": "SEO title",
  "seo_description": "Meta description under 160 chars",
  "tags": ["tag1", "tag2", "tag3"]
}}"""

    user_prompt = f"Write a {word_count}-word news article for the {cat_name} section about:\n\n{topic}"

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
        headers={"Authorization": f"Bearer {api_key}", "content-type": "application/json"},
        method="POST"
    )

    try:
        with urllib.request.urlopen(req, timeout=60) as resp:
            response_data = json.loads(resp.read().decode())
    except urllib.error.HTTPError as e:
        return jsonify({"error": f"Groq API error: {e.code}", "detail": e.read().decode()}), 502
    except Exception as e:
        return jsonify({"error": f"Request failed: {str(e)}"}), 502

    raw_text = ""
    try:
        raw_text = response_data["choices"][0]["message"]["content"].strip()
    except (KeyError, IndexError):
        return jsonify({"error": "Empty response from AI"}), 502

    if raw_text.startswith("```"):
        raw_text = re.sub(r"^```[a-z]*\n?", "", raw_text)
        raw_text = re.sub(r"\n?```$", "", raw_text)

    try:
        generated = json.loads(raw_text)
    except json.JSONDecodeError:
        return jsonify({"error": "AI returned malformed JSON", "raw": raw_text[:500]}), 502

    conn     = get_db()
    cat_row  = fetchone(conn, "SELECT id FROM categories WHERE slug=%s", (cat_slug,))
    if not cat_row:
        conn.close()
        return jsonify({"error": f"Category '{cat_slug}' not found"}), 400

    author = fetchone(conn, "SELECT id FROM authors WHERE slug=%s", (author_slug,)) if author_slug else None
    if not author:
        author = fetchone(conn, "SELECT id FROM authors LIMIT 1")

    title      = generated.get("title", topic)
    base_slug  = slugify(title)
    final_slug = base_slug
    counter    = 1
    while fetchone(conn, "SELECT id FROM articles WHERE slug=%s", (final_slug,)):
        final_slug = f"{base_slug}-{counter}"
        counter   += 1

    body      = generated.get("body", "")
    read_time = estimate_read_time(body)

    cur = execute(conn, """
        INSERT INTO articles
          (title, slug, excerpt, body, status, author_id, category_id,
           read_time, seo_title, seo_description,
           ai_generated, ai_topic_prompt, created_by, updated_by)
        VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
        RETURNING id
    """, (
        title, final_slug,
        generated.get("excerpt", make_excerpt(body)),
        body, "draft",
        author["id"], cat_row["id"], read_time,
        generated.get("seo_title", title),
        generated.get("seo_description", ""),
        1, topic, g.user["id"], g.user["id"]
    ))

    article_id = cur.fetchone()["id"]
    _sync_tags(conn, article_id, generated.get("tags", []))
    conn.commit()

    row     = fetchone(conn, "SELECT * FROM articles WHERE id=%s", (article_id,))
    article = build_article_response(row, conn, include_body=True)
    conn.close()

    return jsonify({"article": article, "message": "AI draft created — review and publish when ready"}), 201


# ════════════════════════════════════════════════════════════
# ADMIN — DASHBOARD STATS
# ════════════════════════════════════════════════════════════

@api.get("/admin/stats")
@require_auth
def admin_stats():
    conn = get_db()
    stats = {
        "total_articles":     fetchone(conn, "SELECT COUNT(*) as c FROM articles")["c"],
        "published_articles": fetchone(conn, "SELECT COUNT(*) as c FROM articles WHERE status='published'")["c"],
        "draft_articles":     fetchone(conn, "SELECT COUNT(*) as c FROM articles WHERE status='draft'")["c"],
        "review_articles":    fetchone(conn, "SELECT COUNT(*) as c FROM articles WHERE status='review'")["c"],
        "scheduled_articles": fetchone(conn, "SELECT COUNT(*) as c FROM articles WHERE status='published' AND scheduled_at IS NOT NULL")["c"],
        "ai_generated":       fetchone(conn, "SELECT COUNT(*) as c FROM articles WHERE ai_generated=1")["c"],
        "total_authors":      fetchone(conn, "SELECT COUNT(*) as c FROM authors WHERE is_active=1")["c"],
        "total_categories":   fetchone(conn, "SELECT COUNT(*) as c FROM categories WHERE is_active=1")["c"],
        "total_views":        fetchone(conn, "SELECT COALESCE(SUM(view_count),0) as c FROM articles WHERE status='published'")["c"],
        "recent_articles": [
            row_to_dict(r) for r in fetchall(conn, """
                SELECT a.id, a.title, a.slug, a.status, a.ai_generated,
                       a.published_at, a.view_count, c.name as category_name, c.color,
                       au.name as author_name
                FROM articles a
                JOIN categories c ON c.id=a.category_id
                JOIN authors au ON au.id=a.author_id
                ORDER BY a.updated_at DESC LIMIT 8
            """)
        ]
    }
    conn.close()
    return jsonify({"stats": stats})


# ════════════════════════════════════════════════════════════
# ADMIN — AUTHORS & CATEGORIES
# ════════════════════════════════════════════════════════════

@api.get("/admin/authors")
@require_auth
def admin_list_authors():
    conn = get_db()
    rows = fetchall(conn, "SELECT * FROM authors ORDER BY name")
    conn.close()
    return jsonify({"authors": [row_to_dict(r) for r in rows]})


@api.post("/admin/authors")
@require_role("admin", "superadmin")
def admin_create_author():
    data = request.get_json(silent=True) or {}
    name = (data.get("name") or "").strip()
    if not name:
        return jsonify({"error": "Name required"}), 400
    slug = slugify(name)
    conn = get_db()
    try:
        cur = execute(conn,
            "INSERT INTO authors (name, slug, bio, email, twitter, linkedin) VALUES (%s,%s,%s,%s,%s,%s) RETURNING id",
            (name, slug, data.get("bio",""), data.get("email",""),
             data.get("twitter",""), data.get("linkedin","")))
        new_id = cur.fetchone()["id"]
        conn.commit()
        row = fetchone(conn, "SELECT * FROM authors WHERE id=%s", (new_id,))
        conn.close()
        return jsonify({"author": row_to_dict(row)}), 201
    except Exception as e:
        conn.close()
        return jsonify({"error": str(e)}), 400


@api.get("/admin/categories")
@require_auth
def admin_list_categories():
    conn = get_db()
    rows = fetchall(conn, "SELECT * FROM categories ORDER BY sort_order")
    conn.close()
    return jsonify({"categories": [row_to_dict(r) for r in rows]})


# ════════════════════════════════════════════════════════════
# HELPERS
# ════════════════════════════════════════════════════════════

def _sync_tags(conn, article_id: int, tag_names: list):
    execute(conn, "DELETE FROM article_tags WHERE article_id=%s", (article_id,))
    for name in tag_names:
        name = str(name).strip()
        if not name:
            continue
        slug     = slugify(name)
        existing = fetchone(conn, "SELECT id FROM tags WHERE slug=%s", (slug,))
        if existing:
            tag_id = existing["id"]
        else:
            cur    = execute(conn, "INSERT INTO tags (name, slug) VALUES (%s,%s) ON CONFLICT DO NOTHING RETURNING id", (name, slug))
            result = cur.fetchone()
            if result:
                tag_id = result["id"]
            else:
                tag_id = fetchone(conn, "SELECT id FROM tags WHERE slug=%s", (slug,))["id"]
        execute(conn,
            "INSERT INTO article_tags (article_id, tag_id) VALUES (%s,%s) ON CONFLICT DO NOTHING",
            (article_id, tag_id))
