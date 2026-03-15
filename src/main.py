import structlog
from fastapi import FastAPI, Request, status
from fastapi.middleware.cors import CORSMiddleware
from starlette.responses import JSONResponse

from src.config import settings
from src.logger import setup_logging, get_logger
from src.middleware.request_logger import RequestLoggingMiddleware

setup_logging()
logger = get_logger(__name__)


app = FastAPI(
    title="Order Service",
    version="0.1.0",
    debug=settings.DEBUG,
)

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
