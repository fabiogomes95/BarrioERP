"""
app/main.py

Ponto de entrada da aplicação FastAPI.

RESPONSABILIDADES:
    1. Criar a instância do FastAPI
    2. Registrar middlewares (CORS)
    3. Registrar os routers (endpoints)
    4. Registrar os exception handlers
    5. Configurar o lifespan (inicialização e shutdown)

CONCEITO — lifespan:
    O lifespan define o que acontece quando o servidor LIGA e DESLIGA.
    @asynccontextmanager:
        yield → servidor está rodando
        código após yield → executa no shutdown

    Usamos para fechar a engine do banco ao desligar o servidor.
    Sem isso, conexões poderiam ficar abertas em produção.

CONCEITO — CORS (Cross-Origin Resource Sharing):
    Browsers bloqueiam requisições de um domínio para outro por segurança.
    O CORS configura quais origens podem acessar a API.

    Em desenvolvimento: allow_origins=["*"] (qualquer origem)
    Em produção: allow_origins=["https://barrio.com.br"] (só o frontend)

CONCEITO — Exception Handlers:
    Em vez de tratar erros em cada endpoint, registramos handlers globais.
    Quando uma exceção de domínio é lançada em qualquer lugar:
        AuthenticationError → handler → HTTP 401
        NotFoundError       → handler → HTTP 404
    O endpoint não precisa saber nada sobre HTTP status codes.
"""

from contextlib import asynccontextmanager
from pathlib import Path
from typing import AsyncGenerator

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from app.api.v1.router import api_router
from app.core.config import settings
from app.core.exceptions import (
    AuthenticationError,
    BarrioError,
    BusinessRuleError,
    ConflictError,
    ForbiddenError,
    NotFoundError,
    OptimisticLockError,
    ValidationError,
)
from app.database.session import engine
from app.core.rate_limit import limiter
from slowapi import _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    """
    Gerencia o ciclo de vida da aplicação.
    Tudo antes do yield: roda ao iniciar.
    Tudo depois do yield: roda ao desligar.
    """
    yield
    # Ao desligar: fecha todas as conexões do pool
    await engine.dispose()


app = FastAPI(
    title=settings.APP_NAME,
    version=settings.APP_VERSION,
    docs_url="/docs" if not settings.is_production else None,
    redoc_url="/redoc" if not settings.is_production else None,
    lifespan=lifespan,
)

app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

# ── Middlewares ───────────────────────────────────────────────────────────────

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ── Routers ───────────────────────────────────────────────────────────────────

app.include_router(api_router, prefix="/api/v1")

# ── Exception Handlers ────────────────────────────────────────────────────────
# Cada handler converte uma exceção de domínio em uma resposta HTTP.
# O formato padrão de erro é: {"error": "CODE", "message": "descrição humana"}

@app.exception_handler(AuthenticationError)
async def auth_error_handler(request: Request, exc: AuthenticationError) -> JSONResponse:
    return JSONResponse(
        status_code=401,
        content={"error": exc.code, "message": exc.message},
        headers={"WWW-Authenticate": "Bearer"},
    )


@app.exception_handler(NotFoundError)
async def not_found_handler(request: Request, exc: NotFoundError) -> JSONResponse:
    return JSONResponse(status_code=404, content={"error": exc.code, "message": exc.message})


@app.exception_handler(ConflictError)
async def conflict_handler(request: Request, exc: ConflictError) -> JSONResponse:
    return JSONResponse(status_code=409, content={"error": exc.code, "message": exc.message})


@app.exception_handler(OptimisticLockError)
async def lock_handler(request: Request, exc: OptimisticLockError) -> JSONResponse:
    return JSONResponse(status_code=409, content={"error": exc.code, "message": exc.message})


@app.exception_handler(ForbiddenError)
async def forbidden_handler(request: Request, exc: ForbiddenError) -> JSONResponse:
    return JSONResponse(status_code=403, content={"error": exc.code, "message": exc.message})


@app.exception_handler(BusinessRuleError)
@app.exception_handler(ValidationError)
async def business_rule_handler(request: Request, exc: BarrioError) -> JSONResponse:
    return JSONResponse(status_code=422, content={"error": exc.code, "message": exc.message})


@app.exception_handler(BarrioError)
async def generic_domain_handler(request: Request, exc: BarrioError) -> JSONResponse:
    # Fallback: qualquer BarrioError não capturado pelos handlers específicos
    return JSONResponse(status_code=400, content={"error": exc.code, "message": exc.message})


# ── Health Check ──────────────────────────────────────────────────────────────

@app.get("/health", tags=["health"])
async def health() -> dict:
    return {"status": "ok", "version": settings.APP_VERSION, "env": settings.ENVIRONMENT}


# ── Frontend estático ─────────────────────────────────────────────────────────
# Serve o build do React. Deve vir DEPOIS das rotas da API.

_FRONTEND = Path(__file__).parent.parent.parent / "frontend" / "dist"

if _FRONTEND.exists():
    app.mount("/assets", StaticFiles(directory=str(_FRONTEND / "assets")), name="assets")

    @app.get("/{full_path:path}", include_in_schema=False)
    async def serve_spa(full_path: str) -> FileResponse:
        # Arquivos soltos em public/ (favicon, ícones, manifest) viram arquivos
        # reais em dist/ — servir direto se existirem, senão cai no index.html
        # (roteamento client-side do React Router).
        candidate = (_FRONTEND / full_path).resolve()
        if full_path and candidate.is_file() and _FRONTEND.resolve() in candidate.parents:
            return FileResponse(str(candidate))
        return FileResponse(
            str(_FRONTEND / "index.html"),
            headers={"Cache-Control": "no-cache, no-store, must-revalidate"},
        )
