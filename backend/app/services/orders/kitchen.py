"""
app/services/orders/kitchen.py

Cozinha (KDS): fila e avanço de status dos itens.

Código movido sem mudança de order_service.py (lá está a explicação geral
e a classe OrderService, que junta todas as partes).
"""

from uuid import UUID


from app.core.exceptions import BusinessRuleError, NotFoundError
from app.models.order import OrderItemStatus, OrderStatus
from app.schemas.order import KitchenQueueItem, KitchenQueueTicket, OrderResponse
from app.services.orders.base import OrderServiceBase


class OrderKitchenMixin(OrderServiceBase):
    """Cozinha (KDS): fila e avanço de status dos itens."""

    async def list_kitchen_queue(self) -> list[KitchenQueueTicket]:
        """Fila do KDS: um 'ticket' por comanda aberta com itens em preparo."""
        establishment_id = self._require_establishment()
        orders = await self._order_repo.list_kitchen_orders(establishment_id)

        tickets = []
        for order in orders:
            kitchen_items = [i for i in order.items if i.status in self._KITCHEN_STATUSES]
            if not kitchen_items:
                continue  # defensivo — o EXISTS do repo já garante isso, mas não custa
            kitchen_items.sort(key=lambda i: i.created_at)
            tickets.append(
                KitchenQueueTicket(
                    order_id=order.id,
                    order_type=order.order_type,
                    table_number=order.table.number if order.table else None,
                    table_label=order.table.label if order.table else None,
                    customer_name=order.customer_name,
                    guest_count=order.guest_count,
                    opened_at=order.created_at,
                    items=[
                        KitchenQueueItem(
                            id=i.id, item_name=i.item_name, quantity=i.quantity,
                            status=i.status, notes=i.notes, created_at=i.created_at,
                        )
                        for i in kitchen_items
                    ],
                )
            )
        # FIFO pelo item mais antigo ainda em preparo — não pelo horário que a
        # comanda abriu (uma mesa aberta há 2h com um item novo não deve
        # "furar a fila" na frente de quem chegou depois, mas também não deve
        # ficar escondida no fim só por causa da hora de abertura).
        tickets.sort(key=lambda t: t.items[0].created_at)
        return tickets

    async def advance_kitchen_status(
        self, order_id: UUID, item_id: UUID, status: OrderItemStatus
    ) -> OrderResponse:
        """
        Move um item entre os status da cozinha (sent/preparing/ready).

        Só aceita os três status "em preparo" — SERVED é feito por
        `mark_item_served()` (ação do garçom, não da cozinha) e CANCELLED
        por `cancel_item()`. Transição livre entre os três (não força
        sequência estrita: a cozinha pode voltar de READY pra PREPARING
        se marcou errado, por exemplo).
        """
        if status not in self._KITCHEN_STATUSES:
            raise BusinessRuleError(
                "Status inválido para a cozinha. Use sent, preparing ou ready."
            )

        establishment_id = self._require_establishment()
        order = await self._get_or_raise(order_id, establishment_id)

        if order.status not in (OrderStatus.OPEN, OrderStatus.BILL_REQUESTED):
            raise BusinessRuleError(
                f"Não é possível alterar itens de uma comanda com status '{order.status.value}'."
            )

        item = await self._order_repo.get_item(item_id, order_id)
        if item is None:
            raise NotFoundError("OrderItem", item_id)

        if item.status not in self._KITCHEN_STATUSES:
            raise BusinessRuleError(
                f"O item '{item.item_name}' não está na fila da cozinha "
                f"(status atual: '{item.status.value}')."
            )

        before_status = item.status.value
        item.status = status
        await self.session.flush()

        await self._log_audit(
            action="order_item.kitchen_status",
            resource_type="order_item",
            resource_id=str(item.id),
            before={"status": before_status},
            after={"status": status.value},
        )
        return await self._get_or_raise(order.id, establishment_id)
