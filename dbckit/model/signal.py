from __future__ import annotations

from enum import Enum
from typing import Any, Optional

from pydantic import BaseModel, Field


class ByteOrder(str, Enum):
    little_endian = "little_endian"  # Intel
    big_endian = "big_endian"        # Motorola


class ValueTable(BaseModel):
    """Named set of integer → label mappings (VAL_TABLE_ or VAL_)."""

    name: str
    values: dict[int, str] = Field(default_factory=dict)

    model_config = {"extra": "forbid"}

    # ── typed accessors ───────────────────────────────────────────────────────

    def get(self, val: int) -> str | None:
        """Return the label for *val*, or ``None`` if not present."""
        return self.values.get(val)

    def has(self, val: int) -> bool:
        """Return ``True`` if *val* has a label entry."""
        return val in self.values

    def labels(self) -> dict[int, str]:
        """Return a copy of the integer → label mapping."""
        return dict(self.values)


class BitSlot(BaseModel):
    """One cell in a signal layout bit grid."""

    bit: int
    signal_name: Optional[str] = None
    is_msb: bool = False
    is_lsb: bool = False
    byte_order: Optional[ByteOrder] = None


class Signal(BaseModel):
    """A single signal within a CAN message."""

    name: str
    start_bit: int
    length: int
    byte_order: ByteOrder = ByteOrder.little_endian
    is_signed: bool = False
    factor: float = 1.0
    offset: float = 0.0
    minimum: Optional[float] = None
    maximum: Optional[float] = None
    unit: str = ""
    receivers: list[str] = Field(default_factory=list)
    comment: Optional[str] = None
    value_table: Optional[ValueTable] = None
    attributes: dict[str, Any] = Field(default_factory=dict)
    multiplex_indicator: Optional[str] = None  # "M", "m0", "m1", etc.
    signal_type: Optional[int] = None  # SIG_VALTYPE_: 1=float, 2=double

    model_config = {"extra": "forbid"}

    # ── typed helpers ─────────────────────────────────────────────────────────

    def decode(self, data: bytes) -> float:
        """Decode this signal from *data* and return the physical value.

        Applies ``factor`` and ``offset``.  For the resolved label (string)
        when a ``value_table`` is present, use :meth:`decode_phys`.
        """
        from dbckit.codec.decoder import decode_signal  # noqa: PLC0415
        return decode_signal(data, self)

    def decode_phys(self, data: bytes) -> float | str:
        """Decode and resolve value-table labels.

        Returns the string label if ``value_table`` has an entry for the raw
        integer, otherwise the float physical value.
        """
        phys = self.decode(data)
        if self.value_table:
            raw_int = int(round((phys - self.offset) / self.factor))
            label = self.value_table.values.get(raw_int)
            if label is not None:
                return label
        return phys

    def choices(self) -> dict[int, str] | None:
        """Return a copy of the value-table mapping, or ``None``."""
        if self.value_table is None:
            return None
        return dict(self.value_table.values)

    def choice(self, val: int) -> str | None:
        """Return the label for integer *val*, or ``None``."""
        if self.value_table is None:
            return None
        return self.value_table.values.get(val)


class SignalGroup(BaseModel):
    """A named group of signals within a message."""

    name: str
    message_id: int
    signal_names: list[str] = Field(default_factory=list)
    repetitions: int = 1

    model_config = {"extra": "forbid"}
