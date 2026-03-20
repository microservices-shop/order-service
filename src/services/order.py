import structlog
import uuid
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.exc import IntegrityError

from src.db.models import OrderStatus, OrderModel
from src.exceptions import (
    OrderConflictException,
    EmptyCartException,
    OutOfStockException,
)
from src.repositories.order import OrderRepository
from src.schemas.internal import (
    ProductReserveItemRequestSchema,
    OrderItemSnapshotSchema,
    CartItemSelectedResponseSchema,
    ProductReserveResponseSchema,
)
from src.schemas.orders import CheckoutResponseSchema
from src.services.cart_client import CartClient
from src.services.product_client import ProductClient
from src.messaging.publisher import publish_payment_wait


logger = structlog.get_logger(__name__)


class OrderService:
    def __init__(
        self,
        session: AsyncSession,
        cart_client: CartClient,
        product_client: ProductClient,
    ) -> None:
        self.session = session
        self.repo = OrderRepository(session)
        self.cart_client = cart_client
        self.product_client = product_client

    async def checkout(
        self, user_id: uuid.UUID, idempotency_key: uuid.UUID
    ) -> CheckoutResponseSchema:
        """Начало оформления заказа с защитой от двойных кликов (идемпотентность)."""

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
        except Exception as exc:
            logger.error("rabbitmq_publish_failed", order_id=order.id, error=str(exc))
            # НЕ выбрасываем ошибку дальше. Заказ уже сохранен в БД
            # Пользователь сможет его оплатить
            # TODO: Реализовать паттерн Transactional Outbox для надежной доставки сообщений в RabbitMQ

        return CheckoutResponseSchema(
            order_id=order.id,
            status=OrderStatus.awaiting_payment,
            total_price=total_price,
        )

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
            logger.error("product_out_of_stock", order_id=order_id)
            raise

    async def _process_order_items(
        self, order_id: uuid.UUID, product_items: list[ProductReserveResponseSchema]
    ) -> int:
        """Создает снапшоты товаров в заказе и рассчитывает итоговую стоимость."""
        snapshots = [
            OrderItemSnapshotSchema(
                product_id=item.product_id,
                product_name=item.name,
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
        )

        # Сохранить снапшоты товаров
        await self.repo.create_items(order_id=order_id, items=snapshots)

        # Финальный коммит
        await self.session.commit()

        return total_price
