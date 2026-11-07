"""
app/services/online_order_pricing.py

Transforma o carrinho do cardápio público em linhas de pedido com preço
calculado AQUI no servidor, a partir do cadastro — o navegador só manda
"qual item, quantos, qual complemento, meio a meio com qual".

Segue exatamente as convenções da comanda (OrderService.add_item), pra um
pedido online ficar igual a um lançado no balcão:
    - Complemento:  "Churrasco - frango", ligado ao Churrasco, preço do item
    - Meio a meio:  "Pizza Calabresa / Mussarela", preço da metade MAIS CARA,
                    só entre itens de pizza (sem menu_item_id único)
    - Item comum:   referência ao menu_item (KDS + baixa de estoque)
A linha guarda a origem (complemento / half_with) pro aceite lançar pelo
mesmo caminho do balcão — cozinha e estoque iguais.

Módulo puro (sem banco/auth) — importado pelo app.public_menu e testado
direto em tests/test_online_order_pricing.py.
"""

from dataclasses import dataclass
from decimal import Decimal
from typing import Protocol
from uuid import UUID


class _MenuItemLike(Protocol):
    id: UUID
    name: str
    price: Decimal
    category_id: UUID
    complementos: list[str]


@dataclass(frozen=True)
class CartLine:
    menu_item_id: UUID
    quantity: int
    complemento: str | None = None
    half_with: UUID | None = None


@dataclass(frozen=True)
class PricedLine:
    menu_item_id: UUID | None  # None = meio a meio (dois sabores)
    item_name: str
    unit_price: Decimal
    quantity: int
    complemento: str | None = None
    half_first: UUID | None = None   # meio a meio: os dois sabores, na ordem do pedido
    half_with: UUID | None = None

    @property
    def subtotal(self) -> Decimal:
        return self.unit_price * self.quantity

    def as_json(self) -> dict:
        return {
            "menu_item_id": str(self.menu_item_id) if self.menu_item_id else None,
            "item_name": self.item_name,
            "unit_price": str(self.unit_price),
            "quantity": self.quantity,
            "complemento": self.complemento,
            "half_first": str(self.half_first) if self.half_first else None,
            "half_with": str(self.half_with) if self.half_with else None,
        }


class CartError(ValueError):
    """Mensagem já pronta pra mostrar ao cliente."""


def half_pizza_name(first: str, second: str) -> str:
    """Mesmo nome que a aba '½ Meia' da comanda gera: 'Pizza Calabresa / Mussarela'."""
    words1, words2 = first.split(" "), second.split(" ")
    short2 = " ".join(words2[1:]) if words1[0] == words2[0] else second
    return f"{first} / {short2}"


def is_pizza_category(name: str) -> bool:
    # Mesma regra da comanda: meio a meio é só pra categoria com "pizza" no nome
    return "pizza" in name.lower()


def price_cart(
    lines: list[CartLine],
    items: dict[UUID, _MenuItemLike],
    pizza_category_ids: set[UUID],
) -> list[PricedLine]:
    """`items` = só itens ativos e disponíveis do estabelecimento."""
    priced: list[PricedLine] = []
    for line in lines:
        item = items.get(line.menu_item_id)
        if item is None:
            raise CartError("Um dos itens do pedido não está mais disponível. Atualize o cardápio.")

        if line.half_with is not None and line.half_with != item.id:
            other = items.get(line.half_with)
            if other is None:
                raise CartError("Um dos sabores da pizza não está mais disponível. Atualize o cardápio.")
            if item.category_id not in pizza_category_ids or other.category_id not in pizza_category_ids:
                raise CartError("Meio a meio é só para pizzas.")
            priced.append(PricedLine(
                menu_item_id=None,
                item_name=half_pizza_name(item.name, other.name),
                unit_price=max(item.price, other.price),
                quantity=line.quantity,
                half_first=item.id,
                half_with=other.id,
            ))
            continue

        if item.complementos:
            if not line.complemento or line.complemento not in item.complementos:
                raise CartError(f"Escolha uma opção para {item.name}.")
            priced.append(PricedLine(
                menu_item_id=item.id,
                item_name=f"{item.name} - {line.complemento}",
                unit_price=item.price,
                quantity=line.quantity,
                complemento=line.complemento,
            ))
            continue

        priced.append(PricedLine(
            menu_item_id=item.id,
            item_name=item.name,
            unit_price=item.price,
            quantity=line.quantity,
        ))
    return priced
