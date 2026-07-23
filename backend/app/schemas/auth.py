"""
app/schemas/auth.py

Schemas de entrada e saída dos endpoints de autenticação.

CONCEITO — Por que schemas separados para entrada e saída?
    Entrada (Request): valida o que o cliente enviou.
    Saída  (Response): define o que o servidor vai devolver.

    Nunca misture os dois — um LoginRequest nunca deve
    ter os campos de UserMeResponse e vice-versa.

FLUXO DE TIPOS:
    Cliente envia JSON  →  LoginRequest  →  AuthService  →  User (ORM)
    User (ORM)          →  UserMeResponse  →  JSON para o cliente
"""

from uuid import UUID

from pydantic import BaseModel, EmailStr, field_validator

from app.models.user import UserRole
from app.schemas.common import BaseSchema, TimestampSchema, UUIDSchema


# ── Entrada (Requests) ────────────────────────────────────────────────────────

class LoginRequest(BaseModel):
    """
    Dados enviados pelo cliente para fazer login.

    Usamos BaseModel (não BaseSchema) porque este schema
    não precisa de from_attributes — nunca vira a partir de um ORM object.

    NOTA SOBRE EMAIL:
    EmailStr valida o formato do e-mail (tem @, tem domínio, etc.).
    Não verifica se o e-mail existe de verdade — só o formato.
    """
    email: EmailStr
    password: str

    @field_validator("password")
    @classmethod
    def password_not_empty(cls, v: str) -> str:
        # Validação básica: não aceitar senha vazia ou só espaços
        if not v or not v.strip():
            raise ValueError("Password cannot be empty")
        return v


class ForgotPasswordRequest(BaseModel):
    """
    Dados enviados pelo cliente para redefinir a senha esquecida.

    Não exige login (o usuário esqueceu a senha, não tem como logar!).
    Em vez de link por e-mail (exigiria configurar envio de e-mail),
    usa um código de recuperação fixo (PASSWORD_RECOVERY_CODE no .env) —
    quem souber o código consegue redefinir a senha de qualquer e-mail
    cadastrado. Funciona mesmo sem nenhum outro admin disponível.
    """
    email: EmailStr
    recovery_code: str
    new_password: str

    @field_validator("new_password")
    @classmethod
    def password_strength(cls, v: str) -> str:
        if len(v) < 4:
            raise ValueError("New password must be at least 4 characters")
        return v


# ── Saída (Responses) ─────────────────────────────────────────────────────────

class TokenResponse(BaseModel):
    """
    Resposta do endpoint de login.

    Padrão Bearer Token:
        Authorization: Bearer eyJhbGci...

    O cliente armazena o access_token (localStorage, cookie httpOnly, etc.)
    e envia em todas as requisições autenticadas.
    """
    access_token: str
    token_type: str = "bearer"  # sempre "bearer" — padrão OAuth2


class UserMeResponse(UUIDSchema, TimestampSchema):
    """
    Dados do usuário logado retornados por GET /auth/me.

    Herda de UUIDSchema     → inclui campo `id`
    Herda de TimestampSchema → inclui campos `created_at` e `updated_at`

    IMPORTANTE: password_hash NÃO está aqui.
    Nunca exponha hashes de senha pela API — seria uma vulnerabilidade grave.
    """
    name: str
    email: str
    role: UserRole
    company_id: UUID
    company_name: str | None = None       # nome do bar (para exibir no topo)
    establishment_id: UUID | None = None  # None = usuário não vinculado a uma filial
    is_active: bool
