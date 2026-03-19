from fastapi import APIRouter, status

from src.api.dependencies import UserIdDep, IdempotencyKeyDep, OrderServiceDep
from src.schemas.orders import CheckoutResponseSchema

router = APIRouter(prefix="/api/v1/orders")


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
