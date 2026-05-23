from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
import random
import asyncio
import httpx

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Твой API-ключ Google Gemini
GEMINI_API_KEY = "AIzaSyDR1uG-0yPYdgec4I7xd4FBOVVRVCxbf3M"
# Используем стабильную версию API v1
GEMINI_URL = f"https://generativelanguage.googleapis.com/v1/models/gemini-1.5-flash:generateContent?key={GEMINI_API_KEY}"

USER_LIMITS = {}
WAITING_PLAYERS = {"ua": [], "en": [], "ru": []}

async def ask_gemini_teenager(user_message: str, lang: str) -> str:
    """Запрос к ИИ Gemini с правильной структурой системных инструкций"""
    
    system_instruction = (
        "Ты - реальный человек, подросток (16-19 лет), общаешься в анонимном чате. "
        "Твоя цель - общаться непринужденно и доказать, что ты не бот. "
        "Отвечай очень коротко (от 1 до 5 слов). Используй молодежный сленг, пиши только маленькими буквами "
        "без точек на конце. Можно использовать простые скобочки типа ) или лол, хз, пон, рил, жиза. "
        "Не будь слишком вежливым, не используй списки. Если говорят что ты бот - отвечай 'че за бред' или 'сам бот'. "
        f"Язык общения строго: {lang}."
    )

    # Правильный формат запроса по документации Google: разделяем системный промт и сообщение пользователя
    payload = {
        "contents": [
            {
                "role": "user",
                "parts": [{"text": user_message}]
            }
        ],
        "systemInstruction": {
            "parts": [{"text": system_instruction}]
        },
        "generationConfig": {
            "temperature": 0.8,
            "maxOutputTokens": 50
        }
    }

    try:
        async with httpx.AsyncClient() as client:
            response = await client.post(GEMINI_URL, json=payload, timeout=8.0)
            
            # Если Google ругается, выведем ошибку в логи Render
            if response.status_code != 200:
                print(f"Google API Error! Status: {response.status_code}, Response: {response.text}")
                return "хз, чет связь лагает"
                
            result = response.json()
            reply = result['candidates'][0]['content']['parts'][0]['text']
            return reply.strip().lower()
            
    except Exception as e:
        print(f"Ошибка отправки запроса: {e}")
    
    return "хz, чето лагануло"

async def simulate_ai_typing() -> None:
    await asyncio.sleep(random.randint(2, 3))

@app.websocket("/ws/{lang}/{user_id}")
async def websocket_endpoint(websocket: WebSocket, lang: str, user_id: str):
    await websocket.accept()
    
    played_games = USER_LIMITS.get(user_id, 0)
    if played_games >= 5:
        await websocket.send_json({"type": "error", "message": "LIMIT_EXCEEDED"})
        await websocket.close()
        return
    
    USER_LIMITS[user_id] = played_games + 1

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
        if lang not in WAITING_PLAYERS:
            WAITING_PLAYERS[lang] = []
            
        WAITING_PLAYERS[lang].append(websocket)
        await websocket.send_json({"type": "start", "opponent": "ai"})
        
        try:
            if websocket in WAITING_PLAYERS[lang]:
                WAITING_PLAYERS[lang].remove(websocket)
                
            while True:
                user_msg = await websocket.receive_text()
                
                # Сначала генерируем ответ от ИИ, а потом искусственно ждем (чтобы юзер не ждал лишнее время)
                ai_reply = await ask_gemini_teenager(user_msg, lang)
                await simulate_ai_typing()
                
                await websocket.send_json({"type": "msg", "text": ai_reply})
        except WebSocketDisconnect:
            if websocket in WAITING_PLAYERS[lang]:
                WAITING_PLAYERS[lang].remove(websocket)
