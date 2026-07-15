"""Helpers for DBC ``SIG_VALTYPE_`` codec behavior."""
from __future__ import annotations

from dbckit.model.signal import Signal


def ieee754_format(signal: Signal) -> str | None:
    """Return the big-endian struct format for a float signal, if any.

    The codec's bit extractors normalize both DBC byte orders into the same
    integer bit pattern, so a single big-endian struct format can reinterpret
    that pattern as IEEE-754.
    """
    if signal.signal_type in (None, 0):
        return None

    formats = {1: (32, ">f"), 2: (64, ">d")}
    definition = formats.get(signal.signal_type)
    if definition is None:
        raise ValueError(
            f"Signal '{signal.name}': unsupported SIG_VALTYPE_ value "
            f"{signal.signal_type}; expected 0 (integer), 1 (float), or 2 (double)"
        )

    expected_length, fmt = definition
    if signal.length != expected_length:
        type_name = "float" if signal.signal_type == 1 else "double"
        raise ValueError(
            f"Signal '{signal.name}': SIG_VALTYPE_ {signal.signal_type} ({type_name}) "
            f"requires length {expected_length}, got {signal.length}"
        )
    return fmt
