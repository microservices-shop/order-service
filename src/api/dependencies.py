import uuid
from typing import Annotated

from fastapi import Depends, Header, HTTPException, status, Request
from sqlalchemy.ext.asyncio import AsyncSession

from src.db.database import async_session_maker
from src.services.order import OrderService
from src.services.cart_client import CartClient
from src.services.product_client import ProductClient


async def get_db() -> AsyncSession:
    async with async_session_maker() as session:
        yield session


def get_user_id(x_user_id: str | None = Header(None)) -> uuid.UUID:
    """Извлекает UUID пользователя из заголовка X-User-Id.

    Raises:
        HTTPException: 401, если заголовок отсутствует или невалидный UUID.
    """
    if not x_user_id:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="X-User-Id header is required",
        )

    try:
        return uuid.UUID(x_user_id)
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="X-User-Id header must be a valid UUID",
        )


def get_idempotency_key(
    idempotency_key: str | None = Header(None, alias="Idempotency-Key"),
) -> str:
    """Извлекает ключ идемпотентности из заголовка Idempotency-Key."""
    if not idempotency_key:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Idempotency-Key header is required",
        )
    return idempotency_key


def get_cart_client(request: Request) -> CartClient:
    return request.app.state.cart_client


def get_product_client(request: Request) -> ProductClient:
    return request.app.state.product_client


CartClientDep = Annotated[CartClient, Depends(get_cart_client)]
ProductClientDep = Annotated[ProductClient, Depends(get_product_client)]


def get_order_service(
    session: Annotated[AsyncSession, Depends(get_db)],
    cart_client: CartClientDep,
    product_client: ProductClientDep,
) -> OrderService:
    """Фабрика для создания сервиса заказов."""
    return OrderService(session, cart_client, product_client)


SessionDep = Annotated[AsyncSession, Depends(get_db)]
UserIdDep = Annotated[uuid.UUID, Depends(get_user_id)]
IdempotencyKeyDep = Annotated[str, Depends(get_idempotency_key)]
OrderServiceDep = Annotated[OrderService, Depends(get_order_service)]
