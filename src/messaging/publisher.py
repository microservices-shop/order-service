"""Публикация сообщений в RabbitMQ."""

import asyncio
import uuid

from src.logger import get_logger
from src.messaging.broker import (
    broker,
    cart_items_remove_queue,
    payment_wait_queue,
    reserve_release_queue,
)
from src.messaging.schemas import (
    CartItemRemoveSchema,
    CartItemsRemoveMessageSchema,
    PaymentWaitMessageSchema,
    ReserveReleaseMessageSchema,
)

logger = get_logger(__name__)

_MAX_RETRIES = 3
_RETRY_BACKOFF_BASE = 0.5


async def _publish_with_retry(message: dict, queue, *, context: str) -> None:
    """Публикует сообщение с retry и экспоненциальным backoff."""
    for attempt in range(1, _MAX_RETRIES + 1):
        try:
            await broker.publish(message=message, queue=queue)
            return
        except Exception as exc:
            if attempt == _MAX_RETRIES:
                raise
            logger.warning(
                "rabbitmq_publish_retry",
                context=context,
                attempt=attempt,
                max_retries=_MAX_RETRIES,
                error=str(exc),
            )
            await asyncio.sleep(_RETRY_BACKOFF_BASE * (2 ** (attempt - 1)))


async def publish_payment_wait(order_id: uuid.UUID) -> None:
    """Публикует сообщение в очередь order.payment.wait.

    Запускает 15-минутный таймер. По истечении TTL сообщение
    через DLX попадает в order.timeout.check.
    """
    message = PaymentWaitMessageSchema(order_id=order_id)
    await _publish_with_retry(
        message.model_dump(mode="json"),
        payment_wait_queue,
        context=f"payment_wait:{order_id}",
    )
    logger.info(
        "payment_wait_published",
        order_id=str(order_id),
        message_id=str(message.message_id),
    )


async def publish_cart_items_remove(
    order_id: uuid.UUID, user_id: uuid.UUID, items: list[CartItemRemoveSchema]
) -> None:
    """Публикует сообщение в очередь cart.items.remove."""
    message = CartItemsRemoveMessageSchema(
        order_id=order_id,
        user_id=user_id,
        items=items,
    )
    await _publish_with_retry(
        message.model_dump(mode="json"),
        cart_items_remove_queue,
        context=f"cart_remove:{order_id}",
    )
    logger.info(
        "cart_items_remove_published",
        order_id=str(order_id),
        user_id=str(user_id),
        message_id=str(message.message_id),
    )


async def publish_reserve_release(order_id: uuid.UUID) -> None:
    """Публикует сообщение в очередь product.reserve.release."""
    message = ReserveReleaseMessageSchema(order_id=order_id)
    await _publish_with_retry(
        message.model_dump(mode="json"),
        reserve_release_queue,
        context=f"reserve_release:{order_id}",
    )
    logger.info(
        "reserve_release_published",
        order_id=str(order_id),
        message_id=str(message.message_id),
    )
