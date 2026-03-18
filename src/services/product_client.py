import asyncio
import uuid

import httpx
import structlog

from src.config import settings
from src.exceptions import OrderServiceException, OutOfStockException
from src.schemas.internal import (
    ProductReserveItemRequestSchema,
    ProductReserveRequestSchema,
    ProductReserveResponseSchema,
)

logger = structlog.get_logger(__name__)


_MAX_RETRIES = 3
_RETRY_BACKOFF_BASE = 0.5  # секунды: 0.5 -> 1.0 -> 2.0


class ProductClient:
    """Клиент для запросов к internal API Product Service."""

    def __init__(self, client: httpx.AsyncClient) -> None:
        self._base_url = settings.PRODUCT_SERVICE_URL.rstrip("/")
        self.client = client

    async def reserve(
        self, order_id: uuid.UUID, items: list[ProductReserveItemRequestSchema]
    ) -> list[ProductReserveResponseSchema]:
        """Зарезервировать товары через Product Service.

        Запрашивает POST /internal/products/reserve.
        При 400 бросает OutOfStockException (ретрай бессмысленен).
        При сетевых ошибках выполняет до 3 попыток с экспоненциальным backoff.
        """
        url = f"{self._base_url}/internal/products/reserve"
        payload = ProductReserveRequestSchema(
            order_id=order_id, items=items
        ).model_dump(mode="json")
        last_exc: Exception | None = None

        for attempt in range(1, _MAX_RETRIES + 1):
            try:
                response = await self.client.post(url, json=payload)

                if response.status_code == httpx.codes.BAD_REQUEST:
                    # детерминированная ошибка 400
                    raise OutOfStockException()

                response.raise_for_status()
                return [
                    ProductReserveResponseSchema.model_validate(item)
                    for item in response.json()
                ]

            except OutOfStockException:
                raise

            except (httpx.ConnectError, httpx.TimeoutException) as exc:
                last_exc = exc
                logger.warning(
                    "product_service_unavailable_retry",
                    order_id=str(order_id),
                    attempt=attempt,
                    max_retries=_MAX_RETRIES,
                    error=str(exc),
                )
                if attempt < _MAX_RETRIES:
                    await asyncio.sleep(_RETRY_BACKOFF_BASE * (2 ** (attempt - 1)))

            except httpx.HTTPStatusError as exc:
                logger.error(
                    "product_service_error",
                    order_id=str(order_id),
                    status_code=exc.response.status_code,
                    error=str(exc),
                )
                raise OrderServiceException(
                    f"Product Service returned error: {exc.response.status_code}"
                )

        logger.error(
            "product_service_unavailable",
            order_id=str(order_id),
            attempts=_MAX_RETRIES,
            error=str(last_exc),
        )
        raise OrderServiceException(
            f"Product Service is temporarily unavailable: {last_exc}"
        )
