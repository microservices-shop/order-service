"""Pydantic-схемы для сообщений RabbitMQ."""

import uuid
from datetime import datetime, timezone

from pydantic import BaseModel, Field


class PaymentWaitMessageSchema(BaseModel):
    """Сообщение в очередь order.payment.wait - запускает таймер оплаты."""

    message_id: uuid.UUID = Field(
        default_factory=uuid.uuid4, description="ID сообщения для дедупликации"
    )
    timestamp: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc), description="Время отправки"
    )
    order_id: uuid.UUID = Field(..., description="ID заказа")
