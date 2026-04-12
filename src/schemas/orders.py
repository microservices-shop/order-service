import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field
from src.config import settings


class OrderItemPreviewSchema(BaseModel):
    """Превью товара в карточке заказа на странице «Мои заказы» (/orders).

    Отображается как миниатюра фото с ценой под ней.
    """

    product_image: str | None = Field(
        default=None, description="URL фото товара на момент покупки"
    )
    unit_price: int = Field(
        ge=0, description="Цена за 1 шт. в копейках", examples=[100000]
    )

    model_config = ConfigDict(from_attributes=True)


class OrderItemResponseSchema(BaseModel):
    """Детальный снапшот товара.

    Отображается как карточка с фото, названием, ценой и количеством.
    """

    product_id: int = Field(ge=1, description="ID товара", examples=[1])
    quantity: int = Field(ge=1, description="Количество", examples=[2])
    unit_price: int = Field(
        ge=0,
        description="Цена за 1 шт. в копейках на момент покупки",
        examples=[100000],
    )
    product_name: str = Field(
        min_length=1,
        max_length=255,
        description="Название товара на момент покупки",
        examples=["iPhone 15"],
    )
    product_image: str | None = Field(
        default=None, description="URL фото товара на момент покупки"
    )

    model_config = ConfigDict(from_attributes=True)


class OrderListResponseSchema(BaseModel):
    """Карточка заказа на странице «Мои заказы» (/orders).

    Содержит дату, сумму и превью товаров (миниатюры с ценами).
    """

    id: uuid.UUID = Field(description="ID заказа")
    total_price: int = Field(
        ge=0, description="Сумма заказа в копейках", examples=[250000]
    )
    created_at: datetime = Field(description="Дата создания")
    items: list[OrderItemPreviewSchema] = Field(
        min_length=1,
        description="Превью товаров (фото + цена)",
    )

    model_config = ConfigDict(from_attributes=True)


class OrderDetailResponseSchema(BaseModel):
    """Детальная страница заказа (/orders/{id}).

    Содержит дату, сумму и полный список товаров с фото, названием,
    ценой и количеством.
    """

    id: uuid.UUID = Field(description="ID заказа")
    total_price: int = Field(
        ge=0, description="Сумма заказа в копейках", examples=[250000]
    )
    created_at: datetime = Field(description="Дата создания")
    items: list[OrderItemResponseSchema] = Field(
        min_length=1,
        description="Товары в заказе (снапшоты)",
    )

    model_config = ConfigDict(from_attributes=True)


class PaginatedOrdersResponseSchema(BaseModel):
    """Пагинированный ответ для страницы «Мои заказы» (/orders).

    Содержит массив заказов текущей страницы и метаданные
    для построения цифровой пагинации на фронтенде.
    """

    total_orders: int = Field(
        description="Общее количество завершённых заказов", examples=[23]
    )
    page: int = Field(description="Номер текущей страницы", examples=[1])
    page_size: int = Field(
        description="Количество заказов на странице",
        ge=1,
        le=settings.MAX_PAGE_SIZE,
        examples=[10],
    )
    pages: int = Field(description="Общее количество страниц", examples=[3])
    items: list[OrderListResponseSchema] = Field(
        min_length=1,
        description="Заказы на текущей странице",
    )


class CheckoutResponseSchema(BaseModel):
    """Ответ на успешное оформление заказа."""

    order_id: uuid.UUID = Field(description="ID созданного заказа")
    status: str = Field(description="Статус заказа", examples=["awaiting_payment"])
    total_price: int = Field(
        ge=0, description="Сумма заказа в копейках", examples=[250000]
    )
    items: list[OrderItemResponseSchema] = Field(
        min_length=1,
        description="Товары в заказе (снапшоты)",
    )


class PayResponseSchema(BaseModel):
    status: str = Field(description="Статус оплаты", examples=["completed"])
