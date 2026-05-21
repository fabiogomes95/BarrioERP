"""
app/repositories/table_repository.py

Acesso ao banco para o modelo Table.

═══════════════════════════════════════════════════════════════
CONCEITO — O que é um Repository?
═══════════════════════════════════════════════════════════════

O Repository é a camada que FALA COM O BANCO DE DADOS.
Ele é o único lugar onde escrevemos SQL (via SQLAlchemy).

Analogia: pensa no Repository como um ALMOXARIFADO.
    - O Service (chefe de cozinha) pede: "me dá as mesas da área externa"
    - O Repository (almoxarife) sabe onde está tudo no estoque e entrega
    - O Service não sabe se as mesas estão em PostgreSQL, MySQL ou Redis

Por que essa separação importa?
    1. MANUTENÇÃO: SQL centralizado — fácil de encontrar bugs de query
    2. TESTABILIDADE: para testes unitários, você pode substituir o Repository
       por um mock sem precisar de banco de dados
    3. REUTILIZAÇÃO: dois Services podem usar o mesmo Repository sem duplicar SQL
    4. MUDANÇA DE BANCO: se precisar trocar PostgreSQL por outro banco,
       só o Repository muda — Service e API continuam iguais

═══════════════════════════════════════════════════════════════
CONCEITO — Como o SQLAlchemy constrói queries?
═══════════════════════════════════════════════════════════════

SQLAlchemy usa uma API fluente (method chaining) para construir SQL:

    select(Table)
        .where(Table.establishment_id == uuid)
        .where(Table.is_active.is_(True))
        .order_by(Table.number)
        .limit(50)

    Isso gera o SQL:
    SELECT * FROM tables
    WHERE establishment_id = '...'
      AND is_active = true
    ORDER BY number
    LIMIT 50

Benefícios sobre SQL raw (strings):
    - Type-safe: o editor detecta erros de digitação nos nomes de colunas
    - Composable: você pode adicionar filtros condicionalmente com .where()
    - Seguro: parâmetros são sempre escapados (sem SQL injection)

═══════════════════════════════════════════════════════════════
CONCEITO — Multi-tenancy neste Repository
═══════════════════════════════════════════════════════════════

Multi-tenancy significa "múltiplos clientes no mesmo sistema".
No BarrioERP, cada restaurante é um tenant (inquilino).

A regra é: uma mesa pertence a um establishment_id.
O garçom do Restaurante A jamais deve ver as mesas do Restaurante B.

COMO GARANTIMOS ISSO?
    Toda query de mesa inclui: WHERE establishment_id = ?
    O establishment_id vem do JWT do usuário logado.

    Mesmo que o cliente mande um table_id de outro restaurante,
    a query retorna None (não encontrado) — não há vazamento de dados.

Esta função faz exatamente isso:
    async def get_by_establishment(table_id, establishment_id):
        SELECT * FROM tables
        WHERE id = table_id AND establishment_id = establishment_id
        ↑ ambos os filtros garantem isolamento
"""

from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.table import Table, TableStatus
from app.repositories.base import BaseRepository


class TableRepository(BaseRepository[Table]):
    """
    Repository para operações com mesas.

    Herda de BaseRepository[Table], que fornece operações CRUD genéricas:
        get()           → busca por PK (usa identity map — eficiente)
        get_or_raise()  → busca por PK, lança NotFoundError se não existir
        list()          → busca com filtros, limit e offset
        count()         → conta registros para paginação
        add()           → INSERT + flush + refresh (retorna objeto atualizado)
        delete()        → DELETE físico (cuidado: irreversível!)

    Aqui adicionamos queries específicas de Table que o BaseRepository
    não consegue expressar de forma genérica.
    """

    model = Table  # informa ao BaseRepository qual model gerenciar

    async def list_by_establishment(
        self,
        establishment_id: UUID,
        *,
        active_only: bool = True,
        status: TableStatus | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> list[Table]:
        """
        Lista mesas de um estabelecimento com filtros opcionais.

        PARÂMETROS:
            establishment_id → isola ao tenant correto (multi-tenancy)
            active_only      → se True, exclui mesas desativadas (is_active=False)
            status           → filtra por status específico (ex: só mesas livres)
            limit/offset     → paginação (ex: limit=50, offset=0 → página 1)

        RETORNA: lista de objetos Table ordenados pelo número da mesa.

        A ordenação por `number` é importante para o garçom:
        mesas aparecem na ordem natural (1, 2, 3...) na interface.

        Por que o `*` nos argumentos?
            O * força que limit, offset, active_only e status sejam
            passados como argumentos nomeados, não posicionais.
            Isso evita erros de ordem: list_by_establishment(id, True, "free")
            fica claro como: list_by_establishment(id, active_only=True, status="free")
        """
        filters = [Table.establishment_id == establishment_id]

        if active_only:
            filters.append(Table.is_active.is_(True))

        if status is not None:
            filters.append(Table.status == status)

        # Usamos o list() do BaseRepository com os filtros construídos acima
        return await self.list(
            *filters,
            limit=limit,
            offset=offset,
            order_by=Table.number,
        )

    async def count_by_establishment(
        self,
        establishment_id: UUID,
        *,
        active_only: bool = True,
    ) -> int:
        """
        Conta mesas de um estabelecimento.

        Usado para calcular paginação:
            total = 47 mesas
            page_size = 20
            pages = ceil(47 / 20) = 3 páginas

        Por que fazer 2 queries (list + count) em vez de 1?
            Uma única query com COUNT e dados ao mesmo tempo é possível,
            mas mais complexa de implementar e raramente vale a pena.
            O banco é rápido para COUNT(*) com índice — o custo é baixo.
        """
        filters = [Table.establishment_id == establishment_id]

        if active_only:
            filters.append(Table.is_active.is_(True))

        return await self.count(*filters)

    async def get_by_establishment(
        self,
        table_id: UUID,
        establishment_id: UUID,
    ) -> Table | None:
        """
        Busca uma mesa pelo ID, garantindo que pertence ao estabelecimento.

        MULTI-TENANCY EM AÇÃO:
            Mesmo que o cliente mande o ID de uma mesa de outro restaurante,
            a cláusula `establishment_id == establishment_id` vai retornar None.
            O Service vai lançar NotFoundError — como se a mesa não existisse.

            Isso é deliberado: não revelamos que a mesa existe, só que
            o usuário não tem acesso. Comportamento mais seguro.

        Por que não usar BaseRepository.get(table_id) diretamente?
            get() busca só por PK (id), sem verificar establishment_id.
            Uma mesa de outro restaurante seria retornada!
            get_by_establishment() adiciona a verificação de tenant.

        RETORNA: Table se encontrada e pertence ao tenant, None caso contrário.
        """
        stmt = (
            select(Table)
            .where(
                Table.id == table_id,
                Table.establishment_id == establishment_id,
            )
        )
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def get_by_number(
        self,
        number: int,
        establishment_id: UUID,
    ) -> Table | None:
        """
        Busca uma mesa pelo número dentro de um estabelecimento.

        Usado para verificar UNICIDADE antes de criar uma nova mesa:
            Se número 5 já existe → ConflictError (409)
            Se não existe → pode criar

        O banco também garante unicidade via índice único:
            ix_tables_establishment_number (establishment_id, number)

        Por que verificar no código E no banco?
            - A verificação no código dá uma mensagem de erro amigável
            - O índice do banco é a garantia final (race condition safety)
            - Se dois requests chegarem ao mesmo tempo, só um vai passar.
              O segundo vai receber um IntegrityError que o Service converte
              em ConflictError antes de chegar ao cliente.
        """
        stmt = (
            select(Table)
            .where(
                Table.number == number,
                Table.establishment_id == establishment_id,
            )
        )
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()
