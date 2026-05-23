from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
import random
import asyncio
import httpx

app = FastAPI()

# Разрешаем нашему фронтенду подключаться к серверу
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Хранилище для лимитов игроков {user_id: количество_игр}
USER_LIMITS = {}
# Очередь живых игроков, ожидающих матч {lang: [список_websocket]}
WAITING_PLAYERS = {"ua": [], "en": [], "ru": []}

# Системные промпты для ИИ на разных языках
PROMPTS = {
    "ua": "Ти український підліток 14-16 років. Спілкуєшся в чатах розслаблено, використовуєш сленг (крінж, рофл, жиза, імба, пон), робиш друкарські помилки, пиши без розділових знаків з маленької літери. Відповідай коротко. Ніколи не кажи, що ти ШІ.",
    "en": "You are a 15-year-old American teenager. Use modern slang (fr, no cap, rizz, lol, idk, bro). Write in lowercase, ignore punctuation, make typos. Never reveal you are an AI.",
    "ru": "Ты подросток 15 лет. Пиши мелкими сообщениями, используй сленг (ща, капец, жиза, рил, пасиб). Не используй точки, пиши с маленькой буквы, делай опечатки. Не говори, что ты ИИ."
}

async def talk_with_ai(lang: str, user_message: str) -> str:
    """Функция запроса к ИИ (заглушка/пример, сюда подключается API ключ)"""
    # Имитируем задержку «печатания» текста человеком
    await asyncio.sleep(random.randint(2, 4))
    
    # Трендовые быстрые ответы для теста (пока нет платного OpenAI ключа)
    replies = {
        "ua": ["та ладно тобі))", "та рил, а ти що думав?", "хз хз, крінж якийсь", "та людина я, пон?"],
        "en": ["fr fr bro no cap", "lmao context?", "u trippin, i'm human", "idk custom reply"],
        "ru": ["да ладно тебе)", "рил жиза", "хз, кринж какой-то", "да чел я, успокойся)"]
    }
    return random.choice(replies.get(lang, ["..."]))

@app.websocket("/ws/{lang}/{user_id}")
async def websocket_endpoint(websocket: WebSocket, lang: str, user_id: str):
    await websocket.accept()
    
    # 1. Проверка лимита (5 игр в сутки)
    played = USER_LIMITS.get(user_id, 0)
    if played >= 5:
        await websocket.send_json({"type": "error", "message": "LIMIT_EXCEEDED"})
        await websocket.close()
        return
    
    USER_LIMITS[user_id] = played + 1

    # 2. Логика подбора соперника (Рандом 50/50: закинет к человеку или к Боту)
    if random.choice([True, False]) and WAITING_PLAYERS[lang]:
        # Нашелся живой соперник! Связываем их
        opponent = WAITING_PLAYERS[lang].pop(0)
        
        await websocket.send_json({"type": "start", "opponent": "human"})
        await opponent.send_json({"type": "start", "opponent": "human"})
        
        # Пересылка сообщений между ними (мост)
        try:
            while True:
                data = await websocket.receive_text()
                await opponent.send_json({"type": "msg", "text": data})
        except WebSocketDisconnect:
            await opponent.send_json({"type": "opponent_left"})
    else:
        # Соперника нет или выпал Бот — подключаем ИИ
        await websocket.send_json({"type": "start", "opponent": "ai"})
        
        try:
            while True:
                user_msg = await websocket.receive_text()
                # Получаем ответ от ИИ под нужный язык
                ai_reply = await talk_with_ai(lang, user_msg)
                await websocket.send_json({"type": "msg", "text": ai_reply})
        except WebSocketDisconnect:
            pass
