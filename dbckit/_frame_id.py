"""Shared helpers for the DBC extended-frame ID convention."""
from __future__ import annotations

DBC_EXTENDED_FRAME_FLAG = 0x80000000
CAN_EXTENDED_FRAME_ID_MASK = 0x1FFFFFFF


def decode_dbc_frame_id(raw_id: int) -> tuple[int, bool]:
    """Return the clean arbitration ID and whether DBC bit 31 is set."""
    is_extended_frame = bool(raw_id & DBC_EXTENDED_FRAME_FLAG)
    arbitration_id = (
        raw_id & CAN_EXTENDED_FRAME_ID_MASK if is_extended_frame else raw_id
    )
    return arbitration_id, is_extended_frame


def encode_dbc_frame_id(arbitration_id: int, is_extended_frame: bool) -> int:
    """Return the DBC integer for a clean arbitration ID and frame type."""
    if is_extended_frame:
        return arbitration_id | DBC_EXTENDED_FRAME_FLAG
    return arbitration_id
