"""Публикация сообщений в RabbitMQ."""

import asyncio
import uuid

from src.logger import get_logger
from src.messaging.broker import broker, cart_items_remove_queue, payment_wait_queue
from src.messaging.schemas import (
    CartItemRemoveSchema,
    CartItemsRemoveMessageSchema,
    PaymentWaitMessageSchema,
)

logger = get_logger(__name__)

_MAX_RETRIES = 3
_RETRY_BACKOFF_BASE = 0.5


async def publish_payment_wait(order_id: uuid.UUID) -> None:
    """Публикует сообщение в очередь order.payment.wait.

    Запускает 15-минутный таймер. По истечении TTL сообщение
    через DLX попадает в order.timeout.check.
    """
    message = PaymentWaitMessageSchema(order_id=order_id)

    for attempt in range(1, _MAX_RETRIES + 1):
        try:
            await broker.publish(
                message=message,
                queue=payment_wait_queue,
            )
            break
        except Exception as exc:
            if attempt == _MAX_RETRIES:
                raise
            logger.warning(
                "rabbitmq_publish_retry",
                order_id=str(order_id),
                attempt=attempt,
                max_retries=_MAX_RETRIES,
                error=str(exc),
            )
            await asyncio.sleep(_RETRY_BACKOFF_BASE * (2 ** (attempt - 1)))

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

    for attempt in range(1, _MAX_RETRIES + 1):
        try:
            await broker.publish(
                message=message,
                queue=cart_items_remove_queue,
            )
            break
        except Exception as exc:
            if attempt == _MAX_RETRIES:
                raise
            logger.warning(
                "rabbitmq_publish_retry_cart_remove",
                order_id=str(order_id),
                attempt=attempt,
                max_retries=_MAX_RETRIES,
                error=str(exc),
            )
            await asyncio.sleep(_RETRY_BACKOFF_BASE * (2 ** (attempt - 1)))

    logger.info(
        "cart_items_remove_published",
        order_id=str(order_id),
        user_id=str(user_id),
        message_id=str(message.message_id),
    )
