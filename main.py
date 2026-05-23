import telebot
import httpx
import random
import time

# НАСТРОЙКА КЛЮЧЕЙ
BOT_TOKEN = "8355758172:AAHF7jPJ-Ney2eJLo0FkqHLTMJsKMcHjJp0"
OPENROUTER_API_KEY = "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"

bot = telebot.TeleBot(BOT_TOKEN)

OPENROUTER_URL = "https://openrouter.ai/api/v1/chat/completions"

# Базы данных в оперативной памяти сервера
USER_LIMITS = {}     # {chat_id: количество_игр}
WAITING_ROOM = []    # Список chat_id игроков, которые ищут матч
ACTIVE_ROOMS = {}    # {chat_id_игрока_1: {"opponent": chat_id_игрока_2_или_ai, "is_ai": True/False}}

# Промт для ИИ, чтобы он косил под подростка
SYSTEM_INSTRUCTION = (
    "Ты - реальный человек, подросток (16-19 лет), общаешься в анонимном чате. "
    "Твоя цель - общаться непринужденно и доказать, что ты не бот. "
    "Отвечай очень коротко (от 1 до 5 слов). Используй молодежный сленг, пиши только маленькими буквами "
    "без точек на конце. Можно использовать простые скобочки вроде ), лол, хз, пон, рил, жиза. "
    "Не будь слишком вежливым. Если говорят что ты бот - отвечай 'че за бред' или 'сам бот'."
)

def ask_openrouter_ai(user_message):
    """Запрос к ИИ через OpenRouter"""
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
    # Сбрасываем старые сессии при старте, если они были
    if chat_id in ACTIVE_ROOMS:
        del ACTIVE_ROOMS[chat_id]
    if chat_id in WAITING_ROOM:
        WAITING_ROOM.remove(chat_id)
        
    welcome_text = (
        "🤖 привет в игре 'Бот или Игрок'!\n\n"
        "команда /search — найти собеседника (это может быть человек или ИИ).\n"
        "команда /stop — закончить чат и угадать, кто это был."
    )
    bot.send_message(chat_id, welcome_text)

@bot.message_handler(commands=['search'])
def search_match(message):
    chat_id = message.chat.id
    
    if chat_id in ACTIVE_ROOMS:
        bot.send_message(chat_id, "ты уже находишься в чате! напиши /stop, чтобы выйти.")
        return
        
    if chat_id in WAITING_ROOM:
        bot.send_message(chat_id, "ты уже ищешь матч, подожди немного...")
        return

    # Проверка лимитов (макс 5 игр)
    played_games = USER_LIMITS.get(chat_id, 0)
    if played_games >= 5:
        bot.send_message(chat_id, "🚫 ты исчерпал лимит в 5 бесплатных игр на сегодня!")
        return
        
    USER_LIMITS[chat_id] = played_games + 1
    bot.send_message(chat_id, "🔍 ищу собеседника...")

    # 50% шанс: если в очереди кто-то есть, соединяем с человеком
    if random.choice([True, False]) and WAITING_ROOM:
        opponent_id = WAITING_ROOM.pop(0)
        
        # Создаем комнату между двумя людьми
        ACTIVE_ROOMS[chat_id] = {"opponent": opponent_id, "is_ai": False}
        ACTIVE_ROOMS[opponent_id] = {"opponent": chat_id, "is_ai": False}
        
        bot.send_message(chat_id, "🎉 собеседник найден! общайся. кто это: бот или человек?")
        bot.send_message(opponent_id, "🎉 собеседник найден! общайся. кто это: бот или человек?")
    else:
        # Иначе — кидаем играть с ИИ
        ACTIVE_ROOMS[chat_id] = {"opponent": "ai", "is_ai": True}
        bot.send_message(chat_id, "🎉 собеседник найден! общайся. кто это: бот или человек?")

@bot.message_handler(commands=['stop'])
def stop_match(message):
    chat_id = message.chat.id
    
    if chat_id in WAITING_ROOM:
        WAITING_ROOM.remove(chat_id)
        bot.send_message(chat_id, "поиск матча отменен.")
        return

    if chat_id not in ACTIVE_ROOMS:
        bot.send_message(chat_id, "ты сейчас не в чате. набери /search, чтобы начать.")
        return

    room = ACTIVE_ROOMS[chat_id]
    
    # Открываем голосование кнопками
    markup = telebot.types.InlineKeyboardMarkup()
    btn_bot = telebot.types.InlineKeyboardButton(text="🤖 Бот", callback_data="vote_bot")
    btn_human = telebot.types.InlineKeyboardButton(text="👤 Человек", callback_data="vote_human")
    markup.add(btn_bot, btn_human)
    
    bot.send_message(chat_id, "чат завершен! так кто же это был по твоему мнению?", reply_markup=markup)

    # Если играли с человеком, закрываем чат и ему тоже
    if not room["is_ai"]:
        opponent_id = room["opponent"]
        if opponent_id in ACTIVE_ROOMS:
            del ACTIVE_ROOMS[opponent_id]
        bot.send_message(opponent_id, "собеседник завершил чат.")
        
        markup_opp = telebot.types.InlineKeyboardMarkup()
        markup_opp.add(telebot.types.InlineKeyboardButton(text="🤖 Бот", callback_data="vote_bot"), 
                       telebot.types.InlineKeyboardButton(text="👤 Человек", callback_data="vote_human"))
        bot.send_message(opponent_id, "чат завершен! так кто же это был по твоему мнению?", reply_markup=markup_opp)

    del ACTIVE_ROOMS[chat_id]

@bot.callback_query_handler(func=lambda call: call.data.startswith('vote_'))
def handle_vote(call):
    bot.answer_callback_query(call.id, "Голос принят!")
    bot.edit_message_reply_markup(call.message.chat.id, call.message.message_id, reply_markup=None)
    bot.send_message(call.message.chat.id, "🎉 спасибо за ответ! правильный результат будет доступен в полной версии.")

@bot.message_handler(func=lambda message: True)
def handle_messages(message):
    chat_id = message.chat.id
    
    if chat_id not in ACTIVE_ROOMS:
        bot.send_message(chat_id, "вы не в чате. напишите /search, чтобы найти собеседника.")
        return

    room = ACTIVE_ROOMS[chat_id]
    
    if room["is_ai"]:
        # Симулируем задержку печатания
        bot.send_chat_action(chat_id, 'typing')
        time.sleep(random.randint(1, 3))
        
        # Получаем ответ от ИИ и отправляем юзеру
        ai_reply = ask_openrouter_ai(message.text)
        bot.send_message(chat_id, ai_reply)
    else:
        # Пересылаем сообщение живому человеку
        opponent_id = room["opponent"]
        try:
            bot.send_message(opponent_id, message.text)
        except:
            bot.send_message(chat_id, "упс, кажется связь с собеседником потеряна.")

# Запуск бота на постоянное прослушивание
if __name__ == "__main__":
    print("Бот запущен...")
    bot.infinity_polling()
