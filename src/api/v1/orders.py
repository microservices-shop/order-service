import uuid

from fastapi import APIRouter, status, Query

from src.api.dependencies import UserIdDep, IdempotencyKeyDep, OrderServiceDep
from src.config import settings
from src.schemas.orders import (
    CheckoutResponseSchema,
    PayResponseSchema,
    OrderDetailResponseSchema,
    PaginatedOrdersResponseSchema,
)

router = APIRouter(prefix="/orders")


@router.post(
    "/checkout",
    response_model=CheckoutResponseSchema,
    status_code=status.HTTP_201_CREATED,
    summary="Оформить заказ",
    description="Создает новый заказ.",
    responses={
        status.HTTP_400_BAD_REQUEST: {
            "description": "Пустая корзина, нет товара на складе, или невалидный Idempotency-Key"
        },
        status.HTTP_401_UNAUTHORIZED: {
            "description": "Не передан или невалиден X-User-Id"
        },
        status.HTTP_409_CONFLICT: {
            "description": "Заказ с таким ключом уже в процессе создания"
        },
        status.HTTP_201_CREATED: {
            "description": "Заказ с таким ключом уже (или только что) был создан",
            "model": CheckoutResponseSchema,
        },
    },
)
async def checkout(
    user_id: UserIdDep,
    idempotency_key: IdempotencyKeyDep,
    service: OrderServiceDep,
) -> CheckoutResponseSchema:
    """Оформление заказа.
    При повторном вызове с тем же ключом:
    - 409 Conflict, если первый заказ еще создается.
    - 201 Created, если первый заказ уже создан (или создан в этом запросе).
    """
    return await service.checkout(user_id, idempotency_key)


@router.post(
    "/{order_id}/pay",
    response_model=PayResponseSchema,
    status_code=status.HTTP_200_OK,
    summary="Оплатить заказ",
    description="Переводит заказ в статус 'completed' и очищает корзину пользователя.",
    responses={
        status.HTTP_400_BAD_REQUEST: {
            "description": "Некорректный статус заказа для оплаты (отменен или ошибка)"
        },
        status.HTTP_401_UNAUTHORIZED: {
            "description": "Не передан или невалиден X-User-Id"
        },
        status.HTTP_404_NOT_FOUND: {
            "description": "Заказ не найден или принадлежит чужому пользователю"
        },
        status.HTTP_409_CONFLICT: {"description": "Заказ еще в процессе создания"},
    },
)
async def pay(
    user_id: UserIdDep,
    order_id: uuid.UUID,
    service: OrderServiceDep,
) -> PayResponseSchema:
    """Оплата заказа и очистка корзины."""
    return await service.pay(user_id=user_id, order_id=order_id)


@router.get(
    "",
    response_model=PaginatedOrdersResponseSchema,
    status_code=status.HTTP_200_OK,
    summary="Список заказов",
    description="Возвращает завершённые заказы пользователя, отсортированные от новых к старым.",
    responses={
        status.HTTP_401_UNAUTHORIZED: {
            "description": "Не передан или невалиден X-User-Id"
        },
    },
)
async def get_orders(
    user_id: UserIdDep,
    service: OrderServiceDep,
    page: int = Query(default=1, ge=1, description="Номер страницы"),
    page_size: int = Query(
        default=settings.DEFAULT_PAGE_SIZE,
        ge=1,
        le=settings.MAX_PAGE_SIZE,
        description="Количество товаров на странице",
    ),
) -> PaginatedOrdersResponseSchema:
    """Список завершённых заказов для страницы «Мои заказы».

    Если заказов нет - возвращает пустой список.
    """
    return await service.get_orders(user_id=user_id, page=page, page_size=page_size)


@router.get(
    "/{order_id}",
    response_model=OrderDetailResponseSchema,
    summary="Детали заказа",
    description="Возвращает детали завершённого заказа с полной информацией о товарах.",
    responses={
        status.HTTP_401_UNAUTHORIZED: {
            "description": "Не передан или невалиден X-User-Id"
        },
        status.HTTP_404_NOT_FOUND: {
            "description": "Заказ не найден, не принадлежит пользователю или не завершён"
        },
    },
)
async def get_order_details(
    user_id: UserIdDep,
    order_id: uuid.UUID,
    service: OrderServiceDep,
) -> OrderDetailResponseSchema:
    """Детали завершённого заказа.

    Возвращает 404, если заказ не найден, принадлежит другому
    пользователю или ещё не в статусе `completed`.
    """
    return await service.get_order_details(user_id=user_id, order_id=order_id)
