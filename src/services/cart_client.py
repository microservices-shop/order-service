import asyncio
import uuid

import httpx
import structlog

from src.config import settings
from src.exceptions import OrderServiceException
from src.schemas.internal import CartItemSelectedResponseSchema

logger = structlog.get_logger(__name__)

_TIMEOUT = httpx.Timeout(timeout=10.0, connect=5.0)

_MAX_RETRIES = 3
_RETRY_BACKOFF_BASE = 0.5  # секунды: 0.5 -> 1.0 -> 2.0


class CartClient:
    """Клиент для запросов к internal API Cart Service."""

    def __init__(self) -> None:
        self._base_url = settings.CART_SERVICE_URL.rstrip("/")

    async def get_selected_items(
        self, user_id: uuid.UUID
    ) -> list[CartItemSelectedResponseSchema]:
        """Получить выбранные товары из корзины пользователя.

        Запрашивает GET /internal/cart/selected с заголовком X-User-Id.
        При сетевых ошибках выполняет до 3 попыток с экспоненциальным backoff.
        """
        url = f"{self._base_url}/internal/cart/selected"
        headers = {"X-User-Id": str(user_id)}
        last_exc: Exception | None = None

        for attempt in range(1, _MAX_RETRIES + 1):
            try:
                async with httpx.AsyncClient(timeout=_TIMEOUT) as client:
                    response = await client.get(url, headers=headers)

                response.raise_for_status()
                return [
                    CartItemSelectedResponseSchema.model_validate(item)
                    for item in response.json()
                ]

            except (httpx.ConnectError, httpx.TimeoutException) as exc:
                last_exc = exc
                logger.warning(
                    "cart_service_unavailable_retry",
                    user_id=str(user_id),
                    attempt=attempt,
                    max_retries=_MAX_RETRIES,
                    error=str(exc),
                )
                if attempt < _MAX_RETRIES:
                    await asyncio.sleep(_RETRY_BACKOFF_BASE * (2 ** (attempt - 1)))

            except httpx.HTTPStatusError as exc:
                logger.error(
                    "cart_service_error",
                    user_id=str(user_id),
                    status_code=exc.response.status_code,
                    error=str(exc),
                )
                raise OrderServiceException(
                    f"Cart Service returned error: {exc.response.status_code}"
                )

        logger.error(
            "cart_service_unavailable",
            user_id=str(user_id),
            attempts=_MAX_RETRIES,
            error=str(last_exc),
        )
        raise OrderServiceException(
            f"Cart Service is temporarily unavailable: {last_exc}"
        )
