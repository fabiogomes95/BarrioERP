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

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import AuthenticationError
from app.core.security import create_access_token, verify_password
from app.repositories.user_repository import UserRepository
from app.schemas.auth import LoginRequest, TokenResponse


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
            raise AuthenticationError("Invalid credentials")

        # extra payload: dados úteis incluídos no JWT para evitar
        # queries desnecessárias a cada requisição autenticada
        token_extra = {
            "company_id": str(user.company_id),
            "role": user.role.value,       # ex: "manager", "waiter"
            "name": user.name,             # para exibir no frontend sem query extra
        }

        access_token = create_access_token(subject=user.id, extra=token_extra)

        return TokenResponse(access_token=access_token)
