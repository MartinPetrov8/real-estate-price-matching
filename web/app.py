#!/usr/bin/env python3
"""
Real Estate Web App - Flask Server
"""
import sqlite3
from flask import Flask, jsonify, request, send_from_directory
from pathlib import Path

app = Flask(__name__, static_folder='public')
DB_PATH = Path(__file__).parent.parent / 'data' / 'properties.db'

def get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

@app.route('/')
def index():
    return send_from_directory('public', 'index.html')

@app.route('/<path:path>')
def static_files(path):
    return send_from_directory('public', path)

@app.route('/api/listings')
def get_listings():
    conn = get_db()
    
    city = request.args.get('city', '')
    min_price = request.args.get('minPrice', type=int)
    max_price = request.args.get('maxPrice', type=int)
    min_size = request.args.get('minSize', type=int)
    max_size = request.args.get('maxSize', type=int)
    sort = request.args.get('sort', 'newest')
    limit = request.args.get('limit', 50, type=int)
    offset = request.args.get('offset', 0, type=int)
    
    query = 'SELECT * FROM listings WHERE 1=1'
    params = []
    
    if city:
        query += ' AND (city LIKE ? OR district LIKE ?)'
        params.extend([f'%{city}%', f'%{city}%'])
    if min_price:
        query += ' AND price_eur >= ?'
        params.append(min_price)
    if max_price:
        query += ' AND price_eur <= ?'
        params.append(max_price)
    if min_size:
        query += ' AND size_sqm >= ?'
        params.append(min_size)
    if max_size:
        query += ' AND size_sqm <= ?'
        params.append(max_size)
    
    # Sorting
    sort_map = {
        'price_asc': 'price_eur ASC',
        'price_desc': 'price_eur DESC',
        'price_sqm_asc': 'price_per_sqm ASC',
        'price_sqm_desc': 'price_per_sqm DESC',
        'size_asc': 'size_sqm ASC',
        'size_desc': 'size_sqm DESC',
        'newest': 'scraped_at DESC'
    }
    query += f' ORDER BY {sort_map.get(sort, "scraped_at DESC")}'
    
    # Count total
    count_query = query.replace('SELECT *', 'SELECT COUNT(*)')
    total = conn.execute(count_query, params).fetchone()[0]
    
    # Get page
    query += f' LIMIT {limit} OFFSET {offset}'
    rows = conn.execute(query, params).fetchall()
    
    listings = [dict(row) for row in rows]
    conn.close()
    
    return jsonify({
        'listings': listings,
        'total': total,
        'limit': limit,
        'offset': offset
    })

@app.route('/api/stats')
def get_stats():
    conn = get_db()
    
    stats = conn.execute('''
        SELECT 
            COUNT(*) as total,
            ROUND(AVG(price_eur), 0) as avg_price,
            ROUND(AVG(price_per_sqm), 0) as avg_price_sqm,
            MIN(price_eur) as min_price,
            MAX(price_eur) as max_price,
            ROUND(AVG(size_sqm), 1) as avg_size
        FROM listings
        WHERE price_eur IS NOT NULL
    ''').fetchone()
    
    districts = conn.execute('''
        SELECT district, COUNT(*) as count, ROUND(AVG(price_per_sqm), 0) as avg_sqm
        FROM listings
        WHERE price_eur IS NOT NULL AND district IS NOT NULL
        GROUP BY district
        ORDER BY count DESC
        LIMIT 20
    ''').fetchall()
    
    conn.close()
    
    return jsonify({
        'total': stats['total'],
        'avg_price': stats['avg_price'],
        'avg_price_sqm': stats['avg_price_sqm'],
        'min_price': stats['min_price'],
        'max_price': stats['max_price'],
        'avg_size': stats['avg_size'],
        'districts': [dict(d) for d in districts]
    })

@app.route('/api/cities')
def get_cities():
    conn = get_db()
    cities = conn.execute('''
        SELECT city, COUNT(*) as count
        FROM listings
        WHERE city IS NOT NULL
        GROUP BY city
        ORDER BY count DESC
    ''').fetchall()
    conn.close()
    return jsonify({'cities': [dict(c) for c in cities]})

@app.route('/api/price-drops')
def get_price_drops():
    conn = get_db()
    try:
        drops = conn.execute('''
            SELECT l.*, 
                   ph.price_eur as old_price,
                   l.price_eur as new_price,
                   ROUND((ph.price_eur - l.price_eur) * 100.0 / ph.price_eur, 1) as drop_percent
            FROM listings l
            JOIN price_history ph ON l.id = ph.listing_id
            WHERE ph.price_eur > l.price_eur
            ORDER BY drop_percent DESC
            LIMIT 50
        ''').fetchall()
        conn.close()
        return jsonify({'listings': [dict(d) for d in drops]})
    except:
        conn.close()
        return jsonify({'listings': []})

if __name__ == '__main__':
    print(f"🏠 Starting Real Estate Tracker...")
    print(f"📊 Database: {DB_PATH}")
    app.run(host='0.0.0.0', port=3456, debug=False)
