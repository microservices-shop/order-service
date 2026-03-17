"""Публикация сообщений в RabbitMQ."""

import uuid

from src.logger import get_logger
from src.messaging.broker import broker, payment_wait_queue, timeout_exchange
from src.messaging.schemas import PaymentWaitMessageSchema

logger = get_logger(__name__)


async def publish_payment_wait(order_id: uuid.UUID) -> None:
    """Публикует сообщение в очередь order.payment.wait.

    Запускает 15-минутный таймер. По истечении TTL сообщение
    через DLX попадает в order.timeout.check.
    """
    message = PaymentWaitMessageSchema(order_id=order_id)

    await broker.publish(
        message=message,
        queue=payment_wait_queue,
        exchange=timeout_exchange,
    )

    logger.info(
        "payment_wait_published",
        order_id=str(order_id),
        message_id=str(message.message_id),
    )
