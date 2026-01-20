import os
import time
import json
import queue
import signal
import threading
import subprocess
import requests
from flask import Flask, request, jsonify
import tkinter as tk
from PIL import Image, ImageTk, ImageEnhance

# CONFIGURATION
DOWNLOAD_FOLDER = './downloaded_images'
STATIC_IMAGES_FOLDER = './static_images'
SERVER_UPDATE_URL = "https://myTree.pythonanywhere.com/admin/update_url"
ADMIN_SECRET = "GOLO_CUBE_SECRET_KEY_2025" 
BRIGHTNESS_STATIC = {"1": 1.25, "2": 1.40, "3": 1.10}
CONTRAST_STATIC = {"1": 1.20, "2": 1.35, "3": 1.00}

os.makedirs(DOWNLOAD_FOLDER, exist_ok=True)
os.makedirs(STATIC_IMAGES_FOLDER, exist_ok=True)

app = Flask(__name__)

# SMART NGROK SYNC
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

class ImageViewer:
    def __init__(self):
        self.root = None
        self.current_window = None
        self.image_queue = queue.Queue()
        self.is_running = True
        self.current_music_process = None
        self.static_images = {"1": "static_1.png", "2": "static_2.png", "3": "static_3.png"}
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
                    data['type'] = 'custom_image'
                
                self.image_queue.put(data)
                return jsonify({'status': 'ok'})
            except Exception as e:
                return jsonify({'error': str(e)}), 500

    def start(self):
        self.root = tk.Tk()
        self.root.withdraw()
        self.process_queue()
        threading.Thread(target=lambda: app.run(host='0.0.0.0', port=5000, use_reloader=False), daemon=True).start()
        threading.Thread(target=sync_ngrok_url_to_server, daemon=True).start()
        print("✅ GUI Started")
        try: self.root.mainloop()
        except KeyboardInterrupt: self.is_running = False

    def process_queue(self):
        if not self.is_running: return
        try:
            self.process_data(self.image_queue.get_nowait())
        except queue.Empty: pass
        self.root.after(100, self.process_queue)

    def process_data(self, data):
        try:
            cmd_type = data.get('type')
            
            # === ЛОГИКА ГРОМКОСТИ ===
            if cmd_type == 'volume':
                action = data.get('action')
                self.set_volume(action)
                return

            # === ЛОГИКА КАРТИНОК ===
            img_num = str(data.get('image_number', '0'))
            b = float(data.get('brightness', 1.0))
            c = float(data.get('contrast', 1.0))
            mus = data.get('music_data', 'off')
            fname = data.get('filename')

            if cmd_type == 'static_image':
                b = BRIGHTNESS_STATIC.get(img_num, b)
                c = CONTRAST_STATIC.get(img_num, c)
                self.handle_static_image(img_num, b, c, mus)
            else:
                self.handle_custom_image(fname, 1.0, 1.0, mus)
        except Exception as e: print(f"Error: {e}")

    # === УПРАВЛЕНИЕ ЗВУКОМ (ALSA) ===
    def set_volume(self, action):
        try:
            cmd = []
            # Используем pactl для управления системным микшером PipeWire
            if action == 'up':
                cmd = ['pactl', 'set-sink-volume', '@DEFAULT_SINK@', '+10%']
                print("🔊 Громкость +10% (PipeWire)")
            elif action == 'down':
                cmd = ['pactl', 'set-sink-volume', '@DEFAULT_SINK@', '-10%']
                print("🔉 Громкость -10% (PipeWire)")
            elif action == 'max':
                cmd = ['pactl', 'set-sink-volume', '@DEFAULT_SINK@', '100%']
                # Принудительно включаем звук (unmute) при максимуме
                subprocess.run(['pactl', 'set-sink-mute', '@DEFAULT_SINK@', '0'], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                print("📢 Громкость MAX (PipeWire)")
            elif action == 'mute':
                cmd = ['pactl', 'set-sink-mute', '@DEFAULT_SINK@', 'toggle']
                print("🔇 Звук MUTE (Toggle)")
            
            if cmd:
                # Запускаем команду
                res = subprocess.run(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE)
                if res.returncode != 0:
                    # Если pactl не сработал, пробуем старый метод amixer как запасной вариант
                    print(f"⚠️ pactl failed, пробуем amixer...")
                    self.set_volume_fallback(action)

        except Exception as e:
            print(f"Ошибка звука: {e}")

    def start_music(self, music_file=None):
        self.stop_music()
        path = music_file if music_file else "./music.mp3"
        if os.path.exists(path):
            self.current_music_process = subprocess.Popen(['mpg123', '--loop', '-1', path], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, preexec_fn=os.setsid)

    def stop_music(self):
        if self.current_music_process:
            try: os.killpg(os.getpgid(self.current_music_process.pid), signal.SIGTERM)
            except: pass
        subprocess.run(['pkill', 'mpg123'], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

    def stop_all_media(self):
        self.stop_music()

    def handle_static_image(self, num, b, c, mus):
        path = os.path.join(STATIC_IMAGES_FOLDER, self.static_images.get(num, ""))
        if os.path.exists(path): self.show_image(path, b, c, mus)

    def handle_custom_image(self, fname, b, c, mus):
        if fname:
            path = os.path.join(DOWNLOAD_FOLDER, fname)
            if os.path.exists(path): self.show_image(path, b, c, mus)

    def show_image(self, path, b, c, mus):
        if self.current_window: self.current_window.destroy()
        self.stop_music()
        if mus == 'on': self.start_music()
        
        win = tk.Toplevel(self.root)
        self.current_window = win
        win.attributes('-fullscreen', True)
        win.attributes('-topmost', True)
        win.configure(bg='black')
        
        w, h = self.root.winfo_screenwidth(), self.root.winfo_screenheight()
        img = Image.open(path).rotate(180, expand=True)
        img = ImageEnhance.Brightness(img).enhance(b)
        img = ImageEnhance.Contrast(img).enhance(c)
        img = img.resize((w, h), Image.LANCZOS)
        
        photo = ImageTk.PhotoImage(img)
        lbl = tk.Label(win, image=photo, bg='black', bd=0)
        lbl.image = photo
        lbl.pack(expand=True, fill='both')
        win.bind('<Escape>', lambda e: (self.stop_music(), win.destroy()))
        win.focus_force()

if __name__ == '__main__':
    ImageViewer().start()