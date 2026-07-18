"""Pure mutation functions for messages — all return a new Database."""
from __future__ import annotations

from dbckit._cycle_time import CYCLE_TIME_ATTRIBUTE
from dbckit.model.database import Database
from dbckit.model.message import Message

from ._cycle_time import definition_for, ensure_definition, normalise_message


def add_message(db: Database, message: Message) -> Database:
    """Return a new Database with *message* added. Raises if id already exists."""
    if message.arbitration_id in db.messages:
        raise ValueError(
            f"Message with arbitration_id={message.arbitration_id:#x} already exists."
        )
    message = normalise_message(message, definition_for(db))
    attributes = db.attributes
    if message.cycle_time is not None:
        attributes = ensure_definition(db)
    return db.model_copy(
        update={
            "attributes": attributes,
            "messages": {**db.messages, message.arbitration_id: message},
        }
    )


def update_message(db: Database, arbitration_id: int, **fields) -> Database:
    """Return a new Database with the specified message fields updated."""
    msg = _get(db, arbitration_id)
    attributes = dict(fields.get("attributes", msg.attributes))
    if "cycle_time" in fields:
        raw_cycle_time = fields["cycle_time"]
        if raw_cycle_time is None:
            attributes.pop(CYCLE_TIME_ATTRIBUTE, None)
        else:
            attributes[CYCLE_TIME_ATTRIBUTE] = raw_cycle_time
    elif "attributes" in fields:
        raw_cycle_time = attributes.get(CYCLE_TIME_ATTRIBUTE)
        fields["cycle_time"] = raw_cycle_time
    fields["attributes"] = attributes
    updated = normalise_message(msg.model_copy(update=fields), definition_for(db))
    definitions = db.attributes
    if updated.cycle_time is not None:
        definitions = ensure_definition(db)
    return db.model_copy(
        update={
            "attributes": definitions,
            "messages": {**db.messages, arbitration_id: updated},
        }
    )


def change_arbitration_id(db: Database, old_id: int, new_id: int) -> Database:
    """Return a database with one message and its signal groups moved to *new_id*."""
    message = _get(db, old_id)
    if old_id == new_id:
        return db
    if new_id in db.messages:
        raise ValueError(f"Message with arbitration_id={new_id:#x} already exists.")

    changed = message.model_copy(update={"arbitration_id": new_id})
    messages = {
        (new_id if arbitration_id == old_id else arbitration_id): (
            changed if arbitration_id == old_id else existing
        )
        for arbitration_id, existing in db.messages.items()
    }
    signal_groups = [
        group.model_copy(update={"message_id": new_id})
        if group.message_id == old_id
        else group
        for group in db.signal_groups
    ]
    return db.model_copy(
        update={"messages": messages, "signal_groups": signal_groups}
    )


def delete_message(db: Database, arbitration_id: int) -> Database:
    """Return a new Database with the message and its signal groups removed."""
    _get(db, arbitration_id)
    new_messages = {k: v for k, v in db.messages.items() if k != arbitration_id}
    signal_groups = [
        group for group in db.signal_groups if group.message_id != arbitration_id
    ]
    return db.model_copy(
        update={"messages": new_messages, "signal_groups": signal_groups}
    )


def rename_message(db: Database, arbitration_id: int, new_name: str) -> Database:
    """Return a new Database with the specified message renamed.

    Raises ``ValueError`` if another message already has *new_name*.
    """
    current = _get(db, arbitration_id)
    if new_name != current.name:
        for msg in db.messages.values():
            if msg.arbitration_id != arbitration_id and msg.name == new_name:
                raise ValueError(
                    f"A message named '{new_name}' already exists "
                    f"(arbitration_id={msg.arbitration_id:#x})."
                )
    return update_message(db, arbitration_id, name=new_name)


def add_sender(db: Database, arbitration_id: int, sender: str) -> Database:
    """Return a new Database with *sender* added to the message."""
    msg = _get(db, arbitration_id)
    if sender in msg.senders:
        raise ValueError(f"Sender '{sender}' already exists in message '{msg.name}'.")
    return update_message(db, arbitration_id, senders=[*msg.senders, sender])


def remove_sender(db: Database, arbitration_id: int, sender: str) -> Database:
    """Return a new Database with *sender* removed from the message."""
    msg = _get(db, arbitration_id)
    if sender not in msg.senders:
        raise KeyError(f"Sender '{sender}' is not present in message '{msg.name}'.")
    return update_message(
        db,
        arbitration_id,
        senders=[existing for existing in msg.senders if existing != sender],
    )


def _get(db: Database, arbitration_id: int) -> Message:
    if arbitration_id not in db.messages:
        raise KeyError(f"No message with arbitration_id={arbitration_id:#x}.")
    return db.messages[arbitration_id]
