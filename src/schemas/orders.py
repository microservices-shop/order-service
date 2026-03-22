import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class OrderItemPreviewSchema(BaseModel):
    """Превью товара в карточке заказа на странице «Мои заказы» (/orders).

    Отображается как миниатюра фото с ценой под ней.
    """

    product_image: str | None = Field(
        description="URL фото товара на момент покупки",
    )
    unit_price: int = Field(description="Цена за 1 шт. в копейках", examples=[100000])

    model_config = ConfigDict(from_attributes=True)


class OrderItemResponseSchema(BaseModel):
    """Детальный снапшот товара на странице «Детали заказа» (/orders/{id}).

    Отображается как карточка с фото, названием, ценой и количеством.
    """

    product_id: int = Field(description="ID товара", examples=[1])
    quantity: int = Field(description="Количество", examples=[2])
    unit_price: int = Field(
        description="Цена за 1 шт. в копейках на момент покупки", examples=[100000]
    )
    product_name: str = Field(
        description="Название товара на момент покупки", examples=["iPhone 15"]
    )
    product_image: str | None = Field(
        description="URL фото товара на момент покупки",
    )

    model_config = ConfigDict(from_attributes=True)


class OrderListResponseSchema(BaseModel):
    """Карточка заказа на странице «Мои заказы» (/orders).

    Содержит дату, сумму и превью товаров (миниатюры с ценами).
    """

    id: uuid.UUID = Field(description="ID заказа")
    total_price: int = Field(description="Сумма заказа в копейках", examples=[250000])
    created_at: datetime = Field(description="Дата создания")
    items: list[OrderItemPreviewSchema] = Field(
        description="Превью товаров (фото + цена)"
    )

    model_config = ConfigDict(from_attributes=True)


class OrderDetailResponseSchema(BaseModel):
    """Детальная страница заказа (/orders/{id}).

    Содержит дату, сумму и полный список товаров с фото, названием,
    ценой и количеством.
    """

    id: uuid.UUID = Field(description="ID заказа")
    total_price: int = Field(description="Сумма заказа в копейках", examples=[250000])
    created_at: datetime = Field(description="Дата создания")
    items: list[OrderItemResponseSchema] = Field(
        default_factory=list, description="Товары в заказе (снапшоты)"
    )

    model_config = ConfigDict(from_attributes=True)


class CheckoutResponseSchema(BaseModel):
    """Ответ на успешное оформление заказа."""

    order_id: uuid.UUID = Field(description="ID созданного заказа")
    status: str = Field(description="Статус заказа", examples=["awaiting_payment"])
    total_price: int = Field(description="Сумма заказа в копейках", examples=[250000])


class PayResponseSchema(BaseModel):
    status: str = Field(description="Статус оплаты", examples=["completed"])
