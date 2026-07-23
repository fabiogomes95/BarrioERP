"""
app/schemas/onboarding.py

Contratos de entrada e saída do fluxo de onboarding — primeiro acesso ao sistema.

═══════════════════════════════════════════════════════════════
CONCEITO — O que é "onboarding" neste contexto?
═══════════════════════════════════════════════════════════════

"Onboarding" é o processo de integração de um novo cliente ao sistema.
Aqui, é o momento em que o dono de um bar preenche um formulário
e, em uma única operação, o sistema cria toda a estrutura necessária
para ele operar:

    [formulário] → Company + Establishment + Usuário OWNER + JWT

Diferente de todos os outros endpoints, este é:
  - Público (não requer autenticação)
  - Atômico (tudo criado numa transação ou nada criado)
  - Terminal (retorna o JWT imediatamente — sem etapa extra de login)

═══════════════════════════════════════════════════════════════
CONCEITO — Por que um schema separado e não reutilizar UserCreate?
═══════════════════════════════════════════════════════════════

`UserCreate` (schemas/user.py) cria um usuário dentro de um tenant
que já existe. O `role` é um campo obrigatório porque o OWNER decide
qual cargo o novo funcionário terá.

`OnboardingRequest` cria o tenant inteiro a partir do zero:
  - O `role` é sempre OWNER — não existe escolha aqui
  - O `bar_name` cria Company + Establishment — conceito inexistente no UserCreate
  - O contexto semântico é diferente: "entrar no sistema" vs "gerenciar equipe"

Reutilizar `UserCreate` forçaria o cliente a preencher um campo `role`
que ele nunca deveria escolher, e exporia ao frontend a arquitetura
interna Company/Establishment/User — que é detalhe de implementação.
"""

from uuid import UUID

from pydantic import EmailStr, field_validator

from app.schemas.common import BaseSchema
from app.schemas.user import UserResponse


# ══════════════════════════════════════════════════════════════════════════════
# SCHEMA DE ENTRADA — o que o formulário "Criar Estabelecimento" envia
# ══════════════════════════════════════════════════════════════════════════════


class OnboardingRequest(BaseSchema):
    """
    Dados do formulário de cadastro do primeiro acesso.

    Usado em: POST /api/v1/onboarding/register

    O USUÁRIO informa apenas o essencial:
        bar_name    → nome do bar (ex: "Bar do João")
        owner_name  → nome completo do proprietário
        email       → e-mail de login
        password    → senha para acesso
        phone       → opcional (telefone de contato)
        address     → opcional (endereço físico do bar)

    O SISTEMA cria automaticamente, sem interação do usuário:
        Company        com name = bar_name
        Establishment  com name = "Matriz" (unidade principal)
        Usuário OWNER  vinculado à Company e ao Establishment

    POR QUE O ESTABLISHMENT SE CHAMA "MATRIZ"?
    ─────────────────────────────────────────
    O modelo de dados suporta múltiplas filiais:
        Company "Bar do João"
            └── Establishment "Matriz"       ← criada aqui
            └── Establishment "Filial Centro"  ← futura expansão

    O usuário não precisa saber dessa divisão na primeira tela.
    Ele diz "meu bar se chama Bar do João" — o sistema cuida da
    organização interna. "Matriz" é o nome convencional da unidade
    principal em sistemas empresariais (ERP, SAP, etc.).

    CAMPOS AUSENTES INTENCIONALMENTE:
        role       → sempre OWNER (dono do bar)
        company_id → criado nesta operação, não existe ainda
        establishment_id → criado nesta operação, não existe ainda
    """

    bar_name: str
    owner_name: str
    email: EmailStr   # EmailStr valida formato: precisa de @, domínio, etc.
    password: str
    phone: str | None = None
    address: str | None = None

    @field_validator("bar_name")
    @classmethod
    def bar_name_not_empty(cls, v: str) -> str:
        """
        Nome do bar não pode ser vazio ou só espaços.

        .strip() remove espaços do início e fim antes de verificar.
        "Bar do João" → aceito
        "  "          → rejeitado (só espaços)
        ""            → rejeitado (vazio)
        """
        v = v.strip()
        if not v:
            raise ValueError("Bar name cannot be empty")
        return v

    @field_validator("owner_name")
    @classmethod
    def owner_name_not_empty(cls, v: str) -> str:
        """Nome do proprietário não pode ser vazio."""
        v = v.strip()
        if not v:
            raise ValueError("Owner name cannot be empty")
        return v

    @field_validator("password")
    @classmethod
    def password_strength(cls, v: str) -> str:
        """Mesma regra de user.py (mínimo 4 caracteres) — ver nota lá sobre
        por que essa validação é duplicada em vez de importada."""
        if len(v) < 4:
            raise ValueError("Password must be at least 4 characters")
        return v

    @field_validator("phone")
    @classmethod
    def normalize_phone(cls, v: str | None) -> str | None:
        """Remove espaços extras do telefone, se informado."""
        return v.strip() if v is not None else None

    @field_validator("address")
    @classmethod
    def normalize_address(cls, v: str | None) -> str | None:
        """Remove espaços extras do endereço, se informado."""
        return v.strip() if v is not None else None


# ══════════════════════════════════════════════════════════════════════════════
# SCHEMA DE SAÍDA — o que a API retorna após o cadastro
# ══════════════════════════════════════════════════════════════════════════════


class OnboardingResponse(BaseSchema):
    """
    Resposta do onboarding — tudo que o frontend precisa para iniciar.

    Retornado por: POST /api/v1/onboarding/register (HTTP 201 Created)

    O DIFERENCIAL deste response:
    O usuário cadastrou-se e JÁ ESTÁ LOGADO.
    O `access_token` retornado aqui pode ser usado imediatamente
    em qualquer endpoint autenticado do sistema.
    Sem etapa extra de "agora vá para o login".

    ─────────────────────────────────────
    CAMPOS:
    ─────────────────────────────────────
    access_token     → JWT pronto para uso.
                       O frontend guarda no localStorage / sessionStorage
                       e envia como "Authorization: Bearer <token>" em
                       todas as requisições seguintes.

    token_type       → Sempre "bearer". Padrão OAuth2.
                       O frontend usa: `Authorization: Bearer {access_token}`

    user             → Dados completos do usuário OWNER criado.
                       Inclui company_id e establishment_id — o frontend
                       não precisa decodar o JWT para obtê-los.

    establishment_name → Nome do Establishment criado.
                         Sempre "Matriz" neste fluxo, mas retornamos
                         explicitamente porque o frontend não deve
                         hardcodar este valor — ele é definido pelo backend.

    ─────────────────────────────────────
    POR QUE NÃO REPETIR company_id E establishment_id NO NÍVEL RAIZ?
    ─────────────────────────────────────
    `UserResponse` já contém `company_id` e `establishment_id`.
    Repetir os mesmos valores em dois lugares diferentes do response
    viola o princípio DRY e pode gerar confusão se os valores
    divergirem por erro futuro.

    O frontend acessa: `response.user.establishment_id`
    O `establishment_name` é o único dado extra que UserResponse não tem.
    """

    access_token: str
    token_type: str = "bearer"   # default fixo — onboarding sempre usa bearer
    user: UserResponse           # inclui company_id, establishment_id, role, etc.
    establishment_name: str      # "Matriz" — o frontend exibe ao usuário
