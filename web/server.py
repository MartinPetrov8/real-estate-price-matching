#!/usr/bin/env python3
"""
Real Estate Web Server - Pure Python (no dependencies)
"""
import json
import sqlite3
import os
from http.server import HTTPServer, SimpleHTTPRequestHandler
from urllib.parse import urlparse, parse_qs
from pathlib import Path

DB_PATH = Path(__file__).parent.parent / 'data' / 'properties.db'

class APIHandler(SimpleHTTPRequestHandler):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=str(Path(__file__).parent / 'public'), **kwargs)
    
    def get_db(self):
        conn = sqlite3.connect(DB_PATH)
        conn.row_factory = sqlite3.Row
        return conn
    
    def send_json(self, data, status=200):
        self.send_response(status)
        self.send_header('Content-Type', 'application/json')
        self.send_header('Access-Control-Allow-Origin', '*')
        self.end_headers()
        self.wfile.write(json.dumps(data, ensure_ascii=False).encode('utf-8'))
    
    def do_GET(self):
        parsed = urlparse(self.path)
        path = parsed.path
        params = parse_qs(parsed.query)
        
        # API routes
        if path == '/api/listings':
            self.handle_listings(params)
        elif path == '/api/stats':
            self.handle_stats(params)
        elif path == '/api/cities':
            self.handle_cities()
        elif path == '/api/price-drops':
            self.handle_price_drops()
        elif path.startswith('/api/'):
            self.send_json({'error': 'Not found'}, 404)
        else:
            # Serve static files
            if path == '/':
                self.path = '/index.html'
            super().do_GET()
    
    def handle_listings(self, params):
        conn = self.get_db()
        
        city = params.get('city', [''])[0]
        min_price = params.get('minPrice', [None])[0]
        max_price = params.get('maxPrice', [None])[0]
        min_size = params.get('minSize', [None])[0]
        sort = params.get('sort', ['newest'])[0]
        limit = int(params.get('limit', ['50'])[0])
        offset = int(params.get('offset', ['0'])[0])
        
        query = 'SELECT * FROM listings WHERE 1=1'
        query_params = []
        
        if city:
            query += ' AND (city LIKE ? OR district LIKE ?)'
            query_params.extend([f'%{city}%', f'%{city}%'])
        if min_price:
            query += ' AND price_eur >= ?'
            query_params.append(int(min_price))
        if max_price:
            query += ' AND price_eur <= ?'
            query_params.append(int(max_price))
        if min_size:
            query += ' AND size_sqm >= ?'
            query_params.append(int(min_size))
        
        sort_map = {
            'price_asc': 'price_eur ASC',
            'price_desc': 'price_eur DESC',
            'price_sqm_asc': 'price_per_sqm ASC',
            'price_sqm_desc': 'price_per_sqm DESC',
            'newest': 'scraped_at DESC'
        }
        query += f' ORDER BY {sort_map.get(sort, "scraped_at DESC")}'
        
        # Count
        count_query = query.replace('SELECT *', 'SELECT COUNT(*)')
        total = conn.execute(count_query, query_params).fetchone()[0]
        
        query += f' LIMIT {limit} OFFSET {offset}'
        rows = conn.execute(query, query_params).fetchall()
        listings = [dict(row) for row in rows]
        conn.close()
        
        self.send_json({'listings': listings, 'total': total, 'limit': limit, 'offset': offset})
    
    def handle_stats(self, params):
        conn = self.get_db()
        
        stats = conn.execute('''
            SELECT 
                COUNT(*) as total,
                ROUND(AVG(price_eur), 0) as avg_price,
                ROUND(AVG(price_per_sqm), 0) as avg_price_sqm,
                MIN(price_eur) as min_price,
                MAX(price_eur) as max_price,
                ROUND(AVG(size_sqm), 1) as avg_size
            FROM listings WHERE price_eur IS NOT NULL
        ''').fetchone()
        
        districts = conn.execute('''
            SELECT district, COUNT(*) as count, ROUND(AVG(price_per_sqm), 0) as avg_sqm
            FROM listings WHERE price_eur IS NOT NULL AND district IS NOT NULL
            GROUP BY district ORDER BY count DESC LIMIT 20
        ''').fetchall()
        
        conn.close()
        
        self.send_json({
            'total': stats['total'],
            'avg_price': stats['avg_price'],
            'avg_price_sqm': stats['avg_price_sqm'],
            'min_price': stats['min_price'],
            'max_price': stats['max_price'],
            'avg_size': stats['avg_size'],
            'districts': [dict(d) for d in districts]
        })
    
    def handle_cities(self):
        conn = self.get_db()
        cities = conn.execute('''
            SELECT city, COUNT(*) as count FROM listings
            WHERE city IS NOT NULL GROUP BY city ORDER BY count DESC
        ''').fetchall()
        conn.close()
        self.send_json({'cities': [dict(c) for c in cities]})
    
    def handle_price_drops(self):
        self.send_json({'listings': []})
    
    def log_message(self, format, *args):
        pass  # Suppress logging

if __name__ == '__main__':
    port = 3456
    print(f"🏠 Real Estate Tracker starting on http://localhost:{port}")
    print(f"📊 Database: {DB_PATH}")
    server = HTTPServer(('0.0.0.0', port), APIHandler)
    server.serve_forever()
