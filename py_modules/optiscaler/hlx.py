"""HelixSR's official releases, downloaded and unpacked whole.

From HelixSR 3.2.0 the release ZIP carries HLX FSR 4 built: its shaders are
made from AMD's FSR SDK (MIT), not from files that must stay on the user's
machine, and the DLL works as it comes out of the ZIP. So, like cyboman's
builds, it is downloaded here instead of taken from a HelixSR Desktop set-up:
the whole ZIP, checked against the digest the release names, unpacked as the
release folder it is. HLX-FSR4/amd_fidelityfx_upscaler_dx12.dll is used from
there, and the rest is what HLX DLSS is built in (hlxbuild.py) when HelixSR
Desktop has not built it already. HelixSR's licence lets it be used
unmodified; nothing of it ships with this plugin.

HLX FSR 4 goes into a game as a drop-in where the game has FSR 3.1, and
otherwise through OptiScaler (see installer.install).
"""

import os
import re
import shutil
import zipfile
from pathlib import Path

from . import helixsr, wiki
from .constants import (
    FFX_UPSCALER_FILE,
    HELIXSR_ASSET_RE,
    HELIXSR_DIR,
    HELIXSR_DLL,
    HELIXSR_HLX_DIR,
    HELIXSR_PREBUILT_HLX,
    HELIXSR_RELEASES_API,
    HELIXSR_REPO,
    HELIXSR_SETUP,
)
from .payload import sha256

ASSET_RE = re.compile(HELIXSR_ASSET_RE)
DOWNLOAD_PREFIX = f"https://github.com/{HELIXSR_REPO}/releases/download/"


def usable_releases(releases):
    """Every release whose ZIP carries HLX FSR 4 built and names its digest, newest first."""
    found = []
    for release in releases or []:
        if not isinstance(release, dict) or release.get("draft"):
            continue
        for asset in release.get("assets") or []:
            match = ASSET_RE.match(asset.get("name") or "")
            url = str(asset.get("browser_download_url") or "")
            digest = str(asset.get("digest") or "")
            if not match or not url.startswith(DOWNLOAD_PREFIX) or not digest.startswith("sha256:"):
                continue
            if tuple(int(n) for n in match["version"].split(".")) < HELIXSR_PREBUILT_HLX:
                break  # built on the user's machine back then, not in the ZIP
            found.append({"tag": release["tag_name"], "version": match["version"],
                          "asset": asset["name"], "url": url,
                          "sha256": digest.split(":", 1)[1].lower(), "size": asset.get("size"),
                          "published_at": release.get("published_at"),
                          "title": release.get("name")})
            break
    return found


def pick_release(releases, tag=None):
    """The newest usable release, or the one tagged ``tag``; None without one."""
    for release in usable_releases(releases):
        if tag is None or release["tag"] == tag:
            return release
    return None


def releases():
    """Every usable release, newest first. Over verified TLS only."""
    data = wiki.download_json(HELIXSR_RELEASES_API, verified_only=True)
    return usable_releases(data if isinstance(data, list) else [])


def hlx_file(release_dir):
    """HLX FSR 4 in an unpacked release."""
    return Path(release_dir) / HELIXSR_HLX_DIR / FFX_UPSCALER_FILE


def _cached(cache, tag):
    folder = Path(cache) / tag
    complete = (folder / HELIXSR_SETUP).is_file() and (folder / HELIXSR_DIR / HELIXSR_DLL).is_file()
    return folder if complete and helixsr.hlx_built(hlx_file(folder)) else None


def kept(cache):
    """The tags of the releases unpacked in ``cache``."""
    cache = Path(cache)
    return {d.name for d in cache.iterdir() if d.is_dir() and _cached(cache, d.name)} if cache.is_dir() else set()


def _unpack(bundle, staging):
    """The ZIP's one top folder (HelixSR-<version>/) into ``staging``, with its modes."""
    tops = {name.split("/", 1)[0] for name in bundle.namelist()}
    if len(tops) != 1:
        raise ValueError("the HelixSR ZIP is not one release folder")
    top = tops.pop() + "/"
    base = staging.resolve()
    for info in bundle.infolist():
        relative = info.filename[len(top):]
        if not relative or info.is_dir():
            continue
        dest = (staging / relative).resolve()
        if base not in dest.parents:
            raise ValueError(f"the HelixSR ZIP names a path outside its folder: {info.filename}")
        dest.parent.mkdir(parents=True, exist_ok=True)
        with bundle.open(info) as source, open(dest, "wb") as out:
            shutil.copyfileobj(source, out)
        mode = (info.external_attr >> 16) & 0o777
        if mode:
            os.chmod(dest, mode)


def fetch_release(cache_dir, logger=None, tag=None):
    """Download, verify and unpack the newest release; returns (folder, tag).

    ``tag`` pins the release picked in Settings instead of the newest. The ZIP
    is checked against its digest before anything is taken out of it, and its
    HLX FSR 4 against the trailer a built one ends in. Offline, the newest one
    unpacked before (or the pinned one) is used; one never downloaded is not.
    """
    cache = Path(cache_dir)
    if tag and _cached(cache, tag):
        return _cached(cache, tag), tag
    try:
        data = wiki.download_json(HELIXSR_RELEASES_API, verified_only=True)
        found = pick_release(data if isinstance(data, list) else [], tag)
        if not found:
            raise FileNotFoundError(f"no HelixSR release{f' {tag}' if tag else ''} with HLX FSR 4 "
                                    f"built and a digest on {HELIXSR_REPO}")
    except Exception:
        candidates = sorted((cache / name for name in kept(cache) if tag is None or name == tag),
                            key=lambda d: d.stat().st_mtime, reverse=True)
        if candidates:
            return candidates[0], candidates[0].name
        raise

    existing = _cached(cache, found["tag"])
    if existing:
        return existing, found["tag"]

    archive = cache / found["asset"]
    if logger:
        logger.info("downloading HelixSR %s", found["url"])
    wiki.download(found["url"], archive, timeout=300)
    staging = cache / (found["tag"] + ".part")
    try:
        actual = sha256(archive)
        if actual != found["sha256"]:
            raise ValueError(f"{found['asset']} checksum mismatch: expected {found['sha256']}, "
                             f"got {actual}")
        if staging.exists():
            shutil.rmtree(staging, ignore_errors=True)
        staging.mkdir(parents=True)
        with zipfile.ZipFile(archive) as bundle:
            _unpack(bundle, staging)
        if not hlx_file(staging).is_file():
            raise FileNotFoundError(f"{found['asset']} has no {HELIXSR_HLX_DIR}/{FFX_UPSCALER_FILE}")
        if not helixsr.hlx_built(hlx_file(staging)):
            raise ValueError(f"{found['asset']}'s HLX FSR 4 is not built")
        if not (staging / HELIXSR_SETUP).is_file() or not (staging / HELIXSR_DIR / HELIXSR_DLL).is_file():
            raise FileNotFoundError(f"{found['asset']} is not a whole HelixSR release")
    except Exception:
        shutil.rmtree(staging, ignore_errors=True)
        raise
    finally:
        archive.unlink(missing_ok=True)
    unpacked = cache / found["tag"]
    if unpacked.exists():
        shutil.rmtree(unpacked, ignore_errors=True)
    staging.replace(unpacked)
    return unpacked, found["tag"]


def fetch(cache_dir, logger=None, tag=None):
    """HLX FSR 4 of the newest (or the pinned) release; returns (dll, tag)."""
    folder, found = fetch_release(cache_dir, logger, tag)
    return hlx_file(folder), found


def prune(cache_dir, keep=()):
    """Remove every unpacked release but ``keep`` and the newest with HLX DLSS built.

    Each one is a few hundred MB, so only what is in use stays: the release
    installs take HLX FSR 4 from, one being built, and the HLX DLSS build HLX
    DLSS installs copy, which another version being picked does not undo.
    """
    cache = Path(cache_dir)
    if not cache.is_dir():
        return
    folders = [d for d in cache.iterdir() if d.is_dir()]
    built = sorted((d for d in folders if helixsr.network_built(d / HELIXSR_DIR / HELIXSR_DLL)),
                   key=lambda d: (d / HELIXSR_DIR / HELIXSR_DLL).stat().st_mtime, reverse=True)
    stay = set(keep) | ({built[0].name} if built else set())
    for folder in folders:
        if folder.name not in stay and not folder.name.endswith(".part"):
            shutil.rmtree(folder, ignore_errors=True)
