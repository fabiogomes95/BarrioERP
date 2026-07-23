"""
app/api/v1/endpoints/notifications.py

Canal de eventos em tempo real (Server-Sent Events). Hoje usado só para
avisar o caixa na hora em que uma mesa solicita a conta pelo celular, sem
precisar ficar checando a tela (polling de 30s na tela de Mesas).

Por que SSE e não WebSocket?
    A necessidade aqui é só o servidor empurrar eventos pro cliente — não tem
    nada que o cliente precise mandar de volta pela mesma conexão. SSE cobre
    esse caso com bem menos código (nativo do navegador via EventSource, com
    reconexão automática embutida) do que abrir/manter um WebSocket.
"""

import asyncio
import json

from fastapi import APIRouter
from fastapi.responses import StreamingResponse

from app.api.deps import CurrentUserSSE
from app.core import events

router = APIRouter()


@router.get(
    "/stream",
    summary="Stream de eventos em tempo real (SSE)",
    description=(
        "Mantém a conexão aberta e empurra eventos assim que acontecem "
        "(hoje: `table.bill_requested`, quando uma mesa solicita a conta). "
        "Autenticação via `?token=` na query string, não no header — "
        "a EventSource do navegador não suporta headers customizados."
    ),
)
async def stream(current_user: CurrentUserSSE) -> StreamingResponse:
    queue = events.subscribe()

    async def event_generator():
        try:
            yield ": conectado\n\n"
            while True:
                raw = await queue.get()
                try:
                    data = json.loads(raw)
                except ValueError:
                    continue
                # Isolamento multi-tenant: só repassa eventos da mesma empresa
                if data.get("company_id") != str(current_user.company_id):
                    continue
                yield f"data: {json.dumps(data)}\n\n"
        except asyncio.CancelledError:
            pass
        finally:
            events.unsubscribe(queue)

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
            "Connection": "keep-alive",
        },
    )
