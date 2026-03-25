"""Инициализация RabbitMQ брокера и объявление очередей."""

import asyncio

from faststream.rabbit import RabbitBroker, RabbitExchange, RabbitQueue
from faststream.rabbit.schemas import ExchangeType

from src.config import settings
from src.logger import get_logger

logger = get_logger(__name__)

broker = RabbitBroker(settings.RABBITMQ_URL)

# DLX: когда TTL истекает, сообщение попадает в exchange -> order.timeout.check
timeout_exchange = RabbitExchange(
    "order.timeout.dlx",
    type=ExchangeType.DIRECT,
)

# Очередь-таймер: сообщение лежит 15 мин, затем через DLX уходит в order.timeout.check
payment_wait_queue = RabbitQueue(
    "order.payment.wait",
    durable=True,
    arguments={
        "x-message-ttl": settings.ORDER_PAYMENT_TIMEOUT_MS,
        "x-dead-letter-exchange": "order.timeout.dlx",
        "x-dead-letter-routing-key": "order.timeout.check",
    },
)

# Очередь для обработки таймаутов, привязанная к DLX по routing_key
timeout_check_queue = RabbitQueue(
    "order.timeout.check",
    durable=True,
    routing_key="order.timeout.check",
)

# Очередь для удаления купленных товаров из корзины (слушает Cart Service)
cart_items_remove_queue = RabbitQueue(
    "cart.items.remove",
    durable=True,
)

# Очередь для возврата товаров в Product Service при таймауте
reserve_release_queue = RabbitQueue(
    "product.reserve.release",
    durable=True,
)

_MAX_RETRIES = 5


async def connect_broker() -> None:
    """Подключение к RabbitMQ с retry и экспоненциальным backoff."""
    for attempt in range(1, _MAX_RETRIES + 1):
        try:
            await broker.connect()
            await broker.start()
            await broker.declare_queue(payment_wait_queue)
            logger.info("rabbitmq_broker_connected")
            return
        except Exception as e:
            if attempt == _MAX_RETRIES:
                logger.critical("rabbitmq_broker_connect_failed", error=str(e))
                raise
            logger.warning(
                "rabbitmq_broker_retry",
                attempt=attempt,
                max_retries=_MAX_RETRIES,
                error=str(e),
            )
            await asyncio.sleep(2**attempt)
