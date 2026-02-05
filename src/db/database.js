const Database = require('better-sqlite3');
const fs = require('fs');
const path = require('path');

const DB_PATH = path.join(__dirname, '../../data/properties.db');
const SCHEMA_PATH = path.join(__dirname, 'schema.sql');

class PropertyDatabase {
    constructor() {
        // Ensure data directory exists
        const dataDir = path.dirname(DB_PATH);
        if (!fs.existsSync(dataDir)) {
            fs.mkdirSync(dataDir, { recursive: true });
        }
        
        this.db = new Database(DB_PATH);
        this.db.pragma('journal_mode = WAL');
        this.initSchema();
    }

    initSchema() {
        const schema = fs.readFileSync(SCHEMA_PATH, 'utf8');
        this.db.exec(schema);
    }

    // КЧСИ Methods
    upsertKchsiProperty(property) {
        const stmt = this.db.prepare(`
            INSERT INTO kchsi_properties (
                bcpea_id, price_eur, city, address, description,
                sqm, rooms, floor, property_type,
                auction_start, auction_end, announcement_date,
                court, executor, cadastral_id
            ) VALUES (
                @bcpea_id, @price_eur, @city, @address, @description,
                @sqm, @rooms, @floor, @property_type,
                @auction_start, @auction_end, @announcement_date,
                @court, @executor, @cadastral_id
            )
            ON CONFLICT(bcpea_id) DO UPDATE SET
                price_eur = @price_eur,
                description = @description,
                sqm = @sqm,
                rooms = @rooms,
                floor = @floor,
                auction_start = @auction_start,
                auction_end = @auction_end,
                announcement_date = @announcement_date,
                updated_at = CURRENT_TIMESTAMP
        `);
        return stmt.run(property);
    }

    getKchsiProperties(city = null) {
        if (city) {
            return this.db.prepare('SELECT * FROM kchsi_properties WHERE city = ?').all(city);
        }
        return this.db.prepare('SELECT * FROM kchsi_properties').all();
    }

    getActiveAuctions() {
        return this.db.prepare(`
            SELECT * FROM kchsi_properties 
            WHERE auction_end >= date('now')
            ORDER BY auction_end ASC
        `).all();
    }

    // Market Methods
    insertMarketListing(listing) {
        const stmt = this.db.prepare(`
            INSERT INTO market_listings (
                source, source_id, price_eur, price_bgn,
                city, neighborhood, address,
                sqm, rooms, floor, total_floors,
                property_type, construction_type, year_built,
                price_per_sqm, url
            ) VALUES (
                @source, @source_id, @price_eur, @price_bgn,
                @city, @neighborhood, @address,
                @sqm, @rooms, @floor, @total_floors,
                @property_type, @construction_type, @year_built,
                @price_per_sqm, @url
            )
        `);
        return stmt.run(listing);
    }

    getMarketListings(city = null, source = null) {
        let query = 'SELECT * FROM market_listings WHERE 1=1';
        const params = [];
        
        if (city) {
            query += ' AND city = ?';
            params.push(city);
        }
        if (source) {
            query += ' AND source = ?';
            params.push(source);
        }
        
        return this.db.prepare(query).all(...params);
    }

    getComparableListings(sqm, city, tolerance = 0.2) {
        const minSqm = sqm * (1 - tolerance);
        const maxSqm = sqm * (1 + tolerance);
        
        return this.db.prepare(`
            SELECT * FROM market_listings 
            WHERE city = ? 
            AND sqm BETWEEN ? AND ?
            ORDER BY sqm ASC
        `).all(city, minSqm, maxSqm);
    }

    // Match Methods
    insertMatch(match) {
        const stmt = this.db.prepare(`
            INSERT OR REPLACE INTO matches (
                kchsi_id, market_id, similarity_score,
                price_difference_eur, price_difference_pct
            ) VALUES (
                @kchsi_id, @market_id, @similarity_score,
                @price_difference_eur, @price_difference_pct
            )
        `);
        return stmt.run(match);
    }

    getBestDeals(limit = 20) {
        return this.db.prepare(`
            SELECT 
                k.*,
                m.price_eur as market_price,
                m.source as market_source,
                m.url as market_url,
                m.neighborhood,
                ma.similarity_score,
                ma.price_difference_eur,
                ma.price_difference_pct
            FROM matches ma
            JOIN kchsi_properties k ON ma.kchsi_id = k.id
            JOIN market_listings m ON ma.market_id = m.id
            WHERE k.auction_end >= date('now')
            ORDER BY ma.price_difference_pct DESC
            LIMIT ?
        `).all(limit);
    }

    // Stats
    getStats() {
        return {
            kchsi_count: this.db.prepare('SELECT COUNT(*) as count FROM kchsi_properties').get().count,
            market_count: this.db.prepare('SELECT COUNT(*) as count FROM market_listings').get().count,
            match_count: this.db.prepare('SELECT COUNT(*) as count FROM matches').get().count,
            active_auctions: this.db.prepare(`
                SELECT COUNT(*) as count FROM kchsi_properties 
                WHERE auction_end >= date('now')
            `).get().count
        };
    }

    close() {
        this.db.close();
    }
}

module.exports = PropertyDatabase;
