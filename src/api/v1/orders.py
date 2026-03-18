from fastapi import APIRouter

from src.api.dependencies import UserIdDep, IdempotencyKeyDep
from src.schemas.orders import CheckoutResponseSchema

router = APIRouter(prefix="/api/v1/orders")


@router.post("/checkout", response_model=CheckoutResponseSchema)
async def checkout(
    user_id: UserIdDep, idempotency_key: IdempotencyKeyDep
) -> CheckoutResponseSchema: ...
