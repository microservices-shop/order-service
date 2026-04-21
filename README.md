# Order Service

> Микросервис для интернет-магазина электроники. Главный репозиторий: [microservices-shop/overview](https://github.com/microservices-shop/overview)

## Tech Stack

![Python](https://img.shields.io/badge/Python-3.12-3776AB?style=for-the-badge&logo=python&logoColor=white)
![FastAPI](https://img.shields.io/badge/FastAPI-0.135-009688?style=for-the-badge&logo=fastapi&logoColor=white)
![PostgreSQL](https://img.shields.io/badge/PostgreSQL-16-4169E1?style=for-the-badge&logo=postgresql&logoColor=white)
![SQLAlchemy](https://img.shields.io/badge/SQLAlchemy-2.0-D71F00?style=for-the-badge&logo=sqlalchemy&logoColor=white)
![Alembic](https://img.shields.io/badge/Alembic-1.18-6BA81E?style=for-the-badge)
![RabbitMQ](https://img.shields.io/badge/RabbitMQ-3.12-FF6600?style=for-the-badge&logo=rabbitmq&logoColor=white)
![FastStream](https://img.shields.io/badge/FastStream-0.6-00C7B7?style=for-the-badge)
![httpx](https://img.shields.io/badge/httpx-0.28-0096D6?style=for-the-badge)
![Pydantic](https://img.shields.io/badge/Pydantic-2.12-E92063?style=for-the-badge&logo=pydantic&logoColor=white)
![structlog](https://img.shields.io/badge/structlog-25.5-000000?style=for-the-badge)
![Pytest](https://img.shields.io/badge/Pytest-9.0-0A9EDC?style=for-the-badge&logo=pytest&logoColor=white)
![Docker](https://img.shields.io/badge/Docker-24-2496ED?style=for-the-badge&logo=docker&logoColor=white)

## Описание

Микросервис управления заказами. Координирует распределённые транзакции между сервисами корзины и каталога товаров, реализуя паттерн **Orchestration Saga**.

Order Service выступает оркестратором при оформлении заказа: резервирует товары в Product Service, создаёт заказ со снапшотами, запускает таймер оплаты (15 минут), и при успешной оплате асинхронно очищает корзину в Cart Service через RabbitMQ. При таймауте или отмене — возвращает резервы обратно на склад.

**Основной функционал:**
- **Оформление заказов** — создание заказа из выбранных товаров корзины с резервированием на складе (Product Service) и сохранением снапшотов (цена, название, фото на момент оформления)
- **Оплата заказов** — фиктивная оплата с переходом заказа в статус `completed` и асинхронной очисткой корзины через RabbitMQ
- **История заказов** — просмотр завершённых заказов пользователя с пагинацией и детальной информацией по каждому заказу
- **Автоматическая отмена** — таймер на 15 минут с автоматической отменой неоплаченного заказа и возвратом зарезервированных товаров на склад
- **Защита от дублей** — идемпотентность через заголовок `Idempotency-Key` и автоматический подхват существующих неоплаченных заказов при повторном оформлении
- **Отказоустойчивость** — retry-механизм с экспоненциальным backoff при сбоях интеграций с Cart/Product Service, структурированное логирование с request tracing

## Структура проекта

```
order-service/
├── src/
│   ├── api/
│   │   ├── v1/
│   │   │   ├── orders.py          # REST эндпоинты
│   │   │   └── router.py          
│   │   └── dependencies.py        
│   ├── db/
│   │   ├── database.py            # Конфигурация БД
│   │   └── models.py              # SQLAlchemy модели
│   ├── repositories/
│   │   └── order.py               
│   ├── services/
│   │   ├── order.py              
│   │   ├── cart_client.py         
│   │   └── product_client.py      
│   ├── messaging/
│   │   ├── broker.py              
│   │   ├── publisher.py           
│   │   ├── consumers.py          
│   │   └── schemas.py             
│   ├── middleware/
│   │   └── request_logger.py     
│   ├── schemas/                   # Pydantic схемы
│   │   ├── orders.py              
│   │   └── internal.py            
│   ├── config.py                  # Конфигурация (pydantic-settings)
│   ├── logger.py                  
│   ├── exceptions.py              
│   └── main.py                    # Точка входа приложения
├── alembic/                       # Миграции БД
├── tests/                       
│   ├── api/                     
│   ├── service/                 
│   ├── unit/                    
│   ├── factories/               
│   └── conftest.py             
├── pyproject.toml                 
├── .env.example                  
└── README.md
```

## API

Сервис запускается на порту **8004**. Интерактивная документация доступна по адресу `http://localhost:8004/docs` (Swagger UI).

### Публичный API (`/api/v1/orders`)

| Метод  | Путь                        | Описание                                                      | Заголовки                                    |
|--------|-----------------------------|---------------------------------------------------------------|----------------------------------------------|
| `POST` | `/api/v1/orders/checkout`   | Оформление заказа (резервирование товаров, запуск таймера)    | `X-User-Id`, `Idempotency-Key`               |
| `POST` | `/api/v1/orders/{id}/pay`   | Оплата заказа (фиктивная, переход в статус `completed`)      | `X-User-Id`                                  |
| `GET`  | `/api/v1/orders`            | Список завершённых заказов (пагинация, превью товаров)       | `X-User-Id`                                  |
| `GET`  | `/api/v1/orders/{id}`       | Детали завершённого заказа (полные снапшоты товаров)         | `X-User-Id`                                  |

### Health Check

| Метод | Путь      | Описание           |
|-------|-----------|--------------------|
| `GET` | `/health` | Проверка здоровья  |

## RabbitMQ Интеграция

### Публикуемые очереди

| Очередь                   | Назначение                                    | Payload                                              |
|---------------------------|-----------------------------------------------|------------------------------------------------------|
| `order.payment.wait`      | Таймер оплаты (TTL 15 мин, DLX)               | `{"order_id": "UUID", "message_id": "UUID", ...}`    |
| `cart.items.remove`       | Очистка корзины после оплаты                  | `{"order_id": "UUID", "user_id": "UUID", "items": [...]}` |
| `product.reserve.release` | Возврат товаров при отмене/таймауте           | `{"order_id": "UUID", "message_id": "UUID", ...}`    |

### Подписки (Consumers)

| Очередь              | Обработчик          | Описание                                    |
|----------------------|---------------------|---------------------------------------------|
| `order.timeout.check`| `process_timeout()` | Обработка таймаута неоплаченных заказов     |

## Flow диаграммы

### Оформление заказа:

```mermaid
sequenceDiagram
    participant U as User
    participant G as API Gateway
    participant O as Order Service
    participant C as Cart Service
    participant P as Product Service
    participant R as RabbitMQ
    participant D as PostgreSQL

    U->>G: POST /api/orders/checkout<br/>(Idempotency-Key)
    G->>O: POST /api/v1/orders/checkout<br/>(X-User-Id)
    
    O->>D: INSERT order (status=reserving)
    
    O->>C: GET /internal/cart/selected
    C-->>O: [{product_id, quantity}]
    
    O->>P: POST /internal/products/reserve
    P->>P: Уменьшить stock
    P-->>O: [{product_id, name, price, image_url}]
    
    O->>D: UPDATE order (status=awaiting_payment)<br/>INSERT order_items (снапшоты)
    
    O->>R: Publish → order.payment.wait<br/>(TTL 15 минут)
    
    O-->>G: 201 Created {order_id, items, total_price}
    G-->>U: Заказ создан, ожидает оплаты
    
    Note over U,R: Пользователь оплачивает в течение 15 минут
    
    U->>G: POST /api/orders/{id}/pay
    G->>O: POST /api/v1/orders/{id}/pay
    O->>D: UPDATE order (status=completed)
    O->>R: Publish → cart.items.remove
    O-->>G: 200 OK {status: completed}
```

### Обработка таймаута:

```mermaid
sequenceDiagram
    participant R as RabbitMQ
    participant O as Order Service
    participant D as PostgreSQL
    participant P as Product Service

    Note over R: Прошло 15 минут с момента создания заказа
    
    R->>R: TTL истёк в order.payment.wait
    R->>R: DLX перенаправляет в order.timeout.check
    
    R->>O: Consumer получает сообщение
    
    O->>D: SELECT order WHERE id=?
    
    alt Заказ не оплачен (status=awaiting_payment)
        O->>D: Проверить expires_at
        
        alt Таймер НЕ продлён (NOW >= expires_at)
            O->>D: UPDATE order (status=cancelled_timeout)
            O->>R: Publish → product.reserve.release
            R->>P: Consumer получает сообщение
            P->>P: Вернуть quantity в stock<br/>Удалить резервы
            O-->>R: ACK
        else Таймер продлён (автоподхват заказа)
            Note over O: Игнорировать старое сообщение<br/>(новое уже опубликовано)
            O-->>R: ACK
        end
    else Заказ уже оплачен (status=completed)
        Note over O: Игнорировать таймаут
        O-->>R: ACK
    end
```

## Установка и запуск

### Требования

- Python 3.12+
- PostgreSQL 14+
- RabbitMQ 3.12+

### Разработка

```bash
# Установка зависимостей
uv sync

cp .env.example .env

# Запуск PostgreSQL
docker-compose -f docker-compose.dev.yml up -d

# Миграции БД
alembic upgrade head

# Запуск сервиса
uvicorn src.main:app --reload --port 8004 --no-access-log
```

### Production

```bash
docker-compose up --build -d
```

## Тестирование

```bash
# Запуск всех тестов
pytest

# С покрытием
pytest --cov=src --cov-report=html
```

**Coverage report:** 90%

## Что можно улучшить

- [ ] **Transactional Outbox** — гарантированная доставка сообщений в RabbitMQ через паттерн Outbox (запись событий в БД в той же транзакции, отдельный процесс для публикации)
- [ ] **Метрики** — интеграция с Prometheus (количество заказов, время резервирования, процент отмен, latency)
- [ ] **Логи в Grafana** — централизованный сбор логов через Loki для визуализации и алертинга
