"""
app/core/exceptions.py

Exceções de domínio do BarrioERP.

CONCEITO — Exceções de Domínio vs HTTPException:
    HTTPException é uma exceção do FastAPI — ela sabe sobre HTTP (status codes).
    Exceções de domínio são agnósticas a HTTP — elas dizem O QUE deu errado
    em termos de negócio, não COMO responder.

    Separação de responsabilidades:
    - Service lança: AuthenticationError("Credenciais inválidas")
    - Endpoint ou handler converte para: HTTP 401

    Por que essa separação importa?
    Se amanhã você criar uma CLI ou um job assíncrono que usa o mesmo Service,
    ele não vai receber HTTPException — vai receber a exceção de domínio
    e pode tratar do jeito que fizer sentido no contexto.

FLUXO:
    Service lança BarrioError
         ↓
    main.py tem @app.exception_handler(BarrioError)
         ↓
    FastAPI chama o handler correto
         ↓
    Handler retorna JSONResponse com status code apropriado
"""

from typing import Any
from uuid import UUID


class BarrioError(Exception):
    """
    Exceção base de todas as exceções de domínio do BarrioERP.

    Toda exceção de negócio herda desta classe.
    O `code` é uma string legível por máquina (ex: "NOT_FOUND").
    O `message` é uma string legível por humanos (ex: "Usuário não encontrado").
    """

    def __init__(self, message: str, code: str | None = None) -> None:
        super().__init__(message)
        self.message = message
        self.code = code or self.__class__.__name__


class NotFoundError(BarrioError):
    """Recurso não encontrado. HTTP 404."""

    def __init__(self, resource: str, identifier: Any) -> None:
        super().__init__(f"{resource} not found: {identifier}", "NOT_FOUND")
        self.resource = resource
        self.identifier = identifier


class ConflictError(BarrioError):
    """Conflito de dados (ex: slug duplicado). HTTP 409."""

    def __init__(self, message: str) -> None:
        super().__init__(message, "CONFLICT")


class OptimisticLockError(BarrioError):
    """
    Conflito de versão — dois usuários editaram o mesmo registro.
    HTTP 409.

    O cliente deve recarregar o recurso e tentar novamente.
    """

    def __init__(self, resource: str) -> None:
        super().__init__(
            f"{resource} was modified by another request. Please retry.",
            "OPTIMISTIC_LOCK",
        )


class AuthenticationError(BarrioError):
    """
    Credenciais inválidas ou token expirado/inválido. HTTP 401.

    Mensagem genérica intencional: não revelamos se o e-mail existe.
    "E-mail não encontrado" seria uma informação valiosa para atacantes.
    """

    def __init__(self, message: str = "Invalid credentials") -> None:
        super().__init__(message, "AUTHENTICATION_ERROR")


class ForbiddenError(BarrioError):
    """Usuário autenticado mas sem permissão. HTTP 403."""

    def __init__(self, message: str = "Access denied") -> None:
        super().__init__(message, "FORBIDDEN")


class ValidationError(BarrioError):
    """Dados inválidos que passaram pelo Pydantic mas falharam na regra de negócio. HTTP 422."""

    def __init__(self, message: str) -> None:
        super().__init__(message, "VALIDATION_ERROR")


class BusinessRuleError(BarrioError):
    """Violação de regra de negócio (ex: mesa já ocupada). HTTP 422."""

    def __init__(self, message: str) -> None:
        super().__init__(message, "BUSINESS_RULE_VIOLATION")


class TenantError(BarrioError):
    """Contexto de tenant não definido ou inválido. HTTP 400."""

    def __init__(self, message: str = "Tenant context not set") -> None:
        super().__init__(message, "TENANT_ERROR")
