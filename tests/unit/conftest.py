from unittest.mock import AsyncMock, patch

import httpx
import pytest

from src.services.cart_client import CartClient


@pytest.fixture
def mock_httpx_client() -> AsyncMock:
    """Создаёт мок httpx.AsyncClient для изоляции от сети."""
    return AsyncMock(spec=httpx.AsyncClient)


@pytest.fixture
def mock_sleep():
    """Мокает asyncio.sleep для проверки backoff-задержек без реального ожидания."""
    with patch("asyncio.sleep", new_callable=AsyncMock) as mock:
        yield mock


@pytest.fixture
def cart_client(mock_httpx_client: AsyncMock) -> CartClient:
    """Создаёт CartClient с замоканным HTTP-транспортом."""
    return CartClient(client=mock_httpx_client)
