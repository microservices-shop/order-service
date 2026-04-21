from src.db.models import OrderStatus
from tests.service.helpers import create_order_in_db


class TestGetOrders:
    """Тесты метода OrderService.get_orders()."""

    async def test_get_orders_with_results(self, order_service, async_session, user_id):
        """Успешное получение заказов с пагинацией (возвращаются только completed)."""
        # Создаем 3 completed заказа
        order1_id = await create_order_in_db(
            async_session, user_id, status=OrderStatus.completed
        )
        order2_id = await create_order_in_db(
            async_session, user_id, status=OrderStatus.completed
        )
        order3_id = await create_order_in_db(
            async_session, user_id, status=OrderStatus.completed
        )

        # Создаем 1 awaiting_payment, он не должен попасть в выборку
        await create_order_in_db(
            async_session, user_id, status=OrderStatus.awaiting_payment
        )

        # Запрашиваем 1 страницу, размер 2
        result = await order_service.get_orders(user_id=user_id, page=1, page_size=2)

        assert result.total_orders == 3
        # 3 заказа / 2 на страницу = 2 страницы
        assert result.pages == 2
        assert result.page == 1
        assert result.page_size == 2
        assert len(result.items) == 2

        # Убеждаемся, что возвращенные заказы - это именно наши те что completed
        completed_ids = {order1_id, order2_id, order3_id}
        assert result.items[0].id in completed_ids
        assert result.items[1].id in completed_ids

    async def test_get_orders_empty_returns_empty_list(self, order_service, user_id):
        """Если заказов нет, возвращается пустой список и total_orders=0."""
        result = await order_service.get_orders(user_id=user_id, page=1, page_size=10)

        assert result.items == []
        assert result.total_orders == 0
        assert result.pages == 0
        assert result.page == 1
        assert result.page_size == 10

    async def test_get_orders_returns_only_completed(
        self, order_service, async_session, user_id
    ):
        """Проверка изоляции статусов: возвращаются только заказы в статусе completed."""
        await create_order_in_db(async_session, user_id, status=OrderStatus.reserving)
        await create_order_in_db(
            async_session, user_id, status=OrderStatus.awaiting_payment
        )
        await create_order_in_db(
            async_session, user_id, status=OrderStatus.failed_out_of_stock
        )
        await create_order_in_db(
            async_session, user_id, status=OrderStatus.cancelled_timeout
        )

        # Ни один из них не completed
        result = await order_service.get_orders(user_id=user_id, page=1, page_size=10)

        assert result.items == []
        assert result.total_orders == 0

    async def test_get_orders_other_user_isolation(
        self, order_service, async_session, user_id, another_user_id
    ):
        """Чужие заказы не возвращаются пользователю."""
        # Заказы для user_id
        await create_order_in_db(async_session, user_id, status=OrderStatus.completed)
        await create_order_in_db(async_session, user_id, status=OrderStatus.completed)

        # Получаем заказы для another_user_id (у которого их 0)
        result = await order_service.get_orders(
            user_id=another_user_id, page=1, page_size=10
        )

        assert result.items == []
        assert result.total_orders == 0

    async def test_get_orders_out_of_bounds_page(
        self, order_service, async_session, user_id
    ):
        """Запрос страницы за пределами существующих (page > pages)."""
        await create_order_in_db(async_session, user_id, status=OrderStatus.completed)

        # У нас всего 1 заказ, значит 1 страница при page_size=10. Запрашиваем 2-ю
        result = await order_service.get_orders(user_id=user_id, page=2, page_size=10)

        # Результат должен быть пустой список, но total_orders = 1
        assert result.items == []
        assert result.total_orders == 1
        assert result.pages == 1
        assert result.page == 2
