"""Logging configuration using structlog.

Provides structured logging with support for both development
(colored console) and production (JSON) formats.
"""

import logging
import sys

import structlog


def configure_logging(
    log_level: str = "INFO",
    json_format: bool = False,
) -> None:
    """Configure structured logging.

    Reason: structlog provides structured output that's easy to parse
    for log aggregation systems while remaining readable in development.

    Args:
        log_level: Minimum log level (DEBUG, INFO, WARNING, ERROR).
        json_format: If True, output JSON format (for production).
    """
    # Convert string level to logging constant
    numeric_level = getattr(logging, log_level.upper(), logging.INFO)

    # Configure standard library logging
    logging.basicConfig(
        format="%(message)s",
        stream=sys.stdout,
        level=numeric_level,
    )

    # Shared processors
    shared_processors: list = [
        structlog.contextvars.merge_contextvars,
        structlog.processors.add_log_level,
        structlog.processors.TimeStamper(fmt="iso"),
        structlog.stdlib.ExtraAdder(),
    ]

    if json_format:
        # Production: JSON format for log aggregation
        structlog.configure(
            processors=shared_processors
            + [
                structlog.processors.format_exc_info,
                structlog.processors.JSONRenderer(),
            ],
            wrapper_class=structlog.make_filtering_bound_logger(numeric_level),
            context_class=dict,
            logger_factory=structlog.PrintLoggerFactory(),
            cache_logger_on_first_use=True,
        )
    else:
        # Development: colored console output
        structlog.configure(
            processors=shared_processors
            + [
                structlog.processors.format_exc_info,
                structlog.dev.ConsoleRenderer(colors=True),
            ],
            wrapper_class=structlog.make_filtering_bound_logger(numeric_level),
            context_class=dict,
            logger_factory=structlog.PrintLoggerFactory(),
            cache_logger_on_first_use=True,
        )


def get_logger(name: str | None = None) -> structlog.stdlib.BoundLogger:
    """Get a logger instance.

    Args:
        name: Optional logger name for context.

    Returns:
        Configured structlog logger.
    """
    logger = structlog.get_logger()
    if name:
        logger = logger.bind(logger=name)
    return logger
