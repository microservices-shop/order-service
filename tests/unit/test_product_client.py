import uuid
from unittest.mock import AsyncMock, call

import httpx
import pytest

from src.exceptions import OrderServiceException, OutOfStockException
from src.schemas.internal import (
    ProductReserveItemRequestSchema,
    ProductReserveResponseSchema,
)
from src.services.product_client import ProductClient


class TestProductClient:
    """Тесты для ProductClient, покрывающие успешные сценарии, парсинг, ошибки 400 и retry-политику."""

    @pytest.fixture
    def product_client(self, mock_httpx_client: AsyncMock) -> ProductClient:
        return ProductClient(client=mock_httpx_client)

    @pytest.fixture
    def order_id(self) -> uuid.UUID:
        return uuid.uuid4()

    @pytest.fixture
    def reserve_items(self) -> list[ProductReserveItemRequestSchema]:
        return [
            ProductReserveItemRequestSchema(product_id=1, quantity=2),
            ProductReserveItemRequestSchema(product_id=2, quantity=1),
        ]

    async def test_reserve_success(
        self,
        product_client: ProductClient,
        mock_httpx_client: AsyncMock,
        order_id: uuid.UUID,
        reserve_items: list[ProductReserveItemRequestSchema],
    ):
        """Успешный запрос возвращает список ProductReserveResponseSchema и проверяет тело запроса."""
        mock_response = httpx.Response(
            200,
            json=[
                {"product_id": 1, "name": "Item A", "price": 10000, "quantity": 2},
                {"product_id": 2, "name": "Item B", "price": 25000, "quantity": 1},
            ],
        )
        mock_response.request = httpx.Request("POST", "http://test")
        mock_httpx_client.post.return_value = mock_response

        response = await product_client.reserve(order_id, reserve_items)

        assert len(response) == 2
        assert all(isinstance(r, ProductReserveResponseSchema) for r in response)
        assert response[0].product_id == 1
        assert response[0].name == "Item A"
        assert response[0].price == 10000

        # Проверка, что POST-тело правильное
        mock_httpx_client.post.assert_called_once()
        call_kwargs = mock_httpx_client.post.call_args.kwargs
        assert "json" in call_kwargs
        assert call_kwargs["json"]["order_id"] == str(order_id)
        assert len(call_kwargs["json"]["items"]) == 2
        assert call_kwargs["json"]["items"][0]["product_id"] == 1

    async def test_reserve_400_raises_out_of_stock(
        self,
        product_client: ProductClient,
        mock_httpx_client: AsyncMock,
        mock_sleep: AsyncMock,
        order_id: uuid.UUID,
        reserve_items: list[ProductReserveItemRequestSchema],
    ):
        """При ответе HTTP 400 клиент должен выбросить OutOfStockException без retry."""
        mock_response = httpx.Response(
            400, json={"detail": "Product is running out of stock"}
        )
        mock_response.request = httpx.Request("POST", "http://test")
        mock_httpx_client.post.return_value = mock_response

        with pytest.raises(OutOfStockException) as exc_info:
            await product_client.reserve(order_id, reserve_items)

        assert "Product is running out of stock" in str(exc_info.value)
        assert mock_httpx_client.post.call_count == 1
        assert mock_sleep.call_count == 0

    async def test_reserve_network_error_retries_fail(
        self,
        product_client: ProductClient,
        mock_httpx_client: AsyncMock,
        mock_sleep: AsyncMock,
        order_id: uuid.UUID,
        reserve_items: list[ProductReserveItemRequestSchema],
    ):
        """Сетевая ошибка (RequestError) триггерит 3 попытки, после чего выбрасывается OrderServiceException."""
        mock_httpx_client.post.side_effect = httpx.RequestError(
            "Connection lost completely"
        )

        with pytest.raises(OrderServiceException) as exc_info:
            await product_client.reserve(order_id, reserve_items)

        assert "Product Service is temporarily unavailable" in str(exc_info.value)
        assert "Connection lost completely" in str(exc_info.value)
        assert mock_httpx_client.post.call_count == 3
        assert mock_sleep.call_count == 2

    async def test_reserve_http_500_no_retry(
        self,
        product_client: ProductClient,
        mock_httpx_client: AsyncMock,
        mock_sleep: AsyncMock,
        order_id: uuid.UUID,
        reserve_items: list[ProductReserveItemRequestSchema],
    ):
        """При HTTPStatusError (например 500) сразу летит OrderServiceException без retry."""
        mock_request = httpx.Request("POST", "http://test")
        mock_response = httpx.Response(500, request=mock_request)
        mock_httpx_client.post.return_value = mock_response

        with pytest.raises(OrderServiceException) as exc_info:
            await product_client.reserve(order_id, reserve_items)

        assert "Product Service returned error: 500" in str(exc_info.value)
        assert mock_httpx_client.post.call_count == 1
        assert mock_sleep.call_count == 0

    async def test_reserve_backoff_delays(
        self,
        product_client: ProductClient,
        mock_httpx_client: AsyncMock,
        mock_sleep: AsyncMock,
        order_id: uuid.UUID,
        reserve_items: list[ProductReserveItemRequestSchema],
    ):
        """Проверка экспоненциального бэкоффа задержек: 0.5s -> 1.0s -> 2.0s."""
        mock_httpx_client.post.side_effect = httpx.RequestError("Timeout here")

        with pytest.raises(OrderServiceException):
            await product_client.reserve(order_id, reserve_items)

        # Вызовы sleep: 0.5 * (2**(1-1)) = 0.5; 0.5 * (2**(2-1)) = 1.0
        assert mock_sleep.call_args_list == [
            call(0.5),
            call(1.0),
        ]
