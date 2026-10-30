"""FSR drop-in: FSR 4 in a game that ships FSR 3.1, by swapping the DLL.

No OptiScaler and no REFramework: the game's own FSR 3.1 option keeps working
and runs FSR 4 instead, through the FidelityFX API it already calls. That is
why it reaches Capcom games without the anti-tamper bypass OptiScaler needs
from REFramework, and why it survives game updates OptiScaler's hooks do not.

The upscaler is one of cyboman's FSR 4.1.2 Lite builds for RDNA2 integrated
graphics (fsr4-shader-performance-overrides: "4.1.2l-exact" or
"4.1.2l-lossy"): AMD's GPU check is lifted, so it starts on the Steam
Deck, and AMD's FidelityFX loader does not check signatures, so it loads like
AMD's own file. The same file goes into OptiScaler as a custom upscaler in
games that have no FSR 3.1 of their own (see installer.install).

Or, for FSR 4 Lite, it is AMD's own FSR 4.1.2 out of the OptiScaler nightly
("amd"), as a test: with no OptiScaler in front of it, its GPU check is AMD's
and may well turn the Steam Deck down.

Or it is HelixSR's HLX FSR 4, from the user's own HelixSR build ("hlx"). That
one goes in the way HelixSR's own drop-in does: under the game's file name,
with the game's file kept beside it as ``*.original.dll``, which it hands what
it does not cover itself.

Everything put down is recorded in a manifest of its own beside the game's
FidelityFX files, every file it replaces is moved into the backup folder, and
removing it puts them back - the same contract as an OptiScaler install.
"""

import json
import os
import re
import shutil
import time
from pathlib import Path

from . import wiki
from .constants import (
    BACKUP_DIR,
    CYBOMAN_LITE_LOSSY,
    DROPIN_ASSET_RE,
    DROPIN_MANIFEST,
    DROPIN_RELEASES_API,
    DROPIN_RELEASES_PAGE,
    DROPIN_REPO,
    DROPIN_VARIANT_HLX,
    FFX_DX12_DLL,
    FFX_FRAMEGEN_FILE,
    FFX_LOADER_FILE,
    FFX_UPSCALER_FILE,
    OPTI_DIR,
)
from .payload import extract_archive, sha256

ASSET_RE = re.compile(DROPIN_ASSET_RE)
DOWNLOAD_PREFIX = f"https://github.com/{DROPIN_REPO}/releases/download/"
# Inside the backup folder, so the originals sit with the rest and a stray
# OptiScaler backup of the same name cannot be overwritten by ours.
STASH_SUBDIR = "dropin"
SKIP_DIRS = {OPTI_DIR.lower(), BACKUP_DIR.lower(), "licenses", "d3d12_optiscaler"}
MAX_DEPTH = 8
# What HLX FSR 4 writes beside itself while the game runs; ours to take out.
HLX_RUNTIME_FILES = ["HLX_FSR.log"]


def original_name(name):
    """``amd_fidelityfx_dx12.dll`` -> ``amd_fidelityfx_dx12.original.dll``."""
    return name[:-4] + ".original.dll" if name.lower().endswith(".dll") else name + ".original"


# -- where a game keeps its FidelityFX -----------------------------------------
def find_target(game_path):
    """The folder holding this game's own DX12 FidelityFX, and its layout.

    ``{"dir": ..., "layout": "split" | "monolithic"}``, or None when the game
    ships no FSR 3.1 DLL for DirectX 12. A folder with the upscaler as a file of
    its own is "split" (whatever else sits beside it); one with only
    amd_fidelityfx_dx12.dll is "monolithic". The shallowest match wins: that is
    the executable's folder in every layout seen so far.
    """
    root = Path(game_path)
    if not root.is_dir():
        return None
    best = None
    root_depth = len(root.parts)
    for dirpath, dirnames, filenames in os.walk(root):
        current = Path(dirpath)
        depth = len(current.parts) - root_depth
        dirnames[:] = [d for d in dirnames
                       if not d.startswith(".") and d.lower() not in SKIP_DIRS]
        if depth >= MAX_DEPTH:
            dirnames[:] = []
        names = {n.lower() for n in filenames}
        layout = ("split" if FFX_UPSCALER_FILE in names
                  else "monolithic" if FFX_DX12_DLL in names else None)
        if layout and (best is None or depth < best[0]):
            best = (depth, {"dir": str(current), "layout": layout})
    return best[1] if best else None


def read_manifest(target_dir):
    path = Path(target_dir) / DROPIN_MANIFEST
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None


def status(game_path):
    """Whether a drop-in is possible here, and whether it is in place."""
    found = find_target(game_path)
    if not found:
        return {"possible": False, "installed": False}
    manifest = read_manifest(found["dir"]) or {}
    installed = bool(manifest)
    # The file the upscaler went in as: always this one for cyboman's builds,
    # the game's own file name for HLX FSR 4.
    upscaler = Path(found["dir"]) / (manifest.get("upscaler_file") or FFX_UPSCALER_FILE)
    # A game update or a file check can put the game's own DLL back, which
    # leaves our record pointing at a file that is no longer ours.
    intact = bool(installed and upscaler.is_file()
                  and sha256(upscaler) == manifest.get("upscaler_sha256"))
    return {
        "possible": True,
        "dir": found["dir"],
        "layout": manifest.get("layout") or found["layout"],
        "installed": installed,
        "intact": intact,
        "tag": manifest.get("tag"),
        "variant": manifest.get("variant"),
        "installed_at": manifest.get("installed_at"),
        "releases": DROPIN_RELEASES_PAGE,
    }


# -- the build -------------------------------------------------------------------
def usable_releases(releases):
    """Every `dll-*` release carrying the RDNA2 integrated-graphics archive, newest first."""
    found = []
    for release in releases or []:
        if not isinstance(release, dict) or release.get("draft"):
            continue
        if not str(release.get("tag_name") or "").startswith("dll-"):
            continue
        for asset in release.get("assets") or []:
            url = str(asset.get("browser_download_url") or "")
            digest = str(asset.get("digest") or "")
            if (ASSET_RE.match(asset.get("name") or "") and url.startswith(DOWNLOAD_PREFIX)
                    and digest.startswith("sha256:")):
                found.append({"tag": release["tag_name"], "asset": asset["name"], "url": url,
                              "sha256": digest.split(":", 1)[1].lower(),
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
    """Every usable build the channel lists, newest first. Over verified TLS only."""
    data = wiki.download_json(DROPIN_RELEASES_API, verified_only=True)
    return usable_releases(data if isinstance(data, list) else [])


def _variant_file(unpacked, variant):
    """The named variant's upscaler inside an unpacked archive, or None."""
    for path in sorted(Path(unpacked).rglob(FFX_UPSCALER_FILE)):
        if path.parent.name.lower() == variant.lower():
            return path
    return None


def fetch(cache_dir, logger=None, variant=CYBOMAN_LITE_LOSSY, tag=None):
    """Download, verify and unpack the newest build; returns (upscaler, tag).

    ``variant`` is the archive folder wanted ("4.1.2l-lossy"...); ``tag`` pins
    the build picked in Settings instead of the newest. The release list is
    read over verified TLS and the archive is checked against the digest it
    names before anything is unpacked. Offline, the newest build verified
    before that carries the variant (or the pinned one) is used; one never
    downloaded is not.
    """
    cache = Path(cache_dir)
    if tag and _variant_file(cache / tag, variant):
        return _variant_file(cache / tag, variant), tag
    try:
        releases = wiki.download_json(DROPIN_RELEASES_API, verified_only=True)
        found = pick_release(releases if isinstance(releases, list) else [], tag)
        if not found:
            raise FileNotFoundError(f"no FSR 4 drop-in build{f' {tag}' if tag else ''} with a "
                                    f"digest on {DROPIN_REPO}")
    except Exception:
        cached = sorted((d for d in cache.glob("dll-*")
                         if _variant_file(d, variant) and (tag is None or d.name == tag)),
                        key=lambda d: d.stat().st_mtime, reverse=True)
        if cached:
            return _variant_file(cached[0], variant), cached[0].name
        raise

    unpacked = cache / found["tag"]
    if unpacked.is_dir():
        existing = _variant_file(unpacked, variant)
        if existing:
            return existing, found["tag"]
        raise FileNotFoundError(f"{found['tag']} has no {variant}/{FFX_UPSCALER_FILE}")

    archive = cache / found["asset"]
    if logger:
        logger.info("downloading FSR 4 drop-in %s", found["url"])
    wiki.download(found["url"], archive)
    actual = sha256(archive)
    if actual != found["sha256"]:
        archive.unlink(missing_ok=True)
        raise ValueError(f"{found['asset']} checksum mismatch: expected {found['sha256']}, got {actual}")
    staging = cache / (found["tag"] + ".part")
    if staging.exists():
        shutil.rmtree(staging, ignore_errors=True)
    extract_archive(archive, staging, logger)
    if not _variant_file(staging, variant):
        shutil.rmtree(staging, ignore_errors=True)
        raise ValueError(f"{found['asset']} has no {variant}/{FFX_UPSCALER_FILE}")
    if unpacked.exists():
        shutil.rmtree(unpacked, ignore_errors=True)
    staging.replace(unpacked)
    archive.unlink(missing_ok=True)
    return _variant_file(unpacked, variant), found["tag"]


def has(cache_dir, tag, variant):
    """Whether build ``tag`` is unpacked in ``cache_dir`` with ``variant``."""
    return bool(tag) and _variant_file(Path(cache_dir) / tag, variant) is not None


def prune(cache_dir, keep=()):
    """Remove every unpacked build but ``keep``: games keep their own copies."""
    cache = Path(cache_dir)
    if not cache.is_dir():
        return
    for folder in cache.glob("dll-*"):
        if folder.is_dir() and folder.name not in keep:
            shutil.rmtree(folder, ignore_errors=True)


# -- putting it in, and taking it out -------------------------------------------
def _stash_dir(target):
    return Path(target) / BACKUP_DIR / STASH_SUBDIR


def install(game_path, upscaler, tag, payload_root=None, logger=None, variant=CYBOMAN_LITE_LOSSY):
    """Put the drop-in upscaler in place of the game's own FSR.

    ``payload_root`` is the unpacked OptiScaler nightly, needed only for a
    monolithic game taking one of cyboman's builds or AMD's: its SDK 2 loader becomes
    amd_fidelityfx_dx12.dll and its frame generator goes beside it, so the
    game's FSR frame generation keeps working once the old all-in-one DLL is
    gone. HLX FSR 4 needs neither: it takes whichever file the game has and
    hands everything else to that file, kept beside it.
    """
    found = find_target(game_path)
    if not found:
        raise FileNotFoundError("this game ships no FSR 3.1 DLL for DirectX 12 to replace")
    target = Path(found["dir"])
    if read_manifest(target):
        uninstall(game_path, logger)
        found = find_target(game_path)
        target = Path(found["dir"])
    layout = found["layout"]

    keep_beside = None
    if variant == DROPIN_VARIANT_HLX:
        upscaler_file = FFX_UPSCALER_FILE if layout == "split" else FFX_DX12_DLL
        sources = {upscaler_file: Path(upscaler)}
        keep_beside = upscaler_file
    else:
        upscaler_file = FFX_UPSCALER_FILE
        sources = {FFX_UPSCALER_FILE: Path(upscaler)}
        if layout == "monolithic":
            if not payload_root:
                raise FileNotFoundError("the OptiScaler nightly is needed for this game's FidelityFX loader")
            opti = Path(payload_root) / OPTI_DIR
            sources[FFX_DX12_DLL] = opti / FFX_LOADER_FILE
            sources[FFX_FRAMEGEN_FILE] = opti / FFX_FRAMEGEN_FILE
    missing = [str(src) for src in sources.values() if not src.is_file()]
    if missing:
        raise FileNotFoundError("missing " + ", ".join(missing))

    stash = _stash_dir(target)
    backups, created = [], []
    for name, source in sources.items():
        destination = target / name
        if destination.exists():
            stash.mkdir(parents=True, exist_ok=True)
            if not (stash / name).exists():
                shutil.move(str(destination), str(stash / name))
            else:
                destination.unlink()
            backups.append(name)
        else:
            created.append(name)
        shutil.copy2(source, destination)
        if logger:
            logger.info("drop-in: %s %s", "replaced" if name in backups else "added", name)

    files = sorted(sources)
    if keep_beside and keep_beside in backups:
        # The game's own file, where HLX FSR 4 looks for it. A copy: the one in
        # the backup folder is what removing the drop-in puts back.
        beside = original_name(keep_beside)
        shutil.copy2(stash / keep_beside, target / beside)
        files.append(beside)
        created.append(beside)

    manifest = {
        "plugin": "decky-optiscaler",
        "layout": layout,
        "tag": tag,
        "variant": variant,
        "files": files,
        "backups": backups,
        "created": created,
        "upscaler_file": upscaler_file,
        "upscaler_sha256": sha256(target / upscaler_file),
        "installed_at": time.time(),
    }
    (target / DROPIN_MANIFEST).write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    return {"dir": str(target), **manifest}


def uninstall(game_path, logger=None):
    """Take the drop-in out and put the game's own FidelityFX files back."""
    found = find_target(game_path)
    target = Path(found["dir"]) if found else None
    manifest = read_manifest(target) if target else None
    if not manifest:
        return {"removed": [], "restored": []}
    stash = _stash_dir(target)
    removed, restored = [], []
    for name in manifest.get("files", []):
        path = target / name
        if path.is_file():
            path.unlink()
            removed.append(name)
        original = stash / name
        if name in manifest.get("backups", []) and original.is_file():
            shutil.move(str(original), str(path))
            restored.append(name)
            if logger:
                logger.info("drop-in: restored %s", name)
    if manifest.get("variant") == DROPIN_VARIANT_HLX:
        for name in HLX_RUNTIME_FILES:
            if (target / name).is_file():
                (target / name).unlink()
                removed.append(name)
    (target / DROPIN_MANIFEST).unlink(missing_ok=True)
    for folder in (stash, stash.parent):
        try:
            folder.rmdir()  # only when nothing else is kept there
        except OSError:
            pass
    return {"removed": removed, "restored": restored}
