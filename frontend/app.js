(function() {
    'use strict';
    
    let allDeals = [];
    let filteredDeals = [];
    
    // DOM elements
    const el = {
        loading: document.getElementById('loadingState'),
        error: document.getElementById('errorState'),
        empty: document.getElementById('emptyState'),
        grid: document.getElementById('dealsGrid'),
        count: document.getElementById('resultsCount'),
        heroTotal: document.getElementById('heroTotalDeals'),
        heroAvg: document.getElementById('heroAvgDiscount'),
        heroBest: document.getElementById('heroBestDeal'),
        city: document.getElementById('cityFilter'),
        type: document.getElementById('typeFilter'),
        minPrice: document.getElementById('minPrice'),
        maxPrice: document.getElementById('maxPrice'),
        discount: document.getElementById('discountFilter'),
        sort: document.getElementById('sortBy')
    };
    
    // Type icons
    const TYPE_ICONS = {
        'apartment': '🏢',
        'house': '🏠',
        'garage': '🚗',
        'commercial': '🏪',
        'other': '🏛️'
    };
    
    // Type labels (Bulgarian)
    const TYPE_LABELS = {
        'apartment': 'Апартамент',
        'house': 'Къща',
        'garage': 'Гараж',
        'commercial': 'Търговски',
        'other': 'Друго'
    };
    
    // Helpers
    function fmtPrice(p) { 
        return p ? '€' + Math.round(p).toLocaleString('de-DE') : '€?'; 
    }
    
    function fmtDate(d) { 
        if (!d) return 'Неизвестна';
        return new Date(d).toLocaleDateString('bg-BG', {day:'numeric', month:'short', year:'numeric'}); 
    }
    
    function daysUntil(d) { 
        if (!d) return null;
        const days = Math.ceil((new Date(d) - new Date()) / 86400000);
        return days;
    }
    
    function isExpired(d) {
        const days = daysUntil(d);
        return days !== null && days < 0;
    }
    
    function getRating(discount) {
        if (!discount || discount <= 0) return {level:'none', label:'Няма данни', stars:0};
        if (discount >= 40) return {level:'excellent', label:'Отлична!', stars:5};
        if (discount >= 30) return {level:'great', label:'Много добра', stars:4};
        if (discount >= 20) return {level:'good', label:'Добра', stars:3};
        if (discount >= 10) return {level:'fair', label:'Приемлива', stars:2};
        return {level:'low', label:'Стандартна', stars:1};
    }
    
    // Create deal card HTML
    function createCard(deal) {
        const isPartial = deal.partial_ownership;
        const hasMarketData = deal.market_avg && deal.discount !== null && !isPartial;
        const r = hasMarketData ? getRating(deal.discount) : {level:'none', label:'', stars:0};
        const days = daysUntil(deal.auction_end);
        const expired = isExpired(deal.auction_end);
        const isUrgent = days !== null && days <= 7 && days >= 0;
        const savings = hasMarketData ? Math.round((deal.market_avg * deal.sqm) - deal.effective_price) : 0;
        
        const icon = TYPE_ICONS[deal.property_type] || '🏛️';
        const typeLabel = deal.property_type_bg || TYPE_LABELS[deal.property_type] || 'Имот';
        
        // Header content based on property type
        let discountBadge = '';
        if (isPartial) {
            discountBadge = `
                <div class="discount-badge partial">
                    <div class="discount-value">⚠️</div>
                    <div class="discount-label">ДРОБНА</div>
                    <div class="discount-amount">Не се сравнява</div>
                </div>`;
        } else if (hasMarketData) {
            discountBadge = `
                <div class="discount-badge">
                    <div class="discount-value">-${Math.round(deal.discount)}%</div>
                    <div class="discount-label">ОТСТЪПКА</div>
                    ${savings > 0 ? '<div class="discount-amount">Спестявате '+fmtPrice(savings)+'</div>' : ''}
                </div>`;
        } else {
            discountBadge = `
                <div class="discount-badge no-data">
                    <div class="discount-value">${fmtPrice(deal.price_per_sqm)}</div>
                    <div class="discount-label">НА М²</div>
                    <div class="discount-amount">Без пазарно сравнение</div>
                </div>`;
        }
        
        // Price comparison section
        let priceSection = '';
        if (hasMarketData) {
            priceSection = `
                <div class="price-section">
                    <div class="price-block price-auction">
                        <div class="price-block-label">Тръжна цена</div>
                        <div class="price-block-value">${fmtPrice(deal.price)}</div>
                        <div class="price-block-sub">${fmtPrice(deal.price_per_sqm)}/m²</div>
                    </div>
                    <div class="price-arrow">→</div>
                    <div class="price-block price-market">
                        <div class="price-block-label">Пазарна</div>
                        <div class="price-block-value">${fmtPrice(deal.market_avg * deal.sqm)}</div>
                        <div class="price-block-sub">${fmtPrice(deal.market_avg)}/m²</div>
                    </div>
                </div>`;
        } else {
            priceSection = `
                <div class="price-section single">
                    <div class="price-block price-auction">
                        <div class="price-block-label">Тръжна цена</div>
                        <div class="price-block-value">${fmtPrice(deal.price)}</div>
                        <div class="price-block-sub">${fmtPrice(deal.price_per_sqm)}/m²</div>
                    </div>
                </div>`;
        }
        
        // Auction status
        let auctionStatus = '';
        if (expired) {
            auctionStatus = '<span class="badge badge-expired">Приключил</span>';
        } else if (isUrgent) {
            auctionStatus = `<span class="badge badge-urgent">⏰ ${days} дни</span>`;
        }
        
        return `<article class="deal-card ${isPartial ? 'deal-partial' : ''} ${expired ? 'deal-expired' : ''}" onclick="window.open('${deal.url}', '_blank')">
            <div class="card-header deal-${r.level}">
                <div class="card-badges">
                    ${auctionStatus}
                    ${isPartial ? '<span class="badge badge-warning">⚠️ '+deal.partial_ownership+'</span>' : ''}
                    <span class="badge badge-type">${icon} ${typeLabel}</span>
                </div>
                ${discountBadge}
            </div>
            <div class="card-body">
                ${priceSection}
                
                <div class="location-section">
                    <span class="location-icon">📍</span>
                    <div class="location-text">
                        <span class="location-city">${deal.city}</span>
                        ${deal.neighborhood ? ', '+deal.neighborhood : ''}
                    </div>
                </div>
                
                <div class="property-info">
                    <div class="info-item">
                        <span class="info-icon">📐</span>
                        <div class="info-content">
                            <span class="info-label">Площ</span>
                            <span class="info-value">${deal.sqm} m²</span>
                        </div>
                    </div>
                    ${deal.rooms ? `
                    <div class="info-item">
                        <span class="info-icon">🚪</span>
                        <div class="info-content">
                            <span class="info-label">Стаи</span>
                            <span class="info-value">${deal.rooms}</span>
                        </div>
                    </div>` : ''}
                    <div class="info-item">
                        <span class="info-icon">📅</span>
                        <div class="info-content">
                            <span class="info-label">Край</span>
                            <span class="info-value">${deal.auction_end ? fmtDate(deal.auction_end) : 'Неизвестен'}</span>
                        </div>
                    </div>
                </div>
            </div>
        </article>`;
    }
    
    // Render deals
    function render(deals) {
        if (deals.length === 0) {
            el.grid.classList.add('hidden');
            el.empty.classList.remove('hidden');
            el.count.textContent = '(0)';
            return;
        }
        el.empty.classList.add('hidden');
        el.grid.classList.remove('hidden');
        el.count.textContent = '(' + deals.length + ')';
        el.grid.innerHTML = deals.map(createCard).join('');
    }
    
    // Update hero stats (only valid apartments)
    function updateHero() {
        const validDeals = allDeals.filter(d => 
            d.discount && d.discount > 0 && !d.partial_ownership
        );
        el.heroTotal.textContent = allDeals.length;
        if (validDeals.length > 0) {
            const avg = validDeals.reduce((s,d) => s + d.discount, 0) / validDeals.length;
            el.heroAvg.textContent = Math.round(avg) + '%';
            el.heroBest.textContent = Math.round(Math.max(...validDeals.map(d => d.discount))) + '%';
        } else {
            el.heroAvg.textContent = '-';
            el.heroBest.textContent = '-';
        }
    }
    
    // Populate city dropdown
    function populateCities() {
        const cities = [...new Set(allDeals.map(d => d.city).filter(Boolean))].sort();
        const val = el.city.value;
        el.city.innerHTML = '<option value="all">Всички градове</option>';
        cities.forEach(c => { 
            const o = document.createElement('option'); 
            o.value = c; 
            o.textContent = c; 
            el.city.appendChild(o); 
        });
        el.city.value = val;
    }
    
    // Filter deals
    function filter() {
        const city = el.city.value;
        const type = el.type.value;
        const minP = parseInt(el.minPrice.value) || 0;
        const maxP = parseInt(el.maxPrice.value) || Infinity;
        const minD = parseInt(el.discount.value) || 0;
        const sort = el.sort.value;
        
        filteredDeals = allDeals.filter(d => {
            // City filter
            if (city !== 'all' && d.city !== city) return false;
            
            // Type filter
            if (type !== 'all') {
                if (type === 'апартамент' && d.property_type !== 'apartment') return false;
                if (type === 'къща' && d.property_type !== 'house') return false;
                if (type === 'гараж' && d.property_type !== 'garage') return false;
            }
            
            // Price filter
            if (d.price < minP || d.price > maxP) return false;
            
            // Discount filter (only for apartments with market data)
            if (minD > 0) {
                if (!d.discount || d.discount < minD || d.partial_ownership) return false;
            }
            
            return true;
        });
        
        // Sort
        filteredDeals.sort((a,b) => {
            if (sort === 'best') {
                const aScore = (a.discount || 0) * (a.partial_ownership ? 0 : 1);
                const bScore = (b.discount || 0) * (b.partial_ownership ? 0 : 1);
                return bScore - aScore;
            }
            if (sort === 'ending') {
                const aDate = a.auction_end ? new Date(a.auction_end) : new Date('2099-01-01');
                const bDate = b.auction_end ? new Date(b.auction_end) : new Date('2099-01-01');
                return aDate - bDate;
            }
            if (sort === 'newest') {
                const aDate = a.auction_end ? new Date(a.auction_end) : new Date('1970-01-01');
                const bDate = b.auction_end ? new Date(b.auction_end) : new Date('1970-01-01');
                return bDate - aDate;
            }
            if (sort === 'price_asc') return a.price - b.price;
            if (sort === 'price_desc') return b.price - a.price;
            return 0;
        });
        
        render(filteredDeals);
    }
    
    // Load deals
    async function load() {
        el.loading.classList.remove('hidden');
        el.error.classList.add('hidden');
        el.grid.classList.add('hidden');
        el.empty.classList.add('hidden');
        
        try {
            const r = await fetch('deals.json');
            if (!r.ok) throw new Error('HTTP ' + r.status);
            const data = await r.json();
            allDeals = Array.isArray(data) ? data : [];
            
            // Filter out expired auctions from display
            allDeals = allDeals.filter(d => {
                if (!d.auction_end) return true;
                const days = daysUntil(d.auction_end);
                return days === null || days >= 0;
            });
            
        } catch(e) {
            console.error('Failed to load deals:', e);
            allDeals = [];
        }
        
        populateCities();
        updateHero();
        el.loading.classList.add('hidden');
        filter();
    }
    
    // Reset filters
    function reset() {
        el.city.value = 'all';
        el.type.value = 'all';
        el.minPrice.value = '';
        el.maxPrice.value = '';
        el.discount.value = '0';
        el.sort.value = 'best';
        filter();
    }
    
    // Debounce helper
    function debounce(fn, ms) {
        let t;
        return (...args) => { clearTimeout(t); t = setTimeout(() => fn(...args), ms); };
    }
    
    // Event listeners
    el.city.addEventListener('change', filter);
    el.type.addEventListener('change', filter);
    el.minPrice.addEventListener('input', debounce(filter, 300));
    el.maxPrice.addEventListener('input', debounce(filter, 300));
    el.discount.addEventListener('change', filter);
    el.sort.addEventListener('change', filter);
    
    document.getElementById('resetFilters')?.addEventListener('click', reset);
    document.getElementById('emptyResetFilters')?.addEventListener('click', reset);
    
    // Global function for reload
    window.loadDeals = load;
    
    // Initial load
    load();
})();
