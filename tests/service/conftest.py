from unittest.mock import AsyncMock, patch

import pytest

from src.repositories.order import OrderRepository
from src.services.order import OrderService


@pytest.fixture
def order_repository(async_session) -> OrderRepository:
    """Создаёт реальный репозиторий с подключением к реальной PostgreSQL через testcontainers."""
    return OrderRepository(async_session)


@pytest.fixture
def order_service(async_session, mock_cart_client, mock_product_client) -> OrderService:
    """Создаёт OrderService с реальной БД и моками внешних клиентов."""
    return OrderService(
        session=async_session,
        cart_client=mock_cart_client,
        product_client=mock_product_client,
    )


@pytest.fixture(autouse=True)
def mock_publishers():
    """Заменяет все RabbitMQ-паблишеры моками для сервисных тестов."""
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
