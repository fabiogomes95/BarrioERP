"""
app/api/v1/endpoints/auth.py

Endpoints de autenticação: login e dados do usuário logado.

ROTAS IMPLEMENTADAS:
    POST /api/v1/auth/login   → Autentica e retorna JWT
    GET  /api/v1/auth/me      → Retorna dados do usuário logado

CONCEITO — O endpoint é fino por design:
    O endpoint tem UMA responsabilidade: receber a requisição HTTP,
    chamar o service, e retornar a resposta HTTP.

    NÃO deve conter regras de negócio.
    NÃO deve fazer queries ao banco diretamente.
    NÃO deve conter lógica complexa.

    Regra de ouro: se você precisar de um comentário para explicar
    O QUE o endpoint faz (além de receber e retornar), provavelmente
    essa lógica deveria estar no service.

CONCEITO — APIRouter:
    Router é como um "sub-app" do FastAPI.
    Agrupa endpoints relacionados com o mesmo prefix e tags.
    O router é registrado no router.py central.
"""

from fastapi import APIRouter, Request

from app.api.deps import CurrentUser, DBSession
from app.core.rate_limit import limiter
from app.models.company import Company
from app.schemas.auth import LoginRequest, TokenResponse, UserMeResponse
from app.services.auth_service import AuthService

# prefix e tags são adicionados no router.py central
# aqui o router é "puro" — só sabe sobre seus próprios endpoints
router = APIRouter()


@router.post(
    "/login",
    response_model=TokenResponse,
    summary="Login com e-mail e senha",
    # status_code padrão é 200 — explícito para clareza
)
@limiter.limit("10/minute")
async def login(
    request: Request,
    credentials: LoginRequest,  # Pydantic valida o JSON automaticamente
    session: DBSession,         # FastAPI injeta a sessão via get_db()
) -> TokenResponse:
    """
    Autentica um usuário e retorna um JWT Bearer Token.

    FLUXO COMPLETO:
        1. FastAPI recebe POST com JSON {"email": "...", "password": "..."}
        2. Pydantic valida e cria LoginRequest
        3. FastAPI injeta a DBSession (sessão de banco)
        4. Criamos AuthService com a sessão
        5. AuthService.login() busca o usuário, verifica senha, gera JWT
        6. Retornamos TokenResponse com o token
        7. FastAPI serializa para JSON: {"access_token": "eyJ...", "token_type": "bearer"}
        8. get_db() faz commit ou rollback ao final

    COMO USAR O TOKEN:
        Nas próximas requisições, envie no header:
        Authorization: Bearer eyJhbGci...

    RESPOSTAS:
        200 → {"access_token": "eyJ...", "token_type": "bearer"}
        401 → {"error": "AUTHENTICATION_ERROR", "message": "Invalid credentials"}
        422 → Erro de validação Pydantic (e-mail inválido, senha vazia)
    """
    service = AuthService(session)
    return await service.login(credentials)


@router.get(
    "/me",
    response_model=UserMeResponse,
    summary="Dados do usuário autenticado",
)
async def me(
    current_user: CurrentUser,  # FastAPI injeta via get_current_user (decodifica JWT + query no banco)
    session: DBSession,
) -> UserMeResponse:
    """
    Retorna os dados do usuário atualmente autenticado.

    FLUXO COMPLETO:
        1. FastAPI lê o header "Authorization: Bearer eyJ..."
        2. oauth2_scheme extrai o token
        3. get_current_user() decodifica o JWT e busca o User no banco
        4. Se inválido/expirado/inativo → HTTP 401 automático
        5. current_user é o objeto User completo do banco
        6. Convertemos para UserMeResponse (sem password_hash!)
        7. FastAPI serializa para JSON

    model_validate() converte um objeto ORM para um schema Pydantic.
    Só funciona porque BaseSchema tem from_attributes=True.

    RESPOSTAS:
        200 → {"id": "...", "email": "...", "role": "...", ...}
        401 → Token ausente, inválido ou expirado
    """
    company = await session.get(Company, current_user.company_id)
    return UserMeResponse.model_validate(current_user).model_copy(
        update={"company_name": company.name if company else None}
    )
