"""
============================================================
THE BROADSHEET CMS — Scheduler Service
File: backend/src/services/scheduler.py

Runs every minute and publishes articles whose
scheduled_at timestamp has passed.
============================================================
"""

import threading
import time
import logging
from datetime import datetime, timezone

logger = logging.getLogger(__name__)


def run_scheduler(app):
    """
    Background thread that checks every 60 seconds for articles
    that need to be auto-published based on their scheduled_at time.
    """
    def _tick():
        while True:
            try:
                with app.app_context():
                    _publish_scheduled()
            except Exception as e:
                logger.error(f"[Scheduler] Error: {e}")
            time.sleep(60)

    t = threading.Thread(target=_tick, daemon=True)
    t.start()
    logger.info("[Scheduler] Started — checking every 60 seconds")


def _publish_scheduled():
    """Publish any articles whose scheduled_at time has passed."""
    from src.database import get_db
    db = get_db()

    due = db.execute("""
        SELECT id, title FROM articles
        WHERE status = 'published'
          AND scheduled_at IS NOT NULL
          AND scheduled_at <= datetime('now')
          AND published_at IS NULL
    """).fetchall()

    # Also catch articles explicitly scheduled for future publish
    future_due = db.execute("""
        SELECT id, title FROM articles
        WHERE status = 'draft'
          AND scheduled_at IS NOT NULL
          AND scheduled_at <= datetime('now')
    """).fetchall()

    all_due = list(due) + list(future_due)

    for article in all_due:
        db.execute("""
            UPDATE articles
            SET status = 'published',
                published_at = datetime('now'),
                scheduled_at = NULL
            WHERE id = ?
        """, (article["id"],))
        logger.info(f"[Scheduler] Auto-published: '{article['title']}' (id={article['id']})")

    if all_due:
        db.commit()

    db.close()
