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
from jwt import InvalidTokenError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import ForbiddenError
from app.core.security import decode_token
from app.database.session import get_db
from app.models.user import User, UserRole

# ── Session ──────────────────────────────────────────────────────────────────

# Tipo anotado que injeta uma AsyncSession via get_db()
# Uso: async def handler(session: DBSession)
#
# scope="function" é OBRIGATÓRIO: sem ele (padrão "request", FastAPI >= 0.118)
# o commit() do get_db só roda DEPOIS que a resposta já saiu pro navegador.
# A tela recebia "201 OK" do pagamento, buscava a lista de pagamentos na mesma
# hora e às vezes lia o banco ANTES do commit — continuava mostrando "Falta
# R$ X", o caixa registrava de novo e levava "comanda já está totalmente paga",
# e o botão de finalizar só aparecia depois de atualizar a página.
# Com "function", o commit acontece antes da resposta: quem recebe OK já
# encontra o dado gravado.
DBSession = Annotated[AsyncSession, Depends(get_db, scope="function")]

# ── OAuth2 Scheme ─────────────────────────────────────────────────────────────

# Declara que a autenticação é via Bearer Token
# tokenUrl → o Swagger UI mostra um botão "Authorize" que posta para este endpoint
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/v1/auth/login")

# ── Dependências de Autenticação ──────────────────────────────────────────────

# Não existe variante "só decodifica o JWT, sem ir ao banco": ela pularia as
# checagens de usuário desativado e de senha trocada (token_version).

async def _load_user_from_token(
    token: str, session: AsyncSession, expected_type: str = "access",
) -> User:
    """Lógica compartilhada entre get_current_user (header, token "access") e
    a variante por query param do SSE (ticket "sse" de 60s — ver
    create_sse_ticket). Um não serve no lugar do outro."""
    try:
        payload = decode_token(token)
        if payload.get("type") != expected_type:
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED,
                                detail="Invalid token type",
                                headers={"WWW-Authenticate": "Bearer"})
        user_id = UUID(payload["sub"])
    except (InvalidTokenError, KeyError, ValueError):
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

    # Senha trocada depois que o token foi emitido → login antigo não vale mais.
    # Token sem "tv" (emitido antes deste controle) conta como versão 0.
    # O ticket do SSE é emitido na hora a partir de um token já validado aqui.
    if expected_type == "access" and payload.get("tv", 0) != user.token_version:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Sessão encerrada: a senha foi trocada. Entre de novo.",
            headers={"WWW-Authenticate": "Bearer"},
        )

    return user


async def get_current_user(
    token: Annotated[str, Depends(oauth2_scheme)],
    session: DBSession,
) -> User:
    """
    Decodifica o JWT (header Authorization) e carrega o usuário completo do banco.

    Use quando você precisa dos dados completos do usuário logado
    (ex: GET /auth/me, verificações de permissão por empresa).

    Por que verificar is_active aqui e não só no JWT?
    O JWT tem validade de até 60 minutos. Se um usuário for desativado
    durante esse período, o token ainda seria válido. Verificando no banco,
    garantimos que usuários desativados são bloqueados imediatamente.
    """
    return await _load_user_from_token(token, session)


async def get_current_user_from_query_token(
    ticket: str,
    session: DBSession,
) -> User:
    """
    Mesma coisa que get_current_user, mas lê `?ticket=` da URL em vez do
    header Authorization.

    Necessário só para o endpoint SSE de notificações — a EventSource do
    navegador não permite mandar headers customizados. Como URL fica gravada
    no log de acesso, aqui vai só um ticket de 60s que só abre o stream
    (POST /notifications/ticket), nunca o token de login.
    """
    return await _load_user_from_token(ticket, session, expected_type="sse")


def require_roles(user: User, *roles: UserRole) -> None:
    """
    Bloqueia o acesso se o usuário não tiver um dos roles permitidos.

    Uso no endpoint (depois de CurrentUser injetado):
        require_roles(current_user, UserRole.OWNER, UserRole.MANAGER)

    Centraliza a checagem de RBAC nos endpoints (garçom não deve poder
    ver faturamento, aplicar desconto, gerenciar caixa, etc.) — sem isso,
    esconder o botão no frontend não impede a chamada direta à API.
    """
    if user.role not in roles:
        raise ForbiddenError(
            "Você não tem permissão para acessar este recurso."
        )


# ── Tipos anotados para uso nos endpoints ─────────────────────────────────────
# Estes tipos são "atalhos" — em vez de repetir Annotated[...] em todo endpoint

# Retorna o objeto User completo (faz query ao banco)
CurrentUser = Annotated[User, Depends(get_current_user)]

# Variante para SSE — autentica via ?ticket= na URL (ver get_current_user_from_query_token)
CurrentUserSSE = Annotated[User, Depends(get_current_user_from_query_token)]
