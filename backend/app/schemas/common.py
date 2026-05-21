"""
app/schemas/common.py

Schemas Pydantic base reutilizáveis por todo o sistema.

CONCEITO — Schema vs Model:
    Model (SQLAlchemy) = representa uma tabela do banco de dados.
                         Contém TUDO, inclusive campos internos (password_hash).
    Schema (Pydantic)  = representa o que entra e sai pela API.
                         Expõe apenas o que o cliente precisa ver.

    Nunca retorne um Model diretamente — sempre converta para Schema.

CONCEITO — from_attributes=True:
    Permite criar um Schema a partir de um objeto ORM diretamente:

        user_orm = await repo.get(user_id)        # objeto SQLAlchemy
        user_out = UserMeResponse.model_validate(user_orm)  # schema Pydantic
        return user_out  # FastAPI serializa para JSON

    Sem from_attributes=True, o Pydantic não consegue ler
    os atributos de objetos que não são dicionários.
"""

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict


class BaseSchema(BaseModel):
    """
    Raiz de todos os schemas do projeto.
    Configura from_attributes=True globalmente.
    """
    model_config = ConfigDict(from_attributes=True)


class TimestampSchema(BaseSchema):
    """Para responses que devem incluir as datas de criação/atualização."""
    created_at: datetime
    updated_at: datetime


class UUIDSchema(BaseSchema):
    """Para responses que devem incluir o ID do recurso."""
    id: UUID


class PaginatedResponse(BaseSchema):
    """
    Estrutura padrão para listagens paginadas.

    Exemplo de resposta:
    {
        "items": [...],
        "total": 150,
        "page": 1,
        "page_size": 20,
        "pages": 8
    }
    """
    items: list
    total: int
    page: int
    page_size: int
    pages: int
