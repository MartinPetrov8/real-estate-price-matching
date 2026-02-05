/**
 * Real Estate Price Matching - Main Entry Point
 * 
 * Scrapes КЧСИ auctions and compares to market prices
 */

const { main: scrapeKchsi } = require('./scrapers/kchsi');
const { main: scrapeImot } = require('./scrapers/imot-bg');
const { analyze } = require('./matching/analyzer');
const PropertyDatabase = require('./db/database');

async function runFull() {
    console.log('=================================');
    console.log('Real Estate Price Matching');
    console.log('=================================\n');
    
    console.log('Step 1: Scraping КЧСИ auctions...\n');
    await scrapeKchsi();
    
    console.log('\nStep 2: Scraping market listings...\n');
    await scrapeImot();
    
    console.log('\nStep 3: Analyzing matches...\n');
    await analyze();
    
    console.log('\n=================================');
    console.log('Complete!');
    console.log('=================================');
}

async function showStats() {
    const db = new PropertyDatabase();
    const stats = db.getStats();
    
    console.log('Database Statistics:');
    console.log(`  КЧСИ properties: ${stats.kchsi_count}`);
    console.log(`  Active auctions: ${stats.active_auctions}`);
    console.log(`  Market listings: ${stats.market_count}`);
    console.log(`  Matches found:   ${stats.match_count}`);
    
    if (stats.match_count > 0) {
        console.log('\nTop Deals:');
        const deals = db.getBestDeals(5);
        for (const deal of deals) {
            console.log(`  ${deal.price_difference_pct}% off: ${deal.city} ${deal.sqm}m² - €${deal.price_eur} (market: €${deal.market_price})`);
        }
    }
    
    db.close();
}

// CLI handling
const args = process.argv.slice(2);
const command = args[0] || 'help';

switch (command) {
    case 'full':
        runFull().catch(console.error);
        break;
    case 'stats':
        showStats().catch(console.error);
        break;
    case 'kchsi':
        scrapeKchsi().catch(console.error);
        break;
    case 'market':
        scrapeImot().catch(console.error);
        break;
    case 'analyze':
        analyze().catch(console.error);
        break;
    case 'help':
    default:
        console.log('Real Estate Price Matching');
        console.log('');
        console.log('Commands:');
        console.log('  node src/index.js full     - Run complete pipeline');
        console.log('  node src/index.js kchsi    - Scrape КЧСИ auctions');
        console.log('  node src/index.js market   - Scrape market listings');
        console.log('  node src/index.js analyze  - Run matching analysis');
        console.log('  node src/index.js stats    - Show database stats');
        console.log('');
}
