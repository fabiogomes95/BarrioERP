"""Preço do pedido online é calculado no servidor — o navegador não decide valor."""

from dataclasses import dataclass, field
from decimal import Decimal
from uuid import UUID, uuid4

import pytest

from app.services.online_order_pricing import CartError, CartLine, half_pizza_name, price_cart

PIZZA_CAT = uuid4()
PETISCO_CAT = uuid4()


@dataclass
class Item:
    name: str
    price: Decimal
    category_id: UUID
    complementos: list[str] = field(default_factory=list)
    id: UUID = field(default_factory=uuid4)


@pytest.fixture
def menu() -> dict[str, Item]:
    return {
        "calabresa": Item("Pizza Calabresa", Decimal("48.00"), PIZZA_CAT),
        "mussarela": Item("Pizza Mussarela", Decimal("42.00"), PIZZA_CAT),
        "churrasco": Item("Churrasco", Decimal("6.00"), PETISCO_CAT, ["carne", "frango"]),
        "batata": Item("Batata Frita P", Decimal("15.00"), PETISCO_CAT),
    }


def _price(menu: dict[str, Item], *lines: CartLine):
    return price_cart(list(lines), {i.id: i for i in menu.values()}, {PIZZA_CAT})


def test_item_comum_referencia_o_cardapio(menu):
    [line] = _price(menu, CartLine(menu["batata"].id, 2))
    assert line.menu_item_id == menu["batata"].id
    assert line.unit_price == Decimal("15.00")
    assert line.subtotal == Decimal("30.00")


def test_meio_a_meio_cobra_a_metade_mais_cara(menu):
    [line] = _price(menu, CartLine(menu["mussarela"].id, 1, half_with=menu["calabresa"].id))
    assert line.unit_price == Decimal("48.00")
    assert line.menu_item_id is None
    # guarda os dois sabores pro aceite lançar pelo caminho do balcão (cozinha/estoque)
    assert (line.half_first, line.half_with) == (menu["mussarela"].id, menu["calabresa"].id)
    # mesmo formato da aba "½ Meia" da comanda
    assert line.item_name == "Pizza Mussarela / Calabresa"


def test_meio_a_meio_com_o_mesmo_sabor_vira_pizza_inteira(menu):
    [line] = _price(menu, CartLine(menu["calabresa"].id, 1, half_with=menu["calabresa"].id))
    assert line.menu_item_id == menu["calabresa"].id
    assert line.item_name == "Pizza Calabresa"


def test_meio_a_meio_fora_de_pizza_e_recusado(menu):
    with pytest.raises(CartError):
        _price(menu, CartLine(menu["calabresa"].id, 1, half_with=menu["batata"].id))


def test_complemento_obrigatorio_e_validado(menu):
    [line] = _price(menu, CartLine(menu["churrasco"].id, 3, complemento="frango"))
    assert line.item_name == "Churrasco - frango"
    assert line.subtotal == Decimal("18.00")
    assert line.menu_item_id == menu["churrasco"].id and line.complemento == "frango"
    with pytest.raises(CartError):
        _price(menu, CartLine(menu["churrasco"].id, 1))
    with pytest.raises(CartError):
        _price(menu, CartLine(menu["churrasco"].id, 1, complemento="picanha"))


def test_item_indisponivel_e_recusado(menu):
    with pytest.raises(CartError):
        _price(menu, CartLine(uuid4(), 1))


def test_nome_meio_a_meio_sem_prefixo_comum():
    assert half_pizza_name("Calabresa", "Frango") == "Calabresa / Frango"
