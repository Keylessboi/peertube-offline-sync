"""SQLite ledger of what was fetched. SQLite is fine here: it lives on a
local-path volume, never NFS."""
from __future__ import annotations

import os
import sqlite3
import time

SCHEMA = """
CREATE TABLE IF NOT EXISTS videos (
  uuid TEXT PRIMARY KEY,
  short_uuid TEXT,
  channel TEXT,
  title TEXT,
  duration INTEGER,
  remote_path TEXT,
  status TEXT NOT NULL,        -- downloaded | watched | deleted
  reason TEXT,
  fetched_at REAL,
  updated_at REAL
);
"""


class State:
    def __init__(self, directory: str):
        os.makedirs(directory, exist_ok=True)
        self.db = sqlite3.connect(os.path.join(directory, "state.db"))
        self.db.row_factory = sqlite3.Row
        self.db.executescript(SCHEMA)

    def known(self, uuid: str) -> bool:
        return self.db.execute("SELECT 1 FROM videos WHERE uuid=?", (uuid,)).fetchone() is not None

    def add(self, uuid, short_uuid, channel, title, duration, remote_path):
        now = time.time()
        self.db.execute(
            "INSERT OR REPLACE INTO videos VALUES (?,?,?,?,?,?,?,?,?,?)",
            (uuid, short_uuid, channel, title, duration, remote_path, "downloaded", "", now, now),
        )
        self.db.commit()

    def set_status(self, uuid: str, status: str, reason: str = ""):
        self.db.execute(
            "UPDATE videos SET status=?, reason=?, updated_at=? WHERE uuid=?",
            (status, reason, time.time(), uuid),
        )
        self.db.commit()

    def by_status(self, status: str) -> list[sqlite3.Row]:
        return self.db.execute("SELECT * FROM videos WHERE status=?", (status,)).fetchall()
