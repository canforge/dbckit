"""Merge two Database instances."""
from __future__ import annotations

from typing import Literal

from dbckit.model.database import Database

MergeStrategy = Literal["raise", "ours", "theirs"]


def merge(
    db_a: Database,
    db_b: Database,
    strategy: MergeStrategy = "raise",
) -> Database:
    """Return a new Database that is the union of *db_a* and *db_b*.

    Conflict resolution for keys present in both:
      "raise"  — raise ValueError on any conflict
      "ours"   — prefer db_a
      "theirs" — prefer db_b
    """
    messages = _merge_dicts(db_a.messages, db_b.messages, strategy, "message")
    nodes = _merge_dicts(db_a.nodes, db_b.nodes, strategy, "node")
    attrs = _merge_dicts(db_a.attributes, db_b.attributes, strategy, "attribute")
    attr_vals = _merge_dicts(db_a.attribute_values, db_b.attribute_values, strategy, "attribute_value")
    value_tables = _merge_dicts(db_a.value_tables, db_b.value_tables, strategy, "value_table")
    envvars = _merge_dicts(db_a.environment_variables, db_b.environment_variables, strategy, "envvar")

    # Signal groups: concat and de-duplicate by (message_id, name)
    sg_keys: set[tuple] = set()
    signal_groups = []
    for sg in (*db_a.signal_groups, *db_b.signal_groups):
        key = (sg.message_id, sg.name)
        if key not in sg_keys:
            sg_keys.add(key)
            signal_groups.append(sg)

    return Database(
        version=db_b.version or db_a.version,
        nodes=nodes,
        messages=messages,
        attributes=attrs,
        attribute_values=attr_vals,
        value_tables=value_tables,
        signal_groups=signal_groups,
        environment_variables=envvars,
        ns_values=list(dict.fromkeys([*db_a.ns_values, *db_b.ns_values])),
        bit_timing=db_b.bit_timing or db_a.bit_timing,
        dbc_specific={**db_a.dbc_specific, **db_b.dbc_specific},
    )


def _merge_dicts(
    a: dict,
    b: dict,
    strategy: MergeStrategy,
    kind: str,
) -> dict:
    result = dict(a)
    for key, val_b in b.items():
        if key in result:
            if result[key] == val_b:
                continue  # identical — no conflict
            if strategy == "raise":
                raise ValueError(f"Merge conflict in {kind} '{key}'.")
            if strategy == "theirs":
                result[key] = val_b
            # "ours" → keep existing
        else:
            result[key] = val_b
    return result
