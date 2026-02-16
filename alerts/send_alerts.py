#!/usr/bin/env python3
"""
Email Alert Sender
==================
Sends deal alerts to verified subscribers based on their preferences.
Run daily after the scraper pipeline.
"""

import sqlite3
import json
import os
import hashlib
import secrets
from datetime import datetime
from typing import List, Dict, Optional
from dotenv import load_dotenv

# Load environment
load_dotenv()

try:
    import resend
    resend.api_key = os.getenv("RESEND_API_KEY")
except ImportError:
    print("ERROR: Install resend: pip install resend python-dotenv")
    exit(1)

# Config
DEALS_PATH = "deals.json"
SUBSCRIBERS_DB = "data/subscribers.db"
SENDER_EMAIL = os.getenv("SENDER_EMAIL", "onboarding@resend.dev")
SENDER_NAME = os.getenv("SENDER_NAME", "Изгоден Имот")
SITE_URL = "https://martinpetrov8.github.io/real-estate-price-matching"

def log(msg):
    print(f"[{datetime.now().strftime('%H:%M:%S')}] {msg}")

def load_deals() -> List[Dict]:
    """Load deals from JSON file."""
    if not os.path.exists(DEALS_PATH):
        return []
    with open(DEALS_PATH, 'r', encoding='utf-8') as f:
        return json.load(f)

def get_verified_subscribers(conn) -> List[Dict]:
    """Get all verified subscribers."""
    c = conn.cursor()
    c.execute('''
        SELECT id, email, cities, min_discount, last_deal_ids 
        FROM subscribers 
        WHERE verified = 1
    ''')
    subscribers = []
    for row in c.fetchall():
        subscribers.append({
            'id': row[0],
            'email': row[1],
            'cities': json.loads(row[2]) if row[2] else [],
            'min_discount': row[3] or 20,
            'last_deal_ids': set(json.loads(row[4])) if row[4] else set()
        })
    return subscribers

def filter_deals_for_subscriber(deals: List[Dict], sub: Dict) -> List[Dict]:
    """Filter deals matching subscriber preferences."""
    matching = []
    for deal in deals:
        # Skip already sent
        deal_id = str(deal.get('id', ''))
        if deal_id in sub['last_deal_ids']:
            continue
        
        # Check city
        city = deal.get('city', '')
        if sub['cities'] and city not in sub['cities']:
            continue
        
        # Check discount
        discount = deal.get('discount_pct', 0)
        if discount < sub['min_discount']:
            continue
        
        matching.append(deal)
    
    return matching[:10]  # Max 10 per email

def generate_email_html(deals: List[Dict], unsubscribe_url: str) -> str:
    """Generate HTML email with deal cards."""
    
    deals_html = ""
    for deal in deals:
        discount = deal.get('discount_pct', 0)
        price = deal.get('price_eur', 0)
        market_price = deal.get('market_median_eur', 0)
        city = deal.get('city', 'Неизвестен')
        neighborhood = deal.get('neighborhood', '')
        size = deal.get('size_sqm', 0)
        url = deal.get('url', '#')
        auction_end = deal.get('auction_end', 'Неизвестна')
        
        location = f"{city}, {neighborhood}" if neighborhood else city
        
        deals_html += f'''
        <div style="background:#fff;border:1px solid #e5e7eb;border-radius:12px;padding:20px;margin-bottom:16px;">
            <div style="display:flex;justify-content:space-between;align-items:start;margin-bottom:12px;">
                <div>
                    <h3 style="margin:0 0 4px 0;color:#111;font-size:18px;">🏠 {location}</h3>
                    <p style="margin:0;color:#6b7280;font-size:14px;">{size} m² • Търг до {auction_end}</p>
                </div>
                <div style="background:#dcfce7;color:#166534;padding:6px 12px;border-radius:20px;font-weight:bold;font-size:14px;">
                    -{discount}%
                </div>
            </div>
            <div style="display:flex;gap:24px;margin-bottom:16px;">
                <div>
                    <p style="margin:0;color:#6b7280;font-size:12px;">Цена на търга</p>
                    <p style="margin:0;color:#111;font-size:20px;font-weight:bold;">€{price:,.0f}</p>
                </div>
                <div>
                    <p style="margin:0;color:#6b7280;font-size:12px;">Пазарна цена</p>
                    <p style="margin:0;color:#6b7280;font-size:20px;text-decoration:line-through;">€{market_price:,.0f}</p>
                </div>
            </div>
            <a href="{url}" style="display:inline-block;background:#2563eb;color:#fff;padding:10px 20px;border-radius:8px;text-decoration:none;font-weight:500;">
                Виж офертата →
            </a>
        </div>
        '''
    
    html = f'''
    <!DOCTYPE html>
    <html>
    <head>
        <meta charset="utf-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
    </head>
    <body style="margin:0;padding:0;background:#f3f4f6;font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,sans-serif;">
        <div style="max-width:600px;margin:0 auto;padding:24px;">
            <!-- Header -->
            <div style="text-align:center;margin-bottom:24px;">
                <h1 style="margin:0;color:#111;font-size:24px;">🏠 Изгоден Имот</h1>
                <p style="margin:8px 0 0 0;color:#6b7280;">Нови оферти под пазарната цена</p>
            </div>
            
            <!-- Deals -->
            <div style="margin-bottom:24px;">
                <p style="color:#374151;margin-bottom:16px;">
                    Здравей! Намерихме <strong>{len(deals)} нови оферти</strong>, които отговарят на твоите критерии:
                </p>
                {deals_html}
            </div>
            
            <!-- CTA -->
            <div style="text-align:center;margin-bottom:24px;">
                <a href="{SITE_URL}" style="display:inline-block;background:#111;color:#fff;padding:14px 28px;border-radius:8px;text-decoration:none;font-weight:500;">
                    Виж всички оферти
                </a>
            </div>
            
            <!-- Footer -->
            <div style="text-align:center;padding-top:24px;border-top:1px solid #e5e7eb;">
                <p style="color:#9ca3af;font-size:12px;margin:0;">
                    Получаваш този имейл, защото си абониран за известия.<br>
                    <a href="{unsubscribe_url}" style="color:#6b7280;">Отпиши се</a>
                </p>
            </div>
        </div>
    </body>
    </html>
    '''
    return html

def send_email(to_email: str, subject: str, html: str) -> bool:
    """Send email via Resend."""
    try:
        response = resend.Emails.send({
            "from": f"{SENDER_NAME} <{SENDER_EMAIL}>",
            "to": to_email,
            "subject": subject,
            "html": html
        })
        return True
    except Exception as e:
        log(f"❌ Failed to send to {to_email}: {e}")
        return False

def update_subscriber_sent(conn, sub_id: int, deal_ids: List[str]):
    """Update subscriber's last_sent_at and last_deal_ids."""
    c = conn.cursor()
    c.execute('''
        UPDATE subscribers 
        SET last_sent_at = ?, last_deal_ids = ?
        WHERE id = ?
    ''', (datetime.utcnow().isoformat(), json.dumps(deal_ids), sub_id))
    conn.commit()

def main():
    log("📧 Email Alert Sender")
    log("=" * 50)
    
    # Load deals
    deals = load_deals()
    log(f"📊 Loaded {len(deals)} deals")
    
    if not deals:
        log("⚠️ No deals to send")
        return
    
    # Connect to subscribers DB
    conn = sqlite3.connect(SUBSCRIBERS_DB)
    subscribers = get_verified_subscribers(conn)
    log(f"👥 Found {len(subscribers)} verified subscribers")
    
    if not subscribers:
        log("⚠️ No subscribers yet")
        conn.close()
        return
    
    # Send emails
    sent_count = 0
    for sub in subscribers:
        matching_deals = filter_deals_for_subscriber(deals, sub)
        
        if not matching_deals:
            log(f"  {sub['email']}: 0 matching deals, skipping")
            continue
        
        # Generate unsubscribe URL (would need token in real implementation)
        unsubscribe_url = f"{SITE_URL}?unsubscribe={sub['id']}"
        
        # Generate email
        subject = f"🏠 {len(matching_deals)} нови оферти под пазарната цена"
        html = generate_email_html(matching_deals, unsubscribe_url)
        
        # Send
        if send_email(sub['email'], subject, html):
            sent_count += 1
            deal_ids = [str(d.get('id', '')) for d in matching_deals]
            update_subscriber_sent(conn, sub['id'], deal_ids)
            log(f"  ✅ {sub['email']}: sent {len(matching_deals)} deals")
        else:
            log(f"  ❌ {sub['email']}: failed")
    
    conn.close()
    log("=" * 50)
    log(f"✅ Sent {sent_count}/{len(subscribers)} emails")

if __name__ == "__main__":
    main()
