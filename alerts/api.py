#!/usr/bin/env python3
"""
Subscribe API - Simple Flask server
===================================
Handles email subscriptions. Can run standalone or deploy to Vercel/Railway.

Endpoints:
  POST /subscribe - Subscribe with email + preferences
  GET  /verify?token=xxx - Verify email
  GET  /unsubscribe?token=xxx - Unsubscribe
"""

import sqlite3
import json
import os
import secrets
import hashlib
from datetime import datetime
from flask import Flask, request, jsonify, redirect
from flask_cors import CORS
from dotenv import load_dotenv

load_dotenv()

try:
    import resend
    resend.api_key = os.getenv("RESEND_API_KEY")
except ImportError:
    resend = None

app = Flask(__name__)
CORS(app)  # Allow requests from GitHub Pages

# Config
DB_PATH = os.getenv("SUBSCRIBERS_DB", "data/subscribers.db")
SENDER_EMAIL = os.getenv("SENDER_EMAIL", "onboarding@resend.dev")
SENDER_NAME = os.getenv("SENDER_NAME", "Изгоден Имот")
SITE_URL = os.getenv("SITE_URL", "https://martinpetrov8.github.io/real-estate-price-matching")
API_URL = os.getenv("API_URL", "http://localhost:5000")

def get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

def generate_token():
    return secrets.token_urlsafe(32)

def send_verification_email(email: str, token: str) -> bool:
    """Send verification email."""
    if not resend:
        print(f"[DEBUG] Would send verification to {email}")
        return True
    
    verify_url = f"{API_URL}/verify?token={token}"
    
    html = f'''
    <div style="font-family:sans-serif;max-width:500px;margin:0 auto;padding:24px;">
        <h1 style="color:#111;">🏠 Потвърди абонамента си</h1>
        <p>Благодарим ти за абонамента за известия от Изгоден Имот!</p>
        <p>Моля, потвърди имейл адреса си:</p>
        <a href="{verify_url}" 
           style="display:inline-block;background:#2563eb;color:#fff;padding:14px 28px;border-radius:8px;text-decoration:none;margin:16px 0;">
            Потвърди имейла
        </a>
        <p style="color:#6b7280;font-size:14px;">
            Ако не си заявил този абонамент, просто игнорирай този имейл.
        </p>
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
        print(f"Failed to send verification: {e}")
        return False

@app.route('/health', methods=['GET'])
def health():
    return jsonify({"status": "ok", "time": datetime.utcnow().isoformat()})

@app.route('/subscribe', methods=['POST'])
def subscribe():
    """Subscribe a new email."""
    data = request.json or {}
    
    email = data.get('email', '').strip().lower()
    cities = data.get('cities', [])  # List of cities
    min_discount = data.get('min_discount', 20)
    
    # Validate email
    if not email or '@' not in email or '.' not in email:
        return jsonify({"error": "Невалиден имейл адрес"}), 400
    
    # Validate cities
    valid_cities = ['София', 'Пловдив', 'Варна', 'Бургас', 'Русе', 'Стара Загора']
    cities = [c for c in cities if c in valid_cities]
    
    # Validate discount
    min_discount = max(10, min(70, int(min_discount)))
    
    conn = get_db()
    c = conn.cursor()
    
    # Check if already subscribed
    c.execute('SELECT id, verified FROM subscribers WHERE email = ?', (email,))
    existing = c.fetchone()
    
    if existing:
        if existing['verified']:
            conn.close()
            return jsonify({"error": "Този имейл вече е абониран"}), 400
        else:
            # Resend verification
            c.execute('SELECT verify_token FROM subscribers WHERE id = ?', (existing['id'],))
            token = c.fetchone()['verify_token']
            send_verification_email(email, token)
            conn.close()
            return jsonify({"message": "Изпратихме ти нов линк за потвърждение"})
    
    # Create new subscriber
    verify_token = generate_token()
    unsubscribe_token = generate_token()
    
    c.execute('''
        INSERT INTO subscribers (email, cities, min_discount, verify_token, unsubscribe_token)
        VALUES (?, ?, ?, ?, ?)
    ''', (email, json.dumps(cities), min_discount, verify_token, unsubscribe_token))
    conn.commit()
    conn.close()
    
    # Send verification email
    if send_verification_email(email, verify_token):
        return jsonify({
            "message": "Изпратихме ти имейл за потвърждение. Провери входящата си поща."
        })
    else:
        return jsonify({"error": "Грешка при изпращане на имейл"}), 500

@app.route('/verify', methods=['GET'])
def verify():
    """Verify email via token."""
    token = request.args.get('token', '')
    
    if not token:
        return redirect(f"{SITE_URL}?error=invalid_token")
    
    conn = get_db()
    c = conn.cursor()
    
    c.execute('SELECT id, email FROM subscribers WHERE verify_token = ?', (token,))
    sub = c.fetchone()
    
    if not sub:
        conn.close()
        return redirect(f"{SITE_URL}?error=invalid_token")
    
    # Mark as verified
    c.execute('''
        UPDATE subscribers 
        SET verified = 1, verified_at = ?, verify_token = NULL
        WHERE id = ?
    ''', (datetime.utcnow().isoformat(), sub['id']))
    conn.commit()
    conn.close()
    
    return redirect(f"{SITE_URL}?verified=true")

@app.route('/unsubscribe', methods=['GET'])
def unsubscribe():
    """Unsubscribe via token."""
    token = request.args.get('token', '')
    
    if not token:
        return redirect(f"{SITE_URL}?error=invalid_token")
    
    conn = get_db()
    c = conn.cursor()
    
    c.execute('DELETE FROM subscribers WHERE unsubscribe_token = ?', (token,))
    deleted = c.rowcount
    conn.commit()
    conn.close()
    
    if deleted:
        return redirect(f"{SITE_URL}?unsubscribed=true")
    else:
        return redirect(f"{SITE_URL}?error=not_found")

@app.route('/stats', methods=['GET'])
def stats():
    """Get subscriber stats (public)."""
    conn = get_db()
    c = conn.cursor()
    c.execute('SELECT COUNT(*) FROM subscribers WHERE verified = 1')
    count = c.fetchone()[0]
    conn.close()
    return jsonify({"subscribers": count})

if __name__ == '__main__':
    port = int(os.getenv('PORT', 5000))
    app.run(host='0.0.0.0', port=port, debug=True)
