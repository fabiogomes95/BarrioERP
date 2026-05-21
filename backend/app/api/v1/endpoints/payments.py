"""
app/api/v1/endpoints/payments.py

Endpoints HTTP para o módulo de pagamentos.

═══════════════════════════════════════════════════════════════
CONCEITO — Rotas "mistas" num único router
═══════════════════════════════════════════════════════════════

Os três endpoints deste módulo têm prefixos DIFERENTES:

    POST  /payments                    ← cria pagamento
    GET   /orders/{order_id}/payments  ← lista pagamentos de uma comanda
    PATCH /orders/{order_id}/finish    ← finaliza comanda

Por que não usar um único prefixo?

    A URL /payments/... faz sentido para criar pagamentos.
    Mas /payments/{order_id}/list seria confuso — o id seria de uma
    comanda, não de um pagamento.

    Semânticamente mais claro:
        GET /orders/{id}/payments → "pagamentos desta comanda específica"
        PATCH /orders/{id}/finish → "finalizar esta comanda"

    Em FastAPI, um router NÃO precisa ter um prefixo único.
    Podemos ter rotas com caminhos completamente diferentes no mesmo arquivo.
    O que os une é o DOMÍNIO (módulo de pagamentos), não o prefixo de URL.

COMO REGISTRAMOS NO ROUTER PRINCIPAL:
    api_router.include_router(payments.router, tags=["payments"])
    ↑ sem prefix → as paths declaradas aqui são usadas como estão

    Isso dá URLs finais:
        POST  /api/v1/payments
        GET   /api/v1/orders/{order_id}/payments
        PATCH /api/v1/orders/{order_id}/finish

CONTRASTE COM OUTROS MÓDULOS:
    orders router  → prefix="/orders"  → todas as rotas sob /orders/...
    tables router  → prefix="/tables"  → todas as rotas sob /tables/...
    payments router → sem prefix       → rotas em /payments/ E /orders/...

═══════════════════════════════════════════════════════════════
CONCEITO — Responsabilidade do endpoint no contexto financeiro
═══════════════════════════════════════════════════════════════

No módulo de pagamentos, o endpoint tem responsabilidade AINDA MENOR
do que em outros módulos. Aqui não há lógica de negócio alguma:

    endpoint → recebe dados → chama service → retorna resultado

Por quê? Porque a lógica financeira é sensível e complexa.
Toda a proteção (verificação de saldo, locking, atomicidade) está no Service.
O endpoint é apenas a "tomada elétrica" — conecta o cliente ao service.

Se futuramente adicionarmos permissões por role (ex: só CASHIER pode registrar pagamentos),
essa verificação vai no endpoint antes de chamar o service.
"""

from uuid import UUID

from fastapi import APIRouter

from app.api.deps import CurrentUser, DBSession
from app.schemas.order import OrderResponse
from app.schemas.payment import OrderFinish, PaymentCreate, PaymentResponse
from app.services.payment_service import PaymentService

router = APIRouter()


# ── Helper ─────────────────────────────────────────────────────────────────────


def _service(session: DBSession, user: CurrentUser) -> PaymentService:
    """
    Cria o PaymentService com contexto do usuário logado.

    O PaymentService usa internamente três repositories:
        PaymentRepository → operações financeiras
        OrderRepository   → fetch e fechamento de comandas
        TableRepository   → liberar mesa ao finalizar
    """
    return PaymentService(
        session=session,
        company_id=user.company_id,
        establishment_id=user.establishment_id,
        user_id=user.id,
    )


# ── POST /payments — Registrar pagamento ──────────────────────────────────────


@router.post(
    "/payments",
    response_model=PaymentResponse,
    status_code=201,
    summary="Registrar pagamento",
    description=(
        "Registra um pagamento para uma comanda. "
        "O valor não pode exceder o saldo devedor. "
        "Para dinheiro, `amount_tendered` calcula o troco automaticamente."
    ),
)
async def register_payment(
    data: PaymentCreate,
    session: DBSession,
    current_user: CurrentUser,
) -> PaymentResponse:
    """
    Registra um pagamento em uma comanda.

    VALIDAÇÕES DO SERVIDOR (não confiar no cliente):
        - amount > 0
        - comanda está em status pagável (OPEN ou BILL_REQUESTED)
        - amount <= saldo_devedor (total_comanda - total_já_pago)

    Para DINHEIRO (method=cash):
        - amount_tendered >= amount (o que o cliente deu deve cobrir o pagamento)
        - change_given é calculado automaticamente: amount_tendered - amount

    STATUS 201 Created: um novo registro financeiro foi criado.
    """
    return await _service(session, current_user).register(data)


# ── GET /orders/{order_id}/payments — Listar pagamentos ───────────────────────


@router.get(
    "/orders/{order_id}/payments",
    response_model=list[PaymentResponse],
    summary="Listar pagamentos da comanda",
    description="Retorna todos os pagamentos registrados para uma comanda específica.",
)
async def list_payments(
    order_id: UUID,
    session: DBSession,
    current_user: CurrentUser,
) -> list[PaymentResponse]:
    """
    Lista todos os pagamentos de uma comanda.

    Retorna pagamentos em ordem cronológica (mais antigos primeiro).
    Retorna [] se a comanda não tiver pagamentos.
    Retorna 404 se a comanda não existir ou pertencer a outro estabelecimento.

    MULTI-TENANCY:
        Verifica que a comanda pertence ao estabelecimento do usuário logado
        antes de listar os pagamentos.
    """
    return await _service(session, current_user).list_for_order(order_id)


# ── PATCH /orders/{order_id}/finish — Finalizar comanda ───────────────────────


@router.patch(
    "/orders/{order_id}/finish",
    response_model=OrderResponse,
    summary="Finalizar comanda",
    description=(
        "Fecha a comanda após verificar que o total pago cobre o total da conta. "
        "A mesa é automaticamente liberada. "
        "Requer `version` para locking otimista."
    ),
)
async def finish_order(
    order_id: UUID,
    data: OrderFinish,
    session: DBSession,
    current_user: CurrentUser,
) -> OrderResponse:
    """
    Finaliza uma comanda com verificação financeira.

    DIFERENÇA entre finish e close:
        PATCH /orders/{id}/close  → fecha sem checar pagamento (override do gerente)
        PATCH /orders/{id}/finish → fecha APENAS se total pago >= total da conta

    PRÉ-CONDIÇÕES:
        - Comanda deve estar OPEN ou BILL_REQUESTED
        - total_pago (soma de pagamentos CONFIRMED) >= order.total
        - `version` deve ser a versão atual da comanda

    EFEITOS:
        - order.status = CLOSED
        - order.closed_at = timestamp atual
        - table.status = FREE (mesa liberada)

    RETORNA:
        OrderResponse com o estado final da comanda (status=CLOSED, closed_at preenchido).

    Se pagamento insuficiente → HTTP 422 com mensagem indicando quanto falta.
    Se conflito de versão → HTTP 409 (alguém editou a comanda — recarregue e tente novamente).
    """
    return await _service(session, current_user).finish(order_id, data)
