#!/bin/bash
# Domain Migration Script
# Usage: ./scripts/migrate-domain.sh kchsi-sdelki.bg

set -e

if [ -z "$1" ]; then
    echo "Usage: $0 <new-domain>"
    echo "Example: $0 kchsi-sdelki.bg"
    exit 1
fi

NEW_DOMAIN="$1"
OLD_PATTERN="martinpetrov8.github.io/real-estate-price-matching"

echo "🔄 Migrating from $OLD_PATTERN to $NEW_DOMAIN"

# Find all files with hardcoded URLs
FILES=$(grep -rl "$OLD_PATTERN" --include="*.html" --include="*.xml" --include="*.js" . 2>/dev/null || true)

if [ -z "$FILES" ]; then
    echo "✅ No hardcoded URLs found - already migrated"
    exit 0
fi

echo "📝 Files to update:"
echo "$FILES"

for file in $FILES; do
    echo "  Updating: $file"
    sed -i "s|https://$OLD_PATTERN|https://$NEW_DOMAIN|g" "$file"
    sed -i "s|$OLD_PATTERN|$NEW_DOMAIN|g" "$file"
done

# Update robots.txt
sed -i "s|Sitemap:.*|Sitemap: https://$NEW_DOMAIN/sitemap.xml|" robots.txt 2>/dev/null || true

echo ""
echo "✅ Migration complete! Next steps:"
echo "  1. Update config.js SITE_URL"
echo "  2. Set up DNS + SSL"  
echo "  3. Submit sitemap to Google Search Console"
