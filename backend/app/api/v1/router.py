"""
app/api/v1/router.py

Roteador central da API v1.

Todos os endpoints são registrados aqui com seu prefix e tags.
O router central é incluído no app FastAPI em main.py.

ESTRUTURA DE URL:
    main.py:    app.include_router(api_router, prefix="/api/v1")
    router.py:  api_router.include_router(auth.router, prefix="/auth")
    endpoint:   @router.post("/login")

    Resultado final: POST /api/v1/auth/login

CONCEITO — tags:
    Tags agrupam endpoints no Swagger UI (/docs).
    Todos os endpoints de auth aparecem juntos sob "auth".
"""

from fastapi import APIRouter

from app.api.v1.endpoints import admin, audit, auth, cash, menu, onboarding, orders, payments, reports, tables, users

api_router = APIRouter()

api_router.include_router(
    onboarding.router,
    prefix="/onboarding",
    tags=["onboarding"],
)

api_router.include_router(
    auth.router,
    prefix="/auth",
    tags=["auth"],
)

api_router.include_router(
    tables.router,
    prefix="/tables",
    tags=["tables"],
)

api_router.include_router(
    orders.router,
    prefix="/orders",
    tags=["orders"],
)

# Payments usa rotas mistas (/payments e /orders/{id}/...) — sem prefix
api_router.include_router(
    payments.router,
    tags=["payments"],
)

api_router.include_router(
    menu.router,
    prefix="/menu",
    tags=["menu"],
)

api_router.include_router(
    users.router,
    prefix="/users",
    tags=["users"],
)

api_router.include_router(
    reports.router,
    prefix="/reports",
    tags=["reports"],
)

api_router.include_router(
    admin.router,
    prefix="/admin",
    tags=["admin"],
)

api_router.include_router(
    cash.router,
    prefix="/cash",
    tags=["cash"],
)

api_router.include_router(
    audit.router,
    prefix="/audit",
    tags=["audit"],
)
