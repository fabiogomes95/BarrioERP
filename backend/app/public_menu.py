"""
app/public_menu.py

Serviço PÚBLICO e independente do ERP principal — cardápio + envio de pedido.

POR QUE UM APP FASTAPI SEPARADO (em vez de um router dentro de app.main)?
    app.main carrega TODO o ERP: login, comandas, caixa, admin, relatórios...
    Se um dia expuséssemos essa porta pra internet (Tailscale Funnel),
    qualquer endpoint autenticado ficaria alcançável por qualquer pessoa do
    mundo — mesmo que ainda precisasse de senha, é superfície de ataque que
    o resto do BarrioERP foi desenhado pra NUNCA ter (ver docs/ARCHITECTURE.md).

    Este arquivo só importa o necessário pra mostrar o cardápio: sessão de
    banco e os repositories de menu/estabelecimento. Nada de auth, comandas,
    caixa. A única escrita é INSERIR um pedido PENDENTE em online_orders
    (preço recalculado aqui, nunca o do navegador) — ele só vira comanda
    quando alguém da casa aceita no app. Se esse processo for comprometido,
    o estrago máximo é "alguém viu o cardápio / mandou pedido falso pra fila
    de aceite" — não dá pra abrir caixa, aplicar desconto ou logar como
    ninguém, porque esse código nem sabe que essas coisas existem.

    Roda como serviço Windows separado (BarrioERP-Menu-Publico), numa porta
    própria (ver deploy/windows/instalar_servico_cardapio_publico.ps1). Só ESSA porta deve
    ser exposta via `tailscale funnel` — o resto do sistema (8000/443)
    continua só na rede local/Tailscale, como sempre foi.

USO (local, pra testar):
    .venv\\Scripts\\python.exe -m uvicorn app.public_menu:app --port 8090
"""

import re
from datetime import datetime
from decimal import Decimal
from pathlib import Path
from zoneinfo import ZoneInfo
from typing import Literal
from uuid import UUID

from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field, field_validator
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
from sqlalchemy import func, select

from app.core import events
from app.core.config import settings
from app.database.session import AsyncSessionLocal
from app.models.establishment import Establishment
from app.models.online_order import OnlineOrder, OnlineOrderStatus
from app.models.order import OrderType
from app.repositories.base import BaseRepository
from app.repositories.menu_repository import MenuCategoryRepository, MenuItemRepository
from app.services.online_order_pricing import CartError, CartLine, is_pizza_category, price_cart
from app.services.establishment_settings import online_orders_paused
from app.services.opening_hours import is_open


class _EstablishmentRepository(BaseRepository[Establishment]):
    model = Establishment


def _client_ip(request: Request) -> str:
    """
    IP real do cliente. Pela internet o acesso chega via `tailscale funnel`,
    que é um proxy local — request.client.host vira 127.0.0.1 pra TODO MUNDO,
    e o limite por IP viraria um limite global (um cliente travaria os outros).

    Só confia no X-Forwarded-For quando a conexão vem do próprio PC (o proxy),
    e pega a ÚLTIMA entrada — a que o proxy acrescentou. As anteriores vêm do
    navegador e podem ser forjadas.
    """
    host = request.client.host if request.client else ""
    if host in ("127.0.0.1", "::1"):
        forwarded = request.headers.get("x-forwarded-for")
        if forwarded:
            return forwarded.split(",")[-1].strip()
    return host or "desconhecido"


# Limite próprio (não compartilha o do app.main) — 30 req/min por IP é
# generoso pra um cliente folheando o cardápio, mas barra scraping/abuso
# numa rota que agora fica acessível de qualquer lugar da internet.
limiter = Limiter(key_func=_client_ip, default_limits=["30/minute"])

# Teto de pedidos esperando aceite — se alguém automatizar spam driblando o
# limite por IP, a fila para de crescer em vez de afogar a tela de Pedidos.
MAX_PENDING_ONLINE_ORDERS = 30

app = FastAPI(
    title="Cardápio — Recanto da Barra",
    docs_url=None,  # não expõe /docs publicamente — não é API pra terceiros
    redoc_url=None,
    openapi_url=None,
)
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

# A página também é publicada no GitHub Pages (abre mesmo com o PC desligado —
# ver deploy/windows/publicar_cardapio.ps1) e chama esta API de outro domínio. Só as origens
# listadas no .env, só leitura do cardápio + envio de pedido, sem cookies.
if settings.PUBLIC_MENU_CORS_ORIGINS:
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.PUBLIC_MENU_CORS_ORIGINS,
        allow_methods=["GET", "POST"],
        allow_headers=["Content-Type"],
        allow_credentials=False,
        max_age=3600,
    )


# ── Schemas de resposta (só o que o cliente pode ver — nunca cost/sku) ──

class MenuItemOut(BaseModel):
    id: UUID  # necessário pra montar o pedido; não dá acesso a nada sozinho
    name: str
    description: str | None
    price: float
    complementos: list[str]


class MenuCategoryOut(BaseModel):
    name: str
    description: str | None
    items: list[MenuItemOut]


class PublicMenuOut(BaseModel):
    establishment_name: str
    whatsapp: str | None
    service_fee_percent: float
    categories: list[MenuCategoryOut]
    # Horário de pedidos ({} = sempre aberto). A página calcula "Aberto/Fechado"
    # com isso — inclusive na cópia do GitHub, com o PC desligado.
    hours: dict[str, str]
    open_now: bool
    # Casa pausou os pedidos pelo site (noite cheia): a página mostra o aviso
    # e o pedido segue pelo WhatsApp, como quando o PC está fora do ar.
    orders_paused: bool = False


# ── API ──────────────────────────────────────────────────────────────────────

async def _get_establishment(session, slug: str) -> Establishment:
    establishments = await _EstablishmentRepository(session).list(
        Establishment.slug == slug,
        Establishment.is_active.is_(True),
        Establishment.deleted_at.is_(None),
        limit=1,
    )
    if not establishments:
        raise HTTPException(status_code=404, detail="Cardápio não encontrado")
    return establishments[0]


@app.get("/api/cardapio/{slug}", response_model=PublicMenuOut)
@limiter.limit("30/minute")
async def get_public_menu(slug: str, request: Request) -> PublicMenuOut:
    async with AsyncSessionLocal() as session:
        establishment = await _get_establishment(session, slug)

        categories = await MenuCategoryRepository(session).list_by_establishment(
            establishment.id, active_only=True,
        )
        items = await MenuItemRepository(session).list_by_establishment(
            establishment.id, active_only=True, available_only=True, limit=500,
        )

    items_by_category: dict = {}
    for item in items:
        items_by_category.setdefault(item.category_id, []).append(item)

    categories_out = [
        MenuCategoryOut(
            name=cat.name,
            description=cat.description,
            items=[
                MenuItemOut(
                    id=i.id, name=i.name, description=i.description,
                    price=float(i.price), complementos=i.complementos or [],
                )
                for i in items_by_category.get(cat.id, [])
            ],
        )
        for cat in categories
        if items_by_category.get(cat.id)  # esconde categorias sem item disponível
    ]

    return PublicMenuOut(
        establishment_name=settings.PUBLIC_MENU_DISPLAY_NAME or establishment.name,
        whatsapp=settings.PUBLIC_MENU_WHATSAPP,
        service_fee_percent=float(establishment.service_fee_percent),
        categories=categories_out,
        hours=settings.PUBLIC_MENU_HOURS,
        open_now=_open_now(),
        orders_paused=online_orders_paused(establishment),
    )


def _open_now() -> bool:
    return is_open(settings.PUBLIC_MENU_HOURS, datetime.now(ZoneInfo(settings.TIMEZONE)))


# ── Envio de pedido (fica pendente até alguém aceitar no app) ────────────────

class CartLineIn(BaseModel):
    menu_item_id: UUID
    quantity: int = Field(ge=1, le=30)
    complemento: str | None = Field(default=None, max_length=60)
    half_with: UUID | None = None  # outra pizza, pra meio a meio


class OnlineOrderIn(BaseModel):
    customer_name: str = Field(min_length=2, max_length=80)
    customer_phone: str = Field(max_length=30)
    fulfillment: Literal["delivery", "pickup"]
    notes: str | None = Field(default=None, max_length=500)
    delivery_location: str | None = Field(default=None, max_length=200)  # opcional, só entrega
    # Obrigatório, só informativo (vai na mensagem e no pedido). Pix: a casa manda a chave no WhatsApp.
    payment_method: Literal["cash", "pix", "credit", "debit"]
    change_for: Decimal | None = Field(default=None, gt=0, le=10000)  # dinheiro: troco pra quanto
    items: list[CartLineIn] = Field(min_length=1, max_length=40)

    @field_validator("customer_name")
    @classmethod
    def _strip_name(cls, v: str) -> str:
        v = " ".join(v.split())
        if len(v) < 2:
            raise ValueError("Informe seu nome.")
        return v

    @field_validator("customer_phone")
    @classmethod
    def _digits_phone(cls, v: str) -> str:
        digits = re.sub(r"\D", "", v)
        # DDD + número (10/11), opcionalmente com 55 na frente
        if not 10 <= len(digits) <= 13:
            raise ValueError("Informe um telefone com DDD.")
        return digits

    @field_validator("notes", "delivery_location")
    @classmethod
    def _blank_notes(cls, v: str | None) -> str | None:
        return v.strip() or None if v else None


class OnlineOrderCreated(BaseModel):
    number: int
    total: float


@app.post("/api/cardapio/{slug}/pedidos", response_model=OnlineOrderCreated, status_code=201)
@limiter.limit("4/minute;20/hour")
async def create_online_order(slug: str, data: OnlineOrderIn, request: Request) -> OnlineOrderCreated:
    if not _open_now():
        raise HTTPException(
            status_code=409,
            detail="Estamos fechados agora. Confira o horário no fim do cardápio!",
        )

    async with AsyncSessionLocal() as session:
        establishment = await _get_establishment(session, slug)
        if online_orders_paused(establishment):
            raise HTTPException(
                status_code=409,
                detail="Os pedidos pelo site estão pausados agora. Finalize pelo WhatsApp!",
            )

        pending = await session.scalar(
            select(func.count()).select_from(OnlineOrder).where(
                OnlineOrder.establishment_id == establishment.id,
                OnlineOrder.status == OnlineOrderStatus.PENDING,
            )
        )
        if pending >= MAX_PENDING_ONLINE_ORDERS:
            raise HTTPException(
                status_code=429,
                detail="Estamos com muitos pedidos agora. Chama a gente no WhatsApp!",
            )

        categories = await MenuCategoryRepository(session).list_by_establishment(
            establishment.id, active_only=True,
        )
        items = await MenuItemRepository(session).list_by_establishment(
            establishment.id, active_only=True, available_only=True, limit=500,
        )
        try:
            lines = price_cart(
                [CartLine(l.menu_item_id, l.quantity, l.complemento, l.half_with) for l in data.items],
                {i.id: i for i in items},
                {c.id for c in categories if is_pizza_category(c.name)},
            )
        except CartError as e:
            raise HTTPException(status_code=422, detail=str(e))

        total = sum((l.subtotal for l in lines), start=Decimal("0"))
        change_for = data.change_for if data.payment_method == "cash" else None
        if change_for is not None and change_for < total:
            raise HTTPException(
                status_code=422,
                detail=f"O troco precisa ser pra um valor maior que o total (R$ {total:.2f})."
                .replace(f"{total:.2f}", f"{total:.2f}".replace(".", ",")),
            )

        online_order = OnlineOrder(
            establishment_id=establishment.id,
            status=OnlineOrderStatus.PENDING,
            fulfillment=OrderType(data.fulfillment),
            customer_name=data.customer_name,
            customer_phone=data.customer_phone,
            notes=data.notes,
            delivery_location=data.delivery_location if data.fulfillment == "delivery" else None,
            payment_method=data.payment_method,
            change_for=change_for,
            items=[l.as_json() for l in lines],
            total=total,
            client_ip=_client_ip(request),
        )
        session.add(online_order)
        await session.flush()  # preenche o number (sequência do banco)

        # Mesmo canal LISTEN/NOTIFY do app.main: o aviso chega no app na hora,
        # mesmo vindo de outro processo. Só é entregue depois do COMMIT.
        await events.publish(
            session,
            "online_order.created",
            company_id=str(establishment.company_id),
            establishment_id=str(establishment.id),
            online_order_id=str(online_order.id),
            number=online_order.number,
            customer_name=online_order.customer_name,
            fulfillment=online_order.fulfillment.value,
            total=str(online_order.total),
        )
        await session.commit()

        return OnlineOrderCreated(number=online_order.number, total=float(online_order.total))


# ── Página estática (HTML/CSS/JS puro, sem build step) ───────────────────────

_STATIC = Path(__file__).parent.parent.parent / "public_menu_static"

if _STATIC.exists():
    app.mount("/static", StaticFiles(directory=str(_STATIC)), name="public-menu-static")

    # no-cache: celular não pode ficar preso numa versão antiga da página —
    # mesmo problema que o app.main já resolve pro SPA principal (ver lá).
    _NO_CACHE = {"Cache-Control": "no-cache, no-store, must-revalidate"}

    @app.get("/cardapio/{slug}", include_in_schema=False)
    async def serve_menu_page(slug: str) -> FileResponse:
        return FileResponse(str(_STATIC / "index.html"), headers=_NO_CACHE)

    @app.get("/", include_in_schema=False)
    async def root() -> FileResponse:
        return FileResponse(str(_STATIC / "index.html"), headers=_NO_CACHE)
