"""OptiPatcher's rolling build: downloaded when first needed, kept current.

OptiPatcher only does anything for the games whose patterns are compiled into
it, and the project adds games every week or two to a single `rolling` release
whose asset is replaced in place. The wiki's OptiPatcher column follows that
build, so the plugin ships no copy of its own: like OptiScaler, the first
install that wants it downloads the newest rolling build, every game shares
that copy, and the channel is asked again once that answer is older than
OPTIPATCHER_CHECK_TTL.

Trust is the same as the nightly's: the release API names the file's SHA-256
and is only read over verified TLS, and the download is checked against it
before it is kept. Offline, the last good download is used; with none, there
is nothing to install, and that is reported rather than papered over.
"""

import json
import time
from pathlib import Path

from . import wiki
from .constants import (
    OPTIPATCHER_CHECK_TTL,
    OPTIPATCHER_NAME,
    OPTIPATCHER_RELEASE_API,
    OPTIPATCHER_RELEASES_PAGE,
    OPTIPATCHER_REPO,
    OPTIPATCHER_TAG,
)
from .payload import sha256

DOWNLOAD_PREFIX = f"https://github.com/{OPTIPATCHER_REPO}/releases/download/{OPTIPATCHER_TAG}/"
META_NAME = "current.json"


def pick_asset(release):
    """OptiPatcher.asi in the rolling release, with the digest it names, or None."""
    for asset in (release or {}).get("assets") or []:
        if asset.get("name") != OPTIPATCHER_NAME:
            continue
        digest = str(asset.get("digest") or "")
        url = str(asset.get("browser_download_url") or "")
        if digest.startswith("sha256:") and url.startswith(DOWNLOAD_PREFIX):
            return {
                "sha256": digest.split(":", 1)[1].lower(),
                "url": url,
                "size": asset.get("size"),
                # The asset is replaced in place, so its own date is the build's.
                "updated_at": asset.get("updated_at"),
            }
    return None


def label(updated_at):
    """"rolling (2026-10-27)" from the asset's ISO timestamp."""
    day = str(updated_at or "")[:10]
    return f"{OPTIPATCHER_TAG} ({day})" if day else OPTIPATCHER_TAG


class OptiPatcherChannel:
    """The downloaded rolling build, and when the channel was last asked."""

    def __init__(self, cache_dir):
        self.dir = Path(cache_dir)
        self.path = self.dir / OPTIPATCHER_NAME
        self.meta_path = self.dir / META_NAME
        # Why the last check failed, for Settings and for an install that
        # wanted OptiPatcher and could not have it.
        self.last_error = None

    def current(self):
        """The download on disk, still the bytes its release named, or None.

        Never touches the network.
        """
        try:
            info = json.loads(self.meta_path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return None
        if not isinstance(info, dict) or not info.get("sha256") or not self.path.is_file():
            return None
        if sha256(self.path) != info["sha256"]:
            return None
        return {**info, "path": str(self.path), "label": label(info.get("updated_at"))}

    def is_stale(self, info=None):
        info = info if info is not None else self.current()
        if not info:
            return True
        return time.time() - (info.get("checked_at") or 0) >= OPTIPATCHER_CHECK_TTL

    def ensure(self, force=False, logger=None):
        """The build to install, downloading a newer one when there is one.

        A failed check falls back to the download already on disk; only having
        nothing at all is an error.
        """
        current = self.current()
        if current and not force and not self.is_stale(current):
            return current
        try:
            release = wiki.download_json(OPTIPATCHER_RELEASE_API, verified_only=True)
            asset = pick_asset(release if isinstance(release, dict) else None)
            if not asset:
                raise ValueError(f"no {OPTIPATCHER_NAME} with a digest on {OPTIPATCHER_REPO}")
            if not (current and current["sha256"] == asset["sha256"]):
                self._download(asset, logger)
            self._write({**asset, "checked_at": time.time()})
            self.last_error = None
        except Exception as exc:  # network, TLS, rate limit, a changed API
            self.last_error = f"{type(exc).__name__}: {exc}"
            if logger:
                logger.warning("OptiPatcher check failed: %s", self.last_error)
            current = self.current()
            if current:
                return current
            raise RuntimeError(
                f"{OPTIPATCHER_REPO}에서 OptiPatcher를 다운로드할 수 없습니다 "
                f"({self.last_error}). 첫 설치에는 인터넷 연결이 필요합니다."
            ) from exc
        return self.current()

    def _download(self, asset, logger):
        self.dir.mkdir(parents=True, exist_ok=True)
        partial = self.path.with_name(self.path.name + ".part")
        if logger:
            logger.info("downloading OptiPatcher %s", label(asset.get("updated_at")))
        wiki.download(asset["url"], partial)
        actual = sha256(partial)
        if actual != asset["sha256"]:
            partial.unlink(missing_ok=True)
            raise ValueError(f"{OPTIPATCHER_NAME} checksum mismatch: expected "
                             f"{asset['sha256']}, got {actual}")
        partial.replace(self.path)

    def status(self):
        current = self.current() or {}
        return {
            "label": current.get("label"),
            "sha256": current.get("sha256"),
            "checked_at": current.get("checked_at"),
            "error": self.last_error,
            "page": OPTIPATCHER_RELEASES_PAGE,
        }

    def _write(self, info):
        self.dir.mkdir(parents=True, exist_ok=True)
        partial = self.meta_path.with_name(self.meta_path.name + ".part")
        partial.write_text(json.dumps(info, indent=2), encoding="utf-8")
        partial.replace(self.meta_path)
