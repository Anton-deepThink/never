from flask import Flask, request, jsonify
from flask_cors import CORS
import smtplib
import random
import time
import sqlite3
import threading
from datetime import datetime, timedelta
from email.mime.text import MIMEText

app = Flask(__name__)
CORS(app)

# ========== КОНФИГУРАЦИЯ ЯНДЕКС SMTP ==========
YANDEX_EMAIL = "anurin.dmit@ya.ru"
YANDEX_PASSWORD = "kiqgyqctsdihmpvo"

# ========== БАЗА ДАННЫХ ==========
def init_db():
    conn = sqlite3.connect('future_messages.db')
    c = conn.cursor()
    c.execute('''CREATE TABLE IF NOT EXISTS users (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        email TEXT UNIQUE NOT NULL,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )''')
    c.execute('''CREATE TABLE IF NOT EXISTS otp_codes (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        email TEXT NOT NULL,
        code TEXT NOT NULL,
        expires_at TIMESTAMP NOT NULL
    )''')
    c.execute('''CREATE TABLE IF NOT EXISTS envelopes (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_email TEXT NOT NULL,
        recipient_email TEXT NOT NULL,
        name TEXT NOT NULL,
        send_date TIMESTAMP NOT NULL,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )''')
    conn.commit()
    conn.close()

init_db()

# ========== ОТПРАВКА ПИСЕМ ==========
def send_email(to_email, subject, body):
    try:
        msg = MIMEText(body, 'plain', 'utf-8')
        msg['Subject'] = subject
        msg['From'] = YANDEX_EMAIL
        msg['To'] = to_email
        
        with smtplib.SMTP_SSL('smtp.yandex.ru', 465) as server:
            server.login(YANDEX_EMAIL, YANDEX_PASSWORD)
            server.send_message(msg)
        print(f"✅ Письмо отправлено на {to_email}")
        return True
    except Exception as e:
        print(f"❌ Ошибка: {e}")
        return False

def send_otp_email(email, code):
    subject = "🔐 Код для входа в Message to Future"
    body = f"""
Ваш код для входа в сервис Message to Future: {code}

Код действителен 10 минут.

Никому не сообщайте этот код.

---
Message to Future — отправь письмо в будущее
    """
    return send_email(email, subject, body)

# ========== API ЭНДПОИНТЫ ==========
@app.route('/send-otp', methods=['POST'])
def send_otp():
    data = request.json
    email = data.get('email')
    
    if not email or '@' not in email:
        return jsonify({'error': 'Неверный email'}), 400
    
    code = str(random.randint(100000, 999999))
    expires_at = datetime.now() + timedelta(minutes=10)
    
    conn = sqlite3.connect('future_messages.db')
    c = conn.cursor()
    c.execute("DELETE FROM otp_codes WHERE email = ?", (email,))
    c.execute("INSERT INTO otp_codes (email, code, expires_at) VALUES (?, ?, ?)",
              (email, code, expires_at.isoformat()))
    conn.commit()
    conn.close()
    
    if send_otp_email(email, code):
        return jsonify({'success': True})
    else:
        return jsonify({'error': 'Не удалось отправить код'}), 500

@app.route('/verify-otp', methods=['POST'])
def verify_otp():
    data = request.json
    email = data.get('email')
    code = data.get('code')
    
    conn = sqlite3.connect('future_messages.db')
    c = conn.cursor()
    c.execute("SELECT code, expires_at FROM otp_codes WHERE email = ? ORDER BY id DESC LIMIT 1", (email,))
    result = c.fetchone()
    conn.close()
    
    if not result:
        return jsonify({'error': 'Код не найден'}), 400
    
    stored_code, expires_at = result
    if stored_code != code or datetime.now() > datetime.fromisoformat(expires_at):
        return jsonify({'error': 'Неверный или просроченный код'}), 400
    
    # Добавляем пользователя в БД
    conn = sqlite3.connect('future_messages.db')
    c = conn.cursor()
    c.execute("INSERT OR IGNORE INTO users (email) VALUES (?)", (email,))
    conn.commit()
    conn.close()
    
    return jsonify({'success': True, 'email': email})

@app.route('/save-envelope', methods=['POST'])
def save_envelope():
    data = request.json
    user_email = data.get('userEmail')
    recipient_email = data.get('recipientEmail')
    name = data.get('name')
    send_date = data.get('sendDate')
    
    conn = sqlite3.connect('future_messages.db')
    c = conn.cursor()
    c.execute('''INSERT INTO envelopes (user_email, recipient_email, name, send_date)
                 VALUES (?, ?, ?, ?)''', (user_email, recipient_email, name, send_date))
    conn.commit()
    conn.close()
    
    return jsonify({'success': True})

@app.route('/get-envelopes', methods=['POST'])
def get_envelopes():
    data = request.json
    user_email = data.get('userEmail')
    
    conn = sqlite3.connect('future_messages.db')
    c = conn.cursor()
    c.execute("SELECT id, recipient_email, name, send_date FROM envelopes WHERE user_email = ? ORDER BY send_date ASC", (user_email,))
    envelopes = [{'id': row[0], 'recipient': row[1], 'name': row[2], 'sendDate': row[3]} for row in c.fetchall()]
    conn.close()
    
    return jsonify({'envelopes': envelopes})

if __name__ == '__main__':
    print("🚀 Сервер запущен на http://localhost:5000")
    print(f"📧 Отправка через {YANDEX_EMAIL}")
    app.run(host='0.0.0.0', port=5000, debug=False)
