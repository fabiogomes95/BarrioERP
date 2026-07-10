"""Testes do AuthService — autenticação e geração de tokens."""

from unittest.mock import AsyncMock, MagicMock
from uuid import UUID

import pytest

from app.models.user import User, UserRole
from app.models.company import Company
from app.schemas.auth import LoginRequest
from app.services.auth_service import AuthService
from app.core.exceptions import AuthenticationError


@pytest.fixture
def service(mock_session):
    return AuthService(session=mock_session)


def make_company(**kwargs) -> MagicMock:
    m = MagicMock(spec=Company)
    m.id = UUID("00000000-0000-0000-0000-000000000001")
    m.name = "Bar do Zé"
    for k, v in kwargs.items():
        setattr(m, k, v)
    return m


def make_user(**kwargs) -> MagicMock:
    m = MagicMock(spec=User)
    m.id = UUID("00000000-0000-0000-0000-000000000003")
    m.company_id = UUID("00000000-0000-0000-0000-000000000001")
    m.email = "garcom@bar.com"
    m.password_hash = "$2b$12$hash"
    m.name = "Garçom"
    m.role = UserRole.WAITER
    m.is_active = True
    for k, v in kwargs.items():
        setattr(m, k, v)
    return m


class TestLogin:
    async def test_login_success(self, service, mock_session, monkeypatch):
        user = make_user()
        company = make_company()

        service.user_repo.get_by_email = AsyncMock(return_value=user)
        mock_session.get = AsyncMock(return_value=company)

        monkeypatch.setattr("app.services.auth_service.verify_password", lambda pw, h: True)
        monkeypatch.setattr("app.services.auth_service.create_access_token", lambda subject, extra: "fake-jwt-token")

        result = await service.login(LoginRequest(email="garcom@bar.com", password="senha123"))

        assert result.access_token == "fake-jwt-token"

    async def test_login_invalid_email(self, service, mock_session, monkeypatch):
        service.user_repo.get_by_email = AsyncMock(return_value=None)
        monkeypatch.setattr("app.services.auth_service.verify_password", lambda pw, h: False)

        with pytest.raises(AuthenticationError, match="E-mail ou senha incorretos"):
            await service.login(LoginRequest(email="naoexiste@bar.com", password="qualquer"))

    async def test_login_wrong_password(self, service, mock_session, monkeypatch):
        user = make_user()
        service.user_repo.get_by_email = AsyncMock(return_value=user)
        monkeypatch.setattr("app.services.auth_service.verify_password", lambda pw, h: False)

        with pytest.raises(AuthenticationError, match="E-mail ou senha incorretos"):
            await service.login(LoginRequest(email="garcom@bar.com", password="senha_errada"))

    async def test_login_inactive_user(self, service, mock_session, monkeypatch):
        user = make_user(is_active=False)
        company = make_company()
        service.user_repo.get_by_email = AsyncMock(return_value=user)
        mock_session.get = AsyncMock(return_value=company)

        monkeypatch.setattr("app.services.auth_service.verify_password", lambda pw, h: True)
        monkeypatch.setattr("app.services.auth_service.create_access_token", lambda subject, extra: "fake-jwt-token")

        result = await service.login(LoginRequest(email="garcom@bar.com", password="senha123"))
        assert result.access_token == "fake-jwt-token"

    async def test_login_company_not_found(self, service, mock_session, monkeypatch):
        """Login funciona mesmo se a company não for encontrada — company_name fica None."""
        user = make_user()
        service.user_repo.get_by_email = AsyncMock(return_value=user)
        mock_session.get = AsyncMock(return_value=None)
        monkeypatch.setattr("app.services.auth_service.verify_password", lambda pw, h: True)
        monkeypatch.setattr("app.services.auth_service.create_access_token", lambda subject, extra: "fake-jwt-token")

        result = await service.login(LoginRequest(email="garcom@bar.com", password="senha123"))
        assert result.access_token == "fake-jwt-token"

    async def test_login_creates_token_with_correct_claims(self, service, mock_session, monkeypatch):
        user = make_user()
        company = make_company(name="Bar do Zé")

        service.user_repo.get_by_email = AsyncMock(return_value=user)
        mock_session.get = AsyncMock(return_value=company)

        captured = {}

        def fake_create_token(*, subject, extra):
            captured["subject"] = subject
            captured["extra"] = extra
            return "fake-jwt"

        monkeypatch.setattr("app.services.auth_service.verify_password", lambda pw, h: True)
        monkeypatch.setattr("app.services.auth_service.create_access_token", fake_create_token)

        await service.login(LoginRequest(email="garcom@bar.com", password="senha123"))

        assert captured["subject"] == user.id
        assert captured["extra"]["company_id"] == str(user.company_id)
        assert captured["extra"]["role"] == "waiter"
        assert captured["extra"]["name"] == "Garçom"
        assert captured["extra"]["company_name"] == "Bar do Zé"
