# КЧСИ Имотни Сделки - Frontend

Mobile-friendly web interface for Bulgarian real estate auction deals.

## Files
- `index.html` - Main page
- `styles.css` - Responsive CSS (mobile-first)
- `app.js` - Vanilla JS app logic
- `deals.json` - Deal data (replace with real data)

## Features
- ✅ Filter by city (София, Пловдив, Варна, Бургас)
- ✅ Filter by star rating (3-5 stars based on discount %)
- ✅ Sort by savings, price, or deadline
- ✅ Prominent savings % display
- ✅ Price comparison (auction vs market)
- ✅ Links to КЧСИ auction pages
- ✅ Mobile responsive
- ✅ Bulgarian language

## Star Rating System
- ⭐⭐⭐⭐⭐ (5 stars): 40%+ discount
- ⭐⭐⭐⭐ (4 stars): 30-40% discount  
- ⭐⭐⭐ (3 stars): 20-30% discount

## Usage

```bash
# Start local server
cd real-estate-price-matching/frontend
python3 -m http.server 8080
# Open http://localhost:8080
```

## Data Format
```json
{
  "bcpea_id": "12345",
  "city": "София",
  "neighborhood": "Лозенец",
  "sqm": 85,
  "rooms": 3,
  "floor": 4,
  "property_type": "Апартамент",
  "auction_price": 85000,
  "market_price": 150000,
  "discount_pct": 43,
  "savings_eur": 65000,
  "auction_end": "2026-02-15T23:59:59Z",
  "market_url": "https://www.alo.bg/obiava/sample"
}
```

## Integration
Replace `deals.json` with output from the analysis pipeline:
```bash
node src/matching/analyzer.js
cp data/latest-analysis.json frontend/deals.json
```
