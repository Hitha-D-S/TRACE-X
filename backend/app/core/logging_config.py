"""
TRACE-X Structured Logging
JSON log lines with correlation IDs and timing metadata.
"""
from __future__ import annotations

import logging
import sys
import time
import uuid
from contextvars import ContextVar
from typing import Any, MutableMapping

import structlog

from app.core.config import get_settings

# Context var to carry correlation ID through the async call chain
correlation_id_var: ContextVar[str] = ContextVar("correlation_id", default="")


def add_correlation_id(
    logger: Any,
    method: str,
    event_dict: MutableMapping[str, Any],
) -> MutableMapping[str, Any]:
    cid = correlation_id_var.get("")
    if cid:
        event_dict["correlation_id"] = cid
    return event_dict


def add_service_info(
    logger: Any,
    method: str,
    event_dict: MutableMapping[str, Any],
) -> MutableMapping[str, Any]:
    event_dict["service"] = "tracex-api"
    event_dict["version"] = "1.0.0"
    return event_dict


def configure_logging() -> None:
    settings = get_settings()
    log_level = getattr(logging, settings.log_level.upper(), logging.INFO)

    shared_processors = [
        structlog.contextvars.merge_contextvars,
        add_correlation_id,
        add_service_info,
        structlog.processors.TimeStamper(fmt="iso"),
        structlog.stdlib.add_log_level,
        structlog.stdlib.add_logger_name,
    ]

    if settings.environment == "production":
        renderer = structlog.processors.JSONRenderer()
    else:
        renderer = structlog.dev.ConsoleRenderer(colors=True)

    structlog.configure(
        processors=[
            *shared_processors,
            structlog.stdlib.PositionalArgumentsFormatter(),
            structlog.processors.StackInfoRenderer(),
            structlog.processors.format_exc_info,
            renderer,
        ],
        wrapper_class=structlog.stdlib.BoundLogger,
        context_class=dict,
        logger_factory=structlog.stdlib.LoggerFactory(),
        cache_logger_on_first_use=True,
    )

    logging.basicConfig(
        format="%(message)s",
        stream=sys.stdout,
        level=log_level,
    )

    # Silence noisy third-party loggers
    for noisy in ("uvicorn.access", "neo4j", "aiokafka", "asyncio"):
        logging.getLogger(noisy).setLevel(logging.WARNING)


def get_logger(name: str = __name__) -> structlog.stdlib.BoundLogger:
    return structlog.get_logger(name)


def new_correlation_id() -> str:
    cid = str(uuid.uuid4())[:12]
    correlation_id_var.set(cid)
    return cid
