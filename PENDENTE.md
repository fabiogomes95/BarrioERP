# BarrioERP — Pendente (retomar aqui)

> Sessão de 2026-07-23 parou no meio do planejamento do módulo de estoque.
> Nada foi codado ainda — só exploração. Este arquivo existe pra não perder
> o desenho já pensado. Apagar depois que o trabalho terminar (não é doc
> permanente como o `CHANGELOG.md`/`ARCHITECTURE.md`).

## Contexto

Dono confirmou que vai comercializar o BarrioERP pra outros bares, não é só
uso próprio — por isso a prioridade em fechar gaps de produto que hoje não
afetam o Recanto mas afetariam outro cliente. Combinado fazer um por um:

1. ~~Relatórios por período~~ — **feito** (v0.11.0)
2. **Controle de estoque/insumos** — parado aqui, retomar amanhã
3. Reservas de mesa com data/hora — não iniciado
4. Tela simplificada pra cozinha (KDS) — não iniciado

**Fora do escopo (decisão do dono):**
- Multi-estabelecimento pela UI — não vai querer
- Emissão fiscal (NFC-e) — descartada, dono não é MEI/CNPJ

---

## 2. Controle de estoque/insumos — desenho planejado

### Decisão de escopo

Fazer o modelo **"recipe"/BOM completo** (um item do cardápio pode consumir
vários insumos, cada um com quantidade própria) em vez do modelo simples
"1 item = 1 insumo direto". Mais próximo da realidade de outros bares
(pra comercializar), não muito mais complexo no nível de dado — só mais
trabalho na tela de editar receita.

### Quando o estoque é deduzido

Investigado: `OrderItemStatus` já tem um fluxo completo no enum
(`pending → sent → preparing → ready → served`), **mas nada no código hoje
transiciona esses status** — a única transição real que existe é
`CANCELLED` (via `cancel_item`). Ou seja, "servido" não é um evento
confiável pra gatilho de estoque hoje (viraria sinal real só quando o KDS,
item 4 da lista, for implementado).

**Decisão:** deduzir estoque no momento em que o item é **adicionado à
comanda** (`OrderService.add_item()`), já que é o único evento real e
confiável no fluxo atual. Reverter (somar de volta) quando o item é
**cancelado** (`cancel_item()`). Ajustar a diferença quando a quantidade
muda (`set_item_quantity()` — dá pra subir ou descer).

Deduzir **sem bloquear a venda** se o estoque ficar negativo (não travar o
garçom por causa de uma divergência de estoque — só alertar visualmente na
tela de Estoque, não impedir operação). Comportamento consistente com POS
pequeno/simples.

### Modelos novos (`app/models/stock.py`)

```python
class StockUnit(str, enum.Enum):
    UNIT = "unit"   # unidade (garrafa, lata, pacote)
    KG = "kg"
    G = "g"
    L = "l"
    ML = "ml"

class StockItem(Base, UUIDMixin, TimestampMixin, SoftDeleteMixin):
    __tablename__ = "stock_items"
    establishment_id: FK establishments, CASCADE
    name: str
    unit: StockUnit
    quantity_on_hand: Numeric(12,3)  # 3 casas — permite fração de kg/L
    min_quantity: Numeric(12,3) default 0  # limiar de alerta "estoque baixo"
    is_active: bool default True
    notes: str | None

class StockMovementKind(str, enum.Enum):
    PURCHASE = "purchase"        # entrada manual (compra)
    ADJUSTMENT = "adjustment"    # ajuste manual (+ ou -)
    SALE = "sale"                # dedução automática por venda
    LOSS = "loss"                # perda/quebra

class StockMovement(Base, UUIDMixin, TimestampMixin):
    __tablename__ = "stock_movements"
    establishment_id: FK
    stock_item_id: FK stock_items, CASCADE
    kind: StockMovementKind
    quantity_change: Numeric(12,3)  # assinado: + entrada, - saída
    reason: str | None
    order_item_id: FK order_items, SET NULL, nullable  # se for dedução automática
    user_id: FK users, SET NULL, nullable  # null se for automático (venda)

class MenuItemIngredient(Base, UUIDMixin, TimestampMixin):
    __tablename__ = "menu_item_ingredients"
    menu_item_id: FK menu_items, CASCADE
    stock_item_id: FK stock_items, CASCADE
    quantity_per_unit: Numeric(12,3)  # quanto consome por unidade vendida
    unique constraint (menu_item_id, stock_item_id)
```

Registrar em `app/models/__init__.py`. Gerar migração:
`alembic revision --autogenerate -m "stock_control"` e revisar antes de
aplicar (autogenerate erra nome de constraint às vezes).

### Camadas (mesmo padrão do resto do projeto)

- `app/schemas/stock.py` — StockItemCreate/Update/Response,
  StockMovementCreate/Response, MenuItemIngredientCreate/Response
- `app/repositories/stock_repository.py` — CRUD + `list_low_stock()`
  (`quantity_on_hand <= min_quantity`)
- `app/services/stock_service.py`:
  - CRUD de `StockItem`
  - `record_movement()` — entrada/ajuste/perda manual, atualiza
    `quantity_on_hand` + grava `StockMovement`
  - `list_low_stock()`
  - `set_ingredients(menu_item_id, [...])` — substitui a lista de
    ingredientes de um item do cardápio
  - `deduct_for_sale(menu_item_id, quantity, order_item_id)` — chamado por
    `OrderService.add_item()`
  - `restore_for_item(order_item_id)` — chamado por `cancel_item()`
  - `adjust_for_quantity_change(order_item_id, old_qty, new_qty)` — chamado
    por `set_item_quantity()`
- `app/api/v1/endpoints/stock.py`:
  - `POST/GET/PATCH/DELETE /stock/items`
  - `POST /stock/items/{id}/movements`, `GET /stock/items/{id}/movements`
  - `GET /stock/low`
  - `GET/PUT /stock/menu-items/{menu_item_id}/ingredients`
  - RBAC: só `owner`/`manager` (mesmo padrão do Cardápio)

### Wiring em `order_service.py`

- `add_item()`: se `menu_item_id` não for `None`, chamar
  `StockService.deduct_for_sale(...)` dentro da mesma transação (mesmo
  `session`, sem commit isolado)
- `cancel_item()`: chamar `restore_for_item()` antes/depois de marcar
  `CANCELLED`
- `set_item_quantity()`: calcular delta e chamar
  `adjust_for_quantity_change()`
- Itens **manuais** (sem `menu_item_id`) não têm receita — não afetam
  estoque, isso é esperado (não tem o que deduzir)

### Frontend

- Página nova `EstoquePage.tsx` (rota `/estoque`, nav item, RBAC
  owner/manager): lista de insumos (nome, unidade, quantidade, mínimo,
  destaque visual se abaixo do mínimo), modais de criar/editar insumo,
  modal de movimentação manual (entrada/perda/ajuste + motivo), histórico
  de movimentações por insumo
- `CardapioPage.tsx`: no modal de editar item, nova seção "Ingredientes" —
  linhas de (insumo + quantidade consumida), adicionar/remover linha
- `api.ts`: funções pra tudo acima
- `App.tsx` + `Layout.tsx`: rota e item de navegação

### Depois disso (itens 3 e 4 da lista, ainda não desenhados)

- **Reservas de mesa com data/hora** — não discutido ainda em detalhe
- **KDS (tela simplificada pra cozinha)** — não discutido ainda em detalhe;
  nota: implementar isso provavelmente é o momento certo de também ativar
  de verdade o fluxo `sent → preparing → ready → served` do
  `OrderItemStatus`, que hoje existe só no enum sem uso real
