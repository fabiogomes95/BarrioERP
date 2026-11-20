"""
app/services/order_service.py

Regras de negócio para o módulo de comandas.

═══════════════════════════════════════════════════════════════
CONCEITO — O que é uma Transaction (Transação)?
═══════════════════════════════════════════════════════════════

Uma transação é um conjunto de operações que deve ser executado
de forma ATÔMICA — ou tudo acontece, ou nada acontece.

Analogia: transferência bancária.
    OPERAÇÃO 1: Débita R$100 da conta A
    OPERAÇÃO 2: Credita R$100 na conta B

    Se der erro entre as duas operações, o banco não pode ficar
    com R$100 a menos na conta A e nada na conta B.
    → A transação garante: ou as duas operações acontecem, ou nenhuma.

No BarrioERP, ao ABRIR uma comanda:
    OPERAÇÃO 1: INSERT na tabela orders (cria a comanda)
    OPERAÇÃO 2: UPDATE na tabela tables (mesa vira OCCUPIED)

    Se a operação 2 falhar (ex: table_id inválido), a operação 1
    deve ser revertida. Não podemos ter uma comanda sem mesa OCCUPIED.
    → session.flush() propaga ambas; session.commit() confirma ambas.
    → Se der erro, o get_db() faz session.rollback() e NADA é salvo.

COMO O SQLAlchemy GERENCIA TRANSAÇÕES:
    A sessão (AsyncSession) abre uma transação automaticamente.
    Você acumula mudanças com session.add() e session.flush().
    O commit() confirma tudo ou o rollback() cancela tudo.
    O get_db() faz isso automaticamente no finally do yield.

═══════════════════════════════════════════════════════════════
CONCEITO — Por que concorrência importa em restaurante?
═══════════════════════════════════════════════════════════════

Um restaurante movimentado pode ter:
    - 4 garçons usando o app ao mesmo tempo
    - 20 mesas abertas simultaneamente
    - Múltiplas requisições chegando por segundo

Cenários problemáticos SEM proteção:

1. ABERTURA DUPLICADA DE COMANDA:
    Garçom A e Garçom B ambos clicam "abrir mesa 5" ao mesmo tempo.
    Sem verificação → duas comandas abertas para a mesma mesa.
    → Confusão: qual comanda é a correta? Qual tem os pedidos?

2. FECHAMENTO DUPLO:
    Garçom A e o caixa tentam fechar a comanda 123 ao mesmo tempo.
    Sem locking → a comanda pode ser fechada "duas vezes".
    → Pagamento duplicado, relatório inconsistente.

3. ITEM ADICIONADO A COMANDA FECHADA:
    Garçom A fecha a comanda enquanto Garçom B adiciona um item.
    Sem verificação de status → item adicionado a comanda já fechada.
    → Total errado, item nunca cobrado.

COMO PROTEGEMOS:
    - Abertura: verificamos ANTES se a mesa tem comanda aberta (check + lock)
    - Fechamento: usamos VersionMixin (optimistic locking)
    - Adição de item: verificamos se status == OPEN antes de adicionar

═══════════════════════════════════════════════════════════════
CONCEITO — Como relacionamentos funcionam no ORM
═══════════════════════════════════════════════════════════════

Quando fazemos `order.items.append(new_item)`:

    1. O SQLAlchemy VÊ que order.items é uma coleção rastreada
    2. Ao fazer append, ele marca new_item como "para ser inserido"
    3. O new_item.order_id é automaticamente definido como order.id
    4. session.flush() executa o INSERT
    5. new_item.id é preenchido com o UUID gerado pelo banco

Isso é a magia das "tracked collections" do SQLAlchemy.
Você não precisa definir order_id manualmente — o ORM faz isso.

ALTERNATIVA (mais explícita, mesma result):
    new_item = OrderItem(order_id=order.id, ...)
    session.add(new_item)

Ambas as formas funcionam. A primeira (append) é mais "pythônica"
porque expressa a intenção: "adicionar um item a esta comanda".
"""


# O código foi dividido por assunto em app/services/orders/ (só movido, sem
# mudar a lógica). Esta classe junta as partes e continua sendo o ponto de
# entrada: `from app.services.order_service import OrderService` não muda.
from app.services.orders.base import OrderServiceBase
from app.services.orders.items import OrderItemsMixin
from app.services.orders.kitchen import OrderKitchenMixin
from app.services.orders.lifecycle import OrderLifecycleMixin
from app.services.orders.reports import OrderReportsMixin


class OrderService(
    OrderLifecycleMixin,
    OrderItemsMixin,
    OrderKitchenMixin,
    OrderReportsMixin,
    OrderServiceBase,
):
    """
    Service de comandas — abre, lista, detalha, adiciona itens e fecha.

    Usa dois repositories:
        _order_repo → operações em orders e order_items
        _table_repo → atualiza o status da mesa ao abrir/fechar comanda

    Os dois repositories compartilham a mesma `session` — logo, estão
    na mesma transação. Se qualquer operação falhar, ambas são revertidas.
    """
