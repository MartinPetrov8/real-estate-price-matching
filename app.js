(function() {
    'use strict';
    let allDeals = [], filteredDeals = [], countdownIntervals = [];
    const DEALS_PER_PAGE = 12;
    // XSS protection: escape HTML in user-controlled data
    const escHtml = (s) => s ? String(s).replace(/[&<>"']/g, m => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[m])) : '';
    let currentPage = 1;
    let displayedDeals = 0;
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
        loadMore: document.getElementById('loadMoreBtn'),
        backToTop: document.getElementById('backToTop'),
        modalBody: document.getElementById('modalBody')
    };
    const BCPEA_URL = 'https://sales.bcpea.org/properties';

    // Property type translations
    const propTypeBg = {
        'apartment': 'Апартамент',
        'house': 'Къща',
        'garage': 'Гараж',
        'commercial': 'Търговски',
        'land': 'Земя',
        'other': 'Друг',
        'апартамент': 'Апартамент',
        'къща': 'Къща',
        'гараж': 'Гараж',
        'магазин': 'Магазин',
        'земя': 'Земя'
    };
    function translatePropType(t) { return propTypeBg[t?.toLowerCase()] || t || 'Имот'; }
    
    function fmtPrice(p) { return !p ? '€?' : '€' + Math.round(p).toLocaleString('bg-BG'); }
    function fmtSqm(p, s) { return !p || !s ? '€?/m²' : '€' + Math.round(p/s).toLocaleString('bg-BG') + '/m²'; }
    function parseDate(d) {
        if (!d) return null;
        // Handle DD.MM.YYYY format (Bulgarian)
        const match = d.match(/^(\d{2})\.(\d{2})\.(\d{4})$/);
        if (match) {
            return new Date(parseInt(match[3]), parseInt(match[2]) - 1, parseInt(match[1]));
        }
        // Handle YYYY-MM-DD format (ISO)
        const isoMatch = d.match(/^(\d{4})-(\d{2})-(\d{2})$/);
        if (isoMatch) {
            return new Date(parseInt(isoMatch[1]), parseInt(isoMatch[2]) - 1, parseInt(isoMatch[3]));
        }
        // Fallback to native parsing
        const date = new Date(d);
        return isNaN(date.getTime()) ? null : date;
    }
    function fmtDate(d) { 
        if (!d) return 'Неизвестна';
        const date = parseDate(d);
        if (!date) return 'Неизвестна';
        return date.toLocaleDateString('bg-BG', {day:'numeric', month:'short', year:'numeric'});
    }
    function daysUntil(d) { 
        if (!d) return null;
        const date = parseDate(d);
        if (!date) return null;
        return Math.ceil((date - new Date()) / 86400000);
    }
    
    // A deal is "new" if auction ends far in future (likely newly listed)
    function isNew(d) { const days = daysUntil(d); return days !== null && days > 20; }
    
    function getRating(pct) {
        // Handle negative discounts (bad deals)
        if (pct < 0) return {level:'bad', label:'Слаба', score:20, stars:1};
        if (pct >= 50) return {level:'excellent', label:'Отлична', score:100, stars:5};
        if (pct >= 40) return {level:'great', label:'Много добра', score:90, stars:4};
        if (pct >= 30) return {level:'good', label:'Добра', score:75, stars:3};
        if (pct >= 20) return {level:'fair', label:'Приемлива', score:60, stars:2};
        return {level:'low', label:'Стандартна', score:40, stars:1};
    }
    
    function propIcon(t) {
        const types = {'апартамент':'🏢','къща':'🏠','гараж':'🚗','магазин':'🏪','земя':'🌾','apartment':'🏢'};
        return types[t?.toLowerCase()] || '🏢';
    }
    
    function startCountdown(id, endDate) {
        const el = document.getElementById(id);
        if (!el || !endDate) return;
        const end = parseDate(endDate);
        if (!end) { el.textContent = 'Неизвестна'; return; }
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
        // Normalize deal data - support both old and new field names
        const bcpeaId = deal.bcpea_id || deal.id;
        const auctionPrice = deal.auction_price || deal.effective_price || deal.price || 0;
        const comparables = deal.comparables_count || deal.market_sample_size || 0;
        const comparablesLevel = deal.comparables_level || null; // 'hood', 'city_size', 'city', null
        const hasReliableMarketData = comparables > 0 && deal.market_price;
        const marketPrice = hasReliableMarketData ? deal.market_price : null;
        const discountPct = deal.discount_pct !== undefined ? deal.discount_pct : (deal.discount || 0);
        const savingsEur = deal.savings_eur !== undefined ? deal.savings_eur : (marketPrice ? Math.max(0, marketPrice - auctionPrice) : 0);
        const pricePerSqm = deal.price_per_sqm || (deal.auction_price && deal.sqm ? deal.auction_price / deal.sqm : 0);
        const auctionEnd = deal.auction_end || null;
        const city = escHtml(deal.city || 'Неизвестен');
        const neighborhood = escHtml(deal.neighborhood || 'Неизвестен');
        const sqm = deal.sqm;
        const buildingSqm = deal.building_sqm;
        const plotSqm = deal.plot_sqm;
        const isHouse = deal.property_type === 'къща';
        const floor = deal.floor;
        const propertyType = escHtml(deal.property_type || 'апартамент');
        const propertyTypeBg = escHtml(deal.property_type_bg || '');
        const roomType = (deal.property_type_bg || '').match(/(едностаен|двустаен|тристаен|многостаен|четиристаен)/i)?.[1] || null;
        const roomTypeDisplay = roomType ? escHtml(roomType.charAt(0).toUpperCase() + roomType.slice(1)) : null;
        const isPartialOwnership = deal.is_partial_ownership || false;
        // comparables already defined above
        const partialOwnership = deal.partial_ownership;
        const rawUrl = deal.url || `${BCPEA_URL}/${bcpeaId}`;
        const url = rawUrl.startsWith('https://sales.bcpea.org/') ? escHtml(rawUrl) : escHtml(`${BCPEA_URL}/${bcpeaId}`);
        
        const r = getRating(discountPct), days = daysUntil(auctionEnd);
        const isNewFlag = days !== null && days > 20;
        const isUrgent = days !== null && days <= 5 && days >= 0;
        const icon = propIcon(propertyType);
        const cid = 'cd-'+bcpeaId;
        const barW = Math.max(10, Math.min(90, (auctionPrice/marketPrice)*100));
        
        // Data reliability warnings
        const hasDataIssues = comparables === 0 || discountPct < 0;
        const dataWarning = hasDataIssues ? `
            <div class="data-warning">
                <span class="warning-icon">⚠️</span>
                <span class="warning-text">${comparables === 0 ? 'Няма достатъчно данни за сравнение' : 'Тръжната цена е по-висока от пазарната'}</span>
            </div>
        ` : '';
        
        // Partial ownership warning
        const ownershipWarning = partialOwnership ? `
            <div class="ownership-warning">
                <span class="warning-icon">⚠</span>
                <span class="warning-text">Частна собственост - проверете дела</span>
            </div>
        ` : '';
        
        return `<article class="deal-card">
            <div class="card-header deal-${r.level}">
                <div class="card-badges">
                    ${isNewFlag ? '<span class="badge badge-new">НОВО</span>' : ''}
                    ${isUrgent ? '<span class="badge badge-urgent">ИЗТИЧАЩ</span>' : ''}
                    <span class="badge badge-type">${translatePropType(propertyType)}</span>${isPartialOwnership ? '<span class="badge badge-warning" title="Дробна собственост - цените не са съпоставими">⚠ Дробна собственост</span>' : ''}
                </div>
                <div class="discount-badge">
                    <div class="discount-value">${discountPct >= 0 ? '-' : '+'}${Math.abs(Math.round(discountPct))}%</div>
                    <div class="discount-label">${discountPct >= 0 ? 'ОТСТЪПКА' : 'НАД ПАЗАРНАТА'}</div>
                    ${discountPct >= 0 ? `<div class="discount-amount">Спестявате ${fmtPrice(savingsEur)}</div>` : `<div class="discount-amount">Пазарна: ${fmtPrice(marketPrice)}</div>`}
                </div>
                <div class="price-comparison-bar">
                    <div class="price-bar-track"><div class="price-bar-fill" style="width:${barW}%"></div></div>
                    <div class="price-bar-labels"><span>Тръжна цена</span><span>Пазарна цена →</span></div>
                </div>
            </div>
            <div class="card-body">
                ${ownershipWarning}
                ${dataWarning}
                ${marketPrice ? `
                <div class="price-section">
                    <div class="price-block price-market">
                        <div class="price-block-label">Пазарна цена</div>
                        <div class="price-block-sqm">${fmtSqm(marketPrice, sqm)}</div>
                        <div class="price-block-total">${fmtPrice(marketPrice)}</div>
                    </div>
                    <div class="price-arrow">→</div>
                    <div class="price-block price-auction">
                        <div class="price-block-label">Тръжна цена</div>
                        <div class="price-block-sqm">${fmtSqm(auctionPrice, sqm)}</div>
                        <div class="price-block-total">${fmtPrice(auctionPrice)}</div>
                    </div>
                </div>
                ` : `
                <div class="price-section">
                    <div class="price-block price-auction" style="flex:1">
                        <div class="price-block-label">Тръжна цена</div>
                        <div class="price-block-sqm">${fmtSqm(auctionPrice, sqm)}</div>
                        <div class="price-block-total">${fmtPrice(auctionPrice)}</div>
                    </div>
                </div>
                <div style="background:var(--warning-light, #FFF8E1);padding:8px 12px;border-radius:var(--radius);margin-top:8px;font-size:13px;color:var(--warning, #F57C00);">
                    ⚠️ Няма данни за пазарна цена
                </div>
                `}
                <div class="deal-score">
                    <div class="score-bar"><div class="score-fill ${r.level}" style="width:${r.score}%"></div></div>
                    <span class="score-value">${r.stars}★</span>
                </div>
                <div class="property-info">
                    <div class="info-item"><div class="info-content"><span class="info-label">Площ</span><span class="info-value">${isHouse && buildingSqm ? buildingSqm+' м² (сграда)' : (sqm ? sqm+' м²' : 'N/A')}</span></div></div>
                    ${isHouse && plotSqm ? '<div class="info-item"><div class="info-content"><span class="info-label">Парцел</span><span class="info-value">'+plotSqm+' м²</span></div></div>' : ''}
                    <div class="info-item"><div class="info-content"><span class="info-label">Етаж</span><span class="info-value">${floor || 'N/A'}</span></div></div>
                    ${roomTypeDisplay ? '<div class="info-item"><div class="info-content"><span class="info-label">Тип</span><span class="info-value">'+roomTypeDisplay+'</span></div></div>' : ''}
                    <div class="info-item"><div class="info-content"><span class="info-label">Сравнения</span><span class="info-value">${comparables > 0 ? (comparables + ' имота' + (comparablesLevel === 'hood' ? '' : ' (в ' + city + ')')) : 'Няма данни'}</span></div></div>
                </div>
                <div class="location-section">
                    <svg class="location-icon" xmlns="http://www.w3.org/2000/svg" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M20 10c0 6-8 12-8 12S4 16 4 10a8 8 0 0 1 16 0z"/><circle cx="12" cy="10" r="3"/></svg>
                    <span class="location-text"><span class="location-city">${city}</span>${neighborhood && neighborhood !== 'Неизвестен' ? ', '+neighborhood : ''}</span>
                </div>
                <div class="countdown-section">
                    <svg class="countdown-icon" xmlns="http://www.w3.org/2000/svg" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="12" r="10"/><polyline points="12 6 12 12 16 14"/></svg>
                    <span class="countdown-text">Край на търга: <span class="countdown-time" id="${cid}"></span></span>
                </div>
                <div class="why-deal">
                    <button class="why-deal-toggle" onclick="toggleWhy('${bcpeaId}')">
                        <span>Защо тази сделка?</span><span id="tgl-${bcpeaId}" class="why-deal-chevron">▼</span>
                    </button>
                    <div class="why-deal-content" id="why-${bcpeaId}">
                        ${discountPct >= 0 ? 
                            `<div class="why-deal-item"><span>Цената е с <strong>${Math.round(discountPct)}%</strong> под пазарното ниво</span></div>` :
                            `<div class="why-deal-item"><span>⚠ Цената е с <strong>${Math.abs(Math.round(discountPct))}%</strong> над пазарното ниво</span></div>`
                        }
                        <div class="why-deal-item"><span>€/м²: <strong>${fmtSqm(auctionPrice, sqm)}</strong> при пазарни <strong>${fmtSqm(marketPrice, sqm)}</strong></span></div>
                        ${deal.neighborhood_range ? `<div class="why-deal-item"><span>Ценови диапазон в района: ${escHtml(deal.neighborhood_range)}</span></div>` : ''}
                        ${comparables > 0 ? `<div class="why-deal-item"><span>Базирано на ${comparables} сравними обяви</span></div>` : '<div class="why-deal-item"><span>⚠ Няма достатъчно сравними обяви за надеждна оценка</span></div>'}
                    </div>
                </div>
                <div class="card-actions">
                    <a href="${url}" target="_blank" class="btn btn-primary">Виж търга →</a>
                    <button class="btn btn-secondary" onclick="showModal('${bcpeaId}')">Детайли</button>
                </div>
            </div>
        </article>`;
    }
    
    function render(deals, append = false) {
        countdownIntervals.forEach(clearInterval);
        countdownIntervals = [];
        
        if (deals.length === 0) {
            el.grid.classList.add('hidden');
            el.empty.classList.remove('hidden');
            el.count.textContent = '(0)';
            if (el.loadMore) el.loadMore.classList.add('hidden');
            return;
        }
        
        el.empty.classList.add('hidden');
        el.grid.classList.remove('hidden');
        el.count.textContent = '(' + deals.length + ')';
        
        // Paginate: show only up to currentPage * DEALS_PER_PAGE
        const toShow = deals.slice(0, currentPage * DEALS_PER_PAGE);
        displayedDeals = toShow.length;
        
        if (append) {
            // Append new cards with fade-in animation
            const newCards = deals.slice((currentPage - 1) * DEALS_PER_PAGE, currentPage * DEALS_PER_PAGE);
            const tempDiv = document.createElement('div');
            tempDiv.innerHTML = newCards.map(createCard).join('');
            Array.from(tempDiv.children).forEach(card => {
                card.style.opacity = '0';
                card.style.transform = 'translateY(20px)';
                el.grid.appendChild(card);
                requestAnimationFrame(() => {
                    card.style.transition = 'opacity 0.3s, transform 0.3s';
                    card.style.opacity = '1';
                    card.style.transform = 'translateY(0)';
                });
            });
        } else {
            el.grid.innerHTML = toShow.map(createCard).join('');
        }
        
        toShow.forEach(d => startCountdown('cd-'+(d.bcpea_id || d.id), d.auction_end));
        
        // Show/hide load more button
        if (el.loadMore) {
            if (displayedDeals < deals.length) {
                el.loadMore.classList.remove('hidden');
                el.loadMore.querySelector('.load-more-count').textContent = 
                    (deals.length - displayedDeals) + ' имота';
            } else {
                el.loadMore.classList.add('hidden');
            }
        }
    }
    
    function loadMore() {
        currentPage++;
        render(filteredDeals, true);
        // Smooth scroll to new content
        const cards = el.grid.querySelectorAll('.deal-card');
        if (cards.length > DEALS_PER_PAGE) {
            cards[(currentPage - 1) * DEALS_PER_PAGE]?.scrollIntoView({ behavior: 'smooth', block: 'start' });
        }
    }
    
    function updateHero() {
        el.heroTotal.textContent = allDeals.length;
        if (allDeals.length > 0) {
            // Only count positive discounts for average
            const discounts = allDeals
                .map(d => d.discount_pct !== undefined ? d.discount_pct : (d.discount || 0))
                .filter(d => d > 0);
            const avg = discounts.length > 0 ? discounts.reduce((s, d) => s + d, 0) / discounts.length : 0;
            el.heroAvg.textContent = Math.round(avg) + '%';
            const best = allDeals.map(d => d.discount_pct !== undefined ? d.discount_pct : (d.discount || 0));
            el.heroBest.textContent = Math.round(Math.max(...best)) + '%';
        }
        // Update data freshness badge
        const meta = window._dealsMetadata;
        const badge = document.getElementById('data-freshness-badge');
        if (badge && meta) {
            const srcList = (meta.sources || ['imot.bg', 'olx.bg']).join(' + ');
            const date = meta.generated_at || '';
            badge.textContent = `Данни: ${srcList}${date ? ' · ' + date : ''}`;
            badge.style.display = 'inline-block';
        }
    }
    
    function populateCities() {
        const MAJOR_CITIES = ['София', 'Варна', 'Пловдив', 'Бургас', 'Стара Загора', 'Русе'];
        const allCities = [...new Set(allDeals.map(d => d.city).filter(Boolean))];
        const val = el.city.value;
        el.city.innerHTML = '<option value="all">Всички градове</option>';
        // Add major cities in fixed order (only if they have deals)
        MAJOR_CITIES.forEach(c => {
            if (allCities.includes(c)) {
                const o = document.createElement('option'); o.value = c; o.textContent = c; el.city.appendChild(o);
            }
        });
        // Add "Други" option for everything else
        const otherCities = allCities.filter(c => !MAJOR_CITIES.includes(c));
        if (otherCities.length > 0) {
            const o = document.createElement('option'); o.value = '_other'; o.textContent = 'Други'; el.city.appendChild(o);
        }
        el.city.value = val;
    }
    
    function getActive() {
        const typeLabels = {
            'apartment': 'Апартамент',
            'house': 'Къща',
            'garage': 'Гараж',
            'commercial': 'Търговски',
            'other': 'Други'
        };
        const f = [];
        if (el.city.value !== 'all') f.push({type:'city', label: el.city.value === '_other' ? 'Други' : el.city.value});
        if (el.type.value !== 'all') f.push({type:'type', label:typeLabels[el.type.value] || el.type.value});
        if (el.minPrice.value) f.push({type:'minPrice', label:'От '+fmtPrice(parseInt(el.minPrice.value))});
        if (el.maxPrice.value) f.push({type:'maxPrice', label:'До '+fmtPrice(parseInt(el.maxPrice.value))});
        if (parseInt(el.discount.value) > 0) f.push({type:'discount', label:el.discount.value+'%+ отстъпка'});
        return f;
    }
    
    function renderActive() {
        const f = getActive();
        el.activeFilters.innerHTML = f.length ? f.map(x => `<span class="active-filter">${escHtml(x.label)}<button onclick="rmFilter('${escHtml(x.type)}')">✕</button></span>`).join('') : '';
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
        currentPage = 1; // Reset pagination on filter change
        updateURL(); // Save filter state to URL
        const city = el.city.value, type = el.type.value;
        const minP = parseInt(el.minPrice.value) || 0, maxP = parseInt(el.maxPrice.value) || Infinity;
        const minD = parseInt(el.discount.value) || 0;
        const pill = document.querySelector('.pill-active')?.dataset.filter || 'all';
        filteredDeals = allDeals.filter(d => {
            const auctionPrice = d.auction_price || d.effective_price || d.price || 0;
            const discountPct = d.discount_pct !== undefined ? d.discount_pct : (d.discount || 0);
            if (city === '_other') { if (['София','Варна','Пловдив','Бургас','Стара Загора','Русе'].includes(d.city)) return false; } else if (city !== 'all' && d.city !== city) return false;
            if (type !== 'all' && d.property_type?.toLowerCase() !== type.toLowerCase()) return false;
            if (auctionPrice < minP || auctionPrice > maxP) return false;
            if (discountPct < minD) return false;
            if (pill === 'new' && !isNew(d.auction_end)) return false;
            if (pill === 'ending') { const days = daysUntil(d.auction_end); if (days === null || days > 7) return false; }
            if (pill === 'best' && discountPct < 40) return false;
            if (pill === 'sofia' && !(d.city && d.city.includes('София'))) return false;
            // No comparison filter - deals without market data
            if (pill === 'nocomparison') {
                const comparables = d.comparables_count || d.market_sample_size || 0;
                if (comparables > 0 && d.market_price) return false;
            }
            return true;
        });
        const sort = el.sort.value;
        filteredDeals.sort((a, b) => {
            const aPrice = a.auction_price || a.effective_price || a.price || 0;
            const bPrice = b.auction_price || b.effective_price || b.price || 0;
            const aDiscount = a.discount_pct !== undefined ? a.discount_pct : (a.discount || 0);
            const bDiscount = b.discount_pct !== undefined ? b.discount_pct : (b.discount || 0);
            const aSavings = Math.max(0, a.savings_eur !== undefined ? a.savings_eur : ((a.market_price || a.market_avg * a.sqm || 0) - aPrice));
            const bSavings = Math.max(0, b.savings_eur !== undefined ? b.savings_eur : ((b.market_price || b.market_avg * b.sqm || 0) - bPrice));
            
            if (sort === 'best') return (bDiscount * Math.log(bSavings+1)) - (aDiscount * Math.log(aSavings+1));
            if (sort === 'ending') return (parseDate(a.auction_end) || new Date(9999,0)) - (parseDate(b.auction_end) || new Date(9999,0));
            if (sort === 'newest') return (parseDate(b.auction_end) || new Date(0)) - (parseDate(a.auction_end) || new Date(0));
            if (sort === 'price_asc') return aPrice - bPrice;
            if (sort === 'price_desc') return bPrice - aPrice;
            return 0;
        });
        render(filteredDeals);
        renderActive();
    }
    
    
    // URL State Management
    function updateURL() {
        const params = new URLSearchParams();
        if (el.city.value !== 'all') params.set('city', el.city.value);
        if (el.type.value !== 'all') params.set('type', el.type.value);
        if (el.minPrice.value) params.set('min', el.minPrice.value);
        if (el.maxPrice.value) params.set('max', el.maxPrice.value);
        if (parseInt(el.discount.value) > 0) params.set('discount', el.discount.value);
        if (el.sort.value !== 'discount') params.set('sort', el.sort.value);
        
        const newURL = params.toString() ? '?' + params.toString() : window.location.pathname;
        history.replaceState(null, '', newURL);
    }
    
    function loadFromURL() {
        const params = new URLSearchParams(window.location.search);
        if (params.get('city')) el.city.value = params.get('city');
        if (params.get('type')) el.type.value = params.get('type');
        if (params.get('min')) el.minPrice.value = params.get('min');
        if (params.get('max')) el.maxPrice.value = params.get('max');
        if (params.get('discount')) el.discount.value = params.get('discount');
        if (params.get('sort')) el.sort.value = params.get('sort');
    }
    
    // Back to top functionality
    function initBackToTop() {
        if (!el.backToTop) return;
        window.addEventListener('scroll', () => {
            if (window.scrollY > 500) {
                el.backToTop.classList.add('visible');
            } else {
                el.backToTop.classList.remove('visible');
            }
        });
        el.backToTop.addEventListener('click', () => {
            window.scrollTo({ top: 0, behavior: 'smooth' });
        });
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
            // Store metadata for data freshness badge
            window._dealsMetadata = Array.isArray(data) ? null : {
                generated_at: data.generated_at || null,
                sources: data.sources || ['imot.bg', 'olx.bg'],
            };
        } catch(e) {
            console.error('Failed to load deals:', e);
            allDeals = [];
        }
        populateCities();
        loadFromURL(); // Apply URL filters after cities are populated
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
        const d = allDeals.find(x => (x.bcpea_id || x.id) === id);
        if (!d) return;
        
        // Normalize data
        const bcpeaId = d.bcpea_id || d.id;
        const auctionPrice = d.auction_price || d.effective_price || d.price || 0;
        const modalComparables = d.comparables_count || d.market_sample_size || 0;
        const modalComparablesLevel = d.comparables_level || null;
        const modalHasMarketData = modalComparables > 0 && d.market_price;
        const marketPrice = modalHasMarketData ? d.market_price : null;
        const discountPct = d.discount_pct !== undefined ? d.discount_pct : (d.discount || 0);
        const savingsEur = Math.max(0, d.savings_eur !== undefined ? d.savings_eur : (marketPrice - auctionPrice));
        const city = escHtml(d.city || 'Неизвестен');
        const neighborhood = escHtml(d.neighborhood || 'Неизвестен');
        const sqm = d.sqm;
        const propertyType = escHtml(d.property_type || 'Имот');
        const auctionEnd = escHtml(d.auction_end || '');
        const comparables = d.comparables_count || 0;
        const partialOwnership = d.partial_ownership;
        const url = d.url || `${BCPEA_URL}/${bcpeaId}`;
        
        const r = getRating(discountPct), days = daysUntil(auctionEnd);
        
        // Warning messages
        const ownershipHtml = partialOwnership ? `
            <div style="background:var(--warning-light, #FFF8E1);padding:12px 16px;border-radius:var(--radius);margin-bottom:16px;border-left:4px solid var(--warning);">
                <strong>⚠️ Частна собственост</strong><br>
                <span style="font-size:13px;">Този имот е с частна собственост. Моля, проверете размера на дела преди участие в търга.</span>
            </div>
        ` : '';
        
        const dataWarningHtml = comparables === 0 ? `
            <div style="background:var(--danger-light);padding:12px 16px;border-radius:var(--radius);margin-bottom:16px;border-left:4px solid var(--danger);">
                <strong>⚠️ Ограничени данни</strong><br>
                <span style="font-size:13px;">Няма намерени сравними обяви. Пазарната цена може да не е точна.</span>
            </div>
        ` : '';
        
        const negativeWarningHtml = discountPct < 0 ? `
            <div style="background:var(--danger-light);padding:12px 16px;border-radius:var(--radius);margin-bottom:16px;border-left:4px solid var(--danger);">
                <strong>⚠️ Внимание</strong><br>
                <span style="font-size:13px;">Тръжната цена е по-висока от оценката на пазарната цена. Това може да не е изгодна сделка.</span>
            </div>
        ` : '';
        
        el.modalBody.innerHTML = `<div style="padding:32px;">
            <div class="card-header deal-${r.level}" style="margin:-32px -32px 24px -32px;padding:32px;">
                <div class="discount-badge">
                    <div class="discount-value">${discountPct >= 0 ? '-' : '+'}${Math.abs(Math.round(discountPct))}%</div>
                    <div class="discount-label">${discountPct >= 0 ? 'ОТСТЪПКА' : 'НАД ПАЗАРНАТА'}</div>
                </div>
            </div>
            ${ownershipHtml}
            ${dataWarningHtml}
            ${negativeWarningHtml}
            <h2 style="font-size:24px;font-weight:700;margin-bottom:8px;">${escHtml(propertyType.charAt(0).toUpperCase() + propertyType.slice(1))} в ${escHtml(city)}</h2>
            <p style="color:var(--gray-500);margin-bottom:24px;">${neighborhood && neighborhood !== 'Неизвестен' ? escHtml(neighborhood) : ''}</p>
            <div style="display:grid;grid-template-columns:${marketPrice ? '1fr 1fr' : '1fr'};gap:16px;margin-bottom:24px;">
                <div style="background:${discountPct >= 0 ? 'var(--success-light)' : 'var(--danger-light)'};padding:16px;border-radius:var(--radius);">
                    <div style="font-size:12px;color:var(--gray-500);text-transform:uppercase;font-weight:600;">Тръжна цена</div>
                    <div style="font-size:24px;font-weight:700;color:${discountPct >= 0 ? 'var(--success)' : 'var(--danger)'};">${fmtPrice(auctionPrice)}</div>
                    <div style="font-size:14px;color:var(--gray-600);">${fmtSqm(auctionPrice, sqm)}</div>
                </div>
                ${marketPrice ? `
                <div style="background:var(--gray-100);padding:16px;border-radius:var(--radius);">
                    <div style="font-size:12px;color:var(--gray-500);text-transform:uppercase;font-weight:600;">Пазарна цена</div>
                    <div style="font-size:20px;font-weight:600;color:var(--gray-500);text-decoration:line-through;">${fmtPrice(marketPrice)}</div>
                    <div style="font-size:14px;color:var(--gray-600);">${fmtSqm(marketPrice, sqm)}</div>
                </div>
                ` : ''}
            </div>
            <div style="background:var(--info-light);padding:20px;border-radius:var(--radius);margin-bottom:24px;">
                <h4 style="font-size:14px;font-weight:600;margin-bottom:12px;">Анализ на сделката</h4>
                <ul style="list-style:none;padding:0;margin:0;font-size:14px;line-height:1.8;">
                    ${marketPrice ? (discountPct >= 0 ? 
                        `<li>✓ Цената е с <strong>${Math.round(discountPct)}%</strong> под пазарната ниво</li>
                         <li>✓ Спестявате <strong>${fmtPrice(savingsEur)}</strong> спрямо пазарната цена</li>` :
                        `<li>⚠ Цената е с <strong>${Math.abs(Math.round(discountPct))}%</strong> над пазарната ниво</li>
                         <li>⚠ Тръжната цена е с <strong>${fmtPrice(auctionPrice - marketPrice)}</strong> по-висока от пазарната</li>`
                    ) : '<li>⚠ Няма достатъчно данни за пазарна оценка</li>'}
                    ${d.neighborhood_range ? `<li>✓ Ценови диапазон в района: ${escHtml(d.neighborhood_range)}</li>` : ''}
                    ${comparables > 0 ? `<li>✓ Базирано на ${comparables} сравними обяви${modalComparablesLevel === 'hood' ? ' в квартала' : modalComparablesLevel === 'city_size' ? ' в ' + city + ' (подобен размер)' : modalComparablesLevel === 'city' ? ' в ' + city + ' (целия град — без квартал)' : ''}</li>` : '<li>⚠ Няма достатъчно сравними обяви за надеждна оценка</li>'}
                </ul>
            </div>
            <div style="margin-bottom:24px;">
                <div style="font-size:12px;color:var(--gray-500);text-transform:uppercase;font-weight:600;margin-bottom:8px;">Край на търга</div>
                <div style="font-size:18px;font-weight:600;color:${days !== null && days <= 3 ? 'var(--danger)' : 'var(--gray-700)'};">${fmtDate(auctionEnd)} ${days !== null ? '('+days+' дни)' : ''}</div>
            </div>
            <div style="display:flex;gap:12px;">
                <a href="${url}" target="_blank" class="btn btn-primary" style="flex:1;justify-content:center;">Виж в КЧСИ →</a>
                <button onclick="closeModal()" class="btn btn-outline">Затвори</button>
            </div>
        </div>`;
        el.modal.classList.remove('hidden');
        document.body.style.overflow = 'hidden';
    };
    
    window.closeModal = function() {
        el.modal.classList.add('hidden');
        document.body.style.overflow = '';
    };
    
    window.loadDeals = load;
    
    function reset() {
        console.log("Reset called");
        el.city.value = 'all'; el.type.value = 'all';
        el.minPrice.value = ''; el.maxPrice.value = '';
        el.discount.value = '0'; el.sort.value = 'best';
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
    document.getElementById('resetFilters')?.addEventListener('click', reset);
    document.getElementById('emptyResetFilters')?.addEventListener('click', reset);
    document.addEventListener('keydown', e => { if (e.key === 'Escape') closeModal(); });
    
    load();
})();

// Mobile filter toggle (global scope for onclick)
function toggleMobileFilters() {
    const panel = document.getElementById('advancedFilters');
    const chevron = document.getElementById('mobileFilterChevron');
    if (!panel) return;
    const isOpen = panel.classList.toggle('open');
    if (chevron) chevron.textContent = isOpen ? '▲' : '▼';
}
