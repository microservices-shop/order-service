"""Инициализация RabbitMQ брокера и объявление очередей."""

from faststream.rabbit import RabbitBroker, RabbitExchange, RabbitQueue
from faststream.rabbit.schemas import ExchangeType

from src.config import settings

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
