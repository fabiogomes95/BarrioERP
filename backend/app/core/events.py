"""
app/core/events.py

Barramento de eventos em tempo real via PostgreSQL LISTEN/NOTIFY.

POR QUE POSTGRES E NÃO SÓ MEMÓRIA?
    O backend roda como dois processos uvicorn separados (HTTP na porta 8000
    e HTTPS na porta 443 — ver instalar_servicos.ps1). Um dicionário em
    memória num processo não seria visto pelo outro processo. O Postgres já
    é compartilhado pelos dois, então usamos LISTEN/NOTIFY como o barramento:
    qualquer processo que dispare NOTIFY é ouvido por todos os processos com
    LISTEN ativo, não importa qual originou o evento.

USO:
    - start_listener()/stop_listener() rodam uma vez por processo, no lifespan
    - publish() é chamado dentro de um service, na mesma sessão/transação —
      o Postgres só entrega a notificação depois do COMMIT
    - subscribe()/unsubscribe() são usados pelo endpoint SSE, um por conexão
"""

import asyncio
import json
import logging

import asyncpg
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings

logger = logging.getLogger(__name__)

CHANNEL = "barrio_events"

_subscribers: set[asyncio.Queue] = set()
_listener_conn: asyncpg.Connection | None = None


def _on_notify(connection: object, pid: int, channel: str, payload: str) -> None:
    for queue in list(_subscribers):
        queue.put_nowait(payload)


async def start_listener() -> None:
    """Abre uma conexão raw dedicada ao Postgres só para LISTEN (fora do pool
    do SQLAlchemy — uma conexão em LISTEN precisa ficar viva indefinidamente,
    o que não combina com um pool de conexões de requisição)."""
    global _listener_conn
    _listener_conn = await asyncpg.connect(
        host=settings.POSTGRES_HOST,
        port=settings.POSTGRES_PORT,
        user=settings.POSTGRES_USER,
        password=settings.POSTGRES_PASSWORD,
        database=settings.POSTGRES_DB,
    )
    await _listener_conn.add_listener(CHANNEL, _on_notify)
    logger.info("Escutando canal '%s' no Postgres para eventos em tempo real.", CHANNEL)


async def stop_listener() -> None:
    global _listener_conn
    if _listener_conn is not None:
        await _listener_conn.remove_listener(CHANNEL, _on_notify)
        await _listener_conn.close()
        _listener_conn = None


def subscribe() -> asyncio.Queue:
    queue: asyncio.Queue = asyncio.Queue()
    _subscribers.add(queue)
    return queue


def unsubscribe(queue: asyncio.Queue) -> None:
    _subscribers.discard(queue)


async def publish(session: AsyncSession, event_type: str, **data: object) -> None:
    """
    Publica um evento no canal — usa pg_notify() pela mesma sessão/transação
    da requisição em vez de NOTIFY direto, porque assim os parâmetros vão
    como argumento de função (bind seguro), sem escapar aspas manualmente.

    A entrega só acontece depois do COMMIT da transação (comportamento nativo
    do Postgres), então nunca notifica um evento que acabou sendo revertido.
    """
    payload = json.dumps({"type": event_type, **data})
    await session.execute(
        text("SELECT pg_notify(:channel, :payload)"),
        {"channel": CHANNEL, "payload": payload},
    )
