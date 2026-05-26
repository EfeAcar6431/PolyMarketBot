from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from services.agent_runner import broadcaster

router = APIRouter()


@router.websocket("/ws/feed")
async def websocket_feed(websocket: WebSocket):
    await websocket.accept()
    await broadcaster.connect(websocket)
    try:
        while True:
            await websocket.receive_text()
    except WebSocketDisconnect:
        broadcaster.disconnect(websocket)
