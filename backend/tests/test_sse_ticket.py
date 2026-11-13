"""Ticket do SSE: só abre o stream, vence em 60s, e o token de login não vale no lugar dele."""

from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest
from fastapi import HTTPException
from jose import jwt

from app.api.deps import _load_user_from_token
from app.core.config import settings
from app.core.security import create_access_token, create_sse_ticket, decode_token


def _session_com_usuario():
    user = MagicMock(is_active=True, deleted_at=None)
    session = MagicMock()
    session.get = AsyncMock(return_value=user)
    return session, user


async def test_ticket_abre_o_stream():
    session, user = _session_com_usuario()
    assert await _load_user_from_token(create_sse_ticket(uuid4()), session, expected_type="sse") is user


async def test_token_de_login_nao_abre_o_stream():
    session, _ = _session_com_usuario()
    with pytest.raises(HTTPException) as e:
        await _load_user_from_token(create_access_token(uuid4()), session, expected_type="sse")
    assert e.value.status_code == 401


async def test_ticket_nao_autentica_a_api():
    session, _ = _session_com_usuario()
    with pytest.raises(HTTPException) as e:
        await _load_user_from_token(create_sse_ticket(uuid4()), session)
    assert e.value.status_code == 401


def test_ticket_vence_em_um_minuto():
    payload = decode_token(create_sse_ticket(uuid4()))
    vida = datetime.fromtimestamp(payload["exp"], UTC) - datetime.fromtimestamp(payload["iat"], UTC)
    assert vida <= timedelta(seconds=60)


async def test_ticket_vencido_e_recusado():
    session, _ = _session_com_usuario()
    agora = datetime.now(UTC)
    vencido = jwt.encode(
        {"sub": str(uuid4()), "type": "sse", "iat": agora - timedelta(minutes=2), "exp": agora - timedelta(minutes=1)},
        settings.SECRET_KEY, algorithm=settings.ALGORITHM,
    )
    with pytest.raises(HTTPException):
        await _load_user_from_token(vencido, session, expected_type="sse")
