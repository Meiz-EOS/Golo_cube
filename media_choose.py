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
STATIC_IMAGES_FOLDER = '/home/un/Downloads'  # change if needed
# SERVER_URL удален, так как мы больше не опрашиваем сервер
# STATIC_IMAGES_LOG удален, так как мы больше не опрашиваем логи
ANIMATION_LOG = "/tmp/animation_player.log"

# Default/user forced values for custom images
USER_BRIGHTNESS = 1.0
USER_CONTRAST = 1.0

# --- Individual settings for static images (per image id as string) ---
BRIGHTNESS_STATIC = {
    "1": 1.25,
    "2": 1.40,
    "3": 1.10,
}

CONTRAST_STATIC = {
    "1": 1.20,
    "2": 1.35,
    "3": 1.00,
}

# --- Per-video overrides: brightness and playback speed ---
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

        # Static assets
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
                        print(f"💾 Received file via PUSH: {filename}")

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

                print("🔔 Webhook (Server Push) data:", data)

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

        # УДАЛЕНО: threading.Thread(target=self.poll_server...
        # УДАЛЕНО: threading.Thread(target=self.poll_static_images...
        
        # Запускаем только Flask сервер для приема входящих подключений
        threading.Thread(target=self.run_flask, daemon=True).start()

        print("✅ ImageViewer started (PUSH MODE ONLY)")
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
        try:
            self.stop_music()

            music_path = None
            if music_file:
                if os.path.isabs(music_file) and os.path.exists(music_file):
                    music_path = music_file
                else:
                    cand1 = os.path.join(DOWNLOAD_FOLDER, music_file)
                    cand2 = os.path.join(STATIC_IMAGES_FOLDER, music_file)
                    if os.path.exists(cand1):
                        music_path = cand1
                    elif os.path.exists(cand2):
                        music_path = cand2
                    elif os.path.exists(music_file):
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
        try:
            self.stop_animation()

            cand1 = os.path.join(STATIC_IMAGES_FOLDER, animation_file)
            cand2 = os.path.join(DOWNLOAD_FOLDER, animation_file)
            cand3 = animation_file

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

            LEFT_OFFSET   = 5
            RIGHT_OFFSET = 100
            TOP_OFFSET    = 0
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

            img_num = str(image_number) if image_number is not None else ''
            raw_vid_brightness = VIDEO_BRIGHTNESS.get(img_num, None)
            vid_speed = VIDEO_SPEED.get(img_num, 1.0)

            vid_brightness = None
            if raw_vid_brightness is not None:
                try:
                    vb = float(raw_vid_brightness)
                    if abs(vb) <= 2.0:
                        vid_brightness = vb * 100.0
                    else:
                        vid_brightness = vb
                except:
                    vid_brightness = None

            vid_gamma = None
            if vid_brightness is not None:
                try:
                    vg = -(vid_brightness / 100.0) * 1.6
                    if vg < -2.0: vg = -2.0
                    if vg > 2.0: vg = 2.0
                    vid_gamma = vg
                except:
                    vid_gamma = None

            cmds = []

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
                mpv_cmd.append(f'--gamma={1.0 + vid_gamma}')
            if vid_speed is not None and float(vid_speed) != 1.0:
                mpv_cmd.append(f'--speed={vid_speed}')

            mpv_cmd += [f'--vf={mpv_vf}', '--loop-file=inf', path]
            cmds.append(mpv_cmd)

            ffplay_vf = f"transpose=1,scale={adj_w}:{adj_h}"
            if vid_brightness is not None:
                try:
                    ff_b = float(vid_brightness) / 100.0
                except:
                    ff_b = 0.0
                ffplay_vf = f"transpose=1,eq=brightness={ff_b},scale={adj_w}:{adj_h}"

            ffplay_cmd = ['ffplay', '-autoexit', '-hide_banner', '-loglevel', 'error', '-vf', ffplay_vf, '-loop', '0', path]
            try:
                if float(vid_speed) != 1.0 and 0.5 <= float(vid_speed) <= 2.0:
                    ffplay_cmd = ['ffplay', '-autoexit', '-hide_banner', '-loglevel', 'error', '-vf', ffplay_vf, '-af', f"atempo={vid_speed}", '-loop', '0', path]
            except:
                pass
            cmds.append(ffplay_cmd)

            vlc_cmd = ['cvlc', '--fullscreen', '--loop', path]
            try:
                if float(vid_speed) != 1.0:
                    vlc_cmd.insert(1, f'--rate={vid_speed}')
            except:
                pass
            cmds.append(vlc_cmd)

            for cmd in cmds:
                player = cmd[0]
                if not shutil.which(player):
                    continue
                try:
                    with open(ANIMATION_LOG, "ab") as lf:
                        proc = subprocess.Popen(cmd, stdout=subprocess.DEVNULL, stderr=lf, env=env, preexec_fn=os.setsid)
                    time.sleep(0.5)
                    if proc.poll() is None:
                        self.current_video_process = proc
                        print("▶ started player:", player)
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

            if str(lighting_data).lower() == 'on':
                anim = self.static_animation.get(img_num)
                if anim:
                    if music_data == 'on':
                        final_music = self.static_music.get(img_num)
                        if final_music:
                            self.start_music(final_music)

                    if self.start_animation(anim, image_number=img_num):
                        self.create_control_window_for_animation()
                        return

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
            # Файл должен уже быть загружен через webhook
            if not os.path.exists(img_path):
                print("⚠️ File not found (push failed?):", img_path)
                return

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
            img = img.rotate(180, expand=True)

            try:
                if brightness is None: brightness = 1.0
                if contrast is None: contrast = 1.0
                try:
                    b = float(brightness)
                except:
                    b = 1.0
                try:
                    c = float(contrast)
                except:
                    c = 1.0

                if abs(b - 1.0) > 1e-6:
                    img = ImageEnhance.Brightness(img).enhance(b)
                if abs(c - 1.0) > 1e-6:
                    img = ImageEnhance.Contrast(img).enhance(c)
            except Exception as e:
                print("⚠️ image enhance error:", e)

            if hasattr(Image, "Resampling"):
                res = Image.Resampling.LANCZOS
            else:
                res = Image.LANCZOS

            img_resized = img.resize((screen_width, screen_height), res)
            photo = ImageTk.PhotoImage(img_resized)

            frame = tk.Frame(window, bg='black')
            frame.pack(fill=tk.BOTH, expand=True)

            label = tk.Label(frame, image=photo, bg='black')
            label.image = photo
            label.pack(fill=tk.BOTH, expand=True)

            if isinstance(music_data, str) and music_data.lower().endswith('.mp3'):
                chosen = None
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

    # ---------- Flask ----------
    def run_flask(self):
        @app.route('/')
        def home():
            return f"<h1>Image Viewer (PUSH MODE)</h1><p>music: {'ON' if self.music_enabled else 'OFF'}</p><p>queue: {self.image_queue.qsize()}</p>"

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
                'queue_size': self.image_queue.qsize(),
                'mode': 'push_only'
            }

        try:
            app.run(host='0.0.0.0', port=5000, debug=False, use_reloader=False)
        except Exception as e:
            print("❌ run_flask error:", e)

# ---------- RUN ----------
if __name__ == '__main__':
    print("🚀 Starting Image Viewer (SERVER-PUSH CONFIG)")
    viewer = ImageViewer()
    viewer.start()