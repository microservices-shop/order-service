import uuid
from pydantic import BaseModel, ConfigDict, Field


class CartItemSelectedResponseSchema(BaseModel):
    """Выбранный товар из корзины."""

    product_id: int = Field(ge=1, description="ID товара")
    quantity: int = Field(ge=1, description="Количество")

    model_config = ConfigDict(from_attributes=True)


class ProductReserveItemRequestSchema(BaseModel):
    """Товар для запроса резервирования."""

    product_id: int = Field(ge=1, description="ID товара")
    quantity: int = Field(ge=1, description="Количество")


class ProductReserveRequestSchema(BaseModel):
    """Запрос на резервирование товаров."""

    order_id: uuid.UUID = Field(description="ID заказа")
    items: list[ProductReserveItemRequestSchema] = Field(
        min_length=1, description="Товары для резерва"
    )


class ProductReserveResponseSchema(BaseModel):
    """Актуальные данные товара после резервирования (снапшот)."""

    product_id: int = Field(ge=1, description="ID товара")
    image_url: str | None = Field(default=None, description="URL фото товара")
    name: str = Field(min_length=1, max_length=255, description="Название товара")
    price: int = Field(ge=0, description="Цена в копейках на момент резерва")
    quantity: int = Field(ge=1, description="Зарезервированное количество")

    model_config = ConfigDict(from_attributes=True)


class OrderItemSnapshotSchema(BaseModel):
    """Внутренняя схема для сохранения снапшота товара в БД."""

    product_id: int = Field(ge=1, description="ID товара")
    product_name: str = Field(
        min_length=1, max_length=255, description="Название товара"
    )
    product_image: str | None = Field(default=None, description="URL фото товара")
    unit_price: int = Field(ge=0, description="Цена за ед. товара")
    quantity: int = Field(ge=1, description="Количество")
