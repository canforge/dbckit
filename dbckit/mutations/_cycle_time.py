"""Cycle-time helpers shared by pure mutation modules."""
from __future__ import annotations

from dbckit._cycle_time import (
    AUTO_CYCLE_TIME_DEFAULT,
    AUTO_CYCLE_TIME_MAXIMUM,
    AUTO_CYCLE_TIME_MINIMUM,
    CYCLE_TIME_ATTRIBUTE,
    validate_cycle_time,
)
from dbckit.model.database import AttributeDefinition, AttributeKind, Database
from dbckit.model.message import Message


def automatic_cycle_time_definition() -> AttributeDefinition:
    """Return the standard definition created for mutation-supplied cycle times."""
    return AttributeDefinition(
        name=CYCLE_TIME_ATTRIBUTE,
        kind=AttributeKind.INT,
        object_type="BO_",
        minimum=AUTO_CYCLE_TIME_MINIMUM,
        maximum=AUTO_CYCLE_TIME_MAXIMUM,
        default=AUTO_CYCLE_TIME_DEFAULT,
    )


def definition_for(db: Database) -> AttributeDefinition | None:
    return db.attributes.get(CYCLE_TIME_ATTRIBUTE)


def ensure_definition(db: Database) -> dict[str, AttributeDefinition]:
    """Return definitions containing the standard cycle-time definition."""
    if CYCLE_TIME_ATTRIBUTE in db.attributes:
        return db.attributes
    return {
        **db.attributes,
        CYCLE_TIME_ATTRIBUTE: automatic_cycle_time_definition(),
    }


def normalise_message(
    message: Message,
    definition: AttributeDefinition | None,
) -> Message:
    """Synchronise a possibly model-copied message and validate its cycle time."""
    raw_cycle_time = message.cycle_time
    if raw_cycle_time is None and CYCLE_TIME_ATTRIBUTE in message.attributes:
        raw_cycle_time = message.attributes[CYCLE_TIME_ATTRIBUTE]
    attributes = dict(message.attributes)
    if raw_cycle_time is None:
        attributes.pop(CYCLE_TIME_ATTRIBUTE, None)
        return message.model_copy(
            update={"cycle_time": None, "attributes": attributes}
        )
    cycle_time = validate_cycle_time(raw_cycle_time, definition)
    attributes[CYCLE_TIME_ATTRIBUTE] = cycle_time
    return message.model_copy(
        update={"cycle_time": cycle_time, "attributes": attributes}
    )
