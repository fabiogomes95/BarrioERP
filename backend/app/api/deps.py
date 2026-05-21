"""
app/api/deps.py

Dependências reutilizáveis do FastAPI (Dependency Injection).

CONCEITO — O que é Dependency Injection?
    Em vez de criar objetos manualmente em cada endpoint, você declara
    o que precisa e o FastAPI entrega automaticamente.

    Pensa assim: em vez de ir até a cozinha buscar um ingrediente,
    você coloca na lista de compras e alguém entrega na sua porta.

    Sem DI (manual, repetitivo):
        @router.get("/me")
        async def me(request: Request):
            token = request.headers.get("Authorization").split(" ")[1]
            payload = decode_token(token)
            session = AsyncSessionLocal()
            user = await session.get(User, UUID(payload["sub"]))
            await session.close()
            return user

    Com DI (automático, limpo):
        @router.get("/me")
        async def me(current_user: CurrentUser):
            return current_user

CONCEITO — Annotated + Depends:
    DBSession = Annotated[AsyncSession, Depends(get_db)]
    ↑ tipo Python         ↑ como o FastAPI cria esse valor

    Quando um endpoint declara `session: DBSession`, o FastAPI:
    1. Vê que é uma dependência (Depends)
    2. Chama get_db() para criar a sessão
    3. Injeta a sessão no parâmetro
    4. Ao final, chama o cleanup de get_db() (commit ou rollback)

CONCEITO — OAuth2PasswordBearer:
    Informa ao FastAPI que este endpoint espera um token Bearer.
    tokenUrl é apenas para o Swagger UI saber onde fazer o login.

    No header HTTP:
        Authorization: Bearer eyJhbGci...
"""

from typing import Annotated
from uuid import UUID

from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from jose import JWTError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import decode_token
from app.database.session import get_db
from app.models.user import User

# ── Session ──────────────────────────────────────────────────────────────────

# Tipo anotado que injeta uma AsyncSession via get_db()
# Uso: async def handler(session: DBSession)
DBSession = Annotated[AsyncSession, Depends(get_db)]

# ── OAuth2 Scheme ─────────────────────────────────────────────────────────────

# Declara que a autenticação é via Bearer Token
# tokenUrl → o Swagger UI mostra um botão "Authorize" que posta para este endpoint
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/v1/auth/login")

# ── Dependências de Autenticação ──────────────────────────────────────────────

async def get_current_user_id(
    token: Annotated[str, Depends(oauth2_scheme)],
) -> UUID:
    """
    Extrai o user_id do JWT sem acessar o banco.

    Use quando você só precisa do ID (ex: registrar quem fez a ação).
    Mais leve que get_current_user() pois não faz query.

    FLUXO:
        Header "Authorization: Bearer eyJ..."
            → oauth2_scheme extrai o token
            → decode_token() verifica assinatura e expiração
            → extrai "sub" do payload
            → retorna UUID
    """
    try:
        payload = decode_token(token)
        if payload.get("type") != "access":
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid token type",
                headers={"WWW-Authenticate": "Bearer"},
            )
        return UUID(payload["sub"])
    except (JWTError, KeyError, ValueError):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired token",
            headers={"WWW-Authenticate": "Bearer"},
            # WWW-Authenticate informa ao cliente como se autenticar
        )


async def get_current_user(
    token: Annotated[str, Depends(oauth2_scheme)],
    session: DBSession,
) -> User:
    """
    Decodifica o JWT e carrega o usuário completo do banco.

    Use quando você precisa dos dados completos do usuário logado
    (ex: GET /auth/me, verificações de permissão por empresa).

    FLUXO:
        1. oauth2_scheme extrai o token do header
        2. decode_token() verifica assinatura e expiração
        3. Extrai user_id do payload "sub"
        4. Busca o User no banco (session.get usa cache interno)
        5. Verifica se o usuário está ativo e não deletado
        6. Retorna o objeto User

    Por que verificar is_active aqui e não só no JWT?
    O JWT tem validade de até 60 minutos. Se um usuário for desativado
    durante esse período, o token ainda seria válido. Verificando no banco,
    garantimos que usuários desativados são bloqueados imediatamente.
    """
    try:
        payload = decode_token(token)
        if payload.get("type") != "access":
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED,
                                detail="Invalid token type",
                                headers={"WWW-Authenticate": "Bearer"})
        user_id = UUID(payload["sub"])
    except (JWTError, KeyError, ValueError):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired token",
            headers={"WWW-Authenticate": "Bearer"},
        )

    # session.get() é eficiente: usa o identity map antes de ir ao banco
    user = await session.get(User, user_id)

    if user is None or not user.is_active or user.deleted_at is not None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User not found or inactive",
            headers={"WWW-Authenticate": "Bearer"},
        )

    return user


# ── Tipos anotados para uso nos endpoints ─────────────────────────────────────
# Estes tipos são "atalhos" — em vez de repetir Annotated[...] em todo endpoint

# Retorna o UUID do usuário (sem query ao banco — só decodifica o JWT)
CurrentUserId = Annotated[UUID, Depends(get_current_user_id)]

# Retorna o objeto User completo (faz query ao banco)
CurrentUser = Annotated[User, Depends(get_current_user)]
