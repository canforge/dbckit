from __future__ import annotations

from enum import Enum
from typing import TYPE_CHECKING, Any, Literal, Optional

from pydantic import BaseModel, Field

from .message import Message
from .signal import SignalGroup, ValueTable

if TYPE_CHECKING:
    from dbckit.operations.diff import DiffResult
    from dbckit.operations.merge import MergeStrategy
    from dbckit.views import MessageView, NodeView, SignalView


class AttributeKind(str, Enum):
    INT = "INT"
    HEX = "HEX"
    FLOAT = "FLOAT"
    STRING = "STRING"
    ENUM = "ENUM"


class AttributeDefinition(BaseModel):
    """BA_DEF_ entry — type, scope, and range of a named attribute."""

    name: str
    kind: AttributeKind
    object_type: str = ""  # "BU_", "BO_", "SG_", "EV_", or "" for database-level
    minimum: Optional[float] = None
    maximum: Optional[float] = None
    values: list[str] = Field(default_factory=list)  # ENUM options
    default: Any = None

    model_config = {"extra": "forbid"}


class Node(BaseModel):
    """A network node (BU_ entry)."""

    name: str
    comment: Optional[str] = None
    attributes: dict[str, Any] = Field(default_factory=dict)

    model_config = {"extra": "forbid"}


class EnvironmentVariable(BaseModel):
    """EV_ entry — parsed and stored, treated as informational."""

    name: str
    var_type: int = 0
    minimum: float = 0.0
    maximum: float = 0.0
    unit: str = ""
    initial_value: float = 0.0
    ev_id: int = 0
    access_type: str = ""
    access_nodes: list[str] = Field(default_factory=list)
    comment: Optional[str] = None
    data_size: Optional[int] = None  # from ENVVAR_DATA_
    attributes: dict[str, Any] = Field(default_factory=dict)
    value_table: Optional[ValueTable] = None

    model_config = {"extra": "forbid"}


class Issue(BaseModel):
    """A validation finding with machine-readable code and structured location."""

    severity: Literal["error", "warning"]
    code: str
    location: str  # e.g. "message:0x1F4", "signal:0x1F4:EngineSpeed", "node:ECU1"
    message: str


class Database(BaseModel):
    """Top-level DBC database."""

    version: str = ""
    filename: Optional[str] = None
    nodes: dict[str, Node] = Field(default_factory=dict)
    messages: dict[int, Message] = Field(default_factory=dict)
    # BA_DEF_ definitions
    attributes: dict[str, AttributeDefinition] = Field(default_factory=dict)
    # BA_ values at the database level
    attribute_values: dict[str, Any] = Field(default_factory=dict)
    value_tables: dict[str, ValueTable] = Field(default_factory=dict)
    signal_groups: list[SignalGroup] = Field(default_factory=list)
    environment_variables: dict[str, EnvironmentVariable] = Field(default_factory=dict)
    ns_values: list[str] = Field(default_factory=list)
    bit_timing: Optional[str] = None
    # Catch-all for non-standard / future sections
    dbc_specific: dict[str, Any] = Field(default_factory=dict)

    model_config = {"extra": "forbid"}

    # ── navigation ────────────────────────────────────────────────────────────

    def message(self, arbitration_id: int) -> MessageView:
        """Return a :class:`~dbckit.views.MessageView` for *arbitration_id*.

        Raises :exc:`KeyError` if the ID is not present.
        """
        if arbitration_id not in self.messages:
            raise KeyError(f"No message with arbitration_id={arbitration_id:#x}")
        from dbckit.views import MessageView  # noqa: PLC0415
        return MessageView(self, arbitration_id)

    def node(self, name: str) -> NodeView:
        """Return a :class:`~dbckit.views.NodeView` for *name*.

        Raises :exc:`KeyError` if the node does not exist.
        """
        if name not in self.nodes:
            raise KeyError(f"No node '{name}'")
        from dbckit.views import NodeView  # noqa: PLC0415
        return NodeView(self, name)

    def list_messages(self) -> list[MessageView]:
        """Return all messages as an ordered list of :class:`~dbckit.views.MessageView`."""
        from dbckit.views import MessageView  # noqa: PLC0415
        return [MessageView(self, aid) for aid in self.messages]

    def list_nodes(self) -> list[NodeView]:
        """Return all nodes as an ordered list of :class:`~dbckit.views.NodeView`."""
        from dbckit.views import NodeView  # noqa: PLC0415
        return [NodeView(self, n) for n in self.nodes]

    def message_by_pgn(self, pgn: int) -> MessageView:
        """Return the unique :class:`~dbckit.views.MessageView` with attribute `PGN == pgn`."""
        from dbckit.operations.j1939 import get_message_by_pgn  # noqa: PLC0415
        return get_message_by_pgn(self, pgn)

    def signal_by_spn(self, spn: int) -> tuple[MessageView, SignalView]:
        """Return the unique `(MessageView, SignalView)` pair with attribute `SPN == spn`."""
        from dbckit.operations.j1939 import get_signal_by_spn  # noqa: PLC0415
        return get_signal_by_spn(self, spn)

    # ── add mutations (no existing entity to root from) ───────────────────────

    def add_message(self, msg: Message) -> Database:
        """Return a new :class:`Database` with *msg* added."""
        from dbckit.mutations.message import add_message  # noqa: PLC0415
        return add_message(self, msg)

    def add_node(self, nd: Node) -> Database:
        """Return a new :class:`Database` with *nd* added."""
        from dbckit.mutations.node import add_node  # noqa: PLC0415
        return add_node(self, nd)

    def define_attribute(self, ad: AttributeDefinition) -> Database:
        """Return a new :class:`Database` with the attribute definition registered."""
        from dbckit.mutations.attribute import define_attribute  # noqa: PLC0415
        return define_attribute(self, ad)

    def delete_attribute(self, name: str) -> Database:
        """Return a new :class:`Database` with the attribute definition and all its values removed."""
        from dbckit.mutations.attribute import delete_attribute  # noqa: PLC0415
        return delete_attribute(self, name)

    def add_signal_group(self, group: SignalGroup) -> Database:
        """Return a new :class:`Database` with *group* added."""
        from dbckit.mutations.signal_group import add_signal_group  # noqa: PLC0415
        return add_signal_group(self, group)

    def remove_signal_group(self, message_id: int, name: str) -> Database:
        """Return a new database without the named signal group."""
        from dbckit.mutations.signal_group import remove_signal_group  # noqa: PLC0415
        return remove_signal_group(self, message_id, name)

    def add_signal_to_group(
        self, message_id: int, group_name: str, signal_name: str
    ) -> Database:
        """Return a new database with a signal added to a signal group."""
        from dbckit.mutations.signal_group import add_signal_to_group  # noqa: PLC0415
        return add_signal_to_group(self, message_id, group_name, signal_name)

    def remove_signal_from_group(
        self, message_id: int, group_name: str, signal_name: str
    ) -> Database:
        """Return a new database with a signal removed from a signal group."""
        from dbckit.mutations.signal_group import remove_signal_from_group  # noqa: PLC0415
        return remove_signal_from_group(self, message_id, group_name, signal_name)

    # ── cross-database operations ─────────────────────────────────────────────

    def validate(self, strict: bool = False) -> list[Issue]:  # type: ignore[override]
        """Run the validator and return a list of :class:`Issue` objects."""
        from dbckit.validator import validate as _validate  # noqa: PLC0415
        return _validate(self, strict=strict)

    def diff(self, other: Database) -> DiffResult:
        """Return a :class:`~dbckit.operations.diff.DiffResult` comparing *self* to *other*."""
        from dbckit.operations.diff import diff as _diff  # noqa: PLC0415
        return _diff(self, other)

    def merge(self, other: Database, strategy: MergeStrategy = "raise") -> Database:
        """Merge *other* into *self* and return the result."""
        from dbckit.operations.merge import merge as _merge  # noqa: PLC0415
        return _merge(self, other, strategy=strategy)

    def extract(
        self,
        message_ids: list[int] | None = None,
        *,
        message_names: list[str] | None = None,
        node_names: list[str] | None = None,
    ) -> Database:
        """Return a new database selected by message IDs, names, or node names."""
        from dbckit.operations.extract import extract as _extract  # noqa: PLC0415
        return _extract(
            self,
            message_ids,
            message_names=message_names,
            node_names=node_names,
        )

    # ── persistence ───────────────────────────────────────────────────────────

    def dump(self) -> str:
        """Serialise this database back to DBC format."""
        from dbckit.serializer import dump as _dump  # noqa: PLC0415
        return _dump(self)

    def save(self, path: Any, *, encoding: str = "utf-8") -> None:
        """Write this database to *path* in DBC format."""
        from pathlib import Path as _Path  # noqa: PLC0415

        from dbckit.io import save as _save  # noqa: PLC0415
        _save(self, _Path(path), encoding=encoding)
