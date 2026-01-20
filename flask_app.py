
# from flask import Flask, request, jsonify, send_file
# import os
# import hashlib
# import requests
# from datetime import datetime
# from werkzeug.utils import secure_filename
# import threading
# import json

# app = Flask(__name__)

# # === Настройки ===
# # Создаем лог-файл для статических изображений
# STATIC_IMAGES_LOG = '/home/myTree/mysite/static_images.log'
# if not os.path.exists(STATIC_IMAGES_LOG):
#     with open(STATIC_IMAGES_LOG, 'w') as f:
#         f.write("Static Images Log\n")
#         f.write("=================\n")
# UPLOAD_FOLDER = '/home/myTree/mysite/uploads'
# ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg'}
# OBSERVER_ENABLED = True
# #   OBSERVER_URL = # В файле Flask сервера найдите строку с OBSERVER_URL и замените на:
# OBSERVER_URL = 'http://134.17.185.25:5000/webhook'  # 👈 замени на свой ngrok или внешний адрес

# # === Инициализация ===
# os.makedirs(UPLOAD_FOLDER, exist_ok=True)
# app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER
# app.config['MAX_CONTENT_LENGTH'] = 16 * 1024 * 1024  # 16 MB


# # === Вспомогательные функции ===
# def allowed_file(filename):
#     return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

# def file_hash(data):
#     return hashlib.md5(data).hexdigest()

# def find_existing_file(file_hash):
#     """Ищет существующий файл с таким же хешем"""
#     for filename in os.listdir(app.config['UPLOAD_FOLDER']):
#         filepath = os.path.join(app.config['UPLOAD_FOLDER'], filename)
#         if os.path.isfile(filepath):
#             try:
#                 with open(filepath, 'rb') as f:
#                     existing_hash = hashlib.md5(f.read()).hexdigest()
#                 if existing_hash == file_hash:
#                     return filename
#             except Exception as e:
#                 print(f"⚠️ Ошибка чтения файла {filename}: {e}")
#     return None

# def notify_observer_async(filename, user_id, file_size, is_duplicate=False, image_data=None):
#     """Асинхронно уведомляем наблюдателя"""
#     def send_notification():
#         payload = {
#             "filename": filename,
#             "user_id": user_id,
#             "file_size": file_size,
#             "timestamp": datetime.now().isoformat(),
#             "download_url": f"https://myTree.pythonanywhere.com/download/{filename}",
#             "is_duplicate": is_duplicate
#         }

#         # Добавляем данные изображения, если они есть
#         if image_data:
#             payload.update(image_data)

#         try:
#             print(f"🔔 Уведомляю наблюдателя: {filename}")
#             print(f"📊 Данные: {image_data}")
#             r = requests.post(OBSERVER_URL, json=payload, timeout=10)
#             print(f"Ответ наблюдателя: {r.status_code}")
#         except Exception as e:
#             print(f"⚠️ Ошибка уведомления наблюдателя: {e}")

#     if OBSERVER_ENABLED:
#         threading.Thread(target=send_notification, daemon=True).start()

# def log_image_data(image_number, user_id, brightness, music_data, lighting_data):
#     """Логирует данные изображения"""
#     log_entry = {
#         "timestamp": datetime.now().isoformat(),
#         "image_number": image_number,
#         "user_id": user_id,
#         "brightness": brightness,
#         "music_data": music_data,
#         "lighting_data": lighting_data
#     }

#     # Логируем в файл
#     with open(STATIC_IMAGES_LOG, 'a') as f:
#         f.write(json.dumps(log_entry) + '\n')

#     print(f"📝 Записаны данные для изображения {image_number}:")
#     print(f"   👤 Пользователь: {user_id}")
#     print(f"   💡 Яркость: {brightness}")
#     print(f"   🎵 Музыка: {music_data}")
#     print(f"   🔦 Подсветка: {lighting_data}")

# @app.route('/files')
# def list_files():
#     try:
#         files = []
#         for filename in os.listdir(app.config['UPLOAD_FOLDER']):
#             filepath = os.path.join(app.config['UPLOAD_FOLDER'], filename)
#             if os.path.isfile(filepath):
#                 files.append({
#                     'filename': filename,
#                     'url': f"https://myTree.pythonanywhere.com/download/{filename}",
#                     'upload_time': datetime.fromtimestamp(os.path.getctime(filepath)).isoformat()
#                 })
#         return jsonify({'files': files}), 200
#     except Exception as e:
#         return jsonify({'error': str(e)}), 500

# # === Роуты ===

# @app.route('/')
# def index():
#     return jsonify({"message": "Flask upload server is running!"})

# @app.route('/upload', methods=['POST'])
# def upload():
#     try:
#         # Получаем данные формы
#         image_number = request.form.get('image_number')
#         user_id = request.form.get('user_id', 'anonymous')
#         brightness = request.form.get('brightness', '0.7')
#         music_data = request.form.get('music_data', 'off')
#         lighting_data = request.form.get('lighting_data', 'off')

#         print(f"📨 Получены данные:")
#         print(f"   Номер изображения: {image_number}")
#         print(f"   Пользователь: {user_id}")
#         print(f"   Яркость: {brightness}")
#         print(f"   Музыка: {music_data}")
#         print(f"   Подсветка: {lighting_data}")

#         # Обработка статических изображений (1, 2, 3)
#         if image_number and image_number in ['1', '2', '3']:
#             print(f"✅ Получена цифра от {user_id}: {image_number}")

#             # Логируем данные
#             log_image_data(image_number, user_id, brightness, music_data, lighting_data)

#             # Подготавливаем данные для наблюдателя
#             image_data = {
#                 "image_number": image_number,
#                 "brightness": float(brightness),
#                 "music_data": music_data,
#                 "lighting_data": lighting_data,
#                 "type": "static_image"
#             }

#             # Уведомляем наблюдателя о цифре
#             notify_observer_async(f"static_image_{image_number}", user_id, 0,
#                                 is_duplicate=False, image_data=image_data)

#             return jsonify({
#                 "message": "Static image data received",
#                 "image_number": image_number,
#                 "user_id": user_id,
#                 "brightness": brightness,
#                 "music_data": music_data,
#                 "lighting_data": lighting_data,
#                 "status": "static_ok"
#             }), 200

#         # Обработка пользовательских изображений (image_number = 0)
#         if 'file' not in request.files:
#             return jsonify({'error': 'No file field'}), 400

#         file = request.files['file']

#         if file.filename == '':
#             return jsonify({'error': 'Empty filename'}), 400

#         if not allowed_file(file.filename):
#             return jsonify({'error': 'Invalid file type'}), 400

#         # Читаем байты и вычисляем хеш
#         data = file.read()
#         file_hash_value = file_hash(data)

#         # Проверяем, существует ли уже такой файл
#         existing_filename = find_existing_file(file_hash_value)

#         # ВАЖНО: всегда используем существующее имя файла если нашли дубликат
#         if existing_filename:
#             print(f"♻️ Файл уже существует: {existing_filename}")
#             filename = existing_filename  # Используем существующее имя
#             file_size = os.path.getsize(os.path.join(app.config['UPLOAD_FOLDER'], existing_filename))
#             status = "duplicate"
#         else:
#             # Если файл новый - сохраняем
#             timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
#             safe_name = secure_filename(file.filename)
#             filename = f"{user_id}_{timestamp}_{file_hash_value[:6]}_{safe_name}"

#             save_path = os.path.join(app.config['UPLOAD_FOLDER'], filename)
#             with open(save_path, "wb") as f:
#                 f.write(data)

#             file_size = os.path.getsize(save_path)
#             status = "ok"
#             print(f"✅ Получен НОВЫЙ файл: {filename} ({file_size} байт) от {user_id}")

#         # 👇 ВАЖНО: ВСЕГДА отправляем данные на Raspberry Pi, даже для дубликатов!
#         image_data = {
#             "image_number": "0",  # 0 для пользовательских изображений
#             "brightness": float(brightness),
#             "music_data": music_data,
#             "lighting_data": lighting_data,
#             "type": "custom_image",
#             "filename": filename  # ← Всегда отправляем имя файла
#         }

#         # ВСЕГДА отправляем уведомление наблюдателю
#         notify_observer_async(filename, user_id, file_size,
#                             is_duplicate=(existing_filename is not None),
#                             image_data=image_data)

#         return jsonify({
#             "message": "Upload successful" if status == "ok" else "File already exists",
#             "filename": filename,
#             "user_id": user_id,
#             "file_size": file_size,
#             "brightness": brightness,
#             "music_data": music_data,
#             "lighting_data": lighting_data,
#             "status": status
#         }), 200

#     except Exception as e:
#         print(f"❌ Ошибка загрузки: {e}")
#         return jsonify({'error': str(e)}), 500

# @app.route('/download/<filename>', methods=['GET'])
# def download(filename):
#     try:
#         path = os.path.join(app.config['UPLOAD_FOLDER'], filename)
#         if os.path.exists(path):
#             return send_file(path)
#         return jsonify({'error': 'File not found'}), 404
#     except Exception as e:
#         return jsonify({'error': str(e)}), 500

# # Новый роут для получения логов
# @app.route('/logs/static_images', methods=['GET'])
# def get_static_images_log():
#     try:
#         if os.path.exists(STATIC_IMAGES_LOG):
#             with open(STATIC_IMAGES_LOG, 'r') as f:
#                 logs = f.readlines()
#             return jsonify({'logs': logs}), 200
#         else:
#             return jsonify({'error': 'Log file not found'}), 404
#     except Exception as e:
#         return jsonify({'error': str(e)}), 500

# if __name__ == '__main__':
#     app.run(debug=True)
from flask import Flask, request, jsonify, send_file
import os
import hashlib
import requests
from datetime import datetime
from werkzeug.utils import secure_filename
import threading
import json

app = Flask(__name__)

# === Настройки ===
STATIC_IMAGES_LOG = '/home/myTree/mysite/static_images.log'
UPLOAD_FOLDER = '/home/myTree/mysite/uploads'
ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg'}
OBSERVER_ENABLED = True
OBSERVER_URL = 'http://134.17.185.25:5000/webhook'

# === Инициализация ===
os.makedirs(UPLOAD_FOLDER, exist_ok=True)
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER
app.config['MAX_CONTENT_LENGTH'] = 16 * 1024 * 1024

if not os.path.exists(STATIC_IMAGES_LOG):
    with open(STATIC_IMAGES_LOG, 'w') as f:
        f.write("Static Images Log\n")
        f.write("=================\n")

# === Вспомогательные функции ===
def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

def file_hash(data):
    return hashlib.md5(data).hexdigest()

def delete_file_after_delay(filename, delay=60):
    """Удаляет файл через указанное время"""
    def delete_file():
        import time
        time.sleep(delay)
        try:
            filepath = os.path.join(app.config['UPLOAD_FOLDER'], filename)
            if os.path.exists(filepath):
                os.remove(filepath)
                print(f"🗑️ Файл удален: {filename}")
            else:
                print(f"⚠️ Файл уже удален: {filename}")
        except Exception as e:
            print(f"❌ Ошибка удаления файла {filename}: {e}")

    threading.Thread(target=delete_file, daemon=True).start()

def notify_observer_async(filename, user_id, file_size, file_data, is_duplicate=False, image_data=None):
    """Асинхронно уведомляем наблюдателя и удаляем файл"""
    def send_notification():
        try:
            # Подготавливаем payload
            files = {
                'file': (filename, file_data, 'image/jpeg')
            }

            payload = {
                "filename": filename,
                "user_id": user_id,
                "file_size": file_size,
                "timestamp": datetime.now().isoformat(),
                "is_duplicate": is_duplicate
            }

            if image_data:
                payload.update(image_data)

            print(f"🚀 Отправляю файл наблюдателю: {filename} ({len(file_data)} байт)")
            r = requests.post(
                OBSERVER_URL,
                data=payload,
                files=files,
                timeout=30
            )
            print(f"📨 Ответ наблюдателя: {r.status_code}")

            if r.status_code == 200:
                print(f"✅ Файл успешно отправлен наблюдателю: {filename}")
                # Удаляем файл после успешной отправки
                delete_file_after_delay(filename, delay=5)  # удаляем через 5 секунд
            else:
                print(f"❌ Ошибка от наблюдателя: {r.text}")
                # Если ошибка, все равно удаляем файл через минуту
                delete_file_after_delay(filename, delay=60)

        except Exception as e:
            print(f"⚠️ Ошибка уведомления наблюдателя: {e}")
            # При ошибке тоже удаляем файл через минуту
            delete_file_after_delay(filename, delay=60)

    if OBSERVER_ENABLED:
        threading.Thread(target=send_notification, daemon=True).start()

def log_image_data(image_number, user_id, brightness, music_data, lighting_data, filename=None):
    """Логирует данные изображения"""
    log_entry = {
        "timestamp": datetime.now().isoformat(),
        "image_number": image_number,
        "user_id": user_id,
        "brightness": brightness,
        "music_data": music_data,
        "lighting_data": lighting_data,
        "filename": filename,
        "type": "custom_image" if image_number == "0" else "static_image"
    }

    with open(STATIC_IMAGES_LOG, 'a') as f:
        f.write(json.dumps(log_entry) + '\n')

    print(f"📝 Записаны данные для изображения {image_number}:")
    print(f"   👤 Пользователь: {user_id}")
    print(f"   💡 Яркость: {brightness}")
    print(f"   🎵 Музыка: {music_data}")
    print(f"   🔦 Подсветка: {lighting_data}")
    if filename:
        print(f"   📁 Файл: {filename}")

@app.route('/files')
def list_files():
    """Показывает текущие файлы (будут автоматически удалены)"""
    try:
        files = []
        for filename in os.listdir(app.config['UPLOAD_FOLDER']):
            filepath = os.path.join(app.config['UPLOAD_FOLDER'], filename)
            if os.path.isfile(filepath):
                files.append({
                    'filename': filename,
                    'url': f"https://myTree.pythonanywhere.com/download/{filename}",
                    'upload_time': datetime.fromtimestamp(os.path.getctime(filepath)).isoformat(),
                    'size': os.path.getsize(filepath)
                })
        return jsonify({'files': files, 'count': len(files)}), 200
    except Exception as e:
        return jsonify({'error': str(e)}), 500

# === Роуты ===

@app.route('/')
def index():
    return jsonify({"message": "Flask upload server is running! Files are auto-deleted after sending to observer."})

@app.route('/upload', methods=['POST'])
def upload():
    try:
        # Получаем данные формы
        image_number = request.form.get('image_number')
        user_id = request.form.get('user_id', 'anonymous')
        brightness = request.form.get('brightness', '0.7')
        music_data = request.form.get('music_data', 'off')
        lighting_data = request.form.get('lighting_data', 'off')

        print(f"📨 Получены данные:")
        print(f"   Номер изображения: {image_number}")
        print(f"   Пользователь: {user_id}")
        print(f"   Яркость: {brightness}")
        print(f"   Музыка: {music_data}")
        print(f"   Подсветка: {lighting_data}")

        # Обработка статических изображений (1, 2, 3)
        if image_number and image_number in ['1', '2', '3']:
            print(f"✅ Получена цифра от {user_id}: {image_number}")

            log_image_data(image_number, user_id, brightness, music_data, lighting_data)

            image_data = {
                "image_number": image_number,
                "brightness": float(brightness),
                "music_data": music_data,
                "lighting_data": lighting_data,
                "type": "static_image"
            }

            # Для статических изображений не нужно отправлять файл
            def send_static_notification():
                try:
                    payload = {
                        "filename": f"static_image_{image_number}",
                        "user_id": user_id,
                        "file_size": 0,
                        "timestamp": datetime.now().isoformat(),
                        "is_duplicate": False
                    }
                    payload.update(image_data)

                    r = requests.post(OBSERVER_URL, json=payload, timeout=10)
                    print(f"📨 Ответ наблюдателя на статическое изображение: {r.status_code}")
                except Exception as e:
                    print(f"⚠️ Ошибка уведомления наблюдателя: {e}")

            if OBSERVER_ENABLED:
                threading.Thread(target=send_static_notification, daemon=True).start()

            return jsonify({
                "message": "Static image data received",
                "image_number": image_number,
                "user_id": user_id,
                "brightness": brightness,
                "music_data": music_data,
                "lighting_data": lighting_data,
                "status": "static_ok"
            }), 200

        # Обработка пользовательских изображений
        if 'file' not in request.files:
            return jsonify({'error': 'No file field'}), 400

        file = request.files['file']

        if file.filename == '':
            return jsonify({'error': 'Empty filename'}), 400

        if not allowed_file(file.filename):
            return jsonify({'error': 'Invalid file type'}), 400

        # Читаем байты и вычисляем хеш
        data = file.read()
        file_hash_value = file_hash(data)

        # Подготавливаем данные изображения
        image_data = {
            "image_number": "0",
            "brightness": float(brightness),
            "music_data": music_data,
            "lighting_data": lighting_data,
            "type": "custom_image"
        }

        # Всегда создаем новый файл (не проверяем дубликаты)
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        safe_name = secure_filename(file.filename)
        filename = f"{user_id}_{timestamp}_{file_hash_value[:8]}_{safe_name}"

        save_path = os.path.join(app.config['UPLOAD_FOLDER'], filename)
        with open(save_path, "wb") as f:
            f.write(data)

        file_size = os.path.getsize(save_path)

        print(f"✅ Получен файл: {filename} ({file_size} байт) от {user_id}")

        log_image_data("0", user_id, brightness, music_data, lighting_data, filename)

        # Отправляем уведомление наблюдателю и удаляем файл после отправки
        notify_observer_async(filename, user_id, file_size, data,
                            is_duplicate=False, image_data=image_data)

        return jsonify({
            "message": "Upload successful. File will be deleted after sending to observer.",
            "filename": filename,
            "user_id": user_id,
            "file_size": file_size,
            "brightness": brightness,
            "music_data": music_data,
            "lighting_data": lighting_data,
            "status": "ok"
        }), 200

    except Exception as e:
        print(f"❌ Ошибка загрузки: {e}")
        return jsonify({'error': str(e)}), 500

@app.route('/download/<filename>', methods=['GET'])
def download(filename):
    """Временная загрузка файла (файл будет удален вскоре после отправки)"""
    try:
        path = os.path.join(app.config['UPLOAD_FOLDER'], filename)
        if os.path.exists(path):
            return send_file(path)
        return jsonify({'error': 'File not found'}), 404
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/logs/static_images', methods=['GET'])
def get_static_images_log():
    try:
        if os.path.exists(STATIC_IMAGES_LOG):
            with open(STATIC_IMAGES_LOG, 'r') as f:
                logs = f.readlines()
            return jsonify({'logs': logs}), 200
        else:
            return jsonify({'error': 'Log file not found'}), 404
    except Exception as e:
        return jsonify({'error': str(e)}), 500

# Роут для принудительной очистки файлов
@app.route('/cleanup', methods=['POST'])
def cleanup_files():
    """Принудительно удаляет все файлы в uploads folder"""
    try:
        deleted_count = 0
        for filename in os.listdir(app.config['UPLOAD_FOLDER']):
            filepath = os.path.join(app.config['UPLOAD_FOLDER'], filename)
            if os.path.isfile(filepath):
                os.remove(filepath)
                deleted_count += 1
                print(f"🗑️ Удален: {filename}")

        return jsonify({'message': f'Deleted {deleted_count} files'}), 200
    except Exception as e:
        return jsonify({'error': str(e)}), 500

if __name__ == '__main__':
    app.run(debug=True)