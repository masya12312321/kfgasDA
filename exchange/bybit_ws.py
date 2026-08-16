"""Bybit V5 public WebSocket (linear): tickers, trades, orderbook, liquidations, kline.

Runs as a supervised task with auto-reconnect. Incoming events are pushed into
per-symbol queues consumed by the scanner. Subscriptions are chunked
(Bybit limit: 10 args per subscribe frame).
"""
from __future__ import annotations

import asyncio
import json
from collections import defaultdict
from typing import Any, Awaitable, Callable, Optional

import aiohttp

from utils.logger import get_logger

log = get_logger("bybit.ws")

EventHandler = Callable[[str, str, dict], Awaitable[None]]  # (topic, symbol, payload)


class BybitWS:
    def __init__(self, url: str = "wss://stream.bybit.com/v5/public/linear"):
        self.url = url
        self._symbols: list[str] = []
        self._handlers: dict[str, EventHandler] = {}  # topic-prefix -> handler
        self._ws: Optional[aiohttp.ClientWebSocketResponse] = None
        self._session: Optional[aiohttp.ClientSession] = None
        self._running = False
        self._task: Optional[asyncio.Task] = None
        self._ping_task: Optional[asyncio.Task] = None

    def on(self, topic_prefix: str, handler: EventHandler) -> None:
        """topic_prefix e.g. 'tickers', 'publicTrade', 'orderbook.50', 'liquidation', 'kline.5'."""
        self._handlers[topic_prefix] = handler

    async def start(self, symbols: list[str]) -> None:
        self._symbols = symbols
        self._running = True
        self._task = asyncio.create_task(self._supervise(), name="bybit-ws")

    async def stop(self) -> None:
        self._running = False
        for t in (self._task, self._ping_task):
            if t:
                t.cancel()
        if self._session and not self._session.closed:
            await self._session.close()

    async def _supervise(self) -> None:
        backoff = 1.0
        while self._running:
            try:
                await self._run()
            except asyncio.CancelledError:
                raise
            except Exception as exc:  # noqa: BLE001 - reconnect on anything
                log.error("WS disconnected: %s — reconnecting in %.1fs", exc, backoff)
                await asyncio.sleep(backoff)
                backoff = min(backoff * 2, 60.0)
            else:
                backoff = 1.0

    def _topics(self) -> list[str]:
        topics: list[str] = []
        for s in self._symbols:
            topics += [
                f"tickers.{s}",
                f"publicTrade.{s}",
                f"orderbook.50.{s}",
                f"liquidation.{s}",
                f"kline.5.{s}",
            ]
        return topics

    async def _run(self) -> None:
        self._session = aiohttp.ClientSession()
        async with self._session.ws_connect(self.url, heartbeat=None) as ws:
            self._ws = ws
            topics = self._topics()
            for i in range(0, len(topics), 10):  # subscribe in chunks of 10
                await ws.send_json({"op": "subscribe", "args": topics[i:i + 10]})
                await asyncio.sleep(0.2)
            log.info("WS subscribed to %d topics (%d symbols)", len(topics), len(self._symbols))
            self._ping_task = asyncio.create_task(self._ping_loop(ws))
            async for msg in ws:
                if msg.type == aiohttp.WSMsgType.TEXT:
                    await self._dispatch(json.loads(msg.data))
                elif msg.type in (aiohttp.WSMsgType.CLOSED, aiohttp.WSMsgType.ERROR):
                    raise RuntimeError(f"WS closed: {msg.data}")

    async def _ping_loop(self, ws: aiohttp.ClientWebSocketResponse) -> None:
        while True:
            await asyncio.sleep(20)
            try:
                await ws.send_json({"op": "ping"})
            except Exception as exc:  # noqa: BLE001
                log.warning("WS ping failed: %s", exc)
                return

    async def _dispatch(self, msg: dict[str, Any]) -> None:
        topic = msg.get("topic")
        if not topic:
            return
        prefix = topic.split(".")[0]
        # orderbook.50.SYMBOL / kline.5.SYMBOL need 2-part prefix
        if prefix in ("orderbook", "kline"):
            prefix = ".".join(topic.split(".")[:2])
            symbol = topic.split(".")[2]
        else:
            symbol = topic.split(".", 1)[1] if "." in topic else ""
        handler = self._handlers.get(prefix)
        if handler:
            try:
                await handler(topic, symbol, msg.get("data"))
            except Exception as exc:  # noqa: BLE001 - handler bug must not kill WS
                log.error("WS handler error for %s: %s", topic, exc)
