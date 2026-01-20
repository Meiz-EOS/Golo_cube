#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
ГОЛОСОВОЙ АССИСТЕНТ (VOSK OFFLINE EDITION)
Работает мгновенно, без интернета. Идеально для коротких команд.
"""

import json
import os
import sys
import time
import queue
import random
import requests
import pyaudio
from vosk import Model, KaldiRecognizer
from typing import Dict, Optional

# Проверка библиотеки AI
try:
    from rapidfuzz import process, fuzz
except ImportError:
    print("❌ ОШИБКА: Не установлена библиотека 'rapidfuzz'.")
    print("👉 pip install rapidfuzz")
    sys.exit(1)

# ================= КОНФИГУРАЦИЯ =================
MEDIA_PLAYER_URL = "http://127.0.0.1:5000/webhook"

# ОПРЕДЕЛЯЕМ АБСОЛЮТНЫЙ ПУТЬ К МОДЕЛИ
# Это гарантирует, что папка найдется, даже если запускать скрипт из другой директории
current_dir = os.path.dirname(os.path.abspath(__file__))
MODEL_PATH = os.path.join(current_dir, "model")

# ================= БАЗЫ ДАННЫХ =================
QUOTES_RU = ["Риск — дело благородное.", "Успех — это путь от неудачи к неудаче."]
FACTS_RUSSIAN = ["Москва основана в 1147 году.", "Байкал — самое глубокое озеро."]

# ================= AI АНАЛИЗАТОР =================
class CommandAnalyzer:
    def __init__(self, intents_map: dict, threshold=60):
        self.intents_map = intents_map
        self.threshold = threshold
        self.corpus = []
        for intent_key, data in self.intents_map.items():
            for phrase in data['phrases']:
                self.corpus.append({'phrase': phrase, 'intent': intent_key})

    def analyze(self, text: str) -> Optional[dict]:
        if not text: return None
        results = []
        for item in self.corpus:
            # Vosk выдает текст без заглавных букв, WRatio отлично справляется
            score = fuzz.WRatio(text, item['phrase'])
            results.append({
                'intent': item['intent'],
                'matched_phrase': item['phrase'],
                'score': score
            })
        
        results.sort(key=lambda x: x['score'], reverse=True)
        
        if results:
            top = results[0]
            # Логируем только если уверенность хоть сколько-то значимая
            if top['score'] > 40:
                print(f"🧠 [AI] '{text}' -> {top['intent']} ({top['score']:.1f}%)")

        best_match = results[0] if results else None
        if best_match and best_match['score'] >= self.threshold:
            return best_match
        return None

# ================= АССИСТЕНТ (VOSK) =================
class InfoAssistant:
    def __init__(self):
        self.running = True
        self.intents = self._setup_intents()
        self.analyzer = CommandAnalyzer(self.intents, threshold=75)
        
        # === ИНИЦИАЛИЗАЦИЯ VOSK ===
        if not os.path.exists(MODEL_PATH):
            print(f"❌ ОШИБКА: Папка '{MODEL_PATH}' не найдена!")
            print("1. Скачайте модель с https://alphacephei.com/vosk/models")
            print("2. Распакуйте её в папку 'model' рядом со скриптом.")
            sys.exit(1)
            
        print("⏳ Загрузка модели Vosk (это может занять пару секунд)...")
        try:
            self.model = Model(MODEL_PATH)
            # Частота 16000 Гц стандарт для распознавания
            self.recognizer = KaldiRecognizer(self.model, 16000)
        except Exception as e:
            print(f"❌ Ошибка загрузки модели: {e}")
            sys.exit(1)
            
        print("✅ Модель загружена. Микрофон готов.")

    def _setup_intents(self) -> Dict:
        return {
            'media_img_1': {
                'func': lambda: self.cmd_send_media("1", "off", "off"),
                'phrases': ['покажи первую картинку', 'изображение один', 'картинка один', 'номер один', 'слайд один', 'один', 'первый']
            },
            'media_img_2': {
                'func': lambda: self.cmd_send_media("2", "off", "off"),
                'phrases': ['покажи вторую картинку', 'изображение два', 'картинка два', 'номер два', 'слайд два', 'два', 'второй']
            },
            'media_img_3': {
                'func': lambda: self.cmd_send_media("3", "off", "off"),
                'phrases': ['покажи третью картинку', 'изображение три', 'картинка три', 'номер три', 'слайд три', 'три', 'третий']
            },
            'media_music_on': {
                'func': lambda: self.cmd_send_media("1", "on", "off"),
                'phrases': ['включи музыку', 'запусти трек', 'играй музыку', 'музыка', 'песня']
            },
            'media_show_video': {
                'func': lambda: self.cmd_send_media("1", "on", "on"),
                'phrases': ['включи видео', 'запусти анимацию', 'покажи ролик', 'видео', 'клип']
            },
            'stop': {
                'func': self.cmd_stop,
                'phrases': ['стоп', 'хватит', 'выход', 'отключись', 'завершить', 'все', 'конец']
            },
             'greeting': {
                'func': self.cmd_hello,
                'phrases': ['привет', 'здравствуй']
            },
            'fact': {
                'func': self.cmd_fact,
                'phrases': ['факт', 'расскажи факт', 'интересное']
            }
        }
    
    def cmd_send_media(self, img="1", mus="off", light="off"):
        payload = {"type": "static_image", "image_number": img, "music_data": mus, "lighting_data": light}
        print(f"📡 ОТПРАВКА: {payload}")
        try:
            requests.post(MEDIA_PLAYER_URL, json=payload, timeout=0.1)
        except:
            pass
        return True

    def cmd_hello(self):
        print("🤖 Привет! Я слушаю.")
        return True

    def cmd_fact(self):
        print(f"🤓 Факт: {random.choice(FACTS_RUSSIAN)}")
        return True

    def cmd_stop(self):
        self.running = False
        print("👋 Завершение работы...")
        return True

    def run(self):
        # Настройка микрофона PyAudio
        p = pyaudio.PyAudio()
        try:
            stream = p.open(format=pyaudio.paInt16, 
                            channels=1, 
                            rate=16000, 
                            input=True, 
                            frames_per_buffer=4000) # Читаем кусками по 0.25 сек
            stream.start_stream()
            
            print("\n🚀 СИСТЕМА ЗАПУЩЕНА (VOSK ENGINE)")
            print("🎤 Говорите... (Ctrl+C для выхода)")

            while self.running:
                # Читаем сырые данные с микрофона
                data = stream.read(4000, exception_on_overflow=False)
                
                # Vosk анализирует поток на лету
                if self.recognizer.AcceptWaveform(data):
                    # Если фраза закончена, получаем полный результат
                    result_json = self.recognizer.Result()
                    result_dict = json.loads(result_json)
                    text = result_dict.get('text', '')
                    
                    if text:
                        print(f"🗣️  Услышал: '{text}'")
                        self.process_command(text)
                else:
                    # (Опционально) Промежуточный результат (PartialResult)
                    # Можно использовать для отображения того, что ассистент слышит прямо сейчас
                    pass

        except KeyboardInterrupt:
            self.cmd_stop()
        except Exception as e:
            print(f"\n💥 Критическая ошибка аудиопотока: {e}")
        finally:
            # Чистка ресурсов
            try:
                stream.stop_stream()
                stream.close()
            except: pass
            p.terminate()
            if sys.platform == "win32":
                os.system("pause")

    def process_command(self, text: str):
        res = self.analyzer.analyze(text)
        if res:
            print(f"🚀 ВЫПОЛНЯЮ: {res['intent'].upper()}")
            self.intents[res['intent']]['func']()

if __name__ == "__main__":
    InfoAssistant().run()