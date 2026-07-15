"""Shared helpers for the DBC ``GenMsgCycleTime`` convention."""
from __future__ import annotations

from decimal import Decimal, InvalidOperation
from math import isfinite
from typing import Any, Protocol

CYCLE_TIME_ATTRIBUTE = "GenMsgCycleTime"
AUTO_CYCLE_TIME_MINIMUM = 0
AUTO_CYCLE_TIME_MAXIMUM = 2_147_483_647
AUTO_CYCLE_TIME_DEFAULT = 0


class CycleTimeDefinition(Protocol):
    """The range fields needed from an attribute definition."""

    minimum: float | None
    maximum: float | None


def coerce_cycle_time(value: Any) -> int:
    """Return *value* as an integer cycle time or raise ``ValueError``."""
    if isinstance(value, bool):
        raise ValueError("GenMsgCycleTime must be an integer, not a boolean")
    try:
        decimal = Decimal(str(value))
    except (InvalidOperation, ValueError, TypeError):
        raise ValueError(f"GenMsgCycleTime must be an integer, got {value!r}") from None
    if not decimal.is_finite() or decimal != decimal.to_integral_value():
        raise ValueError(f"GenMsgCycleTime must be an integer, got {value!r}")
    return int(decimal)


def validate_cycle_time(
    value: Any,
    definition: CycleTimeDefinition | None = None,
) -> int:
    """Coerce and validate a cycle time against an effective definition."""
    cycle_time = coerce_cycle_time(value)
    minimum = (
        AUTO_CYCLE_TIME_MINIMUM if definition is None else definition.minimum
    )
    maximum = (
        AUTO_CYCLE_TIME_MAXIMUM if definition is None else definition.maximum
    )
    if minimum is not None and (not isfinite(minimum) or cycle_time < minimum):
        raise ValueError(
            f"GenMsgCycleTime value {cycle_time} is outside the declared range "
            f"[{_format_bound(minimum)}, {_format_bound(maximum)}]"
        )
    if maximum is not None and (not isfinite(maximum) or cycle_time > maximum):
        raise ValueError(
            f"GenMsgCycleTime value {cycle_time} is outside the declared range "
            f"[{_format_bound(minimum)}, {_format_bound(maximum)}]"
        )
    return cycle_time


def _format_bound(value: float | None) -> str:
    if value is None:
        return "unbounded"
    if not isfinite(value):
        return str(value)
    if value == int(value):
        return str(int(value))
    return str(value)
