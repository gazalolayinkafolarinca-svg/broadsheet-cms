"""
============================================================
THE BROADSHEET CMS — Utilities
File: backend/src/utils/helpers.py
============================================================
"""

import re
import unicodedata
import math
import html


def slugify(text: str) -> str:
    """Convert text to a URL-safe slug."""
    text = str(text)
    text = unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode()
    text = re.sub(r"[^\w\s-]", "", text.lower())
    text = re.sub(r"[-\s]+", "-", text).strip("-")
    return text or "untitled"


def estimate_read_time(html_body: str) -> int:
    """Estimate reading time in minutes from HTML body (avg 238 wpm)."""
    text = re.sub(r"<[^>]+>", " ", html_body)
    words = len(text.split())
    return max(1, math.ceil(words / 238))


def strip_html(html_body: str) -> str:
    """Strip HTML tags and return plain text."""
    text = re.sub(r"<[^>]+>", " ", html_body)
    text = html.unescape(text)
    return re.sub(r"\s+", " ", text).strip()


def make_excerpt(html_body: str, max_chars: int = 200) -> str:
    """Generate an excerpt from HTML body."""
    text = strip_html(html_body)
    if len(text) <= max_chars:
        return text
    truncated = text[:max_chars].rsplit(" ", 1)[0]
    return truncated + "…"


def paginate(query_result: list, page: int, per_page: int) -> dict:
    """Paginate a list and return pagination metadata."""
    page = max(1, page)
    total = len(query_result)
    total_pages = math.ceil(total / per_page) if total > 0 else 1
    start = (page - 1) * per_page
    end = start + per_page
    return {
        "items": query_result[start:end],
        "pagination": {
            "page": page,
            "per_page": per_page,
            "total": total,
            "total_pages": total_pages,
            "has_next": page < total_pages,
            "has_prev": page > 1,
        }
    }


def allowed_file(filename: str) -> bool:
    allowed = {"png", "jpg", "jpeg", "webp", "gif"}
    return "." in filename and filename.rsplit(".", 1)[1].lower() in allowed
