"""Serialize a Database model back to DBC text (round-trip safe)."""
from __future__ import annotations

from dbckit._cycle_time import (
    CYCLE_TIME_ATTRIBUTE,
    coerce_cycle_time,
    validate_cycle_time,
)
from dbckit.model.database import AttributeDefinition, AttributeKind, Database
from dbckit.model.message import Message
from dbckit.model.signal import ByteOrder, Signal
from dbckit.mutations._cycle_time import automatic_cycle_time_definition


def _q(s: str) -> str:
    return f'"{s}"'


def _fmt(v: float) -> str:
    if v == int(v):
        return str(int(v))
    return repr(v)


def dump(db: Database) -> str:
    """Serialize a Database to a DBC-formatted string."""
    out: list[str] = []
    cycle_times = [_message_cycle_time(message) for message in db.messages.values()]
    attributes: dict[str, AttributeDefinition] = db.attributes
    if (
        CYCLE_TIME_ATTRIBUTE not in attributes
        and any(value is not None for value in cycle_times)
    ):
        attributes = {
            **attributes,
            CYCLE_TIME_ATTRIBUTE: automatic_cycle_time_definition(),
        }
    cycle_definition = attributes.get(CYCLE_TIME_ATTRIBUTE)
    for index, value in enumerate(cycle_times):
        if value is not None:
            cycle_times[index] = validate_cycle_time(value, cycle_definition)

    # VERSION
    out.append(f'VERSION "{db.version}"\n')

    # NS_
    out.append("\nNS_ :")
    for ns in db.ns_values:
        out.append(f"\n\t{ns}")
    out.append("\n")

    # BS_
    out.append(f"\nBS_ :{' ' + db.bit_timing if db.bit_timing else ''}\n")

    # BU_
    out.append("\nBU_ :" + "".join(f" {n}" for n in db.nodes) + "\n")

    # VAL_TABLE_
    for vt in db.value_tables.values():
        entries = " ".join(f"{k} {_q(v)}" for k, v in sorted(vt.values.items()))
        out.append(f"\nVAL_TABLE_ {vt.name} {entries} ;\n")

    # BO_ / SG_
    for msg in db.messages.values():
        emit_id = msg.arbitration_id | 0x80000000 if msg.is_extended_frame else msg.arbitration_id
        sender = msg.senders[0] if msg.senders else "Vector__XXX"
        out.append(f"\nBO_ {emit_id} {msg.name}: {msg.length} {sender}\n")
        for sig in msg.signals.values():
            out.append(_fmt_signal(sig))
    out.append("\n")

    # BO_TX_BU_
    tx_lines: list[str] = []
    for msg in db.messages.values():
        if len(msg.senders) > 1:
            emit_id = msg.arbitration_id | 0x80000000 if msg.is_extended_frame else msg.arbitration_id
            tx_lines.append(
                f"BO_TX_BU_ {emit_id} : {','.join(msg.senders)};\n"
            )
    if tx_lines:
        out.append("\n")
        out.extend(tx_lines)

    # EV_ / ENVVAR_DATA_
    if db.environment_variables:
        out.append("\n")
        for ev in db.environment_variables.values():
            nodes_str = ",".join(ev.access_nodes) if ev.access_nodes else "Vector__XXX"
            out.append(
                f"EV_ {ev.name}: {ev.var_type}"
                f" [{_fmt(ev.minimum)}|{_fmt(ev.maximum)}]"
                f" {_q(ev.unit)}"
                f" {_fmt(ev.initial_value)} {ev.ev_id}"
                f" {ev.access_type} {nodes_str} ;\n"
            )
        for ev in db.environment_variables.values():
            if ev.data_size is not None:
                out.append(f"ENVVAR_DATA_ {ev.name}: {ev.data_size} ;\n")

    # CM_
    cm: list[str] = []
    if "comment" in db.dbc_specific:
        cm.append(f"CM_ {_q(str(db.dbc_specific['comment']))};\n")
    for msg in db.messages.values():
        if msg.comment:
            cm.append(f"CM_ BO_  {msg.arbitration_id} {_q(msg.comment)};\n")
        for sig in msg.signals.values():
            if sig.comment:
                cm.append(f"CM_ SG_  {msg.arbitration_id} {sig.name} {_q(sig.comment)};\n")
    for node in db.nodes.values():
        if node.comment:
            cm.append(f"CM_ BU_  {node.name} {_q(node.comment)};\n")
    for ev in db.environment_variables.values():
        if ev.comment:
            cm.append(f"CM_ EV_  {ev.name} {_q(ev.comment)};\n")
    if cm:
        out.append("\n")
        out.extend(cm)

    # BA_DEF_
    if attributes:
        out.append("\n")
        for ad in attributes.values():
            scope = f"{ad.object_type} " if ad.object_type else ""
            out.append(f"BA_DEF_ {scope}{_q(ad.name)} {_fmt_attr_type(ad)};\n")

    # BA_DEF_DEF_
    if attributes:
        out.append("\n")
        for ad in attributes.values():
            if ad.default is not None:
                out.append(f"BA_DEF_DEF_  {_q(ad.name)} {_fmt_attr_val(ad.default, ad.kind)};\n")

    # BA_ — database level
    if db.attribute_values:
        out.append("\n")
        for name, val in db.attribute_values.items():
            ad = attributes.get(name)
            kind = ad.kind if ad else AttributeKind.STRING
            out.append(f"BA_ {_q(name)} {_fmt_attr_val(val, kind)};\n")

    # BA_ — message / signal level
    for msg, cycle_time in zip(db.messages.values(), cycle_times):
        if cycle_time is not None:
            kind = attributes[CYCLE_TIME_ATTRIBUTE].kind
            out.append(
                f"BA_ {_q(CYCLE_TIME_ATTRIBUTE)} BO_ {msg.arbitration_id} "
                f"{_fmt_attr_val(cycle_time, kind)};\n"
            )
        for name, val in msg.attributes.items():
            if name == CYCLE_TIME_ATTRIBUTE:
                continue
            ad = attributes.get(name)
            kind = ad.kind if ad else AttributeKind.STRING
            out.append(f"BA_ {_q(name)} BO_ {msg.arbitration_id} {_fmt_attr_val(val, kind)};\n")
        for sig in msg.signals.values():
            for name, val in sig.attributes.items():
                ad = attributes.get(name)
                kind = ad.kind if ad else AttributeKind.STRING
                out.append(
                    f"BA_ {_q(name)} SG_ {msg.arbitration_id} {sig.name} {_fmt_attr_val(val, kind)};\n"
                )

    # BA_ — node level
    for node in db.nodes.values():
        for name, val in node.attributes.items():
            ad = attributes.get(name)
            kind = ad.kind if ad else AttributeKind.STRING
            out.append(f"BA_ {_q(name)} BU_ {node.name} {_fmt_attr_val(val, kind)};\n")

    # BA_ — environment variable level
    for ev in db.environment_variables.values():
        for name, val in ev.attributes.items():
            ad = attributes.get(name)
            kind = ad.kind if ad else AttributeKind.STRING
            out.append(f"BA_ {_q(name)} EV_ {ev.name} {_fmt_attr_val(val, kind)};\n")

    # VAL_
    val_lines: list[str] = []
    for msg in db.messages.values():
        for sig in msg.signals.values():
            if sig.value_table:
                entries = " ".join(
                    f"{k} {_q(v)}" for k, v in sorted(sig.value_table.values.items())
                )
                val_lines.append(f"VAL_ {msg.arbitration_id} {sig.name} {entries} ;\n")
    for ev in db.environment_variables.values():
        if ev.value_table:
            entries = " ".join(
                f"{k} {_q(v)}" for k, v in sorted(ev.value_table.values.items())
            )
            val_lines.append(f"VAL_ {ev.name} {entries} ;\n")
    if val_lines:
        out.append("\n")
        out.extend(val_lines)

    # SIG_GROUP_
    if db.signal_groups:
        out.append("\n")
        for sg in db.signal_groups:
            out.append(
                f"SIG_GROUP_ {sg.message_id} {sg.name} {sg.repetitions} : "
                + " ".join(sg.signal_names)
                + ";\n"
            )

    # SIG_VALTYPE_
    sigtype_lines: list[str] = []
    for msg in db.messages.values():
        for sig in msg.signals.values():
            if sig.signal_type is not None:
                sigtype_lines.append(
                    f"SIG_VALTYPE_ {msg.arbitration_id} {sig.name} : {sig.signal_type} ;\n"
                )
    if sigtype_lines:
        out.append("\n")
        out.extend(sigtype_lines)

    return "".join(out)


def _message_cycle_time(message: Message) -> int | None:
    """Resolve the effective stored cycle time without mutating the message."""
    if message.cycle_time is not None:
        return coerce_cycle_time(message.cycle_time)
    if CYCLE_TIME_ATTRIBUTE in message.attributes:
        return coerce_cycle_time(message.attributes[CYCLE_TIME_ATTRIBUTE])
    return None


def _fmt_signal(sig: Signal) -> str:
    bo = "1" if sig.byte_order == ByteOrder.little_endian else "0"
    sign = "-" if sig.is_signed else "+"
    receivers = ",".join(sig.receivers) if sig.receivers else "Vector__XXX"
    mux = f" {sig.multiplex_indicator}" if sig.multiplex_indicator else ""
    lo = _fmt(sig.minimum) if sig.minimum is not None else "0"
    hi = _fmt(sig.maximum) if sig.maximum is not None else "0"
    return (
        f" SG_ {sig.name}{mux} : {sig.start_bit}|{sig.length}@{bo}{sign}"
        f" ({_fmt(sig.factor)},{_fmt(sig.offset)}) [{lo}|{hi}] {_q(sig.unit)} {receivers}\n"
    )


def _fmt_attr_type(ad) -> str:
    if ad.kind == AttributeKind.INT:
        lo = _fmt(ad.minimum or 0)
        hi = _fmt(ad.maximum or 0)
        return f"INT {lo} {hi}"
    if ad.kind == AttributeKind.HEX:
        lo = _fmt(ad.minimum or 0)
        hi = _fmt(ad.maximum or 0)
        return f"HEX {lo} {hi}"
    if ad.kind == AttributeKind.FLOAT:
        return f"FLOAT {ad.minimum or 0.0} {ad.maximum or 0.0}"
    if ad.kind == AttributeKind.STRING:
        return "STRING"
    if ad.kind == AttributeKind.ENUM:
        return "ENUM " + ", ".join(_q(v) for v in ad.values)
    return "STRING"


def _fmt_attr_val(value: object, kind: AttributeKind) -> str:
    if kind in (AttributeKind.STRING, AttributeKind.ENUM):
        return _q(str(value))
    if kind == AttributeKind.FLOAT:
        return str(float(value))  # type: ignore[arg-type]
    return str(value)
