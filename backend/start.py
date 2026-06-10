#!/usr/bin/env python3
"""
============================================================
THE BROADSHEET CMS — start.py
One-command startup: initialises DB if needed, then runs server.
Usage:  python start.py
============================================================
"""
import os
import sys

# Must run from backend/ directory
os.chdir(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.getcwd())

from dotenv import load_dotenv
load_dotenv()

db_path = os.getenv("DATABASE_PATH", "instance/broadsheet.db")

if not os.path.exists(db_path):
    print("=" * 50)
    print("First run detected — initialising database...")
    print("=" * 50)
    from src.database import init_db
    init_db()
    print("=" * 50)
    print("Database ready.")
    print("=" * 50)

from src.server import create_app
from src.services.scheduler import run_scheduler

app = create_app()
run_scheduler(app)

port  = int(os.getenv("PORT", 5000))
debug = os.getenv("FLASK_ENV", "production") == "development"

print(f"\n{'='*50}")
print(f"  The Broadsheet CMS")
print(f"  API:    http://localhost:{port}/api/articles")
print(f"  Health: http://localhost:{port}/health")
print(f"  Admin:  Open frontend/public/admin/index.html")
print(f"  Site:   Open frontend/public/index.html")
print(f"{'='*50}\n")

app.run(host="0.0.0.0", port=port, debug=debug, use_reloader=False)
