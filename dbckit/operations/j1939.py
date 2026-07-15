"""Minimal J1939 lookup helpers based on DBC attribute values."""
from __future__ import annotations

from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from dbckit.model.database import Database
    from dbckit.views import MessageView, SignalView


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
