"""
app/schemas/user.py

Contratos de entrada e saída do módulo de gestão de usuários.

═══════════════════════════════════════════════════════════════
CONCEITO — DTO Pattern (Data Transfer Object)
═══════════════════════════════════════════════════════════════

Em sistemas profissionais, cada "fronteira" de comunicação tem seu
próprio objeto de transferência de dados. Nunca usamos o mesmo schema
para criar, atualizar e retornar dados.

Por quê?
  - Criação (UserCreate)  : exige password, não tem id
  - Atualização (UserUpdate): password não está aqui (endpoint separado)
  - Resposta (UserResponse): sem password_hash, com id e timestamps

Se usássemos um único schema "User" para tudo, seria impossível garantir
que password_hash nunca vaza na resposta, ou que o cliente não envie
um `id` falso ao criar.

═══════════════════════════════════════════════════════════════
CONCEITO — Separação entre schemas de Auth e de Users
═══════════════════════════════════════════════════════════════

`UserMeResponse` em schemas/auth.py → quem SOY eu? (contexto de login)
`UserResponse`   em schemas/user.py → dados completos de um usuário gerenciado

São responsabilidades diferentes. O /auth/me retorna o usuário logado,
enquanto /users/{id} retorna qualquer usuário que um manager esteja gerenciando.
Por isso os dois coexistem em arquivos separados.
"""

from uuid import UUID

from pydantic import EmailStr, field_validator, model_validator

from app.models.user import UserRole
from app.schemas.common import BaseSchema, TimestampSchema, UUIDSchema


# ══════════════════════════════════════════════════════════════════════════════
# SCHEMAS DE ENTRADA (Requests)
# O que o cliente envia para a API.
# Nunca contêm `id` — o banco gera. Nunca retornam para o cliente.
# ══════════════════════════════════════════════════════════════════════════════


class UserCreate(BaseSchema):
    """
    Dados necessários para criar um novo usuário.

    Usado em: POST /api/v1/users/

    CAMPOS OBRIGATÓRIOS:
        name, email, password, role

    CAMPOS OPCIONAIS:
        phone          → nem todo funcionário tem telefone cadastrado
        establishment_id → um OWNER pode não estar vinculado a uma filial específica;
                           um WAITER geralmente está.

    CAMPOS AUSENTES INTENCIONALMENTE:
        id         → gerado pelo banco (gen_random_uuid())
        company_id → vem do JWT do usuário logado, nunca do corpo da requisição
                     (multi-tenancy: o cliente não escolhe em qual empresa criar)
        is_active  → sempre True ao criar; desativação é uma operação separada
        created_at → gerado pelo banco
        updated_at → gerado pelo banco
    """

    name: str
    email: EmailStr  # EmailStr valida formato: tem @, tem domínio, etc.
    password: str
    role: UserRole
    phone: str | None = None
    establishment_id: UUID | None = None

    @field_validator("name")
    @classmethod
    def name_must_not_be_empty(cls, v: str) -> str:
        """
        Garante que o nome não é uma string vazia ou só espaços.

        Por que no schema e não no Service?
        Validação de FORMATO pertence ao schema (Pydantic).
        Validação de REGRA DE NEGÓCIO pertence ao Service.

        "Nome não pode ser vazio" é validação de formato.
        "Nome não pode ser igual ao de outro usuário" seria regra de negócio
        (requereria query ao banco — vai para o Service).
        """
        v = v.strip()  # remove espaços do início e fim
        if not v:
            raise ValueError("Name cannot be empty")
        return v

    @field_validator("password")
    @classmethod
    def password_strength(cls, v: str) -> str:
        """
        Valida a força mínima da senha.

        REGRAS IMPLEMENTADAS:
          - Mínimo 8 caracteres
          - Pelo menos 1 letra
          - Pelo menos 1 número

        POR QUE NO SCHEMA?
        O schema é a primeira barreira — rejeita senhas fracas antes de
        chegar ao Service ou ao banco. Isso poupa processamento: não
        cria sessão de banco para depois rejeitar.

        EM PRODUÇÃO SaaS:
        Sistemas maiores usam bibliotecas como `zxcvbn` que avaliam
        a entropia real da senha (ex: "password1" é fraca mesmo tendo letra e número).
        Para nosso contexto, as regras básicas são suficientes.
        """
        if len(v) < 8:
            raise ValueError("Password must be at least 8 characters")
        if not any(c.isalpha() for c in v):
            raise ValueError("Password must contain at least one letter")
        if not any(c.isdigit() for c in v):
            raise ValueError("Password must contain at least one digit")
        return v

    @field_validator("phone")
    @classmethod
    def normalize_phone(cls, v: str | None) -> str | None:
        """
        Remove espaços extras do telefone se fornecido.

        Não validamos o formato do telefone com regex aqui porque
        números brasileiros têm muitos formatos válidos:
          +55 (11) 9 9999-9999
          11999999999
          (11) 9999-9999

        Em produção, usaríamos a biblioteca `phonenumbers` do Google
        para normalizar e validar. Ficamos com a limpeza básica por ora.
        """
        if v is not None:
            return v.strip()
        return v


class UserUpdate(BaseSchema):
    """
    Dados para atualização parcial de um usuário.

    Usado em: PATCH /api/v1/users/{id}

    TODOS OS CAMPOS SÃO OPCIONAIS.
    O cliente envia apenas o que quer alterar.

    Exemplo:
        PATCH /users/uuid
        {"phone": "+55 11 99999-0000"}
        → Só o telefone é atualizado. Nome, email, role permanecem intactos.

    CAMPOS AUSENTES INTENCIONALMENTE:
        password    → troca de senha é um endpoint separado (ChangePasswordRequest)
                      por razões de segurança e auditoria (operação sensível)
        company_id  → nunca se muda o tenant de um usuário
        email       → incluímos, mas o Service deve verificar unicidade antes de salvar

    POR QUE SEPARAR TROCA DE SENHA DO PATCH GENÉRICO?
    Em sistemas SaaS profissionais, troca de senha:
      1. Requer confirmação da senha atual (prova de identidade)
      2. Deve ser auditada separadamente (log de segurança)
      3. Pode disparar notificação por e-mail
      4. Pode invalidar sessões ativas em outros dispositivos
    Misturar com o PATCH genérico tornaria tudo isso mais complexo.
    """

    name: str | None = None
    email: EmailStr | None = None
    phone: str | None = None
    role: UserRole | None = None
    establishment_id: UUID | None = None
    is_active: bool | None = None

    @field_validator("name")
    @classmethod
    def name_not_empty_if_provided(cls, v: str | None) -> str | None:
        """
        Se o nome for enviado, não pode ser vazio.

        LÓGICA:
            name = None      → não enviado, não valida (PATCH parcial)
            name = ""        → enviado vazio, rejeita
            name = "  "      → enviado só espaços, rejeita
            name = "João"    → válido, aceita
        """
        if v is not None:
            v = v.strip()
            if not v:
                raise ValueError("Name cannot be empty if provided")
        return v


class ChangePasswordRequest(BaseSchema):
    """
    Dados para troca de senha de um usuário.

    Usado em: PATCH /api/v1/users/{id}/password

    DESIGN INTENCIONAL — dois casos de uso distintos:

    1. Usuário trocando a própria senha:
       → `current_password` é obrigatório (prova de identidade)
       → Protege contra alguém que pegou o computador desbloqueado

    2. Manager resetando senha de um funcionário:
       → `current_password` é None (manager não sabe a senha do funcionário)
       → O Service deve verificar se o solicitante tem permissão para isso
       → Apenas OWNER ou MANAGER podem fazer isso para subordinados

    Esta flexibilidade (current_password opcional) permite os dois fluxos
    com um único schema. O Service decide qual regra aplicar baseado em
    quem está fazendo a requisição (current_user.role).
    """

    current_password: str | None = None  # None = reset por manager
    new_password: str
    confirm_password: str

    @field_validator("new_password")
    @classmethod
    def new_password_strength(cls, v: str) -> str:
        """Mesmas regras de força que UserCreate.password_strength."""
        if len(v) < 8:
            raise ValueError("New password must be at least 8 characters")
        if not any(c.isalpha() for c in v):
            raise ValueError("New password must contain at least one letter")
        if not any(c.isdigit() for c in v):
            raise ValueError("New password must contain at least one digit")
        return v

    @model_validator(mode="after")
    def passwords_must_match(self) -> "ChangePasswordRequest":
        """
        Valida que new_password e confirm_password são iguais.

        CONCEITO — model_validator vs field_validator:
            field_validator valida UM campo isolado.
            model_validator valida o MODEL INTEIRO após todos os campos
            serem validados — pode comparar campos entre si.

        Essa validação cruzada é impossível com field_validator porque
        precisamos ver DOIS campos ao mesmo tempo.

        `mode="after"` → roda após todos os field_validators terminarem,
        garantindo que new_password e confirm_password já foram processados.
        """
        if self.new_password != self.confirm_password:
            raise ValueError("Passwords do not match")
        return self


# ══════════════════════════════════════════════════════════════════════════════
# SCHEMAS DE SAÍDA (Responses)
# O que a API retorna para o cliente.
# Nunca contêm password_hash. Sempre incluem id e timestamps.
# ══════════════════════════════════════════════════════════════════════════════


class UserResponse(UUIDSchema, TimestampSchema):
    """
    Representação pública de um usuário.

    Retornado por TODOS os endpoints do módulo:
        POST /users/          → retorna o usuário criado
        GET  /users/          → retorna lista de UserResponse
        GET  /users/{id}      → retorna um UserResponse
        PATCH /users/{id}     → retorna o usuário atualizado
        DELETE /users/{id}    → HTTP 204 (sem body)

    HERANÇA:
        UUIDSchema      → adiciona campo `id: UUID`
        TimestampSchema → adiciona `created_at` e `updated_at`
        BaseSchema      → adiciona `model_config = ConfigDict(from_attributes=True)`

    CAMPOS AUSENTES INTENCIONALMENTE:
        password_hash → NUNCA expor. Se aparecer aqui acidentalmente,
                        toda listagem de usuários vaza hashes de senha.
        pin_hash      → mesmo motivo (PIN de ponto de vendas)

    COMO É USADO:
        user_orm = await repo.get(user_id)          # objeto SQLAlchemy
        response = UserResponse.model_validate(user_orm)  # converte para schema
        return response  # FastAPI serializa para JSON

    from_attributes=True (herdado de BaseSchema) permite que o Pydantic
    leia atributos de objetos ORM diretamente, sem precisar converter
    para dict manualmente.
    """

    # Campos de identidade e organização
    company_id: UUID
    establishment_id: UUID | None  # None = usuário sem filial específica (ex: owner)

    # Dados pessoais e de contato
    name: str
    email: str
    phone: str | None

    # Controle de acesso
    role: UserRole  # enum: owner, manager, cashier, waiter, kitchen
    is_active: bool
