import uuid
from typing import Annotated

from fastapi import Depends, Header, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from src.db.database import async_session_maker


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


SessionDep = Annotated[AsyncSession, Depends(get_db)]
UserIdDep = Annotated[uuid.UUID, Depends(get_user_id)]
