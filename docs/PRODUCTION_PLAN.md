# КЧСИ Production Readiness Plan

**Goal:** Get the site production-ready with analytics, auth-ready backend, and all meaningful fixes. Skip the noise.

**Current state:** Working static site (GitHub Pages) + Flask API (Railway) + daily data pipeline. Subscribe flow exists but alerts aren't live yet.

---

## Sprint 1: Analytics + "Coming Soon" Label (ship first)

**Why first:** We need traffic data before any monetization decisions make sense.

### 1.1 Add GA4 to all pages
- Create GA4 property, get Measurement ID
- Add gtag snippet to: `index.html`, `cities/sofia.html`, `cities/varna.html`, `cities/index.html`, `contact.html`, `privacy.html`, `404.html`
- Consent mode: start with `analytics_storage: denied`, flip on consent
- Track key events: `filter_applied`, `deal_modal_open`, `bcpea_click`, `subscribe_modal_open`, `subscribe_attempt`
- Update CSP in `index.html` to allow `https://www.googletagmanager.com` and `https://www.google-analytics.com`

### 1.2 Minimal cookie consent banner
- Small bottom bar: "Използваме бисквитки за анализ на трафика. [Приемам] [Отказвам]"
- On accept: `gtag('consent', 'update', { analytics_storage: 'granted' })`, save preference to localStorage
- On decline: do nothing (GA stays in denied mode, no tracking)
- No heavy CMP library needed — 30 lines of JS

### 1.3 "Очаквайте скоро" badge on Известия
- Add amber pill badge next to nav link
- Inside modal: "Очаквайте скоро" badge + change button to "Запиши ме за ранен достъп" (captures interest without promising live alerts)
- Track clicks as `subscribe_intent` event in GA4

### 1.4 Update privacy.html
- Add GA4 disclosure, what's collected, retention, opt-out info

**Deliverable:** Deploy, wait 2-4 weeks, review traffic data.

---

## Sprint 2: Backend Hardening (auth-ready foundation)

**Why:** Current `app.py` and `alerts/api.py` are duplicated and fragile. Before adding Stripe or any auth, the backend needs to be one clean thing.

### 2.1 Consolidate to single Flask app
- Kill `app.py` (root). Use `alerts/api.py` as the single backend — it already has rate limiting, security headers, input validation, safe redirects
- Verify Railway deploys from the right entrypoint
- Single `requirements.txt` at root

### 2.2 Add proper input validation
- `alerts/api.py` already validates email regex + city whitelist + discount bounds ✅
- Add: max email length check (254 chars) — already done ✅
- Add: request size limit (`MAX_CONTENT_LENGTH = 1024`)

### 2.3 Migrate SQLite → Postgres (Railway)
- SQLite on Railway is ephemeral (resets on deploy). This is a ticking bomb.
- Railway offers Postgres for free tier. Switch now.
- Schema stays the same, just swap `sqlite3` for `psycopg2`
- Add connection pooling

### 2.4 Add user auth table (prep for Stripe)
- New `users` table: `id`, `email`, `password_hash`, `tier` (free/pro), `stripe_customer_id`, `created_at`
- Don't build login UI yet — just have the table ready
- Current `subscribers` table becomes linked to `users` via email

### 2.5 Error tracking
- Add Sentry (free tier) to Flask backend
- Frontend Sentry optional (low priority — static site has few failure modes)

### 2.6 Uptime monitoring
- Add UptimeRobot (free) for:
  - GitHub Pages main URL
  - Railway `/health` endpoint
  - Alert on downtime via Telegram

**Deliverable:** Solid backend that won't lose data and is ready for auth/payments.

---

## Sprint 3: Frontend Polish

### 3.1 Cache busting
- Add `?v=YYYYMMDD` hash to CSS/JS references in HTML
- Or set up a simple build step that appends content hash

### 3.2 Minify CSS/JS
- `styles.css` is 1118 lines. Minify for production.
- `app.js` — same. Can use `terser` + `cssnano` as a pre-deploy step.

### 3.3 Modal accessibility
- Add `role="dialog"`, `aria-modal="true"`, `aria-labelledby`
- Focus trap (Tab cycles within modal)
- Close on Escape key

### 3.4 City pages SEO parity
- Each city page needs unique `<title>`, `<meta description>`, canonical, and structured data
- Check: do they currently have these? If not, template them.

### 3.5 Mobile QA pass
- Test on actual phones (or Chrome DevTools mobile emulation)
- Verify: filter toggle works, cards readable, modal scrollable, nav accessible

**Deliverable:** Professional-feeling frontend.

---

## Sprint 4: Stripe + Paid Alerts (only after traffic data confirms interest)

### 4.1 Stripe Checkout integration
- `POST /billing/create-checkout-session` — creates Stripe session for €5/mo
- Redirect to Stripe hosted checkout, back to success/cancel URLs
- Webhook endpoint: `POST /billing/webhook` with signature verification

### 4.2 Webhook handling
- `checkout.session.completed` → activate subscription
- `customer.subscription.updated` → update tier
- `customer.subscription.deleted` → downgrade to free
- `invoice.payment_failed` → mark `past_due`, send warning email
- Idempotency: store processed event IDs

### 4.3 Alert gating
- `send_alerts.py` checks `users.tier = 'pro'` before sending
- Free users get "Очаквайте скоро" treatment
- Pro users get daily email alerts matching their criteria

### 4.4 Simple login
- Magic link auth (no passwords initially): enter email → get link → click → logged in via JWT cookie
- Or password-based with `bcrypt` if we want traditional flow
- Session management: JWT in httpOnly cookie

**Deliverable:** Revenue. Or at least the plumbing for it.

---

## What I'm NOT doing (and why)

| Suggestion from audit | Skip? | Reason |
|---|---|---|
| Service Worker / offline | ✅ Skip | Overkill for a data site that updates daily |
| SSG migration (Next.js/Astro) | ✅ Skip | Only worth it if JS indexing is confirmed as SEO bottleneck |
| CSRF tokens | ✅ Skip | JSON API + CORS is sufficient for now |
| RealEstateListing schema | ✅ Skip | Google rarely shows rich snippets for RE |
| Frontend Sentry | ✅ Skip | Static site, few failure modes, add later if needed |
| Tighten CSP (remove unsafe-inline) | ⚠️ Later | Requires moving all inline scripts/styles to files — big refactor for low risk |
| Skip-to-content link | ⚠️ Later | Nice to have, not blocking |

---

## Implementation Order

1. **Sprint 1** → I can implement most of this now (except GA4 property creation — you need to do that in Google Analytics console)
2. **Sprint 2** → Needs Railway config changes. Postgres migration is the big one.
3. **Sprint 3** → Pure frontend work, can be done anytime
4. **Sprint 4** → Only after Sprint 1 data proves there's traffic worth monetizing

---

## Decision needed from Martin

1. **GA4 property** — Do you already have one? If not, create at analytics.google.com and give me the `G-XXXXXXXXXX` Measurement ID
2. **Postgres** — Approve Railway Postgres add-on? (free tier available)
3. **Auth approach** — Magic link (simpler, no passwords) vs traditional email+password?
4. **Sprint 1 go-ahead** — Want me to implement analytics + coming soon badge now?
