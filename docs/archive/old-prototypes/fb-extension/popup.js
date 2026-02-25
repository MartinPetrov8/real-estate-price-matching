/**
 * ImotWatch Popup Script
 */

(function() {
  'use strict';

  // State
  let allListings = [];
  let currentFilter = 'all';

  // DOM elements
  const listingsContainer = document.getElementById('listingsContainer');
  const totalCountEl = document.getElementById('totalCount');
  const todayCountEl = document.getElementById('todayCount');
  const refreshBtn = document.getElementById('refreshBtn');
  const clearBtn = document.getElementById('clearBtn');
  const filterBtns = document.querySelectorAll('.filter-btn');

  // ============================================
  // FORMATTING
  // ============================================

  function formatPrice(price) {
    if (!price) return '—';
    const formatted = price.amount.toLocaleString('bg-BG');
    return `${formatted} ${price.currency}`;
  }

  function formatLocation(location) {
    if (!location) return 'Unknown location';
    if (location.neighborhood) {
      return `${location.city}, ${location.neighborhood}`;
    }
    return location.city;
  }

  function formatTime(timestamp) {
    if (!timestamp) return '';
    
    const date = new Date(timestamp);
    const now = new Date();
    const diffMs = now - date;
    const diffHours = Math.floor(diffMs / (1000 * 60 * 60));
    const diffDays = Math.floor(diffHours / 24);
    
    if (diffHours < 1) return 'Just now';
    if (diffHours < 24) return `${diffHours}h ago`;
    if (diffDays < 7) return `${diffDays}d ago`;
    
    return date.toLocaleDateString('bg-BG');
  }

  function getPropertyIcon(type) {
    const icons = {
      '1-стаен': '🏢',
      '2-стаен': '🏢',
      '3-стаен': '🏢',
      '4+-стаен': '🏢',
      'студио': '🏢',
      'мезонет': '🏠',
      'къща': '🏡',
      'парцел': '🌳',
      'гараж': '🚗',
      'офис': '🏬',
      'магазин': '🏪',
      'имот': '🏠',
    };
    return icons[type] || '🏠';
  }

  function getTransactionBadge(type) {
    const badges = {
      'sale': { class: 'badge-sale', text: 'Продава' },
      'rent': { class: 'badge-rent', text: 'Под наем' },
      'wanted': { class: 'badge-wanted', text: 'Търси' },
    };
    return badges[type] || { class: 'badge-sale', text: '' };
  }

  // ============================================
  // RENDERING
  // ============================================

  function renderListing(listing) {
    const badge = getTransactionBadge(listing.transactionType);
    const icon = getPropertyIcon(listing.propertyType);
    
    return `
      <div class="listing" data-url="${listing.postUrl || '#'}">
        <div class="listing-header">
          <div class="listing-type">
            <span class="listing-type-icon">${icon}</span>
            ${listing.propertyType || 'Имот'}
            ${listing.size ? `· ${listing.size} м²` : ''}
          </div>
          <div class="listing-price">${formatPrice(listing.price)}</div>
        </div>
        <div class="listing-location">
          📍 ${formatLocation(listing.location)}
          ${badge.text ? `<span class="listing-badge ${badge.class}">${badge.text}</span>` : ''}
        </div>
        <div class="listing-meta">
          <span class="listing-time">${formatTime(listing.extractedAt)}</span>
          <span class="listing-group">${listing.groupName || ''}</span>
        </div>
      </div>
    `;
  }

  function renderEmptyState() {
    return `
      <div class="empty-state">
        <div class="empty-state-icon">🔍</div>
        <p>No listings found yet.<br>Browse Facebook real estate groups to start collecting.</p>
      </div>
    `;
  }

  function renderListings(listings) {
    if (listings.length === 0) {
      listingsContainer.innerHTML = renderEmptyState();
      return;
    }
    
    listingsContainer.innerHTML = listings.map(renderListing).join('');
    
    // Add click handlers
    listingsContainer.querySelectorAll('.listing').forEach(el => {
      el.addEventListener('click', () => {
        const url = el.dataset.url;
        if (url && url !== '#') {
          chrome.tabs.create({ url });
        }
      });
    });
  }

  function updateStats() {
    totalCountEl.textContent = allListings.length;
    
    // Count today's listings
    const today = new Date();
    today.setHours(0, 0, 0, 0);
    const todayCount = allListings.filter(l => {
      const date = new Date(l.extractedAt);
      return date >= today;
    }).length;
    
    todayCountEl.textContent = todayCount;
  }

  function applyFilter() {
    let filtered = allListings;
    
    if (currentFilter !== 'all') {
      filtered = allListings.filter(l => l.transactionType === currentFilter);
    }
    
    renderListings(filtered);
  }

  // ============================================
  // DATA LOADING
  // ============================================

  async function loadListings() {
    try {
      const result = await chrome.storage.local.get(['listings']);
      allListings = result.listings || [];
      
      // Sort by newest first
      allListings.sort((a, b) => 
        new Date(b.extractedAt) - new Date(a.extractedAt)
      );
      
      updateStats();
      applyFilter();
    } catch (err) {
      console.error('Error loading listings:', err);
      listingsContainer.innerHTML = `
        <div class="empty-state">
          <div class="empty-state-icon">⚠️</div>
          <p>Error loading listings.<br>Please try again.</p>
        </div>
      `;
    }
  }

  async function clearListings() {
    if (confirm('Are you sure you want to clear all listings?')) {
      await chrome.storage.local.set({ listings: [] });
      allListings = [];
      updateStats();
      applyFilter();
    }
  }

  // ============================================
  // EVENT HANDLERS
  // ============================================

  refreshBtn.addEventListener('click', loadListings);
  
  clearBtn.addEventListener('click', clearListings);
  
  filterBtns.forEach(btn => {
    btn.addEventListener('click', () => {
      filterBtns.forEach(b => b.classList.remove('active'));
      btn.classList.add('active');
      currentFilter = btn.dataset.filter;
      applyFilter();
    });
  });

  // Listen for storage changes
  chrome.storage.onChanged.addListener((changes, namespace) => {
    if (namespace === 'local' && changes.listings) {
      allListings = changes.listings.newValue || [];
      allListings.sort((a, b) => 
        new Date(b.extractedAt) - new Date(a.extractedAt)
      );
      updateStats();
      applyFilter();
    }
  });

  // ============================================
  // INITIALIZATION
  // ============================================

  loadListings();

})();
