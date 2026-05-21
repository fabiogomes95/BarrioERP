"""
app/database/base.py

Define a Base declarativa do SQLAlchemy e os Mixins reutilizáveis.

CONCEITO — O que é DeclarativeBase?
    Todo model precisa de uma "Base" — uma classe mãe que registra
    todas as tabelas no mesmo metadado (metadata). O Alembic lê esse
    metadata para saber quais tabelas existem.

CONCEITO — O que é um Mixin?
    Um Mixin é uma classe pequena com um comportamento específico.
    Em vez de repetir os mesmos campos em cada model (copy/paste),
    você herda do Mixin:

        class User(Base, UUIDMixin, TimestampMixin, SoftDeleteMixin):
            pass  ← já tem id, created_at, updated_at, deleted_at
"""

from datetime import UTC, datetime
from uuid import UUID, uuid4

from sqlalchemy import DateTime, func, text
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import DeclarativeBase, Mapped, declared_attr, mapped_column


class Base(DeclarativeBase):
    """
    Raiz de todos os models.

    Ao herdar de Base, o SQLAlchemy registra a tabela no
    Base.metadata — que é o mapa completo do banco de dados.
    O Alembic usa esse mapa para gerar as migrations.
    """
    pass


class TimestampMixin:
    """
    Adiciona created_at e updated_at em qualquer model.

    server_default=func.now() → o PostgreSQL define o valor na inserção.
    onupdate=func.now()       → SQLAlchemy inclui updated_at = now() em todo UPDATE.

    DICA: timezone=True é obrigatório em sistemas reais.
    Sem timezone, "2026-01-01 12:00" é ambíguo — qual fuso horário?
    Com timezone, o valor fica em UTC no banco e pode ser convertido.
    """

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )


class UUIDMixin:
    """
    Chave primária como UUID v4.

    Por que UUID em vez de inteiro autoincrement (1, 2, 3...)?
    - Inteiros expõem informações: /orders/1 revela que você é cliente #1
    - UUIDs são imprevisíveis — melhor segurança por obscuridade
    - UUIDs podem ser gerados pelo cliente sem consultar o banco
    - Em sistemas distribuídos, UUIDs evitam colisões entre servidores

    default=uuid4             → Python gera o UUID antes de enviar ao banco.
    server_default=gen_random_uuid() → O banco TAMBÉM pode gerar (fallback).
    """

    id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        primary_key=True,
        default=uuid4,
        server_default=text("gen_random_uuid()"),
    )


class SoftDeleteMixin:
    """
    Deleção suave — registros nunca são removidos fisicamente.

    Em vez de DELETE FROM users WHERE id = ?, fazemos:
        UPDATE users SET deleted_at = now() WHERE id = ?

    E em todas as queries filtramos: WHERE deleted_at IS NULL

    Por que não deletar de verdade?
    - Auditoria: precisamos saber que o usuário existiu
    - Relatórios históricos: pedidos do mês passado ainda precisam mostrar
      o nome do prato mesmo que ele tenha sido removido do cardápio
    - Reversibilidade: é possível "restaurar" um registro deletado por engano
    """

    deleted_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
        index=True,  # índice porque sempre filtramos por este campo
    )

    @property
    def is_deleted(self) -> bool:
        """Atalho Python para verificar se o registro está deletado."""
        return self.deleted_at is not None

    def soft_delete(self) -> None:
        """Marca como deletado. Não persiste até o session.commit()."""
        self.deleted_at = datetime.now(UTC)


class VersionMixin:
    """
    Optimistic Locking — proteção contra edições concorrentes.

    PROBLEMA: dois garçons editam a mesma comanda ao mesmo tempo.
        1. Garçom A lê comanda (version=1)
        2. Garçom B lê comanda (version=1)
        3. Garçom A salva → banco atualiza version para 2
        4. Garçom B tenta salvar com version=1 → ERRO! (versão antiga)

    O SQLAlchemy detecta a divergência de versão e lança StaleDataError,
    que convertemos para OptimisticLockError (HTTP 409 Conflict).

    server_default=text("1") → garante que o banco insere 1 mesmo em
    inserts SQL diretos (sem passar pelo ORM Python).
    """

    version: Mapped[int] = mapped_column(
        default=1,
        server_default=text("1"),
        nullable=False,
    )

    @declared_attr.directive
    @classmethod
    def __mapper_args__(cls) -> dict:
        # Diz ao SQLAlchemy: "use a coluna version para controle de versão"
        # Forma correta no SQLAlchemy 2.0: declared_attr.directive + classmethod
        return {"version_id_col": cls.__table__.c.version}
