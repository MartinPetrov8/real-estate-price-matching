#!/bin/bash
# Build step: minify JS/CSS and add cache-busting hash
set -e

cd "$(dirname "$0")/.."

HASH=$(date +%Y%m%d%H%M)

echo "Building with hash: $HASH"

# Minify
terser app.js -o app.min.js --compress --mangle
terser analytics.js -o analytics.min.js --compress --mangle
terser subscribe-modal.js -o subscribe-modal.min.js --compress --mangle
cleancss -o styles.min.css styles.css

echo "✓ Minified JS/CSS"

# Update HTML files to use minified versions with cache hash
for f in index.html cities/*.html blog/*.html contact.html privacy.html 404.html; do
    [ -f "$f" ] || continue
    # CSS
    sed -i "s|styles\.min\.css?v=[0-9]*|styles.min.css?v=$HASH|g" "$f"
    sed -i "s|styles\.css|styles.min.css?v=$HASH|g" "$f"
    # JS
    sed -i "s|app\.min\.js?v=[0-9]*|app.min.js?v=$HASH|g" "$f"
    sed -i "s|\"app\.js\"|\"app.min.js?v=$HASH\"|g" "$f"
    sed -i "s|analytics\.min\.js?v=[0-9]*|analytics.min.js?v=$HASH|g" "$f"
    sed -i "s|\"analytics\.js\"|\"analytics.min.js?v=$HASH\"|g" "$f"
    sed -i "s|subscribe-modal\.min\.js?v=[0-9]*|subscribe-modal.min.js?v=$HASH|g" "$f"
    sed -i "s|\"subscribe-modal\.js\"|\"subscribe-modal.min.js?v=$HASH\"|g" "$f"
done

echo "✓ Updated HTML references (hash=$HASH)"

# Sizes
echo ""
echo "Sizes:"
wc -c app.min.js analytics.min.js subscribe-modal.min.js styles.min.css
echo ""
echo "Done!"
