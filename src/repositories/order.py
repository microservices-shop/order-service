import uuid

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from src.db.models import OrderModel, OrderItemModel
from src.schemas.internal import OrderItemSnapshotSchema


class OrderRepository:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def create(
        self, user_id: uuid.UUID, idempotency_key: uuid.UUID
    ) -> OrderModel:
        """Создает новый заказ в статусе reserving."""
        order = OrderModel(user_id=user_id, idempotency_key=idempotency_key)
        self.session.add(order)
        await self.session.flush()
        await self.session.refresh(order)
        return order

    async def get_by_idempotency_key(
        self, idempotency_key: uuid.UUID
    ) -> OrderModel | None:
        """Находит заказ по ключу идемпотентности."""
        query = (
            select(OrderModel)
            .where(OrderModel.idempotency_key == idempotency_key)
            .options(selectinload(OrderModel.items))
        )
        result = await self.session.execute(query)
        return result.scalar_one_or_none()

    async def update(self, order_id: uuid.UUID, **kwargs) -> None:
        """Обновление полей заказа."""
        if not kwargs:
            return

        query = update(OrderModel).where(OrderModel.id == order_id).values(**kwargs)
        await self.session.execute(query)

    async def create_items(
        self, order_id: uuid.UUID, items: list[OrderItemSnapshotSchema]
    ) -> None:
        """Создает снапшоты товаров для заказа."""
        for item in items:
            order_item = OrderItemModel(
                order_id=order_id,
                product_id=item.product_id,
                quantity=item.quantity,
                unit_price=item.unit_price,
                product_name=item.product_name,
            )
            self.session.add(order_item)

        await self.session.flush()
