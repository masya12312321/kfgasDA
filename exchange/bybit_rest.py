"""Bybit V5 public REST client (linear category). Async, rate-limited, retries.

Endpoints used (all public, no API key):
  GET /v5/market/tickers
  GET /v5/market/kline
  GET /v5/market/open-interest
  GET /v5/market/funding/history
  GET /v5/market/account-ratio        (long/short account ratio)
  GET /v5/market/orderbook
  GET /v5/market/recent-trade
  GET /v5/market/instruments-info
"""
from __future__ import annotations

from typing import Any, Optional

import aiohttp

from exchange.models import (
    Candle, FundingPoint, LongShortPoint, OIPoint, OrderBook,
    OrderBookLevel, Ticker, Trade,
)
from utils.logger import get_logger
from utils.rate_limiter import RateLimiter
from utils.retry import CircuitBreaker, async_retry

log = get_logger("bybit.rest")


class BybitRest:
    def __init__(self, base_url: str = "https://api.bybit.com", rate: float = 10.0):
        self.base = base_url.rstrip("/")
        self._session: Optional[aiohttp.ClientSession] = None
        self._limiter = RateLimiter(rate=rate, burst=int(rate * 2))
        self._breaker = CircuitBreaker(failure_threshold=5, cooldown_sec=60)

    async def __aenter__(self) -> "BybitRest":
        await self.start()
        return self

    async def __aexit__(self, *exc) -> None:
        await self.close()

    async def start(self) -> None:
        if self._session is None or self._session.closed:
            timeout = aiohttp.ClientTimeout(total=15)
            self._session = aiohttp.ClientSession(timeout=timeout)

    async def close(self) -> None:
        if self._session and not self._session.closed:
            await self._session.close()

    @async_retry(retries=4, base_delay=0.5, exceptions=(aiohttp.ClientError, TimeoutError, RuntimeError))
    async def _get(self, path: str, params: dict[str, Any]) -> dict:
        if not self._breaker.allow():
            raise RuntimeError("circuit breaker open for Bybit REST")
        assert self._session is not None, "call start() first"
        await self._limiter.acquire()
        params = {"category": "linear", **params}
        async with self._session.get(f"{self.base}{path}", params=params) as resp:
            data = await resp.json(content_type=None)
        if resp.status != 200 or data.get("retCode") != 0:
            self._breaker.record_failure()
            raise RuntimeError(f"Bybit error {data.get('retCode')}: {data.get('retMsg')} ({path})")
        self._breaker.record_success()
        return data["result"]

    # ---------------- market data ----------------

    async def get_tickers(self) -> list[Ticker]:
        res = await self._get("/v5/market/tickers", {})
        out: list[Ticker] = []
        for t in res.get("list", []):
            try:
                out.append(Ticker(
                    symbol=t["symbol"],
                    last_price=float(t.get("lastPrice") or 0),
                    mark_price=float(t.get("markPrice") or 0),
                    index_price=float(t.get("indexPrice") or 0),
                    funding_rate=float(t.get("fundingRate") or 0),
                    next_funding_time=int(t.get("nextFundingTime") or 0),
                    open_interest=float(t.get("openInterest") or 0),
                    open_interest_value=float(t.get("openInterestValue") or 0),
                    turnover_24h=float(t.get("turnover24h") or 0),
                    volume_24h=float(t.get("volume24h") or 0),
                    price_24h_pcnt=float(t.get("price24hPcnt") or 0) * 100,
                    bid1_price=float(t.get("bid1Price") or 0),
                    ask1_price=float(t.get("ask1Price") or 0),
                    high_24h=float(t.get("highPrice24h") or 0),
                    low_24h=float(t.get("lowPrice24h") or 0),
                ))
            except (KeyError, ValueError) as exc:
                log.warning("skip malformed ticker %s: %s", t.get("symbol"), exc)
        return out

    async def get_perp_symbols(self, min_turnover: float, max_symbols: int) -> list[str]:
        tickers = await self.get_tickers()
        perps = [t for t in tickers if t.symbol.endswith("USDT") and t.turnover_24h >= min_turnover]
        perps.sort(key=lambda t: t.turnover_24h, reverse=True)
        return [t.symbol for t in perps[:max_symbols]]

    async def get_klines(self, symbol: str, interval: str = "5", limit: int = 200) -> list[Candle]:
        """interval: Bybit minutes string ('1','5','15','60','240','D'). Oldest first."""
        res = await self._get("/v5/market/kline", {"symbol": symbol, "interval": interval, "limit": limit})
        candles = [
            Candle(start=int(r[0]), open=float(r[1]), high=float(r[2]), low=float(r[3]),
                   close=float(r[4]), volume=float(r[5]), turnover=float(r[6]))
            for r in res.get("list", [])
        ]
        candles.sort(key=lambda c: c.start)
        return candles

    async def get_open_interest_hist(self, symbol: str, interval: str = "5min", limit: int = 288) -> list[OIPoint]:
        """interval: 5min,15min,30min,1h,4h,1d. Oldest first."""
        res = await self._get("/v5/market/open-interest",
                              {"symbol": symbol, "intervalTime": interval, "limit": limit})
        pts = [OIPoint(ts=int(r["timestamp"]), open_interest=float(r["openInterest"]))
               for r in res.get("list", [])]
        pts.sort(key=lambda p: p.ts)
        return pts

    async def get_funding_hist(self, symbol: str, limit: int = 90) -> list[FundingPoint]:
        res = await self._get("/v5/market/funding/history", {"symbol": symbol, "limit": limit})
        pts = [FundingPoint(ts=int(r["fundingRateTimestamp"]), funding_rate=float(r["fundingRate"]))
               for r in res.get("list", [])]
        pts.sort(key=lambda p: p.ts)
        return pts

    async def get_long_short_ratio(self, symbol: str, period: str = "5min", limit: int = 48) -> list[LongShortPoint]:
        """Global long/short ACCOUNT ratio (proxy for positioning; see docs)."""
        res = await self._get("/v5/market/account-ratio",
                              {"symbol": symbol, "period": period, "limit": limit})
        pts = [LongShortPoint(ts=int(r["timestamp"]), buy_ratio=float(r["buyRatio"]),
                              sell_ratio=float(r["sellRatio"]))
               for r in res.get("list", [])]
        pts.sort(key=lambda p: p.ts)
        return pts

    async def get_orderbook(self, symbol: str, limit: int = 50) -> OrderBook:
        res = await self._get("/v5/market/orderbook", {"symbol": symbol, "limit": limit})
        return OrderBook(
            symbol=symbol,
            ts=int(res.get("ts", 0)),
            bids=[OrderBookLevel(price=float(p), size=float(s)) for p, s in res.get("b", [])],
            asks=[OrderBookLevel(price=float(p), size=float(s)) for p, s in res.get("a", [])],
        )

    async def get_recent_trades(self, symbol: str, limit: int = 1000) -> list[Trade]:
        res = await self._get("/v5/market/recent-trade", {"symbol": symbol, "limit": limit})
        trades = [Trade(ts=int(r["time"]), price=float(r["price"]), size=float(r["size"]),
                        side=r["side"]) for r in res.get("list", [])]
        trades.sort(key=lambda t: t.ts)
        return trades
