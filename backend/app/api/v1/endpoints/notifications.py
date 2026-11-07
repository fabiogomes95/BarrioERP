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
from typing import Literal
from uuid import UUID

from fastapi import APIRouter
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from app.api.deps import CurrentUser, CurrentUserSSE, DBSession
from app.core import events
from app.services import direct_print

router = APIRouter()


class KitchenItemIn(BaseModel):
    name: str = Field(max_length=200)
    qty: int = Field(ge=1, le=99)
    notes: str | None = Field(default=None, max_length=300)


class PrintRequestIn(BaseModel):
    order_id: UUID
    print_type: Literal["comanda", "cozinha"] = "comanda"
    # Cozinha: itens escolhidos na tela (ex: só o item recém-lançado).
    # Sem lista = todos os itens da comanda que vão pra cozinha.
    items: list[KitchenItemIn] | None = Field(default=None, max_length=60)


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


@router.post(
    "/print",
    summary="Solicita impressão remota do recibo",
    description=(
        "Publica um evento pro dispositivo marcado como 'impressora do bar' "
        "(a impressora térmica só está fisicamente ligada a um PC — a maioria "
        "dos dispositivos, celulares inclusive, não tem como imprimir e deve "
        "mandar a impressão pra quem tem)."
    ),
)
async def request_print(
    data: PrintRequestIn,
    session: DBSession,
    current_user: CurrentUser,
) -> dict:
    # Térmica ligada neste PC: imprime direto, sem navegador (o window.print()
    # disparado por SSE era bloqueado pelo Chrome como pop-up e o alert()
    # travava a tela do caixa). Sem impressora configurada ou se falhar, cai
    # no caminho antigo (evento pro PC marcado como "impressora do bar").
    if current_user.establishment_id is not None:
        items = [(i.qty, i.name, i.notes) for i in data.items] if data.items else None
        printed = await direct_print.print_or_fallback(
            data.print_type, current_user.company_id, current_user.establishment_id, data.order_id,
            items=items,
        )
        return {"status": "printed" if printed else "sent"}

    await events.publish(
        session,
        "print.request",
        company_id=str(current_user.company_id),
        establishment_id=None,
        order_id=str(data.order_id),
        print_type=data.print_type,
    )
    return {"status": "sent"}
