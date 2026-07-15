"""Diff two Database instances."""
from __future__ import annotations

from typing import Literal

from pydantic import BaseModel

from dbckit.model.database import AttributeDefinition, Database, EnvironmentVariable, Node
from dbckit.model.message import Message
from dbckit.model.signal import Signal, SignalGroup


class SignalDiff(BaseModel):
    signal_name: str
    change: Literal["added", "removed", "modified"]
    before: Signal | None = None
    after: Signal | None = None


class MessageDiff(BaseModel):
    arbitration_id: int
    message_name: str
    signal_diffs: list[SignalDiff] = []
    field_changes: dict[str, tuple] = {}  # field → (before, after)


class DiffResult(BaseModel):
    added_messages: list[Message] = []
    removed_messages: list[Message] = []
    modified_messages: list[MessageDiff] = []
    added_nodes: list[Node] = []
    removed_nodes: list[Node] = []
    added_attributes: list[AttributeDefinition] = []
    removed_attributes: list[AttributeDefinition] = []
    added_signal_groups: list[SignalGroup] = []
    removed_signal_groups: list[SignalGroup] = []
    added_envvars: list[EnvironmentVariable] = []
    removed_envvars: list[EnvironmentVariable] = []

    @property
    def is_empty(self) -> bool:
        return not any([
            self.added_messages,
            self.removed_messages,
            self.modified_messages,
            self.added_nodes,
            self.removed_nodes,
            self.added_attributes,
            self.removed_attributes,
            self.added_signal_groups,
            self.removed_signal_groups,
            self.added_envvars,
            self.removed_envvars,
        ])


def diff(db_a: Database, db_b: Database) -> DiffResult:
    """Return a DiffResult describing changes from *db_a* to *db_b*."""
    result = DiffResult()

    # Messages
    ids_a = set(db_a.messages)
    ids_b = set(db_b.messages)
    result.added_messages = [db_b.messages[i] for i in sorted(ids_b - ids_a)]
    result.removed_messages = [db_a.messages[i] for i in sorted(ids_a - ids_b)]

    for arb_id in sorted(ids_a & ids_b):
        msg_a = db_a.messages[arb_id]
        msg_b = db_b.messages[arb_id]
        mdiff = _diff_message(msg_a, msg_b)
        if mdiff is not None:
            result.modified_messages.append(mdiff)

    # Nodes
    nodes_a = set(db_a.nodes)
    nodes_b = set(db_b.nodes)
    result.added_nodes = [db_b.nodes[n] for n in sorted(nodes_b - nodes_a)]
    result.removed_nodes = [db_a.nodes[n] for n in sorted(nodes_a - nodes_b)]

    # Attribute definitions
    attrs_a = set(db_a.attributes)
    attrs_b = set(db_b.attributes)
    result.added_attributes = [db_b.attributes[n] for n in sorted(attrs_b - attrs_a)]
    result.removed_attributes = [db_a.attributes[n] for n in sorted(attrs_a - attrs_b)]

    # Signal groups — keyed by (message_id, name)
    sg_key = lambda sg: (sg.message_id, sg.name)  # noqa: E731
    sg_a = {sg_key(sg): sg for sg in db_a.signal_groups}
    sg_b = {sg_key(sg): sg for sg in db_b.signal_groups}
    result.added_signal_groups = [sg_b[k] for k in sorted(set(sg_b) - set(sg_a))]
    result.removed_signal_groups = [sg_a[k] for k in sorted(set(sg_a) - set(sg_b))]

    # Environment variables
    ev_a = set(db_a.environment_variables)
    ev_b = set(db_b.environment_variables)
    result.added_envvars = [db_b.environment_variables[n] for n in sorted(ev_b - ev_a)]
    result.removed_envvars = [db_a.environment_variables[n] for n in sorted(ev_a - ev_b)]

    return result


def _diff_message(msg_a: Message, msg_b: Message) -> MessageDiff | None:
    field_changes: dict[str, tuple] = {}
    for field in ("name", "length", "senders", "comment", "cycle_time", "attributes"):
        va = getattr(msg_a, field)
        vb = getattr(msg_b, field)
        if va != vb:
            field_changes[field] = (va, vb)

    sigs_a = set(msg_a.signals)
    sigs_b = set(msg_b.signals)
    signal_diffs: list[SignalDiff] = []

    for name in sorted(sigs_b - sigs_a):
        signal_diffs.append(SignalDiff(signal_name=name, change="added", after=msg_b.signals[name]))
    for name in sorted(sigs_a - sigs_b):
        signal_diffs.append(SignalDiff(signal_name=name, change="removed", before=msg_a.signals[name]))
    for name in sorted(sigs_a & sigs_b):
        sa, sb = msg_a.signals[name], msg_b.signals[name]
        if sa != sb:
            signal_diffs.append(SignalDiff(signal_name=name, change="modified", before=sa, after=sb))

    if not field_changes and not signal_diffs:
        return None

    return MessageDiff(
        arbitration_id=msg_a.arbitration_id,
        message_name=msg_a.name,
        signal_diffs=signal_diffs,
        field_changes=field_changes,
    )
