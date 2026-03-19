import structlog
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
import httpx

from src.config import settings
from src.logger import setup_logging, get_logger
from src.messaging.broker import broker, payment_wait_queue
from src.messaging.consumers import router as messaging_router
from src.middleware.request_logger import RequestLoggingMiddleware
from src.services.cart_client import CartClient
from src.services.product_client import ProductClient
from src.api.v1.orders import router as orders_router
from src.exceptions import (
    EmptyCartException,
    OrderConflictException,
    OrderNotFoundException,
    OutOfStockException,
    OrderServiceException,
)

setup_logging()
logger = get_logger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    await broker.connect()
    await broker.start()

    # Очередь order.payment.wait не имеет consumers,
    # поэтому объявляем её руками (она настроена на DLX)
    await broker.declare_queue(payment_wait_queue)

    # Явно создаём транспорт без прокси.
    transport = httpx.AsyncHTTPTransport(retries=1)
    http_client = httpx.AsyncClient(
        transport=transport,
        timeout=httpx.Timeout(timeout=10.0, connect=5.0),
    )
    app.state.cart_client = CartClient(http_client)
    app.state.product_client = ProductClient(http_client)

    yield

    await http_client.aclose()
    await broker.close()
    logger.info("rabbitmq_broker_closed")


app = FastAPI(
    title="Order Service",
    version="0.1.0",
    debug=settings.DEBUG,
    lifespan=lifespan,
)

app.include_router(orders_router)
broker.include_router(messaging_router)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.add_middleware(RequestLoggingMiddleware)


@app.get("/health")
async def health_check():
    return {"status": "healthy", "service": "order-service"}


@app.exception_handler(EmptyCartException)
async def empty_cart_handler(request: Request, exc: EmptyCartException):
    return JSONResponse(
        status_code=status.HTTP_400_BAD_REQUEST,
        content={"detail": exc.detail},
    )


@app.exception_handler(OutOfStockException)
async def out_of_stock_handler(request: Request, exc: OutOfStockException):
    return JSONResponse(
        status_code=status.HTTP_400_BAD_REQUEST,
        content={"detail": exc.detail},
    )


@app.exception_handler(OrderConflictException)
async def order_conflict_handler(request: Request, exc: OrderConflictException):
    return JSONResponse(
        status_code=status.HTTP_409_CONFLICT,
        content={"detail": exc.detail},
    )


@app.exception_handler(OrderNotFoundException)
async def order_not_found_handler(request: Request, exc: OrderNotFoundException):
    return JSONResponse(
        status_code=status.HTTP_404_NOT_FOUND,
        content={"detail": exc.detail},
    )


@app.exception_handler(OrderServiceException)
async def order_service_exception_handler(request: Request, exc: OrderServiceException):
    logger.error("order_service_business_error", detail=exc.detail)
    return JSONResponse(
        status_code=status.HTTP_400_BAD_REQUEST,
        content={"detail": exc.detail},
    )


@app.exception_handler(Exception)
async def unhandled_exception_handler(request: Request, exc: Exception):
    # request_id АВТОМАТИЧЕСКИ добавляется в логи из контекста structlog
    logger.exception("unhandled_exception")
    request_id = structlog.contextvars.get_contextvars().get("request_id")
    return JSONResponse(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        content={
            "detail": "Internal server error. Please report this ID to support.",
            "request_id": request_id,
        },
    )
