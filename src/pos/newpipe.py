"""Read watch progress out of a NewPipe database export.

NewPipe (Settings -> Backup and restore -> Export database) writes a zip with
`newpipe.db`, a Room/SQLite database. The tables used here are `streams`
(uid, url, duration in seconds), `stream_history` (stream_id) and
`stream_state` (stream_id, progress_time in milliseconds). Column names are
checked at run time and anything missing degrades to "no signal", never to an
error that would delete files."""
from __future__ import annotations

import os
import re
import sqlite3
import tempfile
import zipfile

# PeerTube video URLs: /w/<shortUUID>, /videos/watch/<uuid>, /videos/embed/<id>
_ID = re.compile(r"/(?:w|videos/watch|videos/embed)/([A-Za-z0-9-]+)")


def video_id(url: str) -> str | None:
    m = _ID.search(url or "")
    return m.group(1) if m else None


def watched_ids(zip_path: str, fraction: float = 0.9) -> set[str]:
    """PeerTube ids (uuid or shortUUID, whatever the URL carried) that NewPipe
    shows as watched: in the history and progress >= fraction of duration."""
    with tempfile.TemporaryDirectory() as td:
        with zipfile.ZipFile(zip_path) as z:
            if "newpipe.db" not in z.namelist():
                return set()
            z.extract("newpipe.db", td)
        db = sqlite3.connect("file:" + os.path.join(td, "newpipe.db") + "?mode=ro", uri=True)
        try:
            cols = {r[1] for r in db.execute("PRAGMA table_info(streams)")}
            if not {"uid", "url", "duration"} <= cols:
                return set()
            rows = db.execute(
                """SELECT s.url, s.duration, COALESCE(st.progress_time, 0)
                   FROM stream_history h
                   JOIN streams s ON s.uid = h.stream_id
                   LEFT JOIN stream_state st ON st.stream_id = s.uid"""
            ).fetchall()
        except sqlite3.Error:
            return set()
        finally:
            db.close()
    out = set()
    for url, duration, progress_ms in rows:
        vid = video_id(url)
        if vid and duration and progress_ms / 1000.0 >= duration * fraction:
            out.add(vid)
    return out
