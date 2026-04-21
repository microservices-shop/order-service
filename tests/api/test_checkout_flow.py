from httpx import AsyncClient


from tests.factories.order_factories import make_cart_items, make_reserve_response


class TestCheckoutFlow:
    """Тесты эндпоинта POST /api/v1/orders/checkout."""

    async def test_checkout_returns_201(
        self,
        test_client: AsyncClient,
        mock_cart_client,
        mock_product_client,
        user_id,
        idempotency_key,
    ):
        """Успешный checkout возвращает 201 Created с ожидаемыми полями."""
        # Подготовка данных
        cart_items = make_cart_items(count=2)
        reserve_response = make_reserve_response(cart_items)

        mock_cart_client.get_selected_items.return_value = cart_items
        mock_product_client.reserve.return_value = reserve_response

        # Отправка запроса
        response = await test_client.post(
            "/api/v1/orders/checkout",
            headers={
                "X-User-Id": str(user_id),
                "Idempotency-Key": str(idempotency_key),
            },
        )

        assert response.status_code == 201
        data = response.json()
        assert "order_id" in data
        assert data["status"] == "awaiting_payment"
        assert data["total_price"] == sum(
            r.price * r.quantity for r in reserve_response
        )
        assert len(data["items"]) == 2

        # Проверяем структуру элементов
        item = data["items"][0]
        assert "product_id" in item
        assert "quantity" in item
        assert "unit_price" in item

    async def test_checkout_without_user_id_returns_401(
        self, test_client: AsyncClient, idempotency_key
    ):
        """Отсутствие заголовка X-User-Id приводит к 401."""
        response = await test_client.post(
            "/api/v1/orders/checkout",
            headers={"Idempotency-Key": str(idempotency_key)},
        )
        assert response.status_code == 401
        assert response.json()["detail"] == "X-User-Id header is required"

    async def test_checkout_with_invalid_user_id_returns_401(
        self, test_client: AsyncClient, idempotency_key
    ):
        """Невалидный X-User-Id (не UUID) приводит к 401."""
        response = await test_client.post(
            "/api/v1/orders/checkout",
            headers={
                "X-User-Id": "invalid-uuid",
                "Idempotency-Key": str(idempotency_key),
            },
        )
        assert response.status_code == 401
        assert response.json()["detail"] == "X-User-Id header must be a valid UUID"

    async def test_checkout_without_idempotency_key_returns_400(
        self, test_client: AsyncClient, user_id
    ):
        """Отсутствие заголовка Idempotency-Key приводит к 400."""
        response = await test_client.post(
            "/api/v1/orders/checkout",
            headers={"X-User-Id": str(user_id)},
        )
        assert response.status_code == 400
        assert response.json()["detail"] == "Idempotency-Key header is required"

    async def test_checkout_with_invalid_idempotency_key_returns_400(
        self, test_client: AsyncClient, user_id
    ):
        """Невалидный Idempotency-Key (не UUID) приводит к 400."""
        response = await test_client.post(
            "/api/v1/orders/checkout",
            headers={
                "X-User-Id": str(user_id),
                "Idempotency-Key": "invalid-uuid",
            },
        )
        assert response.status_code == 400
        assert (
            response.json()["detail"] == "Idempotency-Key header must be a valid UUID"
        )
