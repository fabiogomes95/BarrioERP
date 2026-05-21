"""
app/api/v1/endpoints/tables.py

Endpoints HTTP para o módulo de mesas.

═══════════════════════════════════════════════════════════════
CONCEITO — O que é a camada de Endpoint (API)?
═══════════════════════════════════════════════════════════════

O endpoint é a "porta de entrada" da sua API.
É a camada mais externa — a primeira a receber a requisição HTTP
e a última antes de enviar a resposta.

Analogia: é o GARÇOM do restaurante.
    - Recebe o pedido do cliente (HTTP request)
    - Repassa para o gerente (Service)
    - Devolve o resultado para o cliente (HTTP response)

O que o endpoint FAZ:
    ✓ Define a rota HTTP (GET /tables, POST /tables, etc.)
    ✓ Declara o que precisa via parâmetros (FastAPI injeta automaticamente)
    ✓ Chama o Service com os dados recebidos
    ✓ Retorna o resultado (FastAPI serializa para JSON)
    ✓ Define o status code de sucesso (200, 201, 204)

O que o endpoint NÃO faz:
    ✗ Regras de negócio (isso é o Service)
    ✗ SQL ou acesso ao banco (isso é o Repository)
    ✗ Validação de tipos (isso é o Pydantic/Schema)
    ✗ Tratamento de exceções de domínio (isso é o main.py exception handlers)

TAMANHO IDEAL:
    Um endpoint bem escrito cabe em 5-10 linhas.
    Se estiver maior, provavelmente tem lógica no lugar errado.

═══════════════════════════════════════════════════════════════
CONCEITO — Como o FastAPI injeta dependências?
═══════════════════════════════════════════════════════════════

FastAPI usa INJEÇÃO DE DEPENDÊNCIAS via parâmetros do endpoint:

    async def create_table(
        data: TableCreate,       ← lê do corpo JSON da requisição
        session: DBSession,      ← sessão do banco (injetada pelo get_db)
        current_user: CurrentUser, ← usuário logado (injetado pelo get_current_user)
    )

FastAPI analisa o tipo de cada parâmetro e decide como obtê-lo:
    - TableCreate (Pydantic BaseModel) → lê do corpo da requisição (JSON)
    - DBSession = Annotated[..., Depends(get_db)] → chama get_db()
    - CurrentUser = Annotated[..., Depends(get_current_user)] → chama get_current_user()
    - table_id: UUID → lê da URL (/tables/{table_id})
    - status: TableStatus | None = Query(...) → lê da query string (?status=free)

Você não chama get_db() ou get_current_user() manualmente.
Você apenas DECLARA que precisa deles, e o FastAPI cuida do resto.

═══════════════════════════════════════════════════════════════
CONCEITO — Fluxo completo de uma requisição
═══════════════════════════════════════════════════════════════

POST /api/v1/tables
    └─ JSON: {"number": 5, "label": "Mesa 5", "capacity": 4}
    └─ Header: Authorization: Bearer eyJhbGci...

1. FastAPI roteia para create_table()
2. FastAPI lê o JSON → valida com TableCreate → `data` pronto
3. FastAPI chama get_db() → cria AsyncSession → `session` pronto
4. FastAPI chama get_current_user() com o token do header:
    4a. decode_token() → verifica assinatura JWT
    4b. session.get(User, user_id) → carrega usuário do banco
    4c. verifica is_active=True e não deletado
    4d. → `current_user` pronto
5. create_table() cria o TableService com contexto do usuário
6. service.create(data) é chamado:
    6a. Verifica establishment_id do usuário
    6b. Verifica número único no banco
    6c. Cria objeto Table em memória
    6d. repository.add() → INSERT + flush + refresh
7. TableResponse.model_validate(table) converte Model → Schema
8. FastAPI serializa TableResponse para JSON
9. HTTP 201 Created com o JSON da mesa criada
10. get_db() faz commit() e fecha a sessão
"""

from uuid import UUID

from fastapi import APIRouter, Query

from app.api.deps import CurrentUser, DBSession
from app.models.table import TableStatus
from app.schemas.common import PaginatedResponse
from app.schemas.table import TableCreate, TableResponse, TableUpdate
from app.services.table_service import TableService

router = APIRouter()


# ── Helper ────────────────────────────────────────────────────────────────────


def _service(session: DBSession, user: CurrentUser) -> TableService:
    """
    Cria o TableService com o contexto do usuário logado.

    Centraliza a criação do service para não repetir em cada endpoint.
    O contexto (company_id, establishment_id, user_id) vem do JWT
    via get_current_user() — que já foi chamado para autenticar.

    NOTA: DBSession e CurrentUser aqui são só tipos para o type checker.
    O FastAPI injeta os valores reais via Depends() quando o endpoint é chamado.
    """
    return TableService(
        session=session,
        company_id=user.company_id,
        establishment_id=user.establishment_id,
        user_id=user.id,
    )


# ── POST /tables — Criar mesa ─────────────────────────────────────────────────


@router.post(
    "/",
    response_model=TableResponse,
    status_code=201,
    summary="Criar mesa",
    description="Cria uma nova mesa no estabelecimento do usuário logado.",
)
async def create_table(
    data: TableCreate,
    session: DBSession,
    current_user: CurrentUser,
) -> TableResponse:
    """
    Cria uma nova mesa.

    STATUS 201 Created: usado quando um novo recurso é criado com sucesso.
    Diferente do 200 OK que é para operações gerais de sucesso.
    Convenção REST: POST que cria → 201, POST que processa → 200.

    O establishment_id NÃO é passado no body — vem do JWT do usuário logado.
    Isso é segurança: o cliente não pode criar mesas em outro estabelecimento.
    """
    return await _service(session, current_user).create(data)


# ── GET /tables — Listar mesas ────────────────────────────────────────────────


@router.get(
    "/",
    response_model=PaginatedResponse,
    summary="Listar mesas",
    description="Lista as mesas do estabelecimento do usuário logado.",
)
async def list_tables(
    session: DBSession,
    current_user: CurrentUser,
    status: TableStatus | None = Query(
        default=None,
        description="Filtra por status. Omita para listar todas as mesas ativas.",
    ),
    page: int = Query(default=1, ge=1, description="Número da página (começa em 1)"),
    page_size: int = Query(
        default=50, ge=1, le=100, description="Mesas por página (máximo 100)"
    ),
) -> PaginatedResponse:
    """
    Lista mesas com paginação e filtro opcional por status.

    QUERY PARAMETERS (na URL):
        GET /tables              → todas as mesas ativas
        GET /tables?status=free  → só mesas livres
        GET /tables?page=2       → segunda página

    Query parameters são definidos com Query() — FastAPI lê da URL automaticamente.
    Diferentes de path parameters (/{table_id}) que ficam na URL diretamente.
    Diferentes de body parameters (JSON no POST) que ficam no corpo da requisição.
    """
    return await _service(session, current_user).list(
        status=status,
        page=page,
        page_size=page_size,
    )


# ── GET /tables/{table_id} — Buscar mesa específica ──────────────────────────


@router.get(
    "/{table_id}",
    response_model=TableResponse,
    summary="Buscar mesa",
    description="Retorna os dados de uma mesa específica.",
)
async def get_table(
    table_id: UUID,
    session: DBSession,
    current_user: CurrentUser,
) -> TableResponse:
    """
    Retorna uma mesa pelo ID.

    PATH PARAMETER:
        table_id vem direto da URL: GET /tables/550e8400-e29b-41d4-a716-446655440000
        FastAPI converte automaticamente a string para UUID.
        Se o UUID for inválido → HTTP 422 (Pydantic validation error).

    MULTI-TENANCY:
        Se o table_id pertencer a outro restaurante → HTTP 404.
        O Service usa get_by_establishment() que filtra por establishment_id.
    """
    return await _service(session, current_user).get(table_id)


# ── PATCH /tables/{table_id} — Atualizar mesa ─────────────────────────────────


@router.patch(
    "/{table_id}",
    response_model=TableResponse,
    summary="Atualizar mesa",
    description="Atualiza campos de uma mesa existente. Requer `version` para locking otimista.",
)
async def update_table(
    table_id: UUID,
    data: TableUpdate,
    session: DBSession,
    current_user: CurrentUser,
) -> TableResponse:
    """
    Atualiza parcialmente uma mesa.

    EXEMPLO DE REQUEST BODY:
        {"label": "Mesa VIP", "capacity": 8, "version": 3}

    Apenas os campos enviados são atualizados.
    O campo `version` é OBRIGATÓRIO — é o número de versão atual da mesa.
    Obtenha via GET /tables/{id} e envie de volta no PATCH.

    RESPOSTA COM VERSÃO ATUALIZADA:
        A resposta inclui a nova versão (ex: version: 4).
        Use esta versão no próximo PATCH.
    """
    return await _service(session, current_user).update(table_id, data)


# ── DELETE /tables/{table_id} — Desativar mesa ────────────────────────────────


@router.delete(
    "/{table_id}",
    status_code=204,
    summary="Desativar mesa",
    description="Desativa uma mesa (soft delete). A mesa some da listagem mas o histórico é preservado.",
)
async def deactivate_table(
    table_id: UUID,
    session: DBSession,
    current_user: CurrentUser,
) -> None:
    """
    Desativa (soft delete) uma mesa.

    STATUS 204 No Content: operação bem-sucedida, sem body de resposta.
    Convenção REST: DELETE bem-sucedido → 204 (sem body).
    O `return None` explícito + status_code=204 fazem o FastAPI retornar 204.

    SOFT DELETE:
        Não deleta fisicamente — seta is_active = False.
        A mesa some da listagem normal, mas o histórico fica intacto.

    REGRA DE NEGÓCIO:
        Mesas com status OCCUPIED (comanda aberta) não podem ser desativadas.
        → HTTP 422 Business Rule Violation.
    """
    await _service(session, current_user).deactivate(table_id)
