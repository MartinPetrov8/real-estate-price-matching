#!/usr/bin/env python3
"""
КЧСИ API — Subscribe + Auth-ready Backend
==========================================
Single Flask app for Railway deployment.
Supports PostgreSQL (via DATABASE_URL) with SQLite fallback for local dev.
"""

import json
import os
import re
import secrets
import time as _time
from collections import defaultdict
from datetime import datetime
from urllib.parse import urlparse

from flask import Flask, request, jsonify, redirect, g
from flask_cors import CORS

# Optional email via Resend
try:
    import resend
    resend.api_key = os.getenv("RESEND_API_KEY")
    HAS_RESEND = bool(os.getenv("RESEND_API_KEY"))
except ImportError:
    HAS_RESEND = False

# Database driver detection
DATABASE_URL = os.getenv("DATABASE_URL", "")
USE_POSTGRES = DATABASE_URL.startswith("postgresql://") or DATABASE_URL.startswith("postgres://")

if USE_POSTGRES:
    import psycopg2
    import psycopg2.extras
    # Railway sometimes gives postgres:// but psycopg2 needs postgresql://
    if DATABASE_URL.startswith("postgres://"):
        DATABASE_URL = DATABASE_URL.replace("postgres://", "postgresql://", 1)
else:
    import sqlite3
    SQLITE_PATH = os.getenv("SUBSCRIBERS_DB", os.getenv("DB_PATH", "data/subscribers.db"))

# ============================================================
# App setup
# ============================================================

app = Flask(__name__)

ALLOWED_ORIGINS = [
    "https://martinpetrov8.github.io",
    "https://kchsi-sdelki.bg",
    "https://www.kchsi-sdelki.bg",
]
if os.getenv("FLASK_ENV") == "development":
    ALLOWED_ORIGINS.append("http://localhost:3000")

CORS(app, origins=ALLOWED_ORIGINS)

# Config
SENDER_EMAIL = os.getenv("SENDER_EMAIL", "onboarding@resend.dev")
SENDER_NAME = os.getenv("SENDER_NAME", "Изгоден Имот")
SITE_URL = os.getenv("SITE_URL", "https://kchsi-sdelki.bg")
API_URL = os.getenv("RAILWAY_PUBLIC_DOMAIN", os.getenv("API_URL", ""))

app.config['MAX_CONTENT_LENGTH'] = 1024

# ============================================================
# Database abstraction
# ============================================================

def get_db():
    """Get a database connection, stored in Flask's g for request lifecycle."""
    if 'db' not in g:
        if USE_POSTGRES:
            g.db = psycopg2.connect(DATABASE_URL)
            g.db.autocommit = False
        else:
            os.makedirs(os.path.dirname(SQLITE_PATH) if os.path.dirname(SQLITE_PATH) else '.', exist_ok=True)
            g.db = sqlite3.connect(SQLITE_PATH)
            g.db.row_factory = sqlite3.Row
    return g.db

@app.teardown_appcontext
def close_db(exception):
    db = g.pop('db', None)
    if db is not None:
        if exception:
            db.rollback()
        db.close()

def db_execute(query, params=None):
    """Execute a query, adapting placeholders for Postgres (%s) vs SQLite (?)."""
    conn = get_db()
    if USE_POSTGRES:
        # Convert ? placeholders to %s for psycopg2
        query = query.replace('?', '%s')
        cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    else:
        cur = conn.cursor()
    cur.execute(query, params or ())
    return cur

def db_commit():
    get_db().commit()

def db_fetchone(query, params=None):
    cur = db_execute(query, params)
    row = cur.fetchone()
    cur.close()
    return row

def db_fetchall(query, params=None):
    cur = db_execute(query, params)
    rows = cur.fetchall()
    cur.close()
    return rows

# ============================================================
# Schema initialization
# ============================================================

def init_db():
    """Create tables if they don't exist. Works for both Postgres and SQLite."""
    if USE_POSTGRES:
        conn = psycopg2.connect(DATABASE_URL)
        c = conn.cursor()

        c.execute('''
            CREATE TABLE IF NOT EXISTS subscribers (
                id SERIAL PRIMARY KEY,
                email TEXT UNIQUE NOT NULL,
                cities TEXT NOT NULL DEFAULT '[]',
                min_discount INTEGER DEFAULT 20,
                verified BOOLEAN DEFAULT FALSE,
                verify_token TEXT,
                unsubscribe_token TEXT,
                created_at TIMESTAMPTZ DEFAULT NOW(),
                verified_at TIMESTAMPTZ,
                last_sent_at TIMESTAMPTZ,
                last_deal_ids TEXT
            )
        ''')

        c.execute('''
            CREATE TABLE IF NOT EXISTS users (
                id SERIAL PRIMARY KEY,
                email TEXT UNIQUE NOT NULL,
                password_hash TEXT,
                tier TEXT DEFAULT 'free' CHECK(tier IN ('free', 'pro')),
                stripe_customer_id TEXT,
                stripe_subscription_id TEXT,
                subscription_status TEXT DEFAULT 'inactive'
                    CHECK(subscription_status IN ('inactive', 'active', 'past_due', 'canceled')),
                created_at TIMESTAMPTZ DEFAULT NOW(),
                last_login_at TIMESTAMPTZ
            )
        ''')

        c.execute('''
            CREATE TABLE IF NOT EXISTS billing_events (
                id SERIAL PRIMARY KEY,
                event_id TEXT UNIQUE NOT NULL,
                event_type TEXT NOT NULL,
                processed_at TIMESTAMPTZ DEFAULT NOW(),
                payload_json TEXT
            )
        ''')

        conn.commit()
        c.close()
        conn.close()
        print("[DB] PostgreSQL tables initialized")
    else:
        os.makedirs(os.path.dirname(SQLITE_PATH) if os.path.dirname(SQLITE_PATH) else '.', exist_ok=True)
        conn = sqlite3.connect(SQLITE_PATH)
        c = conn.cursor()

        c.execute('''
            CREATE TABLE IF NOT EXISTS subscribers (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                email TEXT UNIQUE NOT NULL,
                cities TEXT NOT NULL DEFAULT '[]',
                min_discount INTEGER DEFAULT 20,
                verified BOOLEAN DEFAULT 0,
                verify_token TEXT,
                unsubscribe_token TEXT,
                created_at TEXT DEFAULT CURRENT_TIMESTAMP,
                verified_at TEXT,
                last_sent_at TEXT,
                last_deal_ids TEXT
            )
        ''')

        c.execute('''
            CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                email TEXT UNIQUE NOT NULL,
                password_hash TEXT,
                tier TEXT DEFAULT 'free' CHECK(tier IN ('free', 'pro')),
                stripe_customer_id TEXT,
                stripe_subscription_id TEXT,
                subscription_status TEXT DEFAULT 'inactive'
                    CHECK(subscription_status IN ('inactive', 'active', 'past_due', 'canceled')),
                created_at TEXT DEFAULT CURRENT_TIMESTAMP,
                last_login_at TEXT
            )
        ''')

        c.execute('''
            CREATE TABLE IF NOT EXISTS billing_events (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                event_id TEXT UNIQUE NOT NULL,
                event_type TEXT NOT NULL,
                processed_at TEXT DEFAULT CURRENT_TIMESTAMP,
                payload_json TEXT
            )
        ''')

        conn.commit()
        c.close()
        conn.close()
        print("[DB] SQLite tables initialized")

# ============================================================
# Rate limiting (in-memory, per-IP)
# ============================================================

_rate_limit = defaultdict(list)
RATE_LIMIT_MAX = 5
RATE_LIMIT_WINDOW = 60

@app.before_request
def check_rate_limit():
    if request.endpoint in ('subscribe',):
        ip = request.headers.get('X-Forwarded-For', request.remote_addr or 'unknown').split(',')[0].strip()
        now = _time.time()
        _rate_limit[ip] = [t for t in _rate_limit[ip] if now - t < RATE_LIMIT_WINDOW]
        if len(_rate_limit[ip]) >= RATE_LIMIT_MAX:
            return jsonify({"error": "Твърде много заявки. Опитай отново след минута."}), 429
        _rate_limit[ip].append(now)

# ============================================================
# Security headers
# ============================================================

@app.after_request
def add_security_headers(response):
    response.headers['X-Content-Type-Options'] = 'nosniff'
    response.headers['X-Frame-Options'] = 'DENY'
    response.headers['X-XSS-Protection'] = '1; mode=block'
    response.headers['Strict-Transport-Security'] = 'max-age=31536000; includeSubDomains'
    response.headers['Referrer-Policy'] = 'strict-origin-when-cross-origin'
    return response

# ============================================================
# Error handlers
# ============================================================

@app.errorhandler(413)
def too_large(e):
    return jsonify({"error": "Заявката е твърде голяма"}), 413

@app.errorhandler(500)
def internal_error(e):
    return jsonify({"error": "Вътрешна грешка на сървъра"}), 500

@app.errorhandler(404)
def not_found(e):
    return jsonify({"error": "Не е намерен"}), 404

# ============================================================
# Helpers
# ============================================================

ALLOWED_REDIRECT_HOSTS = {'martinpetrov8.github.io', 'kchsi-sdelki.bg', 'www.kchsi-sdelki.bg'}

def safe_redirect(url):
    parsed = urlparse(url)
    if parsed.hostname not in ALLOWED_REDIRECT_HOSTS:
        return redirect(SITE_URL)
    return redirect(url)

def generate_token():
    return secrets.token_urlsafe(32)

def send_verification_email(email, token):
    if not HAS_RESEND:
        print(f"[DEBUG] Would send verification to {email}")
        return True

    api_base = f"https://{API_URL}" if API_URL and not API_URL.startswith("http") else API_URL
    verify_url = f"{api_base}/verify?token={token}"

    html = f'''
    <div style="font-family:sans-serif;max-width:500px;margin:0 auto;padding:24px;">
        <h1 style="color:#111;">🏠 Потвърди абонамента си</h1>
        <p>Благодарим за интереса! Потвърди имейла си, за да те уведомим когато пуснем известията.</p>
        <a href="{verify_url}" style="display:inline-block;background:#2563eb;color:#fff;padding:14px 28px;border-radius:8px;text-decoration:none;margin:16px 0;">
            Потвърди имейла
        </a>
        <p style="color:#6b7280;font-size:14px;">Ако не си заявил този абонамент, игнорирай този имейл.</p>
    </div>
    '''

    try:
        resend.Emails.send({
            "from": f"{SENDER_NAME} <{SENDER_EMAIL}>",
            "to": email,
            "subject": "🏠 Потвърди абонамента си — ЧСИ Търгове",
            "html": html
        })
        return True
    except Exception as e:
        print(f"Email error: {e}")
        return False

# ============================================================
# Routes
# ============================================================

@app.route('/', methods=['GET'])
def home():
    db_type = "postgres" if USE_POSTGRES else "sqlite"
    return jsonify({"status": "ok", "service": "kchsi-api", "version": "2.1", "db": db_type})

@app.route('/health', methods=['GET'])
def health():
    # Verify DB connection
    try:
        db_execute("SELECT 1")
        db_ok = True
    except Exception:
        db_ok = False
    return jsonify({
        "status": "ok" if db_ok else "degraded",
        "time": datetime.utcnow().isoformat(),
        "db": "postgres" if USE_POSTGRES else "sqlite",
        "db_connected": db_ok
    })

VALID_CITIES = ['София', 'Пловдив', 'Варна', 'Бургас', 'Русе', 'Стара Загора']
EMAIL_RE = re.compile(r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$')

@app.route('/subscribe', methods=['POST'])
def subscribe():
    if not request.is_json:
        return jsonify({"error": "Content-Type must be application/json"}), 415

    data = request.json or {}
    email = data.get('email', '').strip().lower()
    cities = data.get('cities', [])
    min_discount = data.get('min_discount', 20)

    if not email or len(email) > 254 or not EMAIL_RE.match(email):
        return jsonify({"error": "Невалиден имейл адрес"}), 400

    if not isinstance(cities, list):
        cities = []
    cities = [c for c in cities if c in VALID_CITIES]

    try:
        min_discount = max(10, min(70, int(min_discount)))
    except (ValueError, TypeError):
        min_discount = 20

    # Check existing
    existing = db_fetchone('SELECT id, verified FROM subscribers WHERE email = ?', (email,))

    if existing:
        verified = existing['verified'] if USE_POSTGRES else existing[1] if not hasattr(existing, 'keys') else existing['verified']
        if verified:
            return jsonify({"error": "Този имейл вече е абониран"}), 400
        row_id = existing['id'] if USE_POSTGRES else existing[0] if not hasattr(existing, 'keys') else existing['id']
        token_row = db_fetchone('SELECT verify_token FROM subscribers WHERE id = ?', (row_id,))
        token = token_row['verify_token'] if USE_POSTGRES else token_row[0] if not hasattr(token_row, 'keys') else token_row['verify_token']
        send_verification_email(email, token)
        return jsonify({"message": "Изпратихме нов линк за потвърждение"})

    verify_token = generate_token()
    unsubscribe_token = generate_token()

    try:
        db_execute(
            'INSERT INTO subscribers (email, cities, min_discount, verify_token, unsubscribe_token) VALUES (?, ?, ?, ?, ?)',
            (email, json.dumps(cities), min_discount, verify_token, unsubscribe_token)
        )
        db_commit()
    except Exception as e:
        err_str = str(e).lower()
        if 'unique' in err_str or 'duplicate' in err_str:
            return jsonify({"error": "Този имейл вече е абониран"}), 409
        raise

    if send_verification_email(email, verify_token):
        return jsonify({"message": "Записахме те! Ще получиш имейл за потвърждение."})
    return jsonify({"message": "Записахме те! Ще се свържем скоро."})

@app.route('/verify', methods=['GET'])
def verify():
    token = request.args.get('token', '')
    if not token:
        return safe_redirect(f"{SITE_URL}?error=invalid_token")

    sub = db_fetchone('SELECT id FROM subscribers WHERE verify_token = ?', (token,))
    if not sub:
        return safe_redirect(f"{SITE_URL}?error=invalid_token")

    sub_id = sub['id'] if USE_POSTGRES else sub[0] if not hasattr(sub, 'keys') else sub['id']
    db_execute(
        'UPDATE subscribers SET verified = ?, verified_at = ?, verify_token = NULL WHERE id = ?',
        (True if USE_POSTGRES else 1, datetime.utcnow().isoformat(), sub_id)
    )
    db_commit()
    return safe_redirect(f"{SITE_URL}?verified=true")

@app.route('/unsubscribe', methods=['GET'])
def unsubscribe():
    token = request.args.get('token', '')
    if not token:
        return safe_redirect(f"{SITE_URL}?error=invalid_token")

    db_execute('DELETE FROM subscribers WHERE unsubscribe_token = ?', (token,))
    db_commit()
    return safe_redirect(f"{SITE_URL}?unsubscribed=true")

@app.route('/stats', methods=['GET'])
def stats():
    row = db_fetchone('SELECT COUNT(*) as cnt FROM subscribers WHERE verified = ?', (True if USE_POSTGRES else 1,))
    count = row['cnt'] if USE_POSTGRES else row[0] if not hasattr(row, 'keys') else row['cnt']
    return jsonify({"subscribers": count})

# ============================================================
# Stripe webhook placeholder (Sprint 4)
# ============================================================

@app.route('/billing/webhook', methods=['POST'])
def billing_webhook():
    return jsonify({"error": "Billing not yet enabled"}), 503

# ============================================================
# Init & Run
# ============================================================

init_db()

if __name__ == '__main__':
    port = int(os.getenv('PORT', 5000))
    app.run(host='0.0.0.0', port=port, debug=False)
