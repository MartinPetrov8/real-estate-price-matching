/**
 * Market Price Scraper
 * Scrapes comparable listings from Bulgarian real estate portals
 * for price comparison against КЧСИ auctions
 */

const axios = require('axios');
const cheerio = require('cheerio');

const CONFIG = {
  delayMs: 1500,
  userAgent: 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
  sources: {
    homes: {
      name: 'homes.bg',
      baseUrl: 'https://www.homes.bg',
      searchUrl: (city, type, page) => 
        `https://www.homes.bg/prodazhbi/${type}/${city}/?page=${page}`,
    },
    imoti: {
      name: 'imoti.net',
      baseUrl: 'https://www.imoti.net',
      searchUrl: (city, type, page) =>
        `https://www.imoti.net/bg/obiavi/prodazhba/${city}/${type}/?page=${page}`,
    }
  },
  // Map Bulgarian cities to URL slugs
  cities: {
    'софия': 'grad-sofiya',
    'пловдив': 'grad-plovdiv',
    'варна': 'grad-varna',
    'бургас': 'grad-burgas',
  },
  // Map property types
  propertyTypes: {
    'apartment': 'apartamenti',
    'house': 'kashti',
    'studio': 'garsonieri',
  }
};

// ============================================
// HOMES.BG SCRAPER
// ============================================

async function scrapeHomesBg(city = 'grad-sofiya', propertyType = 'apartamenti', maxPages = 3) {
  const listings = [];
  
  for (let page = 1; page <= maxPages; page++) {
    try {
      const url = `https://www.homes.bg/prodazhbi/${propertyType}/${city}/?page=${page}`;
      console.log(`Fetching: ${url}`);
      
      const response = await axios.get(url, {
        headers: { 'User-Agent': CONFIG.userAgent },
        timeout: 15000,
      });
      
      const pageListings = parseHomesBgPage(response.data);
      listings.push(...pageListings);
      
      console.log(`  Page ${page}: Found ${pageListings.length} listings`);
      
      if (pageListings.length === 0) break;
      
      await sleep(CONFIG.delayMs);
    } catch (err) {
      console.error(`Error on page ${page}:`, err.message);
      break;
    }
  }
  
  return listings;
}

function parseHomesBgPage(html) {
  const $ = cheerio.load(html);
  const listings = [];
  
  // Parse listing links - format: /offer/apartament-za-prodazhba/dvustaen-70m2-sofiya-kv.-malinova-dolina/as1664694
  $('a[href*="/offer/"]').each((i, el) => {
    const $el = $(el);
    const href = $el.attr('href');
    const text = $el.text();
    
    // Skip if not a listing link
    if (!href || !href.includes('apartament-za-prodazhba') && !href.includes('kashta-za-prodazhba')) {
      return;
    }
    
    try {
      // Parse from text: "днескв. Малинова Долина, Софияstar_outlineДвустаен, 70m²Тухла, Необзаведен, Локално отопление160,000 EUR 2,285EUR/m²"
      const listing = parseHomesBgListing(text, href);
      if (listing && listing.price_eur > 0) {
        listings.push(listing);
      }
    } catch (e) {
      // Skip unparseable
    }
  });
  
  return listings;
}

function parseHomesBgListing(text, href) {
  // Extract neighborhood: "кв. Малинова Долина" or "жк. Дружба 2"
  const neighborhoodMatch = text.match(/(?:кв\.|жк\.)\s*([^,]+),\s*([А-Яа-я]+)/);
  
  // Extract property type and size: "Двустаен, 70m²"
  const typeMatch = text.match(/(Едностаен|Двустаен|Тристаен|Четиристаен|Мезонет|Гарсониера),?\s*(\d+)m²/i);
  
  // Extract construction: "Тухла" or "ЕПК" or "Панел"
  const constructionMatch = text.match(/(Тухла|ЕПК|Панел)/i);
  
  // Extract price: "160,000 EUR"
  const priceMatch = text.match(/([\d,]+)\s*EUR/);
  
  // Extract price per sqm: "2,285EUR/m²"
  const pricePerSqmMatch = text.match(/([\d,]+)EUR\/m²/);
  
  // Extract ID from URL
  const idMatch = href.match(/\/as(\d+)$/);
  
  if (!priceMatch) return null;
  
  return {
    id: idMatch ? idMatch[1] : null,
    source: 'homes.bg',
    url: `https://www.homes.bg${href}`,
    city: neighborhoodMatch ? neighborhoodMatch[2] : 'София',
    neighborhood: neighborhoodMatch ? neighborhoodMatch[1].trim() : null,
    property_type: typeMatch ? normalizePropertyType(typeMatch[1]) : null,
    size_sqm: typeMatch ? parseInt(typeMatch[2]) : null,
    construction: constructionMatch ? constructionMatch[1] : null,
    price_eur: parsePrice(priceMatch[1]),
    price_per_sqm: pricePerSqmMatch ? parsePrice(pricePerSqmMatch[1]) : null,
    scraped_at: new Date().toISOString(),
  };
}

// ============================================
// DATA NORMALIZATION
// ============================================

function normalizePropertyType(type) {
  const map = {
    'едностаен': '1-стаен',
    'гарсониера': '1-стаен',
    'двустаен': '2-стаен',
    'тристаен': '3-стаен',
    'четиристаен': '4+-стаен',
    'многостаен': '4+-стаен',
    'мезонет': 'мезонет',
  };
  return map[type.toLowerCase()] || type.toLowerCase();
}

function normalizeNeighborhood(name) {
  if (!name) return null;
  // Remove common prefixes and normalize
  return name
    .replace(/^(кв\.|жк\.|ж\.к\.|квартал|жилищен комплекс)\s*/i, '')
    .trim()
    .toLowerCase();
}

function parsePrice(str) {
  if (!str) return null;
  return parseFloat(str.replace(/,/g, ''));
}

// ============================================
// COMPARISON ENGINE
// ============================================

/**
 * Find comparable listings for a КЧСИ property
 */
function findComparables(kcsiListing, marketListings, options = {}) {
  const {
    sizeTolerancePct = 20,  // ±20% size
    maxResults = 10,
  } = options;
  
  const comparables = marketListings.filter(market => {
    // Must be same city
    if (market.city?.toLowerCase() !== kcsiListing.city?.toLowerCase()) {
      return false;
    }
    
    // Same property type if available
    if (kcsiListing.property_type && market.property_type) {
      if (market.property_type !== kcsiListing.property_type) {
        return false;
      }
    }
    
    // Size within tolerance if available
    if (kcsiListing.size_sqm && market.size_sqm) {
      const sizeDiff = Math.abs(market.size_sqm - kcsiListing.size_sqm) / kcsiListing.size_sqm;
      if (sizeDiff > sizeTolerancePct / 100) {
        return false;
      }
    }
    
    // Same neighborhood bonus (not required)
    // Will be used for scoring
    
    return true;
  });
  
  // Sort by relevance (same neighborhood first, then by size similarity)
  comparables.sort((a, b) => {
    const aNeighborhoodMatch = normalizeNeighborhood(a.neighborhood) === normalizeNeighborhood(kcsiListing.neighborhood);
    const bNeighborhoodMatch = normalizeNeighborhood(b.neighborhood) === normalizeNeighborhood(kcsiListing.neighborhood);
    
    if (aNeighborhoodMatch && !bNeighborhoodMatch) return -1;
    if (!aNeighborhoodMatch && bNeighborhoodMatch) return 1;
    
    // Then by size similarity
    if (kcsiListing.size_sqm && a.size_sqm && b.size_sqm) {
      const aDiff = Math.abs(a.size_sqm - kcsiListing.size_sqm);
      const bDiff = Math.abs(b.size_sqm - kcsiListing.size_sqm);
      return aDiff - bDiff;
    }
    
    return 0;
  });
  
  return comparables.slice(0, maxResults);
}

/**
 * Calculate deal score for a КЧСИ listing
 */
function calculateDealScore(kcsiListing, comparables) {
  if (comparables.length < 3) {
    return {
      score: null,
      confidence: 'low',
      reason: `Only ${comparables.length} comparable(s) found`,
      comparables_count: comparables.length,
    };
  }
  
  const prices = comparables.map(c => c.price_eur).sort((a, b) => a - b);
  
  const median = getMedian(prices);
  const percentile25 = getPercentile(prices, 25);
  const percentile75 = getPercentile(prices, 75);
  const mean = prices.reduce((a, b) => a + b, 0) / prices.length;
  
  const discount = ((median - kcsiListing.price_eur) / median) * 100;
  const discountVsLow = ((percentile25 - kcsiListing.price_eur) / percentile25) * 100;
  
  // Calculate score (1-5 stars)
  let score, verdict;
  if (discount > 35) {
    score = 5;
    verdict = '🔥 EXCEPTIONAL DEAL';
  } else if (discount > 25) {
    score = 4;
    verdict = '⭐ STRONG BUY';
  } else if (discount > 15) {
    score = 3;
    verdict = '👍 GOOD DEAL';
  } else if (discount > 5) {
    score = 2;
    verdict = '📊 SLIGHT DISCOUNT';
  } else if (discount > -5) {
    score = 1;
    verdict = '⚖️ MARKET PRICE';
  } else {
    score = 0;
    verdict = '❌ ABOVE MARKET';
  }
  
  // Confidence based on sample size and neighborhood matches
  const neighborhoodMatches = comparables.filter(c => 
    normalizeNeighborhood(c.neighborhood) === normalizeNeighborhood(kcsiListing.neighborhood)
  ).length;
  
  let confidence;
  if (comparables.length >= 10 && neighborhoodMatches >= 3) {
    confidence = 'high';
  } else if (comparables.length >= 5) {
    confidence = 'medium';
  } else {
    confidence = 'low';
  }
  
  return {
    score,
    verdict,
    confidence,
    kcsi_price: kcsiListing.price_eur,
    market_median: Math.round(median),
    market_low: Math.round(percentile25),
    market_high: Math.round(percentile75),
    market_mean: Math.round(mean),
    discount_pct: Math.round(discount * 10) / 10,
    discount_vs_low_pct: Math.round(discountVsLow * 10) / 10,
    comparables_count: comparables.length,
    neighborhood_matches: neighborhoodMatches,
    comparables: comparables.slice(0, 5).map(c => ({
      price: c.price_eur,
      size: c.size_sqm,
      neighborhood: c.neighborhood,
      url: c.url,
    })),
  };
}

function getMedian(arr) {
  const mid = Math.floor(arr.length / 2);
  return arr.length % 2 !== 0 ? arr[mid] : (arr[mid - 1] + arr[mid]) / 2;
}

function getPercentile(arr, p) {
  const index = Math.ceil((p / 100) * arr.length) - 1;
  return arr[Math.max(0, index)];
}

function sleep(ms) {
  return new Promise(resolve => setTimeout(resolve, ms));
}

// ============================================
// MAIN EXPORTS
// ============================================

module.exports = {
  scrapeHomesBg,
  findComparables,
  calculateDealScore,
  normalizePropertyType,
  normalizeNeighborhood,
};

// ============================================
// CLI TEST
// ============================================

if (require.main === module) {
  async function test() {
    console.log('=== Market Scraper Test ===\n');
    
    // Scrape some market data
    console.log('Scraping homes.bg Sofia apartments...');
    const marketListings = await scrapeHomesBg('grad-sofiya', 'apartamenti', 2);
    console.log(`\nTotal market listings: ${marketListings.length}\n`);
    
    // Sample КЧСИ listing for comparison
    const sampleKcsi = {
      id: 'TEST001',
      city: 'София',
      neighborhood: 'Дружба 2',
      property_type: '2-стаен',
      size_sqm: 70,
      price_eur: 120000,
    };
    
    console.log('Sample КЧСИ listing:', sampleKcsi);
    console.log('\nFinding comparables...');
    
    const comparables = findComparables(sampleKcsi, marketListings);
    console.log(`Found ${comparables.length} comparable listings\n`);
    
    const dealScore = calculateDealScore(sampleKcsi, comparables);
    console.log('Deal Score Analysis:');
    console.log(JSON.stringify(dealScore, null, 2));
  }
  
  test().catch(console.error);
}
