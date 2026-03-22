import uuid
from pydantic import BaseModel, ConfigDict, Field


class CartItemSelectedResponseSchema(BaseModel):
    """Выбранный товар из корзины."""

    product_id: int = Field(description="ID товара")
    quantity: int = Field(description="Количество")

    model_config = ConfigDict(from_attributes=True)


class ProductReserveItemRequestSchema(BaseModel):
    """Товар для запроса резервирования."""

    product_id: int = Field(description="ID товара")
    quantity: int = Field(description="Количество")


class ProductReserveRequestSchema(BaseModel):
    """Запрос на резервирование товаров."""

    order_id: uuid.UUID = Field(description="ID заказа")
    items: list[ProductReserveItemRequestSchema] = Field(
        description="Товары для резерва"
    )


class ProductReserveResponseSchema(BaseModel):
    """Актуальные данные товара после резервирования (снапшот)."""

    product_id: int = Field(description="ID товара")
    image_url: str | None = Field(default=None, description="URL фото товара")
    name: str = Field(description="Название товара")
    price: int = Field(description="Цена в копейках на момент резерва")
    quantity: int = Field(description="Зарезервированное количество")

    model_config = ConfigDict(from_attributes=True)


class OrderItemSnapshotSchema(BaseModel):
    """Внутренняя схема для сохранения снапшота товара в БД."""

    product_id: int = Field(description="ID товара")
    product_name: str = Field(description="Название товара")
    product_image: str | None = Field(default=None, description="URL фото товара")
    unit_price: int = Field(description="Цена за ед. товара")
    quantity: int = Field(description="Количество")
