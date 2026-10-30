"""Unpacking of the OptiScaler release archive downloaded from the nightly channel.

The release ships as a 7z using the BCJ2 filter, which Python's stdlib (and
py7zr) cannot read, so extraction is delegated to whichever archiver the system
provides. SteamOS carries both p7zip and bsdtar.
"""

import hashlib
import shutil
import subprocess
from pathlib import Path

EXTRACTORS = [
    (["7z", "x", "-y"], "-o{dest}"),
    (["7zz", "x", "-y"], "-o{dest}"),
    (["7za", "x", "-y"], "-o{dest}"),
    (["7zr", "x", "-y"], "-o{dest}"),
]
# bsdtar (libarchive) handles BCJ2 and is present wherever pacman is.
BSDTAR = ["bsdtar", "-xf"]

MARKER = "OptiScaler.dll"


def sha256(path, chunk=1 << 20):
    digest = hashlib.sha256()
    with open(path, "rb") as handle:
        while True:
            block = handle.read(chunk)
            if not block:
                break
            digest.update(block)
    return digest.hexdigest()


def available_extractor():
    for command, _ in EXTRACTORS:
        if shutil.which(command[0]):
            return command[0]
    if shutil.which(BSDTAR[0]):
        return BSDTAR[0]
    return None


def extract_archive(archive, dest, logger=None):
    """Unpack an archive with whichever archiver the system has.

    A 7z that uses the BCJ2 filter is beyond the stdlib and py7zr alike, so
    this shells out. SteamOS has p7zip and bsdtar; a desktop usually has one of
    the two.

    Unpacking is not the same as trusting: the archive is checked against the
    hash its release named before it is handed here.
    """
    archive, dest = Path(archive), Path(dest)
    dest.mkdir(parents=True, exist_ok=True)

    errors = []
    for command, dest_flag in EXTRACTORS:
        if not shutil.which(command[0]):
            continue
        ok, message = _run(command + [dest_flag.format(dest=str(dest)), str(archive)], logger)
        if ok:
            return dest
        errors.append(f"{command[0]}: {message}")

    if shutil.which(BSDTAR[0]):
        ok, message = _run(BSDTAR + [str(archive), "-C", str(dest)], logger)
        if ok:
            return dest
        errors.append(f"bsdtar: {message}")

    detail = "; ".join(errors) if errors else (
        "no supported archiver found (need one of 7z, 7zz, 7za, 7zr or bsdtar)"
    )
    raise RuntimeError(f"could not extract {archive.name}: {detail}")


def _run(argv, logger=None):
    """Run one archiver invocation; returns (ok, message)."""
    if logger:
        logger.info("extracting with: %s", " ".join(argv))
    try:
        result = subprocess.run(
            argv, capture_output=True, text=True, timeout=600, check=False
        )
    except (OSError, subprocess.SubprocessError) as exc:
        return False, str(exc)
    if result.returncode != 0:
        return False, (result.stderr or result.stdout or "").strip()[:400]
    return True, ""


class Payload:
    """The unpacked copy of the nightly build installs are made from.

    One folder per release tag, so a game installed from yesterday's build and
    one from today's never share a half-replaced tree, and the previous one is
    dropped once a newer build has unpacked cleanly.
    """

    def __init__(self, channel, extract_root):
        self.channel = channel
        self.extract_root = Path(extract_root)

    def root_for(self, info):
        return self.extract_root / info["tag"]

    @property
    def info(self):
        return self.channel.current()

    @property
    def ready(self):
        info = self.info
        return bool(info) and (self.root_for(info) / MARKER).is_file()

    @property
    def root(self):
        info = self.info
        return self.root_for(info) if info else None

    def status(self):
        channel = self.channel.status()
        info = channel["current"] or {}
        return {
            "version": info.get("version"),
            "tag": info.get("tag"),
            "published_at": info.get("published_at"),
            "checked_at": info.get("checked_at"),
            "release_page": info.get("page") or channel["page"],
            "archive_present": bool(info),
            "extracted": self.ready,
            "extract_path": str(self.root) if info else None,
            "extractor": available_extractor(),
            "error": channel["error"],
        }

    def ensure(self, force=False, logger=None, tag=None):
        """Download (when due) and unpack the current build; returns its folder.

        ``force`` asks the nightly channel for a newer build right now instead
        of using the one on disk; ``tag`` asks for that build.
        """
        info = self.channel.ensure(force, logger, tag)
        root = self.root_for(info)
        if (root / MARKER).is_file():
            return root

        archive = self.channel.verify(info)
        staging = root.with_name(root.name + ".part")
        if staging.exists():
            shutil.rmtree(staging, ignore_errors=True)
        extract_archive(archive, staging, logger)
        if not (staging / MARKER).is_file():
            shutil.rmtree(staging, ignore_errors=True)
            raise RuntimeError(f"{archive.name} has no {MARKER}; not an OptiScaler release")
        if root.exists():
            shutil.rmtree(root, ignore_errors=True)
        staging.replace(root)

        for other in self.extract_root.iterdir():
            if other.is_dir() and other.name != root.name:
                shutil.rmtree(other, ignore_errors=True)
        return root
