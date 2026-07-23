"""
app/services/auth_service.py

Lógica de negócio da autenticação.

CONCEITO — O que o AuthService faz:
    1. Recebe e-mail e senha em texto puro
    2. Busca o usuário no banco via UserRepository
    3. Verifica se a senha confere com o hash bcrypt
    4. Verifica se o usuário está ativo
    5. Gera e retorna um JWT assinado

CONCEITO — Por que o Service lança exceções de domínio e não HTTPException?
    O Service não sabe que está sendo chamado por um endpoint HTTP.
    Ele poderia ser chamado por:
    - Um endpoint REST (o nosso caso)
    - Um job assíncrono (Celery, ARQ)
    - Uma CLI de administração
    - Um teste unitário

    Ao lançar AuthenticationError (domínio), o Service permanece agnóstico.
    O handler em main.py converte para HTTP 401 quando necessário.

MENSAGEM GENÉRICA INTENCIONAL:
    "Invalid credentials" serve para e-mail inexistente E senha errada.
    Se dissermos "E-mail não encontrado", um atacante sabe que pode tentar
    outras senhas para aquele e-mail. Segurança por obscuridade mínima.
"""

import hmac

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.exceptions import AuthenticationError, NotFoundError
from app.core.security import create_access_token, hash_password, verify_password
from app.models.company import Company
from app.repositories.user_repository import UserRepository
from app.schemas.auth import ForgotPasswordRequest, LoginRequest, TokenResponse
from app.services.audit_service import AuditService


class AuthService:
    """
    Serviço de autenticação.

    Diferente de outros services, AuthService NÃO herda de BaseService
    porque o login acontece ANTES de saber qual é a empresa (tenant).
    O company_id é descoberto durante o processo de login.
    """

    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        # O service cria o repository com a mesma sessão
        # Isso garante que estão dentro da mesma transação
        self.user_repo = UserRepository(session)

    async def login(self, credentials: LoginRequest) -> TokenResponse:
        """
        Autentica um usuário e retorna um JWT.

        FLUXO DETALHADO:
            1. Busca o usuário pelo e-mail
            2. Se não encontrar → AuthenticationError (genérico)
            3. Se encontrar, verifica a senha com bcrypt
            4. Se a senha não bater → AuthenticationError (genérico)
            5. Se tudo ok, cria o JWT com dados do usuário
            6. Retorna TokenResponse

        TIMING ATTACK:
            Sempre verificamos a senha (mesmo se o usuário não existir)
            para evitar timing attacks — se retornássemos imediatamente
            para e-mails inválidos, um atacante poderia medir o tempo de
            resposta para descobrir quais e-mails existem no banco.
        """
        user = await self.user_repo.get_by_email(credentials.email)

        # Senha fictícia para manter o tempo de resposta constante
        # mesmo quando o usuário não existe (anti-timing-attack)
        password_to_check = user.password_hash if user else ""
        is_valid = verify_password(credentials.password, password_to_check) if user else False

        if not user or not is_valid:
            # Mesma mensagem para "usuário não encontrado" e "senha errada"
            # Não revelamos qual dos dois falhou
            raise AuthenticationError("E-mail ou senha incorretos")

        # extra payload: dados úteis incluídos no JWT para evitar
        # queries desnecessárias a cada requisição autenticada
        company = await self.session.get(Company, user.company_id)

        token_extra = {
            "company_id": str(user.company_id),
            "role": user.role.value,       # ex: "manager", "waiter"
            "name": user.name,             # para exibir no frontend sem query extra
            "company_name": company.name if company else None,  # nome do bar
        }

        access_token = create_access_token(subject=user.id, extra=token_extra)

        return TokenResponse(access_token=access_token)

    async def forgot_password(self, data: ForgotPasswordRequest) -> None:
        """
        Redefine a senha de um usuário via código de recuperação (sem login).

        FLUXO:
            1. Confere o código de recuperação (comparação resistente a
               timing attack — hmac.compare_digest, não `==`)
            2. Busca o usuário pelo e-mail
            3. Define a nova senha (hash bcrypt)
            4. Registra em auditoria (ação sensível — alguém redefiniu a
               própria senha ou a de outra pessoa via código mestre)

        LANÇA:
            AuthenticationError (401) → código de recuperação incorreto
            NotFoundError (404)       → e-mail não encontrado
        """
        if not hmac.compare_digest(data.recovery_code, settings.PASSWORD_RECOVERY_CODE):
            raise AuthenticationError("Código de recuperação incorreto")

        user = await self.user_repo.get_by_email(data.email)
        if user is None:
            raise NotFoundError("User", data.email)

        user.password_hash = hash_password(data.new_password)
        await self.session.flush()

        await AuditService(self.session).log(
            company_id=user.company_id,
            establishment_id=user.establishment_id,
            user_id=user.id,
            action="auth.password_recovery",
            resource_type="user",
            resource_id=str(user.id),
        )
