"""Pure signal-group mutations; all functions return a new Database."""
from __future__ import annotations

from dbckit.model.database import Database
from dbckit.model.signal import SignalGroup


def add_signal_group(db: Database, group: SignalGroup) -> Database:
    """Return a new Database with *group* added."""
    _require_message(db, group.message_id)
    if _find_group(db, group.message_id, group.name) is not None:
        raise ValueError(
            f"Signal group '{group.name}' already exists for message "
            f"{group.message_id:#x}."
        )
    for signal_name in group.signal_names:
        _require_signal(db, group.message_id, signal_name)
    return db.model_copy(update={"signal_groups": [*db.signal_groups, group]})


def remove_signal_group(db: Database, message_id: int, name: str) -> Database:
    """Return a new Database without the named signal group."""
    index = _require_group_index(db, message_id, name)
    groups = [group for i, group in enumerate(db.signal_groups) if i != index]
    return db.model_copy(update={"signal_groups": groups})


def add_signal_to_group(
    db: Database, message_id: int, group_name: str, signal_name: str
) -> Database:
    """Return a new Database with *signal_name* added to a signal group."""
    index = _require_group_index(db, message_id, group_name)
    _require_signal(db, message_id, signal_name)
    group = db.signal_groups[index]
    if signal_name in group.signal_names:
        raise ValueError(
            f"Signal '{signal_name}' already belongs to signal group '{group_name}'."
        )
    return _replace_group(
        db,
        index,
        group.model_copy(update={"signal_names": [*group.signal_names, signal_name]}),
    )


def remove_signal_from_group(
    db: Database, message_id: int, group_name: str, signal_name: str
) -> Database:
    """Return a new Database with *signal_name* removed from a signal group."""
    index = _require_group_index(db, message_id, group_name)
    group = db.signal_groups[index]
    if signal_name not in group.signal_names:
        raise KeyError(
            f"Signal '{signal_name}' is not in signal group '{group_name}'."
        )
    return _replace_group(
        db,
        index,
        group.model_copy(
            update={
                "signal_names": [
                    existing
                    for existing in group.signal_names
                    if existing != signal_name
                ]
            }
        ),
    )


def _require_message(db: Database, message_id: int) -> None:
    if message_id not in db.messages:
        raise KeyError(f"No message with arbitration_id={message_id:#x}.")


def _require_signal(db: Database, message_id: int, signal_name: str) -> None:
    _require_message(db, message_id)
    msg = db.messages[message_id]
    if signal_name not in msg.signals:
        raise KeyError(f"No signal '{signal_name}' in message '{msg.name}'.")


def _find_group(db: Database, message_id: int, name: str) -> int | None:
    for index, group in enumerate(db.signal_groups):
        if group.message_id == message_id and group.name == name:
            return index
    return None


def _require_group_index(db: Database, message_id: int, name: str) -> int:
    index = _find_group(db, message_id, name)
    if index is None:
        raise KeyError(
            f"No signal group '{name}' for message arbitration_id={message_id:#x}."
        )
    return index


def _replace_group(db: Database, index: int, group: SignalGroup) -> Database:
    groups = [group if i == index else existing for i, existing in enumerate(db.signal_groups)]
    return db.model_copy(update={"signal_groups": groups})
