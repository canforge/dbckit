"""Context-bound proxy views: MessageView, SignalView, NodeView.

Each view holds a reference to a source :class:`~dbckit.model.database.Database`
together with the key needed to locate the underlying model object.  Mutation
methods return a *new* :class:`~dbckit.model.database.Database` — the original is
never modified.

Typical usage::

    db2 = db.message(500).signal("EngineSpeed").update(factor=0.5)
    db3 = db.message(500).rename("MotorData").delete_signal("EngineTemp")
    db4 = db.node("ECU1").rename("EngineECU")
"""
from __future__ import annotations

from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from dbckit.model.database import Database
    from dbckit.model.message import Message
    from dbckit.model.signal import BitSlot, Signal


# ── SignalView ────────────────────────────────────────────────────────────────

class SignalView:
    """Context-bound proxy for a :class:`~dbckit.model.signal.Signal`.

    Exposes every :class:`~dbckit.model.signal.Signal` property as a read-only
    attribute and adds mutation/decode helpers that return a new
    :class:`~dbckit.model.database.Database`.
    """

    __slots__ = ("_db", "_arbitration_id", "_signal_name")

    def __init__(self, db: Database, arbitration_id: int, signal_name: str) -> None:
        self._db = db
        self._arbitration_id = arbitration_id
        self._signal_name = signal_name

    # ── underlying object ─────────────────────────────────────────────────────

    @property
    def _signal(self) -> Signal:
        return self._db.messages[self._arbitration_id].signals[self._signal_name]

    # ── forwarded Signal properties ───────────────────────────────────────────

    @property
    def name(self) -> str:
        return self._signal.name

    @property
    def start_bit(self) -> int:
        return self._signal.start_bit

    @property
    def length(self) -> int:
        return self._signal.length

    @property
    def byte_order(self):  # type: ignore[return]
        return self._signal.byte_order

    @property
    def is_signed(self) -> bool:
        return self._signal.is_signed

    @property
    def factor(self) -> float:
        return self._signal.factor

    @property
    def offset(self) -> float:
        return self._signal.offset

    @property
    def minimum(self) -> float | None:
        return self._signal.minimum

    @property
    def maximum(self) -> float | None:
        return self._signal.maximum

    @property
    def unit(self) -> str:
        return self._signal.unit

    @property
    def receivers(self) -> list[str]:
        return self._signal.receivers

    @property
    def comment(self) -> str | None:
        return self._signal.comment

    @property
    def value_table(self):  # type: ignore[return]
        return self._signal.value_table

    @property
    def attributes(self) -> dict[str, Any]:
        return self._signal.attributes

    @property
    def multiplex_indicator(self) -> str | None:
        return self._signal.multiplex_indicator

    # ── decode helpers ────────────────────────────────────────────────────────

    def decode(self, data: bytes) -> float:
        """Decode this signal from *data* and return the physical value."""
        return self._signal.decode(data)

    def decode_phys(self, data: bytes) -> float | str:
        """Decode and resolve value-table labels (returns ``str`` when matched)."""
        return self._signal.decode_phys(data)

    def choices(self) -> dict[int, str] | None:
        """Return a copy of the value-table mapping, or ``None``."""
        return self._signal.choices()

    def choice(self, val: int) -> str | None:
        """Return the label for integer *val*, or ``None``."""
        return self._signal.choice(val)

    # ── mutation methods ──────────────────────────────────────────────────────

    def update(self, **fields: Any) -> Database:
        """Return a new :class:`~dbckit.model.database.Database` with fields updated."""
        from dbckit.mutations.signal import update_signal  # noqa: PLC0415
        return update_signal(self._db, self._arbitration_id, self._signal_name, **fields)

    def delete(self) -> Database:
        """Return a new :class:`~dbckit.model.database.Database` with this signal removed."""
        from dbckit.mutations.signal import delete_signal  # noqa: PLC0415
        return delete_signal(self._db, self._arbitration_id, self._signal_name)

    def rename(self, new_name: str) -> Database:
        """Return a new :class:`~dbckit.model.database.Database` with this signal renamed."""
        from dbckit.mutations.signal import rename_signal  # noqa: PLC0415
        return rename_signal(self._db, self._arbitration_id, self._signal_name, new_name)

    def add_choice(self, value: int, label: str) -> Database:
        """Return a new :class:`~dbckit.model.database.Database` with a value-table entry added."""
        from dbckit.mutations.signal import add_signal_choice  # noqa: PLC0415
        return add_signal_choice(self._db, self._arbitration_id, self._signal_name, value, label)

    def remove_choice(self, value: int) -> Database:
        """Return a new :class:`~dbckit.model.database.Database` with the value-table entry removed."""
        from dbckit.mutations.signal import remove_signal_choice  # noqa: PLC0415
        return remove_signal_choice(self._db, self._arbitration_id, self._signal_name, value)

    def set_attribute(self, name: str, value: Any) -> Database:
        """Return a new :class:`~dbckit.model.database.Database` with attribute *name* set to *value*."""
        from dbckit.mutations.attribute import set_signal_attribute  # noqa: PLC0415
        return set_signal_attribute(
            self._db,
            self._arbitration_id,
            self._signal_name,
            name,
            value,
        )

    def unset_attribute(self, name: str) -> Database:
        """Return a new :class:`~dbckit.model.database.Database` with attribute *name* removed."""
        from dbckit.mutations.attribute import unset_signal_attribute  # noqa: PLC0415
        return unset_signal_attribute(
            self._db,
            self._arbitration_id,
            self._signal_name,
            name,
        )

    def __repr__(self) -> str:
        s = self._signal
        return (
            f"<SignalView name={s.name!r} start_bit={s.start_bit} "
            f"length={s.length} factor={s.factor} offset={s.offset}>"
        )


# ── MessageView ───────────────────────────────────────────────────────────────

class MessageView:
    """Context-bound proxy for a :class:`~dbckit.model.message.Message`.

    Exposes every :class:`~dbckit.model.message.Message` property as a read-only
    attribute and adds typed accessors for signals plus mutation/codec helpers
    that return a new :class:`~dbckit.model.database.Database`.
    """

    __slots__ = ("_db", "_arbitration_id")

    def __init__(self, db: Database, arbitration_id: int) -> None:
        self._db = db
        self._arbitration_id = arbitration_id

    # ── underlying object ─────────────────────────────────────────────────────

    @property
    def _message(self) -> Message:
        return self._db.messages[self._arbitration_id]

    # ── forwarded Message properties ──────────────────────────────────────────

    @property
    def arbitration_id(self) -> int:
        return self._arbitration_id

    @property
    def name(self) -> str:
        return self._message.name

    @property
    def length(self) -> int:
        return self._message.length

    @property
    def senders(self) -> list[str]:
        return self._message.senders

    @property
    def comment(self) -> str | None:
        return self._message.comment

    @property
    def attributes(self) -> dict[str, Any]:
        return self._message.attributes

    @property
    def cycle_time(self) -> int | None:
        return self._message.cycle_time

    # ── signal accessors ──────────────────────────────────────────────────────

    def signal(self, name: str) -> SignalView:
        """Return a :class:`SignalView` for *name*.

        Raises :exc:`KeyError` if the signal does not exist.
        """
        if name not in self._message.signals:
            raise KeyError(f"No signal '{name}' in message '{self._message.name}'")
        return SignalView(self._db, self._arbitration_id, name)

    def list_signals(self) -> list[SignalView]:
        """Return all signals as an ordered list of :class:`SignalView`."""
        return [
            SignalView(self._db, self._arbitration_id, n)
            for n in self._message.signals
        ]

    def layout(self) -> list[BitSlot]:
        """Return the bit-slot layout for this message."""
        return self._message.layout()

    # ── codec helpers ─────────────────────────────────────────────────────────

    def decode(self, data: bytes) -> dict[str, float | int | str]:
        """Decode all signals and return ``name → physical value``.

        Value-table entries are resolved to string labels.
        """
        from dbckit.codec.decoder import decode_signal  # noqa: PLC0415
        result: dict[str, float | int | str] = {}
        for sig_name, sig in self._message.signals.items():
            phys = decode_signal(data, sig)
            if sig.value_table:
                raw_int = int(round((phys - sig.offset) / sig.factor))
                result[sig_name] = sig.value_table.values.get(raw_int, phys)
            else:
                result[sig_name] = phys
        return result

    def encode(self, values: dict[str, float]) -> bytes:
        """Encode signal values into a CAN frame payload."""
        from dbckit.codec.encoder import encode_signal  # noqa: PLC0415
        data = bytearray(self._message.length)
        for sig_name, physical in values.items():
            sig = self._message.signals.get(sig_name)
            if sig is None:
                raise KeyError(f"No signal '{sig_name}' in message '{self._message.name}'")
            encode_signal(data, sig, physical)
        return bytes(data)

    # ── mutation methods — this message ───────────────────────────────────────

    def update(self, **fields: Any) -> Database:
        """Return a new :class:`~dbckit.model.database.Database` with message fields updated."""
        from dbckit.mutations.message import update_message  # noqa: PLC0415
        return update_message(self._db, self._arbitration_id, **fields)

    def delete(self) -> Database:
        """Return a new :class:`~dbckit.model.database.Database` with this message removed."""
        from dbckit.mutations.message import delete_message  # noqa: PLC0415
        return delete_message(self._db, self._arbitration_id)

    def rename(self, new_name: str) -> Database:
        """Return a new :class:`~dbckit.model.database.Database` with this message renamed."""
        from dbckit.mutations.message import rename_message  # noqa: PLC0415
        return rename_message(self._db, self._arbitration_id, new_name)

    def change_arbitration_id(self, new_id: int) -> Database:
        """Return a new database with this message renumbered to *new_id*."""
        from dbckit.mutations.message import change_arbitration_id  # noqa: PLC0415

        return change_arbitration_id(self._db, self._arbitration_id, new_id)

    def add_sender(self, sender: str) -> Database:
        """Return a new database with *sender* added to this message."""
        from dbckit.mutations.message import add_sender  # noqa: PLC0415
        return add_sender(self._db, self._arbitration_id, sender)

    def remove_sender(self, sender: str) -> Database:
        """Return a new database with *sender* removed from this message."""
        from dbckit.mutations.message import remove_sender  # noqa: PLC0415
        return remove_sender(self._db, self._arbitration_id, sender)

    # ── mutation methods — signals ────────────────────────────────────────────

    def add_signal(self, sig: Signal) -> Database:
        """Return a new :class:`~dbckit.model.database.Database` with *sig* added."""
        from dbckit.mutations.signal import add_signal  # noqa: PLC0415
        return add_signal(self._db, self._arbitration_id, sig)

    def delete_signal(self, name: str) -> Database:
        """Return a new :class:`~dbckit.model.database.Database` with *name* removed."""
        from dbckit.mutations.signal import delete_signal  # noqa: PLC0415
        return delete_signal(self._db, self._arbitration_id, name)

    def rename_signal(self, old_name: str, new_name: str) -> Database:
        """Return a new :class:`~dbckit.model.database.Database` with the signal renamed."""
        from dbckit.mutations.signal import rename_signal  # noqa: PLC0415
        return rename_signal(self._db, self._arbitration_id, old_name, new_name)

    def update_signal(self, name: str, **fields: Any) -> Database:
        """Return a new :class:`~dbckit.model.database.Database` with signal fields updated."""
        from dbckit.mutations.signal import update_signal  # noqa: PLC0415
        return update_signal(self._db, self._arbitration_id, name, **fields)

    def set_attribute(self, name: str, value: Any) -> Database:
        """Return a new :class:`~dbckit.model.database.Database` with attribute *name* set to *value*."""
        from dbckit.mutations.attribute import set_message_attribute  # noqa: PLC0415
        return set_message_attribute(self._db, self._arbitration_id, name, value)

    def unset_attribute(self, name: str) -> Database:
        """Return a new :class:`~dbckit.model.database.Database` with attribute *name* removed."""
        from dbckit.mutations.attribute import unset_message_attribute  # noqa: PLC0415
        return unset_message_attribute(self._db, self._arbitration_id, name)

    def __repr__(self) -> str:
        m = self._message
        return (
            f"<MessageView id={self._arbitration_id:#x} name={m.name!r}"
            f" signals={len(m.signals)}>"
        )


# ── NodeView ──────────────────────────────────────────────────────────────────

class NodeView:
    """Context-bound proxy for a :class:`~dbckit.model.database.Node`.

    Exposes every :class:`~dbckit.model.database.Node` property as a read-only
    attribute and adds mutation helpers that return a new
    :class:`~dbckit.model.database.Database`.
    """

    __slots__ = ("_db", "_name")

    def __init__(self, db: Database, name: str) -> None:
        self._db = db
        self._name = name

    # ── underlying object ─────────────────────────────────────────────────────

    @property
    def _node(self):  # type: ignore[return]
        return self._db.nodes[self._name]

    # ── forwarded Node properties ─────────────────────────────────────────────

    @property
    def name(self) -> str:
        return self._name

    @property
    def comment(self) -> str | None:
        return self._node.comment

    @property
    def attributes(self) -> dict[str, Any]:
        return self._node.attributes

    # ── mutation methods ──────────────────────────────────────────────────────

    def delete(self) -> Database:
        """Return a new :class:`~dbckit.model.database.Database` with this node removed."""
        from dbckit.mutations.node import delete_node  # noqa: PLC0415
        return delete_node(self._db, self._name)

    def rename(self, new_name: str) -> Database:
        """Return a new :class:`~dbckit.model.database.Database` with this node renamed.

        Also patches all message senders and signal receivers that reference
        the old name.
        """
        from dbckit.mutations.node import rename_node  # noqa: PLC0415
        return rename_node(self._db, self._name, new_name)

    def set_attribute(self, name: str, value: Any) -> Database:
        """Return a new :class:`~dbckit.model.database.Database` with attribute *name* set to *value*."""
        from dbckit.mutations.attribute import set_node_attribute  # noqa: PLC0415
        return set_node_attribute(self._db, self._name, name, value)

    def unset_attribute(self, name: str) -> Database:
        """Return a new :class:`~dbckit.model.database.Database` with attribute *name* removed."""
        from dbckit.mutations.attribute import unset_node_attribute  # noqa: PLC0415
        return unset_node_attribute(self._db, self._name, name)

    def __repr__(self) -> str:
        return f"<NodeView name={self._name!r}>"
