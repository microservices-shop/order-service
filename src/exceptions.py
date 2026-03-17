class OrderServiceException(Exception):
    """Базовое исключение Order Service."""

    detail = "Order service internal error"

    def __init__(self, detail: str | None = None):
        if detail:
            self.detail = detail
        super().__init__(self.detail)


class EmptyCartException(OrderServiceException):
    """Корзина пуста - нет выбранных товаров для оформления."""

    detail = "Unable to place order: no items selected"


class OutOfStockException(OrderServiceException):
    """Товара нет в наличии - резерв невозможен."""

    detail = "Item out of stock"


class OrderConflictException(OrderServiceException):
    """Заказ уже в процессе создания (status=reserving)."""

    detail = "Order is already being created"


class OrderNotFoundException(OrderServiceException):
    """Заказ не найден или принадлежит другому пользователю."""

    detail = "Order not found"
