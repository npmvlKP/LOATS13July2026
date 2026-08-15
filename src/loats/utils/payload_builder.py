"""Payload building utilities for OpenAlgo API requests."""

from enum import Enum
from typing import Any

from ..models import (
    OrderType,
    OrderVariety,
    ProductType,
    TransactionType,
)


def _enum_to_value(value: Any | Enum) -> Any:
    """Convert enum to its value if it's an enum, otherwise return as-is."""
    if isinstance(value, Enum):
        return value.value
    return value


def build_place_order_payload(
    symbol: str,
    quantity: int,
    order_type: str | OrderType,
    price: float | None = None,
    variety: str | OrderVariety = "regular",
    transaction_type: str | TransactionType = "BUY",
    product_type: str | ProductType = "MIS",
    trigger_price: float | None = None,
    stop_loss: float | None = None,
    take_profit: float | None = None,
    trailing_stop_loss: float | None = None,
) -> dict[str, Any]:
    """Build payload for place_order API call."""
    payload: dict[str, Any] = {
        "symbol": symbol,
        "quantity": quantity,
        "order_type": _enum_to_value(order_type),
        "variety": _enum_to_value(variety),
        "transaction_type": _enum_to_value(transaction_type),
        "product_type": _enum_to_value(product_type),
    }
    if price is not None:
        payload["price"] = price
    if trigger_price is not None:
        payload["trigger_price"] = trigger_price
    if stop_loss is not None:
        payload["stop_loss"] = stop_loss
    if take_profit is not None:
        payload["take_profit"] = take_profit
    if trailing_stop_loss is not None:
        payload["trailing_stop_loss"] = trailing_stop_loss
    return payload


def build_place_smart_order_payload(
    symbol: str,
    quantity: int,
    order_type: str | OrderType,
    price: float | None = None,
    trigger_price: float | None = None,
    stop_loss: float | None = None,
    take_profit: float | None = None,
    trailing_stop_loss: float | None = None,
    strategy: str = "simple",
    transaction_type: str | TransactionType = "BUY",
    product_type: str | ProductType = "MIS",
    metadata: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Build payload for place_smart_order API call."""
    payload: dict[str, Any] = {
        "symbol": symbol,
        "quantity": quantity,
        "order_type": _enum_to_value(order_type),
        "strategy": strategy,
        "transaction_type": _enum_to_value(transaction_type),
        "product_type": _enum_to_value(product_type),
    }
    if price is not None:
        payload["price"] = price
    if trigger_price is not None:
        payload["trigger_price"] = trigger_price
    if stop_loss is not None:
        payload["stop_loss"] = stop_loss
    if take_profit is not None:
        payload["take_profit"] = take_profit
    if trailing_stop_loss is not None:
        payload["trailing_stop_loss"] = trailing_stop_loss
    if metadata is not None:
        payload["metadata"] = metadata
    return payload


def build_modify_order_payload(
    order_id: str,
    quantity: int | None = None,
    order_type: str | OrderType | None = None,
    price: float | None = None,
    trigger_price: float | None = None,
    stop_loss: float | None = None,
    take_profit: float | None = None,
    trailing_stop_loss: float | None = None,
) -> dict[str, Any]:
    """Build payload for modify_order API call."""
    payload: dict[str, Any] = {"order_id": order_id}
    if quantity is not None:
        payload["quantity"] = quantity
    if order_type is not None:
        payload["order_type"] = _enum_to_value(order_type)
    if price is not None:
        payload["price"] = price
    if trigger_price is not None:
        payload["trigger_price"] = trigger_price
    if stop_loss is not None:
        payload["stop_loss"] = stop_loss
    if take_profit is not None:
        payload["take_profit"] = take_profit
    if trailing_stop_loss is not None:
        payload["trailing_stop_loss"] = trailing_stop_loss
    return payload


def build_cancel_order_payload(order_id: str) -> dict[str, Any]:
    """Build payload for cancel_order API call."""
    return {"order_id": order_id}
