#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
ГОЛОСОВОЙ АССИСТЕНТ С ИНТЕГРАЦИЕЙ MEDIA VIEWER
Управляет показом изображений и музыкой через локальный сервер.
"""

import speech_recognition as sr
import datetime
import webbrowser
import time
import random
import requests  # Нужно для отправки команд в media_choose.py
import json
import os
import sys
from typing import List, Dict, Optional

# Импорт библиотеки для нечеткого сравнения (AI-анализ текста)
try:
    from rapidfuzz import process, fuzz
except ImportError:
    print("❌ ОШИБКА: Не установлена библиотека 'rapidfuzz'.")
    print("👉 Установите её командой: pip install rapidfuzz")
    sys.exit(1)

# ================= КОНФИГУРАЦИЯ СВЯЗИ =================
MEDIA_PLAYER_URL = "http://127.0.0.1:5000/webhook"

# ================= БАЗЫ ДАННЫХ ИНФОРМАЦИИ =================

QUOTES_RU = [
    "Самый большой риск — не рисковать вообще.",
    "Успех — это способность идти от неудачи к неудаче, не теряя энтузиазма.",
    "Лучшее время, чтобы посадить дерево, было 20 лет назад. Следующее — сейчас.",
    "Не ошибается тот, кто ничего не делает.",
    "Сначала они игнорируют тебя, потом смеются, потом борются, а потом ты побеждаешь."
]

FACTS_RUSSIAN = [
    "Москва была основана в 1147 году.",
    "Россия — самая большая страна в мире по площади.",
    "Байкал — самое глубокое озеро в мире.",
    "В Санкт-Петербурге 342 моста.",
    "Матрёшка появилась только в конце 19 века."
]

# ================= КЛАСС АНАЛИЗАТОРА (AI LOGIC) =================

class CommandAnalyzer:
    """Анализирует текст и ищет наиболее похожее намерение"""
    
    def __init__(self, intents_map: dict, threshold=60):
        self.intents_map = intents_map
        self.threshold = threshold
        
        self.corpus = []
        for intent_key, data in self.intents_map.items():
            for phrase in data['phrases']:
                self.corpus.append({
                    'phrase': phrase,
                    'intent': intent_key
                })

    def analyze(self, text: str) -> Optional[dict]:
        if not text:
            return None

        results = []
        for item in self.corpus:
            score = fuzz.WRatio(text, item['phrase'])
            results.append({
                'intent': item['intent'],
                'matched_phrase': item['phrase'],
                'score': score
            })

        results.sort(key=lambda x: x['score'], reverse=True)
        
        print("\n📊 [AI ANALYZER] ТОП-3 ВЕРОЯТНОСТИ:")
        for res in results[:3]:
            marker = "✅" if res['score'] >= self.threshold else "❌"
            print(f"   {marker} Intent: {res['intent'].upper():<15} | Фраза: '{res['matched_phrase']}' -> {res['score']:.1f}%")

        best_match = results[0] if results else None
        
        if best_match and best_match['score'] >= self.threshold:
            return best_match
        else:
            return None

# ================= КЛАСС АССИСТЕНТА =================

class InfoAssistant:
    def __init__(self):
        self.recognizer = sr.Recognizer()
        self.running = True
        
        # Настройка намерений (включая управление медиа)
        self.intents = self._setup_intents()
        
        # Анализатор (порог 65%)
        self.analyzer = CommandAnalyzer(self.intents, threshold=65)
        
        print("🤖 Голосовой ассистент инициализирован")
    
    def _setup_intents(self) -> Dict:
        return {
            # === ИСПРАВЛЕННЫЙ БЛОК МЕДИА ===
            # Мы добавили цифры "1", "2", "3" прямо в фразы, так как Google часто пишет их цифрами
            'media_img_1': {
                'func': lambda: self.cmd_send_media("1", "off", "off"),
                'phrases': [
                    'покажи первую картинку', 'изображение один', 'картинка 1', 
                    'номер 1', 'изображение 1', 'слайд 1', 'первый'
                ]
            },
            'media_img_2': {
                'func': lambda: self.cmd_send_media("2", "off", "off"),
                'phrases': [
                    'покажи вторую картинку', 'изображение два', 'картинка 2', 
                    'номер 2', 'изображение 2', 'слайд 2', 'второй'
                ]
            },
            'media_img_3': {
                'func': lambda: self.cmd_send_media("3", "off", "off"),
                'phrases': [
                    'покажи третью картинку', 'изображение три', 'картинка 3', 
                    'номер 3', 'изображение 3', 'слайд 3', 'третий'
                ]
            },
            
            # === ОСТАЛЬНЫЕ КОМАНДЫ ===
            'media_music_on': {
                'func': lambda: self.cmd_send_media("1", "on", "off"),
                'phrases': ['включи музыку', 'запусти трек', 'играй музыку', 'музыка']
            },
            'media_show_video': {
                'func': lambda: self.cmd_send_media("1", "on", "on"),
                'phrases': ['включи видео', 'запусти анимацию', 'покажи ролик', 'видео']
            },
            'greeting': {
                'func': self.cmd_hello,
                'phrases': ['привет', 'здравствуй']
            },
            'stop': {
                'func': self.cmd_stop,
                'phrases': ['стоп', 'хватит', 'выход', 'отключись']
            }
        }
    
    # --- ФУНКЦИЯ ОТПРАВКИ В MEDIA CHOOSE ---
    def cmd_send_media(self, image_number="1", music="off", lighting="off"):
        """Отправляет JSON-команду на локальный сервер плеера"""
        payload = {
            "type": "static_image",
            "image_number": image_number,
            "music_data": music,
            "lighting_data": lighting,
            "brightness": 1.0,
            "contrast": 1.0
        }
        
        print(f"📡 Отправка команды плееру: {payload}")
        try:
            # Отправляем POST запрос с таймаутом 1 секунда, чтобы не виснуть
            requests.post(MEDIA_PLAYER_URL, json=payload, timeout=1.0)
            self.print_info("МЕДИА", f"Команда отправлена: Имг {image_number}, Муз {music}")
        except requests.exceptions.ConnectionError:
            self.print_info("ОШИБКА", "Медиа-плеер не запущен! (Запустите media_choose.py)")
        except Exception as e:
            self.print_info("ОШИБКА", f"Не удалось отправить команду: {e}")
        return True

    # --- ОСТАЛЬНЫЕ ФУНКЦИИ ---
    def listen_command(self) -> str:
        try:
            with sr.Microphone() as source:
                print("\n🎤 Слушаю... (говорите)")
                self.recognizer.adjust_for_ambient_noise(source, duration=0.5)
                self.recognizer.pause_threshold = 1.0  # Пауза между словами
                
                audio = self.recognizer.listen(source, timeout=5, phrase_time_limit=10)
                
                print("⏳ Распознаю...")
                text = self.recognizer.recognize_google(audio, language='ru-RU')
                print(f"👤 Вы сказали: \"{text}\"")
                return text.lower()
        except Exception:
            return "" # Молча игнорируем ошибки тишины

    def print_info(self, title: str, content: str):
        print("\n" + "="*40)
        print(f"📚 {title.upper()}")
        print("-" * 40)
        print(content)
        print("="*40)
    
    def cmd_hello(self):
        self.print_info("ПРИВЕТ", "Я готов управлять медиа-системой!")
        return True
    
    def cmd_time(self):
        now = datetime.datetime.now().strftime("%H:%M")
        self.print_info("ВРЕМЯ", f"Сейчас {now}")
        return True
    
    def cmd_date(self):
        d = datetime.datetime.now().strftime("%d.%m.%Y")
        self.print_info("ДАТА", f"Сегодня {d}")
        return True
    
    def cmd_fact(self):
        self.print_info("ФАКТ", random.choice(FACTS_RUSSIAN))
        return True
    
    def cmd_stop(self):
        self.print_info("ВЫХОД", "Завершаю работу.")
        self.running = False
        return True
    
    def process_command(self, command_text: str) -> bool:
        if not command_text: return False
        
        result = self.analyzer.analyze(command_text)
        if result:
            intent_name = result['intent']
            score = result['score']
            print(f"🚀 ЗАПУСК: {intent_name} ({score:.1f}%)")
            self.intents[intent_name]['func']()
            return True
        return False
    
    def run(self):
        print("🚀 ГОЛОСОВОЙ АССИСТЕНТ ЗАПУЩЕН")
        while self.running:
            try:
                cmd = self.listen_command()
                if cmd: self.process_command(cmd)
                time.sleep(0.1)
            except KeyboardInterrupt:
                break

# ================= ЗАПУСК =================

def main():
    try:
        assistant = InfoAssistant()
        assistant.run()
    except Exception as e:
        print(f"Error: {e}")

if __name__ == "__main__":
    main()