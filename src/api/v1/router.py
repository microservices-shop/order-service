from fastapi import APIRouter

from src.api.v1.orders import router as orders_router

router = APIRouter(prefix="/api/v1")
router.include_router(orders_router)
