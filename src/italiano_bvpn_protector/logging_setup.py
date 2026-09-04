from __future__ import annotations

import logging
from logging.handlers import RotatingFileHandler
from pathlib import Path

_FORMAT = "%(asctime)s [%(levelname)s] %(name)s: %(message)s"


def setup_root_logging(log_dir: Path) -> None:
    log_dir.mkdir(parents=True, exist_ok=True)
    root = logging.getLogger()
    root.setLevel(logging.INFO)

    console = logging.StreamHandler()
    console.setFormatter(logging.Formatter(_FORMAT))
    root.addHandler(console)

    app_file = RotatingFileHandler(
        log_dir / "app.log", maxBytes=5_000_000, backupCount=5, encoding="utf-8"
    )
    app_file.setFormatter(logging.Formatter(_FORMAT))
    root.addHandler(app_file)


def get_server_logger(log_dir: Path, server_name: str) -> logging.Logger:
    logger = logging.getLogger(f"server.{server_name}")
    logger.setLevel(logging.INFO)
    logger.propagate = True

    safe_name = "".join(c if c.isalnum() or c in "-_" else "_" for c in server_name)
    handler = RotatingFileHandler(
        log_dir / f"{safe_name}.log",
        maxBytes=5_000_000,
        backupCount=5,
        encoding="utf-8",
    )
    handler.setFormatter(logging.Formatter(_FORMAT))
    logger.addHandler(handler)
    return logger
