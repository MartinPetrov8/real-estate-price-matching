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
        return Math.ceil((new Date(d) - new Date()) / 86400000); 
    }
    
    function getRating(pct) {
        if (pct >= 40) return {level:'excellent', label:'Отлична!', stars:5};
        if (pct >= 30) return {level:'great', label:'Много добра', stars:4};
        if (pct >= 20) return {level:'good', label:'Добра', stars:3};
        if (pct >= 10) return {level:'fair', label:'Приемлива', stars:2};
        return {level:'low', label:'Стандартна', stars:1};
    }
    
    // Create deal card HTML
    function createCard(deal) {
        const r = getRating(deal.discount);
        const days = daysUntil(deal.auction_end);
        const isUrgent = days !== null && days <= 7 && days >= 0;
        const savings = Math.round((deal.market_avg * deal.sqm) - deal.effective_price);
        
        return `<article class="deal-card" onclick="window.open('${deal.url}', '_blank')">
            <div class="card-header deal-${r.level}">
                <div class="card-badges">
                    ${isUrgent ? '<span class="badge badge-urgent">⏰ '+days+' дни</span>' : ''}
                    ${deal.partial_ownership ? '<span class="badge badge-warning">⚠️ '+deal.partial_ownership+'</span>' : ''}
                    <span class="badge badge-type">🏢 ${deal.property_type || 'Апартамент'}</span>
                </div>
                <div class="discount-badge">
                    <div class="discount-value">-${Math.round(deal.discount)}%</div>
                    <div class="discount-label">ОТСТЪПКА</div>
                    ${savings > 0 ? '<div class="discount-amount">Спестявате '+fmtPrice(savings)+'</div>' : ''}
                </div>
            </div>
            <div class="card-body">
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
                </div>
                
                <div class="location-section">
                    <span class="location-icon">📍</span>
                    <div class="location-text">
                        <span class="location-city">${deal.city}</span>
                        ${deal.neighborhood ? ', '+deal.neighborhood : ''}
                        <br><small>${deal.address || ''}</small>
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
                    <div class="info-item">
                        <span class="info-icon">⭐</span>
                        <div class="info-content">
                            <span class="info-label">Оценка</span>
                            <span class="info-value">${'★'.repeat(r.stars)}${'☆'.repeat(5-r.stars)}</span>
                        </div>
                    </div>
                </div>
                
                <div class="countdown-section ${isUrgent ? 'countdown-urgent' : ''}">
                    <span class="countdown-icon">📅</span>
                    <div class="countdown-text">
                        Търг: ${fmtDate(deal.auction_start)} - ${fmtDate(deal.auction_end)}
                        ${days !== null ? ' ('+days+' дни)' : ''}
                    </div>
                </div>
                
                <div class="card-actions">
                    <a href="${deal.url}" target="_blank" class="btn btn-primary">Виж в КЧСИ →</a>
                </div>
            </div>
        </article>`;
    }
    
    // Render deals
    function render() {
        if (!el.grid) return;
        
        el.grid.innerHTML = filteredDeals.map(createCard).join('');
        el.grid.classList.remove('hidden');
        
        if (el.count) el.count.textContent = filteredDeals.length;
        if (el.loading) el.loading.classList.add('hidden');
        if (el.empty) el.empty.classList.toggle('hidden', filteredDeals.length > 0);
    }
    
    // Update hero stats
    function updateStats() {
        if (el.heroTotal) el.heroTotal.textContent = allDeals.length;
        if (el.heroAvg && allDeals.length) {
            const avg = allDeals.reduce((s,d) => s + d.discount, 0) / allDeals.length;
            el.heroAvg.textContent = Math.round(avg) + '%';
        }
        if (el.heroBest && allDeals.length) {
            const best = Math.max(...allDeals.map(d => d.discount));
            el.heroBest.textContent = Math.round(best) + '%';
        }
    }
    
    // Filter deals
    function applyFilters() {
        filteredDeals = allDeals.filter(d => {
            if (el.city?.value && el.city.value !== 'all' && d.city !== el.city.value) return false;
            if (el.minPrice?.value && d.price < +el.minPrice.value) return false;
            if (el.maxPrice?.value && d.price > +el.maxPrice.value) return false;
            if (el.discount?.value && d.discount < +el.discount.value) return false;
            return true;
        });
        
        // Sort
        const sort = el.sort?.value || 'best';
        filteredDeals.sort((a,b) => {
            if (sort === 'best') return b.discount - a.discount;
            if (sort === 'price_asc') return a.price - b.price;
            if (sort === 'price_desc') return b.price - a.price;
            if (sort === 'ending') return new Date(a.auction_end) - new Date(b.auction_end);
            return 0;
        });
        
        render();
    }
    
    // Populate city filter
    function populateCities() {
        if (!el.city) return;
        const cities = [...new Set(allDeals.map(d => d.city))].sort();
        cities.forEach(c => {
            const opt = document.createElement('option');
            opt.value = c;
            opt.textContent = c;
            el.city.appendChild(opt);
        });
    }
    
    // Load deals
    async function loadDeals() {
        try {
            if (el.loading) el.loading.classList.remove('hidden');
            if (el.error) el.error.classList.add('hidden');
            
            const res = await fetch('deals.json');
            if (!res.ok) throw new Error('Failed to load deals');
            
            allDeals = await res.json();
            filteredDeals = [...allDeals];
            
            populateCities();
            updateStats();
            applyFilters();
            
        } catch (err) {
            console.error('Error loading deals:', err);
            if (el.loading) el.loading.classList.add('hidden');
            if (el.error) el.error.classList.remove('hidden');
        }
    }
    
    // Setup event listeners
    function setupListeners() {
        [el.city, el.type, el.minPrice, el.maxPrice, el.discount, el.sort].forEach(e => {
            if (e) e.addEventListener('change', applyFilters);
        });
        
        document.getElementById('resetFilters')?.addEventListener('click', () => {
            [el.city, el.type, el.minPrice, el.maxPrice].forEach(e => { if(e) e.value = ''; });
            if (el.discount) el.discount.value = '0';
            if (el.sort) el.sort.value = 'best';
            applyFilters();
        });
    }
    
    // Init
    document.addEventListener('DOMContentLoaded', () => {
        setupListeners();
        loadDeals();
    });
})();
