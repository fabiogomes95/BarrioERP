"""
app/repositories/base.py

Repository base com operações CRUD genéricas.

CONCEITO — Repository Pattern:
    O Repository isola todo o código de acesso ao banco em um único lugar.
    Os Services nunca escrevem SQL — eles chamam o Repository.

    Vantagens:
    1. Se trocar PostgreSQL por outro banco, só muda o Repository.
    2. Código SQL centralizado — fácil de encontrar e manter.
    3. Services ficam focados em regras de negócio, não em queries.

CONCEITO — Generic[ModelT]:
    Esta classe usa Generics do Python para ser reutilizável com qualquer Model.

    class UserRepository(BaseRepository[User]):    ← ModelT = User
        pass

    Agora UserRepository.get() retorna User, não Any.
    O editor de código entende os tipos corretamente.
"""

from typing import Any, Generic, TypeVar
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database.base import Base

# TypeVar define o "buraco genérico" — será preenchido pelo tipo real
# bound=Base garante que só aceitamos subclasses de Base (nossos models)
ModelT = TypeVar("ModelT", bound=Base)


class BaseRepository(Generic[ModelT]):
    """
    CRUD genérico para qualquer Model.

    Subclasses devem definir `model`:
        class UserRepository(BaseRepository[User]):
            model = User
    """

    model: type[ModelT]

    def __init__(self, session: AsyncSession) -> None:
        # A sessão é injetada — o repository não cria sessões próprias
        self.session = session

    async def get(self, id: UUID) -> ModelT | None:
        """
        Busca por chave primária.

        session.get() é a forma mais eficiente — primeiro checa o
        identity map (cache interno da sessão) antes de ir ao banco.
        Se o objeto já foi carregado nesta sessão, não faz nova query.
        """
        return await self.session.get(self.model, id)

    async def get_or_raise(self, id: UUID) -> ModelT:
        """
        Busca por PK, lançando NotFoundError se não existir.

        Use quando a ausência do registro é um erro de negócio.
        Use get() quando a ausência é esperada (retorna None).
        """
        from app.core.exceptions import NotFoundError

        obj = await self.get(id)
        if obj is None:
            raise NotFoundError(self.model.__name__, id)
        return obj

    async def list(
        self,
        *filters: Any,
        limit: int = 20,
        offset: int = 0,
        order_by: Any = None,
    ) -> list[ModelT]:
        """
        Lista registros com filtros, paginação e ordenação opcionais.

        COMO USAR:
            # Todos os usuários ativos de uma empresa
            users = await repo.list(
                User.company_id == company_id,
                User.is_active == True,
                User.deleted_at.is_(None),
                limit=20,
                offset=0,
                order_by=User.name,
            )

        CONCEITO — select():
            select(User) → "SELECT * FROM users"
            .where(...)  → adiciona cláusula WHERE
            .limit(20)   → LIMIT 20
            .offset(0)   → OFFSET 0 (paginação)
        """
        stmt = select(self.model).where(*filters).limit(limit).offset(offset)
        if order_by is not None:
            stmt = stmt.order_by(order_by)
        result = await self.session.execute(stmt)
        return list(result.scalars().all())
        # .scalars() extrai os objetos Model do resultado bruto
        # .all()     converte para lista Python

    async def count(self, *filters: Any) -> int:
        """
        Conta registros para paginação.

        SELECT COUNT(*) FROM tabela WHERE ...
        """
        from sqlalchemy import func

        stmt = select(func.count()).select_from(self.model).where(*filters)
        result = await self.session.execute(stmt)
        return result.scalar_one()

    async def add(self, obj: ModelT) -> ModelT:
        """
        Persiste um novo objeto no banco.

        FLUXO:
            session.add(obj)   → adiciona ao contexto da sessão (apenas memória)
            session.flush()    → envia INSERT ao banco (dentro da transação)
            session.refresh()  → recarrega o objeto do banco para pegar
                                 valores gerados pelo servidor:
                                 - id (gen_random_uuid())
                                 - created_at (now())
                                 - updated_at (now())

        Nota: flush() NÃO faz commit. A transação ainda pode ser revertida.
        O commit acontece em get_db() quando o endpoint termina sem erros.
        """
        self.session.add(obj)
        await self.session.flush()
        await self.session.refresh(obj)
        return obj

    async def delete(self, obj: ModelT) -> None:
        """
        Deleção física — remove o registro permanentemente.

        ATENÇÃO: para models com SoftDeleteMixin, prefira soft_delete():
            obj.soft_delete()
            await session.flush()
        Use este método apenas para dados temporários ou em cascata.
        """
        await self.session.delete(obj)
        await self.session.flush()
