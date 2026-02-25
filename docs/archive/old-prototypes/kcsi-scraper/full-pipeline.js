#!/usr/bin/env node
/**
 * Full Deal Finding Pipeline
 * 
 * 1. Scrapes КЧСИ auction listings
 * 2. Scrapes market data from homes.bg/imot.bg using Puppeteer
 * 3. Compares and scores deals
 * 4. Outputs top opportunities
 * 
 * Usage: node full-pipeline.js [--city=sofia] [--skip-kcsi] [--skip-market]
 */

const fs = require('fs');
const path = require('path');
const { scrape: scrapeKcsi, initDb } = require('./scraper');
const { scrapeMarketData, closeBrowser } = require('./browser-scraper');
const { findComparables, calculateDealScore, normalizePropertyType } = require('./market-scraper');
const { parseKcsiDescription, formatDeal, normalizeCity } = require('./deal-finder');

// ============================================
// CONFIGURATION
// ============================================

const CONFIG = {
  // Target cities for analysis
  targetCities: ['София', 'Пловдив', 'Варна', 'Бургас'],
  
  // Price range for residential properties (EUR)
  minPrice: 15000,
  maxPrice: 300000,
  
  // Minimum deal score to report
  minScoreToReport: 3,
  
  // Output directory
  outputDir: './reports',
};

// ============================================
// MAIN PIPELINE
// ============================================

async function runPipeline(options = {}) {
  const {
    city = 'sofia',
    skipKcsi = false,
    skipMarket = false,
  } = options;
  
  console.log('╔════════════════════════════════════════════════════════════╗');
  console.log('║          КЧСИ DEAL FINDER - Full Pipeline                  ║');
  console.log('╚════════════════════════════════════════════════════════════╝\n');
  
  const startTime = Date.now();
  const report = {
    generated_at: new Date().toISOString(),
    city,
    kcsi_listings: 0,
    market_listings: 0,
    deals_found: 0,
    top_deals: [],
    all_scores: [],
  };
  
  // Ensure output directory exists
  if (!fs.existsSync(CONFIG.outputDir)) {
    fs.mkdirSync(CONFIG.outputDir, { recursive: true });
  }
  
  try {
    // =========================================
    // STEP 1: Get КЧСИ Listings
    // =========================================
    
    console.log('━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━');
    console.log('STEP 1: КЧСИ Auction Data');
    console.log('━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n');
    
    if (!skipKcsi) {
      console.log('📥 Scraping fresh КЧСИ data...');
      await scrapeKcsi();
    } else {
      console.log('⏭️  Skipping КЧСИ scrape (using cached data)');
    }
    
    // Load from database
    const db = initDb();
    const cityPattern = city.toLowerCase() === 'all' ? '%' : `%${normalizeCity(city) || city}%`;
    
    let kcsiListings = db.prepare(`
      SELECT * FROM listings 
      WHERE price_eur > ? 
        AND price_eur < ?
        AND city LIKE ?
    `).all(CONFIG.minPrice, CONFIG.maxPrice, cityPattern);
    
    console.log(`\n📊 Found ${kcsiListings.length} КЧСИ listings in price range €${CONFIG.minPrice}-€${CONFIG.maxPrice}\n`);
    report.kcsi_listings = kcsiListings.length;
    
    if (kcsiListings.length === 0) {
      console.log('⚠️  No КЧСИ listings found. Run without --skip-kcsi to fetch data.\n');
      db.close();
      return report;
    }
    
    // Enhance КЧСИ listings with parsed details
    kcsiListings = kcsiListings.map(l => {
      const details = parseKcsiDescription(l.description || l.address || '');
      return {
        ...l,
        city: normalizeCity(l.city) || l.city,
        neighborhood: details.neighborhood || l.neighborhood,
        property_type: details.rooms ? 
          normalizePropertyType(`${details.rooms}-стаен`) : 
          details.property_type,
        size_sqm: details.size_sqm || l.size_sqm,
        rooms: details.rooms,
        construction: details.construction,
      };
    });
    
    // Filter to residential only (apartments, not land/garage/commercial)
    const residentialKcsi = kcsiListings.filter(l => {
      const type = (l.property_type || '').toLowerCase();
      // Include if it looks like an apartment
      if (type.includes('стаен') || type.includes('apartment') || l.rooms) {
        return true;
      }
      // Exclude if clearly not residential
      if (type.includes('land') || type.includes('парцел') || 
          type.includes('гараж') || type.includes('garage') ||
          type.includes('офис') || type.includes('магазин')) {
        return false;
      }
      // Include unknown for now (might be apartments)
      return true;
    });
    
    console.log(`   ${residentialKcsi.length} appear to be residential properties\n`);
    
    // =========================================
    // STEP 2: Get Market Data
    // =========================================
    
    console.log('━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━');
    console.log('STEP 2: Market Data (Puppeteer)');
    console.log('━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n');
    
    let marketListings = [];
    
    if (!skipMarket) {
      marketListings = await scrapeMarketData({
        city: city.toLowerCase(),
        sources: ['homes.bg'],  // Start with homes.bg, add imot.bg if needed
        maxPagesPerSource: 5,
      });
      
      // Cache market data
      const cacheFile = path.join(CONFIG.outputDir, `market-cache-${city.toLowerCase()}.json`);
      fs.writeFileSync(cacheFile, JSON.stringify(marketListings, null, 2));
      console.log(`💾 Cached ${marketListings.length} market listings\n`);
    } else {
      // Try to load from cache
      const cacheFile = path.join(CONFIG.outputDir, `market-cache-${city.toLowerCase()}.json`);
      if (fs.existsSync(cacheFile)) {
        marketListings = JSON.parse(fs.readFileSync(cacheFile, 'utf-8'));
        console.log(`📂 Loaded ${marketListings.length} market listings from cache\n`);
      } else {
        console.log('⚠️  No cached market data. Run without --skip-market to fetch.\n');
      }
    }
    
    report.market_listings = marketListings.length;
    
    if (marketListings.length === 0) {
      console.log('⚠️  No market data available. Cannot calculate deal scores.\n');
      db.close();
      return report;
    }
    
    // =========================================
    // STEP 3: Compare and Score
    // =========================================
    
    console.log('━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━');
    console.log('STEP 3: Deal Analysis');
    console.log('━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n');
    
    console.log('🔍 Comparing КЧСИ listings against market...\n');
    
    const results = [];
    
    for (const kcsi of residentialKcsi) {
      // Find comparable market listings
      const comparables = findComparables(kcsi, marketListings, {
        sizeTolerancePct: 25,
        maxResults: 15,
      });
      
      // Calculate deal score
      const analysis = calculateDealScore(kcsi, comparables);
      
      results.push({
        kcsi,
        analysis,
      });
    }
    
    // Sort by score
    results.sort((a, b) => {
      if ((b.analysis.score || 0) !== (a.analysis.score || 0)) {
        return (b.analysis.score || 0) - (a.analysis.score || 0);
      }
      return (b.analysis.discount_pct || 0) - (a.analysis.discount_pct || 0);
    });
    
    // Store all scores for report
    report.all_scores = results.map(r => ({
      id: r.kcsi.id,
      city: r.kcsi.city,
      price: r.kcsi.price_eur,
      score: r.analysis.score,
      discount: r.analysis.discount_pct,
      comparables: r.analysis.comparables_count,
    }));
    
    // Filter to reportable deals
    const topDeals = results.filter(r => 
      r.analysis.score >= CONFIG.minScoreToReport
    );
    
    report.deals_found = topDeals.length;
    report.top_deals = topDeals.slice(0, 20).map(d => ({
      ...d.kcsi,
      analysis: d.analysis,
    }));
    
    // =========================================
    // STEP 4: Output Results
    // =========================================
    
    console.log('━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━');
    console.log('RESULTS');
    console.log('━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n');
    
    if (topDeals.length === 0) {
      console.log('😕 No significant deals found (score >= 3)\n');
      console.log('This could mean:');
      console.log('  • КЧСИ prices are at or above market');
      console.log('  • Not enough comparable listings for matching');
      console.log('  • Property types don\'t match well\n');
      
      // Show best available
      const bestAvailable = results.slice(0, 5);
      if (bestAvailable.length > 0) {
        console.log('Best available (any score):\n');
        for (const deal of bestAvailable) {
          console.log(formatDeal(deal));
        }
      }
    } else {
      console.log(`🎯 Found ${topDeals.length} potential deals:\n`);
      
      for (const deal of topDeals.slice(0, 10)) {
        console.log(formatDeal(deal));
      }
    }
    
    // Score distribution
    console.log('\n━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━');
    console.log('SUMMARY');
    console.log('━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n');
    
    const scoreDistribution = {
      5: results.filter(r => r.analysis.score === 5).length,
      4: results.filter(r => r.analysis.score === 4).length,
      3: results.filter(r => r.analysis.score === 3).length,
      2: results.filter(r => r.analysis.score === 2).length,
      1: results.filter(r => r.analysis.score === 1).length,
      0: results.filter(r => r.analysis.score === 0).length,
      null: results.filter(r => r.analysis.score === null).length,
    };
    
    console.log('Score Distribution:');
    console.log(`  🔥 5-star (>35% discount):  ${scoreDistribution[5]}`);
    console.log(`  ⭐ 4-star (25-35%):         ${scoreDistribution[4]}`);
    console.log(`  👍 3-star (15-25%):         ${scoreDistribution[3]}`);
    console.log(`  📊 2-star (5-15%):          ${scoreDistribution[2]}`);
    console.log(`  ⚖️  1-star (market price):   ${scoreDistribution[1]}`);
    console.log(`  ❌ 0-star (above market):   ${scoreDistribution[0]}`);
    console.log(`  ❓ Unscored:                ${scoreDistribution[null]}`);
    
    const elapsed = ((Date.now() - startTime) / 1000).toFixed(1);
    console.log(`\n⏱️  Pipeline completed in ${elapsed}s`);
    
    // Save report
    const reportFile = path.join(
      CONFIG.outputDir, 
      `deal-report-${city.toLowerCase()}-${new Date().toISOString().split('T')[0]}.json`
    );
    fs.writeFileSync(reportFile, JSON.stringify(report, null, 2));
    console.log(`💾 Report saved: ${reportFile}\n`);
    
    db.close();
    return report;
    
  } catch (err) {
    console.error('\n❌ Pipeline error:', err);
    throw err;
  } finally {
    await closeBrowser();
  }
}

// ============================================
// CLI
// ============================================

if (require.main === module) {
  const args = process.argv.slice(2);
  
  const cityArg = args.find(a => a.startsWith('--city='));
  const city = cityArg ? cityArg.split('=')[1] : 'sofia';
  
  const options = {
    city,
    skipKcsi: args.includes('--skip-kcsi'),
    skipMarket: args.includes('--skip-market'),
  };
  
  runPipeline(options)
    .then(() => process.exit(0))
    .catch(() => process.exit(1));
}

module.exports = { runPipeline };
