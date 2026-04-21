import uuid
from datetime import datetime, timedelta, UTC
import pytest
from sqlalchemy import select

from src.db.models import OrderModel, OrderStatus
from src.exceptions import (
    InvalidOrderStatusException,
    OrderConflictException,
    OrderNotFoundException,
)
from src.services.order import OrderService
from src.schemas.internal import OrderItemSnapshotSchema
from tests.service.helpers import create_order_in_db


class TestPay:
    """Тесты метода OrderService.pay()."""

    async def test_pay_success(
        self,
        order_service: OrderService,
        mock_publishers,
        user_id,
        async_session,
    ):
        """Успешная оплата: статус переходит в completed, публикуется cart_items_remove."""
        order_id = await create_order_in_db(
            async_session,
            user_id,
            status=OrderStatus.awaiting_payment,
        )

        result = await order_service.pay(user_id, order_id)

        assert result.status == OrderStatus.completed

        # Проверка в БД
        query = select(OrderModel).where(OrderModel.id == order_id)
        db_result = await async_session.execute(query)
        db_order = db_result.scalar_one()
        assert db_order.status == OrderStatus.completed

        # cart_items_remove опубликован
        mock_publishers["publish_cart_items_remove"].assert_awaited_once()

    async def test_pay_already_completed_returns_success(
        self,
        order_service: OrderService,
        mock_publishers,
        user_id,
        async_session,
    ):
        """Повторная оплата заказа в статусе completed возвращает идемпотентный ответ без ошибки."""
        order_id = await create_order_in_db(
            async_session,
            user_id,
            status=OrderStatus.completed,
        )

        result = await order_service.pay(user_id, order_id)

        assert result.status == OrderStatus.completed

        # Повторная публикация НЕ происходит
        mock_publishers["publish_cart_items_remove"].assert_not_awaited()

    async def test_pay_reserving_raises_conflict(
        self,
        order_service: OrderService,
        user_id,
        async_session,
    ):
        """Заказ в статусе reserving вызывает OrderConflictException."""
        order_id = await create_order_in_db(
            async_session,
            user_id,
            status=OrderStatus.reserving,
        )

        with pytest.raises(OrderConflictException):
            await order_service.pay(user_id, order_id)

    @pytest.mark.parametrize(
        "status",
        [
            OrderStatus.cancelled_timeout,
            OrderStatus.failed_out_of_stock,
            OrderStatus.failed_empty_cart,
        ],
    )
    async def test_pay_invalid_status_raises_exception(
        self,
        order_service: OrderService,
        user_id,
        async_session,
        status: OrderStatus,
    ):
        """Оплата заказа в статусах failed/cancelled вызывает InvalidOrderStatusException."""
        order_id = await create_order_in_db(
            async_session,
            user_id,
            status=status,
        )

        with pytest.raises(InvalidOrderStatusException):
            await order_service.pay(user_id, order_id)

    async def test_pay_not_found_raises_exception(
        self,
        order_service: OrderService,
        user_id,
    ):
        """Обращение к несуществующему заказу вызывает OrderNotFoundException."""
        fake_order_id = uuid.uuid4()

        with pytest.raises(OrderNotFoundException):
            await order_service.pay(user_id, fake_order_id)

    @pytest.mark.parametrize(
        "status",
        [
            OrderStatus.awaiting_payment,
            OrderStatus.completed,
            OrderStatus.cancelled_timeout,
            OrderStatus.failed_out_of_stock,
            OrderStatus.failed_empty_cart,
        ],
    )
    async def test_pay_other_user_order_raises_not_found(
        self,
        order_service: OrderService,
        user_id,
        another_user_id,
        async_session,
        status: OrderStatus,
    ):
        """Попытка оплатить чужой заказ (в любом статусе) вызывает OrderNotFoundException."""
        order_id = await create_order_in_db(
            async_session,
            another_user_id,
            status=status,
        )

        with pytest.raises(OrderNotFoundException):
            await order_service.pay(user_id, order_id)

    async def test_pay_cart_remove_publish_fails_but_pay_succeeds(
        self,
        order_service: OrderService,
        mock_publishers,
        user_id,
        async_session,
    ):
        """Ошибка publish_cart_items_remove логируется, но оплата всё равно проходит успешно."""
        order_id = await create_order_in_db(
            async_session,
            user_id,
            status=OrderStatus.awaiting_payment,
        )
        mock_publishers["publish_cart_items_remove"].side_effect = RuntimeError(
            "RabbitMQ down"
        )

        # Оплата НЕ падает
        result = await order_service.pay(user_id, order_id)

        assert result.status == OrderStatus.completed

        # Заказ в БД всё равно completed
        query = select(OrderModel).where(OrderModel.id == order_id)
        db_result = await async_session.execute(query)
        db_order = db_result.scalar_one()
        assert db_order.status == OrderStatus.completed

    async def test_pay_with_zero_price_order(
        self,
        order_service: OrderService,
        mock_publishers,
        user_id,
        async_session,
    ):
        """Оплата заказа с total_price=0 проходит успешно."""
        zero_price_items = [
            OrderItemSnapshotSchema(
                product_id=1,
                quantity=1,
                unit_price=0,
                product_name="Free Product",
                product_image="https://example.com/free.jpg",
            )
        ]
        order_id = await create_order_in_db(
            async_session,
            user_id,
            status=OrderStatus.awaiting_payment,
            total_price=0,
            items_data=zero_price_items,
        )

        result = await order_service.pay(user_id, order_id)

        assert result.status == OrderStatus.completed

    async def test_pay_order_with_empty_items_raises_exception(
        self,
        order_service: OrderService,
        user_id,
        async_session,
    ):
        """Оплата заказа без товаров логически недопустима и вызывает ошибку."""
        order_id = await create_order_in_db(
            async_session,
            user_id,
            status=OrderStatus.awaiting_payment,
            items_data=[],
        )

        with pytest.raises(InvalidOrderStatusException):
            await order_service.pay(user_id, order_id)

    async def test_pay_after_expires_at(
        self,
        order_service: OrderService,
        user_id,
        async_session,
    ):
        """Оплата заказа в awaiting_payment, но с истёкшим expires_at, вызывает InvalidOrderStatusException."""
        expired_time = datetime.now(UTC) - timedelta(seconds=10)

        order_id = await create_order_in_db(
            async_session,
            user_id,
            status=OrderStatus.awaiting_payment,
            expires_at=expired_time,
        )

        with pytest.raises(InvalidOrderStatusException):
            await order_service.pay(user_id, order_id)
