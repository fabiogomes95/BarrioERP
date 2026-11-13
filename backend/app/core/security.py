"""
app/core/security.py

Utilitários de segurança: hashing de senhas e geração/decodificação de JWT.

CONCEITO — bcrypt:
    bcrypt é um algoritmo de hashing PROPOSITALMENTE LENTO.
    É lento porque o objetivo é dificultar ataques de força bruta:
    se um invasor tiver o hash, vai demorar muito para tentar senhas.

    Características importantes:
    - Cada hash é ÚNICO mesmo para a mesma senha (usa salt aleatório)
    - Irreversível: não é possível obter a senha original do hash
    - Lento: cada verificação leva ~100ms — aceitável para login, ruim para ataques

CONCEITO — JWT (JSON Web Token):
    Um token JWT é como um crachá digital assinado.
    Quem tem o crachá prova que passou pelo servidor de autenticação.

    Estrutura: HEADER.PAYLOAD.SIGNATURE (separados por pontos)

    O payload é Base64 — qualquer um pode LER.
    A assinatura é HMAC — só o servidor pode CRIAR ou VERIFICAR.
    Nunca coloque senhas ou dados sensíveis no payload!
"""

from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import UUID

import bcrypt
import jwt  # PyJWT (antes python-jose, pouco mantido)
from jwt import InvalidTokenError  # noqa: F401 — usado pelos callers (deps.py)

from app.core.config import settings

# bcrypt direto (antes via passlib, abandonado e incompatível com o bcrypt
# atual — gerava "error reading bcrypt version" no log a cada login). Os
# hashes são os mesmos ($2b$...): senhas já cadastradas continuam valendo.
BCRYPT_ROUNDS = 12
# bcrypt só usa os primeiros 72 bytes da senha; corta explícito (passlib
# fazia isso calado, e o bcrypt 5 passou a dar erro em vez de cortar).
_BCRYPT_MAX_BYTES = 72


def _pw_bytes(plain: str) -> bytes:
    return plain.encode("utf-8")[:_BCRYPT_MAX_BYTES]


def hash_password(plain: str) -> str:
    """
    Transforma uma senha em texto puro em um hash bcrypt.

    Exemplo:
        hash = hash_password("minha_senha")
        # → "$2b$12$xKzA3...oq4p2" (diferente a cada chamada!)
    """
    return bcrypt.hashpw(_pw_bytes(plain), bcrypt.gensalt(rounds=BCRYPT_ROUNDS)).decode("ascii")


def verify_password(plain: str, hashed: str) -> bool:
    """
    Verifica se uma senha em texto puro corresponde ao hash.

    O bcrypt extrai o salt embutido no hash e refaz o processo,
    comparando o resultado com o hash armazenado.

    Exemplo:
        verify_password("minha_senha", hash_armazenado)  # True
        verify_password("senha_errada", hash_armazenado) # False
    """
    if not hashed:
        return False
    try:
        return bcrypt.checkpw(_pw_bytes(plain), hashed.encode("ascii"))
    except ValueError:  # hash corrompido/formato desconhecido = senha errada, não erro 500
        return False


def create_access_token(subject: UUID, extra: dict[str, Any] | None = None) -> str:
    """
    Cria um JWT de acesso.

    O payload inclui:
    - sub  : subject — o ID do usuário (quem é o dono do token)
    - exp  : expiration — quando o token expira (Unix timestamp)
    - iat  : issued at — quando foi criado
    - type : "access" — para distinguir de refresh tokens

    Campos extras (company_id, role) são adicionados pelo AuthService
    para evitar queries extras a cada requisição autenticada.
    """
    payload: dict[str, Any] = {
        "sub": str(subject),
        "exp": datetime.now(UTC) + timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES),
        "iat": datetime.now(UTC),
        "type": "access",
    }
    if extra:
        payload.update(extra)
    # jwt.encode assina o payload com SECRET_KEY usando HMAC-SHA256
    return jwt.encode(payload, settings.SECRET_KEY, algorithm=settings.ALGORITHM)


def create_refresh_token(subject: UUID) -> str:
    """
    Cria um JWT de refresh (vida longa).

    Refresh tokens têm vida mais longa (dias) e só servem para
    obter um novo access token — não autenticam endpoints diretamente.
    (Implementação futura)
    """
    payload: dict[str, Any] = {
        "sub": str(subject),
        "exp": datetime.now(UTC) + timedelta(days=settings.REFRESH_TOKEN_EXPIRE_DAYS),
        "iat": datetime.now(UTC),
        "type": "refresh",
    }
    return jwt.encode(payload, settings.SECRET_KEY, algorithm=settings.ALGORITHM)


SSE_TICKET_SECONDS = 60


def create_sse_ticket(subject: UUID) -> str:
    """
    Ticket de vida curta (60s) que só serve pra abrir o stream de
    notificações (SSE). A EventSource do navegador não manda header, então o
    que autentica vai na URL — e URL vai parar no log de acesso. Antes ia o
    token de login inteiro (válido por horas, abre a API toda); agora vai
    este ticket, que expira em 1 minuto e não autentica nenhuma outra rota.
    """
    now = datetime.now(UTC)
    payload: dict[str, Any] = {
        "sub": str(subject),
        "exp": now + timedelta(seconds=SSE_TICKET_SECONDS),
        "iat": now,
        "type": "sse",
    }
    return jwt.encode(payload, settings.SECRET_KEY, algorithm=settings.ALGORITHM)


def decode_token(token: str) -> dict[str, Any]:
    """
    Decodifica e valida um JWT.

    jwt.decode AUTOMATICAMENTE:
    - Verifica a assinatura (detecta adulteração)
    - Verifica a expiração (campo "exp")
    - Lança InvalidTokenError se qualquer verificação falhar

    O caller deve capturar InvalidTokenError para tratar tokens inválidos.
    """
    return jwt.decode(token, settings.SECRET_KEY, algorithms=[settings.ALGORITHM])
