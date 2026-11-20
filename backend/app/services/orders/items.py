"""
app/services/orders/items.py

Itens da comanda: adicionar, cancelar, mudar quantidade, marcar servido.

Código movido sem mudança de order_service.py (lá está a explicação geral
e a classe OrderService, que junta todas as partes).
"""

from datetime import UTC, datetime
from decimal import Decimal
from uuid import UUID

from sqlalchemy.orm.exc import StaleDataError

from app.core.exceptions import BusinessRuleError, NotFoundError, OptimisticLockError
from app.models.user import UserRole
from app.models.order import OrderItem, OrderItemStatus, OrderStatus
from app.schemas.order import OrderItemAdd, OrderResponse
from app.services.online_order_pricing import half_pizza_name, is_pizza_category
from app.services.orders.base import OrderServiceBase


class OrderItemsMixin(OrderServiceBase):
    """Itens da comanda: adicionar, cancelar, mudar quantidade, marcar servido."""

    async def add_item(self, order_id: UUID, data: OrderItemAdd) -> OrderResponse:
        """
        Adiciona um item à comanda e recalcula o total.

        FLUXO:
            1. Busca a comanda com items (eager loaded)
            2. Verifica que está OPEN
            3. Resolve nome/preço do item:
               - Se menu_item_id: busca no cardápio (snapshot)
               - Se manual: usa name/price do request
            4. Cria OrderItem e adiciona à coleção order.items
            5. Recalcula subtotal e total da comanda
            6. Flush → dois INSERTs/UPDATEs na mesma transação
            7. Busca novamente com items para retornar resposta consistente

        CONCEITO — Snapshot de preço em ação:
            Ao adicionar "Hambúrguer Artesanal" com menu_item_id:
                menu_item = busca no banco → name="Hambúrguer", price=25.00
                order_item.item_name = menu_item.name   ← snapshot
                order_item.unit_price = menu_item.price  ← snapshot
                order_item.menu_item_id = menu_item.id  ← referência (pode mudar)

            Se amanhã o hambúrguer mudar de nome ou preço:
                → A comanda já possui os valores do momento do pedido ✓

        CONCORRÊNCIA (por que NÃO pedimos version aqui):
            Adicionar item é uma operação APPEND — adiciona uma linha nova.
            Dois garçons podem adicionar itens ao mesmo tempo sem conflito.

            O problema de concorrência real é ATUALIZAR o subtotal da Order.
            O VersionMixin do SQLAlchemy detectará conflito se dois garçons
            tentarem atualizar o subtotal exatamente ao mesmo tempo:
                → StaleDataError → convertemos em OptimisticLockError (409)
                → O cliente tenta de novo (raramente acontece na prática)

        LANÇA:
            NotFoundError (404)      → comanda não encontrada
            BusinessRuleError (422)  → comanda não está aberta nem com conta solicitada
            NotFoundError (404)      → item do cardápio não encontrado/indisponível
            OptimisticLockError (409) → conflito de concorrência no total

        POR QUE BILL_REQUESTED TAMBÉM ACEITA ITEM NOVO:
            Cliente pede a conta e, antes dela chegar, resolve pedir mais uma
            rodada — cenário comum no dia a dia do bar. Bloquear isso obrigaria
            o garçom a cancelar o pedido de conta só pra lançar um item, sem
            motivo real (a conta ainda não foi fechada/paga, só sinalizada).
        """
        establishment_id = self._require_establishment()
        order = await self._get_or_raise(order_id, establishment_id)

        if order.status not in (OrderStatus.OPEN, OrderStatus.BILL_REQUESTED):
            raise BusinessRuleError(
                f"Não é possível adicionar itens a uma comanda com status '{order.status.value}'. "
                "Apenas comandas ABERTAS ou com CONTA SOLICITADA aceitam novos itens."
            )

        # Resolve nome e preço do item
        if data.menu_item_id is not None:
            # Modo cardápio: busca no banco e usa snapshot
            menu_item = await self._order_repo.get_available_menu_item(
                data.menu_item_id, establishment_id
            )
            if menu_item is None:
                raise NotFoundError("MenuItem", data.menu_item_id)

            item_name = menu_item.name
            unit_price = menu_item.price
            menu_item_id = menu_item.id
            sends_to_kitchen = menu_item.category.sends_to_kitchen
            # Baixa de estoque: (item do cardápio, quantas receitas)
            stock_parts: list[tuple[UUID, Decimal]] = [(menu_item.id, Decimal(data.quantity))]

            if data.half_with is not None and data.half_with != menu_item.id:
                # Pizza meio a meio: "Pizza Calabresa / Mussarela", preço da
                # metade mais cara, meia receita de cada sabor. Sem menu_item_id
                # único (são dois) — set_item_quantity escala a baixa já feita.
                other = await self._order_repo.get_available_menu_item(data.half_with, establishment_id)
                if other is None:
                    raise NotFoundError("MenuItem", data.half_with)
                if not (is_pizza_category(menu_item.category.name) and is_pizza_category(other.category.name)):
                    raise BusinessRuleError("Meio a meio é só para pizzas.")
                item_name = half_pizza_name(menu_item.name, other.name)
                unit_price = max(menu_item.price, other.price)
                menu_item_id = None
                sends_to_kitchen = sends_to_kitchen or other.category.sends_to_kitchen
                half = Decimal(data.quantity) / 2
                stock_parts = [(menu_item.id, half), (other.id, half)]
            elif data.complemento:
                # Ex: "Churrasco - frango" — continua ligado ao Churrasco
                # (cozinha, estoque e relatório por item funcionam normal)
                if data.complemento not in (menu_item.complementos or []):
                    raise BusinessRuleError(f"Opção '{data.complemento}' não existe para {menu_item.name}.")
                item_name = f"{menu_item.name} - {data.complemento}"

            # Categoria marcada "vai pra cozinha" → item nasce direto em SENT
            # (pula PENDING) e já aparece na fila do KDS. Itens sem essa marca
            # (ex: bebida) ficam em PENDING até o garçom marcar como servido.
            initial_status = OrderItemStatus.SENT if sends_to_kitchen else OrderItemStatus.PENDING
        else:
            # Modo manual: usa dados do request (validados no schema)
            item_name = data.item_name  # type: ignore[assignment] — garantido pelo model_validator
            unit_price = data.unit_price  # type: ignore[assignment] — garantido pelo model_validator
            menu_item_id = None
            stock_parts = []
            # Sem menu_item_id não há como saber se precisa de cozinha —
            # fica em PENDING, igual a um item sem preparo.
            initial_status = OrderItemStatus.PENDING

        # Calcula o subtotal do item
        subtotal = unit_price * data.quantity

        # Cria o item e adiciona à comanda
        # Usar order.items.append() em vez de session.add() direto:
        # → SQLAlchemy define order_id automaticamente
        # → O item entra na coleção rastreada imediatamente
        new_item = OrderItem(
            order_id=order.id,
            menu_item_id=menu_item_id,
            item_name=item_name,
            unit_price=unit_price,
            quantity=data.quantity,
            subtotal=subtotal,
            notes=data.notes,
            status=initial_status,
        )
        order.items.append(new_item)

        # Recalcula totais da comanda (inclui o novo item)
        self._recalculate_total(order)

        try:
            await self.session.flush()
        except StaleDataError:
            # Dois garçons atualizaram o total simultaneamente
            # O cliente deve tentar novamente (raramente acontece)
            raise OptimisticLockError("Order")

        # Deduz estoque dos insumos da receita (se o item vier do cardápio).
        # Itens manuais não têm receita — não afetam estoque.
        for stock_menu_item_id, recipes in stock_parts:
            await self._stock_service.deduct_for_sale(
                stock_menu_item_id, recipes, new_item.id, establishment_id
            )

        await self._log_audit(
            action="order_item.add",
            resource_type="order_item",
            resource_id=str(new_item.id),
            after={
                "item_name": item_name,
                "quantity": data.quantity,
                "unit_price": str(unit_price),
                "subtotal": str(subtotal),
                "notes": data.notes,
                "order": self._order_snapshot(order),
            },
        )

        # Re-busca do banco para garantir dados frescos e itens atualizados
        # (após flush, os IDs e timestamps gerados pelo banco estão disponíveis)
        return await self._get_or_raise(order.id, establishment_id)

    async def cancel_item(
        self,
        order_id: UUID,
        item_id: UUID,
        *,
        reason: str | None = None,
        actor_role: UserRole | None = None,
    ) -> OrderResponse:
        """
        Cancela um item de uma comanda aberta.

        REGRAS DE NEGÓCIO:
            1. A comanda deve existir e pertencer ao estabelecimento
            2. A comanda deve estar OPEN ou BILL_REQUESTED
               (não faz sentido cancelar item de comanda já fechada)
            3. O item deve existir e pertencer à comanda informada
            4. O item não pode já estar CANCELLED
            5. O item não pode estar SERVED (já foi entregue ao cliente)

        POR QUE NÃO PERMITIR CANCELAR ITENS SERVED?
            Um item SERVED foi fisicamente entregue ao cliente.
            Cancelar algo que já foi consumido é uma operação de crédito/
            estorno, não um cancelamento simples — teria implicações fiscais
            e de estoque. Para o MVP, bloqueamos. Se necessário, um OWNER
            pode fechar e reabrir a comanda com ajuste manual.

        TOTAIS APÓS CANCELAMENTO:
            _recalculate_total() soma apenas itens com status != CANCELLED.
            Ao marcar o item como CANCELLED antes de chamar esse método,
            ele automaticamente sai do cálculo. A lógica está centralizada
            — não precisamos subtrair manualmente.

        LOCKING OTIMISTA:
            Cancelar um item atualiza order.subtotal e order.total.
            Como Order tem VersionMixin, qualquer UPDATE no registro
            incrementa o version. Se dois cancelamentos simultâneos
            ocorrerem, o segundo receberá StaleDataError → OptimisticLockError.
            O frontend deve recarregar a comanda e tentar novamente.

        LANÇA:
            NotFoundError (404)       → comanda ou item não encontrado
            BusinessRuleError (422)   → comanda fechada, item servido, já cancelado
            OptimisticLockError (409) → conflito de versão concorrente
        """
        establishment_id = self._require_establishment()

        # Carrega a comanda com seus itens (selectinload via get_with_items)
        order = await self._get_or_raise(order_id, establishment_id)

        # Regra 1: comanda deve estar em estado cancelável
        if order.status not in (OrderStatus.OPEN, OrderStatus.BILL_REQUESTED):
            raise BusinessRuleError(
                f"Não é possível cancelar itens de uma comanda com status "
                f"'{order.status.value}'. Apenas comandas ABERTAS ou com "
                "CONTA SOLICITADA permitem cancelamento de itens."
            )

        # Regra 2: item deve pertencer a esta comanda
        item = await self._order_repo.get_item(item_id, order_id)
        if item is None:
            raise NotFoundError("OrderItem", item_id)

        # Regra 3: item não pode estar já cancelado
        if item.status == OrderItemStatus.CANCELLED:
            raise BusinessRuleError(
                f"O item '{item.item_name}' já está cancelado."
            )

        # Regra 4: item não pode ter sido servido
        if item.status == OrderItemStatus.SERVED:
            raise BusinessRuleError(
                f"O item '{item.item_name}' já foi servido e não pode ser cancelado. "
                "Para ajustes pós-serviço, utilize o processo de estorno manual."
            )

        # Regra 5: motivo obrigatório (fica na auditoria e no item) — exceto
        # pro dono, pra quem é opcional (decisão do dono).
        reason = (reason or "").strip()
        if actor_role != UserRole.OWNER and len(reason) < 3:
            raise BusinessRuleError("Informe o motivo do cancelamento.")

        # Regra 6: item que já foi pra cozinha só caixa/gerente/dono cancela
        self._require_can_reduce(item, actor_role)

        before_item = {"item_name": item.item_name, "status": item.status.value, "quantity": item.quantity,
                       "subtotal": str(item.subtotal)}
        # Foto da comanda ANTES de recalcular (antes era tirada depois, e o
        # "antes" da auditoria saía igual ao "depois")
        before_order = self._order_snapshot(order)

        # Devolve ao estoque os insumos deduzidos quando o item foi adicionado
        if item.menu_item_id is not None:
            await self._stock_service.restore_for_item(item.id, establishment_id)

        # Cancela o item — campos de auditoria registram quando e por quê
        item.status = OrderItemStatus.CANCELLED
        item.cancelled_at = datetime.now(UTC)
        item.cancelled_reason = reason or None  # dono pode cancelar sem motivo

        # Recalcula subtotal e total da comanda (exclui automaticamente itens CANCELLED)
        # _recalculate_total() itera sobre order.items já carregados em memória,
        # então o item recém-cancelado já reflete o novo status.
        self._recalculate_total(order)
        await self._ensure_total_covers_payments(order)

        await self._log_audit(
            action="order_item.cancel",
            resource_type="order_item",
            resource_id=str(item.id),
            before={"item": before_item, "order": before_order},
            after={
                "item": {"item_name": item.item_name, "status": "cancelled", "reason": reason},
                "order": self._order_snapshot(order),
            },
        )

        try:
            await self.session.flush()
        except StaleDataError:
            # Dois cancelamentos simultâneos tentaram atualizar o total da comanda.
            # O frontend deve recarregar a comanda e tentar o cancelamento novamente.
            raise OptimisticLockError("Order")

        return await self._get_or_raise(order.id, establishment_id)

    async def set_item_quantity(
        self,
        order_id: UUID,
        item_id: UUID,
        *,
        quantity: int,
        actor_role: UserRole | None = None,
    ) -> OrderResponse:
        """
        Altera a quantidade de um item da comanda e recalcula o total.

        Útil para o caso comum no bar: o cliente pede outra cerveja igual.
        Em vez de criar uma nova linha, incrementamos a quantidade do item.

        REGRAS:
            - Comanda deve estar OPEN ou BILL_REQUESTED
            - Item deve existir e pertencer à comanda
            - Item não pode estar CANCELLED nem SERVED
            - quantity >= 1 (para zerar, use o cancelamento)
        """
        establishment_id = self._require_establishment()
        order = await self._get_or_raise(order_id, establishment_id)

        if order.status not in (OrderStatus.OPEN, OrderStatus.BILL_REQUESTED):
            raise BusinessRuleError(
                f"Não é possível alterar itens de uma comanda com status "
                f"'{order.status.value}'."
            )

        item = await self._order_repo.get_item(item_id, order_id)
        if item is None:
            raise NotFoundError("OrderItem", item_id)

        if item.status == OrderItemStatus.CANCELLED:
            raise BusinessRuleError(f"O item '{item.item_name}' está cancelado.")
        if item.status == OrderItemStatus.SERVED:
            raise BusinessRuleError(
                f"O item '{item.item_name}' já foi servido e não pode ser alterado."
            )
        # Diminuir quantidade é cancelar uma parte: mesma regra do cancel_item
        if quantity < item.quantity:
            self._require_can_reduce(item, actor_role)

        old_quantity = item.quantity
        before_order = self._order_snapshot(order)  # antes de recalcular (ver cancel_item)

        # Ajusta a diferença de estoque pela mudança de quantidade
        if item.menu_item_id is not None:
            await self._stock_service.adjust_for_quantity_change(
                item.menu_item_id, item.id, old_quantity, quantity, establishment_id
            )
        else:
            # Meio a meio (meia receita de cada sabor): repete a baixa original
            # na proporção. Item manual comum não tem baixa — não faz nada.
            await self._stock_service.scale_for_quantity_change(
                item.id, old_quantity, quantity, establishment_id
            )

        item.quantity = quantity
        item.subtotal = item.unit_price * quantity
        self._recalculate_total(order)
        if quantity < old_quantity:
            await self._ensure_total_covers_payments(order)

        try:
            await self.session.flush()
        except StaleDataError:
            raise OptimisticLockError("Order")

        await self._log_audit(
            action="order_item.quantity_change",
            resource_type="order_item",
            resource_id=str(item.id),
            before={"item_name": item.item_name, "quantity": old_quantity, "status": item.status.value,
                    "unit_price": str(item.unit_price), "order": before_order},
            after={"item_name": item.item_name, "quantity": quantity, "order": self._order_snapshot(order)},
        )

        return await self._get_or_raise(order.id, establishment_id)

    # ══════════════════════════════════════════════════════════════
    # KDS — fila de cozinha
    # ══════════════════════════════════════════════════════════════

    _KITCHEN_STATUSES = (OrderItemStatus.SENT, OrderItemStatus.PREPARING, OrderItemStatus.READY)

    async def mark_item_served(self, order_id: UUID, item_id: UUID) -> OrderResponse:
        """
        Marca um item como servido — ação do garçom (não da cozinha).

        Aceita a partir de READY (a cozinha terminou de preparar) ou
        PENDING (item que nunca precisou de cozinha, ex: bebida — ver
        `add_item()`/`MenuCategory.sends_to_kitchen`).
        """
        establishment_id = self._require_establishment()
        order = await self._get_or_raise(order_id, establishment_id)

        if order.status not in (OrderStatus.OPEN, OrderStatus.BILL_REQUESTED):
            raise BusinessRuleError(
                f"Não é possível alterar itens de uma comanda com status '{order.status.value}'."
            )

        item = await self._order_repo.get_item(item_id, order_id)
        if item is None:
            raise NotFoundError("OrderItem", item_id)

        if item.status not in (OrderItemStatus.PENDING, OrderItemStatus.READY):
            raise BusinessRuleError(
                f"O item '{item.item_name}' não pode ser marcado como servido "
                f"(status atual: '{item.status.value}')."
            )

        item.status = OrderItemStatus.SERVED
        await self.session.flush()

        await self._log_audit(
            action="order_item.served",
            resource_type="order_item",
            resource_id=str(item.id),
            after={"status": "served"},
        )
        return await self._get_or_raise(order.id, establishment_id)
