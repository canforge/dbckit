"""Source-aware isolation of bounded unsupported DBC constructs."""
from __future__ import annotations

import re
from typing import Literal

from dbckit._frame_id import decode_dbc_frame_id
from dbckit.model.database import ParseDiagnostic

UnsupportedPolicy = Literal["raise", "skip"]

_CNAME = r"[A-Za-z_][A-Za-z0-9_]*"
_NUMBER = r"[-+]?[0-9]*\.?[0-9]+(?:[eE][-+]?[0-9]+)?"
_MESSAGE_RE = re.compile(rf"^\s*BO_\s+(?P<id>[0-9]+)\s+{_CNAME}\s*:")
_EXTENDED_MUX_SIGNAL_RE = re.compile(
    rf"^\s*SG_\s+(?P<signal>{_CNAME})\s+(?P<mux>m[0-9]+M)\s*:\s*"
    rf"[0-9]+\s*\|\s*[0-9]+\s*@\s*[01][+-]\s*"
    rf"\(\s*{_NUMBER}\s*,\s*{_NUMBER}\s*\)\s*"
    rf"\[\s*{_NUMBER}\s*\|\s*{_NUMBER}\s*\]\s*"
    rf'"[^"]*"\s+{_CNAME}(?:\s*,\s*{_CNAME})*\s*(?://[^\n]*)?$'
)
_EXTENDED_MUX_RANGE_RE = re.compile(
    rf"^\s*SG_MUL_VAL_\s+(?P<id>[0-9]+)\s+"
    rf"(?P<signal>{_CNAME})\s+{_CNAME}\s+[^;\n]+;\s*(?://[^\n]*)?$"
)


def validate_unsupported_policy(on_unsupported: str) -> UnsupportedPolicy:
    """Validate and narrow the public unsupported-construct policy."""
    if on_unsupported not in {"raise", "skip"}:
        raise ValueError("on_unsupported must be 'raise' or 'skip'")
    return on_unsupported  # type: ignore[return-value]


def preprocess_unsupported(
    text: str,
    *,
    on_unsupported: UnsupportedPolicy,
) -> tuple[str, list[ParseDiagnostic]]:
    """Blank safely bounded unsupported lines and retain their source positions."""
    diagnostics: list[ParseDiagnostic] = []
    output: list[str] = []
    current_message_id: int | None = None

    for line_number, line in enumerate(text.splitlines(keepends=True), start=1):
        content = line.rstrip("\r\n")
        stripped = content.lstrip()
        parts = stripped.split(maxsplit=1)
        is_extended_mux_statement = (
            parts[:1] == ["SG_MUL_VAL_"]
            and len(parts) > 1
            and bool(parts[1].split("//", maxsplit=1)[0].strip())
        )
        if is_extended_mux_statement:
            error = (
                f"Unsupported DBC construct 'SG_MUL_VAL_' at line {line_number}: "
                "extended multiplexing ranges are not supported"
            )
            if on_unsupported == "raise":
                raise ValueError(error)
            match = _EXTENDED_MUX_RANGE_RE.fullmatch(content)
            if match is None:
                raise ValueError(error)
            message_id, _ = decode_dbc_frame_id(int(match.group("id")))
            signal_name = match.group("signal")
            diagnostics.append(
                ParseDiagnostic(
                    construct="SG_MUL_VAL_",
                    line=line_number,
                    message_id=message_id,
                    signal_name=signal_name,
                    effect="decode_degraded",
                    detail=(
                        "Skipped unsupported extended multiplexing ranges for "
                        f"signal '{signal_name}' in message arbitration_id={message_id:#x}"
                    ),
                )
            )
            output.append(_blank_line(line))
            current_message_id = None
            continue

        message_match = _MESSAGE_RE.match(content)
        if message_match is not None:
            current_message_id, _ = decode_dbc_frame_id(
                int(message_match.group("id"))
            )
            output.append(line)
            continue

        extended_signal_match = _EXTENDED_MUX_SIGNAL_RE.fullmatch(content)
        if extended_signal_match is not None and current_message_id is not None:
            if on_unsupported == "skip":
                signal_name = extended_signal_match.group("signal")
                mux = extended_signal_match.group("mux")
                diagnostics.append(
                    ParseDiagnostic(
                        construct="SG_",
                        line=line_number,
                        message_id=current_message_id,
                        signal_name=signal_name,
                        effect="decode_degraded",
                        detail=(
                            f"Skipped signal '{signal_name}' with unsupported extended "
                            f"multiplexing indicator '{mux}'"
                        ),
                    )
                )
                output.append(_blank_line(line))
                continue

        if stripped and not stripped.startswith(("SG_", "//", "/*", "*")):
            current_message_id = None
        output.append(line)

    return "".join(output), diagnostics


def _blank_line(line: str) -> str:
    """Remove line content without changing the source line count."""
    if line.endswith("\r\n"):
        return "\r\n"
    if line.endswith(("\n", "\r")):
        return line[-1]
    return ""
