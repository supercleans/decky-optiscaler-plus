"""The HelixSR build HLX DLSS comes from, found on disk.

HLX DLSS is NVIDIA's network rebuilt on the user's own machine, which may not
be shared, so a build made on this Deck is the only one there is: HelixSR
Desktop's, or else the one this plugin had HelixSR's setup make in a release
it downloaded (hlxbuild.py). This finds them, where HelixSR Scaler's own setup
looks and in the plugin's releases, says whether HLX DLSS is built, and hands
the installer the parts it copies: HelixSR Scaler and the HelixSR folder with
HLX DLSS.
"""

import re
from pathlib import Path

from .constants import (
    HELIXSR_DIR,
    HELIXSR_DLL,
    HELIXSR_FOREIGN_MARKERS,
    HELIXSR_HLX_TRAILER,
    HELIXSR_NET_TRAILERS,
    HELIXSR_PAGE,
    HELIXSR_SCALER_DIR,
    HELIXSR_SEARCH,
    OPTI_DIR,
)

VERSION_RE = re.compile(rb"\x00HelixSR (\d+\.\d+\.\d+)\x00")
SCALER_VERSION_RE = re.compile(r"HelixSR Scaler (\d+\.\d+\.\d+)")


def _trailer(path, size):
    try:
        with open(path, "rb") as handle:
            handle.seek(-size, 2)
            return handle.read(8)
    except OSError:
        return b""


def network_built(path):
    """Whether a helixsr.dll carries the network HelixSR's setup builds into it."""
    return _trailer(path, 32) in HELIXSR_NET_TRAILERS


def hlx_built(path):
    """Whether an HLX FSR 4 DLL carries the shaders HelixSR's setup builds into it."""
    return _trailer(path, 24) == HELIXSR_HLX_TRAILER


def _version(dll):
    try:
        with open(dll, "rb") as handle:
            found = VERSION_RE.search(handle.read(4 << 20))
    except OSError:
        return None
    return found.group(1).decode() if found else None


def _scaler_version(scaler):
    for name in ("README-Linux.txt", "README.txt"):
        try:
            found = SCALER_VERSION_RE.search((scaler / name).read_text(errors="replace"))
        except OSError:
            continue
        if found:
            return found.group(1)
    return None


def _describe(helixsr_dir, plugin=False):
    """One candidate build, from its HelixSR folder."""
    root = helixsr_dir.parent
    dll = helixsr_dir / HELIXSR_DLL
    scaler = root / HELIXSR_SCALER_DIR
    scaler_ok = all((scaler / name).exists() for name in ("OptiScaler.dll", "OptiScaler.ini", OPTI_DIR))
    return {
        "found": True,
        "root": str(root),
        "helixsr_dir": str(helixsr_dir),
        "scaler_dir": str(scaler) if scaler_ok else None,
        "version": _version(dll),
        "scaler_version": _scaler_version(scaler) if scaler_ok else None,
        # HLX DLSS needs the network and the Scaler that runs it.
        "dlss_ready": network_built(dll) and scaler_ok,
        "built_at": dll.stat().st_mtime if dll.is_file() else None,
        # Built by this plugin, in a release it downloaded.
        "plugin": plugin,
    }


def find(home, releases=None):
    """The HelixSR build HLX DLSS comes from, or ``{"found": False}``.

    ``releases`` is the folder this plugin unpacks HelixSR's releases in. A
    build HelixSR Desktop made is used before one made there, and the newest
    of each; a folder with a helixsr.dll that was never built is still
    reported when it is all there is, so the UI can offer to build it.
    """
    home = Path(home)
    candidates = {}
    for pattern in HELIXSR_SEARCH:
        for helixsr_dir in home.glob(pattern):
            if (helixsr_dir / HELIXSR_DLL).is_file():
                candidates.setdefault(helixsr_dir.resolve(), False)
    if releases:
        for helixsr_dir in Path(releases).glob(f"*/{HELIXSR_DIR}"):
            if (helixsr_dir / HELIXSR_DLL).is_file() and not helixsr_dir.parent.name.endswith(".part"):
                candidates.setdefault(helixsr_dir.resolve(), True)
    found = [_describe(path, plugin) for path, plugin in candidates.items()]
    if not found:
        return {"found": False, "page": HELIXSR_PAGE}
    # A HelixSR ZIP only extracted (HLX DLSS not built) loses to one set up.
    found.sort(key=lambda item: (item["dlss_ready"], not item["plugin"], item["built_at"] or 0),
               reverse=True)
    return {**found[0], "page": HELIXSR_PAGE}


def tag(build):
    """The install tag a game set up from this build records, like a nightly's."""
    return f"helixsr-{build.get('version') or 'unknown'}"


def foreign_install(folder):
    """The HelixSR Desktop record in a folder, when that app installed there."""
    for name in HELIXSR_FOREIGN_MARKERS:
        if (Path(folder) / name).is_file():
            return name
    return None
