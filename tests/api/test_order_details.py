import uuid
import pytest
from httpx import AsyncClient

from src.db.models import OrderStatus
from tests.service.helpers import create_order_in_db


class TestOrderDetails:
    """Тесты эндпоинта GET /api/v1/orders/{order_id}."""

    async def test_get_order_details_returns_200(
        self, test_client: AsyncClient, async_session, user_id
    ):
        """Успешное получение деталей завершённого заказа."""
        order_id = await create_order_in_db(
            async_session, user_id=user_id, status=OrderStatus.completed
        )

        response = await test_client.get(
            f"/api/v1/orders/{order_id}", headers={"X-User-Id": str(user_id)}
        )

        assert response.status_code == 200
        data = response.json()
        assert data["id"] == str(order_id)
        assert len(data["items"]) == 2  # дефолт в helpers.py

        assert "total_price" in data
        assert "created_at" in data

        item = data["items"][0]
        assert "product_id" in item
        assert "quantity" in item
        assert "unit_price" in item
        assert "product_name" in item
        assert "product_image" in item

    @pytest.mark.parametrize(
        "status_code",
        [
            OrderStatus.awaiting_payment,
            OrderStatus.reserving,
            OrderStatus.cancelled_timeout,
            OrderStatus.failed_out_of_stock,
            OrderStatus.failed_empty_cart,
        ],
    )
    async def test_get_order_details_not_completed_returns_404(
        self, test_client: AsyncClient, async_session, user_id, status_code
    ):
        """Возвращает 404, если заказ существует, но не в статусе completed."""
        order_id = await create_order_in_db(
            async_session, user_id=user_id, status=status_code
        )

        response = await test_client.get(
            f"/api/v1/orders/{order_id}", headers={"X-User-Id": str(user_id)}
        )

        assert response.status_code == 404
        assert response.json()["detail"] == "Order not found"

    async def test_get_order_details_nonexistent_returns_404(
        self, test_client: AsyncClient, user_id
    ):
        """Обращение к несуществующему заказу возвращает 404."""
        nonexistent_id = uuid.uuid4()
        response = await test_client.get(
            f"/api/v1/orders/{nonexistent_id}", headers={"X-User-Id": str(user_id)}
        )
        assert response.status_code == 404

    async def test_get_order_details_other_user_returns_404(
        self, test_client: AsyncClient, async_session, user_id, another_user_id
    ):
        """Попытка посмотреть чужой завершённый заказ возвращает 404."""
        order_id = await create_order_in_db(
            async_session, user_id=user_id, status=OrderStatus.completed
        )

        # Вызываем endpoint от лица another_user_id
        response = await test_client.get(
            f"/api/v1/orders/{order_id}", headers={"X-User-Id": str(another_user_id)}
        )
        assert response.status_code == 404

    async def test_get_order_details_invalid_uuid_in_path_returns_422(
        self, test_client: AsyncClient, user_id
    ):
        """Невалидный UUID в пути возвращает 422 (отлов на уровне FastAPI)."""
        response = await test_client.get(
            "/api/v1/orders/not-a-uuid", headers={"X-User-Id": str(user_id)}
        )
        assert response.status_code == 422

    async def test_get_order_details_without_user_id_returns_401(
        self, test_client: AsyncClient
    ):
        """Отсутствие X-User-Id приводит к 401."""
        order_id = uuid.uuid4()
        response = await test_client.get(f"/api/v1/orders/{order_id}")
        assert response.status_code == 401

    async def test_get_order_details_with_invalid_user_id_returns_401(
        self, test_client: AsyncClient
    ):
        """Невалидный X-User-Id приводит к 401."""
        order_id = uuid.uuid4()
        response = await test_client.get(
            f"/api/v1/orders/{order_id}", headers={"X-User-Id": "invalid-uuid"}
        )
        assert response.status_code == 401
