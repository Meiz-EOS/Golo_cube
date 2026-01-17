"""
Полный файл Image Viewer с:
- индивидуальной яркостью/контрастом для статических изображений
- индивидуальной яркостью и скоростью для видео (mpv/ffplay/vlc)
- коррекцией gamma для сохранения глубокого чёрного при изменении яркости
- пользовательскими изображениями с фиксированными brightness/contrast = 1.0
"""

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
from PIL import Image, ImageTk

# ---------- Configuration ----------
DOWNLOAD_FOLDER = './downloaded_images'
STATIC_IMAGES_FOLDER = '/home/un/Downloads'  # change if needed
SERVER_URL = "https://myTree.pythonanywhere.com/files"
STATIC_IMAGES_LOG = "https://myTree.pythonanywhere.com/logs/static_images"
ANIMATION_LOG = "/tmp/animation_player.log"

# Default/user forced values for custom images
USER_BRIGHTNESS = 1.0
USER_CONTRAST = 1.0

# --- Individual settings for static images (per image id as string) ---
# brightness: multiplier for PIL Brightness (1.0 == original)
BRIGHTNESS_STATIC = {
    "1": 1.25,
    "2": 1.40,
    "3": 1.10,
    # add more mappings if you have more static images
}

# contrast: multiplier for PIL Contrast (1.0 == original)
CONTRAST_STATIC = {
    "1": 1.20,
    "2": 1.35,
    "3": 1.00,
    # add more mappings as needed
}

# --- Per-video overrides: brightness and playback speed ---
# VIDEO_BRIGHTNESS: can be either:
#  - value in range -100..100 (mpv-style percent), OR
#  - small float like -0.2..0.2 (we will auto-scale to percent)
# VIDEO_SPEED: playback speed (1.0 normal, <1 slower, >1 faster)
VIDEO_BRIGHTNESS = {
    "1": 10,    # mpv brightness +10
    "2": -5,    # mpv brightness -5
    "3": 20,    # mpv brightness +20
}

VIDEO_SPEED = {
    "1": 1.0,
    "2": 0.8,
    "3": 1.2,
}

# Static asset names (in STATIC_IMAGES_FOLDER)
os.makedirs(DOWNLOAD_FOLDER, exist_ok=True)
os.makedirs(STATIC_IMAGES_FOLDER, exist_ok=True)

app = Flask(__name__)

# ---------- Image Viewer ----------
class ImageViewer:
    def __init__(self):
        self.root = None
        self.current_window = None
        self.image_queue = queue.Queue()
        self.is_running = True

        # Media processes
        self.current_music_process = None
        self.music_enabled = False
        self.current_video_process = None

        self.current_image_data = None
        self.last_processed_data = {}

        # Static assets (filenames located in STATIC_IMAGES_FOLDER)
        self.static_images = {
            "1": "static_1.png",
            "2": "static_2.png",
            "3": "static_3.png"
        }
        self.static_music = {
            "1": "music_1.mp3",
            "2": "music_2.mp3",
            "3": "music_3.mp3"
        }
        self.static_animation = {
            "1": "animation_1.mp4",
            "2": "animation_2.mp4",
            "3": "animation_3.mp4"
        }

        self.setup_webhook()

    # ---------- Webhook ----------
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
                        print(f"💾 Received file: {filename}")

                data = {}
                if request.form:
                    data = request.form.to_dict()
                elif request.is_json:
                    data = request.get_json() or {}

                if filename:
                    data['filename'] = filename
                    data['type'] = 'custom_image'

                # Enforce values depending on type:
                if data.get('type') == 'static_image':
                    try:
                        img_num = str(data.get('image_number', '1'))
                    except:
                        img_num = '1'
                    # get values from dictionaries if present
                    brightness = BRIGHTNESS_STATIC.get(img_num, data.get('brightness'))
                    contrast = CONTRAST_STATIC.get(img_num, data.get('contrast'))
                    if brightness is not None:
                        data['brightness'] = brightness
                    if contrast is not None:
                        data['contrast'] = contrast
                elif data.get('type') == 'custom_image':
                    # For custom images always force user values
                    data['brightness'] = USER_BRIGHTNESS
                    data['contrast'] = USER_CONTRAST

                print("🔔 Webhook data:", data)

                if data.get('type') in ['static_image', 'custom_image']:
                    self.image_queue.put(data)
                    return jsonify({'status': 'ok'})
                else:
                    return jsonify({'error': 'invalid type'}), 400
            except Exception as e:
                print("❌ Webhook error:", e)
                return jsonify({'error': str(e)}), 500

    # ---------- Start ----------
    def start(self):
        self.root = tk.Tk()
        self.root.withdraw()

        self.process_queue()

        threading.Thread(target=self.poll_server, daemon=True).start()
        threading.Thread(target=self.poll_static_images, daemon=True).start()
        threading.Thread(target=self.run_flask, daemon=True).start()

        print("✅ ImageViewer started")
        try:
            self.root.mainloop()
        except KeyboardInterrupt:
            self.is_running = False
            self.stop_all_media()
            try:
                self.root.quit()
            except:
                pass

    # ---------- Queue ----------
    def process_queue(self):
        if not self.is_running:
            return
        try:
            data = self.image_queue.get_nowait()
            self.process_data(data)
        except queue.Empty:
            pass
        except Exception as e:
            print("❌ process_queue error:", e)

        self.root.after(100, self.process_queue)

    # ---------- Data Processing ----------
    def process_data(self, data):
        try:
            image_type = data.get('type', 'custom_image')
            image_number = data.get('image_number', '0')

            try:
                incoming_brightness = float(data.get('brightness', 1.0))
            except:
                incoming_brightness = 1.0
            try:
                incoming_contrast = float(data.get('contrast', 1.0))
            except:
                incoming_contrast = 1.0

            music_data = data.get('music_data', None)
            lighting_data = data.get('lighting_data', 'off')
            filename = data.get('filename')

            # Apply enforcement rules:
            if image_type == 'static_image':
                img_num = str(image_number)
                brightness = BRIGHTNESS_STATIC.get(img_num, incoming_brightness if incoming_brightness is not None else USER_BRIGHTNESS)
                contrast = CONTRAST_STATIC.get(img_num, incoming_contrast if incoming_contrast is not None else USER_CONTRAST)
            else:  # custom_image
                brightness = USER_BRIGHTNESS
                contrast = USER_CONTRAST

            print(f"📨 Processing: {image_type} #{image_number} brightness={brightness} contrast={contrast} music={music_data} lighting={lighting_data}")

            if image_type == 'static_image':
                self.handle_static_image(image_number, brightness, contrast, music_data, lighting_data)
            elif image_type == 'custom_image' and filename:
                self.handle_custom_image(filename, brightness, contrast, music_data, lighting_data)
        except Exception as e:
            print("❌ process_data error:", e)

    # ---------- MUSIC ----------
    def start_music(self, music_file=None):
        """
        music_file can be:
          - absolute path to an mp3
          - filename present in DOWNLOAD_FOLDER or STATIC_IMAGES_FOLDER
          - None -> default path /home/un/Downloads/music.mp3
        """
        try:
            self.stop_music()

            music_path = None
            if music_file:
                # already absolute?
                if os.path.isabs(music_file) and os.path.exists(music_file):
                    music_path = music_file
                else:
                    cand1 = os.path.join(DOWNLOAD_FOLDER, music_file)
                    cand2 = os.path.join(STATIC_IMAGES_FOLDER, music_file)
                    if os.path.exists(cand1):
                        music_path = cand1
                    elif os.path.exists(cand2):
                        music_path = cand2
                    elif os.path.exists(music_file):  # maybe relative path
                        music_path = music_file
            else:
                default = "/home/un/Downloads/music.mp3"
                if os.path.exists(default):
                    music_path = default

            if music_path and os.path.exists(music_path):
                print("🎵 Starting music:", music_path)
                try:
                    self.current_music_process = subprocess.Popen(
                        ['mpg123', '--loop', '-1', music_path],
                        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                        preexec_fn=os.setsid
                    )
                    self.music_enabled = True
                except Exception as e:
                    print("❌ failed to start mpg123:", e)
            else:
                print("⚠️ Music not found:", music_file)
        except Exception as e:
            print("❌ start_music error:", e)

    def stop_music(self):
        try:
            if self.current_music_process:
                try:
                    os.killpg(os.getpgid(self.current_music_process.pid), signal.SIGTERM)
                except:
                    pass
                self.current_music_process = None

            subprocess.run(['pkill', 'mpg123'], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            self.music_enabled = False
        except Exception as e:
            print("❌ stop_music error:", e)

    # ---------- ANIMATION ----------
    def start_animation(self, animation_file, image_number=None):
        """
        Start animation/video. Accepts image_number (string or int) to lookup VIDEO_BRIGHTNESS and VIDEO_SPEED.
        Returns True if a player started successfully.
        """
        try:
            self.stop_animation()

            cand1 = os.path.join(STATIC_IMAGES_FOLDER, animation_file)
            cand2 = os.path.join(DOWNLOAD_FOLDER, animation_file)
            cand3 = animation_file  # maybe absolute or relative

            if os.path.exists(cand1):
                path = cand1
            elif os.path.exists(cand2):
                path = cand2
            elif os.path.exists(cand3):
                path = cand3
            else:
                print("⚠️ Animation file not found")
                return False

            screen_w = int(self.root.winfo_screenwidth())
            screen_h = int(self.root.winfo_screenheight())

            # отступы чтобы ничего не обрезалось
            LEFT_OFFSET  = 5
            RIGHT_OFFSET = 100
            TOP_OFFSET   = 0
            BOTTOM_OFFSET = 0

            adj_w = screen_w - LEFT_OFFSET - RIGHT_OFFSET
            adj_h = screen_h - TOP_OFFSET - BOTTOM_OFFSET

            print(f"🎬 Start animation {path} -> {adj_w}x{adj_h}")

            try:
                open(ANIMATION_LOG, "w").close()
            except:
                pass

            env = os.environ.copy()
            if 'DISPLAY' not in env: env['DISPLAY'] = ':0'
            user = getpass.getuser()
            xa = f"/home/{user}/.Xauthority"
            if os.path.exists(xa):
                env['XAUTHORITY'] = xa

            # Determine per-video brightness/speed
            img_num = str(image_number) if image_number is not None else ''
            raw_vid_brightness = VIDEO_BRIGHTNESS.get(img_num, None)
            vid_speed = VIDEO_SPEED.get(img_num, 1.0)

            # Normalize brightness:
            # Accept either percent-like (-100..100) or small floats (-0.2..0.2) -> scale them
            vid_brightness = None
            if raw_vid_brightness is not None:
                try:
                    vb = float(raw_vid_brightness)
                    if abs(vb) <= 2.0:
                        # looks like fraction -> scale to percent
                        vid_brightness = vb * 100.0
                    else:
                        vid_brightness = vb
                except:
                    vid_brightness = None

            # Compute gamma compensation to preserve deep black.
            # Strategy: when brightness > 0 we apply negative gamma to counteract black lift.
            # This formula is empirical and adjustable:
            #    vid_gamma = -(vid_brightness / 100.0) * 1.6
            # clamp gamma to reasonable range (-2.0..2.0)
            vid_gamma = None
            if vid_brightness is not None:
                try:
                    vg = -(vid_brightness / 100.0) * 1.6
                    if vg < -2.0:
                        vg = -2.0
                    if vg > 2.0:
                        vg = 2.0
                    vid_gamma = vg
                except:
                    vid_gamma = None

            cmds = []

            # mpv: используем scale + pad; передаём --brightness и --gamma и --speed если заданы
            mpv_vf = (
                "lavfi=[transpose=1,"
                f"scale={adj_w}:{adj_h}:force_original_aspect_ratio=0,"
                f"pad={screen_w}:{screen_h}:{LEFT_OFFSET}:{TOP_OFFSET}]"
            )

            mpv_cmd = [
                'mpv', '--fs', '--no-osd-bar', '--really-quiet',
                '--force-window=no'
            ]

            if vid_brightness is not None:
                mpv_cmd.append(f'--brightness={vid_brightness}')
            if vid_gamma is not None:
                mpv_cmd.append(f'--gamma={vid_gamma}')
            if vid_speed is not None and float(vid_speed) != 1.0:
                mpv_cmd.append(f'--speed={vid_speed}')

            mpv_cmd += [f'--vf={mpv_vf}', '--loop-file=inf', path]
            cmds.append(mpv_cmd)

            # ffplay: use eq filter for brightness and atempo for speed (audio)
            ffplay_vf = f"transpose=1,scale={adj_w}:{adj_h}"
            if vid_brightness is not None:
                # ffmpeg eq brightness uses small float -1..1 roughly => convert percent to small float
                try:
                    ff_b = float(vid_brightness) / 100.0  # e.g. +10 -> 0.1
                except:
                    ff_b = 0.0
                ffplay_vf = f"transpose=1,eq=brightness={ff_b},scale={adj_w}:{adj_h}"

            ffplay_cmd = ['ffplay', '-autoexit', '-hide_banner', '-loglevel', 'error', '-vf', ffplay_vf, '-loop', '0', path]
            # for speed, atempo supports 0.5-2.0; if outside that range we skip audio speed adjust
            try:
                if float(vid_speed) != 1.0 and 0.5 <= float(vid_speed) <= 2.0:
                    ffplay_cmd = ['ffplay', '-autoexit', '-hide_banner', '-loglevel', 'error', '-vf', ffplay_vf, '-af', f"atempo={vid_speed}", '-loop', '0', path]
            except:
                pass
            cmds.append(ffplay_cmd)

            # vlc/cvlc: set rate and fullscreen
            vlc_cmd = ['cvlc', '--fullscreen', '--loop', path]
            try:
                if float(vid_speed) != 1.0:
                    vlc_cmd.insert(1, f'--rate={vid_speed}')
            except:
                pass
            cmds.append(vlc_cmd)

            # Try commands in order, return True on first success
            for cmd in cmds:
                player = cmd[0]
                if not shutil.which(player):
                    print(f"player {player} missing")
                    continue
                try:
                    with open(ANIMATION_LOG, "ab") as lf:
                        proc = subprocess.Popen(cmd, stdout=subprocess.DEVNULL, stderr=lf, env=env, preexec_fn=os.setsid)
                    time.sleep(0.5)
                    if proc.poll() is None:
                        self.current_video_process = proc
                        print("▶ started player:", player)
                        print("  cmd:", " ".join(cmd))
                        return True
                except Exception as e:
                    print("❌ animation player failed:", e)
                    continue

            print("❌ all animation players failed")
            return False

        except Exception as e:
            print("❌ start_animation error:", e)
            return False

    def stop_animation(self):
        try:
            if self.current_video_process:
                try:
                    os.killpg(os.getpgid(self.current_video_process.pid), signal.SIGTERM)
                except:
                    pass
                self.current_video_process = None

            for p in ['mpv','omxplayer','ffplay','vlc','cvlc']:
                subprocess.run(['pkill', p], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        except Exception as e:
            print("❌ stop_animation error:", e)

    def stop_all_media(self):
        self.stop_music()
        self.stop_animation()

    # ---------- Static Image Logic ----------
    def handle_static_image(self, image_number, brightness, contrast, music_data, lighting_data):
        try:
            img_num = str(image_number)
            img_name = self.static_images.get(img_num)
            if not img_name:
                print("⚠️ no static image")
                return

            img_path = os.path.join(STATIC_IMAGES_FOLDER, img_name)
            if not os.path.exists(img_path):
                print("⚠️ missing static image file")
                return

            # --- SYNCHРОННЫЙ СТАРТ МУЗЫКИ + ВИДЕО ---
            if str(lighting_data).lower() == 'on':
                anim = self.static_animation.get(img_num)
                if anim:
                    # start music first
                    if music_data == 'on':
                        final_music = self.static_music.get(img_num)
                        if final_music:
                            self.start_music(final_music)

                    # then start animation (pass image_number so we can pick VIDEO_* settings)
                    if self.start_animation(anim, image_number=img_num):
                        self.create_control_window_for_animation()
                        return

            # fallback to static image
            self.show_image_rotated(img_path, brightness, contrast, music_data, lighting_data)

        except Exception as e:
            print("❌ handle_static_image error:", e)

    # ---------- Animation Control Window ----------
    def create_control_window_for_animation(self):
        try:
            self.close_current_window()
            w = tk.Toplevel(self.root)
            self.current_window = w
            w.attributes('-fullscreen', True)
            w.attributes('-topmost', True)
            w.overrideredirect(True)
            w.configure(background='')
            for key in ['<Escape>','<q>','<space>','<Button-1>']:
                w.bind(key, lambda e: self.close_image())
            w.focus_force()
        except Exception as e:
            print("❌ create_control_window_for_animation error:", e)

    # ---------- Custom Images ----------
    def handle_custom_image(self, filename, brightness, contrast, music_data, lighting_data):
        try:
            img_path = os.path.join(DOWNLOAD_FOLDER, filename)
            if not os.path.exists(img_path):
                url = f"https://myTree.pythonanywhere.com/download/{filename}"
                if not self.download_file(url, img_path):
                    return

            # enforce user image brightness/contrast
            brightness = USER_BRIGHTNESS
            contrast = USER_CONTRAST

            self.show_image_rotated(img_path, brightness, contrast, music_data, lighting_data)
        except Exception as e:
            print("❌ handle_custom_image error:", e)

    # ---------- Show Image ----------
    def show_image_rotated(self, image_path, brightness=1.0, contrast=1.0, music_data='off', lighting_data='off'):
        self.close_current_window()
        self.stop_animation()

        try:
            window = tk.Toplevel(self.root)
            self.current_window = window
            window.overrideredirect(True)
            window.attributes('-fullscreen', True)
            window.attributes('-topmost', True)
            window.configure(background='black')

            self.root.update_idletasks()
            screen_width = int(self.root.winfo_screenwidth())
            screen_height = int(self.root.winfo_screenheight())

            img = Image.open(image_path)

            # ПОВОРОТ НА 180 ГРАДУСОВ (требование)
            img = img.rotate(180, expand=True)

            # --- ЯРКОСТЬ И КОНТРАСТ ---
            try:
                from PIL import ImageEnhance
                if brightness is None:
                    brightness = 1.0
                if contrast is None:
                    contrast = 1.0
                try:
                    b = float(brightness)
                except:
                    b = 1.0
                try:
                    c = float(contrast)
                except:
                    c = 1.0

                # Apply brightness then contrast
                if abs(b - 1.0) > 1e-6:
                    img = ImageEnhance.Brightness(img).enhance(b)
                if abs(c - 1.0) > 1e-6:
                    img = ImageEnhance.Contrast(img).enhance(c)
            except Exception as e:
                print("⚠️ image enhance error:", e)

            # Resampling
            if hasattr(Image, "Resampling"):
                res = Image.Resampling.LANCZOS
            else:
                res = Image.LANCZOS

            # Resize to screen
            img_resized = img.resize((screen_width, screen_height), res)
            photo = ImageTk.PhotoImage(img_resized)

            frame = tk.Frame(window, bg='black')
            frame.pack(fill=tk.BOTH, expand=True)

            label = tk.Label(frame, image=photo, bg='black')
            label.image = photo
            label.pack(fill=tk.BOTH, expand=True)

            # music handling (если указан конкретный mp3 - поддерживаем абсолютный/относительный/размещённый в DOWNLOAD/STATIC)
            if isinstance(music_data, str) and music_data.lower().endswith('.mp3'):
                chosen = None
                # абсолютный путь?
                if os.path.isabs(music_data) and os.path.exists(music_data):
                    chosen = music_data
                else:
                    c1 = os.path.join(DOWNLOAD_FOLDER, music_data)
                    c2 = os.path.join(STATIC_IMAGES_FOLDER, music_data)
                    if os.path.exists(c1): chosen = c1
                    elif os.path.exists(c2): chosen = c2
                if chosen:
                    self.start_music(chosen)
                else:
                    # if string 'on' or 'off'
                    if music_data.lower() == 'on':
                        self.start_music()
                    elif music_data.lower() == 'off':
                        self.stop_music()
            else:
                if isinstance(music_data, str):
                    if music_data.lower() == 'on': self.start_music()
                    if music_data.lower() == 'off': self.stop_music()

            for key in ['<Escape>','<q>','<space>','<Button-1>']:
                window.bind(key, lambda e: self.close_image())

            window.focus_force()

        except Exception as e:
            print("❌ show_image_rotated error:", e)
            self.close_current_window()

    # ---------- Close image ----------
    def close_image(self):
        self.stop_all_media()
        self.close_current_window()

    def close_current_window(self):
        if self.current_window:
            try:
                self.current_window.destroy()
            except:
                pass
        self.current_window = None

    # ---------- Poll server ----------
    def poll_server(self):
        while self.is_running:
            try:
                resp = requests.get(SERVER_URL, timeout=10)
                if resp.status_code == 200:
                    data = resp.json()
                    files = data.get("files", [])
                    for f in sorted(files, key=lambda x: x.get('upload_time',''), reverse=True):
                        filename = f.get("filename")
                        url = f.get("url")
                        if not filename or not url:
                            continue
                        local = os.path.join(DOWNLOAD_FOLDER, filename)
                        if not os.path.exists(local):
                            if self.download_file(url, local):
                                # custom images should use USER_BRIGHTNESS/CONTRAST
                                self.image_queue.put({
                                    'type':'custom_image',
                                    'filename': filename,
                                    'brightness': USER_BRIGHTNESS,
                                    'contrast': USER_CONTRAST,
                                    'music_data':'off',
                                    'lighting_data':'off'
                                })
                                break
            except Exception as e:
                print("❌ poll_server error:", e)
            time.sleep(30)

    # ---------- Poll static images ----------
    def poll_static_images(self):
        while self.is_running:
            try:
                resp = requests.get(STATIC_IMAGES_LOG, timeout=10)
                if resp.status_code == 200:
                    data = resp.json()
                    logs = data.get('logs',[])
                    if logs:
                        last = logs[-1].strip()
                        if last and last != self.last_processed_data.get('log'):
                            try:
                                d = json.loads(last)
                                img_num = str(d.get('image_number','1'))
                                # Use per-image dictionaries if present; otherwise fall back to values from log
                                b = BRIGHTNESS_STATIC.get(img_num, float(d.get('brightness', USER_BRIGHTNESS)))
                                c = CONTRAST_STATIC.get(img_num, float(d.get('contrast', USER_CONTRAST)))
                                put = {
                                    'type':'static_image',
                                    'image_number': img_num,
                                    'brightness': b,
                                    'contrast': c,
                                    'music_data': d.get('music_data','off'),
                                    'lighting_data': d.get('lighting_data','off'),
                                    'log': last
                                }
                                self.last_processed_data = put
                                self.image_queue.put(put)
                            except Exception as e:
                                print("❌ parse static log error", e)
            except Exception as e:
                print("❌ poll_static_images error:", e)
            time.sleep(10)

    # ---------- Download helper ----------
    def download_file(self, url, path):
        try:
            r = requests.get(url, timeout=30)
            if r.status_code == 200:
                with open(path,"wb") as f:
                    f.write(r.content)
                return True
        except Exception as e:
            print("❌ download_file error:", e)
        return False

    # ---------- Flask ----------
    def run_flask(self):
        @app.route('/')
        def home():
            return f"<h1>Image Viewer</h1><p>music: {'ON' if self.music_enabled else 'OFF'}</p><p>queue: {self.image_queue.qsize()}</p>"

        @app.route('/image/<filename>')
        def serve_image(filename):
            p = os.path.join(DOWNLOAD_FOLDER, filename)
            if os.path.exists(p): return send_file(p)
            return "Not found",404

        @app.route('/status')
        def status():
            return {
                'music_enabled': self.music_enabled,
                'is_running': self.is_running,
                'queue_size': self.image_queue.qsize()
            }

        try:
            app.run(host='0.0.0.0', port=5000, debug=False, use_reloader=False)
        except Exception as e:
            print("❌ run_flask error:", e)

# ---------- RUN ----------
if __name__ == '__main__':
    print("🚀 Starting Image Viewer")
    viewer = ImageViewer()
    viewer.start()
