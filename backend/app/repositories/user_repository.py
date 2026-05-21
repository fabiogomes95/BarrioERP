"""
app/repositories/user_repository.py

Repository de usuários — todas as queries relacionadas à tabela `users`.

CONCEITO — Repository específico:
    O BaseRepository tem o CRUD genérico (get, list, add, delete).
    O UserRepository adiciona queries específicas do domínio User.

    Regra: se você está escrevendo SQL (ou equivalente SQLAlchemy) fora de
    um repository, você está violando o Repository Pattern.

CONCEITO — Queries SQLAlchemy explicadas:
    select(User)                    → SELECT * FROM users
    .where(User.email == email)     → WHERE email = 'valor'
    .where(User.deleted_at.is_(None)) → WHERE deleted_at IS NULL
    result.scalar_one_or_none()     → retorna um objeto ou None
"""

from uuid import UUID

from sqlalchemy import select

from app.models.user import User
from app.repositories.base import BaseRepository


class UserRepository(BaseRepository[User]):
    """
    Repository de usuários.

    Herda todo o CRUD de BaseRepository[User].
    Adiciona queries específicas de User.
    """

    model = User  # informa ao BaseRepository com qual tabela trabalhar

    async def get_by_email(self, email: str) -> User | None:
        """
        Busca um usuário ativo pelo e-mail.

        Usada no login: o usuário informa o e-mail, buscamos no banco.

        NOTA MULTI-TENANT:
        E-mails são únicos POR EMPRESA (constraint: company_id + email).
        O mesmo e-mail pode existir em empresas diferentes.
        Esta query retorna o PRIMEIRO usuário ativo com aquele e-mail.

        Em uma implementação futura, o login incluirá company_slug para
        identificar exatamente qual empresa o usuário pertence.

        QUERY GERADA:
            SELECT * FROM users
            WHERE email = :email
              AND is_active = TRUE
              AND deleted_at IS NULL
            LIMIT 1
        """
        stmt = (
            select(User)
            .where(
                User.email == email,
                User.is_active.is_(True),       # só usuários ativos
                User.deleted_at.is_(None),       # não deletados (soft delete)
            )
        )
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()
        # scalar_one_or_none() → retorna o objeto User, ou None se não encontrar
        # scalar_one()         → retorna o objeto, ou LANÇA EXCEÇÃO se não encontrar
        # Preferimos scalar_one_or_none() aqui — ausência é esperada (e-mail errado)

    async def get_by_email_and_company(self, email: str, company_id: UUID) -> User | None:
        """
        Busca um usuário pelo e-mail dentro de uma empresa específica.

        Mais preciso que get_by_email() quando sabemos o company_id.
        Útil para endpoints internos onde o contexto do tenant já está definido.

        QUERY GERADA:
            SELECT * FROM users
            WHERE email = :email
              AND company_id = :company_id
              AND deleted_at IS NULL
        """
        stmt = (
            select(User)
            .where(
                User.email == email,
                User.company_id == company_id,
                User.deleted_at.is_(None),
            )
        )
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def list_by_company(
        self,
        company_id: UUID,
        *,
        active_only: bool = True,
        limit: int = 20,
        offset: int = 0,
    ) -> list[User]:
        """
        Lista usuários de uma empresa com paginação.

        O * (asterisk) nos parâmetros significa que tudo após ele
        deve ser passado como keyword argument:
            await repo.list_by_company(company_id, active_only=True, limit=20)

        QUERY GERADA (com active_only=True):
            SELECT * FROM users
            WHERE company_id = :company_id
              AND is_active = TRUE
              AND deleted_at IS NULL
            ORDER BY name
            LIMIT 20 OFFSET 0
        """
        filters = [
            User.company_id == company_id,
            User.deleted_at.is_(None),
        ]
        if active_only:
            filters.append(User.is_active.is_(True))

        return await self.list(
            *filters,
            limit=limit,
            offset=offset,
            order_by=User.name,  # ordenado por nome — previsível para o usuário
        )
