import math

import structlog
import uuid
from datetime import datetime, timedelta, UTC
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.exc import IntegrityError

from src.config import settings
from src.db.models import OrderStatus, OrderModel
from src.exceptions import (
    OrderConflictException,
    EmptyCartException,
    OutOfStockException,
    OrderNotFoundException,
    InvalidOrderStatusException,
)
from src.repositories.order import OrderRepository
from src.schemas.internal import (
    ProductReserveItemRequestSchema,
    OrderItemSnapshotSchema,
    CartItemSelectedResponseSchema,
    ProductReserveResponseSchema,
)
from src.schemas.orders import (
    CheckoutResponseSchema,
    OrderItemResponseSchema,
    PayResponseSchema,
    OrderListResponseSchema,
    OrderDetailResponseSchema,
    PaginatedOrdersResponseSchema,
)
from src.services.cart_client import CartClient
from src.services.product_client import ProductClient
from src.messaging.publisher import (
    publish_payment_wait,
    publish_cart_items_remove,
    publish_reserve_release,
)
from src.messaging.schemas import CartItemRemoveSchema


logger = structlog.get_logger(__name__)


class OrderService:
    def __init__(
        self,
        session: AsyncSession,
        cart_client: CartClient | None = None,
        product_client: ProductClient | None = None,
    ) -> None:
        self.session = session
        self.repo = OrderRepository(session)
        self.cart_client = cart_client
        self.product_client = product_client

    # --- ПУБЛИЧНЫЕ МЕТОДЫ ---

    async def checkout(
        self, user_id: uuid.UUID, idempotency_key: uuid.UUID
    ) -> CheckoutResponseSchema:
        """Начало оформления заказа с защитой от двойных кликов (идемпотентность)."""

        # Проверка на существующий в точности такой же неоплаченный заказ
        existing_order = await self.repo.get_last_unpaid_order(user_id)
        if existing_order:
            cart_items = await self.cart_client.get_selected_items(user_id)
            if self._is_same_cart_composition(existing_order.items, cart_items):
                # Продлить таймер
                await self.repo.update(
                    order_id=existing_order.id,
                    expires_at=datetime.now(UTC)
                    + timedelta(milliseconds=settings.ORDER_PAYMENT_TIMEOUT_MS),
                )
                await self.session.commit()

                # Опубликовать новое сообщение с полным TTL
                try:
                    await publish_payment_wait(order_id=existing_order.id)
                except Exception as e:
                    logger.error(
                        "smart_cart_payment_wait_publish_failed",
                        order_id=existing_order.id,
                        error=str(e),
                    )

                logger.info(
                    "smart_cart_reused_order",
                    order_id=existing_order.id,
                    user_id=user_id,
                )
                return CheckoutResponseSchema(
                    order_id=existing_order.id,
                    status=existing_order.status,
                    total_price=existing_order.total_price,
                    items=[
                        OrderItemResponseSchema(
                            product_id=item.product_id,
                            product_name=item.product_name,
                            product_image=item.product_image,
                            unit_price=item.unit_price,
                            quantity=item.quantity,
                        )
                        for item in existing_order.items
                    ],
                )

        # Инициализация заказа c idempotency_key и флагом "reserving"
        order, existing_order_response = await self._create_order(
            user_id, idempotency_key
        )
        if existing_order_response:
            return existing_order_response

        # Получаем корзину (cart_client)
        cart_items = await self._get_cart_items(user_id=user_id, order_id=order.id)

        # Резервируем товары (product_client)
        product_items = await self._reserve_products(
            order_id=order.id, cart_items=cart_items
        )

        # Сохраняем снапшоты товаров в заказе
        total_price = await self._process_order_items(
            order_id=order.id, product_items=product_items
        )

        # Публикуем заказ в очередь RabbitMQ order.payment.wait
        try:
            await publish_payment_wait(order_id=order.id)
        except Exception as e:
            logger.error("payment_wait_publish_failed", order_id=order.id, error=str(e))
            await self.repo.update(
                order_id=order.id, status=OrderStatus.cancelled_timeout
            )
            await self.session.commit()
            try:
                await publish_reserve_release(order_id=order.id)
            except Exception:
                logger.error("reserve_release_also_failed", order_id=order.id)
            raise

        return CheckoutResponseSchema(
            order_id=order.id,
            status=OrderStatus.awaiting_payment,
            total_price=total_price,
            items=[
                OrderItemResponseSchema(
                    product_id=item.product_id,
                    product_name=item.name,
                    product_image=item.image_url,
                    unit_price=item.price,
                    quantity=item.quantity,
                )
                for item in product_items
            ],
        )

    async def pay(self, user_id: uuid.UUID, order_id: uuid.UUID) -> PayResponseSchema:
        order = await self.repo.get_by_user_id_and_order_id(
            user_id=user_id, order_id=order_id
        )
        if not order:
            raise OrderNotFoundException()
        if order.status == OrderStatus.reserving:
            raise OrderConflictException("Order creation is in progress")
        if order.status == OrderStatus.completed:
            return PayResponseSchema(status=OrderStatus.completed)
        if order.status not in (OrderStatus.awaiting_payment, OrderStatus.reserving):
            raise InvalidOrderStatusException(
                f"Cannot pay order in status {order.status.value}"
            )

        if not order.items:
            raise InvalidOrderStatusException("Cannot pay for an order without items")

        if order.expires_at and order.expires_at < datetime.now(UTC):
            raise InvalidOrderStatusException("Order payment time expired")

        # Фиктивная оплата
        await self.repo.update(order_id=order_id, status=OrderStatus.completed)
        await self.session.commit()

        items_for_removal = [
            CartItemRemoveSchema(product_id=item.product_id) for item in order.items
        ]

        try:
            await publish_cart_items_remove(
                order_id=order_id, user_id=user_id, items=items_for_removal
            )
        except Exception as e:
            logger.error("rabbitmq_publish_failed", order_id=order.id, error=str(e))

        return PayResponseSchema(status=OrderStatus.completed)

    async def get_orders(
        self, user_id: uuid.UUID, page: int, page_size: int
    ) -> PaginatedOrdersResponseSchema:
        """Возвращает список завершённых заказов пользователя для страницы «Мои заказы»."""
        orders, total_orders = await self.repo.get_completed_by_user_id(
            user_id=user_id, page=page, page_size=page_size
        )
        pages = math.ceil(total_orders / page_size)

        return PaginatedOrdersResponseSchema(
            items=[OrderListResponseSchema.model_validate(order) for order in orders],
            total_orders=total_orders,
            page=page,
            page_size=page_size,
            pages=pages,
        )

    async def get_order_details(
        self, user_id: uuid.UUID, order_id: uuid.UUID
    ) -> OrderDetailResponseSchema:
        """Возвращает детали завершённого заказа пользователя."""
        order = await self.repo.get_by_user_id_and_order_id(
            user_id=user_id,
            order_id=order_id,
            status=OrderStatus.completed,
        )
        if not order:
            raise OrderNotFoundException()
        return OrderDetailResponseSchema.model_validate(order)

    async def process_timeout(self, order_id: uuid.UUID) -> None:
        """Обработка таймаута неоплаченного заказа.
        Вызывается RabbitMQ Consumer-ом при получении сообщения из order.timeout.check.
        """
        order = await self.repo.get_by_id(order_id=order_id)
        if not order:
            logger.warning("timeout_order_not_found", order_id=str(order_id))
            return

        # Если заказ уже оплачен, то таймаут игнорируется
        if order.status == OrderStatus.completed:
            logger.info("timeout_ignored_already_completed", order_id=str(order_id))
            return

        # Если заказ еще не оплачен (или висит в статусе reserving)
        if order.status in (OrderStatus.awaiting_payment, OrderStatus.reserving):
            # Если таймер был продлен, то игнорируем старое сообщение
            if order.expires_at and datetime.now(UTC) < order.expires_at:
                logger.info(
                    "timeout_ignored_timer_extended",
                    order_id=str(order_id),
                    expires_at=order.expires_at.isoformat(),
                )
                return

            # Таймер истек - отменяем заказ
            await self.repo.update(
                order_id=order_id, status=OrderStatus.cancelled_timeout
            )
            await self.session.commit()
            logger.info("order_cancelled_by_timeout", order_id=str(order_id))

            # Возврат товаров в stock
            try:
                await publish_reserve_release(order_id=order_id)
            except Exception as e:
                logger.error(
                    "rabbitmq_publish_failed", order_id=str(order_id), error=str(e)
                )

    # --- ПРИВАТНЫЕ МЕТОДЫ ДЛЯ CHECKOUT ---

    def _is_same_cart_composition(
        self,
        existing_items: list,
        cart_items: list[CartItemSelectedResponseSchema],
    ) -> bool:
        """Сравнивает состав существующего заказа с текущей корзиной."""
        if len(existing_items) != len(cart_items):
            return False

        existing_dict = {item.product_id: item.quantity for item in existing_items}
        cart_dict = {item.product_id: item.quantity for item in cart_items}

        return existing_dict == cart_dict

    async def _create_order(
        self, user_id: uuid.UUID, idempotency_key: uuid.UUID
    ) -> tuple[OrderModel | None, CheckoutResponseSchema | None]:
        """Создает новый заказ или возвращает существующий при совпадении ключа идемпотентности."""
        try:
            order = await self.repo.create(user_id, idempotency_key)
            await self.session.commit()
            logger.info("order_created_idempotent", user_id=user_id, order_id=order.id)
            return order, None
        except IntegrityError:
            # Такой idempotency_key уже есть
            await self.session.rollback()
            existing_order = await self.repo.get_by_idempotency_key(idempotency_key)

            if not existing_order:
                # На случай гонки или если запись была удалена
                logger.error(
                    "order_integrity_error_but_no_order_found",
                    idempotency_key=idempotency_key,
                )
                raise

            # Если заказ еще в процессе создания (reserving), то возвращаем 409
            if existing_order.status == OrderStatus.reserving:
                logger.warning("order_creation_in_progress", order_id=existing_order.id)
                raise OrderConflictException()

            # Если заказ уже создан (awaiting_payment или completed), то возвращаем его (201 Created)
            logger.info(
                "order_already_exists_returning",
                order_id=existing_order.id,
                status=existing_order.status,
            )
            return None, CheckoutResponseSchema(
                order_id=existing_order.id,
                status=existing_order.status,
                total_price=existing_order.total_price,
                items=[
                    OrderItemResponseSchema(
                        product_id=item.product_id,
                        product_name=item.product_name,
                        product_image=item.product_image,
                        unit_price=item.unit_price,
                        quantity=item.quantity,
                    )
                    for item in existing_order.items
                ],
            )

    async def _get_cart_items(
        self, user_id: uuid.UUID, order_id: uuid.UUID
    ) -> list[CartItemSelectedResponseSchema]:
        """Получает выбранные товары из корзины и проверяет её на пустоту."""
        cart_items = await self.cart_client.get_selected_items(user_id)
        if not cart_items:
            await self.repo.update(
                order_id=order_id, status=OrderStatus.failed_empty_cart
            )
            await self.session.commit()
            logger.error("cart_item_not_found", user_id=user_id)
            raise EmptyCartException()
        return cart_items

    async def _reserve_products(
        self, order_id: uuid.UUID, cart_items: list[CartItemSelectedResponseSchema]
    ) -> list[ProductReserveResponseSchema]:
        """Резервирует товары в сервисе продуктов."""
        reserve_items = [
            ProductReserveItemRequestSchema(
                product_id=item.product_id, quantity=item.quantity
            )
            for item in cart_items
        ]
        try:
            return await self.product_client.reserve(
                order_id=order_id, items=reserve_items
            )

        except OutOfStockException:
            await self.repo.update(
                order_id=order_id, status=OrderStatus.failed_out_of_stock
            )
            await self.session.commit()
            logger.warning("product_out_of_stock", order_id=order_id)
            raise

    async def _process_order_items(
        self, order_id: uuid.UUID, product_items: list[ProductReserveResponseSchema]
    ) -> int:
        """Создает снапшоты товаров в заказе и рассчитывает итоговую стоимость."""
        snapshots = [
            OrderItemSnapshotSchema(
                product_id=item.product_id,
                product_name=item.name,
                product_image=item.image_url,
                unit_price=item.price,
                quantity=item.quantity,
            )
            for item in product_items
        ]
        total_price = sum(item.unit_price * item.quantity for item in snapshots)

        # Обновить статус и цену заказа
        await self.repo.update(
            order_id=order_id,
            status=OrderStatus.awaiting_payment,
            total_price=total_price,
            expires_at=datetime.now(UTC)
            + timedelta(milliseconds=settings.ORDER_PAYMENT_TIMEOUT_MS),
        )

        # Сохранить снапшоты товаров
        await self.repo.create_items(order_id=order_id, items=snapshots)

        # Финальный коммит
        await self.session.commit()

        return total_price
