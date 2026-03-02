/**
 * Site Configuration
 * Update SITE_URL when moving to production domain
 */
const CONFIG = {
    SITE_URL: 'https://izgodenimot.bg',
    
    SITE_NAME: 'КЧСИ Сделки',
    SITE_DESCRIPTION: 'Изгодни имоти от принудителни търгове в България',
    
    // Data refresh info
    DATA_REFRESH_HOUR: 9, // Sofia time
    
    // Contact
    CONTACT_EMAIL: 'info@izgodenimot.bg'
};

// For modules
if (typeof module !== 'undefined') {
    module.exports = CONFIG;
}
