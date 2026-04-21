import uuid
from httpx import AsyncClient

from src.db.models import OrderStatus
from tests.service.helpers import create_order_in_db


class TestPayFlow:
    """Тесты эндпоинта POST /api/v1/orders/{order_id}/pay."""

    async def test_pay_returns_200(
        self, test_client: AsyncClient, async_session, user_id
    ):
        """Успешная оплата заказа возвращает 200 OK и status=completed."""
        # Подготовка данных: создаем заказ в статусе awaiting_payment
        order_id = await create_order_in_db(
            async_session, user_id=user_id, status=OrderStatus.awaiting_payment
        )

        # Отправка запроса
        response = await test_client.post(
            f"/api/v1/orders/{order_id}/pay",
            headers={"X-User-Id": str(user_id)},
        )

        # Проверки
        assert response.status_code == 200
        assert response.json()["status"] == "completed"

    async def test_pay_without_user_id_returns_401(self, test_client: AsyncClient):
        """Отсутствие заголовка X-User-Id приводит к 401."""
        order_id = uuid.uuid4()
        response = await test_client.post(f"/api/v1/orders/{order_id}/pay")
        assert response.status_code == 401
        assert response.json()["detail"] == "X-User-Id header is required"

    async def test_pay_with_invalid_user_id_returns_401(self, test_client: AsyncClient):
        """Невалидный X-User-Id (не UUID) приводит к 401."""
        order_id = uuid.uuid4()
        response = await test_client.post(
            f"/api/v1/orders/{order_id}/pay",
            headers={"X-User-Id": "invalid-uuid"},
        )
        assert response.status_code == 401
        assert response.json()["detail"] == "X-User-Id header must be a valid UUID"

    async def test_pay_invalid_uuid_in_path_returns_422(
        self, test_client: AsyncClient, user_id
    ):
        """Невалидный UUID заказа в пути приводит к 422 Unprocessable Entity от FastAPI."""
        response = await test_client.post(
            "/api/v1/orders/not-a-uuid/pay",
            headers={"X-User-Id": str(user_id)},
        )
        assert response.status_code == 422

    async def test_pay_nonexistent_order_returns_404(
        self, test_client: AsyncClient, user_id
    ):
        """Оплата несуществующего заказа возвращает 404."""
        nonexistent_id = uuid.uuid4()
        response = await test_client.post(
            f"/api/v1/orders/{nonexistent_id}/pay",
            headers={"X-User-Id": str(user_id)},
        )
        assert response.status_code == 404
        assert response.json()["detail"] == "Order not found"

    async def test_pay_invalid_status_returns_400(
        self, test_client: AsyncClient, async_session, user_id
    ):
        """Оплата отмененного заказа (cancelled_timeout) возвращает 400 Bad Request."""
        order_id = await create_order_in_db(
            async_session, user_id=user_id, status=OrderStatus.cancelled_timeout
        )

        response = await test_client.post(
            f"/api/v1/orders/{order_id}/pay",
            headers={"X-User-Id": str(user_id)},
        )
        assert response.status_code == 400

    async def test_pay_reserving_status_returns_409(
        self, test_client: AsyncClient, async_session, user_id
    ):
        """Оплата заказа в процессе создания (reserving) возвращает 409 Conflict."""
        order_id = await create_order_in_db(
            async_session, user_id=user_id, status=OrderStatus.reserving
        )

        response = await test_client.post(
            f"/api/v1/orders/{order_id}/pay",
            headers={"X-User-Id": str(user_id)},
        )
        assert response.status_code == 409

    async def test_pay_other_user_order_returns_404(
        self, test_client: AsyncClient, async_session, user_id, another_user_id
    ):
        """Попытка оплатить чужой заказ возвращает 404."""
        order_id = await create_order_in_db(
            async_session, user_id=user_id, status=OrderStatus.awaiting_payment
        )

        # Вызываем endpoint от лица another_user_id
        response = await test_client.post(
            f"/api/v1/orders/{order_id}/pay",
            headers={"X-User-Id": str(another_user_id)},
        )
        assert response.status_code == 404
        assert response.json()["detail"] == "Order not found"
