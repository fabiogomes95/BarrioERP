"""
app/api/v1/endpoints/orders.py

Endpoints HTTP para o módulo de comandas.

═══════════════════════════════════════════════════════════════
CONCEITO — Rotas estáticas vs dinâmicas (IMPORTANTE!)
═══════════════════════════════════════════════════════════════

Um problema clássico em APIs REST:

    GET /orders/open       ← rota ESTÁTICA (a palavra "open" é literal)
    GET /orders/{order_id} ← rota DINÂMICA (qualquer UUID)

Se registrarmos nessa ORDEM:
    1. GET /{order_id}  ← registrado primeiro
    2. GET /open        ← registrado depois

    → Uma requisição GET /orders/open tentaria usar "open" como UUID
    → Pydantic daria erro de validação: "open" não é um UUID válido
    → HTTP 422 Unprocessable Entity

Se registrarmos na ORDEM CORRETA:
    1. GET /open        ← registrado primeiro
    2. GET /{order_id}  ← registrado depois

    → Uma requisição GET /orders/open casa com a rota estática ✓
    → Uma requisição GET /orders/uuid... casa com a rota dinâmica ✓

POR ISSO: list_open_orders está declarado ANTES de get_order neste arquivo.
FastAPI (via Starlette) usa first-match — a primeira rota que casa ganha.

═══════════════════════════════════════════════════════════════
CONCEITO — Status codes HTTP no contexto de comandas
═══════════════════════════════════════════════════════════════

    POST /orders            → 201 Created (nova comanda criada)
    GET  /orders/open       → 200 OK      (lista retornada)
    GET  /orders/{id}       → 200 OK      (recurso retornado)
    POST /orders/{id}/items → 200 OK      (recurso atualizado, não criado)
    PATCH /orders/{id}/close → 200 OK     (recurso atualizado)

Por que POST /items retorna 200 e não 201?
    O item em si é criado (201), mas o que retornamos é a COMANDA atualizada.
    A comanda já existia — ela foi modificada, não criada.
    Retornar o estado atualizado da comanda é mais útil que retornar
    apenas o item criado. Por isso, 200 (Modified) faz mais sentido.

    Convenção adotada: endpoints que modificam um recurso e retornam
    o estado completo atualizado → 200 OK.
"""

from uuid import UUID

from fastapi import APIRouter, Query

from app.api.deps import CurrentUser, DBSession
from app.schemas.order import (
    OrderClose,
    OrderCreate,
    OrderItemAdd,
    OrderResponse,
)
from app.services.order_service import OrderService

router = APIRouter()


# ── Helper ─────────────────────────────────────────────────────────────────────


def _service(session: DBSession, user: CurrentUser) -> OrderService:
    """
    Cria o OrderService com o contexto do usuário logado.

    O OrderService usa dois repositories internamente:
        - OrderRepository → para comandas e itens
        - TableRepository → para atualizar status da mesa

    Ambos recebem a mesma `session` → mesma transação.
    """
    return OrderService(
        session=session,
        company_id=user.company_id,
        establishment_id=user.establishment_id,
        user_id=user.id,
    )


# ── POST /orders — Abrir nova comanda ─────────────────────────────────────────


@router.post(
    "/",
    response_model=OrderResponse,
    status_code=201,
    summary="Abrir comanda",
    description="Abre uma nova comanda para uma mesa. A mesa é automaticamente marcada como OCCUPIED.",
)
async def open_order(
    data: OrderCreate,
    session: DBSession,
    current_user: CurrentUser,
) -> OrderResponse:
    """
    Abre uma nova comanda para a mesa indicada em `table_id`.

    REGRAS:
        - A mesa deve existir e estar ativa
        - A mesa não pode ter outra comanda aberta
        - A mesa é automaticamente marcada como OCCUPIED

    Retorna a comanda recém-criada (com lista de items vazia).
    """
    return await _service(session, current_user).open_order(data)


# ── GET /orders/open — Listar comandas abertas ────────────────────────────────
# IMPORTANTE: Esta rota DEVE vir ANTES de GET /{order_id}!
# Ver explicação no cabeçalho do arquivo sobre rotas estáticas vs dinâmicas.


@router.get(
    "/open",
    response_model=list[OrderResponse],
    summary="Listar comandas abertas",
    description=(
        "Retorna comandas abertas do estabelecimento com seus itens. "
        "Use `table_id` para filtrar pela comanda de uma mesa específica."
    ),
)
async def list_open_orders(
    session: DBSession,
    current_user: CurrentUser,
    table_id: UUID | None = Query(
        default=None,
        description=(
            "Filtra pela comanda aberta de uma mesa específica. "
            "Omita para listar todas as comandas abertas do salão."
        ),
    ),
) -> list[OrderResponse]:
    """
    Lista comandas abertas do estabelecimento.

    SEM FILTRO:
        GET /orders/open
        → Todas as comandas abertas (visão geral — útil para o painel do gerente)

    COM FILTRO:
        GET /orders/open?table_id=uuid-da-mesa
        → Apenas a comanda aberta dessa mesa (0 ou 1 resultado)
        → Usado pelo frontend quando o garçom abre a tela de uma mesa específica

    Inclui os itens de cada comanda (eager loaded — sem N+1 queries).
    Ordenadas por hora de abertura: as mais antigas aparecem primeiro.
    """
    return await _service(session, current_user).list_open(table_id=table_id)


# ── GET /orders/{order_id} — Detalhes da comanda ──────────────────────────────


@router.get(
    "/{order_id}",
    response_model=OrderResponse,
    summary="Detalhes da comanda",
    description="Retorna uma comanda específica com todos os seus itens.",
)
async def get_order(
    order_id: UUID,
    session: DBSession,
    current_user: CurrentUser,
) -> OrderResponse:
    """
    Retorna os detalhes completos de uma comanda.

    Inclui todos os itens (ativos e cancelados).
    Retorna 404 se a comanda não existir ou pertencer a outro estabelecimento.
    """
    return await _service(session, current_user).get(order_id)


# ── POST /orders/{order_id}/items — Adicionar item ────────────────────────────


@router.post(
    "/{order_id}/items",
    response_model=OrderResponse,
    status_code=200,
    summary="Adicionar item à comanda",
    description=(
        "Adiciona um item à comanda e recalcula o total. "
        "Se menu_item_id for fornecido, nome e preço vêm do cardápio. "
        "Caso contrário, item_name e unit_price são obrigatórios."
    ),
)
async def add_item(
    order_id: UUID,
    data: OrderItemAdd,
    session: DBSession,
    current_user: CurrentUser,
) -> OrderResponse:
    """
    Adiciona um item à comanda.

    DOIS MODOS:

    1. Item do cardápio:
        {"menu_item_id": "uuid...", "quantity": 2, "notes": "sem sal"}
        → Nome e preço são buscados do cardápio (snapshot imutável)

    2. Item manual:
        {"item_name": "Sobremesa especial", "unit_price": 15.00, "quantity": 1}
        → Útil para itens fora do cardápio

    Retorna a comanda atualizada com o novo item incluído.
    O campo `total` é recalculado automaticamente pelo servidor.
    """
    return await _service(session, current_user).add_item(order_id, data)


# ── DELETE /orders/{order_id}/items/{item_id} — Cancelar item ─────────────────


@router.delete(
    "/{order_id}/items/{item_id}",
    response_model=OrderResponse,
    summary="Cancelar item da comanda",
    description=(
        "Cancela um item de uma comanda aberta. "
        "O item é marcado como CANCELLED e o total da comanda é recalculado. "
        "Itens já SERVED não podem ser cancelados. "
        "Use o parâmetro opcional `reason` para registrar o motivo."
    ),
)
async def cancel_item(
    order_id: UUID,
    item_id: UUID,
    session: DBSession,
    current_user: CurrentUser,
    reason: str | None = Query(
        default=None,
        description="Motivo do cancelamento (opcional). Ex: 'Cliente desistiu', 'Pedido errado'.",
        max_length=300,
    ),
) -> OrderResponse:
    """
    Cancela um item da comanda.

    CONCEITO — DELETE com retorno de dados:
        Convenção REST clássica: DELETE retorna 204 sem body.
        Aqui fazemos uma exceção: retornamos a comanda atualizada (200 + body).

        Por quê? O frontend precisa atualizar o estado da comanda imediatamente
        após o cancelamento. Se retornássemos 204, o frontend teria que fazer
        um GET separado para buscar a comanda atualizada — dois requests onde
        um é suficiente. Para operações de UI interativa, isso importa.

        Esse padrão (DELETE que retorna o recurso pai atualizado) é comum
        em APIs de e-commerce e sistemas de pedidos.

    CONCEITO — Query param vs body no DELETE:
        Passar dados no body de um DELETE é tecnicamente válido (RFC 7231),
        mas considerado má prática — alguns proxies e clientes descartam
        o body de requisições DELETE.

        Para dados simples como `reason` (uma string opcional), query param
        é a escolha mais portável e compatível com todos os clientes HTTP.

        Exemplo de uso:
            DELETE /orders/{id}/items/{item_id}?reason=Pedido+errado
            DELETE /orders/{id}/items/{item_id}          (sem motivo)

    REGRAS (verificadas no service):
        - Comanda deve ser OPEN ou BILL_REQUESTED
        - Item não pode estar CANCELLED (já cancelado)
        - Item não pode estar SERVED (já entregue — requer estorno manual)

    Retorna a comanda completa com o item marcado como CANCELLED
    e os totais recalculados.
    """
    return await _service(session, current_user).cancel_item(
        order_id, item_id, reason=reason
    )


# ── PATCH /orders/{order_id}/close — Fechar comanda ───────────────────────────


@router.patch(
    "/{order_id}/close",
    response_model=OrderResponse,
    summary="Fechar comanda",
    description=(
        "Fecha a comanda e libera a mesa. "
        "Requer `version` para locking otimista. "
        "A mesa é automaticamente marcada como FREE."
    ),
)
async def close_order(
    order_id: UUID,
    data: OrderClose,
    session: DBSession,
    current_user: CurrentUser,
) -> OrderResponse:
    """
    Fecha a comanda e libera a mesa.

    REGRAS:
        - Comanda deve estar OPEN ou BILL_REQUESTED
        - `version` deve ser a versão atual da comanda (locking otimista)
        - A mesa vinculada é automaticamente marcada como FREE

    Retorna a comanda fechada com status=CLOSED e closed_at preenchido.

    Se a comanda foi modificada por outro usuário desde o último GET:
        → HTTP 409 Conflict (OptimisticLockError)
        → Recarregue a comanda e tente novamente com a nova versão.
    """
    return await _service(session, current_user).close_order(order_id, data)
