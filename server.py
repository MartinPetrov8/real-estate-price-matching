#!/usr/bin/env python3
"""
Simple Real Estate API Server
Uses only Python standard library (no external dependencies)
"""

import json
import sqlite3
import os
from http.server import HTTPServer, SimpleHTTPRequestHandler
from urllib.parse import urlparse, parse_qs

DB_PATH = 'data/properties.db'
PORT = 3001

class APIHandler(SimpleHTTPRequestHandler):
    def __init__(self, *args, **kwargs):
        # Serve static files from web/public
        super().__init__(*args, directory='web/public', **kwargs)
    
    def do_GET(self):
        parsed = urlparse(self.path)
        
        # API routes
        if parsed.path.startswith('/api/'):
            self.handle_api(parsed)
        else:
            # Serve static files
            super().do_GET()
    
    def handle_api(self, parsed):
        try:
            conn = sqlite3.connect(DB_PATH)
            conn.row_factory = sqlite3.Row
            params = parse_qs(parsed.query)
            
            if parsed.path == '/api/stats':
                self.send_stats(conn, params)
            elif parsed.path == '/api/listings':
                self.send_listings(conn, params)
            elif parsed.path == '/api/cities':
                self.send_cities(conn)
            else:
                self.send_json({'error': 'Unknown endpoint'}, 404)
            
            conn.close()
        except Exception as e:
            self.send_json({'error': str(e)}, 500)
    
    def send_stats(self, conn, params):
        city = params.get('city', [''])[0]
        
        query = """
            SELECT 
                COUNT(*) as total,
                ROUND(AVG(price_eur), 0) as avg_price,
                ROUND(AVG(price_per_sqm), 0) as avg_price_sqm,
                MIN(price_eur) as min_price,
                MAX(price_eur) as max_price,
                ROUND(AVG(size_sqm), 1) as avg_size
            FROM listings
            WHERE price_eur IS NOT NULL
        """
        args = []
        
        if city:
            query += " AND city LIKE ?"
            args.append(f"%{city}%")
        
        cursor = conn.execute(query, args)
        row = cursor.fetchone()
        stats = dict(row) if row else {}
        
        # Get districts
        district_query = """
            SELECT district, COUNT(*) as count, ROUND(AVG(price_per_sqm), 0) as avg_sqm
            FROM listings
            WHERE price_eur IS NOT NULL AND district IS NOT NULL
        """
        if city:
            district_query += " AND city LIKE ?"
        district_query += " GROUP BY district ORDER BY count DESC LIMIT 20"
        
        districts = [dict(r) for r in conn.execute(district_query, args if city else [])]
        stats['districts'] = districts
        
        self.send_json(stats)
    
    def send_listings(self, conn, params):
        city = params.get('city', [''])[0]
        district = params.get('district', [''])[0]
        source = params.get('source', [''])[0]
        min_price = params.get('minPrice', [''])[0]
        max_price = params.get('maxPrice', [''])[0]
        sort = params.get('sort', ['price_asc'])[0]
        limit = int(params.get('limit', ['50'])[0])
        offset = int(params.get('offset', ['0'])[0])
        
        query = "SELECT * FROM listings WHERE 1=1"
        args = []
        
        if city:
            query += " AND city LIKE ?"
            args.append(f"%{city}%")
        if district:
            query += " AND (district LIKE ? OR address LIKE ?)"
            args.extend([f"%{district}%", f"%{district}%"])
        if source:
            query += " AND source = ?"
            args.append(source)
        if min_price:
            query += " AND price_eur >= ?"
            args.append(int(min_price))
        if max_price:
            query += " AND price_eur <= ?"
            args.append(int(max_price))
        
        # Sorting
        sort_map = {
            'price_asc': 'price_eur ASC',
            'price_desc': 'price_eur DESC',
            'price_sqm_asc': 'price_per_sqm ASC',
            'price_sqm_desc': 'price_per_sqm DESC',
            'newest': 'scraped_at DESC'
        }
        query += f" ORDER BY {sort_map.get(sort, 'price_eur ASC')}"
        query += f" LIMIT {limit} OFFSET {offset}"
        
        listings = [dict(r) for r in conn.execute(query, args)]
        
        # Get total count
        count_query = "SELECT COUNT(*) FROM listings WHERE 1=1"
        count_args = args[:-2] if len(args) >= 2 else args  # Remove limit/offset
        # Rebuild count query with same filters
        count_query = "SELECT COUNT(*) FROM listings WHERE 1=1"
        count_args = []
        if city:
            count_query += " AND city LIKE ?"
            count_args.append(f"%{city}%")
        if district:
            count_query += " AND (district LIKE ? OR address LIKE ?)"
            count_args.extend([f"%{district}%", f"%{district}%"])
        if source:
            count_query += " AND source = ?"
            count_args.append(source)
        if min_price:
            count_query += " AND price_eur >= ?"
            count_args.append(int(min_price))
        if max_price:
            count_query += " AND price_eur <= ?"
            count_args.append(int(max_price))
        
        total = conn.execute(count_query, count_args).fetchone()[0]
        
        self.send_json({'listings': listings, 'total': total, 'limit': limit, 'offset': offset})
    
    def send_cities(self, conn):
        cities = [dict(r) for r in conn.execute("""
            SELECT DISTINCT city, COUNT(*) as count
            FROM listings WHERE city IS NOT NULL
            GROUP BY city ORDER BY count DESC
        """)]
        self.send_json({'cities': cities})
    
    def send_json(self, data, status=200):
        self.send_response(status)
        self.send_header('Content-Type', 'application/json')
        self.send_header('Access-Control-Allow-Origin', '*')
        self.end_headers()
        self.wfile.write(json.dumps(data).encode())
    
    def log_message(self, format, *args):
        # Quieter logging
        if '/api/' in args[0]:
            print(f"API: {args[0]}")

def main():
    # Check database exists
    if not os.path.exists(DB_PATH):
        print(f"⚠ Database not found at {DB_PATH}")
        print("Run: python3 init_db.py first")
        return
    
    # Check table
    conn = sqlite3.connect(DB_PATH)
    count = conn.execute("SELECT COUNT(*) FROM listings").fetchone()[0]
    conn.close()
    print(f"✓ Database connected: {count} listings")
    
    # Start server
    os.chdir(os.path.dirname(os.path.abspath(__file__)) or '.')
    server = HTTPServer(('0.0.0.0', PORT), APIHandler)
    print(f"🏠 Real Estate App running at http://localhost:{PORT}")
    server.serve_forever()

if __name__ == '__main__':
    main()
