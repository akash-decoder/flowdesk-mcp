"""Forward committed deliveries to operator-configured HTTPS receivers."""
import json
import os
import time
from urllib.parse import urlsplit

import httpx

from .engine import database


def targets():
    result = json.loads(os.getenv("FLOWDESK_TARGETS", "{}"))
    if not isinstance(result, dict):
        raise ValueError("FLOWDESK_TARGETS must be a JSON object")
    for name, url in result.items():
        parsed = urlsplit(url)
        if parsed.scheme != "https" or not parsed.hostname or parsed.username or parsed.fragment:
            raise ValueError(f"Invalid HTTPS destination for {name}")
    return result


def send_one(endpoints, client):
    with database() as db:
        db.execute("BEGIN IMMEDIATE")
        # A crash after sending leaves the outcome unknown. Never blindly replay it.
        db.execute("""UPDATE deliveries SET status='unknown', detail='Worker stopped before acknowledgement'
                      WHERE status='sending' AND claimed < ?""", (time.time() - 300,))
        row = db.execute("SELECT * FROM deliveries WHERE status='queued' ORDER BY rowid LIMIT 1").fetchone()
        if row is None:
            return False
        db.execute("UPDATE deliveries SET status='sending',claimed=? WHERE id=?", (time.time(), row["id"]))
    url = endpoints.get(row["destination"])
    status, detail = "failed", "Destination is not configured"
    if url:
        try:
            with client.stream("POST", url, content=row["data"].encode(), headers={
                "Content-Type": "application/json", "Idempotency-Key": row["id"]
            }) as response:
                status = "sent" if response.is_success else "failed"
                detail = f"HTTP {response.status_code}"
        except httpx.RequestError:
            status, detail = "unknown", "Transport error. Check the receiver before replaying."
    with database() as db:
        db.execute("UPDATE deliveries SET status=?,detail=? WHERE id=?", (status, detail, row["id"]))
    return True


def work():
    endpoints = targets()
    with httpx.Client(follow_redirects=False, timeout=10, trust_env=False) as client:
        while True:
            if not send_one(endpoints, client):
                time.sleep(1)
