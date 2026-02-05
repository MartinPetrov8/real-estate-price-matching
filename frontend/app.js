// КЧСИ Deals App - Vanilla JS
(function() {
    'use strict';

    let allDeals = [];
    let filteredDeals = [];

    const elements = {
        loadingState: document.getElementById('loadingState'),
        errorState: document.getElementById('errorState'),
        emptyState: document.getElementById('emptyState'),
        dealsGrid: document.getElementById('dealsGrid'),
        totalDeals: document.getElementById('totalDeals'),
        avgSavings: document.getElementById('avgSavings'),
        activeAuctions: document.getElementById('activeAuctions'),
        cityFilter: document.getElementById('cityFilter'),
        ratingFilter: document.getElementById('ratingFilter'),
        sortBy: document.getElementById('sortBy')
    };

    const BCPEA_URL = 'https://sales.bcpea.org/properties';

    function getRating(discountPct) {
        if (discountPct >= 40) return { stars: 5, label: 'Отлична' };
        if (discountPct >= 30) return { stars: 4, label: 'Много добра' };
        if (discountPct >= 20) return { stars: 3, label: 'Добра' };
        return { stars: 2, label: 'Приемлива' };
    }

    function formatPrice(price) {
        if (!price) return '€?';
        return '€' + price.toLocaleString('de-DE');
    }

    function formatDate(dateStr) {
        if (!dateStr) return 'Неизвестна';
        const date = new Date(dateStr);
        return date.toLocaleDateString('bg-BG', { day: 'numeric', month: 'long', year: 'numeric' });
    }

    function getDaysUntil(dateStr) {
        if (!dateStr) return null;
        const diff = new Date(dateStr) - new Date();
        return Math.ceil(diff / (1000 * 60 * 60 * 24));
    }

    function renderStars(count) {
        return '⭐'.repeat(count);
    }

    function createDealCard(deal) {
        const rating = getRating(deal.discount_pct);
        const daysLeft = getDaysUntil(deal.auction_end);
        const urgentClass = daysLeft !== null && daysLeft <= 7 ? 'deadline-urgent' : '';
        const deadlineText = daysLeft !== null 
            ? (daysLeft < 0 ? 'Приключи' : daysLeft === 0 ? 'Днес!' : `${daysLeft} дни`)
            : '';

        return `
            <article class="deal-card">
                <div class="deal-header deal-${rating.stars}star">
                    <div class="savings-badge">
                        <span class="savings-value">-${deal.discount_pct}%</span>
                        <span class="savings-label">отстъпка</span>
                    </div>
                    <div class="savings-amount">Спестявате ${formatPrice(deal.savings_eur)}</div>
                    <div class="rating-stars" title="${rating.label}">${renderStars(rating.stars)}</div>
                </div>
                <div class="deal-body">
                    <div class="price-row">
                        <div class="price-item">
                            <div class="price-label">Тръжна цена</div>
                            <div class="auction-price">${formatPrice(deal.auction_price)}</div>
                        </div>
                        <div class="price-arrow">→</div>
                        <div class="price-item">
                            <div class="price-label">Пазарна цена</div>
                            <div class="market-price">${formatPrice(deal.market_price)}</div>
                        </div>
                    </div>
                    <div class="property-info">
                        <div class="info-item">
                            <span class="info-icon">📐</span>
                            <span class="info-value">${deal.sqm || '?'} м²</span>
                        </div>
                        <div class="info-item">
                            <span class="info-icon">🚪</span>
                            <span class="info-value">${deal.rooms || '?'} стаи</span>
                        </div>
                        <div class="info-item">
                            <span class="info-icon">🏢</span>
                            <span class="info-value">ет. ${deal.floor || '?'}</span>
                        </div>
                        <div class="info-item">
                            <span class="info-icon">🏠</span>
                            <span class="info-value">${deal.property_type || 'Апартамент'}</span>
                        </div>
                    </div>
                    <div class="location-row">
                        <span class="info-icon">📍</span>
                        <span>${deal.city}${deal.neighborhood ? ', ' + deal.neighborhood : ''}</span>
                    </div>
                    <div class="deadline-row">
                        <span>⏰</span>
                        <span>Край: <span class="${urgentClass}">${formatDate(deal.auction_end)} ${deadlineText ? `(${deadlineText})` : ''}</span></span>
                    </div>
                    <div class="deal-actions">
                        <a href="${BCPEA_URL}/${deal.bcpea_id}" target="_blank" rel="noopener" class="btn btn-primary">Виж търга →</a>
                        ${deal.market_url ? `<a href="${deal.market_url}" target="_blank" rel="noopener" class="btn btn-secondary">Пазарна обява</a>` : ''}
                    </div>
                </div>
            </article>
        `;
    }

    function updateStats(deals) {
        const total = deals.length;
        const avgDiscount = total > 0 ? Math.round(deals.reduce((s, d) => s + d.discount_pct, 0) / total) : 0;
        elements.totalDeals.textContent = total;
        elements.avgSavings.textContent = avgDiscount + '%';
        elements.activeAuctions.textContent = total;
    }

    function renderDeals(deals) {
        if (deals.length === 0) {
            elements.dealsGrid.classList.add('hidden');
            elements.emptyState.classList.remove('hidden');
            updateStats([]);
            return;
        }
        elements.emptyState.classList.add('hidden');
        elements.dealsGrid.classList.remove('hidden');
        elements.dealsGrid.innerHTML = deals.map(createDealCard).join('');
        updateStats(deals);
    }

    function applyFilters() {
        const city = elements.cityFilter.value;
        const rating = elements.ratingFilter.value;
        const sortBy = elements.sortBy.value;

        filteredDeals = allDeals.filter(deal => {
            const cityMatch = city === 'all' || deal.city === city;
            const ratingMatch = rating === 'all' || getRating(deal.discount_pct).stars >= parseInt(rating);
            return cityMatch && ratingMatch;
        });

        filteredDeals.sort((a, b) => {
            if (sortBy === 'savings') return b.discount_pct - a.discount_pct;
            if (sortBy === 'price') return a.auction_price - b.auction_price;
            if (sortBy === 'deadline') return new Date(a.auction_end) - new Date(b.auction_end);
            return 0;
        });

        renderDeals(filteredDeals);
    }

    async function loadDeals() {
        elements.loadingState.classList.remove('hidden');
        elements.errorState.classList.add('hidden');
        elements.dealsGrid.classList.add('hidden');
        elements.emptyState.classList.add('hidden');

        try {
            const response = await fetch('deals.json');
            if (!response.ok) throw new Error('HTTP ' + response.status);
            const data = await response.json();
            allDeals = Array.isArray(data) ? data : (data.deals || data.topDeals || []);
            if (allDeals.length === 0) allDeals = getSampleDeals();
        } catch (e) {
            console.log('Using sample data:', e.message);
            allDeals = getSampleDeals();
        }

        elements.loadingState.classList.add('hidden');
        applyFilters();
    }

    function getSampleDeals() {
        const now = Date.now();
        const day = 24 * 60 * 60 * 1000;
        return [
            { bcpea_id: "12345", city: "София", neighborhood: "Лозенец", sqm: 85, rooms: 3, floor: 4, property_type: "Апартамент", auction_price: 85000, market_price: 150000, discount_pct: 43, savings_eur: 65000, auction_end: new Date(now + 5*day).toISOString(), market_url: "https://www.alo.bg" },
            { bcpea_id: "12346", city: "София", neighborhood: "Младост 1", sqm: 65, rooms: 2, floor: 8, property_type: "Апартамент", auction_price: 72000, market_price: 110000, discount_pct: 35, savings_eur: 38000, auction_end: new Date(now + 12*day).toISOString(), market_url: null },
            { bcpea_id: "12347", city: "Пловдив", neighborhood: "Център", sqm: 110, rooms: 4, floor: 2, property_type: "Апартамент", auction_price: 95000, market_price: 140000, discount_pct: 32, savings_eur: 45000, auction_end: new Date(now + 8*day).toISOString(), market_url: null },
            { bcpea_id: "12348", city: "Варна", neighborhood: "Чайка", sqm: 55, rooms: 1, floor: 5, property_type: "Апартамент", auction_price: 45000, market_price: 72000, discount_pct: 38, savings_eur: 27000, auction_end: new Date(now + 3*day).toISOString(), market_url: "https://www.alo.bg" },
            { bcpea_id: "12349", city: "Бургас", neighborhood: "Лазур", sqm: 75, rooms: 2, floor: 3, property_type: "Апартамент", auction_price: 58000, market_price: 85000, discount_pct: 32, savings_eur: 27000, auction_end: new Date(now + 15*day).toISOString(), market_url: null },
            { bcpea_id: "12350", city: "София", neighborhood: "Дианабад", sqm: 95, rooms: 3, floor: 6, property_type: "Апартамент", auction_price: 105000, market_price: 175000, discount_pct: 40, savings_eur: 70000, auction_end: new Date(now + 6*day).toISOString(), market_url: "https://www.alo.bg" },
            { bcpea_id: "12351", city: "Пловдив", neighborhood: "Тракия", sqm: 68, rooms: 2, floor: 7, property_type: "Апартамент", auction_price: 51000, market_price: 78000, discount_pct: 35, savings_eur: 27000, auction_end: new Date(now + 20*day).toISOString(), market_url: null },
            { bcpea_id: "12352", city: "Варна", neighborhood: "Център", sqm: 120, rooms: 4, floor: 1, property_type: "Апартамент", auction_price: 120000, market_price: 180000, discount_pct: 33, savings_eur: 60000, auction_end: new Date(now + 10*day).toISOString(), market_url: null },
            { bcpea_id: "12353", city: "Бургас", neighborhood: "Меден рудник", sqm: 62, rooms: 2, floor: 4, property_type: "Апартамент", auction_price: 42000, market_price: 65000, discount_pct: 35, savings_eur: 23000, auction_end: new Date(now + 4*day).toISOString(), market_url: null }
        ];
    }

    function init() {
        elements.cityFilter.addEventListener('change', applyFilters);
        elements.ratingFilter.addEventListener('change', applyFilters);
        elements.sortBy.addEventListener('change', applyFilters);
        loadDeals();
    }

    window.loadDeals = loadDeals;
    document.readyState === 'loading' ? document.addEventListener('DOMContentLoaded', init) : init();
})();
