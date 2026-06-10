"""
============================================================
THE BROADSHEET CMS — Flask Server Entry Point
File: backend/src/server.py
============================================================
"""

import os
import logging
from flask import Flask, send_from_directory, jsonify
from dotenv import load_dotenv

load_dotenv()

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s"
)
logger = logging.getLogger(__name__)


def create_app():
    app = Flask(__name__, static_folder=None)

    # ── Config ──────────────────────────────────────
    app.config["SECRET_KEY"]   = os.getenv("SECRET_KEY", "dev-secret")
    app.config["MAX_CONTENT_LENGTH"] = int(os.getenv("MAX_IMAGE_SIZE_MB", "10")) * 1024 * 1024

    # ── CORS ────────────────────────────────────────
    from flask import request as flask_request
    allowed_origins = [o.strip() for o in os.getenv("CORS_ORIGINS", "http://localhost:5500,http://127.0.0.1:5500").split(",")]

    @app.after_request
    def add_cors(response):
        origin = flask_request.headers.get("Origin", "")
        if origin in allowed_origins or "*" in allowed_origins:
            response.headers["Access-Control-Allow-Origin"]  = origin
            response.headers["Access-Control-Allow-Headers"] = "Content-Type, Authorization"
            response.headers["Access-Control-Allow-Methods"] = "GET, POST, PUT, DELETE, OPTIONS"
        return response

    @app.before_request
    def handle_preflight():
        if flask_request.method == "OPTIONS":
            from flask import Response
            r = Response()
            origin = flask_request.headers.get("Origin", "")
            if origin in allowed_origins:
                r.headers["Access-Control-Allow-Origin"]  = origin
                r.headers["Access-Control-Allow-Headers"] = "Content-Type, Authorization"
                r.headers["Access-Control-Allow-Methods"] = "GET, POST, PUT, DELETE, OPTIONS"
            return r, 204

    # ── Security headers ─────────────────────────────
    @app.after_request
    def security_headers(response):
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"]        = "SAMEORIGIN"
        response.headers["Referrer-Policy"]        = "strict-origin-when-cross-origin"
        return response

    # ── Register API blueprint ───────────────────────
    from src.routes.api import api
    app.register_blueprint(api)

    # ── Serve uploaded media ─────────────────────────
    upload_folder = os.path.join(os.getcwd(), os.getenv("UPLOAD_FOLDER", "uploads"))

    @app.route("/uploads/<path:filename>")
    def serve_upload(filename):
        return send_from_directory(upload_folder, filename)

    # ── Health check ─────────────────────────────────
    @app.route("/health")
    def health():
        return jsonify({"status": "ok", "service": "The Broadsheet CMS", "year": 2026})

    # ── Global error handlers ────────────────────────
    @app.errorhandler(404)
    def not_found(e):
        return jsonify({"error": "Not found"}), 404

    @app.errorhandler(405)
    def method_not_allowed(e):
        return jsonify({"error": "Method not allowed"}), 405

    @app.errorhandler(413)
    def too_large(e):
        return jsonify({"error": "File too large"}), 413

    @app.errorhandler(500)
    def server_error(e):
        logger.error(f"Internal error: {e}")
        return jsonify({"error": "Internal server error"}), 500

    return app


if __name__ == "__main__":
    # Initialise database on first run
    from src.database import init_db
    db_path = os.getenv("DATABASE_PATH", "instance/broadsheet.db")
    if not os.path.exists(db_path):
        logger.info("[Startup] Database not found — initialising...")
        init_db()
    else:
        logger.info(f"[Startup] Using existing database → {db_path}")

    app = create_app()

    # Start background scheduler
    from src.services.scheduler import run_scheduler
    run_scheduler(app)

    port = int(os.getenv("PORT", 5000))
    debug = os.getenv("FLASK_ENV", "production") == "development"

    logger.info(f"[Startup] The Broadsheet CMS running on http://localhost:{port}")
    logger.info(f"[Startup] Admin dashboard → http://localhost:{port}/../frontend/public/admin/index.html")
    app.run(host="0.0.0.0", port=port, debug=debug, use_reloader=False)
