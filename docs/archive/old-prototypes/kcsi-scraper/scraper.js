/**
 * КЧСИ Public Auction Scraper
 * Scrapes property listings from sales.bcpea.org
 */

const axios = require('axios');
const cheerio = require('cheerio');
const Database = require('better-sqlite3');
const path = require('path');

// Configuration
const CONFIG = {
  baseUrl: 'https://sales.bcpea.org',
  listingsPath: '/properties',
  itemsPerPage: 12,
  delayMs: 2000,  // Be respectful
  userAgent: 'Mozilla/5.0 (compatible; ImotWatch/1.0; +https://imotwatch.bg)',
  maxPages: 100,  // Safety limit
};

// Initialize database
function initDb() {
  const dbPath = path.join(__dirname, 'kcsi.db');
  const db = new Database(dbPath);
  
  db.exec(`
    CREATE TABLE IF NOT EXISTS listings (
      id TEXT PRIMARY KEY,
      price_eur REAL,
      city TEXT,
      address TEXT,
      court TEXT,
      executor TEXT,
      bid_start TEXT,
      bid_end TEXT,
      announce_date TEXT,
      url TEXT,
      first_seen TEXT,
      last_seen TEXT,
      notified INTEGER DEFAULT 0
    );
    
    CREATE TABLE IF NOT EXISTS scrape_log (
      id INTEGER PRIMARY KEY AUTOINCREMENT,
      started_at TEXT,
      finished_at TEXT,
      pages_scraped INTEGER,
      listings_found INTEGER,
      new_listings INTEGER,
      errors TEXT
    );
    
    CREATE INDEX IF NOT EXISTS idx_city ON listings(city);
    CREATE INDEX IF NOT EXISTS idx_price ON listings(price_eur);
    CREATE INDEX IF NOT EXISTS idx_bid_end ON listings(bid_end);
  `);
  
  return db;
}

// Fetch a single page
async function fetchPage(pageNum) {
  const url = `${CONFIG.baseUrl}${CONFIG.listingsPath}?page=${pageNum}`;
  
  try {
    const response = await axios.get(url, {
      headers: {
        'User-Agent': CONFIG.userAgent,
        'Accept': 'text/html,application/xhtml+xml',
        'Accept-Language': 'bg,en;q=0.9',
      },
      timeout: 30000,
    });
    return response.data;
  } catch (error) {
    console.error(`Error fetching page ${pageNum}:`, error.message);
    throw error;
  }
}

// Parse price from text (handles EUR format)
function parsePrice(text) {
  if (!text) return null;
  // Remove spaces and extract number
  const cleaned = text.replace(/\s/g, '').replace(',', '.');
  const match = cleaned.match(/([\d.]+)/);
  if (match) {
    return parseFloat(match[1]);
  }
  return null;
}

// Parse date from Bulgarian format
function parseDate(text) {
  if (!text) return null;
  // Expected format: "09.02.2026" or "10.03.2026 09:00"
  const match = text.match(/(\d{2})\.(\d{2})\.(\d{4})(?:\s+(\d{2}):(\d{2}))?/);
  if (match) {
    const [_, day, month, year, hour, minute] = match;
    if (hour && minute) {
      return `${year}-${month}-${day}T${hour}:${minute}:00`;
    }
    return `${year}-${month}-${day}`;
  }
  return text; // Return original if can't parse
}

// Parse listings from HTML
function parseListings(html) {
  const $ = cheerio.load(html);
  const listings = [];
  
  // Each listing card - adjust selector based on actual structure
  // Based on the data we've seen, listings appear in a card/grid format
  $('[class*="card"], [class*="listing"], [class*="property"], .property-item, article').each((i, el) => {
    try {
      const $el = $(el);
      const text = $el.text();
      
      // Skip if doesn't look like a property listing
      if (!text.includes('EUR') && !text.includes('СРОК')) return;
      
      // Extract ID from link
      const link = $el.find('a[href*="/properties/"]').attr('href') || 
                   $el.find('a').filter((i, a) => $(a).attr('href')?.includes('/properties/')).attr('href');
      if (!link) return;
      
      const idMatch = link.match(/\/properties\/(\d+)/);
      if (!idMatch) return;
      
      const id = idMatch[1];
      
      // Extract data points
      const priceMatch = text.match(/([\d\s,.]+)\s*EUR/i);
      const cityMatch = text.match(/НАСЕЛЕНО МЯСТО[:\s]*([^\n]+)/i) ||
                       text.match(/(?:гр\.|с\.)\s*([^\n,]+)/i);
      const addressMatch = text.match(/Адрес[:\s]*([^\n]+)/i);
      const courtMatch = text.match(/ОКРЪЖЕН СЪД[:\s]*([^\n]+)/i);
      const executorMatch = text.match(/ЧАСТЕН СЪДЕБЕН ИЗПЪЛНИТЕЛ[:\s]*([^\n]+)/i);
      const bidPeriodMatch = text.match(/СРОК[:\s]*от\s*(\d{2}\.\d{2}\.\d{4})\s*до\s*(\d{2}\.\d{2}\.\d{4})/i);
      const announceMatch = text.match(/ОБЯВЯВАНЕ НА[:\s]*(\d{2}\.\d{2}\.\d{4}\s*\d{2}:\d{2})/i);
      
      listings.push({
        id,
        price_eur: priceMatch ? parsePrice(priceMatch[1]) : null,
        city: cityMatch ? cityMatch[1].trim() : null,
        address: addressMatch ? addressMatch[1].trim() : null,
        court: courtMatch ? courtMatch[1].trim() : null,
        executor: executorMatch ? executorMatch[1].trim() : null,
        bid_start: bidPeriodMatch ? parseDate(bidPeriodMatch[1]) : null,
        bid_end: bidPeriodMatch ? parseDate(bidPeriodMatch[2]) : null,
        announce_date: announceMatch ? parseDate(announceMatch[1]) : null,
        url: `${CONFIG.baseUrl}/properties/${id}`,
      });
    } catch (e) {
      console.error('Error parsing listing:', e.message);
    }
  });
  
  return listings;
}

// Alternative parser using text blocks (more resilient)
function parseListingsFromText(html) {
  const $ = cheerio.load(html);
  const listings = [];
  const bodyText = $('body').text();
  
  // Split by property IDs
  const propertyBlocks = bodyText.split(/\/properties\/(\d+)/);
  
  for (let i = 1; i < propertyBlocks.length; i += 2) {
    const id = propertyBlocks[i];
    const textBlock = propertyBlocks[i + 1] || '';
    const prevBlock = propertyBlocks[i - 1] || '';
    const combinedText = prevBlock.slice(-500) + textBlock.slice(0, 500);
    
    // Extract price - look for EUR pattern before the ID
    const priceMatch = prevBlock.match(/([\d\s,.]+)\s*EUR\s*$/i) ||
                      combinedText.match(/([\d\s,.]+)\s*EUR/i);
    
    // Extract other fields from surrounding text
    const cityMatch = combinedText.match(/(?:гр\.|с\.)\s*([А-Яа-я\s]+?)(?:\n|,|ОКРЪЖЕН)/i);
    const courtMatch = combinedText.match(/ОКРЪЖЕН СЪД[:\s]*([А-Яа-я\s]+?)(?:\n|ЧАСТЕН)/i);
    const bidMatch = combinedText.match(/от\s*(\d{2}\.\d{2}\.\d{4})\s*до\s*(\d{2}\.\d{2}\.\d{4})/);
    const announceMatch = combinedText.match(/ОБЯВЯВАНЕ НА[:\s]*(\d{2}\.\d{2}\.\d{4}\s*\d{2}:\d{2})/i);
    
    if (id) {
      listings.push({
        id,
        price_eur: priceMatch ? parsePrice(priceMatch[1]) : null,
        city: cityMatch ? cityMatch[1].trim() : null,
        address: null,
        court: courtMatch ? courtMatch[1].trim() : null,
        executor: null,
        bid_start: bidMatch ? parseDate(bidMatch[1]) : null,
        bid_end: bidMatch ? parseDate(bidMatch[2]) : null,
        announce_date: announceMatch ? parseDate(announceMatch[1]) : null,
        url: `${CONFIG.baseUrl}/properties/${id}`,
      });
    }
  }
  
  return listings;
}

// Check if there's a next page
function hasNextPage(html, currentPage) {
  const $ = cheerio.load(html);
  // Look for pagination links or "next" button
  const hasNext = $('a[href*="page=' + (currentPage + 1) + '"]').length > 0 ||
                 $('[class*="next"]').length > 0 ||
                 $('a:contains("»")').length > 0;
  return hasNext;
}

// Sleep helper
function sleep(ms) {
  return new Promise(resolve => setTimeout(resolve, ms));
}

// Main scraping function
async function scrape() {
  console.log('Starting КЧСИ scraper...');
  const startTime = new Date().toISOString();
  const db = initDb();
  
  const stmt = db.prepare(`
    INSERT OR REPLACE INTO listings 
    (id, price_eur, city, address, court, executor, bid_start, bid_end, announce_date, url, first_seen, last_seen)
    VALUES 
    (@id, @price_eur, @city, @address, @court, @executor, @bid_start, @bid_end, @announce_date, @url,
     COALESCE((SELECT first_seen FROM listings WHERE id = @id), @now),
     @now)
  `);
  
  let page = 1;
  let totalListings = 0;
  let newListings = 0;
  const errors = [];
  const now = new Date().toISOString();
  
  // Get existing IDs to track new ones
  const existingIds = new Set(
    db.prepare('SELECT id FROM listings').all().map(r => r.id)
  );
  
  try {
    while (page <= CONFIG.maxPages) {
      console.log(`Fetching page ${page}...`);
      
      const html = await fetchPage(page);
      
      // Try both parsing methods
      let listings = parseListings(html);
      if (listings.length === 0) {
        listings = parseListingsFromText(html);
      }
      
      console.log(`  Found ${listings.length} listings on page ${page}`);
      
      if (listings.length === 0) {
        console.log('  No more listings found, stopping.');
        break;
      }
      
      // Save to database
      for (const listing of listings) {
        try {
          stmt.run({ ...listing, now });
          totalListings++;
          
          if (!existingIds.has(listing.id)) {
            newListings++;
            console.log(`  NEW: ${listing.city || 'Unknown'} - ${listing.price_eur || '?'} EUR`);
          }
        } catch (e) {
          errors.push(`Listing ${listing.id}: ${e.message}`);
        }
      }
      
      // Check for more pages
      if (!hasNextPage(html, page) || listings.length < CONFIG.itemsPerPage) {
        console.log('  Last page reached.');
        break;
      }
      
      page++;
      await sleep(CONFIG.delayMs);
    }
  } catch (error) {
    errors.push(`Scraping error: ${error.message}`);
    console.error('Scraping failed:', error.message);
  }
  
  // Log the scrape
  const finishTime = new Date().toISOString();
  db.prepare(`
    INSERT INTO scrape_log (started_at, finished_at, pages_scraped, listings_found, new_listings, errors)
    VALUES (?, ?, ?, ?, ?, ?)
  `).run(startTime, finishTime, page, totalListings, newListings, errors.join('; '));
  
  console.log('\n--- Scrape Complete ---');
  console.log(`Pages scraped: ${page}`);
  console.log(`Total listings: ${totalListings}`);
  console.log(`New listings: ${newListings}`);
  if (errors.length > 0) {
    console.log(`Errors: ${errors.length}`);
  }
  
  db.close();
  
  return { pages: page, total: totalListings, new: newListings, errors };
}

// Query helpers for testing
function getStats(db) {
  return {
    total: db.prepare('SELECT COUNT(*) as count FROM listings').get().count,
    byCourt: db.prepare('SELECT court, COUNT(*) as count FROM listings GROUP BY court ORDER BY count DESC').all(),
    priceRange: db.prepare('SELECT MIN(price_eur) as min, MAX(price_eur) as max, AVG(price_eur) as avg FROM listings WHERE price_eur > 0').get(),
  };
}

function findDeals(db, maxPrice = 50000) {
  return db.prepare(`
    SELECT * FROM listings 
    WHERE price_eur > 0 AND price_eur <= ? 
    ORDER BY price_eur ASC 
    LIMIT 20
  `).all(maxPrice);
}

// Export for use as module
module.exports = { scrape, initDb, getStats, findDeals };

// Run if called directly
if (require.main === module) {
  scrape().then(result => {
    console.log('\nResult:', result);
  }).catch(err => {
    console.error('Fatal error:', err);
    process.exit(1);
  });
}
