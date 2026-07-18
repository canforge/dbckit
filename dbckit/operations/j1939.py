"""J1939 identifier math and attribute-based lookup helpers."""
from __future__ import annotations

from typing import TYPE_CHECKING, Any

from dbckit._frame_id import CAN_EXTENDED_FRAME_ID_MASK

if TYPE_CHECKING:
    from dbckit.model.database import Database
    from dbckit.views import MessageView, SignalView


def pgn_from_arbitration_id(arbitration_id: int) -> int:
    """Return the 18-bit J1939 PGN encoded in a 29-bit arbitration ID.

    Priority and source-address bits are omitted. For PDU1 identifiers
    (``PF < 240``), the destination-address byte is also cleared. For PDU2
    identifiers, that byte is the group extension and remains part of the PGN.
    """
    if isinstance(arbitration_id, bool) or not isinstance(arbitration_id, int):
        raise TypeError("J1939 arbitration ID must be an integer.")
    if not 0 <= arbitration_id <= CAN_EXTENDED_FRAME_ID_MASK:
        raise ValueError(
            "J1939 arbitration ID must be between 0x0 and 0x1fffffff."
        )

    pgn = (arbitration_id >> 8) & 0x3FFFF
    pdu_format = (arbitration_id >> 16) & 0xFF
    if pdu_format < 0xF0:
        pgn &= 0x3FF00
    return pgn


def find_messages_by_pgn(db: Database, pgn: int) -> list[MessageView]:
    """Return all messages whose `PGN` attribute matches *pgn*."""
    from dbckit.views import MessageView  # noqa: PLC0415

    return [
        MessageView(db, arbitration_id)
        for arbitration_id, message in db.messages.items()
        if _normalize_attr_int(message.attributes.get("PGN")) == pgn
    ]


def find_signals_by_spn(db: Database, spn: int) -> list[tuple[MessageView, SignalView]]:
    """Return all `(MessageView, SignalView)` pairs whose `SPN` attribute matches *spn*."""
    from dbckit.views import MessageView, SignalView  # noqa: PLC0415

    results: list[tuple[MessageView, SignalView]] = []
    for arbitration_id, message in db.messages.items():
        message_view: MessageView | None = None
        for signal_name, signal in message.signals.items():
            if _normalize_attr_int(signal.attributes.get("SPN")) != spn:
                continue
            if message_view is None:
                message_view = MessageView(db, arbitration_id)
            results.append((message_view, SignalView(db, arbitration_id, signal_name)))
    return results


def get_message_by_pgn(db: Database, pgn: int) -> MessageView:
    """Return the unique message whose `PGN` attribute matches *pgn*."""
    matches = find_messages_by_pgn(db, pgn)
    if not matches:
        raise KeyError(f"No message with PGN={pgn}.")
    if len(matches) > 1:
        raise ValueError(f"Multiple messages matched PGN={pgn}.")
    return matches[0]


def get_signal_by_spn(db: Database, spn: int) -> tuple[MessageView, SignalView]:
    """Return the unique `(MessageView, SignalView)` pair whose `SPN` attribute matches *spn*."""
    matches = find_signals_by_spn(db, spn)
    if not matches:
        raise KeyError(f"No signal with SPN={spn}.")
    if len(matches) > 1:
        raise ValueError(f"Multiple signals matched SPN={spn}.")
    return matches[0]


def _normalize_attr_int(value: Any) -> int | None:
    if value is None or isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value
    if isinstance(value, float):
        return int(value) if value.is_integer() else None
    if isinstance(value, str):
        stripped = value.strip()
        if not stripped:
            return None
        try:
            return int(stripped, 0)
        except ValueError:
            return None
    return None
