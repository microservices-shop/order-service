import uuid
from datetime import datetime, timedelta, UTC

from src.db.models import OrderStatus
from tests.service.helpers import create_order_in_db
from src.repositories.order import OrderRepository


class TestProcessTimeout:
    """Тесты метода OrderService.process_timeout()."""

    async def test_timeout_nonexistent_order_does_nothing(
        self, order_service, mock_publishers
    ):
        random_id = uuid.uuid4()
        # Вызов не должен упасть с ошибкой
        await order_service.process_timeout(order_id=random_id)

        # Убеждаемся, что никакие события не публиковались
        mock_publishers["publish_reserve_release"].assert_not_called()

    async def test_timeout_completed_order_ignored(
        self, order_service, async_session, user_id, mock_publishers
    ):
        """Завершённые заказы игнорируются при обработке таймаута."""
        order_id = await create_order_in_db(
            async_session, user_id, status=OrderStatus.completed
        )

        await order_service.process_timeout(order_id=order_id)

        # Проверяем, что статус не изменился
        repo = OrderRepository(async_session)
        order = await repo.get_by_id(order_id)
        assert order.status == OrderStatus.completed

        mock_publishers["publish_reserve_release"].assert_not_called()

    async def test_timeout_awaiting_payment_expired_cancels(
        self, order_service, async_session, user_id, mock_publishers
    ):
        """Просроченный таймер для awaiting_payment переводит заказ в cancelled_timeout и публикует событие."""
        expired_time = datetime.now(UTC) - timedelta(minutes=5)
        order_id = await create_order_in_db(
            async_session,
            user_id,
            status=OrderStatus.awaiting_payment,
            expires_at=expired_time,
        )

        await order_service.process_timeout(order_id=order_id)

        repo = OrderRepository(async_session)
        order = await repo.get_by_id(order_id)
        assert order.status == OrderStatus.cancelled_timeout

        mock_publishers["publish_reserve_release"].assert_awaited_once_with(
            order_id=order_id
        )

    async def test_timeout_reserving_status_expired_cancels(
        self, order_service, async_session, user_id, mock_publishers
    ):
        """Проверка State Transition: если заказ застрял в reserving и таймер вышел, он отменяется."""
        expired_time = datetime.now(UTC) - timedelta(minutes=1)
        order_id = await create_order_in_db(
            async_session,
            user_id,
            status=OrderStatus.reserving,
            expires_at=expired_time,
        )

        await order_service.process_timeout(order_id=order_id)

        repo = OrderRepository(async_session)
        order = await repo.get_by_id(order_id)
        assert order.status == OrderStatus.cancelled_timeout

        mock_publishers["publish_reserve_release"].assert_awaited_once_with(
            order_id=order_id
        )

    async def test_timeout_awaiting_payment_extended_ignored(
        self, order_service, async_session, user_id, mock_publishers
    ):
        """Если expires_at лежит в будущем (таймер был продлен), старое событие игнорируется."""
        future_time = datetime.now(UTC) + timedelta(minutes=5)
        order_id = await create_order_in_db(
            async_session,
            user_id,
            status=OrderStatus.awaiting_payment,
            expires_at=future_time,
        )

        await order_service.process_timeout(order_id=order_id)

        repo = OrderRepository(async_session)
        order = await repo.get_by_id(order_id)
        # Статус не должен поменяться
        assert order.status == OrderStatus.awaiting_payment

        mock_publishers["publish_reserve_release"].assert_not_called()

    async def test_timeout_with_none_expires_at_cancels_order(
        self, order_service, async_session, user_id, mock_publishers
    ):
        """Если expires_at == None для невалидного статуса, заказ отменяется."""
        order_id = await create_order_in_db(
            async_session, user_id, status=OrderStatus.awaiting_payment
        )
        repo = OrderRepository(async_session)
        await repo.update(order_id, expires_at=None)
        await async_session.commit()

        await order_service.process_timeout(order_id=order_id)

        order = await repo.get_by_id(order_id)
        assert order.status == OrderStatus.cancelled_timeout

        mock_publishers["publish_reserve_release"].assert_awaited_once_with(
            order_id=order_id
        )
