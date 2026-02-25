/**
 * Browser-based Market Scraper
 * Uses Puppeteer to scrape JS-rendered property sites
 */

const puppeteer = require('puppeteer');

const CONFIG = {
  headless: true,
  timeout: 30000,
  delayBetweenPages: 2000,
  userAgent: 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
};

// ============================================
// BROWSER MANAGEMENT
// ============================================

let browser = null;

async function getBrowser() {
  if (!browser) {
    browser = await puppeteer.launch({
      headless: CONFIG.headless ? 'new' : false,
      args: [
        '--no-sandbox',
        '--disable-setuid-sandbox',
        '--disable-dev-shm-usage',
        '--disable-accelerated-2d-canvas',
        '--disable-gpu',
        '--window-size=1920,1080',
      ],
    });
  }
  return browser;
}

async function closeBrowser() {
  if (browser) {
    await browser.close();
    browser = null;
  }
}

async function newPage() {
  const b = await getBrowser();
  const page = await b.newPage();
  await page.setUserAgent(CONFIG.userAgent);
  await page.setViewport({ width: 1920, height: 1080 });
  return page;
}

function sleep(ms) {
  return new Promise(resolve => setTimeout(resolve, ms));
}

// ============================================
// IMOT.BG SCRAPER
// ============================================

/**
 * Scrape apartments for sale from imot.bg
 * @param {object} filters - Search filters
 * @param {number} maxPages - Maximum pages to scrape
 */
async function scrapeImotBg(filters = {}, maxPages = 5) {
  const {
    city = 'sofia',
    propertyType = 'apartments', // apartments, houses, studios
    priceMin = null,
    priceMax = null,
    rooms = null, // 1, 2, 3, 4+
  } = filters;

  console.log(`\n📊 Scraping imot.bg: ${city} ${propertyType}`);
  
  const listings = [];
  const page = await newPage();
  
  try {
    // Build search URL
    // imot.bg URL format: /pcgi/imot.cgi?act=3&session_id=&f1=1&f2=1&f3=1&f4=София
    // Or use the friendly URLs: /obiavi/prodazhbi/sofia/
    const baseUrl = 'https://www.imot.bg';
    let searchUrl = `${baseUrl}/obiavi/prodazhbi/`;
    
    // Map city names to URL slugs
    const citySlugs = {
      'sofia': 'sofia',
      'plovdiv': 'plovdiv',
      'varna': 'varna',
      'burgas': 'burgas',
    };
    
    const citySlug = citySlugs[city.toLowerCase()] || city.toLowerCase();
    searchUrl += `${citySlug}/`;
    
    // Navigate to search page
    console.log(`   Loading: ${searchUrl}`);
    await page.goto(searchUrl, { waitUntil: 'networkidle2', timeout: CONFIG.timeout });
    
    // Wait for listings to load
    await page.waitForSelector('.adPrice, .price, [class*="price"]', { timeout: 10000 }).catch(() => {});
    await sleep(1000);
    
    // Scrape pages
    for (let pageNum = 1; pageNum <= maxPages; pageNum++) {
      console.log(`   Page ${pageNum}...`);
      
      // Extract listings from current page
      const pageListings = await page.evaluate(() => {
        const results = [];
        
        // Try multiple selector strategies
        const adContainers = document.querySelectorAll(
          '.adItem, .ad, [class*="offer"], [class*="listing"], table.tablereset tr'
        );
        
        // Also try parsing from the page structure
        const priceElements = document.querySelectorAll('[class*="price"], .cena');
        const locationElements = document.querySelectorAll('[class*="location"], .loca');
        
        // Parse tabular format (common on imot.bg)
        const tables = document.querySelectorAll('table');
        tables.forEach(table => {
          const rows = table.querySelectorAll('tr');
          rows.forEach(row => {
            const text = row.innerText;
            
            // Look for price pattern
            const priceMatch = text.match(/([\d\s]+)\s*(EUR|лв|BGN)/i);
            if (!priceMatch) return;
            
            // Look for area pattern
            const areaMatch = text.match(/(\d+)\s*(?:кв\.?м|m2)/i);
            
            // Look for room pattern  
            const roomMatch = text.match(/(едностаен|двустаен|тристаен|четиристаен|\d-стаен)/i);
            
            // Look for neighborhood
            const neighborhoodPatterns = [
              /(?:кв\.|жк\.|ж\.к\.)\s*([А-Яа-я\s\d]+?)(?:,|\s+-)/i,
              /София,\s*([А-Яа-я\s\d]+?)(?:,|$)/i,
            ];
            let neighborhood = null;
            for (const pattern of neighborhoodPatterns) {
              const match = text.match(pattern);
              if (match) {
                neighborhood = match[1].trim();
                break;
              }
            }
            
            // Get link if available
            const link = row.querySelector('a[href*="obiavi"]');
            const href = link ? link.href : null;
            const id = href ? href.match(/(\d+)/) : null;
            
            if (priceMatch) {
              results.push({
                id: id ? id[1] : Math.random().toString(36).substr(2, 9),
                price_raw: priceMatch[0],
                price_value: parseFloat(priceMatch[1].replace(/\s/g, '')),
                price_currency: priceMatch[2].toUpperCase() === 'EUR' ? 'EUR' : 'BGN',
                area_sqm: areaMatch ? parseInt(areaMatch[1]) : null,
                rooms: roomMatch ? roomMatch[1] : null,
                neighborhood: neighborhood,
                url: href,
                raw_text: text.substring(0, 500),
              });
            }
          });
        });
        
        // Deduplicate by URL or text
        const seen = new Set();
        return results.filter(r => {
          const key = r.url || r.raw_text.substring(0, 100);
          if (seen.has(key)) return false;
          seen.add(key);
          return true;
        });
      });
      
      console.log(`   Found ${pageListings.length} listings on page ${pageNum}`);
      listings.push(...pageListings);
      
      // Try to go to next page
      if (pageNum < maxPages) {
        const nextButton = await page.$('a[class*="next"], a:has-text("следваща"), .paging a:last-child');
        if (nextButton) {
          await nextButton.click();
          await page.waitForNavigation({ waitUntil: 'networkidle2', timeout: CONFIG.timeout }).catch(() => {});
          await sleep(CONFIG.delayBetweenPages);
        } else {
          console.log('   No more pages');
          break;
        }
      }
    }
    
  } catch (err) {
    console.error(`   Error scraping imot.bg: ${err.message}`);
  } finally {
    await page.close();
  }
  
  // Normalize prices to EUR
  const normalized = listings.map(l => ({
    ...l,
    price_eur: l.price_currency === 'EUR' ? l.price_value : Math.round(l.price_value / 1.95583),
    source: 'imot.bg',
    scraped_at: new Date().toISOString(),
  }));
  
  console.log(`   Total: ${normalized.length} listings scraped\n`);
  return normalized;
}

// ============================================
// HOMES.BG SCRAPER
// ============================================

async function scrapeHomesBg(filters = {}, maxPages = 5) {
  const {
    city = 'grad-sofiya',
    propertyType = 'apartamenti',
  } = filters;

  console.log(`\n📊 Scraping homes.bg: ${city} ${propertyType}`);
  
  const listings = [];
  const page = await newPage();
  
  try {
    const baseUrl = 'https://www.homes.bg';
    const searchUrl = `${baseUrl}/prodazhbi/${propertyType}/${city}/`;
    
    console.log(`   Loading: ${searchUrl}`);
    await page.goto(searchUrl, { waitUntil: 'networkidle2', timeout: CONFIG.timeout });
    await sleep(2000);
    
    for (let pageNum = 1; pageNum <= maxPages; pageNum++) {
      console.log(`   Page ${pageNum}...`);
      
      // Extract listings
      const pageListings = await page.evaluate(() => {
        const results = [];
        
        // homes.bg uses cards with specific structure
        const cards = document.querySelectorAll('a[href*="/offer/"]');
        
        cards.forEach(card => {
          const text = card.innerText || '';
          const href = card.href;
          
          // Skip non-listing links
          if (!href.includes('apartament-za-prodazhba') && !href.includes('kashta-za-prodazhba')) {
            return;
          }
          
          // Extract ID from URL: /offer/..../as1234567
          const idMatch = href.match(/\/as(\d+)$/);
          
          // Extract price: "160,000 EUR"
          const priceMatch = text.match(/([\d,]+)\s*EUR/);
          
          // Extract type and size: "Двустаен, 70m²"
          const typeMatch = text.match(/(Едностаен|Двустаен|Тристаен|Четиристаен|Мезонет|Гарсониера)[,\s]*(\d+)m²/i);
          
          // Extract neighborhood: "кв. Малинова Долина, София" or "жк. Дружба 2, София"
          const neighborhoodMatch = text.match(/(?:кв\.|жк\.)\s*([^,]+),\s*([А-Яа-я]+)/i);
          
          // Extract price per sqm
          const pricePerSqmMatch = text.match(/([\d,]+)EUR\/m²/);
          
          // Extract construction type
          const constructionMatch = text.match(/(Тухла|ЕПК|Панел)/i);
          
          if (priceMatch && idMatch) {
            results.push({
              id: idMatch[1],
              url: href,
              price_eur: parseFloat(priceMatch[1].replace(/,/g, '')),
              property_type: typeMatch ? typeMatch[1].toLowerCase() : null,
              size_sqm: typeMatch ? parseInt(typeMatch[2]) : null,
              neighborhood: neighborhoodMatch ? neighborhoodMatch[1].trim() : null,
              city: neighborhoodMatch ? neighborhoodMatch[2] : 'София',
              construction: constructionMatch ? constructionMatch[1] : null,
              price_per_sqm: pricePerSqmMatch ? parseFloat(pricePerSqmMatch[1].replace(/,/g, '')) : null,
            });
          }
        });
        
        return results;
      });
      
      console.log(`   Found ${pageListings.length} listings on page ${pageNum}`);
      listings.push(...pageListings);
      
      // Pagination - homes.bg uses infinite scroll or button
      if (pageNum < maxPages) {
        // Try to scroll down to load more
        await page.evaluate(() => window.scrollTo(0, document.body.scrollHeight));
        await sleep(2000);
        
        // Or try pagination link
        const nextExists = await page.$('a[class*="next"], button[class*="load-more"]');
        if (nextExists) {
          await nextExists.click();
          await sleep(CONFIG.delayBetweenPages);
        } else {
          // Check if new content loaded via scroll
          const newCount = await page.evaluate(() => 
            document.querySelectorAll('a[href*="/offer/"]').length
          );
          if (newCount <= listings.length) {
            console.log('   No more content');
            break;
          }
        }
      }
    }
    
  } catch (err) {
    console.error(`   Error scraping homes.bg: ${err.message}`);
  } finally {
    await page.close();
  }
  
  // Add metadata
  const normalized = listings.map(l => ({
    ...l,
    source: 'homes.bg',
    scraped_at: new Date().toISOString(),
  }));
  
  // Deduplicate
  const seen = new Set();
  const unique = normalized.filter(l => {
    if (seen.has(l.id)) return false;
    seen.add(l.id);
    return true;
  });
  
  console.log(`   Total unique: ${unique.length} listings\n`);
  return unique;
}

// ============================================
// COMBINED SCRAPER
// ============================================

/**
 * Scrape market data from multiple sources
 */
async function scrapeMarketData(options = {}) {
  const {
    city = 'sofia',
    sources = ['homes.bg', 'imot.bg'],
    maxPagesPerSource = 5,
  } = options;
  
  console.log('═══════════════════════════════════════════');
  console.log('       MARKET DATA SCRAPER (Puppeteer)     ');
  console.log('═══════════════════════════════════════════\n');
  
  const allListings = [];
  
  try {
    // Map city to source-specific slugs
    const cityMappings = {
      'sofia': { homes: 'grad-sofiya', imot: 'sofia' },
      'plovdiv': { homes: 'grad-plovdiv', imot: 'plovdiv' },
      'varna': { homes: 'grad-varna', imot: 'varna' },
      'burgas': { homes: 'grad-burgas', imot: 'burgas' },
    };
    
    const cityMap = cityMappings[city.toLowerCase()] || { homes: city, imot: city };
    
    for (const source of sources) {
      if (source === 'homes.bg') {
        const homesBgListings = await scrapeHomesBg(
          { city: cityMap.homes },
          maxPagesPerSource
        );
        allListings.push(...homesBgListings);
      }
      
      if (source === 'imot.bg') {
        const imotBgListings = await scrapeImotBg(
          { city: cityMap.imot },
          maxPagesPerSource
        );
        allListings.push(...imotBgListings);
      }
      
      await sleep(2000); // Delay between sources
    }
    
  } finally {
    await closeBrowser();
  }
  
  console.log(`\n✅ Total market listings: ${allListings.length}`);
  return allListings;
}

// ============================================
// EXPORTS
// ============================================

module.exports = {
  scrapeImotBg,
  scrapeHomesBg,
  scrapeMarketData,
  closeBrowser,
};

// ============================================
// CLI
// ============================================

if (require.main === module) {
  async function main() {
    try {
      const listings = await scrapeMarketData({
        city: 'sofia',
        sources: ['homes.bg'],
        maxPagesPerSource: 2,
      });
      
      console.log('\nSample listings:');
      listings.slice(0, 5).forEach(l => {
        console.log(`  €${l.price_eur} | ${l.property_type || '?'} | ${l.size_sqm || '?'}m² | ${l.neighborhood || 'Unknown'}`);
      });
      
      // Save to file
      const fs = require('fs');
      fs.writeFileSync(
        './market-data.json',
        JSON.stringify(listings, null, 2)
      );
      console.log('\nSaved to market-data.json');
      
    } catch (err) {
      console.error('Fatal error:', err);
    }
  }
  
  main();
}
