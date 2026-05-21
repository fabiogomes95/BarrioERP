"""
app/services/table_service.py

Regras de negócio para o módulo de mesas.

═══════════════════════════════════════════════════════════════
CONCEITO — O que é a camada de Service?
═══════════════════════════════════════════════════════════════

O Service é o CORAÇÃO da aplicação — onde ficam as regras de negócio.

Analogia: é o GERENTE DO RESTAURANTE.
    - O garçom (endpoint) recebe o pedido do cliente
    - O gerente (service) decide se o pedido faz sentido e o executa
    - O almoxarife (repository) busca/salva os dados no banco

O que o Service FAZ:
    ✓ Verifica regras de negócio ("mesa ocupada não pode ser desativada")
    ✓ Orquestra múltiplos repositories ("cria mesa, registra no audit log")
    ✓ Converte Models em Schemas para retornar ao endpoint
    ✓ Lança exceções de domínio (NotFoundError, BusinessRuleError, etc.)

O que o Service NÃO faz:
    ✗ Faz SQL diretamente (isso é o Repository)
    ✗ Formata respostas HTTP com status codes (isso é o endpoint/handler)
    ✗ Valida tipos de dados (isso é o Pydantic/Schema)

═══════════════════════════════════════════════════════════════
CONCEITO — Por que o endpoint não acessa o banco diretamente?
═══════════════════════════════════════════════════════════════

Você poderia escrever toda a lógica no endpoint:

    @router.post("/tables")
    async def create(data, session, current_user):
        existing = await session.execute(
            select(Table).where(Table.number == data.number, ...)
        )
        if existing.scalar_one_or_none():
            raise ConflictError(...)
        table = Table(...)
        session.add(table)
        await session.flush()
        return TableResponse.model_validate(table)

Funciona? Sim. Mas quando você tiver 20 endpoints e 5 regras em cada,
o código vira um caos. Problemas:
    1. DUPLICAÇÃO: a mesma lógica de "verificar número único" vai aparecer
       em múltiplos lugares
    2. TESTABILIDADE: testar endpoints requer subir o servidor HTTP
       Testar o service é só chamar um método Python
    3. REUTILIZAÇÃO: se amanhã um job assíncrono precisar criar mesas,
       ele não pode usar o endpoint — mas pode usar o Service diretamente

O Service torna o código ORGANIZADO, TESTÁVEL e REUTILIZÁVEL.

═══════════════════════════════════════════════════════════════
CONCEITO — "Soft delete" via is_active vs SoftDeleteMixin
═══════════════════════════════════════════════════════════════

Existem duas formas de "deletar sem deletar" no BarrioERP:

1. SoftDeleteMixin (ex: User):
    - Tem coluna `deleted_at: datetime | None`
    - Quando "deletado": deleted_at = now()
    - Quando ativo: deleted_at = None
    - Motivo: precisamos saber QUANDO o usuário foi deletado (auditoria)

2. is_active (ex: Table):
    - Tem coluna `is_active: bool`
    - Quando desativado: is_active = False
    - Quando ativo: is_active = True
    - Motivo: mesa pode ser REATIVADA facilmente, sem timestamp específico

O "DELETE /tables/{id}" neste módulo faz um SOFT DELETE via is_active:
    table.is_active = False  → mesa desaparece da listagem
    O registro continua no banco para histórico de comandas.

Por que não deletar fisicamente?
    Se deletarmos uma mesa com comandas históricas, perdemos o histórico!
    O pedido do dia 3/3 ficaria sem mesa associada — dados corrompidos.
    Soft delete preserva a integridade referencial da história.
"""

from uuid import UUID

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm.exc import StaleDataError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import (
    BusinessRuleError,
    ConflictError,
    NotFoundError,
    OptimisticLockError,
    TenantError,
)
from app.models.table import Table, TableStatus
from app.repositories.table_repository import TableRepository
from app.schemas.common import PaginatedResponse
from app.schemas.table import TableCreate, TableResponse, TableUpdate
from app.services.base import BaseService


class TableService(BaseService):
    """
    Service de mesas — orquestra criação, listagem, edição e desativação.

    Herda de BaseService, que armazena:
        self.session         → sessão do banco (injetada pelo endpoint)
        self.company_id      → empresa do usuário logado (do JWT)
        self.establishment_id → estabelecimento do usuário logado (do JWT)
        self.user_id         → ID do usuário logado (para audit logs futuros)

    O TableService também instancia o TableRepository internamente.
    O Repository recebe a mesma sessão — assim eles compartilham a mesma
    transação. Se qualquer operação falhar, tudo é revertido junto.
    """

    def __init__(
        self,
        session: AsyncSession,
        company_id: UUID,
        establishment_id: UUID | None = None,
        user_id: UUID | None = None,
    ) -> None:
        super().__init__(session, company_id, establishment_id, user_id)
        # Criamos o Repository com a mesma sessão — mesma transação
        self._repo = TableRepository(session)

    # ── Helpers ──────────────────────────────────────────────────────────────

    def _require_establishment(self) -> UUID:
        """
        Garante que o usuário logado está vinculado a um estabelecimento.

        Por que isso é necessário?
            O campo `establishment_id` no User é NULLABLE (pode ser None).
            Um usuário do tipo OWNER pode gerenciar a empresa sem estar
            vinculado a um estabelecimento específico.

            Mas para LISTAR ou CRIAR mesas, precisamos saber QUAL estabelecimento.
            Se não tiver, o Service não sabe de que estabelecimento estamos falando.

        LANÇA: TenantError (HTTP 400) se establishment_id for None.
        RETORNA: establishment_id como UUID se estiver definido.
        """
        if self.establishment_id is None:
            raise TenantError(
                "Este usuário não está vinculado a um estabelecimento. "
                "Vincule o usuário a um estabelecimento para gerenciar mesas."
            )
        return self.establishment_id

    # ── Operações CRUD ────────────────────────────────────────────────────────

    async def create(self, data: TableCreate) -> TableResponse:
        """
        Cria uma nova mesa no estabelecimento do usuário logado.

        FLUXO COMPLETO:
            1. Verifica que o usuário tem um estabelecimento → _require_establishment()
            2. Verifica se o número da mesa já existe → ConflictError se sim
            3. Cria o objeto Table em memória
            4. Persiste no banco via repository.add() (flush + refresh)
            5. Converte o Model para Schema → TableResponse
            6. O commit acontece AUTOMATICAMENTE em get_db() quando o endpoint retorna

        POR QUE NÃO DEFINIMOS `status` no TableCreate?
            Status FREE é a única opção ao criar uma mesa.
            Uma mesa nova nunca pode ser criada já OCCUPIED ou BLOCKED.
            Isso é uma REGRA DE NEGÓCIO — o Service a aplica.
            Se déssemos ao cliente a opção de definir o status inicial,
            poderíamos ter mesas "ocupadas" sem nenhuma comanda. Inconsistente.

        TRATAMENTO DE RACE CONDITION:
            Dois requests simultâneos tentando criar mesa número 5:
            1. Ambos passam pela verificação get_by_number() (retorna None para ambos)
            2. Ambos tentam fazer o INSERT
            3. O segundo vai falhar com IntegrityError (índice único no banco)
            4. Nós capturamos e convertemos em ConflictError amigável

        RETORNA: TableResponse com todos os dados da mesa recém-criada.
        """
        establishment_id = self._require_establishment()

        # Verifica unicidade de número antes de tentar inserir
        existing = await self._repo.get_by_number(data.number, establishment_id)
        if existing is not None:
            raise ConflictError(
                f"Já existe uma mesa com o número {data.number} neste estabelecimento."
            )

        table = Table(
            establishment_id=establishment_id,
            number=data.number,
            label=data.label,
            capacity=data.capacity,
            section=data.section,
            status=TableStatus.FREE,   # regra de negócio: sempre começa FREE
            is_active=True,
        )

        try:
            table = await self._repo.add(table)
        except IntegrityError:
            # Race condition: dois requests simultâneos passaram pela verificação
            # mas o banco rejeitou o segundo via índice único
            raise ConflictError(
                f"Número {data.number} já está em uso neste estabelecimento."
            )

        return TableResponse.model_validate(table)

    async def list(
        self,
        *,
        status: TableStatus | None = None,
        page: int = 1,
        page_size: int = 50,
    ) -> PaginatedResponse:
        """
        Lista mesas do estabelecimento com paginação e filtro opcional.

        PAGINAÇÃO:
            page=1, page_size=50 → LIMIT 50 OFFSET 0  (primeiras 50 mesas)
            page=2, page_size=50 → LIMIT 50 OFFSET 50 (próximas 50 mesas)

            A fórmula: offset = (page - 1) * page_size

        FILTRO POR STATUS:
            GET /tables?status=free    → só mesas livres
            GET /tables?status=occupied → só mesas ocupadas
            GET /tables              → todas as mesas ativas

        RETORNA: PaginatedResponse com:
            - items: lista de TableResponse
            - total: total de mesas (para o cliente calcular páginas)
            - page/page_size/pages: metadados de paginação
        """
        establishment_id = self._require_establishment()
        offset = (page - 1) * page_size

        tables = await self._repo.list_by_establishment(
            establishment_id,
            status=status,
            limit=page_size,
            offset=offset,
        )
        total = await self._repo.count_by_establishment(establishment_id)
        pages = max(1, (total + page_size - 1) // page_size)  # arredonda para cima

        return PaginatedResponse(
            items=[TableResponse.model_validate(t) for t in tables],
            total=total,
            page=page,
            page_size=page_size,
            pages=pages,
        )

    async def get(self, table_id: UUID) -> TableResponse:
        """
        Retorna os dados de uma mesa específica.

        MULTI-TENANCY:
            get_by_establishment() só retorna a mesa se ela pertencer
            ao estabelecimento do usuário logado.
            Se o table_id pertence a outro restaurante → NotFoundError.
            O cliente não sabe que a mesa existe — apenas que não foi encontrada.

        RETORNA: TableResponse com todos os dados da mesa.
        LANÇA: NotFoundError (HTTP 404) se não existir ou for de outro tenant.
        """
        establishment_id = self._require_establishment()
        table = await self._repo.get_by_establishment(table_id, establishment_id)

        if table is None:
            raise NotFoundError("Table", table_id)

        return TableResponse.model_validate(table)

    async def update(self, table_id: UUID, data: TableUpdate) -> TableResponse:
        """
        Atualiza campos de uma mesa existente.

        CONCEITO — PATCH parcial com model_dump(exclude_unset=True):
            Quando o cliente manda:
                {"label": "Mesa 2 Reformada", "version": 3}

            data.model_dump(exclude_unset=True) retorna:
                {"label": "Mesa 2 Reformada", "version": 3}
                ↑ só os campos que foram EXPLICITAMENTE enviados

            Se o cliente não mandou "capacity", não está no dict.
            Então fazemos: setattr(table, field, value) só para esses campos.
            O campo `version` é pulado (é só para locking, não armazena).

            Isso permite:
            - Atualizar só o label sem tocar no status
            - Limpar o section com {"section": null, "version": 5}
            - Alterar o status com {"status": "occupied", "version": 5}

        CONCEITO — Locking Otimista (Optimistic Locking):
            O fluxo seguro de edição é:
            1. GET /tables/uuid → recebe a mesa com version=3
            2. Usuário edita na interface
            3. PATCH /tables/uuid com {"label": "...", "version": 3}
            4. Service compara: data.version (3) == table.version (3) → OK
            5. Atualiza. O banco incrementa version para 4 automaticamente.

            Se outro usuário editou no meio do caminho (version virou 4):
            4. Service compara: data.version (3) ≠ table.version (4) → CONFLITO
            5. Lança OptimisticLockError (HTTP 409)
            6. Cliente recebe: "Mesa foi modificada. Recarregue e tente novamente."

        LANÇA:
            NotFoundError (404) → mesa não existe ou é de outro tenant
            BusinessRuleError (422) → mesa está desativada
            OptimisticLockError (409) → conflito de versão
        """
        establishment_id = self._require_establishment()
        table = await self._repo.get_by_establishment(table_id, establishment_id)

        if table is None:
            raise NotFoundError("Table", table_id)

        if not table.is_active:
            raise BusinessRuleError(
                "Não é possível editar uma mesa desativada. Reative-a primeiro."
            )

        # Verificação de versão ANTES de aplicar mudanças
        if table.version != data.version:
            raise OptimisticLockError("Table")

        # Aplica apenas os campos que foram enviados na requisição
        # exclude_unset=True → campos ausentes no JSON não são incluídos
        # Assim {"label": "x", "version": 3} só altera label, não capacity nem status
        update_data = data.model_dump(exclude_unset=True)
        update_data.pop("version", None)  # version é controle, não dado

        for field, value in update_data.items():
            setattr(table, field, value)

        try:
            await self.session.flush()
        except StaleDataError:
            # O VersionMixin do SQLAlchemy detectou conflito de versão no banco
            # Isso cobre o caso de race condition que passou pela verificação manual
            raise OptimisticLockError("Table")

        await self.session.refresh(table)
        return TableResponse.model_validate(table)

    async def deactivate(self, table_id: UUID) -> None:
        """
        Desativa uma mesa (soft delete via is_active = False).

        SOFT DELETE — por que não deletar fisicamente?
            DELETE FROM tables WHERE id = ?  → PERMANENTE, PERIGOSO
            table.is_active = False          → suave, reversível

            Problemas com deleção física:
            1. Pedidos históricos perdem a referência à mesa
            2. Logs e relatórios ficam com dados inconsistentes
            3. A mesa simplesmente "desaparece" sem rastro

            Com is_active = False:
            - A mesa some da listagem normal (active_only=True por padrão)
            - Os dados históricos continuam intactos
            - Um admin pode REATIVAR a mesa no futuro
            - "Onde foi a Mesa 5?" tem uma resposta clara: foi desativada

        REGRA DE NEGÓCIO:
            Uma mesa com status OCCUPIED pode ter uma comanda aberta.
            Desativar nesse momento deixaria o garçom sem referência para fechar.
            Por isso bloqueamos a desativação de mesas OCCUPIED.

            Mesas em BILL_REQUESTED, RESERVED, BLOCKED podem ser desativadas
            porque não têm comandas em aberto (apenas sinalizações de estado).

        LANÇA:
            NotFoundError (404) → mesa não existe ou é de outro tenant
            BusinessRuleError (422) → mesa já desativada ou está OCCUPIED
        """
        establishment_id = self._require_establishment()
        table = await self._repo.get_by_establishment(table_id, establishment_id)

        if table is None:
            raise NotFoundError("Table", table_id)

        if not table.is_active:
            raise BusinessRuleError("Esta mesa já está desativada.")

        if table.status == TableStatus.OCCUPIED:
            raise BusinessRuleError(
                "Não é possível desativar uma mesa com comanda aberta. "
                "Feche a comanda antes de desativar a mesa."
            )

        table.is_active = False
        await self.session.flush()
        # Não é necessário session.refresh() aqui — o endpoint retorna 204 (sem body)
