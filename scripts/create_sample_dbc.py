from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from dbckit import (  # noqa: E402
    AttributeDefinition,
    AttributeKind,
    Database,
    Message,
    Node,
    Signal,
)


def build_database() -> Database:
    db = Database()

    db = db.add_node(Node(name="ECM", comment="Engine control module"))
    db = db.add_node(Node(name="TCM", comment="Transmission control module"))

    db = db.define_attribute(
        AttributeDefinition(
            name="GenMsgCycleTime",
            kind=AttributeKind.INT,
            object_type="BO_",
            minimum=0,
            maximum=60000,
            default=0,
        )
    )
    db = db.define_attribute(
        AttributeDefinition(
            name="SignalOwner",
            kind=AttributeKind.STRING,
            object_type="SG_",
            default="",
        )
    )

    db = db.add_message(
        Message(
            arbitration_id=0x100,
            name="PowertrainData",
            length=8,
            senders=["ECM"],
            comment="Sample message created by the smoke script.",
        )
    )

    db = db.message(0x100).add_signal(
        Signal(
            name="EngineSpeed",
            start_bit=0,
            length=16,
            factor=0.125,
            unit="rpm",
            receivers=["TCM"],
        )
    )
    db = db.message(0x100).add_signal(
        Signal(
            name="ThrottlePosition",
            start_bit=16,
            length=8,
            factor=0.4,
            unit="%",
            receivers=["TCM"],
        )
    )
    db = db.message(0x100).add_signal(
        Signal(
            name="IgnitionStatus",
            start_bit=24,
            length=2,
            receivers=["TCM"],
        )
    )

    db = db.message(0x100).set_attribute("GenMsgCycleTime", 20)
    db = db.message(0x100).signal("EngineSpeed").set_attribute("SignalOwner", "powertrain")
    db = db.message(0x100).signal("IgnitionStatus").add_choice(0, "Off")
    db = db.message(0x100).signal("IgnitionStatus").add_choice(1, "Run")
    db = db.message(0x100).signal("IgnitionStatus").add_choice(2, "Start")

    return db


def main() -> int:
    out_path = Path(sys.argv[1]) if len(sys.argv) > 1 else ROOT / "sample.dbc"
    db = build_database()
    issues = db.validate()
    errors = [issue for issue in issues if issue.severity == "error"]
    if errors:
        for issue in errors:
            print(f"error: {issue.code} at {issue.location}: {issue.message}", file=sys.stderr)
        return 1

    db.save(out_path)
    print(f"wrote {out_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
