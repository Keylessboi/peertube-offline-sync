import sqlite3
import zipfile

from pos import newpipe
from pos.config import Config
from pos.peertube import pick_file, rebase, watched_from_history
from pos.state import State
from pos.sync import delete_watched, reconcile_phone, remote_path, safe


def f(res, url="https://x/f.mp4"):
    return {"resolution": {"id": res}, "fileDownloadUrl": url + str(res)}


def test_pick_file_prefers_highest_under_cap():
    assert pick_file({"files": [f(360), f(720), f(1080)]}, 720)["resolution"]["id"] == 720


def test_pick_file_falls_back_to_smallest_when_all_too_tall():
    assert pick_file({"files": [f(1080), f(2160)]}, 720)["resolution"]["id"] == 1080


def test_pick_file_uses_hls_files_when_no_web_video():
    v = {"files": [], "streamingPlaylists": [{"files": [f(480)]}]}
    assert pick_file(v, 720)["resolution"]["id"] == 480


def test_pick_file_none():
    assert pick_file({"files": []}, 720) is None


def test_rebase_keeps_path_drops_host():
    assert rebase("https://pt.example/download/a.mp4?x=1", "http://svc:9000") == "http://svc:9000/download/a.mp4?x=1"


def test_history_threshold():
    items = [
        {"uuid": "a", "duration": 100, "userHistory": {"currentTime": 95}},
        {"uuid": "b", "duration": 100, "userHistory": {"currentTime": 40}},
        {"uuid": "c", "duration": 0, "userHistory": {"currentTime": 10}},
    ]
    assert watched_from_history(items, 0.9) == {"a"}


def make_export(path, rows):
    db = path.parent / "newpipe.db"
    c = sqlite3.connect(db)
    c.executescript(
        "CREATE TABLE streams(uid INTEGER PRIMARY KEY,url TEXT,duration INTEGER);"
        "CREATE TABLE stream_history(stream_id INTEGER,access_date INTEGER);"
        "CREATE TABLE stream_state(stream_id INTEGER,progress_time INTEGER);"
    )
    for i, (url, dur, prog) in enumerate(rows, 1):
        c.execute("INSERT INTO streams VALUES (?,?,?)", (i, url, dur))
        c.execute("INSERT INTO stream_history VALUES (?,0)", (i,))
        if prog is not None:
            c.execute("INSERT INTO stream_state VALUES (?,?)", (i, prog))
    c.commit()
    c.close()
    with zipfile.ZipFile(path, "w") as z:
        z.write(db, "newpipe.db")


def test_newpipe_export(tmp_path):
    z = tmp_path / "export" / "NewPipeData.zip"
    z.parent.mkdir()
    make_export(z, [
        ("https://pt.example/w/shortA", 100, 95_000),
        ("https://pt.example/videos/watch/uuid-b", 100, 10_000),
        ("https://pt.example/w/noState", 100, None),
        ("https://youtube.com/watch?v=x", 100, 100_000),
    ])
    assert newpipe.watched_ids(str(z)) == {"shortA"}


def test_newpipe_bad_zip_has_no_signal(tmp_path):
    z = tmp_path / "e.zip"
    with zipfile.ZipFile(z, "w") as zf:
        zf.writestr("other", "x")
    assert newpipe.watched_ids(str(z)) == set()


class FakeDav:
    def __init__(self, listing):
        self.listing, self.deleted = listing, []

    def list(self, path):
        if isinstance(self.listing, Exception):
            raise self.listing
        return self.listing

    def delete(self, path):
        self.deleted.append(path)


def seeded(tmp_path):
    cfg = Config(dav_folder="PT", state_dir=str(tmp_path))
    st = State(str(tmp_path))
    p = remote_path(cfg, "chan", "T/1", "short1")
    st.add("u1", "short1", "chan@h", "T/1", 10, p)
    return cfg, st, p


def test_remote_path_sanitised():
    assert safe('a/b:c*') == "a_b_c_"


def test_watched_deletes_and_marks(tmp_path):
    cfg, st, p = seeded(tmp_path)
    dav = FakeDav([])
    assert delete_watched(cfg, st, dav, {"short1"}) == 1
    assert dav.deleted == [p] and st.by_status("deleted")


def test_dry_run_deletes_nothing(tmp_path):
    cfg, st, p = seeded(tmp_path)
    cfg.dry_run = True
    dav = FakeDav([])
    delete_watched(cfg, st, dav, {"u1"})
    assert dav.deleted == [] and st.by_status("downloaded")


def test_reconcile_marks_missing_file(tmp_path):
    cfg, st, p = seeded(tmp_path)
    assert reconcile_phone(cfg, st, FakeDav(["other/x.mp4"])) == 1


def test_reconcile_ignores_empty_or_failed_listing(tmp_path):
    cfg, st, p = seeded(tmp_path)
    assert reconcile_phone(cfg, st, FakeDav([])) == 0
    assert reconcile_phone(cfg, st, FakeDav(RuntimeError("down"))) == 0
    assert st.by_status("downloaded")
