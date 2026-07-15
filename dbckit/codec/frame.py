"""Encode and decode complete CAN frame payloads."""
from __future__ import annotations

from dbckit.codec.decoder import decode_signal
from dbckit.codec.encoder import encode_signal
from dbckit.model.database import Database
from dbckit.model.signal import Signal


def _resolve_phys(signal: Signal, physical: float) -> float | int | str:
    """Apply value-table resolution to a decoded physical value."""
    if signal.value_table:
        raw_int = int(round((physical - signal.offset) / signal.factor))
        return signal.value_table.values.get(raw_int, physical)
    return physical


def _mux_index(indicator: str | None) -> int | None:
    """Return the integer X from an 'mX' indicator, or None for M / non-mux."""
    if indicator and indicator != "M" and indicator.startswith("m"):
        try:
            return int(indicator[1:])
        except ValueError:
            pass
    return None


def decode_frame(
    db: Database,
    arbitration_id: int,
    data: bytes,
) -> dict[str, float | int | str]:
    """Decode signals in a CAN frame and return name → physical value.

    For multiplexed messages the active mux variant is determined by decoding
    the multiplexer signal (``M``) first. Only the non-mux signals, the ``M``
    signal itself, and the ``mX`` signals whose index matches the selector value
    are included in the result. Signals for other variants are omitted.

    Value-table entries are resolved to their string labels.

    If *data* is shorter than the message DLC, missing bytes are treated as
    ``0x00``. Extra bytes in an overlong payload are ignored by the signal
    layout.
    """
    msg = db.messages.get(arbitration_id)
    if msg is None:
        raise KeyError(f"No message with arbitration_id={arbitration_id:#x}")

    active_selector: int | None = None
    for signal in msg.signals.values():
        if signal.multiplex_indicator == "M":
            physical = decode_signal(data, signal)
            active_selector = int(
                round((physical - signal.offset) / signal.factor)
            )
            break

    result: dict[str, float | int | str] = {}
    for name, signal in msg.signals.items():
        mux_index = _mux_index(signal.multiplex_indicator)
        if mux_index is not None:
            if active_selector is None or mux_index != active_selector:
                continue
        physical = decode_signal(data, signal)
        result[name] = _resolve_phys(signal, physical)
    return result


def encode_frame(
    db: Database,
    arbitration_id: int,
    values: dict[str, float],
    *,
    strict: bool = False,
) -> bytes:
    """Encode signal values into a CAN frame payload sized to the message DLC.

    The multiplexing selector is taken from an explicitly supplied ``M`` value,
    or inferred from supplied ``mX`` signals. Contradictory or inactive mux
    values raise ``ValueError``.
    """
    msg = db.messages.get(arbitration_id)
    if msg is None:
        raise KeyError(f"No message with arbitration_id={arbitration_id:#x}")

    mux_signal_name: str | None = None
    mux_signal: Signal | None = None
    for name, signal in msg.signals.items():
        if signal.multiplex_indicator == "M":
            mux_signal_name = name
            mux_signal = signal
            break

    active_selector: int | None = None
    if mux_signal_name is not None and mux_signal is not None:
        if mux_signal_name in values:
            physical_mux = values[mux_signal_name]
            active_selector = int(
                round((physical_mux - mux_signal.offset) / mux_signal.factor)
            )
        else:
            for name in values:
                signal = msg.signals.get(name)
                if signal is None:
                    continue
                mux_index = _mux_index(signal.multiplex_indicator)
                if mux_index is not None:
                    if active_selector is not None and active_selector != mux_index:
                        raise ValueError(
                            f"Conflicting mux signals in values for message '{msg.name}': "
                            f"implied selector {active_selector} and {mux_index}"
                        )
                    active_selector = mux_index

    data = bytearray(msg.length)

    if (
        mux_signal_name is not None
        and mux_signal is not None
        and mux_signal_name not in values
        and active_selector is not None
    ):
        physical_mux = active_selector * mux_signal.factor + mux_signal.offset
        encode_signal(data, mux_signal, physical_mux, strict=strict)

    for name, physical in values.items():
        signal = msg.signals.get(name)
        if signal is None:
            raise KeyError(f"No signal '{name}' in message '{msg.name}'")
        mux_index = _mux_index(signal.multiplex_indicator)
        if mux_index is not None and (
            active_selector is None or mux_index != active_selector
        ):
            raise ValueError(
                f"Signal '{name}' (mux=m{mux_index}) is not active for selector "
                f"value {active_selector} in message '{msg.name}'"
            )
        encode_signal(data, signal, physical, strict=strict)

    return bytes(data)
