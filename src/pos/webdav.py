"""Just enough Nextcloud WebDAV: MKCOL, PUT, DELETE, PROPFIND (names only)."""
from __future__ import annotations

import xml.etree.ElementTree as ET
from urllib.parse import quote, unquote, urlparse

import requests


class Dav:
    def __init__(self, base: str, user: str, password: str):
        self.base = base.rstrip("/")
        self.s = requests.Session()
        self.s.auth = (user, password)

    def url(self, path: str) -> str:
        return self.base + "/" + quote(path.strip("/"))

    def mkdirs(self, path: str) -> None:
        cur = ""
        for part in [p for p in path.strip("/").split("/") if p]:
            cur += "/" + part
            r = self.s.request("MKCOL", self.url(cur), timeout=30)
            if r.status_code not in (201, 405):  # 405 = exists
                r.raise_for_status()

    def put(self, path: str, local: str) -> None:
        with open(local, "rb") as fh:
            r = self.s.put(self.url(path), data=fh, timeout=(15, 600))
        r.raise_for_status()

    def get(self, path: str, local: str) -> None:
        with self.s.get(self.url(path), stream=True, timeout=(15, 300)) as r:
            r.raise_for_status()
            with open(local, "wb") as fh:
                for chunk in r.iter_content(1 << 20):
                    fh.write(chunk)

    def delete(self, path: str) -> None:
        r = self.s.delete(self.url(path), timeout=30)
        if r.status_code != 404:
            r.raise_for_status()

    def list(self, path: str) -> list[str]:
        """Paths (relative to `path`) of everything below it, depth-first."""
        out: list[str] = []
        self._walk(path.strip("/"), "", out)
        return out

    def _walk(self, root: str, rel: str, out: list[str]) -> None:
        r = self.s.request("PROPFIND", self.url(root + "/" + rel if rel else root),
                           headers={"Depth": "1"}, timeout=30)
        if r.status_code == 404:
            return
        r.raise_for_status()
        here = urlparse(self.url(root + "/" + rel if rel else root)).path.rstrip("/")
        for resp in ET.fromstring(r.content).iter("{DAV:}response"):
            href = unquote(urlparse(resp.findtext("{DAV:}href")).path).rstrip("/")
            if href == unquote(here):
                continue
            name = href.rsplit("/", 1)[-1]
            is_dir = resp.find(".//{DAV:}collection") is not None
            sub = f"{rel}/{name}" if rel else name
            if is_dir:
                self._walk(root, sub, out)
            else:
                out.append(sub)
