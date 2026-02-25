#!/usr/bin/env node
/**
 * КЧСИ Deal Analysis Runner
 * Main entry point that orchestrates the full analysis pipeline
 * 
 * Usage: node run-analysis.js [--scrape] [--city=София]
 */

const { scrape, initDb } = require('./scraper');
const { analyzeDeals, getTopDeals, formatDeal } = require('./deal-finder');

async function main() {
  const args = process.argv.slice(2);
  const shouldScrape = args.includes('--scrape');
  const cityArg = args.find(a => a.startsWith('--city='));
  const targetCity = cityArg ? cityArg.split('=')[1] : null;
  
  console.log('╔════════════════════════════════════════════════════════════╗');
  console.log('║           КЧСИ DEAL FINDER - Price Intelligence            ║');
  console.log('╚════════════════════════════════════════════════════════════╝\n');
  
  // Step 1: Get КЧСИ listings
  let kcsiListings;
  
  if (shouldScrape) {
    console.log('📥 Scraping fresh КЧСИ data...\n');
    await scrape();
  }
  
  // Load from database
  console.log('📂 Loading КЧСИ listings from database...');
  const db = initDb();
  
  let query = 'SELECT * FROM listings WHERE price_eur > 0';
  const params = [];
  
  if (targetCity) {
    query += ' AND city LIKE ?';
    params.push(`%${targetCity}%`);
  }
  
  kcsiListings = db.prepare(query).all(...params);
  console.log(`   Found ${kcsiListings.length} listings\n`);
  
  if (kcsiListings.length === 0) {
    console.log('⚠️  No КЧСИ listings in database.');
    console.log('   Run with --scrape flag to fetch data first.\n');
    db.close();
    return;
  }
  
  // Step 2: Analyze against market data
  console.log('📊 Analyzing against market prices...\n');
  console.log('   (This will scrape homes.bg for comparison data)\n');
  
  const results = await analyzeDeals(kcsiListings, {
    minPrice: 10000,
    maxPrice: 400000,
    targetCities: targetCity ? [targetCity] : ['София', 'Пловдив', 'Варна', 'Бургас'],
  });
  
  // Step 3: Display results
  console.log('\n');
  console.log('╔════════════════════════════════════════════════════════════╗');
  console.log('║                    TOP DEALS FOUND                         ║');
  console.log('╚════════════════════════════════════════════════════════════╝\n');
  
  const topDeals = getTopDeals(results, 3);  // Score >= 3
  
  if (topDeals.length === 0) {
    console.log('😕 No significant deals found (score >= 3)');
    console.log('   This could mean:');
    console.log('   - КЧСИ prices are at market rate');
    console.log('   - Not enough comparable listings found');
    console.log('   - Property types don\'t match well\n');
    
    // Show best available anyway
    const bestAvailable = getTopDeals(results, 0).slice(0, 5);
    if (bestAvailable.length > 0) {
      console.log('📋 Best available (any score):\n');
      for (const deal of bestAvailable) {
        console.log(formatDeal(deal));
      }
    }
  } else {
    console.log(`🎯 Found ${topDeals.length} potential deals:\n`);
    
    for (const deal of topDeals) {
      console.log(formatDeal(deal));
    }
  }
  
  // Summary statistics
  console.log('\n╔════════════════════════════════════════════════════════════╗');
  console.log('║                      SUMMARY                               ║');
  console.log('╚════════════════════════════════════════════════════════════╝\n');
  
  const scoreDistribution = {
    5: results.filter(r => r.analysis.score === 5).length,
    4: results.filter(r => r.analysis.score === 4).length,
    3: results.filter(r => r.analysis.score === 3).length,
    2: results.filter(r => r.analysis.score === 2).length,
    1: results.filter(r => r.analysis.score === 1).length,
    0: results.filter(r => r.analysis.score === 0).length,
    null: results.filter(r => r.analysis.score === null).length,
  };
  
  console.log(`📈 Score Distribution:`);
  console.log(`   🔥 5-star (>35% discount): ${scoreDistribution[5]}`);
  console.log(`   ⭐ 4-star (25-35% discount): ${scoreDistribution[4]}`);
  console.log(`   👍 3-star (15-25% discount): ${scoreDistribution[3]}`);
  console.log(`   📊 2-star (5-15% discount): ${scoreDistribution[2]}`);
  console.log(`   ⚖️  1-star (market price): ${scoreDistribution[1]}`);
  console.log(`   ❌ 0-star (above market): ${scoreDistribution[0]}`);
  console.log(`   ❓ Unscored (insufficient data): ${scoreDistribution[null]}`);
  
  console.log(`\n📊 Total Analyzed: ${results.length}`);
  console.log(`✅ Actionable Deals (score >= 3): ${topDeals.length}`);
  
  // Save results to JSON
  const outputPath = `./deal-report-${new Date().toISOString().split('T')[0]}.json`;
  const fs = require('fs');
  fs.writeFileSync(outputPath, JSON.stringify({
    generated_at: new Date().toISOString(),
    summary: {
      total_analyzed: results.length,
      score_distribution: scoreDistribution,
    },
    top_deals: topDeals.map(d => ({
      kcsi_id: d.kcsi.id,
      city: d.kcsi.city,
      price_eur: d.kcsi.price_eur,
      score: d.analysis.score,
      discount_pct: d.analysis.discount_pct,
      market_median: d.analysis.market_median,
      url: d.kcsi.url,
      bid_end: d.kcsi.bid_end,
    })),
    all_results: results.map(r => ({
      kcsi_id: r.kcsi.id,
      city: r.kcsi.city,
      price: r.kcsi.price_eur,
      score: r.analysis.score,
      discount: r.analysis.discount_pct,
    })),
  }, null, 2));
  
  console.log(`\n💾 Full report saved to: ${outputPath}`);
  
  db.close();
}

main().catch(err => {
  console.error('Fatal error:', err);
  process.exit(1);
});
