"""Configuration loader: .env + config.yaml.

Prefers PyYAML; falls back to a minimal 2-space-indent YAML subset parser
so the core runs even without third-party packages.
"""
from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from dotenv import load_dotenv  # type: ignore

try:
    import yaml  # type: ignore
except Exception:  # pragma: no cover
    yaml = None

BASE_DIR = Path(__file__).resolve().parent


# ---------------- mini YAML fallback ----------------

def _mini_yaml(text: str) -> dict:
    """Parses nested maps with 2-space indentation and scalar values."""
    root: dict = {}
    stack: list[tuple[int, dict]] = [(-1, root)]
    for raw in text.splitlines():
        if not raw.strip() or raw.strip().startswith("#"):
            continue
        indent = len(raw) - len(raw.lstrip(" "))
        key, _, val = raw.strip().partition(":")
        while stack and indent <= stack[-1][0]:
            stack.pop()
        parent = stack[-1][1]
        val = val.strip()
        if not val:
            node: dict = {}
            parent[key] = node
            stack.append((indent, node))
        else:
            parent[key] = _parse_scalar(val)
    return root


def _parse_scalar(v: str) -> Any:
    v = v.split(" #")[0].strip()  # strip trailing comments
    if v.startswith("[") and v.endswith("]"):
        inner = v[1:-1].strip()
        return [_parse_scalar(x) for x in inner.split(",")] if inner else []
    low = v.lower()
    if low in ("true", "false"):
        return low == "true"
    try:
        return int(v)
    except ValueError:
        pass
    try:
        return float(v)
    except ValueError:
        pass
    return v


def load_config(path: Path | None = None) -> dict:
    cfg_path = path or BASE_DIR / "config.yaml"
    text = cfg_path.read_text(encoding="utf-8")
    if yaml is not None:
        return yaml.safe_load(text)
    return _mini_yaml(text)


# ---------------- typed access ----------------

@dataclass
class Settings:
    bot_token: str = ""
    alert_chat_ids: list[int] = field(default_factory=list)
    mode: str = "LIVE"
    log_level: str = "INFO"
    bybit_base: str = "https://api.bybit.com"
    bybit_ws: str = "wss://stream.bybit.com/v5/public/linear"
    db_path: str = "data/signals.db"
    config: dict = field(default_factory=dict)

    def section(self, name: str) -> dict:
        return dict(self.config.get(name, {}))

    @property
    def weights(self) -> dict[str, float]:
        return {k: float(v) for k, v in self.section("weights").items()}


def load_settings() -> Settings:
    load_dotenv(BASE_DIR / ".env")
    cfg = load_config()
    ids = [s.strip() for s in os.getenv("ALERT_CHAT_IDS", "").split(",") if s.strip()]
    return Settings(
        bot_token=os.getenv("BOT_TOKEN", ""),
        alert_chat_ids=[int(x) for x in ids],
        mode=os.getenv("MODE", cfg.get("mode", "LIVE")).upper(),
        log_level=os.getenv("LOG_LEVEL", "INFO"),
        bybit_base=os.getenv("BYBIT_BASE", "https://api.bybit.com"),
        bybit_ws=os.getenv("BYBIT_WS", "wss://stream.bybit.com/v5/public/linear"),
        db_path=os.getenv("DB_PATH", str(BASE_DIR / "data" / "signals.db")),
        config=cfg,
    )
