"""Эндпоинты API для работы с заказами."""

from fastapi import APIRouter

router = APIRouter(prefix="/api/v1/orders", tags=["Orders"])

# Эндпоинты checkout, pay, get_orders, get_order
# будут добавлены на этапах 7–9.
