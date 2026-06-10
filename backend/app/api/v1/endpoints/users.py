"""
app/api/v1/endpoints/users.py

Endpoints HTTP para o módulo de gestão de usuários.

═══════════════════════════════════════════════════════════════
CONCEITO — Responsabilidade da camada Endpoint
═══════════════════════════════════════════════════════════════

Esta é a camada mais EXTERNA da aplicação — a porta de entrada.
Ela não contém regras de negócio, não faz SQL, não valida lógica.

O que o endpoint FAZ:
    ✓ Define a rota HTTP (método + URL)
    ✓ Declara os parâmetros que precisa (FastAPI injeta automaticamente)
    ✓ Chama o Service com os dados recebidos
    ✓ Define o status code de sucesso
    ✓ Declara o schema de retorno (response_model)

O que o endpoint NÃO faz:
    ✗ Regras de negócio → Service
    ✗ Acesso ao banco    → Repository
    ✗ Validação de tipos → Schema (Pydantic)
    ✗ Tratamento de exceções de domínio → exception_handlers em main.py

Sinal de alerta: se um endpoint tem mais de 10 linhas de lógica,
provavelmente tem código que deveria estar no Service.

═══════════════════════════════════════════════════════════════
CONCEITO — Dependency Injection no FastAPI
═══════════════════════════════════════════════════════════════

FastAPI analisa os TIPOS dos parâmetros para saber como obtê-los:

    data: UserCreate          → JSON do corpo da requisição
    user_id: UUID             → path parameter (da URL)
    role: UserRole | None     → query parameter (?role=waiter)
    session: DBSession        → Depends(get_db) → cria/fecha AsyncSession
    current_user: CurrentUser → Depends(get_current_user) → decodifica JWT + busca User

Você não chama get_db() nem get_current_user() manualmente.
Apenas declara que precisa deles — o FastAPI chama e injeta.

═══════════════════════════════════════════════════════════════
CONCEITO — Fluxo completo de uma requisição neste módulo
═══════════════════════════════════════════════════════════════

POST /api/v1/users
    ↓ FastAPI roteia para create_user()
    ↓ Lê JSON → valida com UserCreate (Pydantic)
    ↓ get_db() → cria AsyncSession
    ↓ get_current_user() → decodifica JWT → busca User no banco
    ↓ _service() → cria UserService com acting_user
    ↓ service.create(data) → RBAC → hash senha → INSERT
    ↓ UserResponse.model_validate(user) → serializa para JSON
    ↓ HTTP 201 Created
    ↓ get_db() → commit() e fecha sessão
"""

from uuid import UUID

from fastapi import APIRouter, Query

from app.api.deps import CurrentUser, DBSession
from app.models.user import UserRole
from app.schemas.common import PaginatedResponse
from app.schemas.user import (
    ChangePasswordRequest,
    UserCreate,
    UserResponse,
    UserUpdate,
)
from app.services.user_service import UserService

router = APIRouter()


# ── Helper ────────────────────────────────────────────────────────────────────


def _service(session: DBSession, user: CurrentUser) -> UserService:
    """
    Cria o UserService com o contexto do usuário logado.

    DIFERENÇA em relação a outros módulos (ex: TableService):
        TableService recebe company_id, establishment_id, user_id separados.
        UserService recebe o objeto User completo (acting_user).

    Por quê? O UserService precisa do `role` para RBAC em cada operação.
    Passar o objeto completo evita uma query extra ao banco apenas para obter o role.
    O construtor do UserService extrai o que precisa internamente.
    """
    return UserService(session=session, acting_user=user)


# ══════════════════════════════════════════════════════════════════════════════
# POST /users — Criar usuário
# ══════════════════════════════════════════════════════════════════════════════


@router.post(
    "/",
    response_model=UserResponse,
    status_code=201,
    summary="Criar usuário",
    description=(
        "Cria um novo usuário na empresa do usuário logado. "
        "Apenas Owners e Managers podem criar usuários. "
        "Managers não podem criar usuários com role Owner."
    ),
)
async def create_user(
    data: UserCreate,
    session: DBSession,
    current_user: CurrentUser,
) -> UserResponse:
    """
    Cria um novo usuário.

    STATUS 201 Created:
        Convenção REST: POST que cria um novo recurso → 201.
        POST que executa uma ação sem criar → 200.

    O `company_id` NÃO está no body — vem do JWT do acting_user.
    Multi-tenancy: um Manager da Empresa A não pode criar usuários
    na Empresa B, mesmo que tente passar outro company_id.

    RBAC (aplicado no Service):
        OWNER   → pode criar qualquer role
        MANAGER → pode criar MANAGER, CASHIER, WAITER, KITCHEN
                  NÃO pode criar OWNER
        Outros  → HTTP 403 Forbidden
    """
    return await _service(session, current_user).create(data)


# ══════════════════════════════════════════════════════════════════════════════
# GET /users — Listar usuários
# ══════════════════════════════════════════════════════════════════════════════


@router.get(
    "/",
    response_model=PaginatedResponse,
    summary="Listar usuários",
    description=(
        "Lista usuários da empresa com filtros opcionais. "
        "Apenas Owners e Managers têm acesso a esta listagem."
    ),
)
async def list_users(
    session: DBSession,
    current_user: CurrentUser,
    role: UserRole | None = Query(
        default=None,
        description="Filtra por cargo. Omita para listar todos os cargos.",
    ),
    establishment_id: UUID | None = Query(
        default=None,
        description="Filtra por filial. Omita para listar de todas as filiais.",
    ),
    active_only: bool = Query(
        default=True,
        description="True (padrão): apenas usuários ativos. False: inclui desativados.",
    ),
    page: int = Query(
        default=1,
        ge=1,
        description="Número da página (começa em 1).",
    ),
    page_size: int = Query(
        default=20,
        ge=1,
        le=100,
        description="Usuários por página (máximo 100).",
    ),
) -> PaginatedResponse:
    """
    Lista usuários com paginação e filtros opcionais.

    QUERY PARAMETERS — lidos da URL automaticamente pelo FastAPI:
        GET /users                            → todos os ativos, página 1
        GET /users?role=waiter                → só garçons
        GET /users?establishment_id=uuid      → só de uma filial
        GET /users?active_only=false          → inclui desativados
        GET /users?page=2&page_size=10        → segunda página, 10 por vez
        GET /users?role=waiter&page=2         → garçons, página 2

    VALIDAÇÕES DE PARÂMETRO:
        ge=1  → "greater or equal to 1" — página mínima é 1
        le=100 → "less or equal to 100" — máximo 100 por página
        FastAPI retorna HTTP 422 automaticamente se violadas.

    RBAC (aplicado no Service):
        Apenas OWNER e MANAGER → HTTP 403 para outros roles.
    """
    return await _service(session, current_user).list_users(
        role=role,
        establishment_id=establishment_id,
        active_only=active_only,
        page=page,
        page_size=page_size,
    )


# ══════════════════════════════════════════════════════════════════════════════
# GET /users/{user_id} — Buscar usuário específico
# ══════════════════════════════════════════════════════════════════════════════


@router.get(
    "/{user_id}",
    response_model=UserResponse,
    summary="Buscar usuário",
    description=(
        "Retorna os dados de um usuário específico. "
        "Owners e Managers podem ver qualquer usuário da empresa. "
        "Outros roles podem ver apenas o próprio perfil."
    ),
)
async def get_user(
    user_id: UUID,
    session: DBSession,
    current_user: CurrentUser,
) -> UserResponse:
    """
    Retorna um usuário pelo ID.

    PATH PARAMETER:
        user_id vem da URL: GET /users/550e8400-e29b-41d4-a716-446655440000
        FastAPI converte string → UUID automaticamente.
        UUID inválido → HTTP 422 antes mesmo de chegar ao Service.

    MULTI-TENANCY:
        Se o user_id pertencer a outra empresa → HTTP 404.
        O cliente não descobre se o UUID existe em outro restaurante.
        (Segurança por obscuridade mínima — não confirmamos existência.)

    RBAC FLEXÍVEL (aplicado no Service):
        OWNER, MANAGER → qualquer usuário da empresa
        Outros         → apenas o próprio perfil (user_id == current_user.id)
    """
    return await _service(session, current_user).get(user_id)


# ══════════════════════════════════════════════════════════════════════════════
# PATCH /users/{user_id} — Atualizar usuário
# ══════════════════════════════════════════════════════════════════════════════


@router.patch(
    "/{user_id}",
    response_model=UserResponse,
    summary="Atualizar usuário",
    description=(
        "Atualiza campos de um usuário existente. "
        "Apenas os campos enviados são alterados (PATCH parcial). "
        "Owners e Managers podem editar subordinados. "
        "Outros roles podem editar apenas name e phone do próprio perfil."
    ),
)
async def update_user(
    user_id: UUID,
    data: UserUpdate,
    session: DBSession,
    current_user: CurrentUser,
) -> UserResponse:
    """
    Atualiza parcialmente um usuário.

    PATCH PARCIAL:
        Apenas os campos presentes no body são alterados.
        Campos ausentes permanecem inalterados.

        {"phone": "+55 11 99999-0000"}     → só phone muda
        {"role": "manager", "is_active": true} → role e is_active mudam
        {}                                 → nada muda (body vazio válido)

    RBAC (aplicado no Service):
        OWNER   → pode editar qualquer campo de qualquer usuário
        MANAGER → pode editar qualquer campo de MANAGER/CASHIER/WAITER/KITCHEN
                  NÃO pode alterar role para OWNER
        Outros  → podem editar apenas name/phone do próprio perfil
    """
    return await _service(session, current_user).update(user_id, data)


# ══════════════════════════════════════════════════════════════════════════════
# DELETE /users/{user_id} — Remover usuário (soft delete)
# ══════════════════════════════════════════════════════════════════════════════


@router.delete(
    "/{user_id}",
    status_code=204,
    summary="Remover usuário",
    description=(
        "Remove um usuário via soft delete (deleted_at é preenchido). "
        "O usuário perde acesso imediatamente. "
        "O histórico de comandas e pagamentos é preservado. "
        "Owners e Managers podem remover subordinados. "
        "Não é possível remover o último Owner da empresa."
    ),
)
async def delete_user(
    user_id: UUID,
    session: DBSession,
    current_user: CurrentUser,
) -> None:
    """
    Remove um usuário (soft delete).

    STATUS 204 No Content:
        Convenção REST: DELETE bem-sucedido → 204, sem body.
        O `return None` implícito + status_code=204 fazem o FastAPI
        retornar uma resposta vazia com status 204.

    SOFT DELETE (diferente de is_active=False):
        DELETE /users/{id}        → soft_delete() → deleted_at = now()
        PATCH  /users/{id}        → {"is_active": false}
                                  → is_active = False (desativação temporária)

        deleted_at → mais permanente, semântica de "exclusão"
        is_active  → toggle, semântica de "suspensão temporária"

    PROTEÇÕES (aplicadas no Service):
        - Apenas OWNER e MANAGER podem remover usuários
        - MANAGER não pode remover OWNERs
        - Não pode remover o último Owner ativo da empresa
        - Não pode se auto-deletar
    """
    await _service(session, current_user).delete(user_id)


# ══════════════════════════════════════════════════════════════════════════════
# PATCH /users/{user_id}/password — Alterar senha
# ══════════════════════════════════════════════════════════════════════════════


@router.patch(
    "/{user_id}/password",
    response_model=UserResponse,
    summary="Alterar senha",
    description=(
        "Altera a senha de um usuário. "
        "Auto-troca: qualquer usuário pode alterar a própria senha informando a senha atual. "
        "Reset por gestor: Owners e Managers podem resetar a senha de subordinados "
        "sem informar a senha atual."
    ),
)
async def change_password(
    user_id: UUID,
    data: ChangePasswordRequest,
    session: DBSession,
    current_user: CurrentUser,
) -> UserResponse:
    """
    Altera a senha de um usuário.

    POR QUE ENDPOINT SEPARADO E NÃO CAMPO NO PATCH?
        Senha é um dado sensível com fluxo diferente dos demais:
        1. Auto-troca requer confirmação da senha atual (current_password)
        2. Reset por gestor não requer a senha atual
        3. Em produção: deve disparar notificação por e-mail
        4. Deve ser registrado separadamente no AuditLog

        Misturar com PATCH genérico tornaria a segurança mais difícil
        de implementar e auditar corretamente.

    DOIS FLUXOS (diferenciados no Service por user_id == current_user.id):

        Fluxo 1 — Auto-troca (current_user está alterando a própria senha):
            {"current_password": "antiga123", "new_password": "nova456", "confirm_password": "nova456"}
            current_password é OBRIGATÓRIO → HTTP 422 se ausente

        Fluxo 2 — Reset por gestor (OWNER/MANAGER alterando a senha de subordinado):
            {"new_password": "nova456", "confirm_password": "nova456"}
            current_password é OPCIONAL → gestor não sabe a senha do funcionário

    NOTA DE ROTEAMENTO:
        Esta rota /{user_id}/password não conflita com /{user_id}
        porque têm profundidades diferentes na árvore de rotas.
        O problema estático vs dinâmico ocorre apenas em rotas do mesmo nível.
    """
    return await _service(session, current_user).change_password(user_id, data)
