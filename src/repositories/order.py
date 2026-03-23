import uuid

from sqlalchemy import select, update, func
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from src.db.models import OrderModel, OrderItemModel, OrderStatus
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
                product_image=item.product_image,
            )
            self.session.add(order_item)

        await self.session.flush()

    async def get_by_user_id_and_order_id(
        self, user_id: uuid.UUID, order_id: uuid.UUID, status: OrderStatus | None = None
    ) -> OrderModel | None:
        """Находит заказ по ID пользователя и ID заказа с опциональной фильтрацией по статусу."""
        query = (
            select(OrderModel)
            .where(OrderModel.user_id == user_id, OrderModel.id == order_id)
            .options(selectinload(OrderModel.items))
        )

        if status:
            query = query.where(OrderModel.status == status)

        result = await self.session.execute(query)
        return result.scalar_one_or_none()

    async def get_completed_by_user_id(
        self, user_id: uuid.UUID, page: int, page_size: int
    ) -> tuple[list[OrderModel], int]:
        """Возвращает завершённые заказы пользователя (новые первыми)."""
        count_query = select(func.count(OrderModel.id)).where(
            OrderModel.user_id == user_id,
            OrderModel.status == OrderStatus.completed,
        )
        total_result = await self.session.execute(count_query)
        total_orders = total_result.scalar_one()

        offset = (page - 1) * page_size
        limit = page_size

        query = (
            select(OrderModel)
            .where(
                OrderModel.user_id == user_id,
                OrderModel.status == OrderStatus.completed,
            )
            .options(selectinload(OrderModel.items))
            .order_by(OrderModel.created_at.desc())
            .offset(offset)
            .limit(limit)
        )
        result = await self.session.execute(query)
        orders = list(result.scalars().all())

        return orders, total_orders

    async def get_by_id(self, order_id: uuid.UUID) -> OrderModel | None:
        """Находит заказ по ID."""
        query = (
            select(OrderModel)
            .where(OrderModel.id == order_id)
            .options(selectinload(OrderModel.items))
        )
        result = await self.session.execute(query)
        return result.scalar_one_or_none()
