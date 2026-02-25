/**
 * ImotWatch Content Script
 * Injected into Facebook group pages to extract real estate listings
 */

(function() {
  'use strict';

  // ============================================
  // CONFIGURATION
  // ============================================
  
  const CONFIG = {
    // Keywords that indicate a real estate post (Bulgarian)
    keywords: {
      transaction: [
        'продава', 'продавам', 'продаваме', 'продажба',
        'под наем', 'наем', 'давам под наем', 'отдавам',
        'търся', 'търсим', 'купувам'
      ],
      propertyType: [
        'апартамент', 'апартаменти', 'ап.', 'ап ',
        'стая', 'стаи',
        'къща', 'къщи', 'вила',
        'студио', 'гарсониера',
        'мезонет', 'ателие', 'таван', 'партер',
        'гараж', 'паркомясто', 'паркинг',
        'парцел', 'земя', 'имот', 'УПИ',
        'магазин', 'офис', 'склад', 'помещение'
      ],
      rooms: [
        'едностаен', 'двустаен', 'тристаен', 'четиристаен', 'многостаен',
        '1-стаен', '2-стаен', '3-стаен', '4-стаен',
        '1 стаен', '2 стаен', '3 стаен', '4 стаен',
        '1ст', '2ст', '3ст', '4ст'
      ],
      price: [
        'лв', 'лева', 'bgn', 'евро', 'euro', 'eur', '€'
      ],
      size: [
        'кв.м', 'квм', 'кв м', 'кв.', 'm2', 'м2', 'sqm'
      ]
    },
    // Minimum keyword matches to consider a post relevant
    minKeywordMatches: 2,
    // Debounce delay for processing
    debounceMs: 500,
    // Max posts to store locally
    maxStoredPosts: 500,
  };

  // ============================================
  // STATE
  // ============================================
  
  const state = {
    processedPosts: new Set(),
    foundListings: [],
    groupName: null,
    isProcessing: false,
  };

  // ============================================
  // UTILITIES
  // ============================================
  
  function log(...args) {
    console.log('[ImotWatch]', ...args);
  }

  function debounce(fn, delay) {
    let timeout;
    return function(...args) {
      clearTimeout(timeout);
      timeout = setTimeout(() => fn.apply(this, args), delay);
    };
  }

  // ============================================
  // KEYWORD MATCHING
  // ============================================
  
  function countKeywordMatches(text) {
    const lowerText = text.toLowerCase();
    let matches = 0;
    let matchedCategories = new Set();
    
    for (const [category, words] of Object.entries(CONFIG.keywords)) {
      for (const word of words) {
        if (lowerText.includes(word.toLowerCase())) {
          matches++;
          matchedCategories.add(category);
          break; // Count max 1 per category
        }
      }
    }
    
    return { matches, categories: matchedCategories };
  }

  function isRealEstatePost(text) {
    const { matches, categories } = countKeywordMatches(text);
    // Must have at least 2 matches AND include either transaction or propertyType
    return matches >= CONFIG.minKeywordMatches && 
           (categories.has('transaction') || categories.has('propertyType'));
  }

  // ============================================
  // DATA EXTRACTION
  // ============================================
  
  function extractPrice(text) {
    // Patterns: "50000 лв", "50 000 EUR", "€50,000", etc.
    const patterns = [
      /(\d[\d\s,.]*)\s*(лв|лева|bgn)/i,
      /(\d[\d\s,.]*)\s*(евро|euro|eur|€)/i,
      /(€|EUR)\s*(\d[\d\s,.]*)/i,
    ];
    
    for (const pattern of patterns) {
      const match = text.match(pattern);
      if (match) {
        // Clean the number
        let numStr = match[1] || match[2];
        numStr = numStr.replace(/\s/g, '').replace(',', '');
        const num = parseFloat(numStr);
        
        // Determine currency
        const fullMatch = match[0].toLowerCase();
        const currency = (fullMatch.includes('лв') || fullMatch.includes('bgn')) ? 'BGN' : 'EUR';
        
        if (!isNaN(num) && num > 100 && num < 10000000) {
          return { amount: num, currency };
        }
      }
    }
    return null;
  }

  function extractLocation(text) {
    // Common Sofia neighborhoods
    const sofiaNeighborhoods = [
      'младост', 'люлин', 'дружба', 'надежда', 'красно село', 'лозенец',
      'изток', 'гео милев', 'редута', 'подуяне', 'хаджи димитър', 'център',
      'витоша', 'бояна', 'симеоново', 'драгалевци', 'банкя', 'овча купел',
      'студентски', 'манастирски', 'борово', 'хладилника', 'иван вазов',
      'стрелбище', 'белите брези', 'гоце делчев', 'мотописта', 'бъкстон'
    ];
    
    // Bulgarian cities
    const cities = [
      'софия', 'пловдив', 'варна', 'бургас', 'русе', 'стара загора',
      'плевен', 'добрич', 'сливен', 'шумен', 'перник', 'хасково',
      'пазарджик', 'благоевград', 'велико търново', 'враца', 'габрово'
    ];
    
    const lowerText = text.toLowerCase();
    
    // Check Sofia neighborhoods
    for (const hood of sofiaNeighborhoods) {
      if (lowerText.includes(hood)) {
        return { city: 'София', neighborhood: hood };
      }
    }
    
    // Check cities
    for (const city of cities) {
      if (lowerText.includes(city)) {
        return { city, neighborhood: null };
      }
    }
    
    return null;
  }

  function extractPropertyType(text) {
    const lowerText = text.toLowerCase();
    
    const types = [
      { keywords: ['едностаен', '1-стаен', '1 стаен', 'гарсониера'], type: '1-стаен' },
      { keywords: ['двустаен', '2-стаен', '2 стаен'], type: '2-стаен' },
      { keywords: ['тристаен', '3-стаен', '3 стаен'], type: '3-стаен' },
      { keywords: ['четиристаен', '4-стаен', '4 стаен', 'многостаен'], type: '4+-стаен' },
      { keywords: ['студио'], type: 'студио' },
      { keywords: ['мезонет'], type: 'мезонет' },
      { keywords: ['къща', 'вила'], type: 'къща' },
      { keywords: ['парцел', 'земя', 'упи'], type: 'парцел' },
      { keywords: ['гараж', 'паркомясто'], type: 'гараж' },
      { keywords: ['офис'], type: 'офис' },
      { keywords: ['магазин'], type: 'магазин' },
    ];
    
    for (const { keywords, type } of types) {
      for (const kw of keywords) {
        if (lowerText.includes(kw)) {
          return type;
        }
      }
    }
    
    return 'имот'; // Generic
  }

  function extractTransactionType(text) {
    const lowerText = text.toLowerCase();
    
    if (lowerText.match(/под наем|давам под наем|отдавам|наем/)) {
      return 'rent';
    }
    if (lowerText.match(/продава|продажба|продаваме/)) {
      return 'sale';
    }
    if (lowerText.match(/търся|търсим|купувам/)) {
      return 'wanted';
    }
    return 'unknown';
  }

  function extractContact(text) {
    // Phone patterns
    const phonePatterns = [
      /(\+359|0)[\s.-]?(\d{2,3})[\s.-]?(\d{3})[\s.-]?(\d{3,4})/g,
      /(\d{3})[\s.-]?(\d{3})[\s.-]?(\d{3,4})/g,
    ];
    
    const phones = [];
    for (const pattern of phonePatterns) {
      const matches = text.matchAll(pattern);
      for (const match of matches) {
        phones.push(match[0].replace(/[\s.-]/g, ''));
      }
    }
    
    return phones.length > 0 ? phones : null;
  }

  function extractSize(text) {
    const patterns = [
      /(\d+)\s*(?:кв\.?м|квм|m2|м2|sqm)/i,
      /(\d+)\s*(?:sq\.?\s*m)/i,
    ];
    
    for (const pattern of patterns) {
      const match = text.match(pattern);
      if (match) {
        const size = parseInt(match[1]);
        if (size > 10 && size < 5000) {
          return size;
        }
      }
    }
    return null;
  }

  // ============================================
  // POST EXTRACTION
  // ============================================
  
  function getPostId(element) {
    // Try to find a unique identifier for the post
    const links = element.querySelectorAll('a[href*="/posts/"], a[href*="/permalink/"], a[href*="?story_fbid"]');
    for (const link of links) {
      const href = link.getAttribute('href');
      const match = href.match(/(?:posts|permalink)\/(\d+)|story_fbid=(\d+)/);
      if (match) {
        return match[1] || match[2];
      }
    }
    // Fallback: hash the first 100 chars of text
    const text = element.innerText.substring(0, 100);
    return 'hash_' + hashCode(text);
  }

  function hashCode(str) {
    let hash = 0;
    for (let i = 0; i < str.length; i++) {
      const char = str.charCodeAt(i);
      hash = ((hash << 5) - hash) + char;
      hash = hash & hash;
    }
    return Math.abs(hash).toString(16);
  }

  function getGroupName() {
    // Try various selectors for group name
    const selectors = [
      'h1', // Main heading
      '[role="main"] h2',
      'a[href*="/groups/"][role="link"]',
    ];
    
    for (const sel of selectors) {
      const el = document.querySelector(sel);
      if (el && el.innerText.length > 3 && el.innerText.length < 100) {
        return el.innerText.trim();
      }
    }
    
    // Fallback: try URL
    const match = window.location.pathname.match(/\/groups\/([^/]+)/);
    return match ? match[1] : 'Unknown Group';
  }

  function extractPostUrl(element) {
    const links = element.querySelectorAll('a[href*="/posts/"], a[href*="/permalink/"]');
    for (const link of links) {
      return link.href;
    }
    return window.location.href;
  }

  function extractImages(element) {
    const images = element.querySelectorAll('img[src*="scontent"]');
    return Array.from(images)
      .map(img => img.src)
      .filter(src => !src.includes('emoji') && !src.includes('profile'));
  }

  function extractTimestamp(element) {
    // Look for time elements or timestamp text
    const timeEl = element.querySelector('abbr[data-utime], time, [datetime]');
    if (timeEl) {
      return timeEl.getAttribute('datetime') || 
             timeEl.getAttribute('data-utime') ||
             timeEl.innerText;
    }
    return null;
  }

  function processPost(postElement) {
    const postId = getPostId(postElement);
    
    // Skip if already processed
    if (state.processedPosts.has(postId)) {
      return null;
    }
    state.processedPosts.add(postId);
    
    const text = postElement.innerText || '';
    
    // Skip if too short or not relevant
    if (text.length < 50 || !isRealEstatePost(text)) {
      return null;
    }
    
    // Extract data
    const listing = {
      id: postId,
      rawText: text.substring(0, 2000),
      postUrl: extractPostUrl(postElement),
      groupName: state.groupName,
      timestamp: extractTimestamp(postElement),
      images: extractImages(postElement),
      
      // Parsed data
      price: extractPrice(text),
      location: extractLocation(text),
      propertyType: extractPropertyType(text),
      transactionType: extractTransactionType(text),
      contact: extractContact(text),
      size: extractSize(text),
      
      // Meta
      extractedAt: new Date().toISOString(),
      source: 'facebook',
    };
    
    return listing;
  }

  // ============================================
  // DOM OBSERVATION
  // ============================================
  
  function findPostElements() {
    // Facebook uses [role="article"] for posts
    return document.querySelectorAll('[role="article"]');
  }

  const processVisiblePosts = debounce(() => {
    if (state.isProcessing) return;
    state.isProcessing = true;
    
    const posts = findPostElements();
    let newCount = 0;
    
    posts.forEach(post => {
      const listing = processPost(post);
      if (listing) {
        state.foundListings.push(listing);
        newCount++;
        log('Found listing:', listing.propertyType, listing.price, listing.location);
      }
    });
    
    if (newCount > 0) {
      // Save to storage
      saveListings();
      // Update badge
      updateBadge();
    }
    
    state.isProcessing = false;
  }, CONFIG.debounceMs);

  // ============================================
  // STORAGE
  // ============================================
  
  async function saveListings() {
    try {
      // Get existing
      const result = await chrome.storage.local.get(['listings']);
      let allListings = result.listings || [];
      
      // Merge new listings
      const existingIds = new Set(allListings.map(l => l.id));
      const newListings = state.foundListings.filter(l => !existingIds.has(l.id));
      
      allListings = [...newListings, ...allListings];
      
      // Trim to max
      if (allListings.length > CONFIG.maxStoredPosts) {
        allListings = allListings.slice(0, CONFIG.maxStoredPosts);
      }
      
      await chrome.storage.local.set({ listings: allListings });
      log(`Saved ${newListings.length} new listings, ${allListings.length} total`);
    } catch (err) {
      log('Error saving listings:', err);
    }
  }

  // ============================================
  // BADGE
  // ============================================
  
  async function updateBadge() {
    try {
      const result = await chrome.storage.local.get(['listings']);
      const count = (result.listings || []).length;
      chrome.runtime.sendMessage({ 
        type: 'UPDATE_BADGE', 
        count: count 
      });
    } catch (err) {
      // Ignore - might not have badge permission
    }
  }

  // ============================================
  // INITIALIZATION
  // ============================================
  
  function init() {
    log('Initializing on', window.location.href);
    
    // Get group name
    state.groupName = getGroupName();
    log('Group:', state.groupName);
    
    // Process existing posts
    processVisiblePosts();
    
    // Watch for new posts (infinite scroll)
    const observer = new MutationObserver((mutations) => {
      let hasNewContent = false;
      for (const mutation of mutations) {
        if (mutation.addedNodes.length > 0) {
          hasNewContent = true;
          break;
        }
      }
      if (hasNewContent) {
        processVisiblePosts();
      }
    });
    
    observer.observe(document.body, {
      childList: true,
      subtree: true,
    });
    
    log('Observer started');
  }

  // Wait for page to be ready
  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', init);
  } else {
    init();
  }

})();
