// Subscribe Modal for Real Estate Alerts
// Inject this into index.html

// API URL - reads from config or falls back to Railway deployment
const ALERT_API_URL = (typeof CONFIG !== 'undefined' && CONFIG.API_URL) || 'https://web-production-36c65.up.railway.app';

function createSubscribeModal() {
    // Create modal HTML
    const modalHTML = `
    <div id="subscribeModal" class="modal" style="display:none;position:fixed;top:0;left:0;width:100%;height:100%;background:rgba(0,0,0,0.5);z-index:1000;align-items:center;justify-content:center;">
        <div style="background:#fff;border-radius:16px;padding:32px;max-width:480px;width:90%;max-height:90vh;overflow-y:auto;position:relative;">
            <button onclick="closeSubscribeModal()" style="position:absolute;top:16px;right:16px;background:none;border:none;font-size:24px;cursor:pointer;color:#6b7280;">&times;</button>
            
            <h2 style="margin:0 0 8px 0;font-size:24px;">🔔 Получавай известия</h2>
            <p style="color:#6b7280;margin:0 0 24px 0;">Ще те уведомим когато се появят нови изгодни оферти.</p>
            
            <form id="subscribeForm" onsubmit="handleSubscribe(event)">
                <div style="margin-bottom:20px;">
                    <label style="display:block;font-weight:500;margin-bottom:8px;">Имейл адрес</label>
                    <input type="email" id="subEmail" required placeholder="tvoia@email.com" 
                           style="width:100%;padding:12px;border:1px solid #d1d5db;border-radius:8px;font-size:16px;box-sizing:border-box;">
                </div>
                
                <div style="margin-bottom:20px;">
                    <label style="display:block;font-weight:500;margin-bottom:8px;">Градове</label>
                    <div style="display:grid;grid-template-columns:1fr 1fr;gap:8px;">
                        <label style="display:flex;align-items:center;gap:8px;padding:8px;border:1px solid #e5e7eb;border-radius:8px;cursor:pointer;">
                            <input type="checkbox" name="city" value="София" checked> София
                        </label>
                        <label style="display:flex;align-items:center;gap:8px;padding:8px;border:1px solid #e5e7eb;border-radius:8px;cursor:pointer;">
                            <input type="checkbox" name="city" value="Пловдив" checked> Пловдив
                        </label>
                        <label style="display:flex;align-items:center;gap:8px;padding:8px;border:1px solid #e5e7eb;border-radius:8px;cursor:pointer;">
                            <input type="checkbox" name="city" value="Варна" checked> Варна
                        </label>
                        <label style="display:flex;align-items:center;gap:8px;padding:8px;border:1px solid #e5e7eb;border-radius:8px;cursor:pointer;">
                            <input type="checkbox" name="city" value="Бургас" checked> Бургас
                        </label>
                    </div>
                </div>
                
                <div style="margin-bottom:24px;">
                    <label style="display:block;font-weight:500;margin-bottom:8px;">Минимална отстъпка</label>
                    <div style="display:flex;gap:8px;flex-wrap:wrap;">
                        <label style="display:flex;align-items:center;gap:6px;padding:8px 16px;border:1px solid #e5e7eb;border-radius:20px;cursor:pointer;">
                            <input type="radio" name="discount" value="20" checked> 20%+
                        </label>
                        <label style="display:flex;align-items:center;gap:6px;padding:8px 16px;border:1px solid #e5e7eb;border-radius:20px;cursor:pointer;">
                            <input type="radio" name="discount" value="30"> 30%+
                        </label>
                        <label style="display:flex;align-items:center;gap:6px;padding:8px 16px;border:1px solid #e5e7eb;border-radius:20px;cursor:pointer;">
                            <input type="radio" name="discount" value="40"> 40%+
                        </label>
                        <label style="display:flex;align-items:center;gap:6px;padding:8px 16px;border:1px solid #e5e7eb;border-radius:20px;cursor:pointer;">
                            <input type="radio" name="discount" value="50"> 50%+
                        </label>
                    </div>
                </div>
                
                <button type="submit" id="subscribeBtn" style="width:100%;padding:14px;background:#2563eb;color:#fff;border:none;border-radius:8px;font-size:16px;font-weight:500;cursor:pointer;">
                    Абонирай се
                </button>
                
                <p id="subscribeMsg" style="margin:16px 0 0 0;text-align:center;display:none;"></p>
            </form>
        </div>
    </div>
    `;
    
    document.body.insertAdjacentHTML('beforeend', modalHTML);
}

function openSubscribeModal() {
    document.getElementById('subscribeModal').style.display = 'flex';
}

function closeSubscribeModal() {
    document.getElementById('subscribeModal').style.display = 'none';
}

async function handleSubscribe(e) {
    e.preventDefault();
    
    const btn = document.getElementById('subscribeBtn');
    const msg = document.getElementById('subscribeMsg');
    
    const email = document.getElementById('subEmail').value;
    const cities = [...document.querySelectorAll('input[name="city"]:checked')].map(c => c.value);
    const discount = document.querySelector('input[name="discount"]:checked').value;
    
    btn.disabled = true;
    btn.textContent = 'Изпращане...';
    
    try {
        const resp = await fetch(`${ALERT_API_URL}/subscribe`, {
            method: 'POST',
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify({email, cities, min_discount: parseInt(discount)})
        });
        
        const data = await resp.json();
        
        if (resp.ok) {
            msg.style.color = '#166534';
            msg.textContent = data.message || 'Успешно! Провери имейла си.';
            msg.style.display = 'block';
            document.getElementById('subscribeForm').reset();
        } else {
            msg.style.color = '#dc2626';
            msg.textContent = data.error || 'Възникна грешка';
            msg.style.display = 'block';
        }
    } catch (err) {
        msg.style.color = '#dc2626';
        msg.textContent = 'Грешка при свързване със сървъра';
        msg.style.display = 'block';
    }
    
    btn.disabled = false;
    btn.textContent = 'Абонирай се';
}

// Initialize on page load
document.addEventListener('DOMContentLoaded', createSubscribeModal);

// Handle URL params (verification, unsubscribe)
const params = new URLSearchParams(window.location.search);
if (params.get('verified') === 'true') {
    alert('✅ Имейлът ти е потвърден! Ще получаваш известия за нови оферти.');
}
if (params.get('unsubscribed') === 'true') {
    alert('Успешно се отписа от известията.');
}
