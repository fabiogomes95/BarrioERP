"""
app/repositories/user_repository.py

Repository de usuários — todas as queries relacionadas à tabela `users`.

═══════════════════════════════════════════════════════════════
CONCEITO — Repository Pattern
═══════════════════════════════════════════════════════════════

O Repository é o único lugar do sistema que escreve SQL (ou SQLAlchemy
equivalente). Nenhuma outra camada deve construir queries diretamente.

Por que isso importa?
  - Se o esquema do banco mudar, você muda o Repository e só ele.
  - Os Services focam em regras de negócio, não em sintaxe SQL.
  - Fica fácil testar a lógica de negócio com um Repository mockado.

HIERARQUIA:
  BaseRepository[User]     → CRUD genérico (get, list, add, delete, count)
      └── UserRepository   → queries específicas do domínio User

═══════════════════════════════════════════════════════════════
CONCEITO — Multi-tenancy no Repository
═══════════════════════════════════════════════════════════════

Em um SaaS, cada query de busca por recurso deve filtrar por company_id.

Exemplo de falha:
    user = await repo.get(user_id)  ← BaseRepository.get — só filtra por PK!
    # Um atacante com um UUID de outro restaurante obteria os dados.

Exemplo correto:
    user = await repo.get_by_company(user_id, company_id)
    # Filtra por ID *e* company_id — dados de outro tenant retornam None.

A regra: nunca use BaseRepository.get() diretamente para recursos
que pertencem a um tenant. Sempre crie um método _by_company no repo.
"""

from uuid import UUID

from sqlalchemy import func, select

from app.models.user import User, UserRole
from app.repositories.base import BaseRepository


class UserRepository(BaseRepository[User]):
    """
    Repository de usuários.

    Herda todo o CRUD de BaseRepository[User]:
        get(id)             → busca por PK (use get_by_company em vez disso)
        get_or_raise(id)    → busca por PK ou lança NotFoundError
        list(*filters)      → lista com filtros genéricos
        count(*filters)     → conta registros
        add(obj)            → INSERT + flush + refresh
        delete(obj)         → DELETE físico (não use — prefira soft_delete)

    Métodos específicos deste repositório estão abaixo.
    """

    model = User  # informa ao BaseRepository qual Model gerenciar

    # ══════════════════════════════════════════════════════════════════════
    # MÉTODOS HERDADOS DO MÓDULO AUTH
    # Criados originalmente para servir o AuthService (login).
    # Permanecem aqui porque são reutilizados pelo UserService.
    # ══════════════════════════════════════════════════════════════════════

    async def get_by_email(self, email: str) -> User | None:
        """
        Busca um usuário ativo pelo e-mail, sem filtro de empresa.

        USO PRINCIPAL: login — o usuário informa o e-mail antes de
        sabermos a qual empresa pertence.

        CUIDADO — multi-tenancy:
        E-mails são únicos POR EMPRESA (constraint: company_id + email).
        O mesmo endereço pode existir em duas empresas diferentes.
        Esta query retorna o primeiro usuário ativo encontrado com aquele e-mail.

        Isso é aceitável no login porque, em breve, o fluxo incluirá o
        company_slug no payload (o usuário diz "entro no restaurante X com
        este e-mail"), tornando a busca precisa. Por ora, funciona para
        o cenário comum de e-mails únicos globalmente.

        QUERY GERADA:
            SELECT * FROM users
            WHERE email = :email
              AND is_active = TRUE
              AND deleted_at IS NULL
        """
        stmt = (
            select(User)
            .where(
                User.email == email,
                User.is_active.is_(True),    # apenas usuários habilitados
                User.deleted_at.is_(None),   # não soft-deletados
            )
        )
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()
        # scalar_one_or_none() → retorna objeto ou None (ausência é esperada aqui)
        # scalar_one()         → retorna objeto ou lança NoResultFound (não queremos isso)

    async def get_by_email_and_company(
        self,
        email: str,
        company_id: UUID,
    ) -> User | None:
        """
        Busca um usuário pelo e-mail dentro de uma empresa específica.

        Mais preciso que get_by_email() quando o contexto do tenant é
        conhecido. Usado no UserService para verificar unicidade de
        e-mail ao criar ou atualizar usuário.

        NÃO filtra por is_active — retorna usuários inativos também,
        pois um e-mail "ocupado" por usuário inativo ainda não pode
        ser reutilizado (evita confusão histórica nos logs de auditoria).

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
                User.deleted_at.is_(None),   # exclui soft-deletados
            )
        )
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def list_by_company(
        self,
        company_id: UUID,
        *,
        active_only: bool = True,
        role: UserRole | None = None,
        establishment_id: UUID | None = None,
        limit: int = 20,
        offset: int = 0,
    ) -> list[User]:
        """
        Lista usuários de uma empresa com filtros opcionais e paginação.

        PARÂMETROS KEYWORD-ONLY (após o *):
        O asterisco * força todos os parâmetros seguintes a serem passados
        como keyword argument. Isso evita bugs por posição errada:

            # Sem *: chamada ambígua
            await repo.list_by_company(cid, True, None, None, 20, 0)

            # Com *: chamada explícita e legível
            await repo.list_by_company(cid, active_only=True, role=UserRole.WAITER)

        FILTROS IMPLEMENTADOS:
            active_only=True      → WHERE is_active = TRUE (padrão)
            role=UserRole.WAITER  → WHERE role = 'waiter'
            establishment_id=uuid → WHERE establishment_id = :id

        FILTROS COMBINADOS:
            Os filtros são construídos dinamicamente.
            Somente os filtros não-None são adicionados à query.
            Isso é chamado de "query builder pattern".

        QUERY GERADA (exemplo com todos os filtros):
            SELECT * FROM users
            WHERE company_id = :company_id
              AND deleted_at IS NULL
              AND is_active = TRUE
              AND role = 'waiter'
              AND establishment_id = :establishment_id
            ORDER BY name
            LIMIT 20 OFFSET 0
        """
        # Começa com os filtros base — sempre aplicados
        filters = [
            User.company_id == company_id,
            User.deleted_at.is_(None),    # nunca inclui soft-deletados na listagem
        ]

        # Adiciona filtros opcionais apenas se fornecidos
        if active_only:
            # active_only=True é o padrão: garçons e gerentes só veem equipe ativa
            # active_only=False: admin vê todos (inclusive desativados)
            filters.append(User.is_active.is_(True))

        if role is not None:
            # Filtra por cargo específico
            # Útil para: "liste todos os garçons", "liste todos os gerentes"
            filters.append(User.role == role)

        if establishment_id is not None:
            # Filtra por filial específica
            # Útil para: "liste todos os funcionários desta unidade"
            filters.append(User.establishment_id == establishment_id)

        # Delega para BaseRepository.list() que monta o SELECT com limit/offset
        return await self.list(
            *filters,             # desempacota a lista de filtros como argumentos
            limit=limit,
            offset=offset,
            order_by=User.name,   # ordenado por nome alfabético — consistente e previsível
        )

    # ══════════════════════════════════════════════════════════════════════
    # NOVOS MÉTODOS — necessários para o CRUD completo de Users
    # ══════════════════════════════════════════════════════════════════════

    async def get_by_company(
        self,
        user_id: UUID,
        company_id: UUID,
    ) -> User | None:
        """
        Busca um usuário pelo ID garantindo que pertence à empresa correta.

        ESTE É O MÉTODO QUE O SERVICE DEVE USAR ao buscar usuário por ID.
        Nunca use BaseRepository.get(user_id) diretamente em contexto
        multi-tenant — ele retorna qualquer usuário, independente do tenant.

        POR QUE ISSO É UMA VULNERABILIDADE?
        Imagine o endpoint GET /users/{user_id}.
        Um atacante autenticado no Restaurante A faz:
            GET /users/uuid-de-um-funcionario-do-Restaurante-B

        Se usarmos BaseRepository.get(user_id):
            → Retorna o funcionário do Restaurante B → vazamento de dados.

        Se usarmos get_by_company(user_id, company_id_do_atacante):
            → Retorna None (UUID não pertence a esta empresa)
            → Service converte em NotFoundError → HTTP 404
            → O atacante não sabe se o usuário existe ou não.

        Esse padrão de segurança se chama "tenant isolation" ou
        "row-level security at application layer".

        QUERY GERADA:
            SELECT * FROM users
            WHERE id = :user_id
              AND company_id = :company_id
              AND deleted_at IS NULL
        """
        stmt = (
            select(User)
            .where(
                User.id == user_id,
                User.company_id == company_id,
                User.deleted_at.is_(None),    # não retorna soft-deletados
            )
        )
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def count_active_owners(self, company_id: UUID) -> int:
        """
        Conta quantos usuários com role OWNER estão ativos na empresa.

        PROPÓSITO — Proteção do "último owner":
        Se uma empresa tem apenas 1 OWNER e ele for desativado ou deletado,
        ninguém terá mais permissão de administrar o sistema. O restaurante
        fica órfão — sem acesso de nível administrativo via API.

        O UserService chama este método ANTES de:
          - Desativar um OWNER (PATCH is_active=False)
          - Deletar um OWNER (DELETE /users/{id})
          - Rebaixar um OWNER para outro role (PATCH role=manager)

        LÓGICA NO SERVICE (antecipando a etapa 3):
            count = await repo.count_active_owners(company_id)
            if count <= 1 and operacao_afeta_o_ultimo_owner:
                raise BusinessRuleError("Cannot remove the last owner")

        POR QUE NÃO VERIFICAR ISSO NO ENDPOINT?
        A regra de negócio pertence ao Service, não ao endpoint.
        O endpoint não deve conhecer a lógica de "último owner".
        O endpoint apenas repassa os dados e recebe a resposta.

        QUERY GERADA:
            SELECT COUNT(*) FROM users
            WHERE company_id = :company_id
              AND role = 'owner'
              AND is_active = TRUE
              AND deleted_at IS NULL
        """
        stmt = (
            select(func.count())           # SELECT COUNT(*)
            .select_from(User)             # FROM users
            .where(
                User.company_id == company_id,
                User.role == UserRole.OWNER,  # apenas owners
                User.is_active.is_(True),     # apenas ativos
                User.deleted_at.is_(None),    # não soft-deletados
            )
        )
        result = await self.session.execute(stmt)
        return result.scalar_one()
        # scalar_one() aqui é seguro — COUNT(*) sempre retorna exatamente 1 linha

    async def email_taken_in_company(
        self,
        email: str,
        company_id: UUID,
        *,
        exclude_user_id: UUID | None = None,
    ) -> bool:
        """
        Verifica se um e-mail já está em uso na empresa.

        Retorna True se o e-mail está ocupado, False se está disponível.

        DOIS CASOS DE USO:

        1. Criação de usuário (exclude_user_id=None):
            Verifica se o e-mail já existe na empresa.
            "Existe alguém com este e-mail? Sim → conflito. Não → pode criar."

        2. Atualização de usuário (exclude_user_id=uuid):
            Verifica se o e-mail pertence a OUTRO usuário da empresa.
            "Existe alguém COM ESTE E-MAIL que NÃO É o usuário sendo editado?"

            Por que o exclude_user_id é necessário na atualização?
            Sem ele, editar um usuário sem mudar o e-mail sempre retornaria
            "e-mail já cadastrado" (o próprio usuário tem esse e-mail!).

        EXEMPLO (atualização):
            Usuário A: id=111, email=joao@bar.com
            Usuário B: id=222, email=maria@bar.com

            PATCH /users/111 → {"email": "joao@bar.com"}   (sem mudança)
            email_taken_in_company("joao@bar.com", cid, exclude_user_id=111)
            → Busca: email=joao@bar.com AND company_id=cid AND id != 111
            → Resultado: nenhum outro usuário tem este e-mail → False → OK

            PATCH /users/111 → {"email": "maria@bar.com"}  (conflito!)
            email_taken_in_company("maria@bar.com", cid, exclude_user_id=111)
            → Busca: email=maria@bar.com AND company_id=cid AND id != 111
            → Resultado: Usuário B tem este e-mail → True → ConflictError

        KEYWORD-ONLY:
        exclude_user_id está após * para forçar uso explícito:
            await repo.email_taken_in_company(email, cid, exclude_user_id=user_id)
        Isso evita passar o UUID por posição por engano.

        QUERY GERADA (com exclude_user_id):
            SELECT COUNT(*) FROM users
            WHERE email = :email
              AND company_id = :company_id
              AND id != :exclude_user_id
              AND deleted_at IS NULL
        """
        filters = [
            User.email == email,
            User.company_id == company_id,
            User.deleted_at.is_(None),   # e-mail de soft-deletado ainda "ocupa" o slot
        ]

        if exclude_user_id is not None:
            # Exclui o próprio usuário da verificação (caso de atualização)
            # != em SQLAlchemy é representado por User.id != exclude_user_id
            filters.append(User.id != exclude_user_id)

        stmt = (
            select(func.count())
            .select_from(User)
            .where(*filters)
        )
        result = await self.session.execute(stmt)
        count = result.scalar_one()

        # Retorna bool direto — mais legível no Service do que comparar count > 0
        return count > 0
