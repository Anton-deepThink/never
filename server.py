import os
import sqlite3
import smtplib
import random
import threading
import time
from datetime import datetime, timedelta
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from flask import Flask, request, jsonify
from flask_cors import CORS
import jwt
from functools import wraps

app = Flask(__name__)
CORS(app)

# Конфигурация
SECRET_KEY = "your-secret-key-change-this-12345"
DB_PATH = "messages.db"

# Настройки Яндекс SMTP
YANDEX_EMAIL = "anurin.dmit@ya.ru"
YANDEX_PASSWORD = "kiqgyqctsdihmpvo"
SMTP_SERVER = "smtp.yandex.ru"
SMTP_PORT = 465

# ========== БАЗА ДАННЫХ ==========
def init_db():
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    
    # Пользователи
    c.execute('''CREATE TABLE IF NOT EXISTS users (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        email TEXT UNIQUE NOT NULL,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )''')
    
    # OTP коды
    c.execute('''CREATE TABLE IF NOT EXISTS otp_codes (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        email TEXT NOT NULL,
        code TEXT NOT NULL,
        expires_at TIMESTAMP NOT NULL
    )''')
    
    # Сообщения
    c.execute('''CREATE TABLE IF NOT EXISTS messages (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER NOT NULL,
        recipient_email TEXT NOT NULL,
        subject TEXT NOT NULL,
        message_text TEXT NOT NULL,
        scheduled_time TIMESTAMP NOT NULL,
        reminder_time TIMESTAMP,
        reminder_sent BOOLEAN DEFAULT 0,
        sent BOOLEAN DEFAULT 0,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY (user_id) REFERENCES users (id)
    )''')
    
    conn.commit()
    conn.close()

# ========== ОТПРАВКА EMAIL ==========
def send_email(to_email, subject, html_content):
    """Отправка реального письма через Яндекс SMTP"""
    try:
        msg = MIMEMultipart()
        msg['From'] = YANDEX_EMAIL
        msg['To'] = to_email
        msg['Subject'] = subject
        msg.attach(MIMEText(html_content, 'html', 'utf-8'))
        
        with smtplib.SMTP_SSL(SMTP_SERVER, SMTP_PORT) as server:
            server.login(YANDEX_EMAIL, YANDEX_PASSWORD)
            server.send_message(msg)
        
        print(f"✅ Письмо отправлено на {to_email}")
        return True
    except Exception as e:
        print(f"❌ Ошибка отправки: {e}")
        return False

def send_otp_email(email, code):
    """Отправка кода подтверждения"""
    html = f"""
    <!DOCTYPE html>
    <html>
    <head><meta charset="UTF-8"></head>
    <body style="font-family: Arial, sans-serif; background: linear-gradient(135deg, #667eea 0%, #764ba2 100%); padding: 40px;">
        <div style="max-width: 500px; margin: 0 auto; background: white; border-radius: 20px; padding: 30px; box-shadow: 0 10px 40px rgba(0,0,0,0.2);">
            <h1 style="color: #764ba2; text-align: center;">✨ Message to Future</h1>
            <h2 style="text-align: center;">Ваш код для входа</h2>
            <div style="font-size: 48px; font-weight: bold; text-align: center; background: #f0f0f0; padding: 20px; border-radius: 15px; margin: 20px 0; letter-spacing: 5px;">
                {code}
            </div>
            <p style="text-align: center; color: #666;">Код действителен 10 минут</p>
            <hr style="margin: 20px 0;">
            <p style="text-align: center; font-size: 12px; color: #999;">Message to Future — отправь письмо в будущее</p>
        </div>
    </body>
    </html>
    """
    return send_email(email, "🔐 Код для входа в Message to Future", html)

def send_future_message(recipient_email, subject, message_text, scheduled_date):
    """Отправка запланированного письма"""
    html = f"""
    <!DOCTYPE html>
    <html>
    <head><meta charset="UTF-8"></head>
    <body style="font-family: Arial, sans-serif; background: linear-gradient(135deg, #f5f7fa 0%, #c3cfe2 100%); padding: 40px;">
        <div style="max-width: 600px; margin: 0 auto; background: white; border-radius: 20px; padding: 40px; box-shadow: 0 10px 40px rgba(0,0,0,0.1);">
            <div style="text-align: center; font-size: 50px;">📨</div>
            <h1 style="color: #333; text-align: center;">Послание из прошлого</h1>
            <div style="background: #f9f9f9; padding: 20px; border-radius: 15px; margin: 20px 0;">
                <h3 style="color: #764ba2;">{subject}</h3>
                <p style="font-size: 16px; line-height: 1.6;">{message_text}</p>
            </div>
            <div style="text-align: center; color: #999; font-size: 12px;">
                Это письмо было запланировано к отправке {scheduled_date}
            </div>
            <hr style="margin: 20px 0;">
            <p style="text-align: center; font-size: 12px; color: #999;">Message to Future — путешествие во времени через письма</p>
        </div>
    </body>
    </html>
    """
    return send_email(recipient_email, f"📨 {subject}", html)

def send_reminder(recipient_email, subject, scheduled_date):
    """Отправка напоминания"""
    html = f"""
    <!DOCTYPE html>
    <html>
    <head><meta charset="UTF-8"></head>
    <body style="font-family: Arial, sans-serif; padding: 40px;">
        <div style="max-width: 500px; margin: 0 auto; background: #fff3e0; border-radius: 20px; padding: 30px;">
            <div style="text-align: center; font-size: 40px;">⏰</div>
            <h2 style="text-align: center;">Напоминание о послании</h2>
            <p>Вы запланировали получение письма с темой: <strong>"{subject}"</strong></p>
            <p>Оно будет доставлено: <strong>{scheduled_date}</strong></p>
            <p style="margin-top: 20px;">Не пропустите важный момент!</p>
            <hr>
            <p style="text-align: center; font-size: 12px;">Message to Future</p>
        </div>
    </body>
    </html>
    """
    return send_email(recipient_email, f"⏰ Напоминание: {subject}", html)

# ========== JWT АУТЕНТИФИКАЦИЯ ==========
def generate_token(email):
    return jwt.encode({'email': email, 'exp': datetime.utcnow() + timedelta(days=7)}, SECRET_KEY, algorithm='HS256')

def verify_token(token):
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=['HS256'])
        return payload['email']
    except:
        return None

def get_user_id(email):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("SELECT id FROM users WHERE email = ?", (email,))
    result = c.fetchone()
    conn.close()
    if result:
        return result[0]
    
    # Создаём нового пользователя
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("INSERT INTO users (email) VALUES (?)", (email,))
    conn.commit()
    user_id = c.lastrowid
    conn.close()
    return user_id

# ========== API ЭНДПОИНТЫ ==========
@app.route('/api/send-otp', methods=['POST'])
def send_otp():
    data = request.json
    email = data.get('email')
    
    if not email:
        return jsonify({'error': 'Email обязателен'}), 400
    
    code = str(random.randint(100000, 999999))
    expires_at = datetime.now() + timedelta(minutes=10)
    
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("DELETE FROM otp_codes WHERE email = ?", (email,))
    c.execute("INSERT INTO otp_codes (email, code, expires_at) VALUES (?, ?, ?)", 
              (email, code, expires_at))
    conn.commit()
    conn.close()
    
    if send_otp_email(email, code):
        return jsonify({'success': True})
    else:
        return jsonify({'error': 'Не удалось отправить код'}), 500

@app.route('/api/verify-otp', methods=['POST'])
def verify_otp():
    data = request.json
    email = data.get('email')
    code = data.get('code')
    
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("SELECT code, expires_at FROM otp_codes WHERE email = ? ORDER BY id DESC LIMIT 1", (email,))
    result = c.fetchone()
    conn.close()
    
    if not result:
        return jsonify({'error': 'Код не найден'}), 400
    
    stored_code, expires_at = result
    if stored_code != code or datetime.now() > datetime.fromisoformat(expires_at):
        return jsonify({'error': 'Неверный или просроченный код'}), 400
    
    token = generate_token(email)
    return jsonify({'token': token, 'email': email})

@app.route('/api/messages', methods=['GET', 'POST'])
def handle_messages():
    token = request.headers.get('Authorization', '').replace('Bearer ', '')
    email = verify_token(token)
    
    if not email:
        return jsonify({'error': 'Не авторизован'}), 401
    
    user_id = get_user_id(email)
    
    if request.method == 'GET':
        conn = sqlite3.connect(DB_PATH)
        conn.row_factory = sqlite3.Row
        c = conn.cursor()
        c.execute("SELECT * FROM messages WHERE user_id = ? ORDER BY scheduled_time ASC", (user_id,))
        messages = [dict(row) for row in c.fetchall()]
        conn.close()
        return jsonify({'messages': messages})
    
    if request.method == 'POST':
        data = request.json
        recipient = data.get('recipientEmail')
        subject = data.get('subject')
        text = data.get('messageText')
        scheduled_time = data.get('scheduledTime')
        reminder_days = data.get('reminderDays', 0)
        
        # Вычисляем время напоминания
        reminder_time = None
        if reminder_days > 0:
            scheduled_dt = datetime.fromisoformat(scheduled_time)
            reminder_dt = scheduled_dt - timedelta(days=reminder_days)
            reminder_time = reminder_dt.isoformat()
        
        conn = sqlite3.connect(DB_PATH)
        c = conn.cursor()
        c.execute('''INSERT INTO messages (user_id, recipient_email, subject, message_text, scheduled_time, reminder_time)
                     VALUES (?, ?, ?, ?, ?, ?)''',
                  (user_id, recipient, subject, text, scheduled_time, reminder_time))
        conn.commit()
        conn.close()
        
        return jsonify({'success': True})

# ========== ФОНОВЫЙ ПРОЦЕСС ДЛЯ ОТПРАВКИ ==========
def message_scheduler():
    """Проверяет каждые 30 секунд и отправляет письма по расписанию"""
    while True:
        try:
            conn = sqlite3.connect(DB_PATH)
            conn.row_factory = sqlite3.Row
            c = conn.cursor()
            
            # Отправка основных писем
            now = datetime.now().isoformat()
            c.execute("SELECT * FROM messages WHERE sent = 0 AND scheduled_time <= ?", (now,))
            to_send = c.fetchall()
            
            for msg in to_send:
                success = send_future_message(
                    msg['recipient_email'],
                    msg['subject'],
                    msg['message_text'],
                    msg['scheduled_time']
                )
                if success:
                    c.execute("UPDATE messages SET sent = 1 WHERE id = ?", (msg['id'],))
                    print(f"✅ Отправлено письмо #{msg['id']} на {msg['recipient_email']}")
            
            # Отправка напоминаний
            c.execute("SELECT * FROM messages WHERE reminder_sent = 0 AND sent = 0 AND reminder_time IS NOT NULL AND reminder_time <= ?", (now,))
            to_remind = c.fetchall()
            
            for msg in to_remind:
                success = send_reminder(
                    msg['recipient_email'],
                    msg['subject'],
                    msg['scheduled_time']
                )
                if success:
                    c.execute("UPDATE messages SET reminder_sent = 1 WHERE id = ?", (msg['id'],))
                    print(f"🔔 Отправлено напоминание для письма #{msg['id']}")
            
            conn.commit()
            conn.close()
        except Exception as e:
            print(f"❌ Ошибка в планировщике: {e}")
        
        time.sleep(30)

# ========== ЗАПУСК ==========
if __name__ == '__main__':
    init_db()
    # Запускаем фоновый поток для отправки
    scheduler_thread = threading.Thread(target=message_scheduler, daemon=True)
    scheduler_thread.start()
    print("🚀 Сервер запущен на http://localhost:5000")
    print("📧 Отправка писем через Яндекс SMTP активна")
    app.run(host='0.0.0.0', port=5000, debug=False)
