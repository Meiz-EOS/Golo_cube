from flask import Flask, request, jsonify, send_file
import os
import hashlib
import requests
from datetime import datetime
from werkzeug.utils import secure_filename
import threading
import json
import time

app = Flask(__name__)

# === НАСТРОЙКИ БЕЗОПАСНОСТИ ===
# Этот ключ должен совпадать в обоих файлах (на сервере и на кубе)
ADMIN_SECRET = "GOLO_CUBE_SECRET_KEY_2025"

# === ПУТИ ===
BASE_DIR = '/home/myTree/mysite'
STATIC_IMAGES_LOG = os.path.join(BASE_DIR, 'static_images.log')
UPLOAD_FOLDER = os.path.join(BASE_DIR, 'uploads')
CONFIG_FILE = os.path.join(BASE_DIR, 'observer_url.txt') # Файл для хранения адреса

ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg'}
OBSERVER_ENABLED = True

# === ЗАГРУЗКА АДРЕСА ===
# При запуске сервера читаем последний известный адрес из файла
if os.path.exists(CONFIG_FILE):
    with open(CONFIG_FILE, 'r') as f:
        OBSERVER_URL = f.read().strip()
    print(f"🔄 Адрес восстановлен из файла: {OBSERVER_URL}")
else:
    OBSERVER_URL = 'http://localhost:5000/webhook' # Заглушка

# === ИНИЦИАЛИЗАЦИЯ ===
os.makedirs(UPLOAD_FOLDER, exist_ok=True)
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER
app.config['MAX_CONTENT_LENGTH'] = 16 * 1024 * 1024

if not os.path.exists(STATIC_IMAGES_LOG):
    with open(STATIC_IMAGES_LOG, 'w') as f:
        f.write("Static Images Log\n=================\n")

# === ВСПОМОГАТЕЛЬНЫЕ ФУНКЦИИ ===
def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

def file_hash(data):
    return hashlib.md5(data).hexdigest()

def delete_file_after_delay(filename, delay=60):
    def delete_file():
        time.sleep(delay)
        try:
            filepath = os.path.join(app.config['UPLOAD_FOLDER'], filename)
            if os.path.exists(filepath):
                os.remove(filepath)
                print(f"🗑️ Удален: {filename}")
        except Exception as e:
            print(f"❌ Ошибка удаления {filename}: {e}")
    threading.Thread(target=delete_file, daemon=True).start()

def notify_observer_async(filename, user_id, file_size, file_data, is_duplicate=False, image_data=None):
    """Отправляет данные на Куб по текущему OBSERVER_URL"""
    def send_notification():
        # Если адрес пустой или локальный, нет смысла слать
        if 'localhost' in OBSERVER_URL or '127.0.0.1' in OBSERVER_URL:
            print(f"⚠️ Отправка пропущена, адрес не настроен: {OBSERVER_URL}")
            return

        try:
            files = {'file': (filename, file_data, 'image/jpeg')}
            payload = {
                "filename": filename,
                "user_id": user_id,
                "file_size": file_size,
                "timestamp": datetime.now().isoformat(),
                "is_duplicate": is_duplicate
            }
            if image_data: payload.update(image_data)

            print(f"🚀 [PUSH] Отправка на {OBSERVER_URL}...")
            r = requests.post(OBSERVER_URL, data=payload, files=files, timeout=30)
            
            if r.status_code == 200:
                print(f"✅ Успешно доставлено: {filename}")
                delete_file_after_delay(filename, delay=5)
            else:
                print(f"❌ Ошибка клиента: {r.status_code} - {r.text}")
                delete_file_after_delay(filename, delay=60)

        except Exception as e:
            print(f"⚠️ Ошибка связи с Кубом: {e}")
            delete_file_after_delay(filename, delay=60)

    if OBSERVER_ENABLED:
        threading.Thread(target=send_notification, daemon=True).start()

def log_image_data(image_number, user_id, brightness, music_data, lighting_data, filename=None):
    entry = {
        "timestamp": datetime.now().isoformat(),
        "image_number": image_number,
        "user_id": user_id,
        "brightness": brightness,
        "music_data": music_data,
        "lighting_data": lighting_data,
        "filename": filename,
        "type": "custom" if image_number == "0" else "static"
    }
    try:
        with open(STATIC_IMAGES_LOG, 'a') as f:
            f.write(json.dumps(entry) + '\n')
    except: pass

# === РОУТЫ ===

@app.route('/')
def index():
    return jsonify({
        "status": "online",
        "mode": "PUSH AUTOMATIC",
        "current_observer": OBSERVER_URL
    })

# 🔥 НОВЫЙ РОУТ ДЛЯ АВТО-ОБНОВЛЕНИЯ АДРЕСА
@app.route('/admin/update_url', methods=['POST'])
def update_observer_url():
    try:
        data = request.get_json()
        secret = data.get('secret')
        new_url = data.get('url')

        if secret != ADMIN_SECRET:
            print(f"⛔ Попытка взлома с IP {request.remote_addr}")
            return jsonify({"error": "Forbidden"}), 403

        if not new_url:
            return jsonify({"error": "No URL provided"}), 400

        global OBSERVER_URL
        OBSERVER_URL = new_url

        # Сохраняем в файл, чтобы помнить после перезагрузки
        with open(CONFIG_FILE, 'w') as f:
            f.write(new_url)

        print(f"♻️ АДРЕС КУБА ОБНОВЛЕН: {new_url}")
        return jsonify({"message": "URL updated successfully", "new_url": new_url}), 200

    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route('/upload', methods=['POST'])
def upload():
    try:
        image_number = request.form.get('image_number')
        user_id = request.form.get('user_id', 'anon')
        brightness = request.form.get('brightness', '0.7')
        music_data = request.form.get('music_data', 'off')
        lighting_data = request.form.get('lighting_data', 'off')

        # Статика (1, 2, 3)
        if image_number and image_number in ['1', '2', '3']:
            log_image_data(image_number, user_id, brightness, music_data, lighting_data)
            
            # Отправка команды без файла
            def send_cmd():
                try:
                    payload = {
                        "type": "static_image",
                        "image_number": image_number,
                        "brightness": float(brightness),
                        "music_data": music_data,
                        "lighting_data": lighting_data,
                        "filename": f"static_{image_number}",
                        "user_id": user_id
                    }
                    requests.post(OBSERVER_URL, json=payload, timeout=10)
                except Exception as e:
                    print(f"Ошибка отправки команды: {e}")
            
            if OBSERVER_ENABLED:
                threading.Thread(target=send_cmd, daemon=True).start()
                
            return jsonify({"status": "sent"}), 200

        # Файл
        if 'file' not in request.files: return jsonify({'error': 'No file'}), 400
        file = request.files['file']
        if file.filename == '': return jsonify({'error': 'Empty'}), 400
        if not allowed_file(file.filename): return jsonify({'error': 'Type'}), 400

        data = file.read()
        h = file_hash(data)
        safe_name = secure_filename(file.filename)
        filename = f"{user_id}_{datetime.now().strftime('%Y%m%d_%H%M%S')}_{h[:6]}_{safe_name}"
        
        save_path = os.path.join(app.config['UPLOAD_FOLDER'], filename)
        with open(save_path, "wb") as f:
            f.write(data)

        log_image_data("0", user_id, brightness, music_data, lighting_data, filename)
        
        image_data = {
            "image_number": "0", "brightness": float(brightness),
            "music_data": music_data, "lighting_data": lighting_data,
            "type": "custom_image"
        }
        
        notify_observer_async(filename, user_id, os.path.getsize(save_path), data, False, image_data)

        return jsonify({"status": "ok", "filename": filename}), 200

    except Exception as e:
        print(f"Error: {e}")
        return jsonify({'error': str(e)}), 500

if __name__ == '__main__':
    app.run()