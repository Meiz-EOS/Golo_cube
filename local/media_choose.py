import os
import time
import json
import queue
import signal
import shutil
import getpass
import threading
import subprocess
import requests
from flask import Flask, send_file, request, jsonify
import tkinter as tk
from PIL import Image, ImageTk, ImageEnhance

# ---------- Configuration ----------
DOWNLOAD_FOLDER = './downloaded_images'
STATIC_IMAGES_FOLDER = '/home/un/Downloads'  # Путь к статике
ANIMATION_LOG = "/tmp/animation_player.log"

# 🔥 НАСТРОЙКИ АВТО-ОБНОВЛЕНИЯ
SERVER_UPDATE_URL = "https://myTree.pythonanywhere.com/admin/update_url"
ADMIN_SECRET = "GOLO_CUBE_SECRET_KEY_2025" # Должен совпадать с сервером!

# Значения по умолчанию
USER_BRIGHTNESS = 1.0
USER_CONTRAST = 1.0

# Настройки для статичных картинок
BRIGHTNESS_STATIC = {"1": 1.25, "2": 1.40, "3": 1.10}
CONTRAST_STATIC = {"1": 1.20, "2": 1.35, "3": 1.00}
VIDEO_BRIGHTNESS = {"1": 10, "2": -5, "3": 20}
VIDEO_SPEED = {"1": 1.0, "2": 0.8, "3": 1.2}

# Создаем папки
os.makedirs(DOWNLOAD_FOLDER, exist_ok=True)
os.makedirs(STATIC_IMAGES_FOLDER, exist_ok=True)

app = Flask(__name__)

# === ФУНКЦИЯ АВТО-ОБНОВЛЕНИЯ NGROK ===
def sync_ngrok_url_to_server():
    """Находит локальный Ngrok и отправляет его адрес на сервер"""
    print("⏳ Ожидание запуска ngrok (5 сек)...")
    time.sleep(5) # Даем время ngrok запуститься
    
    max_retries = 10
    for i in range(max_retries):
        try:
            # Спрашиваем у локального API ngrok, какой у нас туннель
            response = requests.get("http://127.0.0.1:4040/api/tunnels", timeout=2)
            data = response.json()
            tunnels = data.get('tunnels', [])
            
            if tunnels:
                # Берем первый публичный URL (обычно https)
                public_url = tunnels[0]['public_url']
                webhook_url = f"{public_url}/webhook"
                
                print(f"🔎 Найден туннель: {public_url}")
                
                # Отправляем на сервер
                payload = {
                    "secret": ADMIN_SECRET,
                    "url": webhook_url
                }
                
                print(f"📡 Отправка нового адреса на сервер...")
                r = requests.post(SERVER_UPDATE_URL, json=payload, timeout=10)
                
                if r.status_code == 200:
                    print(f"✅ СЕРВЕР ОБНОВЛЕН! Теперь он шлет данные на: {webhook_url}")
                    return # Успех, выходим
                else:
                    print(f"❌ Ошибка обновления сервера: {r.status_code} {r.text}")
            else:
                print("⚠️ Туннели ngrok не найдены (ngrok запущен?)")
                
        except Exception as e:
            print(f"⚠️ Попытка {i+1}/{max_retries}: Не могу подключиться к ngrok API ({e})")
            
        time.sleep(3) # Ждем перед повтором
        
    print("❌ Не удалось синхронизировать адрес. Сервер не сможет присылать файлы.")

# ---------- Image Viewer ----------
class ImageViewer:
    def __init__(self):
        self.root = None
        self.current_window = None
        self.image_queue = queue.Queue()
        self.is_running = True
        self.current_music_process = None
        self.music_enabled = False
        self.current_video_process = None

        # Статика (имена файлов)
        self.static_images = {"1": "static_1.png", "2": "static_2.png", "3": "static_3.png"}
        self.static_music = {"1": "music_1.mp3", "2": "music_2.mp3", "3": "music_3.mp3"}
        self.static_animation = {"1": "animation_1.mp4", "2": "animation_2.mp4", "3": "animation_3.mp4"}

        self.setup_webhook()

    def setup_webhook(self):
        @app.route('/webhook', methods=['POST'])
        def webhook():
            try:
                filename = None
                if 'file' in request.files:
                    f = request.files['file']
                    if f and f.filename:
                        filename = f.filename
                        save_path = os.path.join(DOWNLOAD_FOLDER, filename)
                        f.save(save_path)
                        print(f"💾 PUSH получен файл: {filename}")

                data = {}
                if request.form: data = request.form.to_dict()
                elif request.is_json: data = request.get_json() or {}

                if filename:
                    data['filename'] = filename
                    data['type'] = 'custom_image'

                print(f"🔔 WEBHOOK DATA: {data}")
                self.image_queue.put(data)
                return jsonify({'status': 'ok'})
            except Exception as e:
                print(f"❌ Webhook error: {e}")
                return jsonify({'error': str(e)}), 500

    def start(self):
        self.root = tk.Tk()
        self.root.withdraw()

        self.process_queue()
        
        # Запускаем Flask сервер (приемник)
        threading.Thread(target=self.run_flask, daemon=True).start()
        
        # 🔥 ЗАПУСКАЕМ АВТО-СИНХРОНИЗАЦИЮ АДРЕСА
        threading.Thread(target=sync_ngrok_url_to_server, daemon=True).start()

        print("✅ ImageViewer started (AUTO-UPDATE MODE)")
        try:
            self.root.mainloop()
        except KeyboardInterrupt:
            self.is_running = False
            self.stop_all_media()
            try: self.root.quit()
            except: pass

    def process_queue(self):
        if not self.is_running: return
        try:
            data = self.image_queue.get_nowait()
            self.process_data(data)
        except queue.Empty: pass
        self.root.after(100, self.process_queue)

    def process_data(self, data):
        try:
            image_type = data.get('type', 'custom_image')
            image_number = str(data.get('image_number', '0'))
            
            try: incoming_brightness = float(data.get('brightness', 1.0))
            except: incoming_brightness = 1.0
            
            try: incoming_contrast = float(data.get('contrast', 1.0))
            except: incoming_contrast = 1.0

            music_data = data.get('music_data', 'off')
            lighting_data = data.get('lighting_data', 'off')
            filename = data.get('filename')

            # Применяем настройки
            if image_type == 'static_image':
                b = BRIGHTNESS_STATIC.get(image_number, incoming_brightness)
                c = CONTRAST_STATIC.get(image_number, incoming_contrast)
                self.handle_static_image(image_number, b, c, music_data, lighting_data)
            else:
                self.handle_custom_image(filename, USER_BRIGHTNESS, USER_CONTRAST, music_data, lighting_data)
                
        except Exception as e:
            print(f"❌ Process data error: {e}")

    # ... (Остальные методы медиа: start_music, start_animation, handle_static_image, etc. - без изменений)
    # Я сократил их здесь для краткости, так как они не меняются.
    # Вставьте сюда ваши стандартные методы проигрывания из прошлого файла (start_music, stop_music, etc.)
    # Если нужно, я могу вывести их полностью.

    def start_music(self, music_file=None):
        self.stop_music()
        # (Логика поиска музыки как в прошлом файле)
        # Упрощенно для примера:
        path = None
        if music_file and os.path.exists(music_file): path = music_file
        elif music_file: path = os.path.join(DOWNLOAD_FOLDER, music_file)
        
        if not path or not os.path.exists(path): path = "/home/un/Downloads/music.mp3"
        
        if os.path.exists(path):
            try:
                self.current_music_process = subprocess.Popen(['mpg123', '--loop', '-1', path], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, preexec_fn=os.setsid)
                self.music_enabled = True
            except: pass

    def stop_music(self):
        if self.current_music_process:
            try: os.killpg(os.getpgid(self.current_music_process.pid), signal.SIGTERM)
            except: pass
        subprocess.run(['pkill', 'mpg123'], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        self.music_enabled = False

    def stop_all_media(self):
        self.stop_music()
        # self.stop_animation() # Добавьте метод stop_animation из старого кода

    def handle_static_image(self, num, b, c, mus, light):
        img_name = self.static_images.get(num)
        if img_name:
            path = os.path.join(STATIC_IMAGES_FOLDER, img_name)
            if os.path.exists(path):
                self.show_image_rotated(path, b, c, mus, light)

    def handle_custom_image(self, filename, b, c, mus, light):
        if not filename: return
        path = os.path.join(DOWNLOAD_FOLDER, filename)
        if os.path.exists(path):
            self.show_image_rotated(path, b, c, mus, light)

    def show_image_rotated(self, path, b, c, mus, light):
        self.close_current_window()
        self.stop_all_media()
        
        # Музыка
        if mus == 'on': self.start_music()
        
        try:
            window = tk.Toplevel(self.root)
            self.current_window = window
            window.attributes('-fullscreen', True)
            window.attributes('-topmost', True)
            window.configure(bg='black')
            
            w, h = self.root.winfo_screenwidth(), self.root.winfo_screenheight()
            img = Image.open(path).rotate(180, expand=True)
            img = ImageEnhance.Brightness(img).enhance(float(b))
            img = ImageEnhance.Contrast(img).enhance(float(c))
            img = img.resize((w, h), Image.LANCZOS)
            
            photo = ImageTk.PhotoImage(img)
            lbl = tk.Label(window, image=photo, bg='black')
            lbl.image = photo
            lbl.pack()
            
            window.bind('<Escape>', lambda e: self.close_image())
            window.focus_force()
        except Exception as e:
            print(f"Show error: {e}")

    def close_image(self):
        self.stop_all_media()
        self.close_current_window()

    def close_current_window(self):
        if self.current_window:
            try: self.current_window.destroy()
            except: pass
        self.current_window = None

    def run_flask(self):
        app.run(host='0.0.0.0', port=5000, debug=False, use_reloader=False)

if __name__ == '__main__':
    print("🚀 Starting Cube Client")
    ImageViewer().start()