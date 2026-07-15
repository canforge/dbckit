"""Pure mutation functions for signals — all return a new Database."""
from __future__ import annotations

from dbckit.model.database import Database
from dbckit.model.message import Message
from dbckit.model.signal import BitSlot, ByteOrder, Signal, ValueTable


def add_signal(db: Database, arbitration_id: int, signal: Signal) -> Database:
    """Return a new Database with *signal* added to the specified message."""
    msg = _get_msg(db, arbitration_id)
    if signal.name in msg.signals:
        raise ValueError(
            f"Signal '{signal.name}' already exists in message {arbitration_id:#x}."
        )
    new_signals = {**msg.signals, signal.name: signal}
    return _replace_msg(db, msg.model_copy(update={"signals": new_signals}))


def update_signal(
    db: Database, arbitration_id: int, signal_name: str, **fields
) -> Database:
    """Return a new Database with the specified signal fields updated."""
    msg = _get_msg(db, arbitration_id)
    sig = _get_sig(msg, signal_name)
    updated = sig.model_copy(update=fields)
    new_signals = {**msg.signals, signal_name: updated}
    return _replace_msg(db, msg.model_copy(update={"signals": new_signals}))


def delete_signal(
    db: Database, arbitration_id: int, signal_name: str
) -> Database:
    """Return a new Database with the specified signal removed."""
    msg = _get_msg(db, arbitration_id)
    _get_sig(msg, signal_name)
    new_signals = {k: v for k, v in msg.signals.items() if k != signal_name}
    return _replace_msg(db, msg.model_copy(update={"signals": new_signals}))


def rename_signal(
    db: Database, arbitration_id: int, signal_name: str, new_name: str
) -> Database:
    """Return a new Database with the specified signal renamed.

    Raises ``ValueError`` if another signal in the same message already has *new_name*.
    """
    msg = _get_msg(db, arbitration_id)
    _get_sig(msg, signal_name)
    if new_name != signal_name and new_name in msg.signals:
        raise ValueError(
            f"Signal '{new_name}' already exists in message '{msg.name}' "
            f"({arbitration_id:#x})."
        )
    sig = msg.signals[signal_name]
    renamed = sig.model_copy(update={"name": new_name})
    new_signals = {
        (new_name if k == signal_name else k): (renamed if k == signal_name else v)
        for k, v in msg.signals.items()
    }
    return _replace_msg(db, msg.model_copy(update={"signals": new_signals}))


def add_signal_choice(
    db: Database, arbitration_id: int, signal_name: str, value: int, label: str
) -> Database:
    """Return a new Database with a value-description entry added to the signal."""
    msg = _get_msg(db, arbitration_id)
    sig = _get_sig(msg, signal_name)
    vt = sig.value_table or ValueTable(name=signal_name)
    new_vals = {**vt.values, value: label}
    new_vt = vt.model_copy(update={"values": new_vals})
    return _replace_msg(
        db,
        msg.model_copy(
            update={
                "signals": {
                    **msg.signals,
                    signal_name: sig.model_copy(update={"value_table": new_vt}),
                }
            }
        ),
    )


def remove_signal_choice(
    db: Database, arbitration_id: int, signal_name: str, value: int
) -> Database:
    """Return a new Database with a value-description entry removed from the signal."""
    msg = _get_msg(db, arbitration_id)
    sig = _get_sig(msg, signal_name)
    if sig.value_table is None or value not in sig.value_table.values:
        raise KeyError(f"Value {value} not in signal '{signal_name}' value table.")
    new_vals = {k: v for k, v in sig.value_table.values.items() if k != value}
    new_vt = sig.value_table.model_copy(update={"values": new_vals})
    return _replace_msg(
        db,
        msg.model_copy(
            update={
                "signals": {
                    **msg.signals,
                    signal_name: sig.model_copy(update={"value_table": new_vt}),
                }
            }
        ),
    )


def signal_layout(message: Message) -> list[BitSlot]:
    """Return a flat list of BitSlots for the 64-bit frame (8 bytes).

    Cells with no signal have signal_name=None.
    """
    total_bits = message.length * 8
    slots: dict[int, BitSlot] = {b: BitSlot(bit=b) for b in range(total_bits)}

    for sig in message.signals.values():
        bits = _signal_bits(sig)
        for idx, bit in enumerate(bits):
            if 0 <= bit < total_bits:
                slots[bit] = BitSlot(
                    bit=bit,
                    signal_name=sig.name,
                    is_msb=(idx == 0 and sig.byte_order == ByteOrder.big_endian)
                    or (idx == len(bits) - 1 and sig.byte_order == ByteOrder.little_endian),
                    is_lsb=(idx == 0 and sig.byte_order == ByteOrder.little_endian)
                    or (idx == len(bits) - 1 and sig.byte_order == ByteOrder.big_endian),
                    byte_order=sig.byte_order,
                )

    return [slots[b] for b in range(total_bits)]


# ── helpers ───────────────────────────────────────────────────────────────────

def _signal_bits(sig: Signal) -> list[int]:
    if sig.byte_order == ByteOrder.little_endian:
        return [sig.start_bit + i for i in range(sig.length)]
    # Motorola
    bits: list[int] = []
    byte_num = sig.start_bit >> 3
    bit_num = sig.start_bit & 7
    for _ in range(sig.length):
        bits.append(byte_num * 8 + bit_num)
        if bit_num == 0:
            bit_num = 7
            byte_num += 1
        else:
            bit_num -= 1
    return bits


def _get_msg(db: Database, arbitration_id: int) -> Message:
    if arbitration_id not in db.messages:
        raise KeyError(f"No message with arbitration_id={arbitration_id:#x}.")
    return db.messages[arbitration_id]


def _get_sig(msg: Message, name: str) -> Signal:
    if name not in msg.signals:
        raise KeyError(f"No signal '{name}' in message '{msg.name}'.")
    return msg.signals[name]


def _replace_msg(db: Database, msg: Message) -> Database:
    return db.model_copy(
        update={"messages": {**db.messages, msg.arbitration_id: msg}}
    )
