/**
 * Site Configuration
 * Update SITE_URL when moving to production domain
 */
const CONFIG = {
    // Change this when you buy the domain
    SITE_URL: 'https://martinpetrov8.github.io/real-estate-price-matching',
    // SITE_URL: 'https://kchsi-sdelki.bg',  // Uncomment for production
    
    SITE_NAME: 'КЧСИ Сделки',
    SITE_DESCRIPTION: 'Изгодни имоти от принудителни търгове в България',
    
    // Data refresh info
    DATA_REFRESH_HOUR: 9, // Sofia time
    
    // Contact
    CONTACT_EMAIL: 'info@kchsi-sdelki.bg'
};

// For modules
if (typeof module !== 'undefined') {
    module.exports = CONFIG;
}
