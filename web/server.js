const express = require('express');
const sqlite3 = require('better-sqlite3');
const path = require('path');
const cors = require('cors');

const app = express();
const PORT = process.env.PORT || 3000;

// Database connection
const dbPath = path.join(__dirname, '..', 'data', 'properties.db');
let db;

const fs = require('fs');
if (fs.existsSync(dbPath)) {
    try {
        db = sqlite3(dbPath);
        console.log('✓ Database connected:', dbPath);
    } catch (e) {
        console.log('Database error:', e.message);
    }
} else {
    console.log('Database not found at:', dbPath);
}

app.use(cors());
app.use(express.json());
app.use(express.static(path.join(__dirname, 'public')));

// API: Get listings with filters
app.get('/api/listings', (req, res) => {
    if (!db) return res.json({ listings: [], total: 0 });
    
    const { city, district, source, minPrice, maxPrice, minSize, maxSize, sort, limit = 50, offset = 0 } = req.query;
    
    let query = 'SELECT * FROM listings WHERE 1=1';
    const params = [];
    
    if (city) {
        query += ' AND city LIKE ?';
        params.push(`%${city}%`);
    }
    if (district) {
        query += ' AND (district LIKE ? OR address LIKE ?)';
        params.push(`%${district}%`, `%${district}%`);
    }
    if (source) {
        query += ' AND source = ?';
        params.push(source);
    }
    if (minPrice) {
        query += ' AND price_eur >= ?';
        params.push(parseInt(minPrice));
    }
    if (maxPrice) {
        query += ' AND price_eur <= ?';
        params.push(parseInt(maxPrice));
    }
    if (minSize) {
        query += ' AND size_sqm >= ?';
        params.push(parseInt(minSize));
    }
    if (maxSize) {
        query += ' AND size_sqm <= ?';
        params.push(parseInt(maxSize));
    }
    
    // Sorting
    const sortOptions = {
        'price_asc': 'price_eur ASC',
        'price_desc': 'price_eur DESC',
        'price_sqm_asc': 'price_per_sqm ASC',
        'price_sqm_desc': 'price_per_sqm DESC',
        'size_asc': 'size_sqm ASC',
        'size_desc': 'size_sqm DESC',
        'newest': 'scraped_at DESC'
    };
    query += ` ORDER BY ${sortOptions[sort] || 'scraped_at DESC'}`;
    query += ` LIMIT ? OFFSET ?`;
    params.push(parseInt(limit), parseInt(offset));
    
    try {
        const listings = db.prepare(query).all(...params);
        const countQuery = query.replace(/SELECT \*/, 'SELECT COUNT(*) as count').replace(/LIMIT.*/, '');
        const total = db.prepare(countQuery).get(...params.slice(0, -2))?.count || 0;
        
        res.json({ listings, total, limit: parseInt(limit), offset: parseInt(offset) });
    } catch (e) {
        res.status(500).json({ error: e.message });
    }
});

// API: Get market statistics
app.get('/api/stats', (req, res) => {
    if (!db) return res.json({ error: 'No data yet' });
    
    const { city, propertyType } = req.query;
    
    let query = `
        SELECT 
            COUNT(*) as total,
            ROUND(AVG(price_eur), 0) as avg_price,
            ROUND(AVG(price_per_sqm), 0) as avg_price_sqm,
            MIN(price_eur) as min_price,
            MAX(price_eur) as max_price,
            ROUND(AVG(size_sqm), 1) as avg_size,
            COUNT(DISTINCT city) as cities,
            COUNT(DISTINCT district) as districts
        FROM listings
        WHERE price_eur IS NOT NULL
    `;
    const params = [];
    
    if (city) {
        query += ' AND city LIKE ?';
        params.push(`%${city}%`);
    }
    if (propertyType) {
        query += ' AND property_type = ?';
        params.push(propertyType);
    }
    
    try {
        const stats = db.prepare(query).get(...params);
        
        // Get district breakdown
        const districts = db.prepare(`
            SELECT district, COUNT(*) as count, ROUND(AVG(price_per_sqm), 0) as avg_sqm
            FROM listings
            WHERE price_eur IS NOT NULL AND district IS NOT NULL
            ${city ? 'AND city LIKE ?' : ''}
            GROUP BY district
            ORDER BY count DESC
            LIMIT 20
        `).all(city ? `%${city}%` : []);
        
        res.json({ ...stats, districts });
    } catch (e) {
        res.status(500).json({ error: e.message });
    }
});

// API: Get price history for a listing
app.get('/api/listings/:id/history', (req, res) => {
    if (!db) return res.json({ history: [] });
    
    try {
        const history = db.prepare(`
            SELECT price_eur, recorded_at 
            FROM price_history 
            WHERE listing_id = ?
            ORDER BY recorded_at
        `).all(req.params.id);
        
        res.json({ history });
    } catch (e) {
        res.status(500).json({ error: e.message });
    }
});

// API: Get unique cities
app.get('/api/cities', (req, res) => {
    if (!db) return res.json({ cities: [] });
    
    try {
        const cities = db.prepare(`
            SELECT DISTINCT city, COUNT(*) as count
            FROM listings
            WHERE city IS NOT NULL
            GROUP BY city
            ORDER BY count DESC
        `).all();
        
        res.json({ cities });
    } catch (e) {
        res.status(500).json({ error: e.message });
    }
});

// API: Get price drops
app.get('/api/price-drops', (req, res) => {
    if (!db) return res.json({ listings: [] });
    
    try {
        const drops = db.prepare(`
            SELECT l.*, 
                   ph.price_eur as old_price,
                   l.price_eur as new_price,
                   ROUND((ph.price_eur - l.price_eur) * 100.0 / ph.price_eur, 1) as drop_percent
            FROM listings l
            JOIN price_history ph ON l.id = ph.listing_id
            WHERE ph.price_eur > l.price_eur
            ORDER BY drop_percent DESC
            LIMIT 50
        `).all();
        
        res.json({ listings: drops });
    } catch (e) {
        res.status(500).json({ error: e.message });
    }
});

app.listen(PORT, '0.0.0.0', () => {
    console.log(`🏠 Real Estate App running at http://localhost:${PORT}`);
});
