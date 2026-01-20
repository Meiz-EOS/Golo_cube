#!/usr/bin/env python3
# -*- coding: utf-8 -*-
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

try:
    from rapidfuzz import process, fuzz
except ImportError:
    print("Ошибка: pip install rapidfuzz")
    sys.exit(1)

MEDIA_PLAYER_URL = "http://127.0.0.1:5000/webhook"
current_dir = os.path.dirname(os.path.abspath(__file__))
MODEL_PATH = os.path.join(current_dir, "model")
QUOTES_RU = ["Риск — дело благородное.", "Успех — это путь от неудачи к неудаче."]
FACTS_RUSSIAN = ["Москва основана в 1147 году.", "Байкал — самое глубокое озеро."]

class CommandAnalyzer:
    def __init__(self, intents_map: dict, threshold=70):
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
            score = fuzz.WRatio(text, item['phrase'])
            results.append({'intent': item['intent'], 'score': score})
        
        results.sort(key=lambda x: x['score'], reverse=True)
        if results and results[0]['score'] >= self.threshold:
            return results[0]
        return None

class InfoAssistant:
    def __init__(self):
        self.running = True
        self.intents = self._setup_intents()
        self.analyzer = CommandAnalyzer(self.intents, threshold=65)
        self.listen_until = 0.0  # Время, до которого ассистент слушает команды
        
        if not os.path.exists(MODEL_PATH):
            print(f"❌ ОШИБКА: Нет папки model")
            sys.exit(1)
            
        print("⏳ Загрузка модели...")
        try:
            self.model = Model(MODEL_PATH)
            self.recognizer = KaldiRecognizer(self.model, 16000)
        except Exception as e:
            print(f"❌ Ошибка модели: {e}")
            sys.exit(1)
        print("✅ Готов к работе.")

    def _setup_intents(self) -> Dict:
        return {
            # === МЕДИА 1 ===
            'media_1': {
                'func': lambda: self.cmd_send_media("1", "on"),
                'phrases': [
                    'включи медиа один', 'медиа один', 'запусти первую сцену', 'сцена один', 
                    'номер один', 'первый файл', 'картинка один', 'видео один', 
                    'поставь первый', 'вруби первое', 'активируй один', 'единица'
                ]
            },
            # === МЕДИА 2 ===
            'media_2': {
                'func': lambda: self.cmd_send_media("2", "on"),
                'phrases': [
                    'включи медиа два', 'медиа два', 'запусти вторую сцену', 'сцена два', 
                    'номер два', 'второй файл', 'картинка два', 'видео два', 
                    'поставь второй', 'вруби второе', 'активируй два', 'двойка'
                ]
            },
            # === МЕДИА 3 ===
            'media_3': {
                'func': lambda: self.cmd_send_media("3", "on"),
                'phrases': [
                    'включи медиа три', 'медиа три', 'запусти третью сцену', 'сцена три', 
                    'номер три', 'третий файл', 'картинка три', 'видео три', 
                    'поставь третий', 'вруби третье', 'активируй три', 'тройка'
                ]
            },
            # === ГРОМКОСТЬ: ГРОМЧЕ ===
            'volume_up': {
                'func': lambda: self.cmd_volume("up"),
                'phrases': [
                    'громче', 'сделай громче', 'подними звук', 'увеличь громкость', 
                    'добавь звук', 'звук плюс', 'еще громче', 'погромче', 
                    'прибавь громкости', 'усилить звук'
                ]
            },
            # === ГРОМКОСТЬ: ТИШЕ ===
            'volume_down': {
                'func': lambda: self.cmd_volume("down"),
                'phrases': [
                    'тише', 'сделай тише', 'убавь звук', 'уменьши громкость', 
                    'звук минус', 'потише', 'убери громкость', 'снизь звук', 
                    'слишком громко', 'приглуши'
                ]
            },
            # === ГРОМКОСТЬ: МАКСИМУМ ===
            'volume_max': {
                'func': lambda: self.cmd_volume("max"),
                'phrases': [
                    'максимальная громкость', 'звук на максимум', 'полная громкость', 
                    'на всю катушку', 'максимум звука', 'очень громко', 'басы на максимум'
                ]
            },
            # === ГРОМКОСТЬ: ВЫКЛЮЧИТЬ ЗВУК (MUTE) ===
            'volume_mute': {
                'func': lambda: self.cmd_volume("mute"),
                'phrases': [
                    'выключи звук', 'без звука', 'режим немой', 'мут', 'заглуши', 
                    'убери звук полностью', 'выруби звук'
                ]
            },
        }
    
    def cmd_send_media(self, img="1", mus="off"):
        payload = {"type": "static_image", "image_number": img, "music_data": mus}
        try: requests.post(MEDIA_PLAYER_URL, json=payload, timeout=0.1)
        except: pass
        return True

    def cmd_volume(self, action):
        print(f"🔊 ГРОМКОСТЬ: {action}")
        payload = {"type": "volume", "action": action}
        try: requests.post(MEDIA_PLAYER_URL, json=payload, timeout=0.1)
        except: pass
        return True

    def cmd_stop(self):
        self.running = False
        return True

    def run(self):
        p = pyaudio.PyAudio()
        stream = p.open(format=pyaudio.paInt16, channels=1, rate=16000, input=True, frames_per_buffer=4000)
        stream.start_stream()
        print("\n💤 РЕЖИМ ОЖИДАНИЯ. Скажите 'ЮХИН', чтобы активировать...")

        while self.running:
            data = stream.read(4000, exception_on_overflow=False)
            if self.recognizer.AcceptWaveform(data):
                res = json.loads(self.recognizer.Result())
                text = res.get('text', '')
                
                if not text:
                    continue

                current_time = time.time()
                
                # Проверяем, находимся ли мы в активном окне прослушивания
                if current_time < self.listen_until:
                    # ЛОГИКА СКОЛЬЗЯЩЕГО ОКНА:
                    # Если мы услышали речь, мы продлеваем время прослушивания еще на 5 секунд
                    self.listen_until = current_time + 5.0
                    print(f"⏱️  Речь обнаружена. Таймер сброшен (+5 сек).")
                    
                    print(f"🟢 (Активен) Слышу: '{text}'")
                    match = self.analyzer.analyze(text)
                    if match:
                        print(f"🚀 Выполняю: {match['intent']}")
                        self.intents[match['intent']]['func']()
                else:
                    # Режим ожидания: Ищем только ключевое слово "Юхин"
                    # fuzz.partial_ratio позволяет найти имя даже во фразе "Эй Юхин привет"
                    wake_score = fuzz.partial_ratio("юхин", text.lower())
                    if wake_score >= 80:
                        self.listen_until = current_time + 5.0
                        print(f"\n🔔 ЮХИН АКТИВИРОВАН! Слушаю команды 5 секунд...")
                    else:
                        print(f"💤 (Игнор) '{text}'")
        
        stream.stop_stream()
        stream.close()
        p.terminate()

if __name__ == "__main__":
    InfoAssistant().run()