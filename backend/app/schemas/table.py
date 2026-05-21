"""
app/schemas/table.py

Schemas Pydantic para o módulo de mesas.

═══════════════════════════════════════════════════════════════
CONCEITO — Schema vs Model: qual é a diferença?
═══════════════════════════════════════════════════════════════

MODEL (SQLAlchemy):
    Representa uma TABELA no banco de dados.
    É o mapa entre Python e PostgreSQL.
    Fica em app/models/table.py
    Exemplo: class Table(Base) → tabela "tables" no banco

SCHEMA (Pydantic):
    Representa os DADOS QUE TRAFEGAM na API.
    Valida e documenta a entrada/saída dos endpoints.
    Fica em app/schemas/table.py
    Exemplo: class TableCreate → o corpo do POST /tables

Por que são separados?
    - O Model tem campos internos que o cliente não deve ver
      (ex: internal IDs, flags de controle)
    - O Schema controla exatamente o que entra e sai
    - Você pode ter múltiplos schemas para o mesmo model:
        TableCreate   → o que o cliente manda para criar
        TableUpdate   → o que o cliente manda para editar
        TableResponse → o que o servidor devolve para o cliente
    - Se o banco mudar, o schema protege a API pública

═══════════════════════════════════════════════════════════════
CONCEITO — Pydantic v2 e from_attributes=True
═══════════════════════════════════════════════════════════════

Pydantic v2 não sabe, por padrão, ler atributos de objetos Python.
Ele lê dicionários. Para ler um objeto SQLAlchemy (Model):

    TableResponse.model_validate(table)  ✓ — lê atributos do objeto
    TableResponse(**table.__dict__)      ✗ — não funciona com lazy loading

O ConfigDict(from_attributes=True) diz ao Pydantic:
    "Pode ler de atributos de objeto, não só de dicionários."

Isso é configurado em BaseSchema (schemas/common.py) e herdado aqui.
"""

from uuid import UUID

from pydantic import Field, field_validator

from app.models.table import TableStatus
from app.schemas.common import BaseSchema, PaginatedResponse, TimestampSchema, UUIDSchema


# ── Schemas de Entrada ────────────────────────────────────────────────────────
# Estes schemas definem o que o CLIENTE ENVIA para a API.
# O Pydantic valida automaticamente — campos inválidos geram HTTP 422.


class TableCreate(BaseSchema):
    """
    Dados necessários para criar uma nova mesa.

    Usado em: POST /api/v1/tables
    O cliente envia este JSON no corpo da requisição.

    Campos que o SERVIDOR define automaticamente (não aparecem aqui):
    - id              → UUID gerado pelo PostgreSQL
    - establishment_id → vem do JWT do usuário logado
    - status          → sempre começa como FREE (regra de negócio)
    - is_active       → sempre começa como True
    - created_at      → timestamp do banco
    - updated_at      → timestamp do banco
    - version         → começa em 1
    """

    number: int = Field(
        ...,
        gt=0,
        description="Número único da mesa neste estabelecimento (ex: 1, 2, 3)",
    )
    label: str = Field(
        ...,
        min_length=1,
        max_length=50,
        description="Nome visível na interface (ex: 'Mesa 1', 'Balcão', 'Terraço')",
    )
    capacity: int = Field(
        default=4,
        gt=0,
        le=50,
        description="Número máximo de pessoas que cabem na mesa",
    )
    section: str | None = Field(
        default=None,
        max_length=60,
        description="Seção/área do estabelecimento (ex: 'Área externa', 'VIP'). Opcional.",
    )

    @field_validator("label")
    @classmethod
    def label_strip(cls, v: str) -> str:
        """Remove espaços extras do começo e fim do label."""
        return v.strip()


class TableUpdate(BaseSchema):
    """
    Dados para atualizar uma mesa existente.

    Usado em: PATCH /api/v1/tables/{table_id}

    CONCEITO — PATCH vs PUT:
        PUT  → substitui o recurso inteiro (todos os campos obrigatórios)
        PATCH → atualiza apenas os campos enviados (campos opcionais)

        Com PATCH, o cliente manda só o que quer mudar:
        {"label": "Mesa 2", "version": 3}
        ↑ só o label muda — capacity e status ficam como estão

    CONCEITO — Por que `version` é obrigatório?
        Version é o mecanismo de LOCKING OTIMISTA (Optimistic Locking).

        Imagine dois garçons abrindo a mesa 5 ao mesmo tempo:
        1. Garçom A lê mesa 5: version=1, status=FREE
        2. Garçom B lê mesa 5: version=1, status=FREE
        3. Garçom A muda status para OCCUPIED: version vira 2
        4. Garçom B tenta mudar para OCCUPIED: version=1 ≠ version=2 no banco
        5. → HTTP 409 CONFLICT: alguém já mudou, recarregue e tente novamente

        Sem locking otimista, o passo 4 simplesmente sobreescreveria a mudança
        do Garçom A silenciosamente — dados corrompidos sem aviso!

    Todos os campos (exceto version) são opcionais em PATCH.
    Campos não enviados ficam intocados no banco.
    """

    label: str | None = Field(default=None, min_length=1, max_length=50)
    capacity: int | None = Field(default=None, gt=0, le=50)
    status: TableStatus | None = Field(
        default=None,
        description="Novo status da mesa (free, occupied, bill_requested, reserved, blocked)",
    )
    section: str | None = Field(
        default=None,
        max_length=60,
        description="Seção/área. Envie null explicitamente para limpar o campo.",
    )
    version: int = Field(
        ...,
        gt=0,
        description="Versão atual da mesa (locking otimista). Obtenha do GET e envie de volta.",
    )


# ── Schemas de Saída ──────────────────────────────────────────────────────────
# Estes schemas definem o que o SERVIDOR RETORNA ao cliente.
# O FastAPI serializa automaticamente o Model para este schema.


class TableResponse(UUIDSchema, TimestampSchema):
    """
    Representação completa de uma mesa para o cliente.

    Retornado em: POST, GET, PATCH /api/v1/tables/...

    HERANÇA MÚLTIPLA:
        UUIDSchema   → adiciona campo `id: UUID`
        TimestampSchema → adiciona `created_at` e `updated_at`
        TableResponse → adiciona todos os campos específicos de mesa

    Assim evitamos duplicar os campos comuns em cada schema.
    """

    establishment_id: UUID
    number: int
    label: str
    capacity: int
    status: TableStatus
    section: str | None
    is_active: bool
    version: int


# ── Alias tipado para resposta paginada ───────────────────────────────────────
# PaginatedResponse já existe em common.py, mas podemos usá-la diretamente.
# O alias aqui serve de documentação: deixa claro o que o endpoint retorna.
PaginatedTableResponse = PaginatedResponse
