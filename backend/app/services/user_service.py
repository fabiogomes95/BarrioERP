"""
app/services/user_service.py

Regras de negócio do módulo de gestão de usuários.

═══════════════════════════════════════════════════════════════
CONCEITO — Service Layer
═══════════════════════════════════════════════════════════════

O Service é o único lugar onde ficam as REGRAS DE NEGÓCIO.

O que isso significa na prática?
    "Só OWNER pode criar outro OWNER"            → regra de negócio → Service
    "E-mail deve ter @"                          → validação de formato → Schema
    "INSERT INTO users VALUES (...)"             → acesso ao banco     → Repository
    "HTTP 403 se a operação for proibida"        → conversão de erro   → exception_handler

Por que essa separação importa?
    Se amanhã surgir uma CLI de administração, um job de importação em lote
    ou uma integração com sistema de RH, todos eles podem reutilizar o
    UserService sem precisar de um endpoint HTTP.

═══════════════════════════════════════════════════════════════
CONCEITO — RBAC (Role-Based Access Control)
═══════════════════════════════════════════════════════════════

RBAC é o padrão mais usado em sistemas SaaS para controle de acesso.
"Quem você é determina o que você pode fazer."

Hierarquia de permissões do BarrioERP:

    OWNER   → pode gerenciar QUALQUER role (inclusive outros OWNERs)
    MANAGER → pode gerenciar MANAGER, CASHIER, WAITER, KITCHEN
              NÃO pode criar/editar/deletar OWNERs
    Outros  → sem permissão de gestão de usuários

Por que MANAGER não pode tocar em OWNER?
    Se um MANAGER pudesse rebaixar um OWNER, ele poderia sequestrar
    o controle da empresa: remover todos os OWNERs e assumir.
    Esse tipo de proteção hierárquica é padrão em sistemas empresariais.

═══════════════════════════════════════════════════════════════
CONCEITO — acting_user vs target_user
═══════════════════════════════════════════════════════════════

Toda operação sensível tem duas partes:
    acting_user → QUEM está fazendo a ação (usuário logado)
    target_user → EM QUEM a ação está sendo feita

RBAC combina os dois: acting_user.role + target_user.role → permitido ou não.
"""

from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import (
    BusinessRuleError,
    ConflictError,
    ForbiddenError,
    NotFoundError,
    ValidationError,
)
from app.core.security import hash_password, verify_password
from app.models.user import User, UserRole
from app.repositories.user_repository import UserRepository
from app.schemas.common import PaginatedResponse
from app.schemas.user import (
    ChangePasswordRequest,
    UserCreate,
    UserResponse,
    UserUpdate,
)
from app.services.base import BaseService

# ══════════════════════════════════════════════════════════════════════════════
# CONSTANTES DE PERMISSÃO
#
# Centralizamos aqui os roles que têm poder de gestão de usuários.
# Se amanhã um novo role "HR_ADMIN" for criado com poder de gestão,
# basta adicionar aqui — um único lugar, sem alterar nenhum método.
# ══════════════════════════════════════════════════════════════════════════════

# Roles que podem gerenciar outros usuários (criar, editar, deletar)
_MANAGEMENT_ROLES: frozenset[UserRole] = frozenset({
    UserRole.OWNER,
    UserRole.MANAGER,
})

# Roles que MANAGER não pode criar, editar ou deletar
# (apenas OWNER pode gerenciar outros OWNERs)
_OWNER_ONLY_ROLES: frozenset[UserRole] = frozenset({
    UserRole.OWNER,
})


class UserService(BaseService):
    """
    Serviço de gestão de usuários — orquestra as operações de CRUD.

    DIFERENÇA em relação aos outros services:
        TableService, OrderService etc. recebem `company_id` e `user_id`
        separados no construtor.

        UserService recebe o `acting_user` (objeto User completo).
        Motivo: precisamos do `role` para RBAC em cada operação.
        Passar o objeto completo evita uma query extra ao banco.

    O construtor extrai os campos necessários para o BaseService
    diretamente do acting_user.
    """

    def __init__(self, session: AsyncSession, acting_user: User) -> None:
        # Extraímos os campos do acting_user para o BaseService
        # O BaseService armazenará: self.company_id, self.establishment_id, self.user_id
        super().__init__(
            session,
            company_id=acting_user.company_id,
            establishment_id=acting_user.establishment_id,
            user_id=acting_user.id,
        )
        # Guardamos o acting_user completo para verificações de RBAC
        self._acting_user = acting_user
        # O Repository compartilha a mesma sessão → mesma transação
        self._repo = UserRepository(session)

    # ══════════════════════════════════════════════════════════════════════
    # HELPERS PRIVADOS — RBAC
    #
    # Por que privados (prefixo _)?
    # São detalhes de implementação interna. O endpoint não deve chamá-los.
    # Apenas os métodos públicos do Service os utilizam.
    # ══════════════════════════════════════════════════════════════════════

    def _require_management_role(self) -> None:
        """
        Garante que o acting_user tem permissão para gerenciar usuários.

        LANÇA: ForbiddenError se o role não for OWNER ou MANAGER.

        USO: chamado no início de create(), list_users() e delete().
        Não é chamado em get() (todos podem ver seu próprio perfil).
        """
        if self._acting_user.role not in _MANAGEMENT_ROLES:
            raise ForbiddenError(
                "Apenas Owners e Managers podem gerenciar usuários."
            )

    def _require_can_manage_role(self, target_role: UserRole) -> None:
        """
        Garante que o acting_user pode gerenciar um usuário do target_role.

        Diferença em relação a _require_management_role():
            _require_management_role() → "posso gerenciar usuários?"
            _require_can_manage_role() → "posso gerenciar ESTE ROLE específico?"

        REGRAS:
            OWNER   → pode gerenciar qualquer role, incluindo outros OWNERs
            MANAGER → pode gerenciar qualquer role EXCETO OWNER
            Outros  → não podem gerenciar ninguém (bloqueado antes de chegar aqui)

        LANÇA: ForbiddenError se não tiver permissão sobre o target_role.
        """
        acting_role = self._acting_user.role

        if acting_role == UserRole.OWNER:
            # OWNER é onipotente — pode gerenciar qualquer role
            return

        if acting_role == UserRole.MANAGER:
            # MANAGER não pode tocar em OWNERs — proteção hierárquica
            if target_role in _OWNER_ONLY_ROLES:
                raise ForbiddenError(
                    "Managers não podem criar, editar ou remover contas Owner. "
                    "Esta operação requer um usuário Owner."
                )
            return

        # Qualquer outro role não deveria chegar aqui
        # (deveria ter sido bloqueado por _require_management_role antes)
        raise ForbiddenError("Acesso negado.")

    # ══════════════════════════════════════════════════════════════════════
    # HELPERS PRIVADOS — Last Owner Protection
    # ══════════════════════════════════════════════════════════════════════

    async def _ensure_not_last_owner(self, target_user: User) -> None:
        """
        Impede operações que deixariam a empresa sem nenhum Owner ativo.

        Cenário que este método previne:
            Empresa tem 1 Owner (João).
            Alguém tenta: DELETE /users/joao-uuid
            Resultado sem proteção: João é deletado, empresa fica órfã.
            Resultado com proteção: BusinessRuleError → HTTP 422.

        QUANDO É CHAMADO:
            1. delete()  → antes de soft-deletar um Owner
            2. update()  → antes de desativar (is_active=False) um Owner
            3. update()  → antes de rebaixar (role != OWNER) um Owner

        LÓGICA:
            Se o target_user é OWNER E is_active=True E não está deletado:
                → conta como owner ativo
                → count_active_owners() conta quantos existem
                → se for o último (count == 1): bloqueia

        POR QUE NÃO VERIFICAR `count == 0`?
            Verificamos ANTES de executar a operação.
            Neste momento, o owner ainda está ativo.
            Após a operação, haveria 0 owners. Então verificamos: 1 == 1.
        """
        if target_user.role != UserRole.OWNER:
            # Só precisamos verificar para Owners
            return

        if not target_user.is_active or target_user.deleted_at is not None:
            # Se já está inativo ou deletado, não contribui para a contagem
            return

        count = await self._repo.count_active_owners(self.company_id)

        if count <= 1:
            raise BusinessRuleError(
                "Não é possível remover, desativar ou rebaixar o último Owner da empresa. "
                "Promova outro usuário a Owner antes de realizar esta operação."
            )

    # ══════════════════════════════════════════════════════════════════════
    # OPERAÇÕES CRUD
    # ══════════════════════════════════════════════════════════════════════

    async def create(self, data: UserCreate) -> UserResponse:
        """
        Cria um novo usuário na empresa do acting_user.

        FLUXO COMPLETO:
            1. RBAC: acting_user deve ser OWNER ou MANAGER
            2. RBAC: acting_user deve poder gerenciar o role que está criando
            3. Unicidade: e-mail não pode estar em uso na empresa
            4. Hash da senha: NUNCA armazenamos senha em texto puro
            5. company_id: vem do acting_user (multi-tenancy — cliente não escolhe)
            6. Persiste e retorna UserResponse

        DECISÃO ARQUITETURAL — company_id não vem do body:
            O cliente envia: {"name": "Maria", "email": "...", "role": "waiter", ...}
            O Service completa: company_id = acting_user.company_id

            Por que? Um MANAGER logado na Empresa A não pode criar usuários
            na Empresa B passando o company_id dela no body da requisição.
            O tenant é sempre inferido do JWT, nunca aceito do cliente.

        DECISÃO ARQUITETURAL — is_active sempre True ao criar:
            Um usuário recém-criado está ativo por definição.
            Desativação é uma operação posterior e deliberada.
            Se o schema permitisse is_active no create, um descuido poderia
            criar usuários inativos invisíveis na listagem padrão.
        """
        # 1. RBAC — verifica se pode gerenciar usuários
        self._require_management_role()

        # 2. RBAC — verifica se pode criar o role específico
        # (ex: MANAGER não pode criar OWNER)
        self._require_can_manage_role(data.role)

        # 3. Unicidade de e-mail dentro da empresa
        # O mesmo e-mail pode existir em empresas diferentes (SaaS multi-tenant),
        # mas não pode se repetir dentro da mesma empresa.
        email_taken = await self._repo.email_taken_in_company(
            email=data.email,
            company_id=self.company_id,
        )
        if email_taken:
            raise ConflictError(
                f"O e-mail '{data.email}' já está em uso nesta empresa."
            )

        # 4. Hash da senha — nunca armazenar em texto puro
        # hash_password() usa bcrypt: lento por design (dificulta força bruta),
        # salt aleatório embutido (cada hash é único mesmo para a mesma senha)
        password_hash = hash_password(data.password)

        # 5. Cria o objeto User em memória (ainda não está no banco)
        # company_id vem do acting_user — nunca do body da requisição
        user = User(
            company_id=self.company_id,              # inferido do JWT
            establishment_id=data.establishment_id,  # pode ser None
            name=data.name,
            email=data.email.lower(),                # normaliza para minúsculas
            phone=data.phone,
            password_hash=password_hash,             # hash, nunca o texto puro
            role=data.role,
            is_active=True,                          # sempre ativo ao criar
        )

        # 6. Persiste: session.add() + flush() + refresh()
        # O commit acontece automaticamente em get_db() quando o endpoint retorna
        user = await self._repo.add(user)

        # 7. Converte o Model SQLAlchemy para Schema Pydantic
        # from_attributes=True (no BaseSchema) permite isso diretamente
        return UserResponse.model_validate(user)

    async def list_users(
        self,
        *,
        role: UserRole | None = None,
        establishment_id: UUID | None = None,
        active_only: bool = True,
        page: int = 1,
        page_size: int = 20,
    ) -> PaginatedResponse:
        """
        Lista usuários da empresa com filtros opcionais e paginação.

        RBAC:
            Apenas OWNER e MANAGER podem listar usuários.
            CASHIER, WAITER e KITCHEN não têm acesso a esta listagem.

        FILTROS DISPONÍVEIS (todos opcionais):
            role             → listar só garçons, só gerentes, etc.
            establishment_id → listar só funcionários de uma filial
            active_only      → True (padrão) = só ativos; False = todos

        PAGINAÇÃO:
            page=1, page_size=20 → registros 1–20
            page=2, page_size=20 → registros 21–40
            Fórmula: offset = (page - 1) * page_size

        RETORNA: PaginatedResponse com:
            items     → lista de UserResponse desta página
            total     → total de registros (para calcular quantas páginas há)
            page      → página atual
            page_size → registros por página
            pages     → total de páginas
        """
        # RBAC: apenas roles de gestão podem listar usuários
        self._require_management_role()

        offset = (page - 1) * page_size

        # Busca a página de usuários
        users = await self._repo.list_by_company(
            self.company_id,
            active_only=active_only,
            role=role,
            establishment_id=establishment_id,
            limit=page_size,
            offset=offset,
        )

        # Para a contagem total, precisamos dos mesmos filtros aplicados na listagem.
        # Usamos BaseRepository.count() com os filtros construídos manualmente.
        # Isso evita dois chamados com lógica duplicada e é legível.
        count_filters = [
            User.company_id == self.company_id,
            User.deleted_at.is_(None),
        ]
        if active_only:
            count_filters.append(User.is_active.is_(True))
        if role is not None:
            count_filters.append(User.role == role)
        if establishment_id is not None:
            count_filters.append(User.establishment_id == establishment_id)

        total = await self._repo.count(*count_filters)

        # Calcula o total de páginas arredondando para cima
        # Ex: 45 registros, page_size=20 → ceil(45/20) = 3 páginas
        pages = max(1, (total + page_size - 1) // page_size)

        return PaginatedResponse(
            items=[UserResponse.model_validate(u) for u in users],
            total=total,
            page=page,
            page_size=page_size,
            pages=pages,
        )

    async def get(self, user_id: UUID) -> UserResponse:
        """
        Retorna os dados de um usuário específico.

        RBAC FLEXÍVEL:
            OWNER e MANAGER → podem ver qualquer usuário da empresa
            Outros roles    → podem ver apenas o próprio perfil

        Por que outros roles podem ver o próprio perfil?
            Um garçom precisa ver seus próprios dados (nome, role, email).
            Bloquear totalmente seria um design ruim do ponto de vista de UX.
            Mas ele não pode ver os dados de outros funcionários.

        MULTI-TENANCY:
            Usamos get_by_company() que filtra por (id, company_id).
            Se user_id pertencer a outra empresa → retorna None → HTTP 404.
            O cliente não descobre se aquele UUID existe em outro restaurante.
        """
        acting_role = self._acting_user.role

        if acting_role not in _MANAGEMENT_ROLES:
            # Roles não-gestores só podem ver o próprio perfil
            if user_id != self._acting_user.id:
                raise ForbiddenError(
                    "Você não tem permissão para ver o perfil de outros usuários."
                )

        # get_by_company: garante isolamento de tenant
        # Nunca use BaseRepository.get(user_id) — retornaria qualquer usuário
        user = await self._repo.get_by_company(user_id, self.company_id)

        if user is None:
            raise NotFoundError("User", user_id)

        return UserResponse.model_validate(user)

    async def update(self, user_id: UUID, data: UserUpdate) -> UserResponse:
        """
        Atualiza parcialmente um usuário.

        PATCH PARCIAL — model_dump(exclude_unset=True):
            O cliente envia apenas os campos que quer alterar.
            {"phone": "+55 11 99999-0000"} → só phone é atualizado.
            Campos não enviados não são tocados.

        RBAC:
            OWNER   → pode atualizar qualquer usuário, qualquer campo
            MANAGER → pode atualizar qualquer role exceto OWNER
            Outros  → podem atualizar apenas o próprio name/phone
                      (campos não sensíveis — sem role, sem is_active)

        PROTEÇÕES ENCADEADAS:
            1. Verifica se o usuário existe (com tenant isolation)
            2. RBAC: verifica permissão sobre o target_user atual
            3. RBAC: se role está mudando, verifica permissão sobre o NOVO role
            4. Last owner: se está desativando ou rebaixando um Owner
            5. Unicidade: se email está mudando, verifica conflito
            6. Aplica mudanças com setattr dinâmico
        """
        acting_role = self._acting_user.role

        # Busca o usuário alvo (com tenant isolation)
        user = await self._repo.get_by_company(user_id, self.company_id)
        if user is None:
            raise NotFoundError("User", user_id)

        is_self_update = user_id == self._acting_user.id

        if acting_role not in _MANAGEMENT_ROLES:
            # Roles não-gestores só podem atualizar o próprio perfil
            if not is_self_update:
                raise ForbiddenError(
                    "Você não tem permissão para editar o perfil de outros usuários."
                )
            # E mesmo atualizando o próprio perfil, não podem mudar role ou is_active
            if data.role is not None or data.is_active is not None:
                raise ForbiddenError(
                    "Você não pode alterar seu próprio role ou status de ativação."
                )
        else:
            # Gestores: verifica RBAC sobre o target_user
            self._require_can_manage_role(user.role)

            # Se o role está sendo alterado, verifica RBAC sobre o NOVO role também
            # Ex: MANAGER não pode promover um CASHIER a OWNER
            if data.role is not None:
                self._require_can_manage_role(data.role)

        # Proteção do último Owner:
        # Se desativando (is_active=False) ou rebaixando (role != OWNER) um Owner
        is_deactivating = data.is_active is False
        is_downgrading = data.role is not None and data.role != UserRole.OWNER

        if (is_deactivating or is_downgrading) and user.role == UserRole.OWNER:
            # _ensure_not_last_owner só bloqueia se for o ÚLTIMO owner ativo
            await self._ensure_not_last_owner(user)

        # Se o e-mail está sendo alterado, verifica unicidade
        if data.email is not None and data.email.lower() != user.email:
            email_taken = await self._repo.email_taken_in_company(
                email=data.email,
                company_id=self.company_id,
                exclude_user_id=user_id,  # exclui o próprio usuário da verificação
            )
            if email_taken:
                raise ConflictError(
                    f"O e-mail '{data.email}' já está em uso nesta empresa."
                )

        # Aplica apenas os campos que foram enviados (PATCH parcial)
        # exclude_unset=True → ignora campos não presentes no body da requisição
        update_data = data.model_dump(exclude_unset=True)

        for field, value in update_data.items():
            if field == "email" and value is not None:
                value = value.lower()  # normaliza e-mail para minúsculas
            setattr(user, field, value)

        await self.session.flush()
        await self.session.refresh(user)
        return UserResponse.model_validate(user)

    async def delete(self, user_id: UUID) -> None:
        """
        Remove um usuário via soft delete.

        SOFT DELETE — por que não DELETE físico?
            Usuários têm histórico: comandas abertas, pagamentos registrados,
            logs de auditoria. Deletar fisicamente corromperia esse histórico.

            Com soft delete:
                user.deleted_at = now()  → usuário "some" da listagem
                O registro permanece no banco → histórico preservado
                Login é bloqueado em deps.get_current_user() (filtra deleted_at)

        SOFT DELETE vs IS_ACTIVE:
            is_active = False  → desativação temporária (pode reativar via PATCH)
            deleted_at = now() → exclusão permanente (intenção de "remover")

            DELETE /users/{id} usa soft_delete() (deleted_at) porque é
            uma operação de exclusão com semântica de permanência.

        RBAC + PROTEÇÕES:
            1. Apenas OWNER/MANAGER podem deletar
            2. MANAGER não pode deletar OWNERs
            3. Não pode deletar o último Owner ativo
            4. Não pode se auto-deletar (evita lock-out acidental)
        """
        # RBAC: apenas gestores podem deletar
        self._require_management_role()

        # Busca o usuário alvo (com tenant isolation)
        user = await self._repo.get_by_company(user_id, self.company_id)
        if user is None:
            raise NotFoundError("User", user_id)

        # Não pode se auto-deletar via API
        # Motivo: previne lock-out acidental. Se o último admin se deletar,
        # a empresa fica sem acesso. _ensure_not_last_owner também protege,
        # mas ser explícito sobre auto-delete é uma boa prática de segurança.
        if user_id == self._acting_user.id:
            raise BusinessRuleError(
                "Você não pode remover sua própria conta. "
                "Peça a outro Owner ou Manager para realizar esta operação."
            )

        # RBAC: verifica se pode gerenciar o role do target_user
        self._require_can_manage_role(user.role)

        # Proteção do último Owner
        await self._ensure_not_last_owner(user)

        # Soft delete: seta deleted_at = now()
        # O método soft_delete() está definido em SoftDeleteMixin (database/base.py)
        user.soft_delete()
        await self.session.flush()
        # Sem retorno — o endpoint vai responder com HTTP 204 No Content

    async def change_password(
        self,
        user_id: UUID,
        data: ChangePasswordRequest,
    ) -> UserResponse:
        """
        Altera a senha de um usuário.

        DOIS FLUXOS DISTINTOS baseados em quem está chamando:

        1. Usuário alterando a PRÓPRIA senha (self-service):
            - current_password é OBRIGATÓRIO (prova de identidade)
            - Protege contra alguém que pegou o computador desbloqueado
            - Sem RBAC especial — qualquer usuário pode alterar a própria senha

        2. OWNER ou MANAGER resetando a senha de um subordinado:
            - current_password é OPCIONAL/IGNORADO (manager não sabe a senha do funcionário)
            - Requer RBAC: MANAGER não pode resetar senha de OWNERs
            - Útil quando um funcionário esquecer a senha

        POR QUE ENDPOINT SEPARADO E NÃO CAMPO NO PATCH?
            1. AUDITORIA: troca de senha é evento de segurança — deve ser
               registrado separadamente (futura integração com AuditLog)
            2. SEGURANÇA: exige current_password para auto-troca,
               o que não se encaixa no fluxo genérico do PATCH
            3. NOTIFICAÇÕES: pode disparar e-mail de alerta
               ("Sua senha foi alterada. Não foi você? Contate o suporte.")
        """
        # Busca o usuário alvo (com tenant isolation)
        user = await self._repo.get_by_company(user_id, self.company_id)
        if user is None:
            raise NotFoundError("User", user_id)

        is_self = user_id == self._acting_user.id

        if is_self:
            # FLUXO 1: usuário alterando a própria senha
            # current_password é OBRIGATÓRIO para self-service
            if data.current_password is None:
                raise ValidationError(
                    "Para alterar sua própria senha, informe a senha atual no campo 'current_password'."
                )

            # Verifica se a senha atual confere com o hash no banco
            # verify_password usa bcrypt: extrai o salt do hash e recomputa
            if not user.password_hash or not verify_password(data.current_password, user.password_hash):
                raise ValidationError("Senha atual incorreta.")

        else:
            # FLUXO 2: OWNER ou MANAGER resetando senha de subordinado
            # Apenas gestores podem resetar senhas de outros
            self._require_management_role()
            self._require_can_manage_role(user.role)

        # Hash da nova senha — igual ao que é feito na criação
        user.password_hash = hash_password(data.new_password)

        await self.session.flush()
        await self.session.refresh(user)
        return UserResponse.model_validate(user)
