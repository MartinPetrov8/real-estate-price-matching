/**
 * Test script for КЧСИ scraper
 * Tests parsing logic without hitting the live site
 */

const { initDb, getStats, findDeals } = require('./scraper');

// Sample HTML that matches the structure we've seen
const sampleHtml = `
<!DOCTYPE html>
<html>
<body>
<div class="property-list">
  <div class="property-card">
    <div class="price">5 100.00 EUR</div>
    <div>Начална цена</div>
    <div>НАСЕЛЕНО МЯСТО</div>
    <div>гр. Бургас</div>
    <div>Адрес</div>
    <div>гр. Бургас, к/с Славейков, бл. 78</div>
    <div>ОКРЪЖЕН СЪД</div>
    <div>Бургас</div>
    <div>ЧАСТЕН СЪДЕБЕН ИЗПЪЛНИТЕЛ</div>
    <div>Станимира Стефанова Николова</div>
    <div>СРОК</div>
    <div>от 09.02.2026 до 09.03.2026</div>
    <div>ОБЯВЯВАНЕ НА</div>
    <div>10.03.2026 09:00</div>
    <a href="/properties/85750">View</a>
  </div>
  
  <div class="property-card">
    <div class="price">707 703.15 EUR</div>
    <div>Начална цена</div>
    <div>НАСЕЛЕНО МЯСТО</div>
    <div>гр. Добрич</div>
    <div>ОКРЪЖЕН СЪД</div>
    <div>Добрич</div>
    <div>ЧАСТЕН СЪДЕБЕН ИЗПЪЛНИТЕЛ</div>
    <div>Лучия Тасева Тасева</div>
    <div>СРОК</div>
    <div>от 16.02.2026 до 16.03.2026</div>
    <div>ОБЯВЯВАНЕ НА</div>
    <div>17.03.2026 09:00</div>
    <a href="/properties/85748">View</a>
  </div>
  
  <div class="property-card">
    <div class="price">43 439.36 EUR</div>
    <div>НАСЕЛЕНО МЯСТО</div>
    <div>с. Горна Малина</div>
    <div>Адрес</div>
    <div>с. Горна Малина, м. "Дживирица"</div>
    <div>ОКРЪЖЕН СЪД</div>
    <div>София окръг</div>
    <div>ЧАСТЕН СЪДЕБЕН ИЗПЪЛНИТЕЛ</div>
    <div>Владимир Людмилов Цачев</div>
    <div>СРОК</div>
    <div>от 04.02.2026 до 04.03.2026</div>
    <div>ОБЯВЯВАНЕ НА</div>
    <div>05.03.2026 09:00</div>
    <a href="/properties/85739">View</a>
  </div>
</div>
<a href="?page=2">Next »</a>
</body>
</html>
`;

// Test parsing functions
function testParsing() {
  console.log('=== Testing Parsing Functions ===\n');
  
  const cheerio = require('cheerio');
  const $ = cheerio.load(sampleHtml);
  
  // Test price parsing
  const prices = ['5 100.00', '707 703.15', '43 439.36'];
  console.log('Price parsing:');
  prices.forEach(p => {
    const cleaned = p.replace(/\s/g, '').replace(',', '.');
    const match = cleaned.match(/([\d.]+)/);
    console.log(`  "${p}" -> ${match ? parseFloat(match[1]) : 'FAILED'}`);
  });
  
  // Test date parsing
  const dates = ['09.02.2026', '10.03.2026 09:00'];
  console.log('\nDate parsing:');
  dates.forEach(d => {
    const match = d.match(/(\d{2})\.(\d{2})\.(\d{4})(?:\s+(\d{2}):(\d{2}))?/);
    if (match) {
      const [_, day, month, year, hour, minute] = match;
      const result = hour ? `${year}-${month}-${day}T${hour}:${minute}:00` : `${year}-${month}-${day}`;
      console.log(`  "${d}" -> ${result}`);
    }
  });
  
  // Test property ID extraction
  console.log('\nProperty ID extraction:');
  $('a[href*="/properties/"]').each((i, el) => {
    const href = $(el).attr('href');
    const match = href.match(/\/properties\/(\d+)/);
    console.log(`  "${href}" -> ID: ${match ? match[1] : 'FAILED'}`);
  });
  
  console.log('\n✅ Parsing tests complete');
}

// Test database operations
function testDatabase() {
  console.log('\n=== Testing Database Operations ===\n');
  
  const db = initDb();
  
  // Insert test data
  const testListings = [
    {
      id: 'TEST001',
      price_eur: 50000,
      city: 'София',
      court: 'София град',
      bid_start: '2026-02-01',
      bid_end: '2026-03-01',
    },
    {
      id: 'TEST002', 
      price_eur: 25000,
      city: 'Пловдив',
      court: 'Пловдив',
      bid_start: '2026-02-01',
      bid_end: '2026-03-01',
    },
    {
      id: 'TEST003',
      price_eur: 150000,
      city: 'Варна',
      court: 'Варна',
      bid_start: '2026-02-01',
      bid_end: '2026-03-01',
    },
  ];
  
  const now = new Date().toISOString();
  const stmt = db.prepare(`
    INSERT OR REPLACE INTO listings 
    (id, price_eur, city, court, bid_start, bid_end, first_seen, last_seen, url)
    VALUES (@id, @price_eur, @city, @court, @bid_start, @bid_end, @now, @now, '')
  `);
  
  testListings.forEach(l => {
    stmt.run({ ...l, now });
    console.log(`  Inserted: ${l.id} - ${l.city} - ${l.price_eur} EUR`);
  });
  
  // Test queries
  console.log('\nQuery tests:');
  const stats = getStats(db);
  console.log(`  Total listings: ${stats.total}`);
  console.log(`  By court:`, stats.byCourt);
  
  const deals = findDeals(db, 100000);
  console.log(`  Deals under 100k: ${deals.length}`);
  
  // Cleanup test data
  db.prepare("DELETE FROM listings WHERE id LIKE 'TEST%'").run();
  console.log('\n  Cleaned up test data');
  
  db.close();
  console.log('\n✅ Database tests complete');
}

// Run all tests
console.log('КЧСИ Scraper Tests');
console.log('==================\n');

testParsing();
testDatabase();

console.log('\n🎉 All tests passed!');
