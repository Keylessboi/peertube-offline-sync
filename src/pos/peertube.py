"""Minimal PeerTube REST client (public listing, optional OAuth for history)."""
from __future__ import annotations

from urllib.parse import urlparse

import requests


def pick_file(video: dict, max_height: int) -> dict | None:
    """Best single-file rendition not taller than max_height.

    Prefers web-video files; falls back to HLS files, which PeerTube also
    exposes as one fragmented mp4 each. Falls back to the smallest file when
    everything is taller than max_height."""
    files = list(video.get("files") or [])
    if not files:
        for pl in video.get("streamingPlaylists") or []:
            files.extend(pl.get("files") or [])
    files = [f for f in files if f.get("fileDownloadUrl") or f.get("fileUrl")]
    if not files:
        return None
    fits = [f for f in files if (f.get("resolution") or {}).get("id", 0) <= max_height]
    if fits:
        return max(fits, key=lambda f: f["resolution"]["id"])
    return min(files, key=lambda f: f["resolution"]["id"])


def rebase(url: str, base: str) -> str:
    """Put a file URL's path onto our in-cluster base URL."""
    p = urlparse(url)
    return base.rstrip("/") + p.path + (("?" + p.query) if p.query else "")


class PeerTube:
    def __init__(self, base: str, session: requests.Session | None = None):
        self.base = base.rstrip("/")
        self.s = session or requests.Session()
        self.s.headers["User-Agent"] = "peertube-offline-sync/0.1"

    def channel_videos(self, handle: str, count: int) -> list[dict]:
        r = self.s.get(
            f"{self.base}/api/v1/video-channels/{handle}/videos",
            params={"count": count, "sort": "-publishedAt", "skipCount": "true"},
            timeout=30,
        )
        r.raise_for_status()
        return r.json().get("data", [])

    def video(self, uuid: str) -> dict:
        r = self.s.get(f"{self.base}/api/v1/videos/{uuid}", timeout=30)
        r.raise_for_status()
        return r.json()

    def download(self, url: str, dest: str) -> int:
        n = 0
        with self.s.get(rebase(url, self.base), stream=True, timeout=(15, 120)) as r:
            r.raise_for_status()
            with open(dest, "wb") as fh:
                for chunk in r.iter_content(1 << 20):
                    fh.write(chunk)
                    n += len(chunk)
        return n

    def login(self, user: str, password: str) -> None:
        c = self.s.get(f"{self.base}/api/v1/oauth-clients/local", timeout=30)
        c.raise_for_status()
        c = c.json()
        r = self.s.post(
            f"{self.base}/api/v1/users/token",
            data={
                "client_id": c["client_id"],
                "client_secret": c["client_secret"],
                "grant_type": "password",
                "response_type": "code",
                "username": user,
                "password": password,
            },
            timeout=30,
        )
        r.raise_for_status()
        self.s.headers["Authorization"] = "Bearer " + r.json()["access_token"]

    def history(self, count: int = 100) -> list[dict]:
        r = self.s.get(f"{self.base}/api/v1/users/me/history/videos", params={"count": count}, timeout=30)
        r.raise_for_status()
        return r.json().get("data", [])


def watched_from_history(items: list[dict], fraction: float) -> set[str]:
    """UUIDs from PeerTube history whose playback passed `fraction` of duration."""
    out = set()
    for it in items:
        dur = it.get("duration") or 0
        pos = (it.get("userHistory") or {}).get("currentTime", 0)
        if dur and pos >= dur * fraction:
            out.add(it["uuid"])
    return out
