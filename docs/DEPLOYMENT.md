# Deployment Guide

## Current Setup (GitHub Pages)
- URL: https://martinpetrov8.github.io/real-estate-price-matching/
- Hosting: GitHub Pages (free)
- SSL: Automatic via GitHub

## Production Deployment (Custom Domain)

### 1. Buy Domain
Recommended: `kchsi-sdelki.bg` or similar
Registrars: ICN.bg, Superhosting.bg, Namecheap

### 2. DNS Setup (Cloudflare recommended)

```
Type  | Name | Value
------|------|------
A     | @    | 185.199.108.153
A     | @    | 185.199.109.153
A     | @    | 185.199.110.153
A     | @    | 185.199.111.153
CNAME | www  | kchsi-sdelki.bg
```

### 3. GitHub Pages Custom Domain
1. Go to repo Settings → Pages
2. Add custom domain: `kchsi-sdelki.bg`
3. Enable "Enforce HTTPS"

### 4. Run Domain Migration
```bash
./scripts/migrate-domain.sh kchsi-sdelki.bg
git add -A && git commit -m "chore: migrate to production domain"
git push
```

### 5. Update CNAME File
```bash
echo "kchsi-sdelki.bg" > CNAME
git add CNAME && git commit -m "chore: add CNAME" && git push
```

### 6. Submit to Search Engines
- Google Search Console: https://search.google.com/search-console
- Bing Webmaster Tools: https://www.bing.com/webmasters

### 7. Set Up 301 Redirects (Optional)
If keeping GitHub Pages URL active, add redirect in DNS or use Cloudflare Page Rules.

## Monitoring

### Uptime
- Use UptimeRobot (free) or Better Uptime
- Monitor: `https://kchsi-sdelki.bg/deals.json`

### Analytics (Privacy-Friendly)
Options:
- Plausible.io (~€9/mo)
- GoatCounter (free, self-host)
- Cloudflare Analytics (free with Cloudflare)

## Daily Pipeline
Cron job runs at 9:00 AM Sofia time:
1. Scrapes КЧСИ + market data
2. Exports deals.json
3. Pushes to GitHub (auto-deploys)
