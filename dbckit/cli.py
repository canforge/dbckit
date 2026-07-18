"""CLI for dbckit — thin shell over the public API, powered by Typer + Rich."""
from __future__ import annotations

import csv
import json
import sys
from pathlib import Path
from typing import Optional, cast

try:
    import typer
    from rich.console import Console
    from rich.table import Table
except ImportError:  # pragma: no cover
    print("Install the 'cli' extra: pip install dbckit[cli]", file=sys.stderr)
    raise SystemExit(1)

import dbckit
from dbckit.model.database import AttributeDefinition, AttributeKind, Node
from dbckit.model.message import Message
from dbckit.model.signal import ByteOrder, Signal

app = typer.Typer(
    name="dbckit",
    help="DBC file toolkit.",
    no_args_is_help=True,
    rich_markup_mode="rich",
)

# ── sub-apps ──────────────────────────────────────────────────────────────────
db_app = typer.Typer(help="Database-level commands.", no_args_is_help=True)
msg_app = typer.Typer(help="Message commands.", no_args_is_help=True)
sig_app = typer.Typer(help="Signal commands.", no_args_is_help=True)
node_app = typer.Typer(help="Node commands.", no_args_is_help=True)
attr_app = typer.Typer(help="Attribute commands.", no_args_is_help=True)
decode_app = typer.Typer(help="Decode commands.", no_args_is_help=True)
encode_app = typer.Typer(help="Encode commands.", no_args_is_help=True)
codegen_app = typer.Typer(help="Code/doc generation.", no_args_is_help=True)

app.add_typer(db_app, name="db")
app.add_typer(msg_app, name="message")
app.add_typer(sig_app, name="signal")
app.add_typer(node_app, name="node")
app.add_typer(attr_app, name="attribute")
app.add_typer(decode_app, name="decode")
app.add_typer(encode_app, name="encode")
app.add_typer(codegen_app, name="codegen")

console = Console()
err_console = Console(stderr=True)

# ── shared option ─────────────────────────────────────────────────────────────
_DB_OPT = typer.Option(..., "--db", help="Path to .dbc file.", show_default=False)
_OUT_OPT = typer.Option("table", "--output", "-o", help="Output format: table|json|csv.")


def _load(path: Path) -> dbckit.Database:
    return dbckit.load(path)


def _out_format(fmt: str) -> str:
    return fmt.lower()


def _frame_match_mode(value: str) -> dbckit.FrameMatchMode:
    normalized = value.strip().lower()
    if normalized not in ("exact", "j1939", "auto"):
        raise typer.BadParameter(
            "must be one of: exact, j1939, auto",
            param_hint="--match",
        )
    return cast(dbckit.FrameMatchMode, normalized)


def _print_json(obj) -> None:
    if hasattr(obj, "model_dump_json"):
        console.print_json(obj.model_dump_json(indent=2))
    elif isinstance(obj, list):
        console.print_json(json.dumps([
            o.model_dump() if hasattr(o, "model_dump") else o for o in obj
        ], indent=2))
    else:
        console.print_json(json.dumps(obj, indent=2, default=str))


def _print_csv(rows: list[dict[str, object]]) -> None:
    if not rows:
        return
    writer = csv.DictWriter(sys.stdout, fieldnames=list(rows[0].keys()))
    writer.writeheader()
    writer.writerows(rows)


# ═══════════════════════════════════════════════════════════════════════════════
# db commands
# ═══════════════════════════════════════════════════════════════════════════════

@db_app.command("info")
def db_info(
    db_path: Path = _DB_OPT,
    output: str = _OUT_OPT,
):
    """[green]Show high-level database info.[/green]"""
    db = _load(db_path)
    if _out_format(output) == "json":
        _print_json({
            "version": db.version,
            "filename": db.filename,
            "nodes": list(db.nodes),
            "message_count": len(db.messages),
            "attribute_count": len(db.attributes),
        })
        return
    if _out_format(output) == "csv":
        _print_csv([{
            "version": db.version,
            "filename": db.filename or "",
            "nodes": ",".join(db.nodes),
            "message_count": len(db.messages),
            "attribute_count": len(db.attributes),
            "value_table_count": len(db.value_tables),
        }])
        return
    t = Table(title=f"[bold]{db_path.name}[/bold]", show_header=False)
    t.add_column("Field", style="cyan")
    t.add_column("Value")
    t.add_row("Version", db.version or "(none)")
    t.add_row("Nodes", ", ".join(db.nodes) or "(none)")
    t.add_row("Messages", str(len(db.messages)))
    t.add_row("Attributes", str(len(db.attributes)))
    t.add_row("Value tables", str(len(db.value_tables)))
    console.print(t)


@db_app.command("validate")
def db_validate(
    db_path: Path = _DB_OPT,
    strict: bool = typer.Option(False, "--strict", help="Treat warnings as errors."),
    output: str = _OUT_OPT,
):
    """[green]Validate a DBC file and list issues.[/green]"""
    db = _load(db_path)
    issues = dbckit.validate(db, strict=strict)
    errors = sum(1 for i in issues if i.severity == "error")
    if not issues:
        console.print("[green]✓ No issues found.[/green]")
        return
    if _out_format(output) == "json":
        _print_json(issues)
        if errors:
            raise typer.Exit(1)
        return
    if _out_format(output) == "csv":
        _print_csv([
            {
                "severity": iss.severity,
                "code": iss.code,
                "location": iss.location,
                "message": iss.message,
            }
            for iss in issues
        ])
        if errors:
            raise typer.Exit(1)
        return
    t = Table(title="Validation Issues")
    t.add_column("Severity", style="bold")
    t.add_column("Code", style="cyan")
    t.add_column("Location")
    t.add_column("Message")
    for iss in issues:
        color = "red" if iss.severity == "error" else "yellow"
        t.add_row(
            f"[{color}]{iss.severity.upper()}[/{color}]",
            iss.code,
            iss.location,
            iss.message,
        )
    console.print(t)
    if errors:
        raise typer.Exit(1)


@db_app.command("diff")
def db_diff(
    db_a: Path = typer.Argument(..., help="Base DBC file."),
    db_b: Path = typer.Argument(..., help="Changed DBC file."),
    output: str = _OUT_OPT,
):
    """[green]Diff two DBC files.[/green]"""
    result = dbckit.diff(dbckit.load(db_a), dbckit.load(db_b))
    if _out_format(output) == "json":
        _print_json(result)
        return
    if result.is_empty:
        console.print("[green]No differences.[/green]")
        return
    for msg in result.added_messages:
        console.print(f"[green]+ message {msg.name} ({msg.arbitration_id:#x})[/green]")
    for msg in result.removed_messages:
        console.print(f"[red]- message {msg.name} ({msg.arbitration_id:#x})[/red]")
    for md in result.modified_messages:
        console.print(f"[yellow]~ message {md.message_name} ({md.arbitration_id:#x})[/yellow]")
        for field, (before, after) in md.field_changes.items():
            console.print(f"  [yellow]~ {field}: {before!r} → {after!r}[/yellow]")
        for sd in md.signal_diffs:
            sym = "+" if sd.change == "added" else ("-" if sd.change == "removed" else "~")
            color = "green" if sd.change == "added" else ("red" if sd.change == "removed" else "yellow")
            console.print(f"  [{color}]{sym} signal {sd.signal_name}[/{color}]")


@db_app.command("merge")
def db_merge(
    db_a: Path = typer.Argument(..., help="Base DBC file."),
    db_b: Path = typer.Argument(..., help="DBC file to merge in."),
    out: Path = typer.Argument(..., help="Output path."),
    strategy: str = typer.Option("raise", "--strategy", help="raise|ours|theirs"),
):
    """[blue]Merge two DBC files.[/blue]"""
    merged = dbckit.merge(dbckit.load(db_a), dbckit.load(db_b), strategy=strategy)  # type: ignore[arg-type]
    dbckit.save(merged, out)
    console.print(f"[blue]Merged → {out}[/blue]")


@db_app.command("extract")
def db_extract(
    db_path: Path = _DB_OPT,
    ids: list[str] = typer.Argument(..., help="Arbitration IDs (hex or decimal)."),
    out: Path = typer.Option(..., "--out", help="Output path."),
):
    """[blue]Extract messages by ID into a new DBC file.[/blue]"""
    db = _load(db_path)
    parsed_ids = [int(i, 0) for i in ids]
    sub = dbckit.extract(db, parsed_ids)
    dbckit.save(sub, out)
    console.print(f"[blue]Extracted {len(parsed_ids)} message(s) → {out}[/blue]")


@db_app.command("export")
def db_export(
    db_path: Path = _DB_OPT,
    output: str = _OUT_OPT,
    out: Optional[Path] = typer.Option(None, "--out", help="Write exported JSON to a file."),
):
    """[green]Export database as JSON.[/green]"""
    db = _load(db_path)
    payload = db.model_dump_json(indent=2)
    if out:
        out.write_text(payload, encoding="utf-8")
        console.print(f"[green]Exported JSON → {out}[/green]")
        return
    console.print_json(payload)


@db_app.command("import")
def db_import(
    src: Path = typer.Argument(..., help="Path to exported JSON."),
    out: Path = typer.Option(..., "--out", help="Output .dbc path."),
):
    """[blue]Import a database from exported JSON and write a DBC file.[/blue]"""
    db = dbckit.Database.model_validate_json(src.read_text(encoding="utf-8"))
    dbckit.save(db, out)
    console.print(f"[blue]Imported → {out}[/blue]")


# ═══════════════════════════════════════════════════════════════════════════════
# message commands
# ═══════════════════════════════════════════════════════════════════════════════

@msg_app.command("list")
def msg_list(
    db_path: Path = _DB_OPT,
    node: Optional[str] = typer.Option(None, "--node", help="Filter by sender node."),
    pgn: Optional[int] = typer.Option(None, "--pgn", help="Filter by J1939 PGN."),
    output: str = _OUT_OPT,
):
    """[green]List all messages.[/green]"""
    db = _load(db_path)
    if pgn is not None:
        messages = [view._message for view in dbckit.find_messages_by_pgn(db, pgn)]
    else:
        messages = list(db.messages.values())
    if node:
        messages = [m for m in messages if node in m.senders]
    if _out_format(output) == "json":
        _print_json(messages)
        return
    if _out_format(output) == "csv":
        _print_csv([
            {
                "arbitration_id": msg.arbitration_id,
                "name": msg.name,
                "length": msg.length,
                "senders": ",".join(msg.senders),
                "signal_count": len(msg.signals),
            }
            for msg in sorted(messages, key=lambda m: m.arbitration_id)
        ])
        return
    t = Table(title="Messages")
    t.add_column("ID (hex)", style="cyan")
    t.add_column("Name")
    t.add_column("DLC")
    t.add_column("Senders")
    t.add_column("Signals")
    for msg in sorted(messages, key=lambda m: m.arbitration_id):
        t.add_row(
            f"{msg.arbitration_id:#x}",
            msg.name,
            str(msg.length),
            ", ".join(msg.senders) or "(none)",
            str(len(msg.signals)),
        )
    console.print(t)


@msg_app.command("get")
def msg_get(
    db_path: Path = _DB_OPT,
    arb_id: Optional[str] = typer.Argument(None, help="Arbitration ID (hex or decimal)."),
    pgn: Optional[int] = typer.Option(None, "--pgn", help="Look up a message by J1939 PGN."),
    output: str = _OUT_OPT,
):
    """[green]Show details for one message.[/green]"""
    db = _load(db_path)
    if (arb_id is None) == (pgn is None):
        err_console.print("[red]Provide exactly one of <arb_id> or --pgn.[/red]")
        raise typer.Exit(1)
    if pgn is not None:
        try:
            msg = db.message_by_pgn(pgn)._message
            msg_ref = f"PGN {pgn}"
        except (KeyError, ValueError) as exc:
            err_console.print(f"[red]{exc}[/red]")
            raise typer.Exit(1) from exc
    else:
        msg = db.messages.get(int(arb_id, 0))
        if msg is None:
            err_console.print(f"[red]Message {arb_id} not found.[/red]")
            raise typer.Exit(1)
        msg_ref = arb_id
    if _out_format(output) == "json":
        _print_json(msg)
        return
    if _out_format(output) == "csv":
        _print_csv([{
            "arbitration_id": msg.arbitration_id,
            "name": msg.name,
            "length": msg.length,
            "senders": ",".join(msg.senders),
            "comment": msg.comment or "",
        }])
        return
    console.print(f"[bold]{msg.name}[/bold] ({msg_ref})")
    console.print(f"  DLC: {msg.length}  Senders: {', '.join(msg.senders) or '(none)'}")
    if msg.comment:
        console.print(f"  Comment: {msg.comment}")
    _print_signals_table(msg)


@msg_app.command("search")
def msg_search(
    db_path: Path = _DB_OPT,
    query: str = typer.Argument(..., help="Search term."),
    output: str = _OUT_OPT,
):
    """[green]Search messages by name/comment.[/green]"""
    db = _load(db_path)
    results = dbckit.search_messages(db, query)
    if _out_format(output) == "json":
        _print_json(results)
        return
    if _out_format(output) == "csv":
        _print_csv([
            {"arbitration_id": msg.arbitration_id, "name": msg.name, "comment": msg.comment or ""}
            for msg in results
        ])
        return
    console.print(f"Found {len(results)} message(s):")
    for msg in results:
        console.print(f"  [cyan]{msg.arbitration_id:#x}[/cyan] {msg.name}")


@msg_app.command("create")
def msg_create(
    db_path: Path = _DB_OPT,
    arb_id: str = typer.Argument(..., help="Arbitration ID (hex or decimal)."),
    name: str = typer.Argument(..., help="Message name."),
    length: int = typer.Option(8, "--length", "-l", help="DLC in bytes."),
    sender: Optional[str] = typer.Option(None, "--sender", help="Sender node name."),
):
    """[blue]Add a new message.[/blue]"""
    db = _load(db_path)
    msg = Message(
        arbitration_id=int(arb_id, 0),
        name=name,
        length=length,
        senders=[sender] if sender else [],
    )
    db2 = db.add_message(msg)
    dbckit.save(db2, db_path)
    console.print(f"[blue]Added message {name} ({arb_id})[/blue]")


@msg_app.command("update")
def msg_update(
    db_path: Path = _DB_OPT,
    arb_id: str = typer.Argument(..., help="Arbitration ID (hex or decimal)."),
    length: Optional[int] = typer.Option(None, "--length", "-l", help="DLC in bytes."),
    sender: list[str] = typer.Option([], "--sender", help="Sender node name. Repeat to replace senders."),
    comment: Optional[str] = typer.Option(None, "--comment", help="Message comment."),
    cycle_time: Optional[int] = typer.Option(None, "--cycle-time", help="Cycle time in milliseconds."),
):
    """[blue]Update an existing message.[/blue]"""
    updates: dict[str, object] = {}
    if length is not None:
        updates["length"] = length
    if sender:
        updates["senders"] = sender
    if comment is not None:
        updates["comment"] = comment
    if not updates and cycle_time is None:
        err_console.print("[red]No update fields provided.[/red]")
        raise typer.Exit(1)
    db = _load(db_path)
    message_id = int(arb_id, 0)
    db2 = db.message(message_id).update(**updates) if updates else db
    if cycle_time is not None:
        db2 = db2.message(message_id).set_attribute("GenMsgCycleTime", cycle_time)
    dbckit.save(db2, db_path)
    console.print(f"[blue]Updated message {arb_id}[/blue]")


@msg_app.command("delete")
def msg_delete(
    db_path: Path = _DB_OPT,
    arb_id: str = typer.Argument(..., help="Arbitration ID (hex or decimal)."),
):
    """[blue]Delete a message.[/blue]"""
    db = _load(db_path)
    db2 = db.message(int(arb_id, 0)).delete()
    dbckit.save(db2, db_path)
    console.print(f"[blue]Deleted message {arb_id}[/blue]")


@msg_app.command("rename")
def msg_rename(
    db_path: Path = _DB_OPT,
    arb_id: str = typer.Argument(...),
    new_name: str = typer.Argument(...),
):
    """[blue]Rename a message.[/blue]"""
    db = _load(db_path)
    db2 = db.message(int(arb_id, 0)).rename(new_name)
    dbckit.save(db2, db_path)
    console.print(f"[blue]Renamed → {new_name}[/blue]")


# ═══════════════════════════════════════════════════════════════════════════════
# signal commands
# ═══════════════════════════════════════════════════════════════════════════════

@sig_app.command("list")
def sig_list(
    db_path: Path = _DB_OPT,
    arb_id: str = typer.Argument(..., help="Message arbitration ID."),
    output: str = _OUT_OPT,
):
    """[green]List signals in a message.[/green]"""
    db = _load(db_path)
    msg = _require_msg(db, arb_id)
    if _out_format(output) == "json":
        _print_json(list(msg.signals.values()))
        return
    if _out_format(output) == "csv":
        _print_csv([
            {
                "name": sig.name,
                "start_bit": sig.start_bit,
                "length": sig.length,
                "byte_order": sig.byte_order.value,
                "factor": sig.factor,
                "offset": sig.offset,
                "unit": sig.unit,
                "multiplex_indicator": sig.multiplex_indicator or "",
            }
            for sig in msg.signals.values()
        ])
        return
    _print_signals_table(msg)


@sig_app.command("get")
def sig_get(
    db_path: Path = _DB_OPT,
    arb_id: str = typer.Argument(...),
    signal_name: str = typer.Argument(...),
    output: str = _OUT_OPT,
):
    """[green]Show details for one signal.[/green]"""
    db = _load(db_path)
    msg = _require_msg(db, arb_id)
    sig = _require_sig(msg, signal_name)
    if _out_format(output) == "json":
        _print_json(sig)
        return
    if _out_format(output) == "csv":
        _print_csv([{
            "message_id": int(arb_id, 0),
            "name": sig.name,
            "start_bit": sig.start_bit,
            "length": sig.length,
            "byte_order": sig.byte_order.value,
            "is_signed": sig.is_signed,
            "factor": sig.factor,
            "offset": sig.offset,
            "unit": sig.unit,
            "receivers": ",".join(sig.receivers),
            "comment": sig.comment or "",
        }])
        return
    console.print(f"[bold]{sig.name}[/bold]")
    console.print(f"  start_bit={sig.start_bit} length={sig.length}")
    console.print(f"  byte_order={sig.byte_order.value} signed={sig.is_signed}")
    console.print(f"  factor={sig.factor} offset={sig.offset}")
    console.print(f"  unit={sig.unit!r} receivers={sig.receivers}")
    if sig.comment:
        console.print(f"  comment: {sig.comment}")
    if sig.value_table:
        console.print("  values:")
        for k, v in sorted(sig.value_table.values.items()):
            console.print(f"    {k} = {v}")


@sig_app.command("search")
def sig_search(
    db_path: Path = _DB_OPT,
    query: str = typer.Argument(..., help="Search term."),
    output: str = _OUT_OPT,
):
    """[green]Search signals by name/comment.[/green]"""
    db = _load(db_path)
    results = dbckit.search_signals(db, query)
    if _out_format(output) == "json":
        _print_json([{"message": m.name, "signal": s.name} for m, s in results])
        return
    if _out_format(output) == "csv":
        _print_csv([
            {"message": msg.name, "message_id": msg.arbitration_id, "signal": sig.name}
            for msg, sig in results
        ])
        return
    console.print(f"Found {len(results)} signal(s):")
    for msg, sig in results:
        console.print(f"  [cyan]{msg.name}[/cyan] / {sig.name}")


@sig_app.command("layout")
def sig_layout(
    db_path: Path = _DB_OPT,
    arb_id: str = typer.Argument(..., help="Message arbitration ID."),
):
    """[green]Render signal bit-grid for a message.[/green]"""
    db = _load(db_path)
    msg = _require_msg(db, arb_id)
    slots = db.message(msg.arbitration_id).layout()
    _render_bit_grid(msg, slots)


@sig_app.command("delete")
def sig_delete(
    db_path: Path = _DB_OPT,
    arb_id: str = typer.Argument(...),
    signal_name: str = typer.Argument(...),
):
    """[blue]Delete a signal from a message.[/blue]"""
    db = _load(db_path)
    db2 = db.message(int(arb_id, 0)).signal(signal_name).delete()
    dbckit.save(db2, db_path)
    console.print(f"[blue]Deleted signal {signal_name}[/blue]")


@sig_app.command("create")
def sig_create(
    db_path: Path = _DB_OPT,
    arb_id: str = typer.Argument(..., help="Message arbitration ID."),
    signal_name: str = typer.Argument(..., help="Signal name."),
    start_bit: int = typer.Option(..., "--start-bit", help="Signal start bit."),
    length: int = typer.Option(..., "--length", help="Signal length in bits."),
    byte_order: ByteOrder = typer.Option(ByteOrder.little_endian, "--byte-order", help="Signal byte order."),
    is_signed: Optional[bool] = typer.Option(None, "--signed/--unsigned", help="Signal signedness."),
    factor: float = typer.Option(1.0, "--factor", help="Scale factor."),
    offset: float = typer.Option(0.0, "--offset", help="Physical offset."),
    minimum: Optional[float] = typer.Option(None, "--minimum", help="Minimum physical value."),
    maximum: Optional[float] = typer.Option(None, "--maximum", help="Maximum physical value."),
    unit: str = typer.Option("", "--unit", help="Signal engineering unit."),
    receiver: list[str] = typer.Option([], "--receiver", help="Receiver node name. Repeat as needed."),
    comment: Optional[str] = typer.Option(None, "--comment", help="Signal comment."),
    multiplex: Optional[str] = typer.Option(None, "--multiplex", help="Multiplex indicator, e.g. M or m0."),
):
    """[blue]Add a new signal to a message.[/blue]"""
    db = _load(db_path)
    signal = Signal(
        name=signal_name,
        start_bit=start_bit,
        length=length,
        byte_order=byte_order,
        is_signed=is_signed if is_signed is not None else False,
        factor=factor,
        offset=offset,
        minimum=minimum,
        maximum=maximum,
        unit=unit,
        receivers=receiver,
        comment=comment,
        multiplex_indicator=multiplex,
    )
    db2 = db.message(int(arb_id, 0)).add_signal(signal)
    dbckit.save(db2, db_path)
    console.print(f"[blue]Added signal {signal_name} to {arb_id}[/blue]")


@sig_app.command("update")
def sig_update(
    db_path: Path = _DB_OPT,
    arb_id: str = typer.Argument(..., help="Message arbitration ID."),
    signal_name: str = typer.Argument(..., help="Signal name."),
    start_bit: Optional[int] = typer.Option(None, "--start-bit", help="Signal start bit."),
    length: Optional[int] = typer.Option(None, "--length", help="Signal length in bits."),
    byte_order: Optional[ByteOrder] = typer.Option(None, "--byte-order", help="Signal byte order."),
    is_signed: Optional[bool] = typer.Option(None, "--signed/--unsigned", help="Signal signedness."),
    factor: Optional[float] = typer.Option(None, "--factor", help="Scale factor."),
    offset: Optional[float] = typer.Option(None, "--offset", help="Physical offset."),
    minimum: Optional[float] = typer.Option(None, "--minimum", help="Minimum physical value."),
    maximum: Optional[float] = typer.Option(None, "--maximum", help="Maximum physical value."),
    unit: Optional[str] = typer.Option(None, "--unit", help="Signal engineering unit."),
    receiver: list[str] = typer.Option([], "--receiver", help="Receiver node name. Repeat to replace receivers."),
    comment: Optional[str] = typer.Option(None, "--comment", help="Signal comment."),
    multiplex: Optional[str] = typer.Option(None, "--multiplex", help="Multiplex indicator."),
):
    """[blue]Update an existing signal.[/blue]"""
    updates: dict[str, object] = {}
    if start_bit is not None:
        updates["start_bit"] = start_bit
    if length is not None:
        updates["length"] = length
    if byte_order is not None:
        updates["byte_order"] = byte_order
    if is_signed is not None:
        updates["is_signed"] = is_signed
    if factor is not None:
        updates["factor"] = factor
    if offset is not None:
        updates["offset"] = offset
    if minimum is not None:
        updates["minimum"] = minimum
    if maximum is not None:
        updates["maximum"] = maximum
    if unit is not None:
        updates["unit"] = unit
    if receiver:
        updates["receivers"] = receiver
    if comment is not None:
        updates["comment"] = comment
    if multiplex is not None:
        updates["multiplex_indicator"] = multiplex
    if not updates:
        err_console.print("[red]No update fields provided.[/red]")
        raise typer.Exit(1)
    db = _load(db_path)
    db2 = db.message(int(arb_id, 0)).update_signal(signal_name, **updates)
    dbckit.save(db2, db_path)
    console.print(f"[blue]Updated signal {signal_name}[/blue]")


@sig_app.command("rename")
def sig_rename(
    db_path: Path = _DB_OPT,
    arb_id: str = typer.Argument(...),
    signal_name: str = typer.Argument(...),
    new_name: str = typer.Argument(...),
):
    """[blue]Rename a signal.[/blue]"""
    db = _load(db_path)
    db2 = db.message(int(arb_id, 0)).signal(signal_name).rename(new_name)
    dbckit.save(db2, db_path)
    console.print(f"[blue]Renamed {signal_name} → {new_name}[/blue]")


@sig_app.command("add-choice")
def sig_add_choice(
    db_path: Path = _DB_OPT,
    arb_id: str = typer.Argument(...),
    signal_name: str = typer.Argument(...),
    value: int = typer.Argument(..., help="Integer value."),
    label: str = typer.Argument(..., help="Label string."),
):
    """[blue]Add a value-description (choice) to a signal.[/blue]"""
    db = _load(db_path)
    db2 = db.message(int(arb_id, 0)).signal(signal_name).add_choice(value, label)
    dbckit.save(db2, db_path)
    console.print(f"[blue]Added choice {value} = {label!r}[/blue]")


@sig_app.command("remove-choice")
def sig_remove_choice(
    db_path: Path = _DB_OPT,
    arb_id: str = typer.Argument(...),
    signal_name: str = typer.Argument(...),
    value: int = typer.Argument(..., help="Integer value to remove."),
):
    """[blue]Remove a value-description from a signal.[/blue]"""
    db = _load(db_path)
    db2 = db.message(int(arb_id, 0)).signal(signal_name).remove_choice(value)
    dbckit.save(db2, db_path)
    console.print(f"[blue]Removed choice {value}[/blue]")


# ═══════════════════════════════════════════════════════════════════════════════
# node commands
# ═══════════════════════════════════════════════════════════════════════════════

@node_app.command("list")
def node_list(db_path: Path = _DB_OPT, output: str = _OUT_OPT):
    """[green]List all nodes.[/green]"""
    db = _load(db_path)
    if _out_format(output) == "json":
        _print_json(list(db.nodes.values()))
        return
    if _out_format(output) == "csv":
        _print_csv([
            {"name": node.name, "comment": node.comment or ""}
            for node in db.nodes.values()
        ])
        return
    t = Table(title="Nodes")
    t.add_column("Name", style="cyan")
    t.add_column("Comment")
    for node in db.nodes.values():
        t.add_row(node.name, node.comment or "")
    console.print(t)


@node_app.command("get")
def node_get(
    db_path: Path = _DB_OPT,
    name: str = typer.Argument(...),
    output: str = _OUT_OPT,
):
    """[green]Show details for one node.[/green]"""
    db = _load(db_path)
    node = db.nodes.get(name)
    if node is None:
        err_console.print(f"[red]Node '{name}' not found.[/red]")
        raise typer.Exit(1)
    if _out_format(output) == "json":
        _print_json(node)
        return
    if _out_format(output) == "csv":
        _print_csv([{
            "name": node.name,
            "comment": node.comment or "",
            "attributes": json.dumps(node.attributes),
        }])
        return
    console.print(f"[bold]{node.name}[/bold]")
    console.print(f"  Comment: {node.comment or '(none)'}")
    console.print(f"  Attributes: {json.dumps(node.attributes) if node.attributes else '{}'}")


@node_app.command("create")
def node_create(
    db_path: Path = _DB_OPT,
    name: str = typer.Argument(...),
    comment: Optional[str] = typer.Option(None, "--comment"),
):
    """[blue]Add a new node.[/blue]"""
    db = _load(db_path)
    db2 = db.add_node(Node(name=name, comment=comment))
    dbckit.save(db2, db_path)
    console.print(f"[blue]Added node {name}[/blue]")


@node_app.command("delete")
def node_delete(db_path: Path = _DB_OPT, name: str = typer.Argument(...)):
    """[blue]Delete a node.[/blue]"""
    db = _load(db_path)
    db2 = db.node(name).delete()
    dbckit.save(db2, db_path)
    console.print(f"[blue]Deleted node {name}[/blue]")


@node_app.command("rename")
def node_rename(
    db_path: Path = _DB_OPT,
    name: str = typer.Argument(...),
    new_name: str = typer.Argument(...),
):
    """[blue]Rename a node.[/blue]"""
    db = _load(db_path)
    db2 = db.node(name).rename(new_name)
    dbckit.save(db2, db_path)
    console.print(f"[blue]Renamed {name} → {new_name}[/blue]")


# ═══════════════════════════════════════════════════════════════════════════════
# attribute commands
# ═══════════════════════════════════════════════════════════════════════════════

@attr_app.command("list")
def attr_list(db_path: Path = _DB_OPT, output: str = _OUT_OPT):
    """[green]List attribute definitions.[/green]"""
    db = _load(db_path)
    if _out_format(output) == "json":
        _print_json(list(db.attributes.values()))
        return
    if _out_format(output) == "csv":
        _print_csv([
            {
                "name": ad.name,
                "kind": ad.kind.value,
                "scope": ad.object_type or "DB",
                "minimum": ad.minimum if ad.minimum is not None else "",
                "maximum": ad.maximum if ad.maximum is not None else "",
                "default": ad.default if ad.default is not None else "",
            }
            for ad in db.attributes.values()
        ])
        return
    t = Table(title="Attribute Definitions")
    t.add_column("Name", style="cyan")
    t.add_column("Kind")
    t.add_column("Scope")
    t.add_column("Default")
    for ad in db.attributes.values():
        t.add_row(ad.name, ad.kind.value, ad.object_type or "DB", str(ad.default))
    console.print(t)


@attr_app.command("get")
def attr_get(
    db_path: Path = _DB_OPT,
    name: str = typer.Argument(...),
    output: str = _OUT_OPT,
):
    """[green]Show details for one attribute definition.[/green]"""
    db = _load(db_path)
    attr = db.attributes.get(name)
    if attr is None:
        err_console.print(f"[red]Attribute '{name}' not found.[/red]")
        raise typer.Exit(1)
    if _out_format(output) == "json":
        _print_json(attr)
        return
    if _out_format(output) == "csv":
        _print_csv([{
            "name": attr.name,
            "kind": attr.kind.value,
            "scope": attr.object_type or "DB",
            "minimum": attr.minimum if attr.minimum is not None else "",
            "maximum": attr.maximum if attr.maximum is not None else "",
            "default": attr.default if attr.default is not None else "",
            "values": ",".join(attr.values),
        }])
        return
    console.print(f"[bold]{attr.name}[/bold]")
    console.print(f"  Kind: {attr.kind.value}")
    console.print(f"  Scope: {attr.object_type or 'DB'}")
    console.print(f"  Range: {attr.minimum} .. {attr.maximum}")
    console.print(f"  Default: {attr.default!r}")
    if attr.values:
        console.print(f"  Enum values: {', '.join(attr.values)}")


@attr_app.command("define")
def attr_define(
    db_path: Path = _DB_OPT,
    name: str = typer.Argument(..., help="Attribute name."),
    kind: AttributeKind = typer.Argument(..., help="Attribute kind."),
    scope: str = typer.Option("DB", "--scope", help="One of DB, BU_, BO_, SG_, EV_."),
    minimum: Optional[float] = typer.Option(None, "--minimum", help="Minimum numeric value."),
    maximum: Optional[float] = typer.Option(None, "--maximum", help="Maximum numeric value."),
    default: Optional[str] = typer.Option(None, "--default", help="Default attribute value."),
    enum_value: list[str] = typer.Option([], "--enum-value", help="Enum option. Repeat as needed."),
):
    """[blue]Define or update an attribute definition.[/blue]"""
    object_type = "" if scope == "DB" else scope
    definition = AttributeDefinition(
        name=name,
        kind=kind,
        object_type=object_type,
        minimum=minimum,
        maximum=maximum,
        values=enum_value,
        default=_parse_attr_value(default, kind) if default is not None else None,
    )
    db = _load(db_path)
    db2 = db.define_attribute(definition)
    dbckit.save(db2, db_path)
    console.print(f"[blue]Defined attribute {name}[/blue]")


@attr_app.command("set")
def attr_set(
    db_path: Path = _DB_OPT,
    target: str = typer.Argument(..., help="Target: '', 'node:ECU1', 'message:0x1F4', 'signal:0x1F4:Speed'"),
    name: str = typer.Argument(..., help="Attribute name."),
    value: str = typer.Argument(..., help="Value (string)."),
):
    """[blue]Set an attribute value.[/blue]"""
    db = _load(db_path)
    db2 = _set_attribute_target(db, target, name, value)
    dbckit.save(db2, db_path)
    console.print(f"[blue]Set {name}={value!r} on {target or 'DB'}[/blue]")


@attr_app.command("unset")
def attr_unset(
    db_path: Path = _DB_OPT,
    target: str = typer.Argument(...),
    name: str = typer.Argument(...),
):
    """[blue]Remove an attribute value.[/blue]"""
    db = _load(db_path)
    db2 = _unset_attribute_target(db, target, name)
    dbckit.save(db2, db_path)
    console.print(f"[blue]Unset {name} on {target or 'DB'}[/blue]")


@attr_app.command("delete")
def attr_delete(db_path: Path = _DB_OPT, name: str = typer.Argument(...)):
    """[blue]Delete an attribute definition and all its values.[/blue]"""
    db = _load(db_path)
    db2 = db.delete_attribute(name)
    dbckit.save(db2, db_path)
    console.print(f"[blue]Deleted attribute '{name}'[/blue]")


# ═══════════════════════════════════════════════════════════════════════════════
# decode commands
# ═══════════════════════════════════════════════════════════════════════════════

@decode_app.command("frame")
def decode_frame_cmd(
    db_path: Path = _DB_OPT,
    arb_id: str = typer.Argument(..., help="Arbitration ID (hex or decimal)."),
    hex_data: str = typer.Argument(..., help="Frame bytes as hex string."),
    output: str = _OUT_OPT,
):
    """[yellow]Decode a CAN frame payload.[/yellow]"""
    db = _load(db_path)
    data = bytes.fromhex(hex_data)
    values = dbckit.decode_frame(db, int(arb_id, 0), data)
    if _out_format(output) == "json":
        _print_json(values)
        return
    t = Table(title=f"Decoded frame {arb_id}")
    t.add_column("Signal", style="cyan")
    t.add_column("Value")
    for name, val in values.items():
        t.add_row(name, str(val))
    console.print(t)


@decode_app.command("signal")
def decode_signal_cmd(
    db_path: Path = _DB_OPT,
    arb_id: str = typer.Argument(...),
    signal_name: str = typer.Argument(...),
    hex_data: str = typer.Argument(...),
):
    """[yellow]Decode a single signal from frame bytes.[/yellow]"""
    db = _load(db_path)
    msg = _require_msg(db, arb_id)
    sig = _require_sig(msg, signal_name)
    val = dbckit.decode_signal(bytes.fromhex(hex_data), sig)
    console.print(f"{signal_name} = [yellow]{val}[/yellow] {sig.unit}")


@decode_app.command("log")
def decode_log_cmd(
    db_path: Path = _DB_OPT,
    log_path: Path = typer.Argument(..., help="Path to a supported CAN log file."),
    output: str = _OUT_OPT,
    limit: int = typer.Option(0, "--limit", help="Max frames to output (0 = all)."),
    format_: str | None = typer.Option(
        None,
        "--format",
        help="Reader format override, with or without a leading dot.",
    ),
    match: str = typer.Option(
        "exact",
        "--match",
        help="Message resolution mode: exact, j1939, or auto.",
    ),
):
    """[yellow]Decode frames from a CAN log file.[/yellow]"""
    match_mode = _frame_match_mode(match)
    db = _load(db_path)
    count = 0
    for frame in dbckit.decode_log(
        db,
        log_path,
        format=format_,
        match=match_mode,
    ):
        if _out_format(output) == "json":
            _print_json(frame)
        elif isinstance(frame, dbckit.AmbiguousFrameMatch):
            candidates = ", ".join(
                f"{candidate:#x}" for candidate in frame.candidate_message_ids
            )
            console.print(
                f"[cyan]{frame.timestamp:.6f}[/cyan] "
                f"[bold]{frame.arbitration_id:#x}[/bold]: "
                f"[yellow]ambiguous J1939 match[/yellow] "
                f"(candidates: {candidates})"
            )
        else:
            message_ref = f"[bold]{frame.arbitration_id:#x}[/bold]"
            if frame.message_arbitration_id != frame.arbitration_id:
                message_ref += f" → [bold]{frame.message_arbitration_id:#x}[/bold]"
            console.print(
                f"[cyan]{frame.timestamp:.6f}[/cyan] "
                f"{message_ref}: "
                + ", ".join(f"{k}={v}" for k, v in frame.signals.items())
            )
        count += 1
        if limit and count >= limit:
            break


# ═══════════════════════════════════════════════════════════════════════════════
# encode commands
# ═══════════════════════════════════════════════════════════════════════════════

@encode_app.command("frame")
def encode_frame_cmd(
    db_path: Path = _DB_OPT,
    arb_id: str = typer.Argument(..., help="Arbitration ID (hex or decimal)."),
    kv: list[str] = typer.Argument(..., help="Signal=value pairs, e.g. Speed=100.0"),
):
    """[yellow]Encode signal values into a CAN frame payload.[/yellow]"""
    db = _load(db_path)
    values = {}
    for item in kv:
        k, _, v = item.partition("=")
        values[k.strip()] = float(v.strip())
    raw = dbckit.encode_frame(db, int(arb_id, 0), values)
    console.print(f"[yellow]{raw.hex().upper()}[/yellow]")


# ═══════════════════════════════════════════════════════════════════════════════
# codegen commands
# ═══════════════════════════════════════════════════════════════════════════════

def _codegen_cmd(target: str):
    def _cmd(
        db_path: Path = _DB_OPT,
        out: Optional[Path] = typer.Option(None, "--out", help="Output file path."),
    ):
        db = _load(db_path)
        result = dbckit.codegen(db, target)  # type: ignore[arg-type]
        if out:
            out.write_text(result, encoding="utf-8")
            console.print(f"[magenta]Written to {out}[/magenta]")
        else:
            console.print(result)
    _cmd.__doc__ = f"[magenta]Generate {target} code/docs.[/magenta]"
    return _cmd


codegen_app.command("c")(_codegen_cmd("c"))
codegen_app.command("python")(_codegen_cmd("python"))
codegen_app.command("markdown")(_codegen_cmd("markdown"))
codegen_app.command("json-schema")(_codegen_cmd("json-schema"))


# ═══════════════════════════════════════════════════════════════════════════════
# helpers
# ═══════════════════════════════════════════════════════════════════════════════

def _require_msg(db: dbckit.Database, arb_id: str):
    msg = db.messages.get(int(arb_id, 0))
    if msg is None:
        err_console.print(f"[red]Message {arb_id} not found.[/red]")
        raise typer.Exit(1)
    return msg


def _require_sig(msg, name: str):
    sig = msg.signals.get(name)
    if sig is None:
        err_console.print(f"[red]Signal '{name}' not found in '{msg.name}'.[/red]")
        raise typer.Exit(1)
    return sig


def _set_attribute_target(db: dbckit.Database, target: str, name: str, value: str) -> dbckit.Database:
    parsed_value = _parse_attr_value(value, db.attributes[name].kind) if name in db.attributes else value
    if not target:
        from dbckit.mutations.attribute import set_database_attribute  # noqa: PLC0415
        return set_database_attribute(db, name, parsed_value)

    kind, _, rest = target.partition(":")
    if kind == "node":
        return db.node(rest).set_attribute(name, parsed_value)
    if kind == "message":
        return db.message(int(rest, 0)).set_attribute(name, parsed_value)
    if kind == "signal":
        msg_id, _, signal_name = rest.partition(":")
        return db.message(int(msg_id, 0)).signal(signal_name).set_attribute(name, parsed_value)
    err_console.print(f"[red]Unsupported target '{target}'.[/red]")
    raise typer.Exit(1)


def _unset_attribute_target(db: dbckit.Database, target: str, name: str) -> dbckit.Database:
    if not target:
        from dbckit.mutations.attribute import unset_database_attribute  # noqa: PLC0415
        return unset_database_attribute(db, name)

    kind, _, rest = target.partition(":")
    if kind == "node":
        return db.node(rest).unset_attribute(name)
    if kind == "message":
        return db.message(int(rest, 0)).unset_attribute(name)
    if kind == "signal":
        msg_id, _, signal_name = rest.partition(":")
        return db.message(int(msg_id, 0)).signal(signal_name).unset_attribute(name)
    err_console.print(f"[red]Unsupported target '{target}'.[/red]")
    raise typer.Exit(1)


def _print_signals_table(msg) -> None:
    t = Table(title=f"Signals in {msg.name}")
    t.add_column("Name", style="cyan")
    t.add_column("Bits")
    t.add_column("Order")
    t.add_column("Factor")
    t.add_column("Offset")
    t.add_column("Unit")
    t.add_column("Mux")
    for sig in msg.signals.values():
        bo = "Intel" if sig.byte_order == ByteOrder.little_endian else "Motorola"
        t.add_row(
            sig.name,
            f"{sig.start_bit}|{sig.length}",
            bo,
            str(sig.factor),
            str(sig.offset),
            sig.unit or "-",
            sig.multiplex_indicator or "",
        )
    console.print(t)


def _parse_attr_value(raw: str, kind: AttributeKind):
    if kind == AttributeKind.STRING:
        return raw
    if kind == AttributeKind.ENUM:
        return raw
    if kind == AttributeKind.FLOAT:
        return float(raw)
    return int(raw, 0)


def _render_bit_grid(msg, slots) -> None:
    """Render an 8-column bit grid using Rich."""
    from rich.text import Text

    # Assign a color per signal name
    colors = ["cyan", "green", "yellow", "blue", "magenta", "red", "bright_cyan", "bright_green"]
    sig_colors: dict[str, str] = {}
    idx = 0
    for slot in slots:
        if slot.signal_name and slot.signal_name not in sig_colors:
            sig_colors[slot.signal_name] = colors[idx % len(colors)]
            idx += 1

    t = Table(title=f"Bit Layout: {msg.name}", show_header=True, show_lines=True)
    t.add_column("Byte", style="dim")
    for bit_in_byte in range(7, -1, -1):
        t.add_column(f"b{bit_in_byte}", justify="center")

    for byte_idx in range(msg.length):
        row: list[str | Text] = [str(byte_idx)]
        for bit_in_byte in range(7, -1, -1):
            linear_bit = byte_idx * 8 + bit_in_byte
            slot = slots[linear_bit] if linear_bit < len(slots) else None
            if slot and slot.signal_name:
                color = sig_colors.get(slot.signal_name, "white")
                abbrev = slot.signal_name[:3]
                row.append(Text(abbrev, style=color))
            else:
                row.append(Text("···", style="dim"))
        t.add_row(*row)

    console.print(t)
    if sig_colors:
        console.print("Legend:")
        for name, color in sig_colors.items():
            console.print(f"  [{color}]■[/{color}] {name}")
