"""
Vigile — Structured Logging Configuration (Master / Python).

Centralized logging setup with TRACE level, JSON structured output,
rotating file handler, and correlation ID enrichment. Zero extra deps.
"""

from __future__ import annotations

import json
import logging
import logging.handlers
import os
import sys
from datetime import datetime, timezone
from typing import Any

TRACE_LEVEL_NUM = 5
logging.addLevelName(TRACE_LEVEL_NUM, "TRACE")


def trace(self: logging.Logger, message: str, *args: Any, **kwargs: Any) -> None:
    if self.isEnabledFor(TRACE_LEVEL_NUM):
        self._log(TRACE_LEVEL_NUM, message, args, **kwargs)


logging.Logger.trace = trace  # type: ignore[attr-defined]


class JSONFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        ts = datetime.fromtimestamp(record.created, tz=timezone.utc).isoformat()
        entry: dict[str, Any] = {
            "timestamp": ts, "level": record.levelname, "level_num": record.levelno,
            "logger": record.name, "message": record.getMessage(),
            "module": record.module, "function": record.funcName, "line": record.lineno,
            "pid": record.process, "thread": record.thread,
        }
        for key in ("correlation_id", "request_id", "node_id", "intent_id",
                     "action", "duration_ms", "http_method", "http_path",
                     "http_status", "client_addr"):
            val = record.__dict__.get(key)
            if val is not None:
                entry[key] = val
        if record.exc_info and record.exc_info[1] is not None:
            entry["exception"] = {
                "type": record.exc_info[0].__name__ if record.exc_info[0] else "Unknown",
                "message": str(record.exc_info[1]),
                "traceback": self.formatException(record.exc_info),
            }
        return json.dumps(entry, default=str)


class VerboseConsoleFormatter(logging.Formatter):
    FORMAT = (
        "%(asctime)s.%(msecs)03d %(levelname)-8s "
        "[%(correlation_id)s] %(name)s:%(funcName)s:%(lineno)d %(message)s"
    )
    def format(self, record: logging.LogRecord) -> str:
        if not hasattr(record, "correlation_id"):
            record.correlation_id = "\u2014"  # type: ignore[attr-defined]
        return super().format(record)


class CorrelationFilter(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        if record.__dict__.get("correlation_id") in (None, ""):
            record.correlation_id = "\u2014"  # type: ignore[attr-defined]
        return True


def setup_logging(
    level: int | str = logging.DEBUG,
    output_format: str = "json",
    log_file: str | None = None,
    max_bytes: int = 10 * 1024 * 1024,
    backup_count: int = 5,
    force_verbose: bool = False,
) -> logging.Logger:
    resolved_level = logging.DEBUG if force_verbose else (
        level if isinstance(level, int) else logging.getLevelName(str(level).upper())
    )
    root = logging.getLogger()
    root.setLevel(logging.DEBUG if force_verbose else resolved_level)
    for handler in root.handlers[:]:
        root.removeHandler(handler)
    root.addFilter(CorrelationFilter())

    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setLevel(resolved_level)
    console_handler.setFormatter(VerboseConsoleFormatter(
        fmt=VerboseConsoleFormatter.FORMAT, datefmt="%Y-%m-%dT%H:%M:%S"))
    root.addHandler(console_handler)

    json_handler = logging.StreamHandler(sys.stderr)
    json_handler.setLevel(logging.DEBUG)
    json_handler.setFormatter(JSONFormatter())
    root.addHandler(json_handler)

    default_log_dir = os.path.join(
        os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data", "logs"
    )
    target = log_file or os.path.join(default_log_dir, "vigile-master.log")
    try:
        os.makedirs(os.path.dirname(target), exist_ok=True)
        fh = logging.handlers.RotatingFileHandler(
            target, maxBytes=max_bytes, backupCount=backup_count, encoding="utf-8")
        fh.setLevel(logging.DEBUG)
        fh.setFormatter(JSONFormatter())
        root.addHandler(fh)
    except OSError:
        pass

    for noisy in ("uvicorn.access", "passlib", "httpcore", "httpx"):
        logging.getLogger(noisy).setLevel(logging.WARNING)

    logging.getLogger("vigile").info(
        "Vigile structured logging initialized",
        extra={"level": logging.getLevelName(resolved_level), "pid": os.getpid()},
    )
    return root


def get_logger(name: str) -> logging.Logger:
    return logging.getLogger(f"vigile.{name}")
