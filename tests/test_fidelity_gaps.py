"""Regression tests for pre-publish DBC fidelity and message API guarantees."""
from __future__ import annotations

import pytest
from pydantic import ValidationError

import dbckit
from dbckit.model.database import (
    AttributeDefinition,
    AttributeKind,
    Database,
    EnvironmentVariable,
)
from dbckit.model.message import Message
from dbckit.model.signal import SignalGroup, ValueTable
from dbckit.mutations.attribute import (
    define_attribute,
    delete_attribute,
    set_message_attribute,
    unset_message_attribute,
)
from dbckit.mutations.message import (
    add_message,
    change_arbitration_id,
    update_message,
)

CYCLE = "GenMsgCycleTime"
MINIMAL = '''VERSION ""
NS_ :
BS_ :
BU_ : ECU
BO_ 100 Msg: 8 ECU
'''


def _cycle_definition(minimum: int = 0, maximum: int = 1000):
    return AttributeDefinition(
        name=CYCLE,
        kind=AttributeKind.INT,
        object_type="BO_",
        minimum=minimum,
        maximum=maximum,
    )


def _database(*, definition: AttributeDefinition | None = None) -> Database:
    message = Message(arbitration_id=100, name="Msg", length=8)
    attributes = {CYCLE: definition} if definition is not None else {}
    return Database(messages={100: message}, attributes=attributes)


def test_message_construction_synchronises_cycle_time_and_attribute():
    from_attribute = Message(
        arbitration_id=1,
        name="M",
        length=8,
        attributes={CYCLE: "25"},
    )
    cycle_wins = Message(
        arbitration_id=1,
        name="M",
        length=8,
        attributes={CYCLE: 10},
        cycle_time=20,
    )
    from_json = Message.model_validate_json(
        '{"arbitration_id":1,"name":"M","length":8,'
        '"attributes":{"GenMsgCycleTime":"30"}}'
    )

    assert (from_attribute.cycle_time, from_attribute.attributes[CYCLE]) == (25, 25)
    assert (cycle_wins.cycle_time, cycle_wins.attributes[CYCLE]) == (20, 20)
    assert (from_json.cycle_time, from_json.attributes[CYCLE]) == (30, 30)


@pytest.mark.parametrize("value", [True, 1.5, "1.5", "not-an-int"])
def test_message_construction_rejects_non_integral_cycle_time(value):
    with pytest.raises((ValueError, ValidationError), match="must be an integer"):
        Message(arbitration_id=1, name="M", length=8, cycle_time=value)


def test_parse_cycle_time_populates_both_representations():
    db = dbckit.parse(
        MINIMAL
        + 'BA_DEF_ BO_ "GenMsgCycleTime" INT 0 1000;\n'
        + 'BA_ "GenMsgCycleTime" BO_ 100 500;\n'
    )

    assert db.messages[100].cycle_time == 500
    assert db.messages[100].attributes[CYCLE] == 500


def test_definitionless_cycle_time_is_repaired_on_dump_and_reparse():
    db = dbckit.parse(MINIMAL + 'BA_ "GenMsgCycleTime" BO_ 100 500;\n')

    assert CYCLE not in db.attributes
    assert db.messages[100].cycle_time == 500
    text = dbckit.dump(db)
    assert f'BA_DEF_ BO_ "{CYCLE}" INT 0 2147483647;' in text
    assert f'BA_DEF_DEF_  "{CYCLE}" 0;' in text
    assert text.count(f'BA_ "{CYCLE}" BO_ 100 500;') == 1
    reparsed = dbckit.parse(text)
    assert reparsed.messages[100].cycle_time == 500
    assert reparsed.attributes[CYCLE].default == 0


@pytest.mark.parametrize(
    "body",
    [
        'BA_DEF_ BO_ "GenMsgCycleTime" INT 0 100;\n'
        'BA_ "GenMsgCycleTime" BO_ 100 101;\n',
        'BA_ "GenMsgCycleTime" BO_ 100 101;\n'
        'BA_DEF_ BO_ "GenMsgCycleTime" INT 0 100;\n',
    ],
)
def test_parse_rejects_cycle_time_outside_existing_range(body):
    with pytest.raises(ValueError, match="outside the declared range"):
        dbckit.parse(MINIMAL + body)


def test_parse_rejects_fractional_cycle_time():
    with pytest.raises(ValueError, match="must be an integer"):
        dbckit.parse(
            MINIMAL
            + 'BA_DEF_ BO_ "GenMsgCycleTime" INT 0 100;\n'
            + 'BA_ "GenMsgCycleTime" BO_ 100 1.5;\n'
        )


def test_cycle_time_mutation_hooks_synchronise_and_preserve_input():
    original = _database()
    updated = update_message(original, 100, cycle_time=20)
    replaced = update_message(updated, 100, attributes={CYCLE: "30"})
    explicit = update_message(
        replaced,
        100,
        attributes={CYCLE: 40},
        cycle_time=50,
    )
    cleared = update_message(explicit, 100, attributes={})
    set_value = set_message_attribute(cleared, 100, CYCLE, 60)
    unset_value = unset_message_attribute(set_value, 100, CYCLE)

    assert original.messages[100].cycle_time is None
    assert CYCLE not in original.attributes
    assert updated.messages[100].attributes[CYCLE] == 20
    assert updated.attributes[CYCLE].minimum == 0
    assert updated.attributes[CYCLE].maximum == 2_147_483_647
    assert updated.attributes[CYCLE].default == 0
    assert (replaced.messages[100].cycle_time, explicit.messages[100].cycle_time) == (
        30,
        50,
    )
    assert cleared.messages[100].cycle_time is None
    assert CYCLE not in cleared.messages[100].attributes
    assert set_value.messages[100].cycle_time == 60
    assert unset_value.messages[100].cycle_time is None


def test_add_message_with_cycle_time_creates_definition():
    db = add_message(
        Database(),
        Message(arbitration_id=100, name="M", length=8, cycle_time=25),
    )

    assert db.messages[100].attributes[CYCLE] == 25
    assert db.attributes[CYCLE].maximum == 2_147_483_647


def test_existing_cycle_time_range_is_never_widened_by_mutation():
    definition = _cycle_definition(maximum=100)
    db = _database(definition=definition)

    with pytest.raises(ValueError, match="outside the declared range"):
        update_message(db, 100, cycle_time=101)
    with pytest.raises(ValueError, match="outside the declared range"):
        set_message_attribute(db, 100, CYCLE, 101)
    assert db.attributes[CYCLE] is definition
    assert db.attributes[CYCLE].maximum == 100


def test_definition_replacement_validates_existing_cycle_times():
    db = update_message(_database(), 100, cycle_time=80)

    with pytest.raises(ValueError, match="outside the declared range"):
        define_attribute(db, _cycle_definition(maximum=50))
    replaced = define_attribute(db, _cycle_definition(maximum=100))
    assert replaced.attributes[CYCLE].maximum == 100
    assert replaced.messages[100].cycle_time == 80


def test_deleting_cycle_definition_clears_cycle_values():
    db = update_message(_database(), 100, cycle_time=80)
    deleted = delete_attribute(db, CYCLE)

    assert CYCLE not in deleted.attributes
    assert deleted.messages[100].cycle_time is None
    assert CYCLE not in deleted.messages[100].attributes


def test_dump_cycle_time_uses_field_precedence_once_without_mutation():
    definition = _cycle_definition(maximum=25)
    message = Message(arbitration_id=100, name="M", length=8, cycle_time=20)
    inconsistent = message.model_copy(
        update={"attributes": {CYCLE: 10}, "cycle_time": 20}
    )
    db = Database(messages={100: inconsistent}, attributes={CYCLE: definition})

    text = dbckit.dump(db)
    assert text.count(f'BA_ "{CYCLE}" BO_ 100 20;') == 1
    assert f'BA_ "{CYCLE}" BO_ 100 10;' not in text
    assert db.messages[100].attributes[CYCLE] == 10


def test_dump_rejects_cycle_time_outside_existing_range():
    definition = _cycle_definition(maximum=10)
    message = Message(arbitration_id=100, name="M", length=8, cycle_time=11)
    db = Database(messages={100: message}, attributes={CYCLE: definition})

    with pytest.raises(ValueError, match="outside the declared range"):
        dbckit.dump(db)


def _env_dbc(*, value_before_definition: bool = False) -> str:
    env = 'EV_ EvName: 0 [0|1] "" 0 1 DUMMY_NODE_VECTOR0 ECU ;\n'
    choices = 'VAL_ EvName 0 "Off" 1 "On" ;\n'
    return MINIMAL + (choices + env if value_before_definition else env + choices)


def test_environment_variable_choices_parse_serialize_and_roundtrip():
    db = dbckit.parse(_env_dbc())

    assert "EvName" not in db.value_tables
    assert db.environment_variables["EvName"].value_table is not None
    assert db.environment_variables["EvName"].value_table.values == {
        0: "Off",
        1: "On",
    }
    reparsed = dbckit.parse(dbckit.dump(db))
    assert reparsed.environment_variables["EvName"].value_table.values[1] == "On"
    assert "EvName" not in reparsed.value_tables


@pytest.mark.parametrize("text", [MINIMAL + 'VAL_ Missing 0 "Off";\n', _env_dbc(value_before_definition=True)])
def test_environment_variable_choices_require_an_existing_target(text):
    with pytest.raises(ValueError, match="VAL_ references unknown environment variable"):
        dbckit.parse(text)


def test_constructed_environment_variable_choices_serialize():
    env = EnvironmentVariable(
        name="EvName",
        access_type="DUMMY_NODE_VECTOR0",
        value_table=ValueTable(name="EvName", values={0: "Off"}),
    )
    text = dbckit.dump(Database(environment_variables={"EvName": env}))
    assert 'VAL_ EvName 0 "Off" ;' in text


@pytest.mark.parametrize(
    ("specific", "expected"),
    [({}, None), ({"comment": ""}, 'CM_ "";'), ({"comment": "database"}, 'CM_ "database";')],
)
def test_database_comment_presence_and_roundtrip(specific, expected):
    db = Database(dbc_specific=specific)
    text = dbckit.dump(db)

    if expected is None:
        assert "CM_" not in text
    else:
        assert text.count(expected) == 1
        second = dbckit.dump(dbckit.parse(text))
        assert second.count(expected) == 1


def test_change_arbitration_id_preserves_order_metadata_and_groups():
    first = Message(
        arbitration_id=100,
        name="First",
        length=8,
        is_extended_frame=True,
    )
    second = Message(arbitration_id=200, name="Second", length=8)
    group = SignalGroup(name="Group", message_id=100, signal_names=[])
    original = Database(
        messages={100: first, 200: second},
        signal_groups=[group],
    )

    changed = change_arbitration_id(original, 100, 150)

    assert list(changed.messages) == [150, 200]
    assert changed.messages[150].arbitration_id == 150
    assert changed.messages[150].is_extended_frame is True
    assert changed.signal_groups[0].message_id == 150
    assert list(original.messages) == [100, 200]
    assert original.signal_groups[0].message_id == 100
    reparsed = dbckit.parse(dbckit.dump(changed))
    assert reparsed.messages[150].is_extended_frame is True
    assert reparsed.signal_groups[0].message_id == 150


def test_message_view_changes_arbitration_id():
    changed = _database().message(100).change_arbitration_id(150)
    assert 150 in changed.messages
    assert 100 not in changed.messages


def test_change_arbitration_id_noop_missing_and_collision():
    db = Database(
        messages={
            100: Message(arbitration_id=100, name="A", length=8),
            200: Message(arbitration_id=200, name="B", length=8),
        }
    )

    assert change_arbitration_id(db, 100, 100) is db
    with pytest.raises(KeyError, match="0x12c"):
        change_arbitration_id(db, 300, 300)
    with pytest.raises(ValueError, match="already exists"):
        change_arbitration_id(db, 100, 200)
