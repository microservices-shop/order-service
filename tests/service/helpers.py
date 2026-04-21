import uuid
from datetime import datetime

from src.db.models import OrderStatus
from src.repositories.order import OrderRepository
from src.schemas.internal import OrderItemSnapshotSchema


async def create_order_in_db(
    session,
    user_id: uuid.UUID,
    *,
    status: OrderStatus = OrderStatus.awaiting_payment,
    total_price: int = 200_000,
    idempotency_key: uuid.UUID | None = None,
    expires_at: datetime | None = None,
    items_data: list[OrderItemSnapshotSchema] | None = None,
) -> uuid.UUID:
    """Вставляет заказ напрямую через репозиторий, минуя бизнес-логику."""
    repo = OrderRepository(session)
    key = idempotency_key or uuid.uuid4()
    order = await repo.create(user_id, key)

    update_fields: dict = {"status": status, "total_price": total_price}
    if expires_at is not None:
        update_fields["expires_at"] = expires_at
    await repo.update(order_id=order.id, **update_fields)

    if items_data is None:
        items_data = [
            OrderItemSnapshotSchema(
                product_id=1,
                quantity=2,
                unit_price=50_000,
                product_name="Product 1",
                product_image="https://example.com/1.jpg",
            ),
            OrderItemSnapshotSchema(
                product_id=2,
                quantity=2,
                unit_price=50_000,
                product_name="Product 2",
                product_image="https://example.com/2.jpg",
            ),
        ]

    await repo.create_items(order_id=order.id, items=items_data)

    await session.commit()
    return order.id
