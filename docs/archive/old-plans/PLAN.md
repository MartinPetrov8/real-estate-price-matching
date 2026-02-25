# Real Estate Tools - Master Project Plan

**Status:** Active
**Created:** 2026-02-01
**Owner:** Cookie + Martin

---

## 🎯 Vision

Build profitable real estate tools for the Bulgarian market, targeting underserved segments:
1. **КЧСИ Auction Monitor** — Alert system for enforcement auctions
2. **FB Group Aggregator** — Browser extension to aggregate listings from Facebook groups

---

## 📊 Market Opportunity

### КЧСИ Auctions
- ~1,000+ active property listings at any time
- 30-day notice before auction closes
- Starting prices at 80% of valuation (often below market)
- **Zero competition** for tooling
- Target users: Investors, brokers, bargain hunters

### Facebook Groups
- Primary discovery channel for many Bulgarian brokers
- Manual monitoring is painful (10-20+ groups)
- API access killed by Meta in April 2024
- **Zero legal tools exist** for aggregation
- Target users: Brokers, agencies

---

## 🏗️ Architecture

```
┌─────────────────────────────────────────────────────────┐
│                    FRONTEND                              │
│  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐     │
│  │  Web App    │  │  Telegram   │  │  Extension  │     │
│  │  Dashboard  │  │    Bot      │  │   Popup     │     │
│  └──────┬──────┘  └──────┬──────┘  └──────┬──────┘     │
└─────────┼────────────────┼────────────────┼─────────────┘
          │                │                │
          ▼                ▼                ▼
┌─────────────────────────────────────────────────────────┐
│                    BACKEND API                           │
│  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐     │
│  │  Listings   │  │   Alerts    │  │   Users     │     │
│  │  Service    │  │   Service   │  │   Service   │     │
│  └──────┬──────┘  └──────┬──────┘  └──────┬──────┘     │
└─────────┼────────────────┼────────────────┼─────────────┘
          │                │                │
          ▼                ▼                ▼
┌─────────────────────────────────────────────────────────┐
│                    DATA LAYER                            │
│  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐     │
│  │  SQLite/    │  │   Redis     │  │  S3/Local   │     │
│  │  Postgres   │  │   Cache     │  │   Storage   │     │
│  └─────────────┘  └─────────────┘  └─────────────┘     │
└─────────────────────────────────────────────────────────┘
          ▲                              ▲
          │                              │
┌─────────┴──────────┐    ┌─────────────┴─────────────┐
│   КЧСИ Scraper     │    │   FB Extension Content    │
│   (Cron Job)       │    │   Script (User Browser)   │
└────────────────────┘    └───────────────────────────┘
```

---

## 📦 Deliverables

### Phase 1: MVP Prototypes (This Week)
- [ ] КЧСИ scraper - working data extraction
- [ ] КЧСИ alert system - Telegram notifications
- [ ] FB extension - basic post extraction
- [ ] Shared backend API skeleton

### Phase 2: Beta Product (Week 2-3)
- [ ] Web dashboard for both tools
- [ ] User accounts + saved searches
- [ ] Payment integration (Stripe)
- [ ] 5 beta users recruited

### Phase 3: Launch (Week 4)
- [ ] Landing page
- [ ] Pricing page
- [ ] Chrome Web Store submission
- [ ] Marketing push

---

## 💰 Business Model

| Product | Free Tier | Paid Tier | Price |
|---------|-----------|-----------|-------|
| КЧСИ Monitor | 1 alert/day | Unlimited + filters | €15/mo |
| FB Aggregator | 3 groups | Unlimited + alerts | €20/mo |
| Bundle | - | Both products | €30/mo |

**Target:** 100 paying users = €3,000/mo MRR

---

## ⚠️ Risks & Mitigations

| Risk | Probability | Impact | Mitigation |
|------|-------------|--------|------------|
| КЧСИ blocks scraping | Low | High | Respectful rate limits, user-agent rotation |
| FB detects extension | Medium | High | Minimal DOM manipulation, no automation |
| Low user adoption | Medium | High | Start with broker network, referral incentives |
| Competition enters | Low | Medium | Move fast, build moat with data/features |

---

## 📁 Project Structure

```
projects/real-estate/
├── PLAN.md (this file)
├── LOG.md (activity log)
├── plans/
│   ├── kcsi-prototype.md
│   └── fb-extension-prototype.md
└── prototypes/
    ├── kcsi-scraper/
    │   ├── scraper.js
    │   ├── parser.js
    │   ├── alerter.js
    │   └── package.json
    └── fb-extension/
        ├── manifest.json
        ├── content.js
        ├── background.js
        ├── popup.html
        └── popup.js
```

---

## 📅 Next Steps

1. Build КЧСИ scraper prototype
2. Build FB extension prototype
3. Test both with sample data
4. Critical review of viability
5. Present findings to Martin (morning Feb 2)
