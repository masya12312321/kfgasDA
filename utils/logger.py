"""Central logging setup. No silent failures: every module logs via get_logger."""
import logging
import sys
from logging.handlers import RotatingFileHandler
from pathlib import Path

_CONFIGURED = False


def setup_logging(level: str = "INFO", log_dir: str = "logs") -> None:
    global _CONFIGURED
    if _CONFIGURED:
        return
    _CONFIGURED = True

    Path(log_dir).mkdir(parents=True, exist_ok=True)
    root = logging.getLogger()
    root.setLevel(getattr(logging, level.upper(), logging.INFO))

    fmt = logging.Formatter(
        "%(asctime)s | %(levelname)-7s | %(name)s | %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    console = logging.StreamHandler(sys.stdout)
    console.setFormatter(fmt)
    root.addHandler(console)

    fileh = RotatingFileHandler(
        Path(log_dir) / "bot.log", maxBytes=10 * 1024 * 1024, backupCount=5, encoding="utf-8"
    )
    fileh.setFormatter(fmt)
    root.addHandler(fileh)

    logging.getLogger("aiohttp").setLevel(logging.WARNING)
    logging.getLogger("aiogram").setLevel(logging.WARNING)


def get_logger(name: str) -> logging.Logger:
    return logging.getLogger(name)
