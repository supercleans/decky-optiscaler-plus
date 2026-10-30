"""OptiScaler's nightly channel: where the build every install uses comes from.

The plugin bundles no OptiScaler. Its set-up downloads the newest nightly
release (or the one pinned), every game shares that copy, and a newer one is
downloaded only when Settings updates it. A newer build only reaches a game
when it is installed again.

Trust is the release API's: it names the archive and its SHA-256, and it is
only read over a verified TLS connection. The archive itself can come over any
connection the wiki transport manages, because it is checked against that hash
before it is kept, and again before it is unpacked.

Offline, the last download is used as it is. With no download at all there is
nothing to install, and that is reported rather than papered over.
"""

import json
import re
import time
from pathlib import Path

from . import wiki
from .payload import sha256
from .constants import (
    NIGHTLY_ASSET_RE,
    NIGHTLY_RELEASES_API,
    NIGHTLY_RELEASES_PAGE,
    NIGHTLY_REPO,
)

ASSET_RE = re.compile(NIGHTLY_ASSET_RE)
DOWNLOAD_PREFIX = f"https://github.com/{NIGHTLY_REPO}/releases/download/"
META_NAME = "current.json"


def usable_releases(releases):
    """Every release that carries an archive and says what it hashes to.

    In the API's order, newest first. A release whose asset has no digest is
    skipped rather than trusted, and so is one whose download URL points
    anywhere but the nightly repository's own releases.
    """
    found = []
    for release in releases or []:
        if not isinstance(release, dict) or release.get("draft"):
            continue
        for asset in release.get("assets") or []:
            match = ASSET_RE.match(asset.get("name") or "")
            digest = str(asset.get("digest") or "")
            url = str(asset.get("browser_download_url") or "")
            if not match or not digest.startswith("sha256:") or not url.startswith(DOWNLOAD_PREFIX):
                continue
            found.append({
                "tag": release.get("tag_name") or match["date"],
                "version": match["version"],
                "date": match["date"],
                "asset": asset["name"],
                "url": url,
                "sha256": digest.split(":", 1)[1].lower(),
                "size": asset.get("size"),
                "published_at": release.get("published_at"),
                "page": release.get("html_url") or NIGHTLY_RELEASES_PAGE,
            })
            break
    return found


def pick_release(releases, tag=None):
    """The newest usable release, or the one tagged ``tag``; None without one."""
    for release in usable_releases(releases):
        if tag is None or release["tag"] == tag:
            return release
    return None


class NightlyChannel:
    """The downloaded nightly, and when the channel was last asked about it."""

    def __init__(self, cache_dir):
        self.dir = Path(cache_dir)
        self.dir.mkdir(parents=True, exist_ok=True)
        self.meta_path = self.dir / META_NAME
        # Why the last check failed, for Settings to print. A failed check with
        # a download already on disk is not an error anywhere else.
        self.last_error = None

    def current(self):
        """The download on disk, or None. Never touches the network."""
        try:
            info = json.loads(self.meta_path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return None
        if not isinstance(info, dict) or not info.get("asset") or not info.get("sha256"):
            return None
        archive = self.archive_path(info)
        if not archive.is_file():
            return None
        if info.get("size") and archive.stat().st_size != info["size"]:
            return None
        return info

    def archive_path(self, info):
        # The name came from the API; keep it to a bare file name regardless.
        return self.dir / Path(info["asset"]).name

    def releases(self):
        """Every usable build the channel lists, newest first. Over verified TLS only."""
        return usable_releases(wiki.download_json(NIGHTLY_RELEASES_API, verified_only=True))

    def latest(self, tag=None):
        """What the channel offers now: the newest build, or the one tagged ``tag``."""
        releases = wiki.download_json(NIGHTLY_RELEASES_API, verified_only=True)
        release = pick_release(releases, tag)
        if not release:
            raise ValueError(f"no usable release{f' {tag}' if tag else ''} on {NIGHTLY_REPO}")
        return release

    def ensure(self, force=False, logger=None, tag=None):
        """The build to install from: the one on disk, or a download.

        Installs use the build that was downloaded, and a newer one comes only
        with ``force`` (set-up and Settings' update), so nothing changes behind
        the user. ``tag`` pins a build picked in Settings: that one is used,
        downloaded when it is not the one on disk. A failed check falls back to
        the download already on disk; only having nothing at all (or not the
        build pinned) is an error.
        """
        current = self.current()
        if tag:
            if current and current.get("tag") == tag:
                return current
        elif current and not force:
            return current

        try:
            release = self.latest(tag)
        except Exception as exc:  # network, TLS, rate limit, a changed API
            self.last_error = f"{type(exc).__name__}: {exc}"
            if logger:
                logger.warning("nightly check failed: %s", self.last_error)
            if current and not tag:
                return current
            raise RuntimeError(
                f"{NIGHTLY_REPO}에서 OptiScaler {tag or ''}를 다운로드할 수 없습니다 "
                f"({self.last_error}). 첫 설치나 다른 버전을 고른 뒤에는 인터넷 연결이 필요합니다."
            ) from exc
        self.last_error = None
        now = time.time()

        if (current and current["sha256"] == release["sha256"]
                and current["asset"] == release["asset"]):
            current["checked_at"] = now
            self._write(current)
            return current

        archive = self.archive_path(release)
        if not (archive.is_file() and sha256(archive) == release["sha256"]):
            if logger:
                logger.info("downloading OptiScaler %s (%s)", release["tag"], release["asset"])
            wiki.download(release["url"], archive, timeout=120)
            actual = sha256(archive)
            if actual != release["sha256"]:
                archive.unlink(missing_ok=True)
                raise ValueError(
                    f"{release['asset']} checksum mismatch: expected {release['sha256']}, "
                    f"got {actual}"
                )

        info = {**release, "downloaded_at": now, "checked_at": now}
        self._write(info)
        # One build at a time: games keep their own copy, so an older archive
        # has nothing left to serve.
        for other in self.dir.glob("*.7z"):
            if other.name != archive.name:
                other.unlink(missing_ok=True)
        return info

    def verify(self, info):
        """Check the archive on disk is still the one the API named."""
        archive = self.archive_path(info)
        actual = sha256(archive)
        if actual != info["sha256"]:
            raise ValueError(
                f"{archive.name} checksum mismatch: expected {info['sha256']}, got {actual}"
            )
        return archive

    def status(self):
        current = self.current()
        return {
            "current": current,
            "error": self.last_error,
            "page": NIGHTLY_RELEASES_PAGE,
        }

    def _write(self, info):
        partial = self.meta_path.with_name(self.meta_path.name + ".part")
        partial.write_text(json.dumps(info, indent=2), encoding="utf-8")
        partial.replace(self.meta_path)
