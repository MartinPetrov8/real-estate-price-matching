import os
import sqlite3
import secrets
from flask import Flask, request, jsonify
from flask_cors import CORS

app = Flask(__name__)
CORS(app, origins=["https://martinpetrov8.github.io"])

DB_PATH = os.environ.get('DB_PATH', 'data/subscribers.db')

def get_db():
    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    conn = get_db()
    conn.execute('''
        CREATE TABLE IF NOT EXISTS subscribers (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            email TEXT UNIQUE NOT NULL,
            cities TEXT,
            min_discount INTEGER DEFAULT 0,
            verified INTEGER DEFAULT 0,
            verify_token TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    conn.commit()
    conn.close()

@app.route('/health', methods=['GET'])
def health():
    return jsonify({'status': 'ok'})

@app.route('/subscribe', methods=['POST'])
def subscribe():
    data = request.get_json()
    if not data or 'email' not in data:
        return jsonify({'error': 'Email is required'}), 400
    
    email = data['email'].strip().lower()
    cities = data.get('cities', '')
    min_discount = data.get('min_discount', 0)
    verify_token = secrets.token_urlsafe(32)
    
    try:
        conn = get_db()
        conn.execute('INSERT INTO subscribers (email, cities, min_discount, verify_token) VALUES (?, ?, ?, ?)',
                     (email, cities, min_discount, verify_token))
        conn.commit()
        conn.close()
        return jsonify({'success': True, 'message': 'Успешно се абонирахте!'})
    except sqlite3.IntegrityError:
        return jsonify({'error': 'Този имейл вече е абониран'}), 409

@app.route('/verify/<token>', methods=['GET'])
def verify(token):
    conn = get_db()
    result = conn.execute('UPDATE subscribers SET verified = 1 WHERE verify_token = ?', (token,))
    conn.commit()
    if result.rowcount > 0:
        conn.close()
        return jsonify({'success': True, 'message': 'Имейлът е потвърден!'})
    conn.close()
    return jsonify({'error': 'Невалиден токен'}), 404

@app.route('/unsubscribe/<token>', methods=['GET'])
def unsubscribe(token):
    conn = get_db()
    result = conn.execute('DELETE FROM subscribers WHERE verify_token = ?', (token,))
    conn.commit()
    conn.close()
    if result.rowcount > 0:
        return jsonify({'success': True, 'message': 'Успешно се отписахте'})
    return jsonify({'error': 'Невалиден токен'}), 404

init_db()

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port, debug=False)
