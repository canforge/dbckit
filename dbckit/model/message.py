from __future__ import annotations

from typing import Any, Optional

from pydantic import BaseModel, Field, model_validator

from dbckit._cycle_time import CYCLE_TIME_ATTRIBUTE, coerce_cycle_time

from .signal import Signal


class Message(BaseModel):
    """A CAN message (BO_ block) containing signals."""

    arbitration_id: int
    name: str
    length: int  # DLC in bytes
    is_extended_frame: bool = False
    senders: list[str] = Field(default_factory=list)
    signals: dict[str, Signal] = Field(default_factory=dict)
    comment: Optional[str] = None
    attributes: dict[str, Any] = Field(default_factory=dict)
    cycle_time: Optional[int] = None

    model_config = {"extra": "forbid"}

    @model_validator(mode="before")
    @classmethod
    def _synchronise_cycle_time(cls, data: Any) -> Any:
        """Keep the convenience field and DBC attribute representation aligned."""
        if not isinstance(data, dict):
            return data
        values = dict(data)
        attributes = dict(values.get("attributes") or {})
        if "cycle_time" in values:
            raw_cycle_time = values["cycle_time"]
            if raw_cycle_time is None:
                attributes.pop(CYCLE_TIME_ATTRIBUTE, None)
            else:
                cycle_time = coerce_cycle_time(raw_cycle_time)
                values["cycle_time"] = cycle_time
                attributes[CYCLE_TIME_ATTRIBUTE] = cycle_time
        elif CYCLE_TIME_ATTRIBUTE in attributes:
            cycle_time = coerce_cycle_time(attributes[CYCLE_TIME_ATTRIBUTE])
            values["cycle_time"] = cycle_time
            attributes[CYCLE_TIME_ATTRIBUTE] = cycle_time
        values["attributes"] = attributes
        return values

    # ── typed accessors ───────────────────────────────────────────────────────

    def signal(self, name: str) -> Signal:
        """Return the :class:`Signal` named *name*.

        Raises :exc:`KeyError` if the signal does not exist.
        """
        try:
            return self.signals[name]
        except KeyError:
            raise KeyError(f"No signal '{name}' in message '{self.name}'") from None

    def list_signals(self) -> list[Signal]:
        """Return all signals as an ordered list."""
        return list(self.signals.values())

    def layout(self) -> list[Any]:
        """Return the bit-slot layout for this message.

        Each slot is a :class:`~dbckit.model.signal.BitSlot` instance.
        Delegates to :func:`dbckit.mutations.signal.signal_layout`.
        """
        from dbckit.mutations.signal import signal_layout  # noqa: PLC0415
        return signal_layout(self)
