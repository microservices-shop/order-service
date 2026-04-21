import uuid
from unittest.mock import AsyncMock, call

import httpx
import pytest
from pydantic import ValidationError

from src.exceptions import OrderServiceException
from src.schemas.internal import CartItemSelectedResponseSchema
from src.services.cart_client import CartClient


class TestCartClient:
    """Тесты для CartClient, покрывающие успешные сценарии, парсинг, ошибки и retry-политику."""

    async def test_get_selected_items_success(
        self, cart_client: CartClient, mock_httpx_client: AsyncMock, user_id: uuid.UUID
    ):
        """Успешный запрос должен возвращать список CartItemSelectedResponseSchema и передавать правильные заголовки."""
        mock_response = httpx.Response(
            200,
            json=[{"product_id": 1, "quantity": 2}, {"product_id": 42, "quantity": 10}],
        )
        mock_response.request = httpx.Request("GET", "http://test")
        mock_httpx_client.get.return_value = mock_response

        items = await cart_client.get_selected_items(user_id)

        assert len(items) == 2
        assert all(isinstance(i, CartItemSelectedResponseSchema) for i in items)
        assert items[0].product_id == 1
        assert items[0].quantity == 2

        # Проверка, что заголовки переданы правильно
        mock_httpx_client.get.assert_called_once()
        call_kwargs = mock_httpx_client.get.call_args.kwargs
        assert "headers" in call_kwargs
        assert call_kwargs["headers"] == {"X-User-Id": str(user_id)}

    async def test_get_selected_items_empty_cart(
        self, cart_client: CartClient, mock_httpx_client: AsyncMock, user_id: uuid.UUID
    ):
        """Возврат пустой корзины должен корректно парситься в пустой список."""
        mock_response = httpx.Response(200, json=[])
        mock_response.request = httpx.Request("GET", "http://test")
        mock_httpx_client.get.return_value = mock_response

        items = await cart_client.get_selected_items(user_id)

        assert items == []

    async def test_get_selected_items_invalid_payload(
        self, cart_client: CartClient, mock_httpx_client: AsyncMock, user_id: uuid.UUID
    ):
        """Если ответ сервиса содержит невалидные данные, Pydantic должен вызывать ValidationError."""
        mock_response = httpx.Response(
            200, json=[{"product_id": "not_an_int", "quantity": -5}]
        )
        mock_response.request = httpx.Request("GET", "http://test")
        mock_httpx_client.get.return_value = mock_response

        with pytest.raises(ValidationError):
            await cart_client.get_selected_items(user_id)

    async def test_get_selected_items_network_error_retries_fail(
        self,
        cart_client: CartClient,
        mock_httpx_client: AsyncMock,
        mock_sleep: AsyncMock,
        user_id: uuid.UUID,
    ):
        """При RequestError клиент должен сделать 3 попытки, спать между ними и в конце бросить OrderServiceException."""
        mock_httpx_client.get.side_effect = httpx.RequestError("Connection timeout")

        with pytest.raises(OrderServiceException) as exc_info:
            await cart_client.get_selected_items(user_id)

        assert "Cart Service is temporarily unavailable" in str(exc_info.value)
        assert "Connection timeout" in str(exc_info.value)
        assert mock_httpx_client.get.call_count == 3
        # Должно быть 2 вызова sleep: после 1-й и 2-й попыток
        assert mock_sleep.call_count == 2

    async def test_get_selected_items_network_error_recovers(
        self,
        cart_client: CartClient,
        mock_httpx_client: AsyncMock,
        mock_sleep: AsyncMock,
        user_id: uuid.UUID,
    ):
        """Если после RequestError запрос проходит на 2-й или 3-й попытке, данные должны успешно возвращаться."""
        mock_response = httpx.Response(200, json=[{"product_id": 5, "quantity": 1}])
        mock_response.request = httpx.Request("GET", "http://test")

        # 1-й вызов - ошибка, 2-й - ошибка, 3-й - успех
        mock_httpx_client.get.side_effect = [
            httpx.RequestError("Connection drop"),
            httpx.RequestError("Connection timeout"),
            mock_response,
        ]

        items = await cart_client.get_selected_items(user_id)

        assert len(items) == 1
        assert items[0].product_id == 5
        assert mock_httpx_client.get.call_count == 3
        assert mock_sleep.call_count == 2

    async def test_get_selected_items_http_500_no_retry(
        self,
        cart_client: CartClient,
        mock_httpx_client: AsyncMock,
        mock_sleep: AsyncMock,
        user_id: uuid.UUID,
    ):
        """При HTTPStatusError (например, 500 Internal Server Error) retry не выполняются, ошибка бросается сразу."""
        mock_request = httpx.Request("GET", "http://test")
        mock_response = httpx.Response(500, request=mock_request)

        mock_httpx_client.get.return_value = mock_response

        with pytest.raises(OrderServiceException) as exc_info:
            await cart_client.get_selected_items(user_id)

        assert "Cart Service returned error: 500" in str(exc_info.value)
        assert mock_httpx_client.get.call_count == 1
        assert mock_sleep.call_count == 0

    async def test_get_selected_items_backoff_delays(
        self,
        cart_client: CartClient,
        mock_httpx_client: AsyncMock,
        mock_sleep: AsyncMock,
        user_id: uuid.UUID,
    ):
        """Проверка экспоненциального бэкоффа задержек: 0.5s -> 1.0s -> 2.0s."""
        mock_httpx_client.get.side_effect = httpx.RequestError("Connection failure!")

        with pytest.raises(OrderServiceException):
            await cart_client.get_selected_items(user_id)

        # Вызовы sleep: 0.5 * (2**(1-1)) = 0.5
        # Вызовы sleep: 0.5 * (2**(2-1)) = 1.0
        assert mock_sleep.call_args_list == [
            call(0.5),
            call(1.0),
        ]

    async def test_get_selected_items_http_404_no_retry(
        self,
        cart_client: CartClient,
        mock_httpx_client: AsyncMock,
        mock_sleep: AsyncMock,
        user_id: uuid.UUID,
    ):
        """Проверка, что не 5xx ошибки (например 404), также приводят к HTTPStatusError без retry."""
        mock_request = httpx.Request("GET", "http://test")
        mock_response = httpx.Response(404, request=mock_request)
        mock_httpx_client.get.return_value = mock_response

        with pytest.raises(OrderServiceException) as exc_info:
            await cart_client.get_selected_items(user_id)

        assert "Cart Service returned error: 404" in str(exc_info.value)
        assert mock_httpx_client.get.call_count == 1
        assert mock_sleep.call_count == 0
