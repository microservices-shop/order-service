import structlog
from sqlalchemy.ext.asyncio import AsyncSession

from src.repositories.order import OrderRepository
from src.services.cart_client import CartClient
from src.services.product_client import ProductClient


logger = structlog.get_logger(__name__)


class OrderService:
    def __init__(
        self,
        session: AsyncSession,
        cart_client: CartClient,
        product_client: ProductClient,
    ) -> None:
        self.session = session
        self.repo = OrderRepository(session)
        self.cart_client = cart_client
        self.product_client = product_client
