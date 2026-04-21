import uuid
import pytest

from src.db.models import OrderStatus
from src.exceptions import OrderNotFoundException
from tests.service.helpers import create_order_in_db


class TestGetOrderDetails:
    """Тесты метода OrderService.get_order_details()."""

    async def test_get_order_details_success(
        self, order_service, async_session, user_id
    ):
        """Возвращает информацию о заказе со всеми вложенными items для статуса completed."""
        # Создаем заказ с 2 товарами
        order_id = await create_order_in_db(
            async_session, user_id, status=OrderStatus.completed, total_price=200_000
        )

        result = await order_service.get_order_details(
            user_id=user_id, order_id=order_id
        )

        assert result.id == order_id
        assert result.total_price == 200_000
        assert len(result.items) == 2

        # Проверяем, что вложенные данные (items) корректно сериализуются
        assert result.items[0].product_id == 1
        assert result.items[0].quantity == 2
        assert result.items[0].unit_price == 50_000
        assert result.items[0].product_name == "Product 1"

    @pytest.mark.parametrize(
        "invalid_status",
        [
            OrderStatus.awaiting_payment,
            OrderStatus.reserving,
            OrderStatus.cancelled_timeout,
            OrderStatus.failed_empty_cart,
            OrderStatus.failed_out_of_stock,
        ],
    )
    async def test_get_order_details_not_completed_raises_exception(
        self, order_service, async_session, user_id, invalid_status
    ):
        """Если заказ существует, но не завершен (любой другой статус), он недоступен для просмотра."""
        order_id = await create_order_in_db(
            async_session, user_id, status=invalid_status
        )

        with pytest.raises(OrderNotFoundException):
            await order_service.get_order_details(user_id=user_id, order_id=order_id)

    async def test_get_order_details_other_user_raises_exception(
        self, order_service, async_session, user_id, another_user_id
    ):
        """Пользователь не может посмотреть существующий выполненный чужой заказ."""
        # Заказ принадлежит another_user_id
        order_id = await create_order_in_db(
            async_session, another_user_id, status=OrderStatus.completed
        )

        # Пытаемся получить от имени user_id
        with pytest.raises(OrderNotFoundException):
            await order_service.get_order_details(user_id=user_id, order_id=order_id)

    async def test_get_order_details_nonexistent_id_raises_exception(
        self, order_service, user_id
    ):
        """При запросе по случайному (несуществующему) ID выбрасывается исключение."""
        random_order_id = uuid.uuid4()

        with pytest.raises(OrderNotFoundException):
            await order_service.get_order_details(
                user_id=user_id, order_id=random_order_id
            )
