import uuid
from datetime import datetime, timedelta, UTC
from unittest.mock import AsyncMock

import pytest
from sqlalchemy import select

from src.db.models import OrderModel, OrderStatus
from src.exceptions import (
    EmptyCartException,
    OrderConflictException,
    OutOfStockException,
)
from src.schemas.internal import (
    CartItemSelectedResponseSchema,
    ProductReserveResponseSchema,
)
from src.services.order import OrderService
from tests.factories.order_factories import (
    make_cart_items,
    make_reserve_response,
)
from tests.service.helpers import create_order_in_db


def _setup_checkout_mocks(
    mock_cart_client: AsyncMock,
    mock_product_client: AsyncMock,
    cart_count: int = 2,
    unit_price: int = 50_000,
):
    """Настраивает happy-path моки для checkout."""
    cart_items = make_cart_items(count=cart_count)
    reserve_response = make_reserve_response(cart_items, unit_price)
    mock_cart_client.get_selected_items.return_value = cart_items
    mock_product_client.reserve.return_value = reserve_response
    return cart_items, reserve_response


class TestCheckout:
    """Тесты метода OrderService.checkout()."""

    async def test_checkout_success_creates_order(
        self,
        order_service: OrderService,
        mock_cart_client,
        mock_product_client,
        mock_publishers,
        user_id,
        idempotency_key,
        async_session,
    ):
        """Happy path: заказ создан, товары зарезервированы, снапшоты сохранены, publish вызван."""
        cart_items, reserve_response = _setup_checkout_mocks(
            mock_cart_client, mock_product_client
        )

        result = await order_service.checkout(user_id, idempotency_key)

        # Статус и цена
        assert result.status == OrderStatus.awaiting_payment
        expected_price = sum(item.price * item.quantity for item in reserve_response)
        assert result.total_price == expected_price
        assert len(result.items) == 2

        # Снапшоты сохранены корректно
        assert result.items[0].product_name == "Product 1"
        assert result.items[1].product_name == "Product 2"

        # Publishers вызваны
        mock_publishers["publish_payment_wait"].assert_awaited_once()
        mock_cart_client.get_selected_items.assert_awaited_once_with(user_id)
        mock_product_client.reserve.assert_awaited_once()

        # Проверка в БД
        query = select(OrderModel).where(OrderModel.id == result.order_id)
        db_result = await async_session.execute(query)
        db_order = db_result.scalar_one()
        assert db_order.status == OrderStatus.awaiting_payment
        assert db_order.total_price == expected_price

    async def test_checkout_single_item_cart(
        self,
        order_service: OrderService,
        mock_cart_client,
        mock_product_client,
        mock_publishers,
        user_id,
        idempotency_key,
        async_session,
    ):
        cart_items, reserve_response = _setup_checkout_mocks(
            mock_cart_client, mock_product_client, cart_count=1
        )

        result = await order_service.checkout(user_id, idempotency_key)

        # Статус и цена
        assert result.status == OrderStatus.awaiting_payment
        expected_price = sum(item.price * item.quantity for item in reserve_response)
        assert result.total_price == expected_price
        assert len(result.items) == 1
        assert result.items[0].product_name == "Product 1"

        # Publishers вызваны
        mock_publishers["publish_payment_wait"].assert_awaited_once()
        mock_cart_client.get_selected_items.assert_awaited_once_with(user_id)
        mock_product_client.reserve.assert_awaited_once()

        # Проверка в БД
        query = select(OrderModel).where(OrderModel.id == result.order_id)
        db_result = await async_session.execute(query)
        db_order = db_result.scalar_one()
        assert db_order.status == OrderStatus.awaiting_payment
        assert db_order.total_price == expected_price

    async def test_checkout_zero_price(
        self,
        order_service: OrderService,
        mock_cart_client,
        mock_product_client,
        mock_publishers,
        user_id,
        idempotency_key,
        async_session,
    ):
        cart_items, reserve_response = _setup_checkout_mocks(
            mock_cart_client, mock_product_client, cart_count=1, unit_price=0
        )

        result = await order_service.checkout(user_id, idempotency_key)

        # Статус и цена
        assert result.status == OrderStatus.awaiting_payment
        assert result.total_price == 0
        assert len(result.items) == 1
        assert result.items[0].product_name == "Product 1"

        # Publishers вызваны
        mock_publishers["publish_payment_wait"].assert_awaited_once()
        mock_cart_client.get_selected_items.assert_awaited_once_with(user_id)
        mock_product_client.reserve.assert_awaited_once()

        # Проверка в БД
        query = select(OrderModel).where(OrderModel.id == result.order_id)
        db_result = await async_session.execute(query)
        db_order = db_result.scalar_one()
        assert db_order.status == OrderStatus.awaiting_payment
        assert db_order.total_price == 0

    async def test_checkout_empty_cart_raises_exception(
        self,
        order_service: OrderService,
        mock_cart_client,
        mock_publishers,
        user_id,
        idempotency_key,
        async_session,
    ):
        """Пустая корзина вызывает EmptyCartException, статус заказа обновляется на failed_empty_cart."""
        mock_cart_client.get_selected_items.return_value = []

        with pytest.raises(EmptyCartException):
            await order_service.checkout(user_id, idempotency_key)

        # Статус заказа в БД - failed_empty_cart
        query = select(OrderModel).where(OrderModel.user_id == user_id)
        db_result = await async_session.execute(query)
        db_order = db_result.scalar_one()
        assert db_order.status == OrderStatus.failed_empty_cart

        # publish_payment_wait НЕ вызван
        mock_publishers["publish_payment_wait"].assert_not_awaited()

    async def test_checkout_out_of_stock_raises_exception(
        self,
        order_service: OrderService,
        mock_cart_client,
        mock_product_client,
        mock_publishers,
        user_id,
        idempotency_key,
        async_session,
    ):
        """Товар отсутствует в наличии: вызывается OutOfStockException, статус обновляется на failed_out_of_stock."""
        cart_items = make_cart_items(count=2)
        mock_cart_client.get_selected_items.return_value = cart_items
        mock_product_client.reserve.side_effect = OutOfStockException()

        with pytest.raises(OutOfStockException):
            await order_service.checkout(user_id, idempotency_key)

        # Статус в БД
        query = select(OrderModel).where(OrderModel.user_id == user_id)
        db_result = await async_session.execute(query)
        db_order = db_result.scalar_one()
        assert db_order.status == OrderStatus.failed_out_of_stock

        mock_publishers["publish_payment_wait"].assert_not_awaited()

    async def test_checkout_smart_cart_reuses_order(
        self,
        order_service: OrderService,
        mock_cart_client,
        mock_publishers,
        user_id,
        async_session,
    ):
        """Повторный checkout с тем же составом корзины: переиспользует существующий заказ и продлевает таймер."""
        # Создаём существующий awaiting_payment заказ
        old_order_id = await create_order_in_db(
            async_session,
            user_id,
            status=OrderStatus.awaiting_payment,
            expires_at=datetime.now(UTC) + timedelta(minutes=5),
        )

        # Корзина совпадает с заказом (product_id=1 qty=2, product_id=2 qty=2)
        cart_items = make_cart_items(count=2)
        mock_cart_client.get_selected_items.return_value = cart_items

        result = await order_service.checkout(user_id, uuid.uuid4())

        # Вернулся существующий заказ
        assert result.order_id == old_order_id
        assert result.status == OrderStatus.awaiting_payment

        # Таймер продлён - publish_payment_wait вызван для переиздания таймера
        mock_publishers["publish_payment_wait"].assert_awaited_once()

    async def test_checkout_smart_cart_changed_cart_creates_new(
        self,
        order_service: OrderService,
        mock_cart_client,
        mock_product_client,
        mock_publishers,
        user_id,
        async_session,
    ):
        """Повторный checkout с изменённой корзиной: создаётся новый заказ."""
        # Существующий заказ с product_id=1,2
        await create_order_in_db(
            async_session,
            user_id,
            status=OrderStatus.awaiting_payment,
            expires_at=datetime.now(UTC) + timedelta(minutes=5),
        )

        # Корзина ДРУГАЯ - 3 товара вместо 2
        new_cart = make_cart_items(count=3)
        reserve_resp = make_reserve_response(new_cart)
        mock_cart_client.get_selected_items.return_value = new_cart
        mock_product_client.reserve.return_value = reserve_resp

        result = await order_service.checkout(user_id, uuid.uuid4())

        # Создан новый заказ (не старый)
        assert len(result.items) == 3
        assert result.status == OrderStatus.awaiting_payment

    async def test_checkout_after_cancelled_timeout_creates_new_order(
        self,
        order_service: OrderService,
        mock_cart_client,
        mock_product_client,
        mock_publishers,
        user_id,
        async_session,
    ):
        """Если предыдущий заказ отменён по таймауту, Smart Cart его игнорирует и создаёт новый."""
        # Создаем отмененный заказ
        old_order_id = await create_order_in_db(
            async_session,
            user_id,
            status=OrderStatus.cancelled_timeout,
            expires_at=datetime.now(UTC) - timedelta(minutes=5),
        )

        cart_items, reserve_response = _setup_checkout_mocks(
            mock_cart_client, mock_product_client
        )

        result = await order_service.checkout(user_id, uuid.uuid4())

        # Проверяем, что создан НОВЫЙ заказ, а не вернулся старый
        assert result.order_id != old_order_id
        assert result.status == OrderStatus.awaiting_payment
        assert len(result.items) == 2

    async def test_checkout_smart_cart_multiple_old_orders(
        self,
        order_service: OrderService,
        mock_cart_client,
        mock_product_client,
        mock_publishers,
        user_id,
        async_session,
    ):
        """При наличии нескольких заказов Smart Cart выбирает последний актуальный awaiting_payment."""
        # 1. Старый оплаченный заказ (должен игнорироваться)
        await create_order_in_db(
            async_session,
            user_id,
            status=OrderStatus.completed,
        )

        # 2. Старый отмененный заказ (должен игнорироваться)
        await create_order_in_db(
            async_session,
            user_id,
            status=OrderStatus.cancelled_timeout,
        )

        # 3. Актуальный неоплаченный заказ (именно его должна подхватить Smart Cart)
        valid_order_id = await create_order_in_db(
            async_session,
            user_id,
            status=OrderStatus.awaiting_payment,
            expires_at=datetime.now(UTC) + timedelta(minutes=10),
        )

        # Состав корзины совпадает с товарами из create_order_in_db по умолчанию
        cart_items = make_cart_items(count=2)
        mock_cart_client.get_selected_items.return_value = cart_items

        result = await order_service.checkout(user_id, uuid.uuid4())

        # Проверяем, что подхватился именно актуальный неоплаченный заказ
        assert result.order_id == valid_order_id
        assert result.status == OrderStatus.awaiting_payment

    async def test_checkout_idempotency_reserving_raises_conflict(
        self,
        order_service: OrderService,
        mock_cart_client,
        mock_product_client,
        user_id,
        async_session,
    ):
        """При IntegrityError и заказе в статусе reserving выбрасывается OrderConflictException (409)."""
        idem_key = uuid.uuid4()

        # Создаём заказ в статусе reserving с тем же idempotency_key
        await create_order_in_db(
            async_session,
            user_id,
            status=OrderStatus.reserving,
            idempotency_key=idem_key,
        )

        with pytest.raises(OrderConflictException):
            await order_service.checkout(user_id, idem_key)

    async def test_checkout_idempotency_awaiting_returns_existing(
        self,
        order_service: OrderService,
        mock_cart_client,
        mock_product_client,
        user_id,
        async_session,
    ):
        """При IntegrityError и заказе в awaiting_payment возвращается существующий заказ (201)."""
        idem_key = uuid.uuid4()

        order_id = await create_order_in_db(
            async_session,
            user_id,
            status=OrderStatus.awaiting_payment,
            idempotency_key=idem_key,
        )

        result = await order_service.checkout(user_id, idem_key)

        assert result.order_id == order_id
        assert result.status == OrderStatus.awaiting_payment
        assert len(result.items) == 2

    async def test_checkout_payment_wait_publish_failed_cancels_order(
        self,
        order_service: OrderService,
        mock_cart_client,
        mock_product_client,
        mock_publishers,
        user_id,
        idempotency_key,
        async_session,
    ):
        """Ошибка publish_payment_wait отменяет заказ со статусом cancelled_timeout и публикует reserve_release."""
        _setup_checkout_mocks(mock_cart_client, mock_product_client)
        mock_publishers["publish_payment_wait"].side_effect = RuntimeError(
            "RabbitMQ down"
        )

        with pytest.raises(RuntimeError, match="RabbitMQ down"):
            await order_service.checkout(user_id, idempotency_key)

        # Заказ отменён
        query = select(OrderModel).where(OrderModel.user_id == user_id)
        db_result = await async_session.execute(query)
        db_order = db_result.scalar_one()
        assert db_order.status == OrderStatus.cancelled_timeout

        # reserve_release опубликован
        mock_publishers["publish_reserve_release"].assert_awaited_once()

    async def test_checkout_payment_wait_and_release_both_fail(
        self,
        order_service: OrderService,
        mock_cart_client,
        mock_product_client,
        mock_publishers,
        user_id,
        idempotency_key,
        async_session,
    ):
        """Обе публикации падают: ошибка логируется, исключение пробрасывается."""
        _setup_checkout_mocks(mock_cart_client, mock_product_client)
        mock_publishers["publish_payment_wait"].side_effect = RuntimeError(
            "RabbitMQ down"
        )
        mock_publishers["publish_reserve_release"].side_effect = RuntimeError(
            "Also down"
        )

        with pytest.raises(RuntimeError, match="RabbitMQ down"):
            await order_service.checkout(user_id, idempotency_key)

        # Оба publisher-а были вызваны (второй тоже упал)
        mock_publishers["publish_payment_wait"].assert_awaited_once()
        mock_publishers["publish_reserve_release"].assert_awaited_once()

        # Заказ всё равно отменён
        query = select(OrderModel).where(OrderModel.user_id == user_id)
        db_result = await async_session.execute(query)
        db_order = db_result.scalar_one()
        assert db_order.status == OrderStatus.cancelled_timeout

    @pytest.mark.parametrize(
        "terminal_status",
        [
            OrderStatus.completed,
            OrderStatus.failed_out_of_stock,
            OrderStatus.failed_empty_cart,
            OrderStatus.cancelled_timeout,
        ],
    )
    async def test_checkout_idempotency_terminal_status_returns_existing(
        self,
        order_service: OrderService,
        mock_cart_client,
        mock_product_client,
        user_id,
        async_session,
        terminal_status,
    ):
        """При IntegrityError и терминальном статусе возвращается существующий заказ."""
        idem_key = uuid.uuid4()
        order_id = await create_order_in_db(
            async_session,
            user_id,
            status=terminal_status,
            idempotency_key=idem_key,
        )
        result = await order_service.checkout(user_id, idem_key)
        assert result.order_id == order_id
        assert result.status == terminal_status

    async def test_smart_cart_reuse_publish_failure_still_returns_order(
        self,
        order_service: OrderService,
        mock_cart_client,
        mock_publishers,
        user_id,
        async_session,
    ):
        """Smart cart: если publish_payment_wait упал, заказ всё равно возвращается."""
        old_order_id = await create_order_in_db(
            async_session,
            user_id,
            status=OrderStatus.awaiting_payment,
            expires_at=datetime.now(UTC) + timedelta(minutes=5),
        )
        cart_items = make_cart_items(count=2)
        mock_cart_client.get_selected_items.return_value = cart_items
        mock_publishers["publish_payment_wait"].side_effect = RuntimeError(
            "RabbitMQ down"
        )

        result = await order_service.checkout(user_id, uuid.uuid4())

        assert result.order_id == old_order_id
        assert result.status == OrderStatus.awaiting_payment

    async def test_checkout_total_price_calculated_correctly(
        self,
        order_service: OrderService,
        mock_cart_client,
        mock_product_client,
        mock_publishers,
        user_id,
        idempotency_key,
    ):
        """Итоговая цена корректно рассчитывается для товаров с разными ценами."""
        cart_items = [
            CartItemSelectedResponseSchema(product_id=1, quantity=3),
            CartItemSelectedResponseSchema(product_id=2, quantity=1),
        ]
        reserve_response = [
            ProductReserveResponseSchema(
                product_id=1,
                name="Cheap",
                image_url="https://example.com/1.jpg",
                price=10_000,
                quantity=3,
            ),
            ProductReserveResponseSchema(
                product_id=2,
                name="Expensive",
                image_url="https://example.com/2.jpg",
                price=500_000,
                quantity=1,
            ),
        ]
        mock_cart_client.get_selected_items.return_value = cart_items
        mock_product_client.reserve.return_value = reserve_response

        result = await order_service.checkout(user_id, idempotency_key)

        assert result.total_price == 10_000 * 3 + 500_000 * 1  # 530_000
