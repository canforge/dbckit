"""Pure mutation functions for nodes — all return a new Database."""
from __future__ import annotations

from dbckit.model.database import Database, Node


def add_node(db: Database, node: Node) -> Database:
    """Return a new Database with *node* added. Raises if name already exists."""
    if node.name in db.nodes:
        raise ValueError(f"Node '{node.name}' already exists.")
    return db.model_copy(update={"nodes": {**db.nodes, node.name: node}})


def delete_node(db: Database, name: str) -> Database:
    """Return a new Database with the named node removed."""
    _get(db, name)
    return db.model_copy(update={"nodes": {k: v for k, v in db.nodes.items() if k != name}})


def rename_node(db: Database, name: str, new_name: str) -> Database:
    """Return a new Database with the named node renamed.

    Also updates all message senders and signal receivers that reference the node.
    Raises ``ValueError`` if a node named *new_name* already exists.
    """
    _get(db, name)
    if new_name != name and new_name in db.nodes:
        raise ValueError(f"A node named '{new_name}' already exists.")
    node = db.nodes[name]
    renamed_node = node.model_copy(update={"name": new_name})
    new_nodes = {(new_name if k == name else k): (renamed_node if k == name else v)
                 for k, v in db.nodes.items()}

    # Patch senders / receivers
    new_messages = {}
    for arb_id, msg in db.messages.items():
        new_senders = [new_name if s == name else s for s in msg.senders]
        new_signals = {}
        for sig_name, sig in msg.signals.items():
            new_rx = [new_name if r == name else r for r in sig.receivers]
            new_signals[sig_name] = sig.model_copy(update={"receivers": new_rx})
        new_messages[arb_id] = msg.model_copy(
            update={"senders": new_senders, "signals": new_signals}
        )

    return db.model_copy(update={"nodes": new_nodes, "messages": new_messages})


def _get(db: Database, name: str) -> Node:
    if name not in db.nodes:
        raise KeyError(f"Node '{name}' not found.")
    return db.nodes[name]
