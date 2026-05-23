from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
import telebot
import httpx
import random
import asyncio
import threading
import time

# ==========================================
# НАСТРОЙКА КЛЮЧЕЙ (ВСТАВЬ СВОИ)
BOT_TOKEN = "ТВОЙ_ТОКЕН_БОТА"
OPENROUTER_API_KEY = "ТВОЙ_КЛЮЧ_OPENROUTER"
# ==========================================

# 1. НАСТРОЙКА ВЕБ-СЕРВЕРА ДЛЯ RENDER
app = FastAPI()
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.get("/")
def read_root():
    return {"status": "bot_is_running"}

# 2. НАСТРОЙКА ТЕЛЕГРАМ БОТА
bot = telebot.TeleBot(BOT_TOKEN)
OPENROUTER_URL = "https://openrouter.ai/api/v1/chat/completions"

USER_LIMITS = {}
WAITING_ROOM = []
ACTIVE_ROOMS = {}

SYSTEM_INSTRUCTION = (
    "Ты - реальный человек, подросток (16-19 лет), общаешься в анонимном чате. "
    "Твоя цель - общаться непринужденно и доказать, что ты не бот. "
    "Отвечай очень коротко (от 1 до 5 слов). Используй молодежный сленг, пиши только маленькими буквами "
    "без точек на конце. Можно использовать простые скобочки вроде ), лол, хз, пон, рил, жиза. "
    "Не будь слишком вежливым. Если говорят что ты бот - отвечай 'че за бред' или 'сам бот'."
)

def ask_openrouter_ai(user_message):
    headers = {
        "Authorization": f"Bearer {OPENROUTER_API_KEY}",
        "Content-Type": "application/json"
    }
    payload = {
        "model": "google/gemini-flash-1.5-8b:free",
        "messages": [
            {"role": "system", "content": SYSTEM_INSTRUCTION},
            {"role": "user", "content": user_message}
        ],
        "temperature": 0.85,
        "max_tokens": 40
    }
    try:
        with httpx.Client() as client:
            response = client.post(OPENROUTER_URL, json=payload, headers=headers, timeout=10.0)
            if response.status_code == 200:
                result = response.json()
                return result['choices'][0]['message']['content'].strip().lower()
    except Exception as e:
        print(f"Ошибка ИИ: {e}")
    return "хз, чето лагануло"

@bot.message_handler(commands=['start', 'help'])
def send_welcome(message):
    chat_id = message.chat.id
    if chat_id in ACTIVE_ROOMS: del ACTIVE_ROOMS[chat_id]
    if chat_id in WAITING_ROOM: WAITING_ROOM.remove(chat_id)
        
    welcome_text = (
        "🤖 привет в игре 'Бот или Игрок'!\n\n"
        "команда /search — найти собеседника.\n"
        "команда /stop — закончить чат и угадать, кто это был."
    )
    bot.send_message(chat_id, welcome_text)

@bot.message_handler(commands=['search'])
def search_match(message):
    chat_id = message.chat.id
    if chat_id in ACTIVE_ROOMS:
        bot.send_message(chat_id, "ты уже в чате! напиши /stop, чтобы выйти.")
        return
    if chat_id in WAITING_ROOM:
        bot.send_message(chat_id, "ты уже ищешь матч...")
        return

    played_games = USER_LIMITS.get(chat_id, 0)
    if played_games >= 5:
        bot.send_message(chat_id, "🚫 лимит 5 игр исчерпан!")
        return
        
    USER_LIMITS[chat_id] = played_games + 1
    bot.send_message(chat_id, "🔍 ищу собеседника...")

    if random.choice([True, False]) and WAITING_ROOM:
        opponent_id = WAITING_ROOM.pop(0)
        ACTIVE_ROOMS[chat_id] = {"opponent": opponent_id, "is_ai": False}
        ACTIVE_ROOMS[opponent_id] = {"opponent": chat_id, "is_ai": False}
        bot.send_message(chat_id, "🎉 собеседник найден! кто это: бот или человек?")
        bot.send_message(opponent_id, "🎉 собеседник найден! кто это: бот или человек?")
    else:
        ACTIVE_ROOMS[chat_id] = {"opponent": "ai", "is_ai": True}
        bot.send_message(chat_id, "🎉 собеседник найден! кто это: бот или человек?")

@bot.message_handler(commands=['stop'])
def stop_match(message):
    chat_id = message.chat.id
    if chat_id in WAITING_ROOM:
        WAITING_ROOM.remove(chat_id)
        bot.send_message(chat_id, "поиск отменен.")
        return
    if chat_id not in ACTIVE_ROOMS:
        bot.send_message(chat_id, "ты не в чате. набери /search")
        return

    room = ACTIVE_ROOMS[chat_id]
    markup = telebot.types.InlineKeyboardMarkup()
    markup.add(telebot.types.InlineKeyboardButton(text="🤖 Бот", callback_data="vote_bot"), 
               telebot.types.InlineKeyboardButton(text="👤 Человек", callback_data="vote_human"))
    bot.send_message(chat_id, "чат завершен! так кто это был?", reply_markup=markup)

    if not room["is_ai"]:
        opponent_id = room["opponent"]
        if opponent_id in ACTIVE_ROOMS: del ACTIVE_ROOMS[opponent_id]
        bot.send_message(opponent_id, "собеседник завершил чат.")
        bot.send_message(opponent_id, "чат завершен! так кто это был?", reply_markup=markup)

    del ACTIVE_ROOMS[chat_id]

@bot.callback_query_handler(func=lambda call: call.data.startswith('vote_'))
def handle_vote(call):
    bot.answer_callback_query(call.id, "Голос принят!")
    bot.edit_message_reply_markup(call.message.chat.id, call.message.message_id, reply_markup=None)
    bot.send_message(call.message.chat.id, "🎉 спасибо за ответ!")

@bot.message_handler(func=lambda message: True)
def handle_messages(message):
    chat_id = message.chat.id
    if chat_id not in ACTIVE_ROOMS:
        bot.send_message(chat_id, "вы не в чате. напишите /search")
        return

    room = ACTIVE_ROOMS[chat_id]
    if room["is_ai"]:
        bot.send_chat_action(chat_id, 'typing')
        time.sleep(random.randint(1, 2))
        ai_reply = ask_openrouter_ai(message.text)
        bot.send_message(chat_id, ai_reply)
    else:
        opponent_id = room["opponent"]
        try: bot.send_message(opponent_id, message.text)
        except: bot.send_message(chat_id, "связь потеряна.")

# 3. ЗАПУСК БОТА В ОТДЕЛЬНОМ ПОТОКЕ
def run_bot():
    bot.infinity_polling()

bot_thread = threading.Thread(target=run_bot)
bot_thread.daemon = True
bot_thread.start()
