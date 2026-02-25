/**
 * КЧСИ Deal Finder
 * Combines КЧСИ auction data with market prices to find deals
 */

const { findComparables, calculateDealScore } = require('./market-scraper');

// Try to load browser scraper, fall back to simple scraper
let scrapeMarketData;
try {
  const browserScraper = require('./browser-scraper');
  scrapeMarketData = browserScraper.scrapeMarketData;
} catch (e) {
  console.log('Note: Puppeteer not available, using simple scraper');
  const simpleScraper = require('./market-scraper');
  scrapeMarketData = async (opts) => simpleScraper.scrapeHomesBg(opts.city, 'apartamenti', 3);
}

// ============================================
// КЧСИ LISTING ENHANCER
// ============================================

/**
 * Extract additional details from КЧСИ listing description
 */
function parseKcsiDescription(text) {
  const result = {
    property_type: null,
    rooms: null,
    size_sqm: null,
    floor: null,
    construction: null,
    neighborhood: null,
  };
  
  if (!text) return result;
  
  const lowerText = text.toLowerCase();
  
  // Property type from description
  if (lowerText.includes('апартамент') || lowerText.includes('жилище')) {
    result.property_type = 'apartment';
  } else if (lowerText.includes('къща') || lowerText.includes('вила')) {
    result.property_type = 'house';
  } else if (lowerText.includes('парцел') || lowerText.includes('земя') || lowerText.includes('упи')) {
    result.property_type = 'land';
  } else if (lowerText.includes('гараж') || lowerText.includes('паркомясто')) {
    result.property_type = 'parking';
  } else if (lowerText.includes('магазин') || lowerText.includes('офис')) {
    result.property_type = 'commercial';
  }
  
  // Room count
  const roomPatterns = [
    { pattern: /едностаен|1[\s-]?стаен|гарсониер/i, rooms: 1 },
    { pattern: /двустаен|2[\s-]?стаен/i, rooms: 2 },
    { pattern: /тристаен|3[\s-]?стаен/i, rooms: 3 },
    { pattern: /четиристаен|4[\s-]?стаен/i, rooms: 4 },
    { pattern: /многостаен|5[\s-]?стаен/i, rooms: 5 },
  ];
  
  for (const { pattern, rooms } of roomPatterns) {
    if (pattern.test(text)) {
      result.rooms = rooms;
      result.property_type = 'apartment';
      break;
    }
  }
  
  // Size in sqm
  const sizeMatch = text.match(/(\d+(?:[.,]\d+)?)\s*(?:кв\.?\s*м|m2|м2|sqm)/i);
  if (sizeMatch) {
    result.size_sqm = parseFloat(sizeMatch[1].replace(',', '.'));
  }
  
  // Floor
  const floorMatch = text.match(/(\d+)[\s-]?(?:ти|ри|ви)?\s*етаж/i) ||
                     text.match(/етаж[\s:]*(\d+)/i);
  if (floorMatch) {
    result.floor = parseInt(floorMatch[1]);
  }
  
  // Construction type
  if (lowerText.includes('панел')) {
    result.construction = 'панел';
  } else if (lowerText.includes('тухла')) {
    result.construction = 'тухла';
  } else if (lowerText.includes('епк') || lowerText.includes('е.п.к')) {
    result.construction = 'ЕПК';
  }
  
  // Try to extract neighborhood from Sofia
  const sofiaNeighborhoods = [
    'младост', 'люлин', 'дружба', 'надежда', 'красно село', 'лозенец',
    'изток', 'гео милев', 'редута', 'подуяне', 'хаджи димитър', 'център',
    'витоша', 'бояна', 'симеоново', 'драгалевци', 'банкя', 'овча купел',
    'студентски', 'манастирски', 'борово', 'хладилника', 'иван вазов',
    'стрелбище', 'белите брези', 'гоце делчев', 'бъкстон', 'банишора',
    'слатина', 'полигона', 'горубляне', 'малинова долина', 'павлово',
    'кръстова вада', 'мусагеница', 'дианабад', 'яворов', 'докторски паметник'
  ];
  
  for (const hood of sofiaNeighborhoods) {
    if (lowerText.includes(hood)) {
      result.neighborhood = hood;
      break;
    }
  }
  
  return result;
}

/**
 * Map КЧСИ rooms to property type
 */
function roomsToPropertyType(rooms) {
  if (!rooms) return null;
  if (rooms === 1) return '1-стаен';
  if (rooms === 2) return '2-стаен';
  if (rooms === 3) return '3-стаен';
  if (rooms >= 4) return '4+-стаен';
  return null;
}

/**
 * Normalize city name for comparison
 */
function normalizeCity(cityStr) {
  if (!cityStr) return null;
  
  const lower = cityStr.toLowerCase()
    .replace(/^(гр\.|с\.|село|град)\s*/i, '')
    .trim();
  
  // Map variations to standard names
  const cityMap = {
    'софия': 'София',
    'sofiya': 'София',
    'пловдив': 'Пловдив',
    'варна': 'Варна',
    'бургас': 'Бургас',
    'русе': 'Русе',
    'стара загора': 'Стара Загора',
  };
  
  return cityMap[lower] || cityStr;
}

// ============================================
// DEAL FINDER
// ============================================

/**
 * Analyze a batch of КЧСИ listings against market data
 */
async function analyzeDeals(kcsiListings, options = {}) {
  const {
    minPrice = 5000,       // Ignore very cheap listings (likely land/parking)
    maxPrice = 500000,     // Ignore extremely expensive (commercial)
    targetCities = ['София', 'Пловдив', 'Варна', 'Бургас'],
  } = options;
  
  console.log(`\nAnalyzing ${kcsiListings.length} КЧСИ listings...\n`);
  
  // Filter relevant listings
  const relevantListings = kcsiListings.filter(l => {
    if (!l.price_eur || l.price_eur < minPrice || l.price_eur > maxPrice) return false;
    const city = normalizeCity(l.city);
    if (!targetCities.includes(city)) return false;
    return true;
  });
  
  console.log(`${relevantListings.length} listings in target cities with valid prices\n`);
  
  // Scrape market data for each relevant city
  const marketData = {};
  const citiesToScrape = [...new Set(relevantListings.map(l => normalizeCity(l.city)))];
  
  for (const city of citiesToScrape) {
    const citySlug = getCitySlug(city);
    if (!citySlug) continue;
    
    console.log(`Scraping market data for ${city}...`);
    try {
      marketData[city] = await scrapeHomesBg(citySlug, 'apartamenti', 5);
      console.log(`  Found ${marketData[city].length} market listings\n`);
    } catch (err) {
      console.error(`  Error scraping ${city}:`, err.message);
      marketData[city] = [];
    }
  }
  
  // Analyze each КЧСИ listing
  const results = [];
  
  for (const kcsi of relevantListings) {
    const city = normalizeCity(kcsi.city);
    const market = marketData[city] || [];
    
    if (market.length === 0) {
      results.push({
        kcsi,
        analysis: { score: null, reason: 'No market data for city' }
      });
      continue;
    }
    
    // Enhance КЧСИ listing with parsed details
    const details = parseKcsiDescription(kcsi.description || kcsi.address || '');
    const enhanced = {
      ...kcsi,
      city,
      neighborhood: details.neighborhood || kcsi.neighborhood,
      property_type: roomsToPropertyType(details.rooms) || details.property_type,
      size_sqm: details.size_sqm || kcsi.size_sqm,
      rooms: details.rooms,
      construction: details.construction,
    };
    
    // Find comparables
    const comparables = findComparables(enhanced, market);
    
    // Calculate deal score
    const analysis = calculateDealScore(enhanced, comparables);
    
    results.push({
      kcsi: enhanced,
      analysis,
    });
  }
  
  return results;
}

function getCitySlug(city) {
  const slugs = {
    'София': 'grad-sofiya',
    'Пловдив': 'grad-plovdiv',
    'Варна': 'grad-varna',
    'Бургас': 'grad-burgas',
  };
  return slugs[city];
}

/**
 * Get top deals from analysis results
 */
function getTopDeals(results, minScore = 3, limit = 20) {
  return results
    .filter(r => r.analysis.score >= minScore)
    .sort((a, b) => {
      // Sort by score descending, then by discount
      if (b.analysis.score !== a.analysis.score) {
        return b.analysis.score - a.analysis.score;
      }
      return (b.analysis.discount_pct || 0) - (a.analysis.discount_pct || 0);
    })
    .slice(0, limit);
}

/**
 * Format deal for display
 */
function formatDeal(result) {
  const { kcsi, analysis } = result;
  
  let output = `
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
${analysis.verdict || 'UNKNOWN'} | Score: ${analysis.score || '?'}/5 | Confidence: ${analysis.confidence || 'low'}
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

📍 Location: ${kcsi.city}${kcsi.neighborhood ? `, ${kcsi.neighborhood}` : ''}
🏠 Type: ${kcsi.property_type || 'Unknown'}${kcsi.size_sqm ? ` | ${kcsi.size_sqm} m²` : ''}
💰 КЧСИ Price: €${kcsi.price_eur?.toLocaleString()}

📊 Market Comparison:
   Median: €${analysis.market_median?.toLocaleString() || '?'}
   Low:    €${analysis.market_low?.toLocaleString() || '?'}
   High:   €${analysis.market_high?.toLocaleString() || '?'}
   
💎 Discount: ${analysis.discount_pct?.toFixed(1) || '?'}% below median
   vs. Low:  ${analysis.discount_vs_low_pct?.toFixed(1) || '?'}% below 25th percentile

📅 Bidding ends: ${kcsi.bid_end || 'Unknown'}
🔗 ${kcsi.url || 'No URL'}

Comparables: ${analysis.comparables_count || 0} found (${analysis.neighborhood_matches || 0} in same area)
`;

  if (analysis.comparables?.length > 0) {
    output += `\nSample comparables:\n`;
    for (const comp of analysis.comparables.slice(0, 3)) {
      output += `  • €${comp.price?.toLocaleString()} | ${comp.size || '?'}m² | ${comp.neighborhood || 'Unknown'}\n`;
    }
  }
  
  return output;
}

// ============================================
// EXPORTS
// ============================================

module.exports = {
  parseKcsiDescription,
  roomsToPropertyType,
  normalizeCity,
  analyzeDeals,
  getTopDeals,
  formatDeal,
};

// ============================================
// CLI TEST
// ============================================

if (require.main === module) {
  async function test() {
    console.log('=== КЧСИ Deal Finder Test ===\n');
    
    // Sample КЧСИ listings (simulated)
    const sampleKcsiListings = [
      {
        id: '85750',
        price_eur: 45000,
        city: 'гр. София',
        address: 'жк. Дружба 2, бл. 215',
        description: 'Двустаен апартамент, 65 кв.м., 4-ти етаж, панел',
        bid_end: '2026-03-09',
        url: 'https://sales.bcpea.org/properties/85750',
      },
      {
        id: '85748',
        price_eur: 120000,
        city: 'гр. София',
        address: 'кв. Лозенец, ул. Криволак 15',
        description: 'Тристаен апартамент, 85 кв.м., тухла, 2-ри етаж',
        bid_end: '2026-03-16',
        url: 'https://sales.bcpea.org/properties/85748',
      },
      {
        id: '85745',
        price_eur: 78000,
        city: 'гр. София',
        address: 'жк. Младост 1',
        description: 'Двустаен апартамент, 58 кв.м., панел, 8-ми етаж',
        bid_end: '2026-03-12',
        url: 'https://sales.bcpea.org/properties/85745',
      },
    ];
    
    // Run analysis
    const results = await analyzeDeals(sampleKcsiListings);
    
    // Show results
    console.log('\n\n========== DEAL ANALYSIS RESULTS ==========\n');
    
    const topDeals = getTopDeals(results, 0);  // Show all for testing
    
    if (topDeals.length === 0) {
      console.log('No deals found meeting criteria.');
    } else {
      for (const deal of topDeals) {
        console.log(formatDeal(deal));
      }
    }
    
    console.log('\n========== SUMMARY ==========');
    console.log(`Total analyzed: ${results.length}`);
    console.log(`5-star deals: ${results.filter(r => r.analysis.score === 5).length}`);
    console.log(`4-star deals: ${results.filter(r => r.analysis.score === 4).length}`);
    console.log(`3-star deals: ${results.filter(r => r.analysis.score === 3).length}`);
  }
  
  test().catch(console.error);
}
