#!/usr/bin/env python3
"""
Subscribe API - Flask server for Railway
"""

import sqlite3
import json
import os
import secrets
from datetime import datetime
from flask import Flask, request, jsonify, redirect
from flask_cors import CORS

# Optional imports
try:
    import resend
    resend.api_key = os.getenv("RESEND_API_KEY")
    HAS_RESEND = True
except ImportError:
    HAS_RESEND = False

app = Flask(__name__)
CORS(app)

# Config
DB_PATH = os.getenv("SUBSCRIBERS_DB", "data/subscribers.db")
SENDER_EMAIL = os.getenv("SENDER_EMAIL", "onboarding@resend.dev")
SENDER_NAME = os.getenv("SENDER_NAME", "Изгоден Имот")
SITE_URL = os.getenv("SITE_URL", "https://martinpetrov8.github.io/real-estate-price-matching")
API_URL = os.getenv("RAILWAY_PUBLIC_DOMAIN", os.getenv("API_URL", ""))

def init_db():
    """Initialize database if not exists."""
    os.makedirs(os.path.dirname(DB_PATH) if os.path.dirname(DB_PATH) else '.', exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute('''
        CREATE TABLE IF NOT EXISTS subscribers (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            email TEXT UNIQUE NOT NULL,
            cities TEXT NOT NULL,
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
    conn.commit()
    return conn

def get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

def generate_token():
    return secrets.token_urlsafe(32)

def send_verification_email(email, token):
    if not HAS_RESEND or not os.getenv("RESEND_API_KEY"):
        print(f"[DEBUG] Would send verification to {email}")
        return True
    
    api_base = f"https://{API_URL}" if API_URL and not API_URL.startswith("http") else API_URL
    verify_url = f"{api_base}/verify?token={token}"
    
    html = f'''
    <div style="font-family:sans-serif;max-width:500px;margin:0 auto;padding:24px;">
        <h1 style="color:#111;">🏠 Потвърди абонамента си</h1>
        <p>Благодарим за абонамента за известия!</p>
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
            "subject": "🏠 Потвърди абонамента си - Изгоден Имот",
            "html": html
        })
        return True
    except Exception as e:
        print(f"Email error: {e}")
        return False

# Initialize DB on startup
init_db()

@app.route('/', methods=['GET'])
def home():
    return jsonify({"status": "ok", "service": "real-estate-alerts-api"})

@app.route('/health', methods=['GET'])
def health():
    return jsonify({"status": "ok", "time": datetime.utcnow().isoformat()})

@app.route('/subscribe', methods=['POST'])
def subscribe():
    data = request.json or {}
    email = data.get('email', '').strip().lower()
    cities = data.get('cities', [])
    min_discount = data.get('min_discount', 20)
    
    if not email or '@' not in email:
        return jsonify({"error": "Невалиден имейл адрес"}), 400
    
    valid_cities = ['София', 'Пловдив', 'Варна', 'Бургас', 'Русе', 'Стара Загора']
    cities = [c for c in cities if c in valid_cities]
    min_discount = max(10, min(70, int(min_discount)))
    
    conn = get_db()
    c = conn.cursor()
    
    c.execute('SELECT id, verified FROM subscribers WHERE email = ?', (email,))
    existing = c.fetchone()
    
    if existing:
        if existing['verified']:
            conn.close()
            return jsonify({"error": "Този имейл вече е абониран"}), 400
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
        return jsonify({"message": "Изпратихме имейл за потвърждение!"})
    return jsonify({"error": "Грешка при изпращане"}), 500

@app.route('/verify', methods=['GET'])
def verify():
    token = request.args.get('token', '')
    if not token:
        return redirect(f"{SITE_URL}?error=invalid_token")
    
    conn = get_db()
    c = conn.cursor()
    c.execute('SELECT id FROM subscribers WHERE verify_token = ?', (token,))
    sub = c.fetchone()
    
    if not sub:
        conn.close()
        return redirect(f"{SITE_URL}?error=invalid_token")
    
    c.execute('UPDATE subscribers SET verified = 1, verified_at = ?, verify_token = NULL WHERE id = ?',
              (datetime.utcnow().isoformat(), sub['id']))
    conn.commit()
    conn.close()
    return redirect(f"{SITE_URL}?verified=true")

@app.route('/unsubscribe', methods=['GET'])
def unsubscribe():
    token = request.args.get('token', '')
    if not token:
        return redirect(f"{SITE_URL}?error=invalid_token")
    
    conn = get_db()
    c = conn.cursor()
    c.execute('DELETE FROM subscribers WHERE unsubscribe_token = ?', (token,))
    conn.commit()
    conn.close()
    return redirect(f"{SITE_URL}?unsubscribed=true")

@app.route('/stats', methods=['GET'])
def stats():
    conn = get_db()
    c = conn.cursor()
    c.execute('SELECT COUNT(*) FROM subscribers WHERE verified = 1')
    count = c.fetchone()[0]
    conn.close()
    return jsonify({"subscribers": count})

if __name__ == '__main__':
    port = int(os.getenv('PORT', 5000))
    app.run(host='0.0.0.0', port=port)
