/**
 * ImotWatch Background Service Worker
 * Handles badge updates and optional API sync
 */

// Listen for messages from content script
chrome.runtime.onMessage.addListener((message, sender, sendResponse) => {
  if (message.type === 'UPDATE_BADGE') {
    updateBadge(message.count);
    sendResponse({ success: true });
  }
  return true;
});

// Update extension badge with listing count
function updateBadge(count) {
  const text = count > 0 ? count.toString() : '';
  const color = count > 0 ? '#4CAF50' : '#9E9E9E';
  
  chrome.action.setBadgeText({ text });
  chrome.action.setBadgeBackgroundColor({ color });
}

// Initialize badge on install
chrome.runtime.onInstalled.addListener(async () => {
  console.log('[ImotWatch] Extension installed');
  
  // Initialize storage
  const result = await chrome.storage.local.get(['listings']);
  if (!result.listings) {
    await chrome.storage.local.set({ listings: [] });
  }
  
  updateBadge(result.listings?.length || 0);
});

// Update badge when storage changes
chrome.storage.onChanged.addListener((changes, namespace) => {
  if (namespace === 'local' && changes.listings) {
    const newCount = changes.listings.newValue?.length || 0;
    updateBadge(newCount);
  }
});

// Optional: Sync to backend API
async function syncToBackend() {
  try {
    const result = await chrome.storage.local.get(['listings', 'lastSync']);
    const listings = result.listings || [];
    const lastSync = result.lastSync || 0;
    
    // Get unsent listings
    const unsent = listings.filter(l => 
      new Date(l.extractedAt).getTime() > lastSync
    );
    
    if (unsent.length === 0) return;
    
    // TODO: Send to backend
    // const response = await fetch('https://api.imotwatch.bg/listings', {
    //   method: 'POST',
    //   headers: { 'Content-Type': 'application/json' },
    //   body: JSON.stringify({ listings: unsent })
    // });
    
    // Update last sync time
    await chrome.storage.local.set({ lastSync: Date.now() });
    
    console.log(`[ImotWatch] Synced ${unsent.length} listings`);
  } catch (err) {
    console.error('[ImotWatch] Sync failed:', err);
  }
}

// Periodic sync (every 5 minutes when active)
// chrome.alarms.create('sync', { periodInMinutes: 5 });
// chrome.alarms.onAlarm.addListener((alarm) => {
//   if (alarm.name === 'sync') {
//     syncToBackend();
//   }
// });
