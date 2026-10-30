"""One reconcile pass. Run it from a CronJob; it is idempotent.

Order matters: reconcile the phone side first (a file deleted on the phone
means "done"), then apply watch signals (delete what was watched), then fetch
new videos, then enforce retention."""
from __future__ import annotations

import logging
import os
import re
import sys
import time
from datetime import datetime, timedelta, timezone

from . import newpipe
from .config import Config
from .peertube import PeerTube, pick_file, watched_from_history
from .state import State
from .webdav import Dav

log = logging.getLogger("pos")
NEWPIPE_DIR = "_newpipe"  # drop NewPipe database exports here


def safe(name: str) -> str:
    name = re.sub(r'[\\/:*?"<>|\x00-\x1f]', "_", name).strip(" .")
    return name[:120] or "video"


def remote_path(cfg: Config, channel: str, title: str, short_uuid: str) -> str:
    return f"{cfg.dav_folder}/{safe(channel)}/{safe(title)} [{short_uuid}].mp4"


def reconcile_phone(cfg: Config, st: State, dav: Dav) -> int:
    """A tracked file that vanished from the folder was deleted on the phone."""
    try:
        present = set(dav.list(cfg.dav_folder))
    except Exception as e:  # listing failure must never look like "all deleted"
        log.warning("listing failed, skipping reconcile: %s", e)
        return 0
    prefix = cfg.dav_folder + "/"
    present = {prefix + p for p in present}
    if not present:  # empty listing is indistinguishable from an outage
        return 0
    n = 0
    for row in st.by_status("downloaded"):
        if row["remote_path"] not in present:
            st.set_status(row["uuid"], "deleted", "removed on phone")
            n += 1
    return n


def watched_ids(cfg: Config, pt: PeerTube, dav: Dav, tmp: str) -> set[str]:
    ids: set[str] = set()
    if cfg.peertube_user:
        try:
            pt.login(cfg.peertube_user, cfg.peertube_password)
            ids |= watched_from_history(pt.history(), cfg.watched_fraction)
        except Exception as e:
            log.warning("PeerTube history unavailable: %s", e)
    try:
        exports = sorted(p for p in dav.list(f"{cfg.dav_folder}/{NEWPIPE_DIR}") if p.endswith(".zip"))
        if exports:
            local = os.path.join(tmp, "newpipe.zip")
            dav.get(f"{cfg.dav_folder}/{NEWPIPE_DIR}/{exports[-1]}", local)  # names sort by date
            ids |= newpipe.watched_ids(local, cfg.watched_fraction)
    except Exception as e:
        log.warning("NewPipe export unavailable: %s", e)
    return ids


def delete_watched(cfg: Config, st: State, dav: Dav, ids: set[str]) -> int:
    n = 0
    for row in st.by_status("downloaded"):
        if row["uuid"] in ids or row["short_uuid"] in ids:
            log.info("watched, deleting %s", row["remote_path"])
            if not cfg.dry_run:
                dav.delete(row["remote_path"])
                st.set_status(row["uuid"], "deleted", "watched")
            n += 1
    return n


def fetch_new(cfg: Config, st: State, pt: PeerTube, dav: Dav, tmp: str) -> int:
    cutoff = datetime.now(timezone.utc) - timedelta(days=cfg.max_age_days)
    done = 0
    for handle in cfg.channels:
        try:
            vids = pt.channel_videos(handle, cfg.per_channel)
        except Exception as e:
            log.warning("channel %s: %s", handle, e)
            continue
        for v in reversed(vids):  # oldest first, so a cap drops the newest last
            if done >= cfg.max_downloads_per_run:
                return done
            if st.known(v["uuid"]):
                continue
            pub = datetime.fromisoformat(v["publishedAt"].replace("Z", "+00:00"))
            if pub < cutoff:
                continue
            try:
                detail = pt.video(v["uuid"])
                f = pick_file(detail, cfg.max_height)
                if not f:
                    log.info("no downloadable file yet for %s", v["uuid"])
                    continue  # still transcoding: try next run
                path = remote_path(cfg, handle.split("@")[0], v["name"], v.get("shortUUID", v["uuid"]))
                log.info("fetching %s -> %s", v["name"], path)
                if cfg.dry_run:
                    done += 1
                    continue
                local = os.path.join(tmp, "dl.mp4")
                pt.download(f.get("fileDownloadUrl") or f["fileUrl"], local)
                dav.mkdirs(path.rsplit("/", 1)[0])
                dav.put(path, local)
                os.unlink(local)
                st.add(v["uuid"], v.get("shortUUID", ""), handle, v["name"], v.get("duration", 0), path)
                done += 1
            except Exception as e:
                log.warning("video %s failed, will retry next run: %s", v["uuid"], e)
    return done


def expire(cfg: Config, st: State, dav: Dav) -> int:
    n = 0
    limit = time.time() - cfg.keep_days * 86400
    for row in st.by_status("downloaded"):
        if row["fetched_at"] < limit:
            log.info("expired, deleting %s", row["remote_path"])
            if not cfg.dry_run:
                dav.delete(row["remote_path"])
                st.set_status(row["uuid"], "deleted", "expired")
            n += 1
    return n


def run(cfg: Config) -> dict:
    if not cfg.dav_base:
        raise SystemExit("POS_DAV_BASE is required")
    os.makedirs(cfg.tmp_dir, exist_ok=True)
    st = State(cfg.state_dir)
    pt = PeerTube(cfg.peertube_url)
    dav = Dav(cfg.dav_base, cfg.dav_user, cfg.dav_password)
    if not cfg.channels:
        log.warning("POS_CHANNELS is empty: nothing will be fetched")
    gone = reconcile_phone(cfg, st, dav)
    deleted = delete_watched(cfg, st, dav, watched_ids(cfg, pt, dav, cfg.tmp_dir))
    fetched = fetch_new(cfg, st, pt, dav, cfg.tmp_dir)
    expired = expire(cfg, st, dav)
    return {"removed_on_phone": gone, "deleted_watched": deleted, "fetched": fetched, "expired": expired}


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    log.info("done: %s", run(Config.from_env()))


if __name__ == "__main__":
    sys.exit(main())
