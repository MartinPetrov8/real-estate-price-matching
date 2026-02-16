# Deployment Guide

## Railway API Deployment

### Initial Setup
1. Go to [railway.app](https://railway.app)
2. Create new project → Deploy from GitHub
3. Select `real-estate-price-matching` repo

### Configuration
Railway looks for `app.py` in project root. The app uses:
- `Procfile`: `web: python -m gunicorn app:app --bind 0.0.0.0:$PORT`
- `railway.toml`: Build and deploy settings

### Environment Variables
Add in Railway → Service → Variables:

| Variable | Value | Required |
|----------|-------|----------|
| `RESEND_API_KEY` | Your Resend API key | Yes |
| `SENDER_EMAIL` | `onboarding@resend.dev` | Yes |
| `SENDER_NAME` | `Изгоден Имот` | Optional |
| `SITE_URL` | `https://martinpetrov8.github.io/real-estate-price-matching` | Yes |

### Expose API
1. Click service card
2. Go to Settings tab
3. Scroll to Networking
4. Click "Generate Domain"

### Common Issues

**`gunicorn: command not found`**
- Use `python -m gunicorn` instead of `gunicorn`
- Ensure `gunicorn` is in `requirements.txt`

**Build succeeds but app crashes**
- Check Deploy Logs for errors
- Verify all env vars are set
- Make sure `app.py` is in project root

**502 Application failed to respond**
- App is crashing on startup
- Check for missing dependencies
- Verify database path exists

## Scraper Deployment

### OLX (Playwright)
OLX.bg requires Playwright to bypass CAPTCHA:

```bash
# Install Playwright
pip install playwright

# Install browsers (specify custom path)
PLAYWRIGHT_BROWSERS_PATH=/path/to/browsers playwright install chromium

# Run scraper
PLAYWRIGHT_BROWSERS_PATH=/path/to/browsers python scrapers/olx_playwright.py
```

### Daily Cron
Add to crontab:
```bash
# Run pipeline at 6 AM Sofia time (4 AM UTC)
0 4 * * * cd /path/to/repo && PLAYWRIGHT_BROWSERS_PATH=/path/to/browsers python run_pipeline.py
```
