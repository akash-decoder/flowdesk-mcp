"""Workflow definitions and atomic execution shared by the web and MCP adapters."""
import hashlib
import json
import os
import re
import secrets
import sqlite3
import uuid
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, StringConstraints

Name = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=100)]
FieldName = Annotated[str, StringConstraints(pattern=r"^[A-Za-z_][A-Za-z0-9_]{0,63}$")]
ShortText = Annotated[str, StringConstraints(max_length=2048)]


class Strict(BaseModel):
    model_config = ConfigDict(extra="forbid")


class Filter(Strict):
    kind: Literal["filter"]
    field: FieldName
    equals: ShortText


class SetField(Strict):
    kind: Literal["set"]
    field: FieldName
    template: ShortText


class Store(Strict):
    kind: Literal["record"]


class Deliver(Strict):
    kind: Literal["deliver"]
    destination: FieldName


Step = Annotated[Filter | SetField | Store | Deliver, Field(discriminator="kind")]


class Workflow(Strict):
    name: Name
    steps: list[Step] = Field(min_length=1, max_length=24)


def now():
    return datetime.now(timezone.utc).isoformat(timespec="milliseconds")


def encode(value):
    return json.dumps(value, ensure_ascii=False, allow_nan=False, separators=(",", ":"))


@contextmanager
def database():
    path = Path(os.getenv("FLOWDESK_DB", "~/.flowdesk/workspace.sqlite3")).expanduser()
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    db = sqlite3.connect(path, timeout=10)
    db.row_factory = sqlite3.Row
    try:
        with db:
            yield db
    finally:
        db.close()


def initialize():
    with database() as db:
        db.execute("PRAGMA journal_mode=WAL")
        db.executescript("""
          CREATE TABLE IF NOT EXISTS flows (
            id TEXT PRIMARY KEY, name TEXT, steps TEXT, secret TEXT, revision INTEGER);
          CREATE TABLE IF NOT EXISTS runs (
            id TEXT PRIMARY KEY, flow TEXT, revision INTEGER, at TEXT, status TEXT,
            event TEXT, fingerprint TEXT, result TEXT, UNIQUE(flow,event));
          CREATE INDEX IF NOT EXISTS runs_by_flow ON runs(flow,at);
          CREATE TABLE IF NOT EXISTS records (
            id INTEGER PRIMARY KEY, run TEXT, flow TEXT, data TEXT);
          CREATE TABLE IF NOT EXISTS deliveries (
            id TEXT PRIMARY KEY, run TEXT, destination TEXT, data TEXT,
            status TEXT, detail TEXT, claimed REAL);
        """)


def unpack(row):
    return dict(id=row["id"], name=row["name"], steps=json.loads(row["steps"]),
                revision=row["revision"])


def workflows():
    with database() as db:
        return [unpack(row) for row in db.execute("SELECT * FROM flows ORDER BY name,id")]


def lookup(db, flow_id):
    row = db.execute("SELECT * FROM flows WHERE id=?", (flow_id,)).fetchone()
    if row is None:
        raise KeyError("Workflow not found")
    return row


class Conflict(ValueError):
    pass


def save(definition, flow_id=None, revision=None):
    if flow_id is not None and (type(revision) is not int or revision < 1):
        raise ValueError("Expected a positive integer revision")
    with database() as db:
        steps = encode(definition.model_dump()["steps"])
        if flow_id is None:
            flow_id = uuid.uuid4().hex
            db.execute("INSERT INTO flows VALUES(?,?,?,?,1)",
                       (flow_id, definition.name, steps, secrets.token_urlsafe(32)))
        else:
            updated = db.execute(
                "UPDATE flows SET name=?,steps=?,revision=revision+1 WHERE id=? AND revision=?",
                (definition.name, steps, flow_id, revision))
            if not updated.rowcount:
                lookup(db, flow_id)
                raise Conflict("Workflow changed. Reload the saved version before editing.")
        return unpack(lookup(db, flow_id))


def render(template, data):
    def replace(match):
        key = match.group(1)
        if key not in data:
            raise ValueError(f"Missing field: {key}")
        value = data[key]
        return value if isinstance(value, str) else encode(value)
    result = re.sub(r"\{\{([A-Za-z_][A-Za-z0-9_]*)\}\}", replace, template)
    if len(result.encode()) > 65536:
        raise ValueError("Rendered field exceeds 64 KiB")
    return result


def simulate(definition, payload):
    if not isinstance(payload, dict) or len(encode(payload).encode()) > 65536:
        raise ValueError("Input must be a JSON object of at most 64 KiB")
    data, effects, trace = payload.copy(), [], []
    status = "completed"
    for index, step in enumerate(definition.steps, 1):
        entry = {"step": index, "kind": step.kind, "status": "ok"}
        trace.append(entry)
        try:
            if isinstance(step, Filter) and data.get(step.field) != step.equals:
                status = entry["status"] = "filtered"
                break
            if isinstance(step, SetField):
                data[step.field] = render(step.template, data)
                if len(encode(data).encode()) > 65536:
                    raise ValueError("Output exceeds 64 KiB")
            if isinstance(step, (Store, Deliver)):
                effects.append((step, encode(data)))
        except ValueError as exc:
            status = entry["status"] = "failed"
            entry["error"] = str(exc)
            break
    return {"status": status, "output": data, "trace": trace}, effects


def run(flow_id, payload, event_id=None, *, preview=False, hook_secret=None):
    if event_id is not None and (not isinstance(event_id, str) or not 1 <= len(event_id) <= 200):
        raise ValueError("Event ID must contain 1 to 200 characters")
    with database() as db:
        if not preview:
            db.execute("BEGIN IMMEDIATE")
        row = lookup(db, flow_id)
        if hook_secret is not None and not secrets.compare_digest(row["secret"].encode(), hook_secret.encode()):
            raise PermissionError("Invalid webhook key")
        fingerprint = hashlib.sha256(json.dumps(payload, sort_keys=True, allow_nan=False).encode()).hexdigest()
        if event_id and not preview:
            previous = db.execute("SELECT * FROM runs WHERE flow=? AND event=?", (flow_id, event_id)).fetchone()
            if previous:
                if previous["fingerprint"] != fingerprint:
                    raise Conflict("Event ID already used for another payload")
                return json.loads(previous["result"])
        definition = Workflow(name=row["name"], steps=json.loads(row["steps"]))
        result, effects = simulate(definition, payload)
        result.update(workflow_id=flow_id, revision=row["revision"])
        if preview:
            return result
        result.update(id=uuid.uuid4().hex, at=now())
        db.execute("INSERT INTO runs VALUES(?,?,?,?,?,?,?,?)",
                   (result["id"], flow_id, row["revision"], result["at"], result["status"],
                    event_id, fingerprint, encode(result)))
        if result["status"] == "completed":
            for step, snapshot in effects:
                if isinstance(step, Store):
                    db.execute("INSERT INTO records(run,flow,data) VALUES(?,?,?)",
                               (result["id"], flow_id, snapshot))
                else:
                    db.execute("INSERT INTO deliveries VALUES(?,?,?,?,'queued','',0)",
                               (uuid.uuid4().hex, result["id"], step.destination, snapshot))
        return result


def history(flow_id):
    with database() as db:
        lookup(db, flow_id)
        return [json.loads(r[0]) for r in db.execute(
            "SELECT result FROM runs WHERE flow=? ORDER BY rowid DESC LIMIT 50", (flow_id,))]


def records(flow_id):
    with database() as db:
        lookup(db, flow_id)
        return [dict(id=r["id"], run=r["run"], data=json.loads(r["data"])) for r in db.execute(
            "SELECT * FROM records WHERE flow=? ORDER BY id DESC LIMIT 100", (flow_id,))]


def deliveries(flow_id):
    with database() as db:
        lookup(db, flow_id)
        return [dict(r) for r in db.execute("""
            SELECT d.id,d.run,d.destination,d.status,d.detail FROM deliveries d
            JOIN runs r ON d.run=r.id WHERE r.flow=? ORDER BY d.rowid DESC LIMIT 100
        """, (flow_id,))]
