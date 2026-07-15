"""dbckit — parse, inspect, encode, decode, and transform DBC (CAN database) files."""
from __future__ import annotations

# ── codec ─────────────────────────────────────────────────────────────────────
from dbckit.codec import decode_frame, decode_signal, encode_frame, encode_signal

# ── io ────────────────────────────────────────────────────────────────────────
from dbckit.io import load, save

# ── models ────────────────────────────────────────────────────────────────────
from dbckit.model.database import (
    AttributeDefinition,
    AttributeKind,
    Database,
    Issue,
    Node,
)
from dbckit.model.message import Message
from dbckit.model.signal import BitSlot, ByteOrder, Signal, SignalGroup, ValueTable

# ── operations ────────────────────────────────────────────────────────────────
from dbckit.operations import (
    AscReader,
    CodegenTarget,
    DecodedFrame,
    DiffResult,
    FrameLike,
    MergeStrategy,
    MessageDiff,
    RawFrame,
    SignalDiff,
    codegen,
    decode_frames,
    decode_log,
    diff,
    extract,
    find_messages_by_pgn,
    find_signals_by_spn,
    merge,
    register_reader,
    search_messages,
    search_signals,
)
from dbckit.parser.grammar import parse_string
from dbckit.parser.tokenizer import normalize
from dbckit.serializer import dump
from dbckit.validator import validate

# ── views ─────────────────────────────────────────────────────────────────────
from dbckit.views import MessageView, NodeView, SignalView

__all__ = [
    # models
    "Database", "Message", "Signal", "SignalGroup", "Node",
    "ByteOrder", "ValueTable", "BitSlot",
    "AttributeDefinition", "AttributeKind", "Issue",
    # views
    "MessageView", "SignalView", "NodeView",
    # parse / io
    "parse", "load", "dump", "save",
    # validate
    "validate",
    # codec
    "decode_frame", "encode_frame", "decode_signal", "encode_signal",
    # operations
    "diff", "DiffResult", "MessageDiff", "SignalDiff",
    "merge", "MergeStrategy",
    "extract",
    "search_messages", "search_signals",
    "find_messages_by_pgn", "find_signals_by_spn",
    "codegen", "CodegenTarget",
    "decode_frames", "decode_log", "DecodedFrame", "FrameLike", "RawFrame",
    "AscReader", "register_reader",
]


def parse(text: str) -> Database:
    """Parse a DBC-formatted string and return a Database model."""
    return parse_string(normalize(text))
