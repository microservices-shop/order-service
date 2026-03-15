import logging
import sys
import structlog

from src.config import settings


def setup_logging() -> None:
    """Конфигурирует structlog в зависимости от режима DEBUG."""
    shared_processors = [
        structlog.contextvars.merge_contextvars,
        structlog.processors.add_log_level,
        structlog.processors.TimeStamper(fmt="iso", utc=True),
    ]

    if settings.DEBUG:
        processors = shared_processors + [
            structlog.dev.ConsoleRenderer(
                colors=True,
                sort_keys=False,
                pad_event=0,
                pad_level=False,
            ),
        ]
    else:
        processors = shared_processors + [
            structlog.processors.StackInfoRenderer(),
            structlog.processors.format_exc_info,
            structlog.processors.JSONRenderer(),
        ]

    log_level = getattr(logging, settings.LOG_LEVEL.upper(), logging.INFO)

    structlog.configure(
        processors=processors,
        wrapper_class=structlog.make_filtering_bound_logger(log_level),
        logger_factory=structlog.WriteLoggerFactory(file=sys.stderr),
        cache_logger_on_first_use=True,
    )


def get_logger(name: str | None = None) -> structlog.stdlib.BoundLogger:
    """Возвращает настроенный логгер."""
    return structlog.get_logger(name)
