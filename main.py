from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
import random
import asyncio

app = FastAPI()

# Разрешаем подключение любых фронтендов
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Хранилище лимитов {user_id: количество_игр}
USER_LIMITS = {}
# Очередь живых игроков по языкам
WAITING_PLAYERS = {"ua": [], "en": [], "ru": []}

# Шаблоны ответов ИИ (пока не подключен платный ключ OpenAI, для тестов)
AI_REPLIES = {
    "ua": ["та ладно тобі))", "та рил, а ти що думав?", "хз хз, крінж якийсь", "та людина я, пон?", "та погнали в некст мач", "ти рофлиш?"],
    "en": ["fr fr bro no cap", "lmao context?", "u trippin, i'm human", "idk custom reply", "stfu bro im real", "whatever lol"],
    "ru": ["да ладно тебе)", "рил жиза", "хз, кринж какой-то", "да чел я, успокойся)", "че думаешь я бот?", "пон, ну ок"]
}

async def simulate_ai_typing(lang: str) -> str:
    """Имитирует паузу перед ответом, как будто человек пишет"""
    await asyncio.sleep(random.randint(2, 4))
    return random.choice(AI_REPLIES.get(lang, ["..."]))

@app.websocket("/ws/{lang}/{user_id}")
async def websocket_endpoint(websocket: WebSocket, lang: str, user_id: str):
    await websocket.accept()
    
    # 1. ПРОВЕРКА ЛИМИТА ИГР (Максимум 5)
    played_games = USER_LIMITS.get(user_id, 0)
    if played_games >= 5:
        await websocket.send_json({"type": "error", "message": "LIMIT_EXCEEDED"})
        await websocket.close()
        return
    
    # Засчитываем игру
    USER_LIMITS[user_id] = played_games + 1

    # 2. ПОДБОР СОПЕРНИКА (50% шанс попасть на человека, если кто-то ждет)
    if random.choice([True, False]) and WAITING_PLAYERS.get(lang):
        opponent_ws = WAITING_PLAYERS[lang].pop(0)
        
        # Запускаем чат между людьми
        await websocket.send_json({"type": "start", "opponent": "human"})
        await opponent_ws.send_json({"type": "start", "opponent": "human"})
        
        try:
            while True:
                data = await websocket.receive_text()
                await opponent_ws.send_json({"type": "msg", "text": data})
        except WebSocketDisconnect:
            try:
                await opponent_ws.send_json({"type": "opponent_left"})
            except:
                pass
    else:
        # ИГРА С ИИ
        if lang not in WAITING_PLAYERS:
            WAITING_PLAYERS[lang] = []
            
        # Если живого соперника нет, кидаем текущего юзера в ожидание, но параллельно запускаем ИИ режим
        WAITING_PLAYERS[lang].append(websocket)
        await websocket.send_json({"type": "start", "opponent": "ai"})
        
        try:
            # Убираем из очереди, так как мы уже играем с ботом
            if websocket in WAITING_PLAYERS[lang]:
                WAITING_PLAYERS[lang].remove(websocket)
                
            while True:
                user_msg = await websocket.receive_text()
                # Генерируем ответ подростка-ИИ
                ai_reply = await simulate_ai_typing(lang)
                await websocket.send_json({"type": "msg", "text": ai_reply})
        except WebSocketDisconnect:
            if websocket in WAITING_PLAYERS[lang]:
                WAITING_PLAYERS[lang].remove(websocket)
