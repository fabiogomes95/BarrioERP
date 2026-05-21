"""
app/services/base.py

Service base com contexto de tenant (empresa ativa).

CONCEITO — Service Layer:
    O Service contém as REGRAS DE NEGÓCIO. Exemplos:
    - "Um usuário só pode logar se estiver ativo"
    - "Uma mesa só pode ter uma comanda aberta por vez"
    - "O total da comanda deve ser recalculado ao adicionar um item"

    O Service NÃO:
    - Fala diretamente com o banco (isso é o Repository)
    - Formata respostas HTTP (isso é o endpoint)
    - Valida tipos de dados (isso é o Pydantic/Schema)

CONCEITO — Multi-tenancy no Service:
    Em um SaaS, toda operação pertence a uma empresa (Company).
    Ao injetar company_id no Service, garantimos que nenhuma query
    acidentalmente retorne dados de outro restaurante.

    O company_id vem do JWT token do usuário logado.
"""

from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession


class BaseService:
    """
    Serviço base com contexto de tenant.

    Todos os services de negócio herdam desta classe.
    O contexto (company_id, establishment_id, user_id) fica disponível
    em todos os métodos via self.company_id, etc.

    EXEMPLO DE USO:
        class OrderService(BaseService):
            async def list_open_orders(self):
                # self.company_id já está disponível — vem do JWT
                return await self.order_repo.list(
                    Order.company_id == self.company_id,
                    Order.status == OrderStatus.OPEN,
                )
    """

    def __init__(
        self,
        session: AsyncSession,
        company_id: UUID,
        establishment_id: UUID | None = None,
        user_id: UUID | None = None,
    ) -> None:
        self.session = session
        self.company_id = company_id
        self.establishment_id = establishment_id
        self.user_id = user_id  # quem está executando a ação (para audit logs)
