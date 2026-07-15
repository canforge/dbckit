"""Extract a subset of messages into a new Database."""
from __future__ import annotations

from dbckit.model.database import Database


def extract(
    db: Database,
    message_ids: list[int] | None = None,
    *,
    message_names: list[str] | None = None,
    node_names: list[str] | None = None,
) -> Database:
    """Return a new Database containing messages selected by ID, name, or node.

    Selectors are combined as a union. Referenced nodes (senders/receivers) are
    included automatically. Node selection matches both senders and receivers.
    """
    message_ids = message_ids or []
    message_names = message_names or []
    node_names = node_names or []

    missing = [mid for mid in message_ids if mid not in db.messages]
    if missing:
        missing_hex = ", ".join(f"{m:#x}" for m in missing)
        raise KeyError(f"Message ids not found: {missing_hex}")

    known_message_names = {msg.name for msg in db.messages.values()}
    missing_names = [name for name in message_names if name not in known_message_names]
    if missing_names:
        raise KeyError(f"Message names not found: {', '.join(missing_names)}")

    missing_nodes = [name for name in node_names if name not in db.nodes]
    if missing_nodes:
        raise KeyError(f"Node names not found: {', '.join(missing_nodes)}")

    selected_ids = set(message_ids)
    requested_message_names = set(message_names)
    requested_node_names = set(node_names)
    for mid, msg in db.messages.items():
        if msg.name in requested_message_names:
            selected_ids.add(mid)
        if requested_node_names.intersection(msg.senders):
            selected_ids.add(mid)
            continue
        if any(requested_node_names.intersection(sig.receivers) for sig in msg.signals.values()):
            selected_ids.add(mid)

    ordered_ids = list(dict.fromkeys(message_ids))
    ordered_ids.extend(mid for mid in db.messages if mid in selected_ids and mid not in ordered_ids)
    messages = {mid: db.messages[mid] for mid in ordered_ids}

    # Collect referenced node names
    referenced_node_names: set[str] = set(node_names)
    for msg in messages.values():
        referenced_node_names.update(msg.senders)
        for sig in msg.signals.values():
            referenced_node_names.update(sig.receivers)

    nodes = {n: db.nodes[n] for n in referenced_node_names if n in db.nodes}

    # Signal groups referencing extracted messages
    signal_groups = [sg for sg in db.signal_groups if sg.message_id in messages]

    return Database(
        version=db.version,
        filename=db.filename,
        nodes=nodes,
        messages=messages,
        attributes=db.attributes,
        attribute_values=db.attribute_values,
        value_tables=db.value_tables,
        signal_groups=signal_groups,
        environment_variables=db.environment_variables,
        ns_values=db.ns_values,
        bit_timing=db.bit_timing,
        dbc_specific=db.dbc_specific,
    )


def search_messages(db: Database, query: str) -> list:
    """Return messages whose name or comment contains *query* (case-insensitive)."""
    q = query.lower()
    return [
        msg for msg in db.messages.values()
        if q in msg.name.lower() or (msg.comment and q in msg.comment.lower())
    ]


def search_signals(db: Database, query: str) -> list[tuple]:
    """Return (Message, Signal) pairs where signal name/comment matches *query*."""
    q = query.lower()
    results = []
    for msg in db.messages.values():
        for sig in msg.signals.values():
            if q in sig.name.lower() or (sig.comment and q in sig.comment.lower()):
                results.append((msg, sig))
    return results
