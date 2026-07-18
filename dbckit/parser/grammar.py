"""Lark grammar loader and AST → model transformer."""
from __future__ import annotations

from pathlib import Path
from typing import Any

from lark import Lark, Transformer, v_args
from lark.exceptions import VisitError

from dbckit._cycle_time import (
    CYCLE_TIME_ATTRIBUTE,
    coerce_cycle_time,
    validate_cycle_time,
)
from dbckit._frame_id import decode_dbc_frame_id
from dbckit.model.database import (
    AttributeDefinition,
    AttributeKind,
    Database,
    EnvironmentVariable,
    Node,
)
from dbckit.model.message import Message
from dbckit.model.signal import ByteOrder, Signal, SignalGroup, ValueTable


def _load_grammar() -> str:
    return (Path(__file__).parent / "dbc.lark").read_text(encoding="utf-8")


def _make_parser() -> Lark:
    return Lark(
        _load_grammar(),
        parser="lalr",
        propagate_positions=False,
    )


_PARSER: Lark | None = None


def get_parser() -> Lark:
    global _PARSER
    if _PARSER is None:
        _PARSER = _make_parser()
    return _PARSER


def _str(token: Any) -> str:
    s = str(token)
    if len(s) >= 2 and s[0] == '"' and s[-1] == '"':
        return s[1:-1]
    return s


def _int(token: Any) -> int:
    return int(float(str(token)))


def _float(token: Any) -> float:
    return float(str(token))


def _coerce_attr(raw: Any, kind: AttributeKind) -> Any:
    s = str(raw)
    if kind == AttributeKind.STRING:
        return _str(raw)
    if kind in (AttributeKind.INT, AttributeKind.HEX):
        try:
            return int(float(s))
        except (ValueError, TypeError):
            return _str(raw)
    if kind == AttributeKind.FLOAT:
        try:
            return float(s)
        except (ValueError, TypeError):
            return _str(raw)
    if kind == AttributeKind.ENUM:
        return _str(raw)
    return _str(raw)


@v_args(inline=False)
class DBCTransformer(Transformer):
    """Transforms a Lark parse tree into a Database model."""

    def __init__(self) -> None:
        super().__init__()
        self._db = Database()

    def _require_message(self, arb_id: int, section: str) -> Message:
        msg = self._db.messages.get(arb_id)
        if msg is None:
            raise ValueError(
                f"{section} references unknown message arbitration_id={arb_id:#x}"
            )
        return msg

    def _require_signal(
        self, arb_id: int, sig_name: str, section: str
    ) -> tuple[Message, Signal]:
        msg = self._require_message(arb_id, section)
        sig = msg.signals.get(sig_name)
        if sig is None:
            raise ValueError(
                f"{section} references unknown signal '{sig_name}' in message "
                f"arbitration_id={arb_id:#x}"
            )
        return msg, sig

    def _require_envvar(self, name: str, section: str) -> EnvironmentVariable:
        envvar = self._db.environment_variables.get(name)
        if envvar is None:
            raise ValueError(
                f"{section} references unknown environment variable '{name}'"
            )
        return envvar

    def start(self, items: list) -> Database:
        return self._db

    # ── VERSION ──────────────────────────────────────────────────────────
    def version_section(self, items: list) -> None:
        self._db.version = _str(items[0])

    # ── NS_ ──────────────────────────────────────────────────────────────
    def ns_section(self, items: list) -> None:
        self._db.ns_values = [str(t) for t in items]

    # ── BS_ ──────────────────────────────────────────────────────────────
    def bs_section(self, items: list) -> None:
        if items:
            self._db.bit_timing = str(items[0])

    def bit_timing(self, items: list) -> str:
        return ":".join(str(i) for i in items)

    # ── BU_ ──────────────────────────────────────────────────────────────
    def bu_section(self, items: list) -> None:
        for name in items:
            s = str(name)
            if s not in self._db.nodes:
                self._db.nodes[s] = Node(name=s)

    # ── VAL_TABLE_ ───────────────────────────────────────────────────────
    def val_table_section(self, items: list) -> None:
        name = str(items[0])
        vals: dict[int, str] = {}
        for i in range(1, len(items), 2):
            vals[_int(items[i])] = _str(items[i + 1])
        self._db.value_tables[name] = ValueTable(name=name, values=vals)

    # ── BO_ messages ─────────────────────────────────────────────────────
    def message_section(self, items: list) -> None:
        arb_id, is_extended = decode_dbc_frame_id(_int(items[0]))
        name = str(items[1])
        dlc = _int(items[2])
        sender = str(items[3])
        senders = [sender] if sender != "Vector__XXX" else []
        signals: dict[str, Signal] = {}
        for item in items[4:]:
            if isinstance(item, Signal):
                signals[item.name] = item
        self._db.messages[arb_id] = Message(
            arbitration_id=arb_id,
            is_extended_frame=is_extended,
            name=name,
            length=dlc,
            senders=senders,
            signals=signals,
        )

    def signal_section(self, items: list) -> Signal:
        name = str(items[0])
        mux: str | None = None
        sig: Signal | None = None
        for item in items[1:]:
            if isinstance(item, str):
                mux = item
            elif isinstance(item, Signal):
                sig = item
        if mux is not None and mux.startswith("m") and mux.endswith("M"):
            raise NotImplementedError(
                f"Extended multiplexing indicator '{mux}' on signal '{name}' "
                "is not supported"
            )
        if sig is None:
            raise ValueError(f"No signal data for '{name}'")
        return sig.model_copy(update={"name": name, "multiplex_indicator": mux})

    def mux_indicator(self, items: list) -> str:
        return str(items[0])

    def signal_def(self, items: list) -> Signal:
        start_bit = _int(items[0])
        length = _int(items[1])
        bo_sign = str(items[2])
        byte_order = ByteOrder.little_endian if bo_sign[0] == "1" else ByteOrder.big_endian
        is_signed = bo_sign[1] == "-"
        factor = _float(items[3])
        offset = _float(items[4])
        minimum = _float(items[5])
        maximum = _float(items[6])
        unit = _str(items[7])
        receivers: list[str] = items[8] if isinstance(items[8], list) else []
        return Signal(
            name="",
            start_bit=start_bit,
            length=length,
            byte_order=byte_order,
            is_signed=is_signed,
            factor=factor,
            offset=offset,
            minimum=minimum if minimum != 0.0 or maximum != 0.0 else None,
            maximum=maximum if minimum != 0.0 or maximum != 0.0 else None,
            unit=unit,
            receivers=receivers,
        )

    def receiver_list(self, items: list) -> list[str]:
        return [r for r in (str(t) for t in items) if r != "Vector__XXX"]

    # ── BO_TX_BU_ ────────────────────────────────────────────────────────
    def message_transmitters_section(self, items: list) -> None:
        arb_id, _ = decode_dbc_frame_id(_int(items[0]))
        senders = [str(t) for t in items[1:]]
        msg = self._db.messages.get(arb_id)
        if msg is not None:
            self._db.messages[msg.arbitration_id] = msg.model_copy(
                update={"senders": senders}
            )

    # ── SIG_GROUP_ ───────────────────────────────────────────────────────
    def sig_group_section(self, items: list) -> None:
        msg_id, _ = decode_dbc_frame_id(_int(items[0]))
        name = str(items[1])
        repetitions = _int(items[2])
        signal_names = [str(t) for t in items[3:]]
        self._db.signal_groups.append(
            SignalGroup(
                name=name,
                message_id=msg_id,
                signal_names=signal_names,
                repetitions=repetitions,
            )
        )

    # ── CM_ comments ─────────────────────────────────────────────────────
    def msg_comment(self, items: list) -> None:
        arb_id, _ = decode_dbc_frame_id(_int(items[0]))
        msg = self._require_message(arb_id, "CM_")
        self._db.messages[msg.arbitration_id] = msg.model_copy(
            update={"comment": _str(items[1])}
        )

    def sig_comment(self, items: list) -> None:
        arb_id, _ = decode_dbc_frame_id(_int(items[0]))
        sig_name = str(items[1])
        msg, sig = self._require_signal(arb_id, sig_name, "CM_")
        msg.signals[sig_name] = sig.model_copy(update={"comment": _str(items[2])})

    def node_comment(self, items: list) -> None:
        name = str(items[0])
        comment = _str(items[1])
        node = self._db.nodes.get(name, Node(name=name))
        self._db.nodes[name] = node.model_copy(update={"comment": comment})

    def envvar_comment(self, items: list) -> None:
        name = str(items[0])
        envvar = self._require_envvar(name, "CM_")
        self._db.environment_variables[name] = envvar.model_copy(
            update={"comment": _str(items[1])}
        )

    def db_comment(self, items: list) -> None:
        self._db.dbc_specific["comment"] = _str(items[0])

    # ── BA_DEF_ attribute definitions ────────────────────────────────────
    def attr_def_bu(self, items: list) -> None:
        self._register_attr_def("BU_", items)

    def attr_def_bo(self, items: list) -> None:
        self._register_attr_def("BO_", items)

    def attr_def_sg(self, items: list) -> None:
        self._register_attr_def("SG_", items)

    def attr_def_ev(self, items: list) -> None:
        self._register_attr_def("EV_", items)

    def attr_def_db(self, items: list) -> None:
        self._register_attr_def("", items)

    def _register_attr_def(self, obj_type: str, items: list) -> None:
        name = _str(items[0])
        kind, lo, hi, enum_vals = items[1]
        ad = AttributeDefinition(
            name=name,
            kind=kind,
            object_type=obj_type,
            minimum=lo,
            maximum=hi,
            values=enum_vals or [],
        )
        if name == CYCLE_TIME_ATTRIBUTE:
            for arb_id, msg in self._db.messages.items():
                raw_cycle_time = msg.cycle_time
                if raw_cycle_time is None and name in msg.attributes:
                    raw_cycle_time = msg.attributes[name]
                if raw_cycle_time is None:
                    continue
                cycle_time = validate_cycle_time(raw_cycle_time, ad)
                msg.attributes[name] = cycle_time
                self._db.messages[arb_id] = msg.model_copy(
                    update={"cycle_time": cycle_time}
                )
        self._db.attributes[name] = ad

    def attr_int(self, items: list) -> tuple:
        return (AttributeKind.INT, _float(items[0]), _float(items[1]), None)

    def attr_hex(self, items: list) -> tuple:
        return (AttributeKind.HEX, _float(items[0]), _float(items[1]), None)

    def attr_float(self, items: list) -> tuple:
        return (AttributeKind.FLOAT, _float(items[0]), _float(items[1]), None)

    def attr_string(self, items: list) -> tuple:
        return (AttributeKind.STRING, None, None, None)

    def attr_enum(self, items: list) -> tuple:
        return (AttributeKind.ENUM, None, None, [_str(t) for t in items])

    # ── BA_DEF_DEF_ ──────────────────────────────────────────────────────
    def attr_def_def_num(self, items: list) -> None:
        self._apply_default(_str(items[0]), items[1])

    def attr_def_def_str(self, items: list) -> None:
        self._apply_default(_str(items[0]), items[1])

    def _apply_default(self, name: str, raw: Any) -> None:
        if name not in self._db.attributes:
            return
        ad = self._db.attributes[name]
        val = _coerce_attr(raw, ad.kind)
        self._db.attributes[name] = ad.model_copy(update={"default": val})

    # ── BA_ attribute values ─────────────────────────────────────────────
    def attr_val_node_num(self, items: list) -> None:
        self._apply_node_attr(_str(items[0]), str(items[1]), items[2])

    def attr_val_node_str(self, items: list) -> None:
        self._apply_node_attr(_str(items[0]), str(items[1]), items[2])

    def _apply_node_attr(self, name: str, node_name: str, raw: Any) -> None:
        ad = self._db.attributes.get(name)
        val = _coerce_attr(raw, ad.kind if ad else AttributeKind.STRING)
        node = self._db.nodes.get(node_name, Node(name=node_name))
        node.attributes[name] = val
        self._db.nodes[node_name] = node

    def attr_val_msg_num(self, items: list) -> None:
        self._apply_msg_attr(_str(items[0]), _int(items[1]), items[2])

    def attr_val_msg_str(self, items: list) -> None:
        self._apply_msg_attr(_str(items[0]), _int(items[1]), items[2])

    def _apply_msg_attr(self, name: str, raw_id: int, raw: Any) -> None:
        arb_id, _ = decode_dbc_frame_id(raw_id)
        msg = self._require_message(arb_id, "BA_")
        ad = self._db.attributes.get(name)
        if name == CYCLE_TIME_ATTRIBUTE:
            val = (
                coerce_cycle_time(raw)
                if ad is None
                else validate_cycle_time(raw, ad)
            )
            attributes = {**msg.attributes, name: val}
            self._db.messages[msg.arbitration_id] = msg.model_copy(
                update={"attributes": attributes, "cycle_time": val}
            )
        else:
            val = _coerce_attr(raw, ad.kind if ad else AttributeKind.STRING)
            msg.attributes[name] = val

    def attr_val_sig_num(self, items: list) -> None:
        self._apply_sig_attr(_str(items[0]), _int(items[1]), str(items[2]), items[3])

    def attr_val_sig_str(self, items: list) -> None:
        self._apply_sig_attr(_str(items[0]), _int(items[1]), str(items[2]), items[3])

    def _apply_sig_attr(self, name: str, raw_id: int, sig_name: str, raw: Any) -> None:
        arb_id, _ = decode_dbc_frame_id(raw_id)
        _, sig = self._require_signal(arb_id, sig_name, "BA_")
        ad = self._db.attributes.get(name)
        val = _coerce_attr(raw, ad.kind if ad else AttributeKind.STRING)
        sig.attributes[name] = val

    def attr_val_env_num(self, items: list) -> None:
        self._apply_env_attr(_str(items[0]), str(items[1]), items[2])

    def attr_val_env_str(self, items: list) -> None:
        self._apply_env_attr(_str(items[0]), str(items[1]), items[2])

    def _apply_env_attr(self, name: str, ev_name: str, raw: Any) -> None:
        envvar = self._require_envvar(ev_name, "BA_")
        ad = self._db.attributes.get(name)
        val = _coerce_attr(raw, ad.kind if ad else AttributeKind.STRING)
        envvar.attributes[name] = val

    def attr_val_db_num(self, items: list) -> None:
        name = _str(items[0])
        ad = self._db.attributes.get(name)
        val = _coerce_attr(items[1], ad.kind if ad else AttributeKind.FLOAT)
        self._db.attribute_values[name] = val

    def attr_val_db_str(self, items: list) -> None:
        name = _str(items[0])
        ad = self._db.attributes.get(name)
        val = _coerce_attr(items[1], ad.kind if ad else AttributeKind.STRING)
        self._db.attribute_values[name] = val

    # ── VAL_ ─────────────────────────────────────────────────────────────
    def signal_val(self, items: list) -> None:
        arb_id, _ = decode_dbc_frame_id(_int(items[0]))
        sig_name = str(items[1])
        msg, sig = self._require_signal(arb_id, sig_name, "VAL_")
        vals: dict[int, str] = {}
        for i in range(2, len(items), 2):
            vals[_int(items[i])] = _str(items[i + 1])
        vt = ValueTable(name=sig_name, values=vals)
        msg.signals[sig_name] = sig.model_copy(update={"value_table": vt})

    def table_val(self, items: list) -> None:
        name = str(items[0])
        envvar = self._require_envvar(name, "VAL_")
        vals: dict[int, str] = {}
        for i in range(1, len(items), 2):
            vals[_int(items[i])] = _str(items[i + 1])
        self._db.environment_variables[name] = envvar.model_copy(
            update={"value_table": ValueTable(name=name, values=vals)}
        )

    # ── SIG_VALTYPE_ / EV_ / ENVVAR_DATA_ ────────────────────────────────
    def sig_valtype_section(self, items: list) -> None:
        arb_id, _ = decode_dbc_frame_id(_int(items[0]))
        sig_name = str(items[1])
        sig_type = _int(items[2])
        msg, sig = self._require_signal(arb_id, sig_name, "SIG_VALTYPE_")
        msg.signals[sig_name] = sig.model_copy(update={"signal_type": sig_type})

    def envvar_section(self, items: list) -> None:
        name = str(items[0])
        ev = EnvironmentVariable(
            name=name,
            var_type=_int(items[1]),
            minimum=_float(items[2]),
            maximum=_float(items[3]),
            unit=_str(items[4]),
            initial_value=_float(items[5]),
            ev_id=_int(items[6]),
            access_type=str(items[7]),
            access_nodes=[str(t) for t in items[8:]],
        )
        self._db.environment_variables[name] = ev

    def envvar_data_section(self, items: list) -> None:
        name = str(items[0])
        size = _int(items[1])
        envvar = self._require_envvar(name, "ENVVAR_DATA_")
        self._db.environment_variables[name] = envvar.model_copy(
            update={"data_size": size}
        )


def parse_string(text: str) -> Database:
    """Parse a DBC-formatted string and return a Database model."""
    for line_number, line in enumerate(text.splitlines(), start=1):
        parts = line.lstrip().split(maxsplit=1)
        is_extended_mux_statement = (
            parts[:1] == ["SG_MUL_VAL_"]
            and len(parts) > 1
            and bool(parts[1].split("//", maxsplit=1)[0].strip())
        )
        if is_extended_mux_statement:
            raise ValueError(
                f"Unsupported DBC construct 'SG_MUL_VAL_' at line {line_number}: "
                "extended multiplexing ranges are not supported"
            )
    tree = get_parser().parse(text)
    try:
        return DBCTransformer().transform(tree)
    except VisitError as exc:
        if isinstance(exc.orig_exc, ValueError):
            raise exc.orig_exc from None
        raise
