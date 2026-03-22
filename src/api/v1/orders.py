import uuid

from fastapi import APIRouter, status

from src.api.dependencies import UserIdDep, IdempotencyKeyDep, OrderServiceDep
from src.schemas.orders import (
    CheckoutResponseSchema,
    PayResponseSchema,
    OrderListResponseSchema,
)

router = APIRouter(prefix="/orders")


@router.post(
    "/checkout",
    response_model=CheckoutResponseSchema,
    status_code=status.HTTP_201_CREATED,
    summary="Оформить заказ",
    description="Создает новый заказ.",
    responses={
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
        status.HTTP_404_NOT_FOUND: {"description": "Заказ не найден"},
        status.HTTP_400_BAD_REQUEST: {
            "description": "Некорректный статус заказа для оплаты (отменен или уже оплачен)"
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
    response_model=list[OrderListResponseSchema],
    status_code=status.HTTP_200_OK,
    summary="Список заказов",
    description="Возвращает завершённые заказы пользователя, отсортированные от новых к старым.",
)
async def get_orders(
    user_id: UserIdDep,
    service: OrderServiceDep,
) -> list[OrderListResponseSchema]:
    """Список завершённых заказов для страницы «Мои заказы».

    Если заказов нет - возвращает пустой список.
    """
    return await service.get_orders(user_id=user_id)
