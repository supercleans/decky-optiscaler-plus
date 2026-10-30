"""Whether a newer release of this plugin is out, and what Decky needs to install it.

Decky Loader only offers updates for plugins from its own store; one installed
from a URL is never told about a new version. So the plugin asks its GitHub
releases itself, at most every PLUGIN_CHECK_TTL unless asked to now, and hands
the frontend what Decky's own installer takes: the zip's address, the name the
plugin is installed under, the version and the SHA-256. Decky downloads the zip,
checks that hash, and asks the user to confirm before replacing anything.

Only the latest full release counts - GitHub's /releases/latest leaves
prereleases out - and only an asset in this repository's own release downloads,
with a digest, is offered.
"""

import re
import time

from . import wiki
from .constants import PLUGIN_ASSET_RE, PLUGIN_CHECK_TTL, PLUGIN_RELEASE_API, PLUGIN_REPO

ASSET_RE = re.compile(PLUGIN_ASSET_RE)
DOWNLOAD_PREFIX = f"https://github.com/{PLUGIN_REPO}/releases/download/"
VERSION_RE = re.compile(r"^v?(\d+)\.(\d+)\.(\d+)(?:-([0-9A-Za-z.]+))?$")


def version_key(version):
    """A sortable form of MAJOR.MINOR.PATCH[-PRE]; None when it is not one.

    A prerelease sorts before its release, as semantic versioning has it.
    """
    match = VERSION_RE.match(str(version or "").strip())
    if not match:
        return None
    major, minor, patch, pre = match.groups()
    return (int(major), int(minor), int(patch), 0 if pre else 1, pre or "")


def pick_asset(release):
    """The installable zip of a release, or None."""
    for asset in (release or {}).get("assets") or []:
        match = ASSET_RE.match(asset.get("name") or "")
        digest = str(asset.get("digest") or "")
        url = str(asset.get("browser_download_url") or "")
        if match and digest.startswith("sha256:") and url.startswith(DOWNLOAD_PREFIX):
            return {
                "version": match["version"],
                "url": url,
                "sha256": digest.split(":", 1)[1].lower(),
                "size": asset.get("size"),
            }
    return None


class PluginUpdates:
    """The last answer from this plugin's releases, kept for PLUGIN_CHECK_TTL."""

    def __init__(self, current_version, plugin_name):
        self.current = current_version
        self.name = plugin_name
        self._answer = None

    def check(self, force=False):
        answer = self._answer
        if answer and not force and time.time() - answer["checked_at"] < PLUGIN_CHECK_TTL:
            return answer

        answer = {
            "current": self.current,
            "name": self.name,
            "latest": None,
            "update_available": False,
            "url": None,
            "sha256": None,
            "size": None,
            "page": f"https://github.com/{PLUGIN_REPO}/releases",
            "published_at": None,
            "checked_at": time.time(),
            "error": None,
        }
        try:
            release = wiki.download_json(PLUGIN_RELEASE_API, verified_only=True)
            asset = pick_asset(release)
            if not asset:
                raise ValueError("the latest release has no installable zip with a digest")
            answer.update(
                latest=asset["version"], url=asset["url"], sha256=asset["sha256"],
                size=asset["size"], published_at=release.get("published_at"),
                page=release.get("html_url") or answer["page"],
            )
            newer, mine = version_key(asset["version"]), version_key(self.current)
            answer["update_available"] = bool(newer and mine and newer > mine)
        except Exception as exc:  # offline, rate-limited, no release yet
            answer["error"] = f"{type(exc).__name__}: {exc}"
            # A failed check is retried sooner than a successful one.
            answer["checked_at"] = time.time() - PLUGIN_CHECK_TTL + 15 * 60
        self._answer = answer
        return answer
