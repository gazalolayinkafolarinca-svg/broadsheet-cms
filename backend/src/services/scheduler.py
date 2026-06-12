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
    conn = get_db()
    cur  = conn.cursor()

    cur.execute("""
        UPDATE articles
        SET status      = 'published',
            published_at = NOW()::text,
            scheduled_at = NULL
        WHERE status = 'draft'
          AND scheduled_at IS NOT NULL
          AND scheduled_at <= NOW()::text
        RETURNING id, title
    """)

    updated = cur.fetchall()
    for row in updated:
        logger.info(f"[Scheduler] Auto-published: '{row['title']}' (id={row['id']})")

    conn.commit()
    conn.close()
