"""Encode physical signal values into raw CAN frame bytes."""
from __future__ import annotations

import struct

from dbckit.codec._signal_type import ieee754_format
from dbckit.model.signal import ByteOrder, Signal


def _pack_raw_little_endian(data: bytearray, start_bit: int, length: int, raw: int) -> None:
    """Pack raw integer into bytearray using Intel (little-endian) bit layout.

    Bits that fall beyond the end of *data* are silently skipped.
    """
    for i in range(length):
        bit_pos = start_bit + i
        byte_idx = bit_pos >> 3
        bit_idx = bit_pos & 7
        if byte_idx < len(data):
            if (raw >> i) & 1:
                data[byte_idx] |= 1 << bit_idx
            else:
                data[byte_idx] &= ~(1 << bit_idx)


def _pack_raw_big_endian(data: bytearray, start_bit: int, length: int, raw: int) -> None:
    """Pack raw integer into bytearray using Motorola (big-endian) bit layout.

    Bits that fall beyond the end of *data* are silently skipped.
    """
    byte_num = start_bit >> 3
    bit_num = start_bit & 7

    for i in range(length):
        if byte_num < len(data):
            if (raw >> (length - 1 - i)) & 1:
                data[byte_num] |= 1 << bit_num
            else:
                data[byte_num] &= ~(1 << bit_num)
        if bit_num == 0:
            bit_num = 7
            byte_num += 1
        else:
            bit_num -= 1


def encode_signal(
    data: bytearray,
    signal: Signal,
    physical: float,
    *,
    strict: bool = False,
) -> None:
    """Encode a physical value into *data* for the given signal (in-place).

    Integer signals convert the physical value to a raw integer via::

        raw = round((physical - offset) / factor)

    ``SIG_VALTYPE_`` 1 and 2 signals instead store IEEE-754 single- or
    double-precision values after reversing the scale and offset.

    **Overflow behaviour** — by default an integer raw value is *clamped* to the
    signal's bit-width range before writing, so out-of-range values are
    silently truncated.  Pass ``strict=True`` to raise ``ValueError`` instead.

    If any signal bits fall beyond the end of *data* they are silently skipped
    (the buffer is not extended).  Use a buffer of at least ``ceil(DLC)`` bytes
    to avoid partial writes.
    """
    unscaled = (physical - signal.offset) / signal.factor
    float_format = ieee754_format(signal)
    if float_format is not None:
        try:
            raw = int.from_bytes(struct.pack(float_format, unscaled), "big")
        except (OverflowError, struct.error) as exc:
            type_name = "float" if signal.signal_type == 1 else "double"
            raise ValueError(
                f"Signal '{signal.name}': physical {physical!r} cannot be represented "
                f"as an IEEE-754 {type_name}"
            ) from exc

        if signal.byte_order == ByteOrder.little_endian:
            _pack_raw_little_endian(data, signal.start_bit, signal.length, raw)
        else:
            _pack_raw_big_endian(data, signal.start_bit, signal.length, raw)
        return

    raw = int(round(unscaled))

    if signal.is_signed:
        min_val = -(1 << (signal.length - 1))
        max_val = (1 << (signal.length - 1)) - 1
    else:
        min_val = 0
        max_val = (1 << signal.length) - 1

    if not (min_val <= raw <= max_val):
        if strict:
            raise ValueError(
                f"Signal '{signal.name}': physical {physical!r} → raw {raw} is outside "
                f"[{min_val}, {max_val}] for a "
                f"{'signed' if signal.is_signed else 'unsigned'} {signal.length}-bit signal"
            )
        raw = max(min_val, min(max_val, raw))

    # Two's complement for negative signed values
    if raw < 0:
        raw += 1 << signal.length

    if signal.byte_order == ByteOrder.little_endian:
        _pack_raw_little_endian(data, signal.start_bit, signal.length, raw)
    else:
        _pack_raw_big_endian(data, signal.start_bit, signal.length, raw)
