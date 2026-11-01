"""Bounded JSON-line application logs; do not log secret or raw model inputs."""

import logging
from collections.abc import MutableMapping
from logging.handlers import RotatingFileHandler
from pathlib import Path
from typing import Any

import structlog


def redact_secrets(_: Any, __: str, event: MutableMapping[str, Any]) -> MutableMapping[str, Any]:
    """Redact nested secret fields before serialization."""

    def clean(value: Any) -> Any:
        if isinstance(value, dict):
            return {
                key: "[REDACTED]"
                if any(
                    marker in str(key).lower()
                    for marker in ("key", "token", "password", "secret", "authorization")
                )
                else clean(item)
                for key, item in value.items()
            }
        if isinstance(value, (list, tuple)):
            return [clean(item) for item in value]
        return value

    result: dict[str, Any] = clean(event)
    return result


def create_logger(path: Path) -> Any:
    """Create a dedicated rotating logger without altering global logging."""
    path.parent.mkdir(parents=True, exist_ok=True)
    logger = logging.getLogger(f"ctf_forge.{path.resolve()}")
    for old_handler in list(logger.handlers):
        logger.removeHandler(old_handler)
        old_handler.close()
    handler = RotatingFileHandler(path, maxBytes=1048576, backupCount=2, encoding="utf-8")
    handler.setFormatter(logging.Formatter("%(message)s"))
    logger.addHandler(handler)
    logger.setLevel(logging.INFO)
    logger.propagate = False
    return structlog.wrap_logger(
        logger,
        processors=[
            structlog.processors.TimeStamper(fmt="iso", utc=True),
            structlog.stdlib.add_log_level,
            redact_secrets,
            structlog.processors.JSONRenderer(ensure_ascii=True),
        ],
    )
