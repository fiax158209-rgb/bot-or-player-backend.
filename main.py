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

# ТВОЙ НОВЫЙ КЛЮЧ С OPENROUTER
OPENROUTER_API_KEY = "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"
OPENROUTER_URL = "https://openrouter.ai/api/v1/chat/completions"

USER_LIMITS = {}
WAITING_PLAYERS = {"ua": [], "en": [], "ru": []}

async def ask_gemini_teenager(user_message: str, lang: str) -> str:
    """Запрос к ИИ через OpenRouter (работает без региональных блокировок)"""
    
    system_instruction = (
        "Ты - реальный человек, подросток (16-19 лет), общаешься в анонимном чате. "
        "Твоя цель - общаться непринужденно и доказать, что ты не бот. "
        "Отвечай очень коротко (от 1 до 5 слов). Используй молодежный сленг, пиши только маленькими буквами "
        "без точек на конце. Можно использовать простые скобочки типа ) или лол, хз, пон, рил, жиза. "
        "Не будь слишком вежливым, не используй списки. Если говорят что ты бот - отвечай 'че за бред' или 'сам бот'. "
        f"Язык общения строго: {lang}."
    )

    headers = {
        "Authorization": f"Bearer {OPENROUTER_API_KEY}",
        "Content-Type": "application/json"
    }

    payload = {
        # Используем абсолютно бесплатную и умную модель Google Gemini 1.5 Flash через мост
        "model": "google/gemini-flash-1.5-8b:free", 
        "messages": [
            {"role": "system", "content": system_instruction},
            {"role": "user", "content": user_message}
        ],
        "temperature": 0.85,
        "max_tokens": 40
    }

    try:
        async with httpx.AsyncClient() as client:
            response = await client.post(OPENROUTER_URL, json=payload, headers=headers, timeout=10.0)
            
            if response.status_code != 200:
                print(f"OpenRouter Error: {response.status_code}, {response.text}")
                return "хз, чет связь лагает"
                
            result = response.json()
            reply = result['choices'][0]['message']['content']
            return reply.strip().lower()
            
    except Exception as e:
        print(f"Ошибка OpenRouter: {e}")
    
    return "хз, чето лагануло"

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
                
                ai_reply = await ask_gemini_teenager(user_msg, lang)
                await simulate_ai_typing()
                
                await websocket.send_json({"type": "msg", "text": ai_reply})
        except WebSocketDisconnect:
            if websocket in WAITING_PLAYERS[lang]:
                WAITING_PLAYERS[lang].remove(websocket)
