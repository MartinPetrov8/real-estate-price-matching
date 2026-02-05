/**
 * Imot.bg Scraper - Scrapes market listings for comparison
 * Target cities: Sofia, Plovdiv, Varna, Burgas
 */

const puppeteer = require('puppeteer');
const PropertyDatabase = require('../db/database');

const BASE_URL = 'https://www.imot.bg';

// City codes for imot.bg
const CITY_CONFIG = {
    'София': { code: 'grad_sofia', name: 'София' },
    'Пловдив': { code: 'grad_plovdiv', name: 'Пловдив' },
    'Варна': { code: 'grad_varna', name: 'Варна' },
    'Бургас': { code: 'grad_burgas', name: 'Бургас' }
};

// BGN to EUR conversion (approximate)
const BGN_TO_EUR = 0.51;

function extractPrice(priceText) {
    if (!priceText) return { eur: null, bgn: null };
    
    const text = priceText.replace(/\s/g, '');
    
    // Try EUR first
    let match = text.match(/([\d,\.]+)\s*EUR/i);
    if (match) {
        const eur = parseFloat(match[1].replace(/,/g, ''));
        return { eur, bgn: Math.round(eur / BGN_TO_EUR) };
    }
    
    // Try BGN/лв
    match = text.match(/([\d,\.]+)\s*(?:BGN|лв)/i);
    if (match) {
        const bgn = parseFloat(match[1].replace(/,/g, ''));
        return { eur: Math.round(bgn * BGN_TO_EUR), bgn };
    }
    
    // Just a number
    match = text.match(/([\d,\.]+)/);
    if (match) {
        const val = parseFloat(match[1].replace(/,/g, ''));
        // Assume BGN if > 500
        if (val > 500) {
            return { eur: Math.round(val * BGN_TO_EUR), bgn: val };
        }
    }
    
    return { eur: null, bgn: null };
}

function extractSqm(text) {
    if (!text) return null;
    
    const patterns = [
        /([\d,\.]+)\s*(?:кв\.?м|m2|m²|sqm)/i,
        /площ[^\d]*([\d,\.]+)/i
    ];
    
    for (const pattern of patterns) {
        const match = text.match(pattern);
        if (match) {
            return parseFloat(match[1].replace(',', '.'));
        }
    }
    return null;
}

function extractRooms(text) {
    if (!text) return null;
    
    const patterns = [
        /(\d+)\s*[-–]?\s*(?:стаен|стаи|стая)/i,
        /(\d+)\s*rooms?/i
    ];
    
    const roomWords = {
        'едностаен': 1, 'гарсониера': 1,
        'двустаен': 2,
        'тристаен': 3,
        'четиристаен': 4,
        'многостаен': 5
    };
    
    const textLower = text.toLowerCase();
    for (const [word, num] of Object.entries(roomWords)) {
        if (textLower.includes(word)) return num;
    }
    
    for (const pattern of patterns) {
        const match = text.match(pattern);
        if (match) return parseInt(match[1]);
    }
    
    return null;
}

function extractFloor(text) {
    if (!text) return { floor: null, totalFloors: null };
    
    // Match "3/5" or "ет. 3 от 5"
    let match = text.match(/(?:ет\.?\s*)?(\d+)\s*[\/от]\s*(\d+)/i);
    if (match) {
        return { floor: parseInt(match[1]), totalFloors: parseInt(match[2]) };
    }
    
    // Just floor number
    match = text.match(/ет\.?\s*(\d+)/i);
    if (match) {
        return { floor: parseInt(match[1]), totalFloors: null };
    }
    
    return { floor: null, totalFloors: null };
}

function extractPropertyType(text) {
    if (!text) return 'other';
    const textLower = text.toLowerCase();
    
    if (textLower.includes('гарсониера')) return 'studio';
    if (textLower.includes('апартамент') || textLower.match(/\d+-?стаен/)) return 'apartment';
    if (textLower.includes('къща')) return 'house';
    if (textLower.includes('вила')) return 'villa';
    if (textLower.includes('офис')) return 'office';
    if (textLower.includes('магазин') || textLower.includes('търговск')) return 'commercial';
    if (textLower.includes('парцел') || textLower.includes('земя')) return 'land';
    if (textLower.includes('гараж') || textLower.includes('паркомясто')) return 'garage';
    if (textLower.includes('ателие')) return 'studio';
    
    return 'apartment'; // Default for imot.bg
}

function extractConstruction(text) {
    if (!text) return null;
    const textLower = text.toLowerCase();
    
    if (textLower.includes('тухла')) return 'brick';
    if (textLower.includes('панел')) return 'panel';
    if (textLower.includes('епк') || textLower.includes('ек')) return 'epk';
    if (textLower.includes('гредоред')) return 'beam';
    
    return null;
}

async function scrapeImotBgSearch(page, city, pageNum = 1) {
    // Build search URL for sale listings in the city
    const cityConfig = CITY_CONFIG[city];
    if (!cityConfig) {
        console.error(`Unknown city: ${city}`);
        return [];
    }
    
    // imot.bg search URL pattern
    const url = `${BASE_URL}/pcgi/imot.cgi?act=3&session_id=&f1=1&f2=1&f3=&f4=&f5=&f6=&cf=0&cf1=${pageNum}`;
    
    console.log(`Scraping ${city} page ${pageNum}`);
    
    try {
        await page.goto(url, { waitUntil: 'networkidle2', timeout: 30000 });
        
        // Wait for listings
        await page.waitForSelector('body', { timeout: 10000 });
        
        const listings = await page.evaluate((cityName) => {
            const items = [];
            
            // Find listing tables/divs
            const listingEls = document.querySelectorAll('table[width="660"], .listingDiv, .adPrice, [class*="listing"]');
            
            listingEls.forEach(el => {
                const text = el.innerText || '';
                const html = el.innerHTML || '';
                
                // Find link to listing
                const linkEl = el.querySelector('a[href*="imot.cgi?act=5"]');
                const link = linkEl ? linkEl.href : null;
                const sourceId = link ? (link.match(/adv=([^&]+)/) || [])[1] : null;
                
                if (!link || !sourceId) return;
                
                // Basic parsing from listing card
                items.push({
                    source: 'imot.bg',
                    source_id: sourceId,
                    url: link,
                    city: cityName,
                    raw_text: text.substring(0, 2000) // Store raw for later parsing
                });
            });
            
            return items;
        }, city);
        
        return listings;
        
    } catch (err) {
        console.error(`Error scraping ${city}:`, err.message);
        return [];
    }
}

async function scrapeListingDetail(page, listing) {
    try {
        await page.goto(listing.url, { waitUntil: 'networkidle2', timeout: 30000 });
        
        const detail = await page.evaluate(() => {
            const text = document.body.innerText || '';
            
            // Extract key info from detail page
            const priceEl = document.querySelector('.price, [class*="price"], .adPrice');
            const price = priceEl ? priceEl.innerText : '';
            
            // Look for specific fields
            const getField = (pattern) => {
                const match = text.match(pattern);
                return match ? match[1].trim() : null;
            };
            
            return {
                price: price,
                fullText: text.substring(0, 5000),
                neighborhood: getField(/(?:квартал|ж\.к\.|кв\.)[:\s]*([^\n,]+)/i),
                address: getField(/(?:адрес|улица)[:\s]*([^\n]+)/i)
            };
        });
        
        return detail;
        
    } catch (err) {
        console.error(`Error fetching detail ${listing.source_id}:`, err.message);
        return null;
    }
}

async function main() {
    console.log('Starting Imot.bg scraper...');
    
    const db = new PropertyDatabase();
    
    const browser = await puppeteer.launch({
        headless: 'new',
        args: ['--no-sandbox', '--disable-setuid-sandbox']
    });
    
    const page = await browser.newPage();
    await page.setUserAgent('Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36');
    
    // Set Bulgarian locale
    await page.setExtraHTTPHeaders({
        'Accept-Language': 'bg-BG,bg;q=0.9,en;q=0.8'
    });
    
    try {
        // Get КЧСИ properties we need to find comparables for
        const kchsiProperties = db.getActiveAuctions();
        console.log(`Found ${kchsiProperties.length} active КЧСИ auctions to match`);
        
        // Group by city
        const byCity = {};
        for (const prop of kchsiProperties) {
            if (!byCity[prop.city]) byCity[prop.city] = [];
            byCity[prop.city].push(prop);
        }
        
        // For each city, scrape listings
        for (const [city, properties] of Object.entries(byCity)) {
            console.log(`\n=== ${city}: ${properties.length} auctions to match ===`);
            
            let allListings = [];
            const maxPages = 5; // Limit for POC
            
            // Scrape search results
            for (let pageNum = 1; pageNum <= maxPages; pageNum++) {
                const listings = await scrapeImotBgSearch(page, city, pageNum);
                
                if (listings.length === 0) break;
                
                allListings = allListings.concat(listings);
                console.log(`Page ${pageNum}: ${listings.length} listings`);
                
                await new Promise(r => setTimeout(r, 2000)); // Rate limit
            }
            
            console.log(`Total listings found: ${allListings.length}`);
            
            // Scrape details and save
            for (const listing of allListings.slice(0, 50)) { // Limit for POC
                const detail = await scrapeListingDetail(page, listing);
                
                if (!detail) continue;
                
                const fullText = detail.fullText || listing.raw_text || '';
                const { eur, bgn } = extractPrice(detail.price || fullText);
                const sqm = extractSqm(fullText);
                const rooms = extractRooms(fullText);
                const { floor, totalFloors } = extractFloor(fullText);
                
                const record = {
                    source: 'imot.bg',
                    source_id: listing.source_id,
                    price_eur: eur,
                    price_bgn: bgn,
                    city: city,
                    neighborhood: detail.neighborhood,
                    address: detail.address,
                    sqm: sqm,
                    rooms: rooms,
                    floor: floor,
                    total_floors: totalFloors,
                    property_type: extractPropertyType(fullText),
                    construction_type: extractConstruction(fullText),
                    year_built: null, // Would need more parsing
                    price_per_sqm: sqm && eur ? Math.round(eur / sqm) : null,
                    url: listing.url
                };
                
                try {
                    db.insertMarketListing(record);
                    console.log(`✓ ${listing.source_id}: ${sqm || '?'}m² - €${eur || '?'}`);
                } catch (err) {
                    // Likely duplicate
                    if (!err.message.includes('UNIQUE')) {
                        console.error(`✗ ${listing.source_id}:`, err.message);
                    }
                }
                
                await new Promise(r => setTimeout(r, 1000)); // Rate limit
            }
        }
        
        // Print stats
        const stats = db.getStats();
        console.log('\n=== Scraping Complete ===');
        console.log(`Market listings: ${stats.market_count}`);
        
    } catch (err) {
        console.error('Scraper error:', err);
    } finally {
        await browser.close();
        db.close();
    }
}

if (require.main === module) {
    main().catch(console.error);
}

module.exports = { main };
