import pytest
from httpx import AsyncClient

from datetime import datetime, timedelta, UTC
from sqlalchemy import update
from src.db.models import OrderModel

from src.db.models import OrderStatus
from tests.service.helpers import create_order_in_db


class TestOrdersList:
    """Тесты эндпоинта GET /api/v1/orders."""

    async def test_get_orders_returns_200_and_only_completed(
        self, test_client: AsyncClient, async_session, user_id
    ):
        """Возвращает 200 OK и статус завершенных заказов (фильтрует остальные)."""
        # 1 Завершенный заказ
        await create_order_in_db(
            async_session, user_id=user_id, status=OrderStatus.completed
        )
        # 2 Незавершенных заказа (не должны попасть в выдачу)
        await create_order_in_db(
            async_session, user_id=user_id, status=OrderStatus.awaiting_payment
        )
        await create_order_in_db(
            async_session, user_id=user_id, status=OrderStatus.cancelled_timeout
        )

        response = await test_client.get(
            "/api/v1/orders", headers={"X-User-Id": str(user_id)}
        )

        assert response.status_code == 200
        data = response.json()
        assert data["total_orders"] == 1
        assert len(data["items"]) == 1

    async def test_get_orders_sorts_newest_first(
        self, test_client: AsyncClient, async_session, user_id
    ):
        """Заказы сортируются от новых к старым."""
        # В рамках одной транзакции (как работают тесты) SQL CURRENT_TIMESTAMP не меняется.
        # Поэтому принудительно обновим created_at вручную для гарантии детерминированности.
        id1 = await create_order_in_db(
            async_session, user_id=user_id, status=OrderStatus.completed
        )
        id2 = await create_order_in_db(
            async_session, user_id=user_id, status=OrderStatus.completed
        )
        id3 = await create_order_in_db(
            async_session, user_id=user_id, status=OrderStatus.completed
        )

        now = datetime.now(UTC)
        await async_session.execute(
            update(OrderModel)
            .where(OrderModel.id == id1)
            .values(created_at=now - timedelta(days=2))
        )
        await async_session.execute(
            update(OrderModel)
            .where(OrderModel.id == id2)
            .values(created_at=now - timedelta(days=1))
        )
        await async_session.execute(
            update(OrderModel).where(OrderModel.id == id3).values(created_at=now)
        )
        await async_session.commit()

        response = await test_client.get(
            "/api/v1/orders", headers={"X-User-Id": str(user_id)}
        )

        assert response.status_code == 200
        items = response.json()["items"]
        assert len(items) == 3
        # Проверяем, что первый заказ в списке - самый последний добавленный
        assert items[0]["id"] == str(id3)
        assert items[1]["id"] == str(id2)
        assert items[2]["id"] == str(id1)

    async def test_get_orders_empty_returns_empty_list(
        self, test_client: AsyncClient, user_id
    ):
        """Если заказов нет, возвращается пустой список и total_orders=0."""
        response = await test_client.get(
            "/api/v1/orders", headers={"X-User-Id": str(user_id)}
        )
        assert response.status_code == 200
        data = response.json()
        assert data["total_orders"] == 0
        assert data["items"] == []

    @pytest.mark.parametrize(
        "page_size, status_code",
        [
            (0, 422),  # Ниже границы
            (1, 200),  # Граница (минимум)
            (100, 200),  # Граница (максимум)
            (101, 422),  # Выше границы
        ],
    )
    async def test_get_orders_page_size_boundaries(
        self, test_client: AsyncClient, user_id, page_size, status_code
    ):
        """Проверка граничных значений (Boundary Value Analysis) для page_size."""
        response = await test_client.get(
            f"/api/v1/orders?page_size={page_size}", headers={"X-User-Id": str(user_id)}
        )
        assert response.status_code == status_code

    @pytest.mark.parametrize("page, status_code", [(-1, 422), (0, 422), (1, 200)])
    async def test_get_orders_page_boundaries(
        self, test_client: AsyncClient, user_id, page, status_code
    ):
        """Проверка граничных значений для page."""
        response = await test_client.get(
            f"/api/v1/orders?page={page}", headers={"X-User-Id": str(user_id)}
        )
        assert response.status_code == status_code

    async def test_get_orders_without_user_id_returns_401(
        self, test_client: AsyncClient
    ):
        """Отсутствие X-User-Id приводит к 401."""
        response = await test_client.get("/api/v1/orders")
        assert response.status_code == 401

    async def test_get_orders_with_invalid_user_id_returns_401(
        self, test_client: AsyncClient
    ):
        """Невалидный X-User-Id приводит к 401."""
        response = await test_client.get(
            "/api/v1/orders", headers={"X-User-Id": "invalid-uuid"}
        )
        assert response.status_code == 401
