"""Pre-processing pass to normalize DBC text before Lark parsing."""
from __future__ import annotations


def normalize(text: str) -> str:
    """Normalize raw DBC text: CRLF → LF, tabs → spaces, strip BOM."""
    # Strip BOM if present
    text = text.lstrip("\ufeff")
    # Normalize Windows line endings
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    # Replace tabs with spaces
    text = text.replace("\t", " ")
    # Ensure file ends with newline
    if not text.endswith("\n"):
        text += "\n"
    return text
