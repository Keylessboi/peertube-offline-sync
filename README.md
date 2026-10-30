# peertube-offline-sync

Companion for a self-hosted PeerTube. One run does four things, in order:

1. A tracked file that vanished from the Nextcloud folder was deleted on the phone: mark it done.
2. Videos watched (PeerTube account history, or a NewPipe database export dropped in `<folder>/_newpipe/`) are deleted from the folder.
3. New videos from the configured channels are downloaded (best file <= `POS_MAX_HEIGHT`) and uploaded over WebDAV to the Nextcloud folder the phone keeps offline.
4. Anything older than `POS_KEEP_DAYS` is deleted.

Run it as a CronJob. Configuration is environment variables, see `src/pos/config.py`.
`POS_CHANNELS` (comma separated `name@host` handles) has no default: it is the owner's list.
`POS_DRY_RUN=1` logs what would happen and changes nothing.

    pip install -e '.[dev]' && pytest
