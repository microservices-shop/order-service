import structlog
from faststream.rabbit import RabbitRouter

from src.messaging.broker import timeout_check_queue, timeout_exchange
from src.messaging.schemas import PaymentWaitMessageSchema

logger = structlog.get_logger(__name__)

router = RabbitRouter()


@router.subscriber(
    queue=timeout_check_queue,
    exchange=timeout_exchange,
)
async def process_order_timeout(msg: PaymentWaitMessageSchema) -> None:
    """
    Consumer для обработки таймаутов неоплаченных заказов.
    Срабатывает, когда сообщение из order.payment.wait истекает по TTL (15 мин)
    и попадает через DLX в order.timeout.check.
    """
    logger.info(
        "processing_order_timeout",
        order_id=str(msg.order_id),
        message_id=str(msg.message_id),
    )

    # Заглушка

    logger.info("order_timeout_processed_stub", order_id=str(msg.order_id))
