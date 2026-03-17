import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class OrderItemResponseSchema(BaseModel):
    """Снапшот товара в составе заказа."""

    product_id: int = Field(..., description="ID товара", example=1)
    quantity: int = Field(..., description="Количество", example=2)
    unit_price: int = Field(
        ..., description="Цена за 1 шт. в копейках на момент покупки", example=100000
    )
    product_name: str = Field(
        ..., description="Название товара на момент покупки", example="iPhone 15"
    )

    model_config = ConfigDict(from_attributes=True)


class OrderResponseSchema(BaseModel):
    """Полное представление заказа."""

    id: uuid.UUID = Field(..., description="ID заказа")
    user_id: uuid.UUID = Field(..., description="ID пользователя")
    idempotency_key: uuid.UUID = Field(..., description="Ключ идемпотентности")
    status: str = Field(..., description="Статус заказа", example="awaiting_payment")
    total_price: int = Field(..., description="Сумма заказа в копейках", example=250000)
    created_at: datetime = Field(..., description="Дата создания")
    updated_at: datetime = Field(..., description="Дата обновления")
    items: list[OrderItemResponseSchema] = Field(
        default_factory=list, description="Товары в заказе (снапшоты)"
    )

    model_config = ConfigDict(from_attributes=True)


class CheckoutResponseSchema(BaseModel):
    """Ответ на успешное оформление заказа."""

    order_id: uuid.UUID = Field(..., description="ID созданного заказа")
    status: str = Field(..., description="Статус заказа", example="awaiting_payment")
    total_price: int = Field(..., description="Сумма заказа в копейках", example=250000)
