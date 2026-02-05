/**
 * Property Matching Analyzer
 * Compares КЧСИ auctions to market listings to find undervalued properties
 */

const PropertyDatabase = require('../db/database');

// Similarity thresholds
const CONFIG = {
    SQM_TOLERANCE: 0.20,      // ±20% square meters
    ROOMS_TOLERANCE: 1,        // ±1 room
    FLOOR_TOLERANCE: 2,        // ±2 floors
    MIN_SIMILARITY_SCORE: 0.5, // Minimum overall similarity
    MIN_DISCOUNT_PCT: 15       // Minimum discount to flag as deal
};

/**
 * Calculate similarity score between КЧСИ property and market listing
 * Returns score from 0 to 1
 */
function calculateSimilarity(kchsi, market) {
    let score = 0;
    let factors = 0;
    
    // City must match (already filtered, but double-check)
    if (kchsi.city !== market.city) return 0;
    
    // Square meters similarity (most important)
    if (kchsi.sqm && market.sqm) {
        const sqmDiff = Math.abs(kchsi.sqm - market.sqm) / kchsi.sqm;
        if (sqmDiff <= CONFIG.SQM_TOLERANCE) {
            score += (1 - sqmDiff / CONFIG.SQM_TOLERANCE) * 3; // Weight: 3x
            factors += 3;
        } else {
            return 0; // Outside tolerance = no match
        }
    }
    
    // Room count similarity
    if (kchsi.rooms && market.rooms) {
        const roomDiff = Math.abs(kchsi.rooms - market.rooms);
        if (roomDiff <= CONFIG.ROOMS_TOLERANCE) {
            score += (1 - roomDiff / (CONFIG.ROOMS_TOLERANCE + 1)) * 2; // Weight: 2x
            factors += 2;
        }
    }
    
    // Floor similarity (less important)
    if (kchsi.floor && market.floor) {
        const floorDiff = Math.abs(kchsi.floor - market.floor);
        if (floorDiff <= CONFIG.FLOOR_TOLERANCE) {
            score += (1 - floorDiff / (CONFIG.FLOOR_TOLERANCE + 1)); // Weight: 1x
            factors += 1;
        }
    }
    
    // Property type match
    if (kchsi.property_type && market.property_type) {
        if (kchsi.property_type === market.property_type) {
            score += 1;
            factors += 1;
        }
    }
    
    return factors > 0 ? score / factors : 0;
}

/**
 * Find best market matches for a КЧСИ property
 */
function findMatches(kchsiProperty, marketListings) {
    const matches = [];
    
    for (const market of marketListings) {
        // Must have price and sqm
        if (!market.price_eur || !market.sqm) continue;
        if (!kchsiProperty.price_eur) continue;
        
        const similarity = calculateSimilarity(kchsiProperty, market);
        
        if (similarity >= CONFIG.MIN_SIMILARITY_SCORE) {
            const priceDiffEur = market.price_eur - kchsiProperty.price_eur;
            const priceDiffPct = (priceDiffEur / market.price_eur) * 100;
            
            matches.push({
                kchsi_id: kchsiProperty.id,
                market_id: market.id,
                similarity_score: Math.round(similarity * 100) / 100,
                price_difference_eur: Math.round(priceDiffEur),
                price_difference_pct: Math.round(priceDiffPct * 10) / 10,
                market_listing: market
            });
        }
    }
    
    // Sort by price difference (best deals first)
    matches.sort((a, b) => b.price_difference_pct - a.price_difference_pct);
    
    return matches;
}

/**
 * Format currency for display
 */
function formatEur(amount) {
    if (!amount) return '?';
    return '€' + amount.toLocaleString('de-DE');
}

/**
 * Main analysis function
 */
async function analyze() {
    console.log('=== Property Matching Analysis ===\n');
    
    const db = new PropertyDatabase();
    
    try {
        // Get stats
        const stats = db.getStats();
        console.log(`Database status:`);
        console.log(`  КЧСИ properties: ${stats.kchsi_count}`);
        console.log(`  Active auctions: ${stats.active_auctions}`);
        console.log(`  Market listings: ${stats.market_count}`);
        console.log(`  Existing matches: ${stats.match_count}\n`);
        
        if (stats.kchsi_count === 0) {
            console.log('No КЧСИ properties found. Run the КЧСИ scraper first:');
            console.log('  npm run scrape:kchsi');
            return;
        }
        
        if (stats.market_count === 0) {
            console.log('No market listings found. Run the market scraper first:');
            console.log('  npm run scrape:imot');
            return;
        }
        
        // Get active auctions
        const auctions = db.getActiveAuctions();
        console.log(`Analyzing ${auctions.length} active auctions...\n`);
        
        let totalMatches = 0;
        let dealsFound = 0;
        const topDeals = [];
        
        for (const auction of auctions) {
            // Skip if missing key data
            if (!auction.sqm || !auction.price_eur) {
                console.log(`⚠ Skipping ${auction.bcpea_id}: missing sqm or price`);
                continue;
            }
            
            // Get comparable listings
            const comparables = db.getComparableListings(auction.sqm, auction.city, CONFIG.SQM_TOLERANCE);
            
            if (comparables.length === 0) {
                console.log(`- ${auction.bcpea_id} (${auction.city}, ${auction.sqm}m²): No comparables found`);
                continue;
            }
            
            // Find matches
            const matches = findMatches(auction, comparables);
            
            if (matches.length === 0) {
                console.log(`- ${auction.bcpea_id} (${auction.city}, ${auction.sqm}m²): No matches above threshold`);
                continue;
            }
            
            // Save matches to database
            for (const match of matches) {
                db.insertMatch({
                    kchsi_id: match.kchsi_id,
                    market_id: match.market_id,
                    similarity_score: match.similarity_score,
                    price_difference_eur: match.price_difference_eur,
                    price_difference_pct: match.price_difference_pct
                });
            }
            
            totalMatches += matches.length;
            
            // Check for significant deals
            const bestMatch = matches[0];
            if (bestMatch.price_difference_pct >= CONFIG.MIN_DISCOUNT_PCT) {
                dealsFound++;
                topDeals.push({
                    auction: auction,
                    match: bestMatch
                });
                
                console.log(`✓ ${auction.bcpea_id}: ${bestMatch.price_difference_pct}% below market!`);
                console.log(`  Auction: ${formatEur(auction.price_eur)} | Market: ${formatEur(bestMatch.market_listing.price_eur)}`);
                console.log(`  ${auction.city}, ${auction.sqm}m², ${auction.rooms || '?'} rooms`);
            }
        }
        
        // Summary
        console.log('\n=== Analysis Summary ===');
        console.log(`Total matches found: ${totalMatches}`);
        console.log(`Properties >${CONFIG.MIN_DISCOUNT_PCT}% below market: ${dealsFound}`);
        
        // Top deals
        if (topDeals.length > 0) {
            console.log('\n=== TOP DEALS ===\n');
            
            topDeals.sort((a, b) => b.match.price_difference_pct - a.match.price_difference_pct);
            
            for (const deal of topDeals.slice(0, 10)) {
                const a = deal.auction;
                const m = deal.match;
                
                console.log(`🔥 ${m.price_difference_pct}% DISCOUNT`);
                console.log(`   Auction Price: ${formatEur(a.price_eur)}`);
                console.log(`   Market Price:  ${formatEur(m.market_listing.price_eur)}`);
                console.log(`   Savings:       ${formatEur(m.price_difference_eur)}`);
                console.log(`   Location:      ${a.city} - ${a.address || 'N/A'}`);
                console.log(`   Details:       ${a.sqm}m², ${a.rooms || '?'} rooms, floor ${a.floor || '?'}`);
                console.log(`   Auction ends:  ${a.auction_end}`);
                console.log(`   BCPEA ID:      ${a.bcpea_id}`);
                console.log(`   Link:          https://sales.bcpea.org/properties/${a.bcpea_id}`);
                console.log('');
            }
        }
        
        // Save report
        const report = {
            timestamp: new Date().toISOString(),
            stats: stats,
            config: CONFIG,
            totalMatches: totalMatches,
            dealsFound: dealsFound,
            topDeals: topDeals.map(d => ({
                bcpea_id: d.auction.bcpea_id,
                city: d.auction.city,
                address: d.auction.address,
                sqm: d.auction.sqm,
                rooms: d.auction.rooms,
                auction_price: d.auction.price_eur,
                market_price: d.match.market_listing.price_eur,
                discount_pct: d.match.price_difference_pct,
                savings_eur: d.match.price_difference_eur,
                auction_end: d.auction.auction_end,
                url: `https://sales.bcpea.org/properties/${d.auction.bcpea_id}`
            }))
        };
        
        const fs = require('fs');
        const path = require('path');
        const reportPath = path.join(__dirname, '../../data/latest-analysis.json');
        fs.writeFileSync(reportPath, JSON.stringify(report, null, 2));
        console.log(`Report saved to: ${reportPath}`);
        
    } catch (err) {
        console.error('Analysis error:', err);
    } finally {
        db.close();
    }
}

if (require.main === module) {
    analyze().catch(console.error);
}

module.exports = { analyze, calculateSimilarity, findMatches };
