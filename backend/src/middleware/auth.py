"""
============================================================
THE BROADSHEET CMS — Auth Middleware
File: backend/src/middleware/auth.py
============================================================
"""

import os
import jwt
from functools import wraps
from flask import request, jsonify, g
from src.database import get_db

JWT_ALGORITHM = "HS256"


def _get_secret():
    return os.getenv("JWT_SECRET", "broadsheet-super-secret-2026-xK9mP2qL8rT")


def generate_token(user_id: int, email: str, role: str) -> str:
    import time
    expiry_hours = int(os.getenv("JWT_EXPIRY_HOURS", "24"))
    payload = {
        "sub": str(user_id),
        "email": email,
        "role": role,
        "iat": int(time.time()),
        "exp": int(time.time()) + expiry_hours * 3600,
    }
    return jwt.encode(payload, _get_secret(), algorithm=JWT_ALGORITHM)


def decode_token(token: str) -> dict:
    return jwt.decode(token, _get_secret(), algorithms=[JWT_ALGORITHM])


def require_auth(f):
    """Decorator: require a valid JWT. Sets g.user on success."""
    @wraps(f)
    def decorated(*args, **kwargs):
        auth_header = request.headers.get("Authorization", "")
        if not auth_header.startswith("Bearer "):
            return jsonify({"error": "Missing or invalid Authorization header"}), 401
        token = auth_header[7:]
        try:
            payload = decode_token(token)
        except jwt.ExpiredSignatureError:
            return jsonify({"error": "Token expired"}), 401
        except jwt.InvalidTokenError:
            return jsonify({"error": "Invalid token"}), 401

        db = get_db()
        user = db.execute(
            "SELECT id, email, name, role, is_active FROM admin_users WHERE id=?",
            (int(payload["sub"]),)
        ).fetchone()
        db.close()

        if not user or not user["is_active"]:
            return jsonify({"error": "User not found or inactive"}), 401

        g.user = dict(user)
        return f(*args, **kwargs)
    return decorated


def require_role(*roles):
    """Decorator: require auth + specific role(s)."""
    def decorator(f):
        @wraps(f)
        @require_auth
        def decorated(*args, **kwargs):
            if g.user["role"] not in roles:
                return jsonify({"error": "Insufficient permissions"}), 403
            return f(*args, **kwargs)
        return decorated
    return decorator
