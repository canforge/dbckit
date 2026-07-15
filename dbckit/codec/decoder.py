"""Decode raw CAN frame bytes into physical signal values."""
from __future__ import annotations

import struct

from dbckit.codec._signal_type import ieee754_format
from dbckit.model.signal import ByteOrder, Signal


def _extract_raw_little_endian(data: bytes, start_bit: int, length: int) -> int:
    """Extract raw integer from bytes using Intel (little-endian) bit layout."""
    raw = 0
    for i in range(length):
        bit_pos = start_bit + i
        byte_idx = bit_pos >> 3
        bit_idx = bit_pos & 7
        if byte_idx < len(data) and (data[byte_idx] >> bit_idx) & 1:
            raw |= 1 << i
    return raw


def _extract_raw_big_endian(data: bytes, start_bit: int, length: int) -> int:
    """Extract raw integer from bytes using Motorola (big-endian) bit layout.

    In Motorola layout the start_bit is the MSB position counted in the DBC
    'visual' bit numbering (byte 0 bit 7 = bit 7, byte 1 bit 7 = bit 15, …).
    """
    # Convert DBC Motorola start_bit (MSB) to a linear bit stream bit index
    byte_num = start_bit >> 3
    bit_num = start_bit & 7

    raw = 0
    for i in range(length):
        if byte_num < len(data) and (data[byte_num] >> bit_num) & 1:
            raw |= 1 << (length - 1 - i)
        if bit_num == 0:
            bit_num = 7
            byte_num += 1
        else:
            bit_num -= 1
    return raw


def decode_signal(data: bytes, signal: Signal) -> float:
    """Decode a single signal from raw frame bytes.

    Integer signals use their signed or unsigned raw value. ``SIG_VALTYPE_``
    1 and 2 signals reinterpret their 32-bit or 64-bit payload as IEEE-754.
    The result is returned as ``numeric * factor + offset``.
    """
    if signal.byte_order == ByteOrder.little_endian:
        raw = _extract_raw_little_endian(data, signal.start_bit, signal.length)
    else:
        raw = _extract_raw_big_endian(data, signal.start_bit, signal.length)

    float_format = ieee754_format(signal)
    if float_format is not None:
        numeric = struct.unpack(float_format, raw.to_bytes(signal.length // 8, "big"))[0]
    else:
        # Sign-extend for signed integer signals
        if signal.is_signed and signal.length > 0:
            sign_bit = 1 << (signal.length - 1)
            if raw & sign_bit:
                raw -= 1 << signal.length
        numeric = raw

    return numeric * signal.factor + signal.offset
