"""
app/schemas/order.py

Schemas Pydantic para o módulo de comandas (orders).

═══════════════════════════════════════════════════════════════
CONCEITO — Order vs OrderItem: qual a diferença?
═══════════════════════════════════════════════════════════════

Pensa em uma comanda de restaurante de verdade:
    - A COMANDA em si (Order):
        Mesa 5 | Aberta às 19h30 | Garçom: João | Total: R$ 87,00

    - Os ITENS da comanda (OrderItems):
        1x Cerveja Heineken ........... R$ 12,00
        2x Frango com Fritas .......... R$ 54,00
        1x Suco de laranja ............ R$ 9,00

Tecnicamente:
    Order     → cabeçalho da comanda (uma linha no banco)
    OrderItem → cada produto pedido (múltiplas linhas por comanda)

Isso é um relacionamento 1:N (um para muitos):
    Uma Order TEM MUITOS OrderItems
    Cada OrderItem PERTENCE A UMA Order

Em banco de dados:
    orders table:
    id | table_id | total | status
    -- | -------- | ----- | ------
    A1 |   mesa5  | 87.00 | open

    order_items table:
    id | order_id | item_name          | unit_price | quantity | subtotal
    -- | -------- | ------------------ | ---------- | -------- | --------
    B1 |    A1    | Cerveja Heineken   |   12.00    |     1    |  12.00
    B2 |    A1    | Frango com Fritas  |   27.00    |     2    |  54.00
    B3 |    A1    | Suco de laranja    |    9.00    |     1    |   9.00

═══════════════════════════════════════════════════════════════
CONCEITO — Por que o total NÃO deve vir do frontend?
═══════════════════════════════════════════════════════════════

Regra de ouro em sistemas financeiros: NUNCA confie em cálculos do cliente.

Cenário de fraude simples:
    Cliente pede: POST /orders/A1/items
    Body: {"item_name": "Filé Mignon", "unit_price": 0.01, "quantity": 1}
    → O frontend poderia alterar o preço para R$ 0,01!

A solução: quando o item é do cardápio (menu_item_id fornecido):
    1. O servidor busca o MenuItem no banco
    2. Usa o PREÇO DO BANCO como unit_price
    3. Ignora qualquer preço enviado pelo cliente

Quando o item é manual (sem menu_item_id):
    Apenas usuários autorizados deveriam poder criar itens manuais.
    O servidor ainda registra quem fez o pedido e quando.

═══════════════════════════════════════════════════════════════
CONCEITO — Snapshot de preço (por que OrderItem guarda item_name e unit_price)
═══════════════════════════════════════════════════════════════

Imagine que hoje um hambúrguer custa R$ 25,00.
A comanda da mesa 3 tem 1 hambúrguer.

Amanhã o dono muda o preço para R$ 30,00.

O que deve aparecer na comanda da mesa 3?
    R$ 25,00 — o preço NA HORA DO PEDIDO

Por isso, o OrderItem armazena uma CÓPIA (snapshot) do nome e preço:
    item_name = "Hambúrguer Artesanal"  ← copiado do cardápio
    unit_price = 25.00                  ← copiado do cardápio na hora do pedido

Mesmo que o MenuItem seja editado ou deletado depois, o histórico está preservado.
Essa é uma decisão arquitetural crítica em sistemas financeiros.
"""

from datetime import datetime
from decimal import Decimal
from uuid import UUID

from pydantic import Field, model_validator

from app.models.order import OrderItemStatus, OrderStatus
from app.schemas.common import BaseSchema, TimestampSchema, UUIDSchema


# ── Schemas de OrderItem ──────────────────────────────────────────────────────


class OrderItemAdd(BaseSchema):
    """
    Dados para adicionar um item à comanda.

    Usado em: POST /api/v1/orders/{order_id}/items

    DOIS MODOS DE FUNCIONAMENTO:

    1. Item do cardápio (com menu_item_id):
        {"menu_item_id": "uuid...", "quantity": 2}
        → O servidor busca o nome e preço do cardápio
        → unit_price e item_name enviados pelo cliente são IGNORADOS

    2. Item manual (sem menu_item_id):
        {"item_name": "Chopp da casa", "unit_price": 8.50, "quantity": 3}
        → O servidor usa os dados do cliente
        → útil para itens fora do cardápio padrão

    O model_validator abaixo garante que:
        - Se não tem menu_item_id → item_name e unit_price são obrigatórios
        - Se tem menu_item_id → item_name e unit_price são opcionais (ignorados)
    """

    menu_item_id: UUID | None = Field(
        default=None,
        description="UUID do item do cardápio. Se fornecido, nome e preço vêm do banco.",
    )
    item_name: str | None = Field(
        default=None,
        max_length=200,
        description="Nome do item (obrigatório se menu_item_id não for fornecido).",
    )
    unit_price: Decimal | None = Field(
        default=None,
        ge=Decimal("0"),
        description="Preço unitário (obrigatório se menu_item_id não for fornecido; ignorado se fornecido).",
    )
    quantity: int = Field(
        default=1,
        ge=1,
        le=99,
        description="Quantidade do item (1 a 99).",
    )
    notes: str | None = Field(
        default=None,
        max_length=300,
        description="Observações do item (ex: 'sem cebola', 'ao ponto').",
    )

    @model_validator(mode="after")
    def validate_item_source(self) -> "OrderItemAdd":
        """
        Garante que os dados necessários foram fornecidos conforme o modo.

        model_validator(mode="after") roda APÓS o Pydantic validar cada campo.
        Aqui validamos a RELAÇÃO ENTRE campos, não cada campo individualmente.

        Isso é chamado de validação cruzada — quando a validade de um campo
        depende do valor de outro campo.
        """
        if self.menu_item_id is None:
            if not self.item_name or not self.item_name.strip():
                raise ValueError(
                    "item_name é obrigatório quando menu_item_id não é informado."
                )
            if self.unit_price is None:
                raise ValueError(
                    "unit_price é obrigatório quando menu_item_id não é informado."
                )
        return self


class OrderItemResponse(UUIDSchema, TimestampSchema):
    """
    Representação completa de um item da comanda.

    Notar que item_name e unit_price são SNAPSHOTS — valores copiados
    do cardápio no momento do pedido. Podem diferir dos valores atuais
    do cardápio se ele foi editado depois.
    """

    order_id: UUID
    menu_item_id: UUID | None       # referência ao cardápio (pode ser None se manual)
    item_name: str                   # snapshot: nome no momento do pedido
    unit_price: Decimal              # snapshot: preço no momento do pedido
    quantity: int
    subtotal: Decimal                # unit_price × quantity (calculado pelo servidor)
    notes: str | None
    status: OrderItemStatus

    # Campos de cancelamento — None para itens ativos, preenchidos ao cancelar
    cancelled_at: datetime | None       # quando foi cancelado
    cancelled_reason: str | None        # motivo informado pelo garçom/gestor


# ── Schemas de Order ──────────────────────────────────────────────────────────


class OrderCreate(BaseSchema):
    """
    Dados para abrir uma nova comanda.

    Usado em: POST /api/v1/orders

    Campos que o SERVIDOR define automaticamente:
        - establishment_id → do JWT do usuário logado
        - waiter_id → do JWT do usuário logado (quem abriu a comanda)
        - status → sempre começa como OPEN
        - subtotal, service_fee, discount, total → começam em 0.00
        - version → começa em 1
    """

    table_id: UUID | None = Field(
        default=None,
        description="Mesa que será atendida. Opcional — comanda de balcão/avulsa não tem mesa.",
    )
    guest_count: int = Field(
        default=1,
        ge=1,
        le=200,
        description="Quantidade de pessoas na mesa.",
    )
    customer_name: str | None = Field(
        default=None,
        max_length=200,
        description="Nome do cliente (opcional — útil para delivery ou reservas).",
    )
    notes: str | None = Field(
        default=None,
        max_length=500,
        description="Observações gerais da comanda (ex: 'aniversariante na mesa').",
    )


class OrderClose(BaseSchema):
    """
    Dados para fechar uma comanda.

    Usado em: PATCH /api/v1/orders/{order_id}/close

    CONCEITO — Por que version é obrigatório aqui?
        Fechar uma comanda é uma operação CRÍTICA e IRREVERSÍVEL.
        Se dois garçons tentarem fechar a mesma comanda ao mesmo tempo:
            1. Garçom A carrega a comanda (version=3)
            2. Garçom B carrega a comanda (version=3)
            3. Garçom A fecha → version vira 4
            4. Garçom B tenta fechar com version=3 → CONFLITO (version=4 no banco)
            5. Garçom B recebe HTTP 409 → deve recarregar a comanda

        Sem o locking, a comanda seria "fechada duas vezes" — inconsistência grave.
    """

    version: int = Field(
        ...,
        gt=0,
        description="Versão atual da comanda (locking otimista). Obtenha do GET e envie de volta.",
    )
    notes: str | None = Field(
        default=None,
        max_length=500,
        description="Observações finais (opcional).",
    )


class OrderResponse(UUIDSchema, TimestampSchema):
    """
    Representação completa de uma comanda com seus itens.

    Retornado em: POST, GET, PATCH /api/v1/orders/...

    CONCEITO — Relacionamento aninhado no JSON:
        O response inclui `items: list[OrderItemResponse]`.
        O Pydantic v2 sabe como serializar isso automaticamente.

        Quando chamamos OrderResponse.model_validate(order):
            1. Lê todos os campos diretos do objeto Order (id, status, total...)
            2. Lê `order.items` — que é uma lista de objetos OrderItem
            3. Para cada OrderItem, cria um OrderItemResponse

        IMPORTANTE: `order.items` DEVE estar carregado (eager loading)
        antes de chamar model_validate. Se estiver em modo lazy (padrão),
        o acesso fora de uma sessão async vai falhar.

        Por isso, no repository, usamos selectinload(Order.items)
        sempre que vamos retornar um OrderResponse.
    """

    establishment_id: UUID
    table_id: UUID | None
    waiter_id: UUID | None
    status: OrderStatus
    guest_count: int
    customer_name: str | None
    notes: str | None
    subtotal: Decimal
    service_fee: Decimal
    discount: Decimal
    total: Decimal
    closed_at: datetime | None
    version: int                     # necessário para o próximo PATCH
    items: list[OrderItemResponse]   # itens já carregados (eager loaded)
