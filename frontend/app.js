(function() {
    'use strict';
    let allDeals = [], filteredDeals = [], countdownIntervals = [];
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
        sort: document.getElementById('sortBy'),
        activeFilters: document.getElementById('activeFilters'),
        modal: document.getElementById('dealModal'),
        modalBody: document.getElementById('modalBody')
    };
    const BCPEA_URL = 'https://sales.bcpea.org/property';
    
    function fmtPrice(p) { return !p ? '€?' : '€' + Math.round(p).toLocaleString('de-DE'); }
    function fmtSqm(p, s) { return !p || !s ? '€?/m²' : '€' + Math.round(p/s).toLocaleString('de-DE') + '/m²'; }
    function fmtDate(d) { return !d ? 'Неизвестна' : new Date(d).toLocaleDateString('bg-BG', {day:'numeric', month:'short'}); }
    function daysUntil(d) { return !d ? null : Math.ceil((new Date(d) - new Date()) / 86400000); }
    function isNew(d) { const days = daysUntil(d); return days !== null && days > 20; }
    function getRating(pct) {
        if (pct >= 50) return {level:'excellent', label:'Отлична!', score:100, stars:5};
        if (pct >= 40) return {level:'great', label:'Много добра', score:90, stars:4};
        if (pct >= 30) return {level:'good', label:'Добра', score:75, stars:3};
        if (pct >= 20) return {level:'fair', label:'Приемлива', score:60, stars:2};
        return {level:'low', label:'Стандартна', score:40, stars:1};
    }
    function propIcon(t) {
        const types = {'апартамент':'🏢','къща':'🏠','гараж':'🚗','магазин':'🏪','земя':'🌾'};
        return types[t?.toLowerCase()] || '🏢';
    }
    function startCountdown(id, endDate) {
        const el = document.getElementById(id);
        if (!el || !endDate) return;
        const end = new Date(endDate);
        function upd() {
            const diff = end - new Date();
            if (diff <= 0) { el.textContent = 'Приключи'; return; }
            const d = Math.floor(diff/86400000), h = Math.floor((diff%86400000)/3600000), m = Math.floor((diff%3600000)/60000);
            el.textContent = d > 0 ? d+'д '+h+'ч' : h > 0 ? h+'ч '+m+'м' : m+' мин';
            if (d < 3) el.closest('.countdown-section')?.classList.add('countdown-urgent');
        }
        upd();
        countdownIntervals.push(setInterval(upd, 60000));
    }
    function createCard(deal) {
        const r = getRating(deal.discount_pct), days = daysUntil(deal.auction_end);
        const isNew = days !== null && days > 20, isUrgent = days !== null && days <= 5 && days >= 0;
        const icon = propIcon(deal.property_type), cid = 'cd-'+deal.bcpea_id;
        const barW = Math.max(10, Math.min(90, (deal.auction_price/deal.market_price)*100));
        return \`<article class="deal-card">
            <div class="card-header deal-\${r.level}">
                <div class="card-badges">
                    \${isNew ? '<span class="badge badge-new">✨ НОВО</span>' : ''}
                    \${isUrgent ? '<span class="badge badge-urgent">⏰ СКОРО</span>' : ''}
                    <span class="badge badge-type">\${icon} \${deal.property_type || 'Апартамент'}</span>
                </div>
                <div class="discount-badge">
                    <div class="discount-value">-\${Math.round(deal.discount_pct)}%</div>
                    <div class="discount-label">ОТСТЪПКА</div>
                    <div class="discount-amount">Спестявате \${fmtPrice(deal.savings_eur)}</div>
                </div>
                <div class="price-comparison-bar">
                    <div class="price-bar-track"><div class="price-bar-fill" style="width:\${barW}%"></div></div>
                    <div class="price-bar-labels"><span>Тръжна цена</span><span>Пазарна цена</span></div>
                </div>
            </div>
            <div class="card-body">
                <div class="price-section">
                    <div class="price-block price-auction">
                        <div class="price-block-label">Тръжна цена</div>
                        <div class="price-block-value">\${fmtPrice(deal.auction_price)}</div>
                        <div class="price-block-sub">\${fmtSqm(deal.auction_price, deal.sqm)}</div>
                    </div>
                    <div class="price-arrow">→</div>
                    <div class="price-block price-market">
                        <div class="price-block-label">Пазарна цена</div>
                        <div class="price-block-value">\${fmtPrice(deal.market_price)}</div>
                        <div class="price-block-sub">\${fmtSqm(deal.market_price, deal.sqm)}</div>
                    </div>
                </div>
                <div class="deal-score">
                    <span class="score-label">Оценка:</span>
                    <div class="score-bar"><div class="score-fill \${r.level}" style="width:\${r.score}%"></div></div>
                    <span class="score-value">\${r.stars}★</span>
                </div>
                <div class="property-info">
                    <div class="info-item"><span class="info-icon">📐</span><div class="info-content"><span class="info-label">Площ</span><span class="info-value">\${deal.sqm ? deal.sqm+' м²' : 'N/A'}</span></div></div>
                    <div class="info-item"><span class="info-icon">🚪</span><div class="info-content"><span class="info-label">Стаи</span><span class="info-value">\${deal.rooms || 'N/A'}</span></div></div>
                    <div class="info-item"><span class="info-icon">🏢</span><div class="info-content"><span class="info-label">Етаж</span><span class="info-value">\${deal.floor || 'N/A'}</span></div></div>
                    <div class="info-item"><span class="info-icon">📊</span><div class="info-content"><span class="info-label">Сравнения</span><span class="info-value">\${deal.comparables_count || 0} имота</span></div></div>
                </div>
                <div class="location-section">
                    <span class="location-icon">📍</span>
                    <span class="location-text"><span class="location-city">\${deal.city}</span>\${deal.neighborhood && deal.neighborhood !== 'Неизвестен' ? ', '+deal.neighborhood : ''}</span>
                </div>
                <div class="countdown-section">
                    <span class="countdown-icon">⏰</span>
                    <span class="countdown-text">Край на търга: <span class="countdown-time" id="\${cid}"></span></span>
                </div>
                <div class="why-deal">
                    <button class="why-deal-toggle" onclick="toggleWhy('\${deal.bcpea_id}')">
                        <span>💡 Защо тази сделка?</span><span id="tgl-\${deal.bcpea_id}">▼</span>
                    </button>
                    <div class="why-deal-content" id="why-\${deal.bcpea_id}">
                        <div class="why-deal-item"><span class="why-deal-icon">💰</span><span>Цената е с <strong>\${Math.round(deal.discount_pct)}%</strong> под пазарната ниво</span></div>
                        <div class="why-deal-item"><span class="why-deal-icon">📏</span><span>€/м²: <strong>\${fmtSqm(deal.auction_price, deal.sqm)}</strong> при пазарни <strong>\${fmtSqm(deal.market_price, deal.sqm)}</strong></span></div>
                        \${deal.neighborhood_range ? \`<div class="why-deal-item"><span class="why-deal-icon">🏘️</span><span>Ценови диапазон в района: \${deal.neighborhood_range}</span></div>\` : ''}
                        <div class="why-deal-item"><span class="why-deal-icon">🔍</span><span>Базирано на \${deal.comparables_count || 0} сравними обяви</span></div>
                    </div>
                </div>
                <div class="card-actions">
                    <a href="\${BCPEA_URL}/\${deal.bcpea_id}" target="_blank" class="btn btn-primary">Виж търга →</a>
                    <button class="btn btn-secondary" onclick="showModal('\${deal.bcpea_id}')">Детайли</button>
                </div>
            </div>
        </article>\`;
    }
    function render(deals) {
        countdownIntervals.forEach(clearInterval);
        countdownIntervals = [];
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
        deals.forEach(d => startCountdown('cd-'+d.bcpea_id, d.auction_end));
    }
    function updateHero() {
        el.heroTotal.textContent = allDeals.length;
        if (allDeals.length > 0) {
            const avg = allDeals.reduce((s,d) => s+d.discount_pct, 0) / allDeals.length;
            el.heroAvg.textContent = Math.round(avg) + '%';
            el.heroBest.textContent = Math.max(...allDeals.map(d => d.discount_pct)) + '%';
        }
    }
    function populateCities() {
        const cities = [...new Set(allDeals.map(d => d.city).filter(Boolean))].sort();
        const val = el.city.value;
        el.city.innerHTML = '<option value="all">Всички градове</option>';
        cities.forEach(c => { const o = document.createElement('option'); o.value = c; o.textContent = c; el.city.appendChild(o); });
        el.city.value = val;
    }
    function getActive() {
        const f = [];
        if (el.city.value !== 'all') f.push({type:'city', label:el.city.value});
        if (el.type.value !== 'all') f.push({type:'type', label:el.type.value});
        if (el.minPrice.value) f.push({type:'minPrice', label:'От '+fmtPrice(parseInt(el.minPrice.value))});
        if (el.maxPrice.value) f.push({type:'maxPrice', label:'До '+fmtPrice(parseInt(el.maxPrice.value))});
        if (parseInt(el.discount.value) > 0) f.push({type:'discount', label:el.discount.value+'%+ отстъпка'});
        return f;
    }
    function renderActive() {
        const f = getActive();
        el.activeFilters.innerHTML = f.length ? f.map(x => \`<span class="active-filter">\${x.label}<button onclick="rmFilter('\${x.type}')">✕</button></span>\`).join('') : '';
    }
    window.rmFilter = function(t) {
        if (t === 'city') el.city.value = 'all';
        if (t === 'type') el.type.value = 'all';
        if (t === 'minPrice') el.minPrice.value = '';
        if (t === 'maxPrice') el.maxPrice.value = '';
        if (t === 'discount') el.discount.value = '0';
        filter();
    };
    function filter() {
        const city = el.city.value, type = el.type.value;
        const minP = parseInt(el.minPrice.value) || 0, maxP = parseInt(el.maxPrice.value) || Infinity;
        const minD = parseInt(el.discount.value) || 0;
        const pill = document.querySelector('.pill-active')?.dataset.filter || 'all';
        filteredDeals = allDeals.filter(d => {
            if (city !== 'all' && d.city !== city) return false;
            if (type !== 'all' && d.property_type?.toLowerCase() !== type.toLowerCase()) return false;
            if (d.auction_price < minP || d.auction_price > maxP) return false;
            if (d.discount_pct < minD) return false;
            if (pill === 'new' && !isNew(d.auction_end)) return false;
            if (pill === 'ending') { const days = daysUntil(d.auction_end); if (days === null || days > 7) return false; }
            if (pill === 'best' && d.discount_pct < 40) return false;
            if (pill === 'sofia' && d.city !== 'София') return false;
            return true;
        });
        const sort = el.sort.value;
        filteredDeals.sort((a,b) => {
            if (sort === 'best') return (b.discount_pct * Math.log(b.savings_eur+1)) - (a.discount_pct * Math.log(a.savings_eur+1));
            if (sort === 'ending') return new Date(a.auction_end) - new Date(b.auction_end);
            if (sort === 'newest') return new Date(b.auction_end) - new Date(a.auction_end);
            if (sort === 'price_asc') return a.auction_price - b.auction_price;
            if (sort === 'price_desc') return b.auction_price - a.auction_price;
            return 0;
        });
        render(filteredDeals);
        renderActive();
    }
    async function load() {
        el.loading.classList.remove('hidden');
        el.error.classList.add('hidden');
        el.grid.classList.add('hidden');
        el.empty.classList.add('hidden');
        try {
            const r = await fetch('deals.json');
            if (!r.ok) throw new Error('HTTP '+r.status);
            const data = await r.json();
            allDeals = Array.isArray(data) ? data : (data.deals || []);
        } catch(e) {
            allDeals = [];
        }
        populateCities();
        updateHero();
        el.loading.classList.add('hidden');
        filter();
    }
    window.toggleWhy = function(id) {
        const c = document.getElementById('why-'+id), t = document.getElementById('tgl-'+id);
        if (c.classList.contains('show')) { c.classList.remove('show'); t.textContent = '▼'; }
        else { c.classList.add('show'); t.textContent = '▲'; }
    };
    window.showModal = function(id) {
        const d = allDeals.find(x => x.bcpea_id === id);
        if (!d) return;
        const r = getRating(d.discount_pct), days = daysUntil(d.auction_end);
        el.modalBody.innerHTML = \`<div style="padding:32px;">
            <div class="card-header deal-\${r.level}" style="margin:-32px -32px 24px -32px;padding:32px;">
                <div class="discount-badge">
                    <div class="discount-value">-\${Math.round(d.discount_pct)}%</div>
                    <div class="discount-label">ОТСТЪПКА</div>
                </div>
            </div>
            <h2 style="font-size:24px;font-weight:700;margin-bottom:8px;">\${d.property_type || 'Имот'} в \${d.city}</h2>
            <p style="color:var(--gray-500);margin-bottom:24px;">\${d.neighborhood && d.neighborhood !== 'Неизвестен' ? d.neighborhood : ''}</p>
            <div style="display:grid;grid-template-columns:1fr 1fr;gap:16px;margin-bottom:24px;">
                <div style="background:var(--success-light);padding:16px;border-radius:var(--radius);">
                    <div style="font-size:12px;color:var(--gray-500);text-transform:uppercase;font-weight:600;">Тръжна цена</div>
                    <div style="font-size:24px;font-weight:700;color:var(--success);">\${fmtPrice(d.auction_price)}</div>
                    <div style="font-size:14px;color:var(--gray-600);">\${fmtSqm(d.auction_price, d.sqm)}</div>
                </div>
                <div style="background:var(--gray-100);padding:16px;border-radius:var(--radius);">
                    <div style="font-size:12px;color:var(--gray-500);text-transform:uppercase;font-weight:600;">Пазарна цена</div>
                    <div style="font-size:20px;font-weight:600;color:var(--gray-500);text-decoration:line-through;">\${fmtPrice(d.market_price)}</div>
                    <div style="font-size:14px;color:var(--gray-600);">\${fmtSqm(d.market_price, d.sqm)}</div>
                </div>
            </div>
            <div style="background:var(--info-light);padding:20px;border-radius:var(--radius);margin-bottom:24px;">
                <h4 style="font-size:14px;font-weight:600;margin-bottom:12px;">💡 Анализ на сделката</h4>
                <ul style="list-style:none;padding:0;margin:0;font-size:14px;line-height:1.8;">
                    <li>✓ Цената е с <strong>\${Math.round(d.discount_pct)}%</strong> под пазарната ниво</li>
                    <li>✓ Спестявате <strong>\${fmtPrice(d.savings_eur)}</strong> спрямо пазарната цена</li>
                    \${d.neighborhood_range ? \`<li>✓ Ценови диапазон в района: \${d.neighborhood_range}</li>\` : ''}
                    <li>✓ Базирано на \${d.comparables_count || 0} сравними обяви</li>
                </ul>
            </div>
            <div style="margin-bottom:24px;">
                <div style="font-size:12px;color:var(--gray-500);text-transform:uppercase;font-weight:600;margin-bottom:8px;">Край на търга</div>
                <div style="font-size:18px;font-weight:600;color:\${days !== null && days <= 3 ? 'var(--danger)' : 'var(--gray-700)'};">\${fmtDate(d.auction_end)} \${days !== null ? '('+days+' дни)' : ''}</div>
            </div>
            <div style="display:flex;gap:12px;">
                <a href="\${BCPEA_URL}/\${d.bcpea_id}" target="_blank" class="btn btn-primary" style="flex:1;justify-content:center;">Виж на КЧСИ →</a>
                <button onclick="closeModal()" class="btn btn-outline">Затвори</button>
            </div>
        </div>\`;
        el.modal.classList.remove('hidden');
        document.body.style.overflow = 'hidden';
    };
    window.closeModal = function() {
        el.modal.classList.add('hidden');
        document.body.style.overflow = '';
    };
    window.loadDeals = load;
    function reset() {
        el.city.value = 'all'; el.type.value = 'all';
        el.minPrice.value = ''; el.maxPrice.value = '';
        el.discount.value = '40'; el.sort.value = 'best';
        document.querySelectorAll('.pill').forEach(p => p.classList.remove('pill-active'));
        document.querySelector('[data-filter="all"]').classList.add('pill-active');
        filter();
    }
    function debounce(fn, ms) {
        let t;
        return (...args) => { clearTimeout(t); t = setTimeout(() => fn(...args), ms); };
    }
    document.querySelectorAll('.pill').forEach(p => {
        p.addEventListener('click', () => {
            document.querySelectorAll('.pill').forEach(x => x.classList.remove('pill-active'));
            p.classList.add('pill-active');
            filter();
        });
    });
    el.city.addEventListener('change', filter);
    el.type.addEventListener('change', filter);
    el.minPrice.addEventListener('input', debounce(filter, 300));
    el.maxPrice.addEventListener('input', debounce(filter, 300));
    el.discount.addEventListener('change', filter);
    el.sort.addEventListener('change', filter);
    document.getElementById('resetFilters').addEventListener('click', reset);
    document.getElementById('emptyResetFilters').addEventListener('click', reset);
    document.addEventListener('keydown', e => { if (e.key === 'Escape') closeModal(); });
    load();
})();
