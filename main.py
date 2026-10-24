import json
import secrets
from pathlib import Path

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

BASE_DIR = Path(__file__).resolve().parent
app = FastAPI(title="GhostChat MVP")
app.mount("/static", StaticFiles(directory=BASE_DIR / "static"), name="static")


class ChatHub:
    def __init__(self):
        self.connections: dict[WebSocket, dict[str, str]] = {}

    async def connect(self, ws: WebSocket, nickname: str, user_id: str):
        await ws.accept()
        self.connections[ws] = {"nickname": nickname, "user_id": user_id}
        await self.broadcast({
            "type": "system",
            "text": f"{nickname} подключился к чату."
        })

    def disconnect(self, ws: WebSocket):
        user = self.connections.pop(ws, None)
        return user

    async def broadcast(self, message: dict):
        stale = []
        payload = json.dumps(message, ensure_ascii=False)
        for ws in list(self.connections):
            try:
                await ws.send_text(payload)
            except Exception:
                stale.append(ws)
        for ws in stale:
            self.connections.pop(ws, None)


hub = ChatHub()


@app.get("/")
async def index():
    return FileResponse(BASE_DIR / "static" / "index.html")


@app.websocket("/ws")
async def websocket_chat(ws: WebSocket):
    nickname = (ws.query_params.get("nickname") or "Гость").strip()[:24]
    user_id = (ws.query_params.get("user_id") or "").strip()[:40]
    if not user_id:
        user_id = secrets.token_hex(8)

    await hub.connect(ws, nickname, user_id)
    try:
        while True:
            raw = await ws.receive_text()
            try:
                data = json.loads(raw)
            except json.JSONDecodeError:
                continue

            if data.get("type") != "message":
                continue
            text = str(data.get("text", "")).strip()[:2000]
            if not text:
                continue

            await hub.broadcast({
                "type": "message",
                "nickname": nickname,
                "user_id": user_id,
                "text": text
            })
    except WebSocketDisconnect:
        user = hub.disconnect(ws)
        if user:
            await hub.broadcast({
                "type": "system",
                "text": f'{user["nickname"]} отключился от чата.'
            })
    except Exception:
        user = hub.disconnect(ws)
        if user:
            await hub.broadcast({
                "type": "system",
                "text": f'{user["nickname"]} отключился от чата.'
            })
