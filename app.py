#!/usr/bin/env python3
"""
КЧСИ API — Subscribe + Auth-ready Backend
==========================================
Single Flask app for Railway deployment.
Consolidates alerts/api.py + root app.py.
"""

import sqlite3
import json
import os
import re
import secrets
import time as _time
from collections import defaultdict
from datetime import datetime
from urllib.parse import urlparse

from flask import Flask, request, jsonify, redirect
from flask_cors import CORS

# Optional email via Resend
try:
    import resend
    resend.api_key = os.getenv("RESEND_API_KEY")
    HAS_RESEND = bool(os.getenv("RESEND_API_KEY"))
except ImportError:
    HAS_RESEND = False

# ============================================================
# App setup
# ============================================================

app = Flask(__name__)

ALLOWED_ORIGINS = [
    "https://martinpetrov8.github.io",
    "https://kchsi-sdelki.bg",
]
# Allow localhost in dev
if os.getenv("FLASK_ENV") == "development":
    ALLOWED_ORIGINS.append("http://localhost:3000")

CORS(app, origins=ALLOWED_ORIGINS)

# Config
DB_PATH = os.getenv("SUBSCRIBERS_DB", os.getenv("DB_PATH", "data/subscribers.db"))
SENDER_EMAIL = os.getenv("SENDER_EMAIL", "onboarding@resend.dev")
SENDER_NAME = os.getenv("SENDER_NAME", "Изгоден Имот")
SITE_URL = os.getenv("SITE_URL", "https://martinpetrov8.github.io/real-estate-price-matching")
API_URL = os.getenv("RAILWAY_PUBLIC_DOMAIN", os.getenv("API_URL", ""))

# Request size limit (1KB — no reason for larger payloads)
app.config['MAX_CONTENT_LENGTH'] = 1024

# ============================================================
# Rate limiting (in-memory, per-IP)
# ============================================================

_rate_limit = defaultdict(list)
RATE_LIMIT_MAX = 5
RATE_LIMIT_WINDOW = 60  # seconds

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
# Database
# ============================================================

ALLOWED_REDIRECT_HOSTS = {'martinpetrov8.github.io', 'kchsi-sdelki.bg'}

def safe_redirect(url):
    parsed = urlparse(url)
    if parsed.hostname not in ALLOWED_REDIRECT_HOSTS:
        return redirect(SITE_URL)
    return redirect(url)

def init_db():
    os.makedirs(os.path.dirname(DB_PATH) if os.path.dirname(DB_PATH) else '.', exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()

    # Subscribers table
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

    # Users table (auth-ready, for future Stripe integration)
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

    # Billing events (idempotency for Stripe webhooks)
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
    return conn

def get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

def generate_token():
    return secrets.token_urlsafe(32)

# ============================================================
# Email
# ============================================================

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
    return jsonify({"status": "ok", "service": "kchsi-api", "version": "2.0"})

@app.route('/health', methods=['GET'])
def health():
    return jsonify({"status": "ok", "time": datetime.utcnow().isoformat()})

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

    # Validate email
    if not email or len(email) > 254 or not EMAIL_RE.match(email):
        return jsonify({"error": "Невалиден имейл адрес"}), 400

    # Validate cities
    if not isinstance(cities, list):
        cities = []
    cities = [c for c in cities if c in VALID_CITIES]

    # Validate discount
    try:
        min_discount = max(10, min(70, int(min_discount)))
    except (ValueError, TypeError):
        min_discount = 20

    conn = get_db()
    c = conn.cursor()

    # Check existing
    c.execute('SELECT id, verified FROM subscribers WHERE email = ?', (email,))
    existing = c.fetchone()

    if existing:
        if existing['verified']:
            conn.close()
            return jsonify({"error": "Този имейл вече е абониран"}), 400
        # Resend verification
        c.execute('SELECT verify_token FROM subscribers WHERE id = ?', (existing['id'],))
        token = c.fetchone()['verify_token']
        send_verification_email(email, token)
        conn.close()
        return jsonify({"message": "Изпратихме нов линк за потвърждение"})

    verify_token = generate_token()
    unsubscribe_token = generate_token()

    c.execute('''INSERT INTO subscribers (email, cities, min_discount, verify_token, unsubscribe_token)
                 VALUES (?, ?, ?, ?, ?)''',
              (email, json.dumps(cities), min_discount, verify_token, unsubscribe_token))
    conn.commit()
    conn.close()

    if send_verification_email(email, verify_token):
        return jsonify({"message": "Записахме те! Ще получиш имейл за потвърждение."})
    return jsonify({"message": "Записахме те! Ще се свържем скоро."})

@app.route('/verify', methods=['GET'])
def verify():
    token = request.args.get('token', '')
    if not token:
        return safe_redirect(f"{SITE_URL}?error=invalid_token")

    conn = get_db()
    c = conn.cursor()
    c.execute('SELECT id FROM subscribers WHERE verify_token = ?', (token,))
    sub = c.fetchone()

    if not sub:
        conn.close()
        return safe_redirect(f"{SITE_URL}?error=invalid_token")

    c.execute('UPDATE subscribers SET verified = 1, verified_at = ?, verify_token = NULL WHERE id = ?',
              (datetime.utcnow().isoformat(), sub['id']))
    conn.commit()
    conn.close()
    return safe_redirect(f"{SITE_URL}?verified=true")

@app.route('/unsubscribe', methods=['GET'])
def unsubscribe():
    token = request.args.get('token', '')
    if not token:
        return safe_redirect(f"{SITE_URL}?error=invalid_token")

    conn = get_db()
    c = conn.cursor()
    c.execute('DELETE FROM subscribers WHERE unsubscribe_token = ?', (token,))
    conn.commit()
    conn.close()
    return safe_redirect(f"{SITE_URL}?unsubscribed=true")

@app.route('/stats', methods=['GET'])
def stats():
    conn = get_db()
    c = conn.cursor()
    c.execute('SELECT COUNT(*) FROM subscribers WHERE verified = 1')
    count = c.fetchone()[0]
    conn.close()
    return jsonify({"subscribers": count})

# ============================================================
# Stripe webhook placeholder (Sprint 4)
# ============================================================

@app.route('/billing/webhook', methods=['POST'])
def billing_webhook():
    """Stripe webhook endpoint — not yet active."""
    return jsonify({"error": "Billing not yet enabled"}), 503

# ============================================================
# Init & Run
# ============================================================

init_db()

if __name__ == '__main__':
    port = int(os.getenv('PORT', 5000))
    app.run(host='0.0.0.0', port=port, debug=False)
