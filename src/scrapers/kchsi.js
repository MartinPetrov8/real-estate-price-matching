/**
 * КЧСИ Scraper - Scrapes forced auction properties from sales.bcpea.org
 * Target cities: Sofia, Plovdiv, Varna, Burgas
 */

const puppeteer = require('puppeteer');
const PropertyDatabase = require('../db/database');

const BASE_URL = 'https://sales.bcpea.org';
const TARGET_CITIES = ['София', 'Пловдив', 'Варна', 'Бургас'];

// City name normalization
const CITY_MAP = {
    'гр. София': 'София',
    'гр. Пловдив': 'Пловдив',
    'гр. Варна': 'Варна',
    'гр. Бургас': 'Бургас',
    'София': 'София',
    'Пловдив': 'Пловдив',
    'Варна': 'Варна',
    'Бургас': 'Бургас'
};

function normalizeCity(cityText) {
    if (!cityText) return null;
    for (const [pattern, normalized] of Object.entries(CITY_MAP)) {
        if (cityText.includes(pattern)) return normalized;
    }
    return null;
}

function extractSqm(description) {
    // Match patterns like "112.15 кв.м." or "112,15 кв.м" or "площ от 112.15"
    const patterns = [
        /(\d+[.,]\d+)\s*кв\.?м/i,
        /площ[^\d]*(\d+[.,]\d+)/i,
        /(\d+)\s*кв\.?м/i
    ];
    
    for (const pattern of patterns) {
        const match = description.match(pattern);
        if (match) {
            return parseFloat(match[1].replace(',', '.'));
        }
    }
    return null;
}

function extractRooms(description) {
    // Match patterns like "четири стаи", "3-стаен", "тристаен"
    const numberWords = {
        'едно': 1, 'една': 1, 'един': 1,
        'две': 2, 'два': 2, 'двустаен': 2,
        'три': 3, 'тристаен': 3,
        'четири': 4, 'четиристаен': 4,
        'пет': 5, 'петстаен': 5,
        'шест': 6, 'многостаен': 6
    };
    
    const descLower = description.toLowerCase();
    
    // Try word patterns first
    for (const [word, num] of Object.entries(numberWords)) {
        if (descLower.includes(word)) return num;
    }
    
    // Try numeric patterns like "3-стаен"
    const numMatch = descLower.match(/(\d+)\s*[-–]?\s*стаен/);
    if (numMatch) return parseInt(numMatch[1]);
    
    // Count "стаи" mentions
    const staiMatch = description.match(/(\d+)\s*стаи/i);
    if (staiMatch) return parseInt(staiMatch[1]);
    
    return null;
}

function extractFloor(description) {
    // Match patterns like "ет.1", "етаж 3", "на 2-ри етаж"
    const patterns = [
        /ет\.?\s*[-–]?\s*(\d+)/i,
        /етаж\s*[-–]?\s*(\d+)/i,
        /на\s*(\d+)[–-]?[ирв]?и?\s*етаж/i
    ];
    
    for (const pattern of patterns) {
        const match = description.match(pattern);
        if (match) {
            return parseInt(match[1]);
        }
    }
    return null;
}

function extractCadastralId(description) {
    // Match cadastral IDs like "68134.1505.2367.8.1"
    const match = description.match(/идентификатор\s*(\d+\.\d+\.\d+\.\d+\.\d+)/i);
    return match ? match[1] : null;
}

/**
 * Detect partial ownership fractions from property description
 * Returns fraction string like "1/6", "1/4", "1/2", "1/3" or null if full ownership
 */
function detectPartialOwnership(description) {
    if (!description) return null;
    
    const descLower = description.toLowerCase();
    
    // Pattern mappings: regex -> fraction
    const patterns = [
        // 1/2 patterns
        { regex: /½|1\s*\/\s*2|една\s+втора|половин\s+идеална\s+част/i, fraction: '1/2' },
        // 1/3 patterns  
        { regex: /1\s*\/\s*3|една\s+трета/i, fraction: '1/3' },
        // 1/4 patterns
        { regex: /¼|1\s*\/\s*4|една\s+четвърт/i, fraction: '1/4' },
        // 1/5 patterns
        { regex: /1\s*\/\s*5|една\s+пета/i, fraction: '1/5' },
        // 1/6 patterns
        { regex: /1\s*\/\s*6|една\s+шеста/i, fraction: '1/6' },
        // 1/8 patterns
        { regex: /1\s*\/\s*8|една\s+осма/i, fraction: '1/8' },
        // 2/3 patterns
        { regex: /2\s*\/\s*3|две\s+трети/i, fraction: '2/3' },
        // 3/4 patterns  
        { regex: /3\s*\/\s*4|три\s+четвърти/i, fraction: '3/4' },
    ];
    
    for (const pattern of patterns) {
        if (pattern.regex.test(descLower)) {
            return pattern.fraction;
        }
    }
    
    // Check for generic "идеална част" without specific fraction - flag as unknown partial
    if (/идеална\s+част/.test(descLower)) {
        return 'unknown';
    }
    
    return null;
}

function extractPropertyType(description) {
    const descLower = description.toLowerCase();
    
    if (descLower.includes('апартамент') || descLower.includes('жилище')) return 'apartment';
    if (descLower.includes('къща')) return 'house';
    if (descLower.includes('вила')) return 'villa';
    if (descLower.includes('офис')) return 'office';
    if (descLower.includes('магазин') || descLower.includes('търговск')) return 'commercial';
    if (descLower.includes('парцел') || descLower.includes('земя') || descLower.includes('нива')) return 'land';
    if (descLower.includes('гараж') || descLower.includes('паркомясто')) return 'garage';
    if (descLower.includes('ателие')) return 'studio';
    if (descLower.includes('склад')) return 'warehouse';
    
    return 'other';
}

function parseDate(dateStr) {
    // Parse dates like "19.02.2026" or "20.03.2026 13:30"
    if (!dateStr) return null;
    
    const match = dateStr.match(/(\d{2})\.(\d{2})\.(\d{4})(?:\s+(\d{2}):(\d{2}))?/);
    if (match) {
        const [, day, month, year, hour, minute] = match;
        if (hour && minute) {
            return `${year}-${month}-${day}T${hour}:${minute}:00`;
        }
        return `${year}-${month}-${day}`;
    }
    return null;
}

function parsePeriod(periodStr) {
    // Parse "от 19.02.2026 до 19.03.2026"
    if (!periodStr) return { start: null, end: null };
    
    const match = periodStr.match(/от\s+(\d{2}\.\d{2}\.\d{4})\s+до\s+(\d{2}\.\d{2}\.\d{4})/);
    if (match) {
        return {
            start: parseDate(match[1]),
            end: parseDate(match[2])
        };
    }
    return { start: null, end: null };
}

async function scrapePropertyList(page, pageNum = 1) {
    const url = `${BASE_URL}/properties?page=${pageNum}`;
    console.log(`Scraping page ${pageNum}: ${url}`);
    
    await page.goto(url, { waitUntil: 'networkidle2', timeout: 30000 });
    
    // Wait for content to load
    await page.waitForSelector('body', { timeout: 10000 });
    
    const properties = await page.evaluate(() => {
        const items = [];
        
        // Find all property cards (adjust selector based on actual HTML)
        const cards = document.querySelectorAll('[class*="property"], [class*="card"], article');
        
        cards.forEach(card => {
            const text = card.innerText;
            
            // Extract property link
            const linkEl = card.querySelector('a[href*="/properties/"]');
            const link = linkEl ? linkEl.getAttribute('href') : null;
            
            // Extract price
            const priceMatch = text.match(/([\d\s,\.]+)\s*EUR/);
            const price = priceMatch ? parseFloat(priceMatch[1].replace(/[\s,]/g, '').replace(',', '.')) : null;
            
            // Extract city
            const cityMatch = text.match(/НАСЕЛЕНО МЯСТО\s*([^\n]+)/);
            const city = cityMatch ? cityMatch[1].trim() : null;
            
            // Extract address
            const addressMatch = text.match(/Адрес\s*([^\n]+)/i);
            const address = addressMatch ? addressMatch[1].trim() : null;
            
            // Extract period
            const periodMatch = text.match(/СРОК\s*от\s+([\d\.]+)\s+до\s+([\d\.]+)/);
            
            // Extract announcement date
            const announceMatch = text.match(/ОБЯВЯВАНЕ НА\s*([\d\.\s:]+)/);
            
            // Extract court and executor
            const courtMatch = text.match(/ОКРЪЖЕН СЪД\s*([^\n]+)/);
            const executorMatch = text.match(/ЧАСТЕН СЪДЕБЕН ИЗПЪЛНИТЕЛ\s*([^\n]+)/);
            
            if (link) {
                items.push({
                    bcpea_id: link.split('/').pop(),
                    url: link,
                    price_eur: price,
                    city: city,
                    address: address,
                    period: periodMatch ? { start: periodMatch[1], end: periodMatch[2] } : null,
                    announcement: announceMatch ? announceMatch[1].trim() : null,
                    court: courtMatch ? courtMatch[1].trim() : null,
                    executor: executorMatch ? executorMatch[1].trim() : null
                });
            }
        });
        
        return items;
    });
    
    return properties;
}

async function scrapePropertyDetail(page, propertyId) {
    const url = `${BASE_URL}/properties/${propertyId}`;
    console.log(`Scraping detail: ${url}`);
    
    try {
        await page.goto(url, { waitUntil: 'networkidle2', timeout: 30000 });
        
        const detail = await page.evaluate(() => {
            const text = document.body.innerText;
            
            // Get full description
            const descMatch = text.match(/ОПИСАНИЕ\s*([\s\S]*?)(?=Адрес|$)/i);
            const description = descMatch ? descMatch[1].trim() : text;
            
            return { description };
        });
        
        return detail;
    } catch (err) {
        console.error(`Error scraping ${propertyId}:`, err.message);
        return null;
    }
}

async function main() {
    console.log('Starting КЧСИ scraper...');
    console.log(`Target cities: ${TARGET_CITIES.join(', ')}`);
    
    const db = new PropertyDatabase();
    
    const browser = await puppeteer.launch({
        headless: 'new',
        args: ['--no-sandbox', '--disable-setuid-sandbox']
    });
    
    const page = await browser.newPage();
    await page.setUserAgent('Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36');
    
    try {
        let allProperties = [];
        let pageNum = 1;
        const maxPages = 50; // Limit for POC
        
        // Scrape listing pages
        while (pageNum <= maxPages) {
            const properties = await scrapePropertyList(page, pageNum);
            
            if (properties.length === 0) break;
            
            // Filter for target cities
            const filtered = properties.filter(p => {
                const normalized = normalizeCity(p.city);
                return normalized && TARGET_CITIES.includes(normalized);
            });
            
            console.log(`Page ${pageNum}: Found ${properties.length} properties, ${filtered.length} in target cities`);
            allProperties = allProperties.concat(filtered);
            
            pageNum++;
            
            // Rate limiting
            await new Promise(r => setTimeout(r, 1000));
        }
        
        console.log(`\nTotal properties to process: ${allProperties.length}`);
        
        // Scrape details and save to database
        for (const prop of allProperties) {
            const detail = await scrapePropertyDetail(page, prop.bcpea_id);
            
            if (!detail) continue;
            
            const description = detail.description || '';
            const period = prop.period ? parsePeriod(`от ${prop.period.start} до ${prop.period.end}`) : { start: null, end: null };
            
            // Detect partial ownership
            const partialOwnership = detectPartialOwnership(description);
            if (partialOwnership) {
                console.log(`⚠️ PARTIAL OWNERSHIP DETECTED: ${prop.bcpea_id} - ${partialOwnership}`);
            }
            
            const property = {
                bcpea_id: prop.bcpea_id,
                price_eur: prop.price_eur,
                city: normalizeCity(prop.city),
                address: prop.address,
                description: description,
                sqm: extractSqm(description),
                rooms: extractRooms(description),
                floor: extractFloor(description),
                property_type: extractPropertyType(description),
                auction_start: period.start,
                auction_end: period.end,
                announcement_date: parseDate(prop.announcement),
                court: prop.court,
                executor: prop.executor,
                cadastral_id: extractCadastralId(description),
                partial_ownership: partialOwnership
            };
            
            try {
                db.upsertKchsiProperty(property);
                const ownershipNote = partialOwnership ? ` [${partialOwnership} ownership]` : '';
                console.log(`✓ Saved: ${prop.bcpea_id} - ${property.city} - ${property.sqm || '?'}m² - €${property.price_eur}${ownershipNote}`);
            } catch (err) {
                console.error(`✗ Error saving ${prop.bcpea_id}:`, err.message);
            }
            
            // Rate limiting
            await new Promise(r => setTimeout(r, 500));
        }
        
        // Print stats
        const stats = db.getStats();
        console.log('\n=== Scraping Complete ===');
        console.log(`КЧСИ properties: ${stats.kchsi_count}`);
        console.log(`Active auctions: ${stats.active_auctions}`);
        
    } catch (err) {
        console.error('Scraper error:', err);
    } finally {
        await browser.close();
        db.close();
    }
}

// Run if called directly
if (require.main === module) {
    main().catch(console.error);
}

module.exports = { main, TARGET_CITIES, detectPartialOwnership };
