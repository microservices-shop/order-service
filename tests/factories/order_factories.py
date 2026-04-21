"""Фабрики для генерации тестовых данных."""

import uuid
from datetime import datetime, timedelta, UTC

from src.db.models import OrderModel, OrderItemModel, OrderStatus
from src.schemas.internal import (
    CartItemSelectedResponseSchema,
    ProductReserveResponseSchema,
)


def make_order(
    user_id: uuid.UUID | None = None,
    idempotency_key: uuid.UUID | None = None,
    status: OrderStatus = OrderStatus.awaiting_payment,
    total_price: int = 100_000,
    items_count: int = 2,
    expires_at: datetime | None = None,
) -> OrderModel:
    """Создаёт OrderModel с вложенными items.

    По умолчанию: заказ в статусе awaiting_payment с 2 товарами.
    """
    order_id = uuid.uuid4()
    order = OrderModel(
        id=order_id,
        user_id=user_id or uuid.uuid4(),
        idempotency_key=idempotency_key or uuid.uuid4(),
        status=status,
        total_price=total_price,
        expires_at=expires_at
        if expires_at is not None
        else datetime.now(UTC) + timedelta(minutes=15),
    )
    order.items = [
        make_order_item(order_id=order_id, product_id=i + 1) for i in range(items_count)
    ]
    return order


def make_order_item(
    order_id: uuid.UUID | None = None,
    product_id: int = 1,
    quantity: int = 2,
    unit_price: int = 50_000,
    product_name: str | None = None,
    product_image: str | None = None,
) -> OrderItemModel:
    """Создаёт OrderItemModel, представляющий снапшот товара."""
    return OrderItemModel(
        id=uuid.uuid4(),
        order_id=order_id or uuid.uuid4(),
        product_id=product_id,
        quantity=quantity,
        unit_price=unit_price,
        product_name=product_name or f"Test Product {product_id}",
        product_image=product_image or f"https://example.com/img/{product_id}.jpg",
    )


def make_cart_items(count: int = 2) -> list[CartItemSelectedResponseSchema]:
    """Генерирует список выбранных товаров из корзины."""
    return [
        CartItemSelectedResponseSchema(product_id=i + 1, quantity=2)
        for i in range(count)
    ]


def make_reserve_response(
    cart_items: list[CartItemSelectedResponseSchema], unit_price: int = 50_000
) -> list[ProductReserveResponseSchema]:
    """Генерирует ответ Product Service на резервирование.

    Цена фиксирована: 50 000 за штуку, URL и name генерируются из product_id.
    """
    return [
        ProductReserveResponseSchema(
            product_id=item.product_id,
            name=f"Product {item.product_id}",
            image_url=f"https://example.com/{item.product_id}.jpg",
            price=unit_price,
            quantity=item.quantity,
        )
        for item in cart_items
    ]
