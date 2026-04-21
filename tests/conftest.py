"""Глобальные фикстуры тестового окружения.

Паттерн: session-scoped контейнер и engine,
function-scoped сессия с изоляцией через savepoint.
"""

import uuid
from unittest.mock import AsyncMock

import os
import pytest
import pytest_asyncio

# Отключаем Ryuk (сервис очистки testcontainers), т.к. на Docker Desktop (Windows)
# он часто падает с ошибкой проброса портов
os.environ["TESTCONTAINERS_RYUK_DISABLED"] = "true"

from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from testcontainers.postgres import PostgresContainer

from src.db.database import Base
from src.services.cart_client import CartClient
from src.services.product_client import ProductClient


@pytest.fixture(scope="session")
def postgres_container():
    """Запускает PostgreSQL-контейнер один раз на всю сессию тестов."""
    with PostgresContainer("postgres:18", driver="asyncpg") as pg:
        yield pg


@pytest_asyncio.fixture(scope="session")
async def async_engine(postgres_container):
    """Создаёт асинхронный движок один раз на всю сессию тестов."""
    url = postgres_container.get_connection_url()
    engine = create_async_engine(url, echo=False)

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    yield engine

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
    await engine.dispose()


@pytest_asyncio.fixture(scope="function")
async def async_session(async_engine) -> AsyncSession:
    """Создаёт изолированную сессию БД для одного теста.

    Паттерн: внешняя транзакция с вложенным savepoint.
    После теста транзакция откатывается.
    """
    connection = await async_engine.connect()
    transaction = await connection.begin()

    session = AsyncSession(
        bind=connection,
        expire_on_commit=False,
        join_transaction_mode="create_savepoint",
    )

    yield session

    await session.close()
    await transaction.rollback()
    await connection.close()


# --- Моки внешних сервисов ---


@pytest.fixture
def mock_cart_client() -> AsyncMock:
    """Создаёт мок CartClient с управляемыми данными корзины."""
    return AsyncMock(spec=CartClient)


@pytest.fixture
def mock_product_client() -> AsyncMock:
    """Создаёт мок ProductClient с управляемыми данными резерва."""
    return AsyncMock(spec=ProductClient)


# --- Хелперы для тестовых данных ---


@pytest.fixture
def user_id() -> uuid.UUID:
    """Возвращает фиксированный UUID пользователя для тестов."""
    return uuid.UUID("11111111-1111-1111-1111-111111111111")


@pytest.fixture
def another_user_id() -> uuid.UUID:
    """Возвращает UUID второго пользователя для проверки изоляции данных."""
    return uuid.UUID("22222222-2222-2222-2222-222222222222")


@pytest.fixture
def idempotency_key() -> uuid.UUID:
    """Генерирует уникальный ключ идемпотентности для каждого теста."""
    return uuid.uuid4()
