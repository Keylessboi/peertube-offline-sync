"""JSON ledger of what was fetched.

A JSON file, not SQLite: the cluster keeps this on an NFS volume, where SQLite
locking is unsafe. One writer is guaranteed by the CronJob's
concurrencyPolicy: Forbid; writes are atomic (temp file + rename)."""
from __future__ import annotations

import json
import os
import time


class State:
    def __init__(self, directory: str):
        os.makedirs(directory, exist_ok=True)
        self.path = os.path.join(directory, "state.json")
        try:
            with open(self.path) as fh:
                self.rows: dict[str, dict] = json.load(fh)
        except FileNotFoundError:
            self.rows = {}

    def _save(self) -> None:
        tmp = self.path + ".tmp"
        with open(tmp, "w") as fh:
            json.dump(self.rows, fh, indent=1, sort_keys=True)
            fh.flush()
            os.fsync(fh.fileno())
        os.replace(tmp, self.path)

    def known(self, uuid: str) -> bool:
        return uuid in self.rows

    def add(self, uuid, short_uuid, channel, title, duration, remote_path):
        now = time.time()
        self.rows[uuid] = {
            "uuid": uuid, "short_uuid": short_uuid, "channel": channel, "title": title,
            "duration": duration, "remote_path": remote_path, "status": "downloaded",
            "reason": "", "fetched_at": now, "updated_at": now,
        }
        self._save()

    def set_status(self, uuid: str, status: str, reason: str = ""):
        self.rows[uuid].update(status=status, reason=reason, updated_at=time.time())
        self._save()

    def by_status(self, status: str) -> list[dict]:
        return [r for r in self.rows.values() if r["status"] == status]
