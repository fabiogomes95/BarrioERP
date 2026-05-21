"""
app/database/session.py

Configura a engine async do SQLAlchemy e o gerador de sessões.

CONCEITO — Engine vs Session:
    Engine  = a conexão ao banco. É criada UMA vez e reutilizada.
              Gerencia um pool de conexões internamente.
    Session = uma "transação" com o banco. É criada a cada requisição
              e descartada ao final. Nunca compartilhe sessions entre requests!

CONCEITO — Connection Pool:
    Abrir e fechar conexões ao banco é caro (lento).
    O pool mantém N conexões abertas e as reutiliza.
    pool_size=10 → 10 conexões permanentes prontas para uso.
    max_overflow=20 → pode abrir até 20 extras em pico de tráfego.
"""

from collections.abc import AsyncGenerator

from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from app.core.config import settings

# ── Engine ──────────────────────────────────────────────────────────────────
# A engine é o objeto central de conexão. Criada uma vez na inicialização.
# URL: postgresql+asyncpg://user:pass@host:port/dbname
# asyncpg é o driver async para PostgreSQL — muito mais rápido que psycopg2

engine = create_async_engine(
    settings.database_url,
    pool_size=settings.DATABASE_POOL_SIZE,      # conexões permanentes no pool
    max_overflow=settings.DATABASE_MAX_OVERFLOW, # extras permitidas em pico
    pool_pre_ping=settings.DATABASE_POOL_PRE_PING, # testa conexão antes de usar
    echo=settings.DEBUG,  # em DEBUG=True, imprime todo SQL gerado no terminal
    future=True,          # usa a API moderna do SQLAlchemy 2.0
)

# ── Session Factory ──────────────────────────────────────────────────────────
# async_sessionmaker é uma "fábrica" — chame AsyncSessionLocal() para criar
# uma nova sessão. Pensa nela como um molde de bolo: o molde é um, os bolos são muitos.

AsyncSessionLocal = async_sessionmaker(
    bind=engine,
    class_=AsyncSession,
    expire_on_commit=False,  # após commit, objetos mantêm seus valores
    # sem isso, acessar user.email depois do commit causaria um erro async
    autocommit=False,  # nunca commita automaticamente — queremos controle explícito
    autoflush=False,   # nunca faz flush automático — evita comportamentos surpreendentes
)


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    """
    Dependency do FastAPI que fornece uma sessão de banco por requisição.

    Uso nos endpoints:
        @router.get("/something")
        async def handler(session: DBSession):  ← FastAPI injeta automaticamente
            ...

    FLUXO:
        1. Cria uma nova AsyncSession
        2. yield session → o endpoint usa a sessão
        3. Se sem erros → commit() (persiste as mudanças)
        4. Se com erro  → rollback() (reverte tudo — atomicidade)
        5. finally      → close() (sempre fecha, com ou sem erro)

    CONCEITO — yield em generators:
        O código ANTES do yield roda antes do endpoint.
        O endpoint roda onde está o yield.
        O código DEPOIS do yield roda depois do endpoint.
        É como um "try/finally" automático.
    """
    async with AsyncSessionLocal() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
        finally:
            await session.close()
