"""
app/public_menu.py

Serviço PÚBLICO e independente do ERP principal — só cardápio, só leitura.

POR QUE UM APP FASTAPI SEPARADO (em vez de um router dentro de app.main)?
    app.main carrega TODO o ERP: login, comandas, caixa, admin, relatórios...
    Se um dia expuséssemos essa porta pra internet (Tailscale Funnel),
    qualquer endpoint autenticado ficaria alcançável por qualquer pessoa do
    mundo — mesmo que ainda precisasse de senha, é superfície de ataque que
    o resto do BarrioERP foi desenhado pra NUNCA ter (ver ARCHITECTURE.md).

    Este arquivo só importa o necessário pra mostrar o cardápio: sessão de
    banco (leitura) e os repositories de menu/estabelecimento. Nada de auth,
    pedidos, caixa. Se esse processo for comprometido, o estrago máximo é
    "alguém viu o cardápio" — não dá pra abrir caixa, aplicar desconto ou
    logar como ninguém, porque esse código nem sabe que essas coisas existem.

    Roda como serviço Windows separado (BarrioERP-Menu-Publico), numa porta
    própria (ver instalar_servico_cardapio_publico.ps1). Só ESSA porta deve
    ser exposta via `tailscale funnel` — o resto do sistema (8000/443)
    continua só na rede local/Tailscale, como sempre foi.

USO (local, pra testar):
    .venv\\Scripts\\python.exe -m uvicorn app.public_menu:app --port 8090
"""

from pathlib import Path

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
from slowapi.util import get_remote_address

from app.core.config import settings
from app.database.session import AsyncSessionLocal
from app.models.establishment import Establishment
from app.repositories.base import BaseRepository
from app.repositories.menu_repository import MenuCategoryRepository, MenuItemRepository


class _EstablishmentRepository(BaseRepository[Establishment]):
    model = Establishment


# Limite próprio (não compartilha o do app.main) — 30 req/min por IP é
# generoso pra um cliente folheando o cardápio, mas barra scraping/abuso
# numa rota que agora fica acessível de qualquer lugar da internet.
limiter = Limiter(key_func=get_remote_address, default_limits=["30/minute"])

app = FastAPI(
    title="Cardápio — Recanto da Barra",
    docs_url=None,  # não expõe /docs publicamente — não é API pra terceiros
    redoc_url=None,
)
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)


# ── Schemas de resposta (só o que o cliente pode ver — nunca cost/sku/ids internos) ──

class MenuItemOut(BaseModel):
    name: str
    description: str | None
    price: float


class MenuCategoryOut(BaseModel):
    name: str
    description: str | None
    items: list[MenuItemOut]


class PublicMenuOut(BaseModel):
    establishment_name: str
    whatsapp: str | None
    service_fee_percent: float
    categories: list[MenuCategoryOut]


# ── API ──────────────────────────────────────────────────────────────────────

@app.get("/api/cardapio/{slug}", response_model=PublicMenuOut)
@limiter.limit("30/minute")
async def get_public_menu(slug: str, request: Request) -> PublicMenuOut:
    async with AsyncSessionLocal() as session:
        establishments = await _EstablishmentRepository(session).list(
            Establishment.slug == slug,
            Establishment.is_active.is_(True),
            Establishment.deleted_at.is_(None),
            limit=1,
        )
        if not establishments:
            raise HTTPException(status_code=404, detail="Cardápio não encontrado")
        establishment = establishments[0]

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
                MenuItemOut(name=i.name, description=i.description, price=float(i.price))
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
    )


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
