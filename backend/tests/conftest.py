from unittest.mock import AsyncMock, MagicMock

import pytest
from sqlalchemy.ext.asyncio import AsyncSession


@pytest.fixture
def mock_session() -> AsyncMock:
    session = AsyncMock(spec=AsyncSession)
    session.flush = AsyncMock()
    session.get = AsyncMock()
    session.execute = AsyncMock()
    return session


@pytest.fixture
def company_id() -> str:
    return "00000000-0000-0000-0000-000000000001"


@pytest.fixture
def establishment_id() -> str:
    return "00000000-0000-0000-0000-000000000002"


@pytest.fixture
def user_id() -> str:
    return "00000000-0000-0000-0000-000000000003"


@pytest.fixture
def table_id() -> str:
    return "00000000-0000-0000-0000-000000000004"


@pytest.fixture
def order_id() -> str:
    return "00000000-0000-0000-0000-000000000005"


@pytest.fixture
def menu_item_id() -> str:
    return "00000000-0000-0000-0000-000000000006"
