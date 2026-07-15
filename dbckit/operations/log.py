"""Decode CAN log files into structured frames."""
from __future__ import annotations

import re
from collections.abc import Iterable, Iterator
from importlib import metadata
from pathlib import Path
from typing import Protocol

from pydantic import BaseModel

from dbckit.codec.frame import decode_frame
from dbckit.model.database import Database


class FrameLike(Protocol):
    """Minimal structural contract accepted by :func:`decode_frames`."""

    timestamp: float
    arbitration_id: int
    data: bytes


class RawFrame(BaseModel):
    """A single raw CAN frame read from a log file."""

    timestamp: float
    arbitration_id: int
    data: bytes
    channel: int | None = None
    is_extended_frame: bool = False


class DecodedFrame(BaseModel):
    """A decoded CAN frame with per-signal physical values."""

    timestamp: float
    arbitration_id: int
    raw: bytes
    signals: dict[str, float | int | str]
    channel: int | None = None
    is_extended_frame: bool = False

    model_config = {"arbitrary_types_allowed": True}


class LogReader(Protocol):
    def read(self, path: Path) -> Iterator[FrameLike]: ...


class AscReader:
    """Reader for Vector CANalyzer .asc log files."""

    # Example line (spaces vary):
    #    0.123456 1  0A1  Rx   d 8 01 02 03 04 05 06 07 08
    _FRAME_RE = re.compile(
        r"^\s*"
        r"(?P<ts>[0-9]+\.[0-9]+)"        # timestamp
        r"\s+(?P<channel>\d+)"              # channel
        r"\s+(?P<id>[0-9A-Fa-f]+)(?P<extended>[xX])?"  # CAN ID
        r"\s+(?:Rx|Tx)"                    # direction
        r"\s+d"                            # data frame flag
        r"\s+\d+"                          # DLC
        r"(?P<bytes>(?:\s+[0-9A-Fa-f]{2})+)"  # data bytes
    )

    def read(self, path: Path) -> Iterator[RawFrame]:
        with open(path, encoding="utf-8", errors="replace") as fh:
            for line in fh:
                m = self._FRAME_RE.match(line)
                if not m:
                    continue
                timestamp = float(m.group("ts"))
                channel = int(m.group("channel"))
                arb_id = int(m.group("id"), 16)
                data = bytes.fromhex(m.group("bytes").replace(" ", ""))
                yield RawFrame(
                    timestamp=timestamp,
                    arbitration_id=arb_id,
                    data=data,
                    channel=channel,
                    is_extended_frame=m.group("extended") is not None,
                )


_BUILTIN_READERS: dict[str, LogReader] = {
    ".asc": AscReader(),
}
_REGISTERED_READERS: dict[str, LogReader] = {}
_ENTRY_POINTS: dict[str, list[metadata.EntryPoint]] | None = None
_ENTRY_POINT_READERS: dict[str, LogReader] = {}


def _normalize_extension(extension: str) -> str:
    normalized = extension.strip().lower()
    if not normalized:
        raise ValueError("Reader extension must not be empty.")
    if not normalized.startswith("."):
        normalized = f".{normalized}"
    return normalized


def register_reader(extension: str, reader: LogReader) -> None:
    """Register a custom log reader for a file extension.

    The extension is case-insensitive and may be supplied with or without a
    leading dot. Registration is process-global and replaces an existing
    reader for the normalized extension.
    """
    _REGISTERED_READERS[_normalize_extension(extension)] = reader


def _discover_entry_points() -> dict[str, list[metadata.EntryPoint]]:
    global _ENTRY_POINTS
    if _ENTRY_POINTS is None:
        discovered: dict[str, list[metadata.EntryPoint]] = {}
        for entry_point in metadata.entry_points(group="dbckit.readers"):
            extension = _normalize_extension(entry_point.name)
            discovered.setdefault(extension, []).append(entry_point)
        _ENTRY_POINTS = discovered
    return _ENTRY_POINTS


def _load_entry_point_reader(
    extension: str,
    candidates: list[metadata.EntryPoint],
) -> LogReader:
    cached = _ENTRY_POINT_READERS.get(extension)
    if cached is not None:
        return cached

    if len(candidates) > 1:
        values = ", ".join(sorted(entry_point.value for entry_point in candidates))
        raise ValueError(
            f"Multiple dbckit.readers entry points are registered for "
            f"'{extension}': {values}"
        )

    entry_point = candidates[0]
    try:
        factory = entry_point.load()
        if not callable(factory):
            raise TypeError("entry point value is not callable")
        reader = factory()
        if not callable(getattr(reader, "read", None)):
            raise TypeError("reader factory did not return an object with read(path)")
    except Exception as exc:
        raise RuntimeError(
            f"Failed to load dbckit reader for '{extension}' from entry point "
            f"'{entry_point.value}': {exc}"
        ) from exc

    _ENTRY_POINT_READERS[extension] = reader
    return reader


def _available_extensions(
    entry_points: dict[str, list[metadata.EntryPoint]],
) -> list[str]:
    return sorted(
        set(_BUILTIN_READERS) | set(_REGISTERED_READERS) | set(entry_points)
    )


def _reader_for(extension: str) -> LogReader:
    entry_points = _discover_entry_points()

    registered = _REGISTERED_READERS.get(extension)
    if registered is not None:
        return registered

    candidates = entry_points.get(extension)
    if candidates:
        return _load_entry_point_reader(extension, candidates)

    builtin = _BUILTIN_READERS.get(extension)
    if builtin is not None:
        return builtin

    available = ", ".join(_available_extensions(entry_points)) or "(none)"
    label = extension or "<no extension>"
    raise ValueError(
        f"Unknown log format '{label}'. Registered extensions: {available}"
    )


def decode_frames(
    db: Database,
    frames: Iterable[FrameLike],
) -> Iterator[DecodedFrame]:
    """Decode an iterable of structurally compatible CAN frames."""
    for frame in frames:
        if frame.arbitration_id not in db.messages:
            continue
        yield DecodedFrame(
            timestamp=frame.timestamp,
            arbitration_id=frame.arbitration_id,
            raw=frame.data,
            signals=decode_frame(db, frame.arbitration_id, frame.data),
            channel=getattr(frame, "channel", None),
            is_extended_frame=getattr(frame, "is_extended_frame", False),
        )


def decode_log(
    db: Database,
    path: str | Path,
    *,
    format: str | None = None,
) -> Iterator[DecodedFrame]:
    """Decode frames from *path* using an explicit or extension-based format."""
    p = Path(path)
    if format is not None:
        extension = _normalize_extension(format)
    elif p.suffix:
        extension = _normalize_extension(p.suffix)
    else:
        extension = ""
    reader = _reader_for(extension)
    return decode_frames(db, reader.read(p))


__all__ = [
    "AscReader",
    "DecodedFrame",
    "FrameLike",
    "LogReader",
    "RawFrame",
    "decode_frames",
    "decode_log",
    "register_reader",
]
