import os
import time
import json
import queue
import signal
import threading
import subprocess
import requests
from flask import Flask, request, jsonify
import sys

# --- БЛОК ИНИЦИАЛИЗАЦИИ ЗВУКА ---
HAS_PULSE = False 
try:
    import pulsectl
    HAS_PULSE = True
except ImportError:
    HAS_PULSE = False
    print("⚠️ ВНИМАНИЕ: Библиотека 'pulsectl' не найдена. Звук регулироваться не будет.")

# --- ОПРЕДЕЛЕНИЕ ПУТЕЙ (АБСОЛЮТНАЯ ПРИВЯЗКА) ---
# Получаем точный путь к папке, где лежит этот скрипт (media_choose.py)
BASE_DIR = os.path.dirname(os.path.abspath(__file__))

DOWNLOAD_FOLDER = os.path.join(BASE_DIR, 'downloaded_media')
STATIC_VIDEO_FOLDER = os.path.join(BASE_DIR, 'static_videos')

SERVER_UPDATE_URL = "https://myTree.pythonanywhere.com/admin/update_url"
ADMIN_SECRET = "GOLO_CUBE_SECRET_KEY_2025" 

# Настройки изображения для MPV (Яркость/Контраст: -100 до 100)
VIDEO_SETTINGS = {
    "1": {"brightness": 25, "contrast": 20},
    "2": {"brightness": 40, "contrast": 35},
    "3": {"brightness": 10, "contrast": 0},
}

# Создаем папки, если их нет
os.makedirs(DOWNLOAD_FOLDER, exist_ok=True)
os.makedirs(STATIC_VIDEO_FOLDER, exist_ok=True)

app = Flask(__name__)

# --- СИНХРОНИЗАЦИЯ NGROK ---
def sync_ngrok_url_to_server():
    time.sleep(3)
    try:
        response = requests.get("http://127.0.0.1:4040/api/tunnels", timeout=1)
        tunnels = response.json().get('tunnels', [])
        if tunnels:
            url = tunnels[0]['public_url'] + "/webhook"
            print(f"✅ ONLINE: {url}")
            requests.post(SERVER_UPDATE_URL, json={"secret": ADMIN_SECRET, "url": url}, timeout=5)
    except: pass

class MediaController:
    def __init__(self):
        self.cmd_queue = queue.Queue()
        self.is_running = True
        self.current_process = None
        # Имена файлов должны быть именно такими внутри папки static_videos
        self.static_files = {
            "1": "video_1.mp4",
            "2": "video_2.mp4",
            "3": "video_3.mp4"
        }
        self.setup_webhook()

    def setup_webhook(self):
        @app.route('/webhook', methods=['POST'])
        def webhook():
            try:
                fname = None
                if 'file' in request.files:
                    f = request.files['file']
                    fname = f.filename
                    f.save(os.path.join(DOWNLOAD_FOLDER, fname))
                
                data = request.form.to_dict() if request.form else (request.get_json() or {})
                if fname: 
                    data['filename'] = fname
                    data['type'] = 'custom_video'
                
                self.cmd_queue.put(data)
                return jsonify({'status': 'ok'})
            except Exception as e:
                return jsonify({'error': str(e)}), 500

    def start(self):
        threading.Thread(target=lambda: app.run(host='0.0.0.0', port=5000, use_reloader=False), daemon=True).start()
        threading.Thread(target=sync_ngrok_url_to_server, daemon=True).start()
        
        print(f"✅ MEDIA CONTROLLER STARTED")
        print(f"📂 Корневая директория: {BASE_DIR}")
        print(f"📂 Папка с видео (ожидаемая): {STATIC_VIDEO_FOLDER}")
        
        try:
            while self.is_running:
                try:
                    data = self.cmd_queue.get(timeout=1)
                    self.process_data(data)
                except queue.Empty:
                    pass
        except KeyboardInterrupt:
            self.stop_all()

    def process_data(self, data):
        try:
            cmd_type = data.get('type')
            print(f"⚙️ Processing: {cmd_type}")

            if cmd_type == 'stop':
                self.stop_all()
                return

            if cmd_type == 'volume':
                self.set_volume(data.get('action'))
                return

            # Логика воспроизведения
            fname = data.get('filename')
            img_num = str(data.get('image_number', '0'))
            
            target_path = None
            settings = {"brightness": 0, "contrast": 0}

            # 1. СТАТИЧЕСКИЕ ВИДЕО (Медиа 1, 2, 3)
            if cmd_type == 'static_image': 
                if img_num in self.static_files:
                    target_path = os.path.join(STATIC_VIDEO_FOLDER, self.static_files[img_num])
                    settings = VIDEO_SETTINGS.get(img_num, settings)
                else:
                    print(f"⚠️ Неизвестный номер медиа: {img_num}")
            
            # 2. КАСТОМНЫЕ ФАЙЛЫ
            elif cmd_type == 'custom_video' or (cmd_type == 'custom_image' and fname):
                if fname:
                    target_path = os.path.join(DOWNLOAD_FOLDER, fname)
            
            # ПРОВЕРКА И ЗАПУСК
            if target_path:
                if os.path.exists(target_path):
                    self.play_video(target_path, settings)
                else:
                    print(f"❌ ФАЙЛ НЕ НАЙДЕН ПО ПУТИ: {target_path}")
                    print(f"   Убедитесь, что файл '{self.static_files.get(img_num, '???')}' лежит в папке 'static_videos' рядом со скриптом.")
            else:
                print("⚠️ Путь к файлу не сформирован.")

        except Exception as e:
            print(f"Error processing: {e}")

    def play_video(self, path, settings):
        self.stop_all()
        
        cmd = [
            'mpv',
            '--loop',
            '--fs',
            '--video-rotate=180',
            f'--brightness={settings["brightness"]}',
            f'--contrast={settings["contrast"]}',
            '--no-osc',
            path
        ]
        
        print(f"▶️ Запуск: {path}")
        try:
            self.current_process = subprocess.Popen(
                cmd, 
                stdout=subprocess.DEVNULL, 
                stderr=subprocess.DEVNULL
            )
        except FileNotFoundError:
            print("❌ ОШИБКА: 'mpv' не установлен! (sudo apt install mpv)")

    def stop_all(self):
        if self.current_process:
            print("⏹️ Стоп")
            try:
                self.current_process.terminate()
                self.current_process.wait(timeout=1)
            except:
                try: self.current_process.kill() 
                except: pass
            self.current_process = None
        subprocess.run(['pkill', 'mpv'], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

    def set_volume(self, action):
        if not HAS_PULSE: return
        try:
            with pulsectl.Pulse('golo-volume') as pulse:
                sinks = pulse.sink_list()
                for sink in sinks:
                    if action == 'up': pulse.volume_change_all_chans(sink, 0.1)
                    elif action == 'down': pulse.volume_change_all_chans(sink, -0.1)
                    elif action == 'max': 
                        pulse.volume_set_all_chans(sink, 1.0)
                        pulse.mute(sink, False)
                    elif action == 'mute': pulse.mute(sink, not sink.mute)
        except Exception as e:
            print(f"Audio Error: {e}")

if __name__ == '__main__':
    MediaController().start()