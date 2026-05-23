from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
import random
import asyncio
import httpx

app = FastAPI()

# Разрешаем подключение любых фронтендов
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Твой API-ключ Google Gemini
GEMINI_API_KEY = "AIzaSyDR1uG-0yPYdgec4I7xd4FBOVVRVCxbf3M"
GEMINI_URL = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-1.5-flash:generateContent?key={GEMINI_API_KEY}"

# Хранилище лимитов {user_id: количество_игр}
USER_LIMITS = {}
# Очередь живых игроков по языкам
WAITING_PLAYERS = {"ua": [], "en": [], "ru": []}

async def ask_gemini_teenager(user_message: str, lang: str) -> str:
    """Запрос к ИИ Gemini с жестким промтом подростка"""
    
    # Промт, который заставит ИИ косить под человека
    system_instruction = (
        "Ты - реальный человек, подросток (16-19 лет), играешь в анонимном чате 'Бот или Игрок'. "
        "Твоя главная цель - убедить собеседника, что ты НЕ ИИ и НЕ Бот. "
        "Отвечай очень коротко (1-6 слов), используй современный интернет-сленг, пиши только маленькими буквами, "
        "иногда делай мелкие опечатки, используй простые смайлики типа ), )) или лол, хз, крінж, пон, рил. "
        "Никаких умных фраз, никаких списков, никаких приветствий как у ассистента. Если тебя обвиняют в том, что ты бот, "
        "агрессивно или иронично отрицай это (например: 'ты рофлишь?', 'сам ты бот чел'). "
        f"Отвечай строго на языке: {lang}."
    )

    payload = {
        "contents": [
            {
                "parts": [
                    {"text": f"Системная установка: {system_instruction}\n\nСообщение собеседника: {user_message}\nТвой короткий ответ:"}
                ]
            }
        ],
        "generationConfig": {
            "temperature": 0.85,  # Добавляем креатива и хаотичности
            "maxOutputTokens": 40
        }
    }

    try:
        async with httpx.AsyncClient() as client:
            response = await client.post(GEMINI_URL, json=payload, timeout=10.0)
            if response.status_code == 200:
                result = response.json()
                reply = result['candidates'][0]['content']['parts'][0]['text']
                return reply.strip().lower()  # Приводим к нижнему регистру для реализма
    except Exception as e:
        print(f"Gemini Error: {e}")
    
    # Если нейросеть вдруг не ответила, выдаем дефолтный пацанский ответ
    fallbacks = {"ru": "хз, чет связь лагает", "ua": "хз, щось інет тупить", "en": "idk laggy connection fr"}
    return fallbacks.get(lang, "...")

async def simulate_ai_typing() -> None:
    """Имитируем паузу, пока 'подросток' печатает сообщение"""
    await asyncio.sleep(random.randint(2, 4))

@app.websocket("/ws/{lang}/{user_id}")
async def websocket_endpoint(websocket: WebSocket, lang: str, user_id: str):
    await websocket.accept()
    
    # 1. ПРОВЕРКА ЛИМИТА ИГР
    played_games = USER_LIMITS.get(user_id, 0)
    if played_games >= 5:
        await websocket.send_json({"type": "error", "message": "LIMIT_EXCEEDED"})
        await websocket.close()
        return
    
    USER_LIMITS[user_id] = played_games + 1

    # 2. ПОДБОР СОПЕРНИКА (50% шанс попасть на ИИ или человека)
    if random.choice([True, False]) and WAITING_PLAYERS.get(lang):
        opponent_ws = WAITING_PLAYERS[lang].pop(0)
        await websocket.send_json({"type": "start", "opponent": "human"})
        await opponent_ws.send_json({"type": "start", "opponent": "human"})
        
        try:
            while True:
                data = await websocket.receive_text()
                await opponent_ws.send_json({"type": "msg", "text": data})
        except WebSocketDisconnect:
            try: await opponent_ws.send_json({"type": "opponent_left"})
            except: pass
    else:
        # ИГРА С НЕЙРОСЕТЬЮ GEMINI
        if lang not in WAITING_PLAYERS:
            WAITING_PLAYERS[lang] = []
            
        WAITING_PLAYERS[lang].append(websocket)
        await websocket.send_json({"type": "start", "opponent": "ai"})
        
        try:
            if websocket in WAITING_PLAYERS[lang]:
                WAITING_PLAYERS[lang].remove(websocket)
                
            while True:
                user_msg = await websocket.receive_text()
                
                # Запускаем симуляцию печатания и одновременно спрашиваем Gemini
                await simulate_ai_typing()
                ai_reply = await ask_gemini_teenager(user_msg, lang)
                
                await websocket.send_json({"type": "msg", "text": ai_reply})
        except WebSocketDisconnect:
            if websocket in WAITING_PLAYERS[lang]:
                WAITING_PLAYERS[lang].remove(websocket)
