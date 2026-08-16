"""Pydantic models for Bybit V5 data (linear USDT perpetuals)."""
from __future__ import annotations

from typing import Optional

from pydantic import BaseModel


class Ticker(BaseModel):
    symbol: str
    last_price: float
    mark_price: float
    index_price: float
    funding_rate: float
    next_funding_time: int
    open_interest: float            # in contracts/coins
    open_interest_value: float      # in USDT
    turnover_24h: float
    volume_24h: float
    price_24h_pcnt: float
    bid1_price: float
    ask1_price: float
    high_24h: float
    low_24h: float


class Candle(BaseModel):
    start: int      # ms
    open: float
    high: float
    low: float
    close: float
    volume: float
    turnover: float


class OrderBookLevel(BaseModel):
    price: float
    size: float


class OrderBook(BaseModel):
    symbol: str
    ts: int
    bids: list[OrderBookLevel]
    asks: list[OrderBookLevel]


class Trade(BaseModel):
    ts: int
    price: float
    size: float
    side: str       # "Buy" | "Sell"


class OIPoint(BaseModel):
    ts: int
    open_interest: float


class FundingPoint(BaseModel):
    ts: int
    funding_rate: float


class LongShortPoint(BaseModel):
    ts: int
    buy_ratio: float
    sell_ratio: float


class Liquidation(BaseModel):
    symbol: str
    side: str       # liquidated position side: "Buy" = long liq
    price: float
    size: float
    ts: int


class FactorResult(BaseModel):
    """Output of one indicator engine, fed into weighted voting."""
    name: str
    signal: float = 0.0          # -1..+1
    strength: float = 0.0        # 0..100
    confidence: float = 0.0      # 0..100 data confidence for this factor
    available: bool = True
    details: dict = {}
    note: Optional[str] = None


class SignalDecision(BaseModel):
    symbol: str
    direction: str               # STRONG_LONG..STRONG_SHORT/NEUTRAL
    weighted_vote: float
    confidence: float
    quality: str                 # A+..D
    priority: str                # CRITICAL/HIGH/NORMAL/LOW
    regime: str
    factors: list[FactorResult]
    price: float
    data_quality: float
    conflicts: list[str] = []
    ts: int = 0
