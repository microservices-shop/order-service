from unittest.mock import AsyncMock, patch

import pytest
from httpx import AsyncClient, ASGITransport

from src.main import app
from src.api.dependencies import get_db, get_cart_client, get_product_client


@pytest.fixture(scope="function")
async def test_client(async_session, mock_cart_client, mock_product_client):
    """Асинхронный HTTP-клиент для тестирования эндпоинтов."""

    async def override_db():
        yield async_session

    app.dependency_overrides[get_db] = override_db
    app.dependency_overrides[get_cart_client] = lambda: mock_cart_client
    app.dependency_overrides[get_product_client] = lambda: mock_product_client

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        yield client

    app.dependency_overrides.clear()


@pytest.fixture(autouse=True)
def mock_publishers():
    """Мокает все RabbitMQ publishers для api-тестов."""
    with (
        patch("src.services.order.publish_payment_wait", new_callable=AsyncMock) as pw,
        patch(
            "src.services.order.publish_cart_items_remove", new_callable=AsyncMock
        ) as cr,
        patch(
            "src.services.order.publish_reserve_release", new_callable=AsyncMock
        ) as rr,
    ):
        yield {
            "publish_payment_wait": pw,
            "publish_cart_items_remove": cr,
            "publish_reserve_release": rr,
        }
