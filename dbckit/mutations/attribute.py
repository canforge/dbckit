"""Pure internal helpers for attribute mutations."""
from __future__ import annotations

from typing import Any

from dbckit._cycle_time import CYCLE_TIME_ATTRIBUTE, validate_cycle_time
from dbckit.model.database import AttributeDefinition, Database

from ._cycle_time import ensure_definition, normalise_message


def define_attribute(db: Database, definition: AttributeDefinition) -> Database:
    """Return a new Database with the attribute definition added/replaced."""
    messages = db.messages
    if definition.name == CYCLE_TIME_ATTRIBUTE:
        messages = {
            arbitration_id: normalise_message(message, definition)
            for arbitration_id, message in db.messages.items()
        }
    return db.model_copy(
        update={
            "attributes": {**db.attributes, definition.name: definition},
            "messages": messages,
        }
    )


def set_database_attribute(db: Database, name: str, value: Any) -> Database:
    """Set a database-level attribute value."""
    return db.model_copy(
        update={"attribute_values": {**db.attribute_values, name: value}}
    )


def unset_database_attribute(db: Database, name: str) -> Database:
    """Remove a database-level attribute value."""
    return db.model_copy(
        update={"attribute_values": {k: v for k, v in db.attribute_values.items() if k != name}}
    )


def set_node_attribute(db: Database, node_name: str, name: str, value: Any) -> Database:
    """Set an attribute on one node."""
    node = _get_node(db, node_name)
    new_node = node.model_copy(update={"attributes": {**node.attributes, name: value}})
    return db.model_copy(update={"nodes": {**db.nodes, node_name: new_node}})


def unset_node_attribute(db: Database, node_name: str, name: str) -> Database:
    """Remove an attribute from one node."""
    node = _get_node(db, node_name)
    new_node = node.model_copy(
        update={"attributes": {k: v for k, v in node.attributes.items() if k != name}}
    )
    return db.model_copy(update={"nodes": {**db.nodes, node_name: new_node}})


def set_message_attribute(db: Database, arbitration_id: int, name: str, value: Any) -> Database:
    """Set an attribute on one message."""
    msg = _get_msg(db, arbitration_id)
    attributes = {**msg.attributes, name: value}
    update: dict[str, Any] = {"attributes": attributes}
    definitions = db.attributes
    if name == CYCLE_TIME_ATTRIBUTE:
        definition = db.attributes.get(CYCLE_TIME_ATTRIBUTE)
        cycle_time = validate_cycle_time(value, definition)
        attributes[name] = cycle_time
        update["cycle_time"] = cycle_time
        if definition is None:
            definitions = ensure_definition(db)
    new_msg = msg.model_copy(update=update)
    return db.model_copy(
        update={
            "attributes": definitions,
            "messages": {**db.messages, arbitration_id: new_msg},
        }
    )


def unset_message_attribute(db: Database, arbitration_id: int, name: str) -> Database:
    """Remove an attribute from one message."""
    msg = _get_msg(db, arbitration_id)
    update: dict[str, Any] = {
        "attributes": {k: v for k, v in msg.attributes.items() if k != name}
    }
    if name == CYCLE_TIME_ATTRIBUTE:
        update["cycle_time"] = None
    new_msg = msg.model_copy(update=update)
    return db.model_copy(update={"messages": {**db.messages, arbitration_id: new_msg}})


def set_signal_attribute(
    db: Database,
    arbitration_id: int,
    signal_name: str,
    name: str,
    value: Any,
) -> Database:
    """Set an attribute on one signal."""
    msg = _get_msg(db, arbitration_id)
    sig = _get_sig(msg, signal_name)
    new_sig = sig.model_copy(update={"attributes": {**sig.attributes, name: value}})
    new_msg = msg.model_copy(update={"signals": {**msg.signals, signal_name: new_sig}})
    return db.model_copy(update={"messages": {**db.messages, arbitration_id: new_msg}})


def unset_signal_attribute(db: Database, arbitration_id: int, signal_name: str, name: str) -> Database:
    """Remove an attribute from one signal."""
    msg = _get_msg(db, arbitration_id)
    sig = _get_sig(msg, signal_name)
    new_sig = sig.model_copy(
        update={"attributes": {k: v for k, v in sig.attributes.items() if k != name}}
    )
    new_msg = msg.model_copy(update={"signals": {**msg.signals, signal_name: new_sig}})
    return db.model_copy(update={"messages": {**db.messages, arbitration_id: new_msg}})


def delete_attribute(db: Database, name: str) -> Database:
    """Remove the attribute definition *name* and all its values."""
    new_defs = {k: v for k, v in db.attributes.items() if k != name}
    new_av = {k: v for k, v in db.attribute_values.items() if k != name}
    new_nodes = {
        node_name: node.model_copy(
            update={"attributes": {k: v for k, v in node.attributes.items() if k != name}}
        )
        for node_name, node in db.nodes.items()
    }

    new_messages = {}
    for arb_id, msg in db.messages.items():
        new_msg_attrs = {k: v for k, v in msg.attributes.items() if k != name}
        new_sigs = {
            sn: sig.model_copy(
                update={"attributes": {k: v for k, v in sig.attributes.items() if k != name}}
            )
            for sn, sig in msg.signals.items()
        }
        update: dict[str, Any] = {
            "attributes": new_msg_attrs,
            "signals": new_sigs,
        }
        if name == CYCLE_TIME_ATTRIBUTE:
            update["cycle_time"] = None
        new_messages[arb_id] = msg.model_copy(update=update)

    return db.model_copy(
        update={
            "attributes": new_defs,
            "attribute_values": new_av,
            "nodes": new_nodes,
            "messages": new_messages,
        }
    )


def _get_msg(db: Database, arb_id: int):
    if arb_id not in db.messages:
        raise KeyError(f"No message with arbitration_id={arb_id:#x}.")
    return db.messages[arb_id]


def _get_node(db: Database, node_name: str):
    if node_name not in db.nodes:
        raise KeyError(f"Node '{node_name}' not found.")
    return db.nodes[node_name]


def _get_sig(msg, signal_name: str):
    if signal_name not in msg.signals:
        raise KeyError(f"Signal '{signal_name}' not in message {msg.arbitration_id:#x}.")
    return msg.signals[signal_name]
