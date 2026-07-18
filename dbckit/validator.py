"""Validate a Database model and return a list of Issues."""
from __future__ import annotations

from dbckit.model.database import AttributeKind, Database, Issue
from dbckit.model.signal import ByteOrder, Signal


def validate(db: Database, strict: bool = False) -> list[Issue]:
    """Return all Issues found in *db*. If *strict*, warnings become errors."""
    issues: list[Issue] = []
    issues.extend(_check_messages(db))
    issues.extend(_check_signal_groups(db))
    issues.extend(_check_attributes(db))
    if strict:
        for i, iss in enumerate(issues):
            if iss.severity == "warning":
                issues[i] = iss.model_copy(update={"severity": "error"})
    return issues


# ── helpers ───────────────────────────────────────────────────────────────────

def _loc_msg(arb_id: int) -> str:
    return f"message:{arb_id:#x}"


def _loc_sig(arb_id: int, sig_name: str) -> str:
    return f"signal:{arb_id:#x}:{sig_name}"


def _loc_node(name: str) -> str:
    return f"node:{name}"


def _loc_attr(name: str) -> str:
    return f"attribute:{name}"


def _loc_signal_group(message_id: int, name: str) -> str:
    return f"signal-group:{message_id:#x}:{name}"


def _mux_index(indicator: str | None) -> int | None:
    if indicator and indicator.startswith("m") and indicator[1:].isdigit():
        return int(indicator[1:])
    return None


# ── message / signal checks ───────────────────────────────────────────────────

def _check_messages(db: Database) -> list[Issue]:
    issues: list[Issue] = []
    seen_ids: set[int] = set()

    for msg in db.messages.values():
        # DUPLICATE_ID
        if msg.arbitration_id in seen_ids:
            issues.append(Issue(
                severity="error",
                code="DUPLICATE_ID",
                location=_loc_msg(msg.arbitration_id),
                message=f"Duplicate arbitration_id {msg.arbitration_id:#x}.",
            ))
        seen_ids.add(msg.arbitration_id)

        # INVALID_ID
        max_id = 0x1FFFFFFF if msg.is_extended_frame else 0x7FF
        if not (0 <= msg.arbitration_id <= max_id):
            issues.append(Issue(
                severity="error",
                code="INVALID_ID",
                location=_loc_msg(msg.arbitration_id),
                message=(
                    f"Arbitration ID {msg.arbitration_id:#x} is out of range for a "
                    f"{'29-bit extended' if msg.is_extended_frame else '11-bit standard'} "
                    f"frame (max {max_id:#x})."
                ),
            ))

        # MISSING_SENDER
        for sender in msg.senders:
            if sender and sender not in db.nodes:
                issues.append(Issue(
                    severity="warning",
                    code="MISSING_SENDER",
                    location=_loc_msg(msg.arbitration_id),
                    message=f"Sender '{sender}' not in node list.",
                ))

        msg_bits = msg.length * 8
        bit_usage: dict[int, str] = {}
        seen_sig_names: set[str] = set()
        mux_signals = [s for s in msg.signals.values() if s.multiplex_indicator == "M"]

        if len(mux_signals) > 1:
            issues.append(Issue(
                severity="error",
                code="MUX_INVALID",
                location=_loc_msg(msg.arbitration_id),
                message=f"Message has {len(mux_signals)} multiplexer signals; only 1 allowed.",
            ))

        for sig in msg.signals.values():
            # DUPLICATE_SIGNAL
            if sig.name in seen_sig_names:
                issues.append(Issue(
                    severity="error",
                    code="DUPLICATE_SIGNAL",
                    location=_loc_sig(msg.arbitration_id, sig.name),
                    message=f"Duplicate signal name '{sig.name}'.",
                ))
            seen_sig_names.add(sig.name)

            # MISSING_RECEIVER
            for rx in sig.receivers:
                if rx and rx not in db.nodes:
                    issues.append(Issue(
                        severity="warning",
                        code="MISSING_RECEIVER",
                        location=_loc_sig(msg.arbitration_id, sig.name),
                        message=f"Receiver '{rx}' not in node list.",
                    ))

            issues.extend(_check_signal(sig, msg.arbitration_id, msg.name, msg_bits, bit_usage))

        mux_variants = [
            (sig, selector)
            for sig in msg.signals.values()
            if (selector := _mux_index(sig.multiplex_indicator)) is not None
        ]
        mux_signal = mux_signals[0] if len(mux_signals) == 1 else None
        variant_usage: dict[int, dict[int, str]] = {}

        for sig, selector in mux_variants:
            loc = _loc_sig(msg.arbitration_id, sig.name)
            if mux_signal is None:
                issues.append(Issue(
                    severity="error",
                    code="MUX_MISSING_SELECTOR",
                    location=loc,
                    message=(
                        f"Signal '{sig.name}' selects m{selector}, but message "
                        "does not contain exactly one multiplexer signal (M)."
                    ),
                ))
            elif mux_signal.length > 0:
                max_selector = (
                    (1 << (mux_signal.length - 1)) - 1
                    if mux_signal.is_signed
                    else (1 << mux_signal.length) - 1
                )
                if selector > max_selector:
                    issues.append(Issue(
                        severity="error",
                        code="MUX_SELECTOR_OUT_OF_RANGE",
                        location=loc,
                        message=(
                            f"Signal '{sig.name}' selects m{selector}, outside the "
                            f"representable range of multiplexer '{mux_signal.name}' "
                            f"({max_selector} max)."
                        ),
                    ))

            usage = variant_usage.setdefault(selector, dict(bit_usage))
            for bit in _signal_bit_positions(sig):
                existing = usage.get(bit)
                if existing is not None and existing != sig.name:
                    issues.append(Issue(
                        severity="error",
                        code="MUX_OVERLAP",
                        location=loc,
                        message=(
                            f"Signal '{sig.name}' overlaps '{existing}' at bit {bit} "
                            f"for selector m{selector} in '{msg.name}'."
                        ),
                    ))
                else:
                    usage[bit] = sig.name

    return issues


# ── signal-group checks ──────────────────────────────────────────────────────

def _check_signal_groups(db: Database) -> list[Issue]:
    issues: list[Issue] = []

    for group in db.signal_groups:
        loc = _loc_signal_group(group.message_id, group.name)
        msg = db.messages.get(group.message_id)
        if msg is None:
            issues.append(Issue(
                severity="error",
                code="SIGNAL_GROUP_MISSING_MESSAGE",
                location=loc,
                message=(
                    f"Signal group '{group.name}' references missing message "
                    f"{group.message_id:#x}."
                ),
            ))
            continue

        for signal_name in group.signal_names:
            if signal_name not in msg.signals:
                issues.append(Issue(
                    severity="error",
                    code="SIGNAL_GROUP_MISSING_SIGNAL",
                    location=loc,
                    message=(
                        f"Signal group '{group.name}' references missing signal "
                        f"'{signal_name}' in message '{msg.name}'."
                    ),
                ))

    return issues


def _signal_bit_positions(sig: Signal) -> list[int]:
    bits: list[int] = []
    if sig.byte_order == ByteOrder.little_endian:
        for i in range(sig.length):
            bits.append(sig.start_bit + i)
    else:
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


def _check_signal(
    sig: Signal,
    arb_id: int,
    msg_name: str,
    msg_bits: int,
    bit_usage: dict[int, str],
) -> list[Issue]:
    issues: list[Issue] = []
    loc = _loc_sig(arb_id, sig.name)

    if sig.length <= 0:
        issues.append(Issue(
            severity="error",
            code="SIGNAL_EXCEEDS_LENGTH",
            location=loc,
            message=f"Signal '{sig.name}' has length ≤ 0.",
        ))
        return issues

    bit_positions = _signal_bit_positions(sig)
    max_bit = max(bit_positions) if bit_positions else 0

    if max_bit >= msg_bits:
        issues.append(Issue(
            severity="error",
            code="SIGNAL_EXCEEDS_LENGTH",
            location=loc,
            message=(
                f"Signal '{sig.name}' in '{msg_name}' uses bit {max_bit}, "
                f"exceeding message length ({msg_bits} bits)."
            ),
        ))

    # Only check overlap for non-multiplexed / multiplexer signals
    if sig.multiplex_indicator and sig.multiplex_indicator != "M":
        return issues

    for bit in bit_positions:
        if bit in bit_usage:
            existing = bit_usage[bit]
            if existing != sig.name:
                issues.append(Issue(
                    severity="error",
                    code="SIGNAL_OVERLAP",
                    location=loc,
                    message=(
                        f"Signal '{sig.name}' overlaps '{existing}' at bit {bit} "
                        f"in '{msg_name}'."
                    ),
                ))
        else:
            bit_usage[bit] = sig.name

    return issues


# ── attribute checks ──────────────────────────────────────────────────────────

def _check_attributes(db: Database) -> list[Issue]:
    issues: list[Issue] = []

    def _check_val(name: str, value, loc: str) -> None:
        ad = db.attributes.get(name)
        if ad is None:
            issues.append(Issue(
                severity="warning",
                code="ATTR_UNDEFINED",
                location=loc,
                message=f"Attribute '{name}' has no definition (BA_DEF_).",
            ))
            return
        if ad.kind in (AttributeKind.INT, AttributeKind.HEX, AttributeKind.FLOAT):
            if ad.minimum is not None and ad.maximum is not None:
                try:
                    v = float(value)
                    if v < ad.minimum or v > ad.maximum:
                        issues.append(Issue(
                            severity="warning",
                            code="ATTR_OUT_OF_RANGE",
                            location=loc,
                            message=(
                                f"Attribute '{name}' value {v} outside "
                                f"[{ad.minimum}, {ad.maximum}]."
                            ),
                        ))
                except (TypeError, ValueError):
                    pass
        if ad.kind == AttributeKind.ENUM and ad.values:
            if str(value) not in ad.values:
                issues.append(Issue(
                    severity="warning",
                    code="ATTR_OUT_OF_RANGE",
                    location=loc,
                    message=f"Attribute '{name}' value '{value}' not in enum {ad.values}.",
                ))

    for name, val in db.attribute_values.items():
        _check_val(name, val, _loc_attr(name))

    for msg in db.messages.values():
        for name, val in msg.attributes.items():
            _check_val(name, val, _loc_msg(msg.arbitration_id))
        for sig in msg.signals.values():
            for name, val in sig.attributes.items():
                _check_val(name, val, _loc_sig(msg.arbitration_id, sig.name))

    return issues
