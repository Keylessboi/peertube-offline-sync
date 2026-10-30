"""Configuration, all from environment variables so a Kubernetes Secret and
ConfigMap can supply it without a config file format of our own."""
from __future__ import annotations

import os
from dataclasses import dataclass, field


def _int(name: str, default: int) -> int:
    return int(os.environ.get(name, default))


@dataclass
class Config:
    # PeerTube. Use the in-cluster service URL; file URLs the API returns carry
    # the public host and are rewritten onto this base.
    peertube_url: str = "http://peertube.peertube.svc.cluster.local:9000"
    # Optional account for watch history (OAuth password grant). Empty = skip.
    peertube_user: str = ""
    peertube_password: str = ""
    # Channel handles to mirror offline, e.g. "name@host" or "name". Never
    # defaulted: the list is the owner's choice.
    channels: list[str] = field(default_factory=list)

    # Nextcloud WebDAV target.
    dav_base: str = ""  # https://host/remote.php/dav/files/<user>
    dav_user: str = ""
    dav_password: str = ""  # an app password, not the login password
    dav_folder: str = "PeerTube"

    state_dir: str = "/state"
    tmp_dir: str = "/tmp/pos"

    max_height: int = 720  # biggest resolution to fetch
    max_age_days: int = 14  # ignore videos older than this on first sight
    per_channel: int = 5  # newest N per channel considered each run
    max_downloads_per_run: int = 5
    keep_days: int = 30  # hard retention ceiling, watched or not
    watched_fraction: float = 0.9  # progress/duration that counts as watched
    dry_run: bool = False

    @classmethod
    def from_env(cls) -> "Config":
        e = os.environ.get
        chans = [c.strip() for c in e("POS_CHANNELS", "").replace("\n", ",").split(",") if c.strip()]
        return cls(
            peertube_url=e("POS_PEERTUBE_URL", cls.peertube_url).rstrip("/"),
            peertube_user=e("POS_PEERTUBE_USER", ""),
            peertube_password=e("POS_PEERTUBE_PASSWORD", ""),
            channels=chans,
            dav_base=e("POS_DAV_BASE", "").rstrip("/"),
            dav_user=e("POS_DAV_USER", ""),
            dav_password=e("POS_DAV_PASSWORD", ""),
            dav_folder=e("POS_DAV_FOLDER", "PeerTube").strip("/"),
            state_dir=e("POS_STATE_DIR", "/state"),
            tmp_dir=e("POS_TMP_DIR", "/tmp/pos"),
            max_height=_int("POS_MAX_HEIGHT", 720),
            max_age_days=_int("POS_MAX_AGE_DAYS", 14),
            per_channel=_int("POS_PER_CHANNEL", 5),
            max_downloads_per_run=_int("POS_MAX_DOWNLOADS", 5),
            keep_days=_int("POS_KEEP_DAYS", 30),
            watched_fraction=float(e("POS_WATCHED_FRACTION", "0.9")),
            dry_run=e("POS_DRY_RUN", "") not in ("", "0", "false"),
        )
