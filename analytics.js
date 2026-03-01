/**
 * Analytics & Cookie Consent
 * 
 * GA4 loads in consent-denied mode by default.
 * Only starts tracking after user accepts cookies.
 * Consent choice persisted in localStorage.
 */

(function() {
    'use strict';

    // ==================== CONFIG ====================
    // TODO: Replace with your GA4 Measurement ID
    var GA_ID = 'G-XXXXXXXXXX';
    // ================================================

    // Skip if placeholder ID not replaced
    if (GA_ID === 'G-XXXXXXXXXX') {
        console.warn('[Analytics] GA4 ID not configured. Replace G-XXXXXXXXXX in analytics.js');
    }

    // -- GA4 initialization (consent-denied by default) --
    window.dataLayer = window.dataLayer || [];
    function gtag() { dataLayer.push(arguments); }
    window.gtag = gtag;

    gtag('consent', 'default', {
        ad_storage: 'denied',
        analytics_storage: 'denied',
        ad_user_data: 'denied',
        ad_personalization: 'denied'
    });

    // Load gtag.js async
    var s = document.createElement('script');
    s.async = true;
    s.src = 'https://www.googletagmanager.com/gtag/js?id=' + GA_ID;
    document.head.appendChild(s);

    gtag('js', new Date());
    gtag('config', GA_ID, {
        anonymize_ip: true,
        send_page_view: true
    });

    // -- Check stored consent --
    var consent = localStorage.getItem('cookie_consent');
    if (consent === 'accepted') {
        gtag('consent', 'update', { analytics_storage: 'granted' });
    }

    // -- Cookie consent banner --
    function createConsentBanner() {
        if (consent) return; // Already chose

        var banner = document.createElement('div');
        banner.id = 'cookieConsent';
        banner.setAttribute('role', 'alert');
        banner.innerHTML =
            '<div class="cookie-banner">' +
                '<p>Използваме бисквитки за анализ на трафика.' +
                    ' <a href="privacy.html" style="color:#2563eb;text-decoration:underline;">Научете повече</a>' +
                '</p>' +
                '<div class="cookie-buttons">' +
                    '<button id="cookieAccept" class="cookie-btn cookie-accept">Приемам</button>' +
                    '<button id="cookieDecline" class="cookie-btn cookie-decline">Отказвам</button>' +
                '</div>' +
            '</div>';
        document.body.appendChild(banner);

        document.getElementById('cookieAccept').addEventListener('click', function() {
            localStorage.setItem('cookie_consent', 'accepted');
            gtag('consent', 'update', { analytics_storage: 'granted' });
            banner.remove();
        });

        document.getElementById('cookieDecline').addEventListener('click', function() {
            localStorage.setItem('cookie_consent', 'declined');
            banner.remove();
        });
    }

    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', createConsentBanner);
    } else {
        createConsentBanner();
    }

    // -- Event tracking helper --
    window.trackEvent = function(name, params) {
        if (typeof gtag === 'function') {
            gtag('event', name, params || {});
        }
    };

    // -- Track outbound BCPEA clicks --
    document.addEventListener('click', function(e) {
        var a = e.target.closest('a[href*="sales.bcpea.org"]');
        if (a) trackEvent('bcpea_click', { href: a.href });
    });

})();
