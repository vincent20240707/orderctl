from __future__ import annotations

from enum import Enum


class Verdict(str, Enum):
    PASS = "PASS"
    ALLOW = "ALLOW"
    WARN = "WARN"
    BLOCK = "BLOCK"
    ERROR = "ERROR"
    UNKNOWN = "UNKNOWN"


class IntentType(str, Enum):
    OPEN_LONG = "OPEN_LONG"
    CLOSE_LONG = "CLOSE_LONG"
    OPEN_SHORT = "OPEN_SHORT"
    CLOSE_SHORT = "CLOSE_SHORT"


class OrderRole(str, Enum):
    ENTRY = "ENTRY"
    STOP_LOSS = "STOP_LOSS"
    TAKE_PROFIT = "TAKE_PROFIT"
    SCALE_IN = "SCALE_IN"
    SCALE_OUT = "SCALE_OUT"
    BACKSTOP = "BACKSTOP"
    HEDGE = "HEDGE"
    EMERGENCY_EXIT = "EMERGENCY_EXIT"


class Side(str, Enum):
    BUY = "BUY"
    SELL = "SELL"


class OrderType(str, Enum):
    LIMIT = "LIMIT"
    STOP = "STOP"
    STOP_LIMIT = "STOP_LIMIT"
    TRAILING_STOP = "TRAILING_STOP"
    MARKET = "MARKET"


class PositionSide(str, Enum):
    LONG = "LONG"
    SHORT = "SHORT"
    FLAT = "FLAT"
    UNKNOWN = "UNKNOWN"
