# Facebook Group Aggregator Extension - Detailed Plan

## 🎯 Objective

Build a Chrome extension that:
1. Detects when user is browsing Facebook groups
2. Extracts real estate listings from posts
3. Sends data to backend for aggregation
4. Shows unified feed in extension popup

---

## 📊 Target Data

### From Facebook Group Posts
- Post text content
- Poster name (optional, for contacting)
- Post timestamp
- Group name/ID
- Images (URLs)
- Comments count
- Post URL/ID

### Extracted Structured Data (via parsing/AI)
- Property type (apartment, house, room, etc.)
- Transaction type (sale, rent)
- Price
- Location (city, neighborhood)
- Size (rooms, sqm)
- Contact info (phone, "DM me")

---

## 🔧 Technical Architecture

### Extension Components

```
fb-extension/
├── manifest.json        # Extension config (Manifest V3)
├── content.js           # Injected into Facebook pages
├── background.js        # Service worker for API calls
├── popup.html           # Extension popup UI
├── popup.js             # Popup logic
├── styles.css           # Popup styling
└── icons/               # Extension icons
    ├── icon16.png
    ├── icon48.png
    └── icon128.png
```

### Data Flow

```
┌─────────────────────────────────────────────────────────┐
│                    USER'S BROWSER                        │
│                                                          │
│  ┌─────────────────┐    ┌─────────────────┐             │
│  │   Facebook.com  │    │   Extension     │             │
│  │   Group Page    │───▶│   Content.js    │             │
│  └─────────────────┘    └────────┬────────┘             │
│                                  │ Extract posts        │
│                                  ▼                      │
│                         ┌─────────────────┐             │
│                         │  Background.js  │             │
│                         │  (Service Wkr)  │             │
│                         └────────┬────────┘             │
│                                  │                      │
└──────────────────────────────────┼──────────────────────┘
                                   │ POST /api/listings
                                   ▼
                          ┌─────────────────┐
                          │   Backend API   │
                          │   (Your Server) │
                          └────────┬────────┘
                                   │
                                   ▼
                          ┌─────────────────┐
                          │    Database     │
                          │  (Aggregated)   │
                          └─────────────────┘
```

---

## 📐 Manifest V3 Configuration

```json
{
  "manifest_version": 3,
  "name": "ImotWatch - Real Estate Aggregator",
  "version": "0.1.0",
  "description": "Aggregate real estate listings from Facebook groups",
  "permissions": [
    "storage",
    "activeTab"
  ],
  "host_permissions": [
    "https://www.facebook.com/*",
    "https://api.imotwatch.bg/*"
  ],
  "content_scripts": [
    {
      "matches": ["https://www.facebook.com/groups/*"],
      "js": ["content.js"],
      "run_at": "document_idle"
    }
  ],
  "background": {
    "service_worker": "background.js"
  },
  "action": {
    "default_popup": "popup.html",
    "default_icon": {
      "16": "icons/icon16.png",
      "48": "icons/icon48.png",
      "128": "icons/icon128.png"
    }
  },
  "icons": {
    "16": "icons/icon16.png",
    "48": "icons/icon48.png",
    "128": "icons/icon128.png"
  }
}
```

---

## 🔍 Content Script Strategy

### Post Detection

Facebook's DOM is complex and changes frequently. Strategy:

1. **Mutation Observer** — Watch for new posts loaded via infinite scroll
2. **Semantic selectors** — Target `[role="article"]` rather than class names
3. **Text patterns** — Look for real estate keywords to filter relevant posts

### Keywords to Match (Bulgarian)

```javascript
const RE_KEYWORDS = [
  // Transaction
  'продава', 'продавам', 'под наем', 'наем', 'давам под наем',
  // Property types
  'апартамент', 'стая', 'къща', 'студио', 'мезонет', 'ателие',
  'гараж', 'паркомясто', 'парцел', 'магазин', 'офис',
  // Rooms
  'едностаен', 'двустаен', 'тристаен', 'многостаен',
  '1-стаен', '2-стаен', '3-стаен', '4-стаен',
  // Price indicators
  'лв', 'лева', 'евро', 'eur', '€', 'bgn',
  // Size
  'кв.м', 'квм', 'кв м', 'm2', 'м2'
];
```

### Data Extraction

```javascript
function extractListingData(postElement) {
  const text = postElement.innerText;
  
  return {
    // Raw data
    rawText: text.substring(0, 2000),
    postUrl: extractPostUrl(postElement),
    groupName: extractGroupName(),
    timestamp: extractTimestamp(postElement),
    images: extractImageUrls(postElement),
    
    // Parsed (basic regex, AI enhancement later)
    price: extractPrice(text),
    location: extractLocation(text),
    propertyType: extractPropertyType(text),
    transactionType: extractTransactionType(text),
    contact: extractContact(text),
    
    // Meta
    extractedAt: new Date().toISOString(),
    extensionVersion: '0.1.0'
  };
}
```

---

## 🖼️ Popup UI Design

```
┌────────────────────────────────────┐
│  🏠 ImotWatch          [⚙️] [🔄]  │
├────────────────────────────────────┤
│  📊 Today: 12 listings found       │
│  📍 Groups monitored: 5            │
├────────────────────────────────────┤
│  ┌────────────────────────────┐   │
│  │ 🏢 2-стаен, Младост        │   │
│  │ 💰 85,000 EUR              │   │
│  │ 📅 2 hours ago             │   │
│  │ [View Post] [Contact]      │   │
│  └────────────────────────────┘   │
│  ┌────────────────────────────┐   │
│  │ 🏠 Къща, Бояна             │   │
│  │ 💰 250,000 EUR             │   │
│  │ 📅 5 hours ago             │   │
│  │ [View Post] [Contact]      │   │
│  └────────────────────────────┘   │
│  ... more listings ...             │
├────────────────────────────────────┤
│  [View All in Dashboard →]         │
└────────────────────────────────────┘
```

---

## 📝 MVP Scope

### Include
- [x] Manifest V3 setup
- [x] Content script injection on FB groups
- [x] Basic post detection
- [x] Keyword filtering for real estate
- [x] Local storage of found listings
- [x] Simple popup showing found listings

### Exclude (Phase 2)
- Backend API integration
- User accounts
- Cross-device sync
- Advanced NLP parsing
- AI-powered extraction
- Telegram alerts

---

## ⚠️ Technical Risks

| Risk | Probability | Mitigation |
|------|-------------|------------|
| FB DOM changes | High | Use semantic selectors, monitor & update |
| Extension blocked by FB | Low | Minimal DOM manipulation, passive reading |
| Chrome Web Store rejection | Medium | Follow policies strictly, clear privacy policy |
| Performance impact | Low | Debounce extraction, limit processing |

---

## 🔐 Privacy Considerations

- Extension only activates on facebook.com/groups/*
- No data sent without user consent
- Clear disclosure of what data is collected
- Option to disable sync, use locally only
- No password/credential access
- Open source code for transparency

---

## ✅ Success Criteria

1. Extension loads on Facebook group pages
2. Detects and extracts real estate posts
3. Filters out non-relevant posts (>80% accuracy)
4. Displays found listings in popup
5. Works across common Bulgarian RE groups
6. No errors, no performance degradation
