from datetime import datetime
from decimal import Decimal
from uuid import UUID

from pydantic import Field

from app.models.online_order import OnlineOrderStatus
from app.models.order import OrderType
from app.schemas.common import BaseSchema


class OnlineOrderLine(BaseSchema):
    menu_item_id: UUID | None
    item_name: str
    unit_price: Decimal
    quantity: int


class OnlineOrderResponse(BaseSchema):
    id: UUID
    number: int
    status: OnlineOrderStatus
    fulfillment: OrderType
    customer_name: str
    customer_phone: str
    notes: str | None
    delivery_location: str | None
    payment_method: str | None
    change_for: Decimal | None
    items: list[OnlineOrderLine]
    total: Decimal
    order_id: UUID | None
    created_at: datetime


class OnlineOrderAccepted(BaseSchema):
    order_id: UUID


class OnlineOrdersPause(BaseSchema):
    paused: bool


class DayNoticeIn(BaseSchema):
    """Aviso do dia no cardápio. Texto vazio + entrega ligada = tira o aviso."""
    text: str = Field(default="", max_length=280)
    no_delivery: bool = False


class DayNoticeOut(BaseSchema):
    active: bool
    text: str = ""
    no_delivery: bool = False
    until: datetime | None = None  # some sozinho às 5h


class OnlineTopItem(BaseSchema):
    name: str
    quantity: int
    total: Decimal


class OnlineOrdersReport(BaseSchema):
    received: int
    accepted: int
    rejected: int
    pending: int
    accepted_total: Decimal      # soma dos pedidos aceitos, como o cliente pediu
    average_ticket: Decimal      # accepted_total / accepted
    delivery: int                # entre os aceitos
    pickup: int
    top_items: list[OnlineTopItem]
