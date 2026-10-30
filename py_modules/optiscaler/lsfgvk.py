"""lsfg-vk: Lossless Scaling's frame generation as a Vulkan layer, set up per game.

lsfg-vk (https://lsfg-vk.dev) runs the frame generation of the Windows app
Lossless Scaling in any Vulkan program, so in every game Proton runs. Its
official build is downloaded from builds.lsfg-vk.dev and unpacked unmodified
into ~/.local, in the layout its manual install and decky-lsfg-vk use; its
licence (CC BY-NC-ND 4.0) allows that and no change to it. The frame
generation itself is the user's own Lossless Scaling: its "lsfg-vk" Steam
branch carries the lsfg-vk.dll the layer reads.

A game gets frame generation from a [[profile]] in ~/.config/lsfg-vk/conf.toml
whose active_in is its Steam app id, the convention decky-lsfg-vk uses, so the
two plugins see and keep each other's profiles. The file is written the way
decky-lsfg-vk writes it, with the keys it knows, and checked by lsfg-vk's own
CLI before it replaces the one there.
"""

import json
import os
import re
import shutil
import subprocess
import tarfile
import tempfile
import tomllib
from pathlib import Path

from . import steam, wiki
from .constants import (
    DECKY_PLUGINS,
    LOSSLESS_APPID,
    LOSSLESS_BRANCH,
    LOSSLESS_DIR,
    LOSSLESS_DLL,
    LSFG_BUILDS,
    LSFG_CLI,
    LSFG_CONFIG,
    LSFG_LEGACY,
    LSFG_PAYLOAD,
    LSFG_PROFILE_DEFAULTS,
    LSFG_RELEASE_RE,
    LSFG_REQUIRED,
    LSFG_SHA256,
    LSFG_WRAPPER,
    LSFG_WRAPPER_MARKER,
    LSFG_WRAPPER_PATTERN,
    LSFG_WRAPPER_STATE,
)
from .payload import sha256

RELEASE_RE = re.compile(LSFG_RELEASE_RE)


# -- the layer ---------------------------------------------------------------
def installed(home):
    """Whether the layer is in ~/.local, however it got there."""
    return all((Path(home) / LSFG_PAYLOAD[member][0]).is_file() for member in LSFG_REQUIRED)


def releases():
    """The latest release the build server names: [{tag, version, url}]."""
    page = wiki._http_get(LSFG_BUILDS, timeout=20, verified_only=True)
    found = RELEASE_RE.search(page if isinstance(page, str) else page.decode("utf-8", "replace"))
    if not found:
        raise ValueError(f"{LSFG_BUILDS} names no latest release")
    return [{"tag": found["version"], "version": found["version"], "url": LSFG_BUILDS + found["file"]}]


def install(home, cache_dir, logger=None, version=None):
    """Download the release (the latest, or ``version``) and unpack it into ~/.local.

    Each file is written beside its destination and moved over it, so a game
    loading the layer never reads half of one. lsfg-vk v1's files go, as v2
    asks. Returns the version installed.
    """
    home, cache = Path(home), Path(cache_dir)
    if version is None:
        version = releases()[0]["version"]
    url = f"{LSFG_BUILDS}lsfg-vk-{version}.tar.xz"
    archive = cache / f"lsfg-vk-{version}.tar.xz"
    if logger:
        logger.info("downloading lsfg-vk %s", url)
    wiki.download(url, archive, timeout=120, verified_only=True)
    try:
        expected = LSFG_SHA256.get(version)
        if expected and sha256(archive) != expected:
            raise ValueError(f"lsfg-vk {version}: the download is not the official build")
        with tarfile.open(archive, "r:xz") as bundle:
            members = {m.name.removeprefix("./"): m for m in bundle.getmembers() if m.isfile()}
            missing = [name for name in LSFG_PAYLOAD if name not in members]
            if missing:
                raise ValueError(f"lsfg-vk {version} has no {', '.join(missing)}")
            for name, (relative, mode) in LSFG_PAYLOAD.items():
                destination = home / relative
                destination.parent.mkdir(parents=True, exist_ok=True)
                partial = destination.with_name(f".{destination.name}.part")
                with bundle.extractfile(members[name]) as source, open(partial, "wb") as out:
                    shutil.copyfileobj(source, out)
                os.chmod(partial, mode)
                os.replace(partial, destination)
    finally:
        archive.unlink(missing_ok=True)
    for relative in LSFG_LEGACY:
        (home / relative).unlink(missing_ok=True)
    return version


def uninstall(home):
    """Remove the layer's files; the configuration, shared with the user, stays."""
    for relative, _ in LSFG_PAYLOAD.values():
        (Path(home) / relative).unlink(missing_ok=True)


# -- decky-lsfg-vk's launch wrapper --------------------------------------------
def decky_lsfg_installed(home):
    """Whether decky-lsfg-vk, which keeps ~/.lsfg, is installed in Decky."""
    plugins = Path(home) / DECKY_PLUGINS
    for manifest in plugins.glob("*/plugin.json") if plugins.is_dir() else []:
        try:
            name = str(json.loads(manifest.read_text(encoding="utf-8")).get("name", ""))
        except (OSError, ValueError):
            continue
        if "lsfg" in name.lower():
            return True
    return False


def wrapper_workarounds(home, appid):
    """The workarounds decky-lsfg-vk's wrapper applies to this game, or None."""
    try:
        data = json.loads((Path(home) / LSFG_WRAPPER_STATE).read_text(encoding="utf-8"))
        state = data["apps"][str(appid)]["state"]
    except (OSError, ValueError, KeyError, TypeError):
        return None
    return state if isinstance(state, dict) else None


def release_wrapper(home, appid):
    """A game is leaving decky-lsfg-vk's wrapper for this plugin's launch options.

    Returns that game's workarounds from the wrapper (to carry over) and
    whether the wrapper itself went: only when it is decky-lsfg-vk's (its
    marker), decky-lsfg-vk is not installed to keep it, and no other game's
    launch options still run it, which would fail without it.
    """
    home = Path(home)
    state = wrapper_workarounds(home, appid)
    wrapper = home / LSFG_WRAPPER
    removed = False
    try:
        owned = (wrapper.is_file() and not wrapper.is_symlink()
                 and LSFG_WRAPPER_MARKER in "\n".join(wrapper.read_text(encoding="utf-8").splitlines()[:8]))
    except OSError:
        owned = False
    if owned and not decky_lsfg_installed(home):
        others = steam.apps_launching_with(home, LSFG_WRAPPER_PATTERN) - {str(appid)}
        if not others:
            wrapper.unlink(missing_ok=True)
            (home / LSFG_WRAPPER_STATE).unlink(missing_ok=True)
            removed = True
    return {"workarounds": state, "removed": removed}


# -- Lossless Scaling ----------------------------------------------------------
def lossless(home):
    """The user's Lossless Scaling on Steam: {installed, branch, dll, ready}.

    ``branch`` is the one picked in Steam (``public`` for none); the layer only
    has its DLL on the lsfg-vk branch.
    """
    for library in steam.library_folders(home):
        folder = library / "steamapps" / "common" / LOSSLESS_DIR
        manifest = library / "steamapps" / f"appmanifest_{LOSSLESS_APPID}.acf"
        if not folder.is_dir() and not manifest.is_file():
            continue
        state = {}
        try:
            state = steam.parse_vdf(manifest.read_text(encoding="utf-8", errors="replace")).get("appstate", {})
        except OSError:
            pass
        branch = (state.get("userconfig") or {}).get("betakey") or "public"
        dll = folder / LOSSLESS_DLL
        return {"installed": True, "branch": branch,
                "dll": str(dll) if dll.is_file() else None,
                "ready": branch == LOSSLESS_BRANCH and dll.is_file()}
    return {"installed": False, "branch": None, "dll": None, "ready": False}


# -- the configuration ---------------------------------------------------------
def config_path(home):
    return Path(home) / LSFG_CONFIG


def _profile(raw):
    """A profile with the keys decky-lsfg-vk knows, normalised."""
    profile = {**LSFG_PROFILE_DEFAULTS, **{k: v for k, v in raw.items() if k in LSFG_PROFILE_DEFAULTS}}
    active = raw.get("active_in", [])
    profile["active_in"] = [active] if isinstance(active, str) else [str(a) for a in active or [] if str(a)]
    profile["name"] = str(raw.get("name", ""))
    profile["pacing_mode"] = str(profile["pacing_mode"]).lower()
    profile["multiplier"] = int(profile["multiplier"])
    profile["flow_scale"] = float(profile["flow_scale"])
    for key in ("performance_mode", "override_present_mode", "preserve_swapchain_image_count"):
        profile[key] = bool(profile[key])
    return profile


def read_config(home):
    """{global: {dll, allow_fp16}, profiles: [...]}; an empty one where there is none.

    A v1 configuration counts as none, as decky-lsfg-vk treats it: v2 cannot
    read it. Any other version is not this plugin's to rewrite.
    """
    path = config_path(home)
    if not path.is_file():
        return {"global": {"dll": "", "allow_fp16": True}, "profiles": []}
    data = tomllib.loads(path.read_text(encoding="utf-8"))
    version = data.get("version")
    if version != 2:
        if version is None or (isinstance(version, (int, float)) and not isinstance(version, bool)
                               and version < 2) or version == "1":
            return {"global": {"dll": "", "allow_fp16": True}, "profiles": []}
        raise ValueError(f"lsfg-vk configuration version {version!r} is not supported")
    raw_global = data.get("global") or {}
    profiles = [_profile(raw) for raw in data.get("profile") or []
                if raw.get("name") or raw.get("active_in")]
    return {"global": {"dll": str(raw_global.get("dll") or ""),
                       "allow_fp16": bool(raw_global.get("allow_fp16", True))},
            "profiles": profiles}


def _value(value):
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, str):
        return '"' + value.replace("\\", "\\\\").replace('"', '\\"') + '"'
    if isinstance(value, list):
        return "[ " + ", ".join(_value(item) for item in value) + " ]"
    return str(value)


def render(config):
    """The configuration as decky-lsfg-vk writes it, profiles in name order."""
    lines = ["version = 2", "", "[global]"]
    if config["global"].get("dll"):
        lines.append(f"dll = {_value(config['global']['dll'])}")
    lines.append(f"allow_fp16 = {_value(bool(config['global'].get('allow_fp16', True)))}")
    profiles = sorted(config["profiles"], key=lambda p: p["name"]) or [_profile({})]
    for profile in profiles:
        lines += ["", "[[profile]]", f"name = {_value(profile['name'])}"]
        if profile["active_in"]:
            lines.append(f"active_in = {_value(profile['active_in'])}")
        lines += [f"{key} = {_value(profile[key])}" for key in LSFG_PROFILE_DEFAULTS]
    return "\n".join(lines) + "\n"


def _validate(home, content, environment):
    """lsfg-vk's own check of a configuration, when its CLI is there; raise when it refuses."""
    cli = Path(home) / LSFG_CLI
    if not (cli.is_file() and os.access(cli, os.X_OK)):
        return
    path = config_path(home)
    with tempfile.NamedTemporaryFile("w", encoding="utf-8", dir=path.parent, prefix=".conf.toml.",
                                     suffix=".tmp", delete=False) as handle:
        handle.write(content)
        temporary = Path(handle.name)
    try:
        result = subprocess.run([str(cli), "validate", "--config", str(temporary)], env=environment,
                                capture_output=True, text=True, timeout=10, check=False)
    except (OSError, subprocess.SubprocessError):
        return  # a CLI that does not run checks nothing; the file is written as decky-lsfg-vk writes it
    finally:
        temporary.unlink(missing_ok=True)
    if result.returncode != 0:
        raise ValueError((result.stdout + result.stderr).strip()[:600] or "lsfg-vk rejected the configuration")


def _game_index(config, appid):
    return next((i for i, p in enumerate(config["profiles"]) if p["active_in"] == [str(appid)]), None)


def game_profile(home, appid):
    """The profile that gives this game frame generation, or None."""
    config = read_config(home)
    index = _game_index(config, appid)
    return config["profiles"][index] if index is not None else None


def set_game_profile(home, appid, name, settings, dll=None, environment=None):
    """Turn frame generation on for a game with ``settings``, or off with None.

    On: the game's profile (any matching its app id alone) gets the settings,
    or a new one named after the game is added, renamed with the app id when
    another profile has that name. Off: that profile goes. Every other profile
    is kept. ``dll`` fills in the global DLL path when the one there is gone.
    """
    appid = str(appid)
    config = read_config(home)
    index = _game_index(config, appid)
    if settings is None:
        if index is None:
            return None
        config["profiles"].pop(index)
        profile = None
    else:
        if index is None:
            label = str(name or appid).strip() or appid
            if any(p["name"] == label for p in config["profiles"]):
                label = f"{label} ({appid})"
            current = {"name": label}
        else:
            current = config["profiles"].pop(index)
        profile = _profile({**current, **{k: v for k, v in settings.items() if k in LSFG_PROFILE_DEFAULTS},
                            "active_in": [appid]})
        if not 1 <= profile["multiplier"] <= 6:
            raise ValueError("배수는 끔(1)이나 2~6배여야 합니다.")
        if not 0.25 <= profile["flow_scale"] <= 1.0:
            raise ValueError("Flow Scale은 0.25~1.0이어야 합니다.")
        config["profiles"].append(profile)
    if dll and not Path(config["global"].get("dll") or "").is_file():
        config["global"]["dll"] = str(dll)
    content = render(config)
    path = config_path(home)
    path.parent.mkdir(parents=True, exist_ok=True)
    _validate(home, content, environment)
    partial = path.with_name(f".{path.name}.part")
    partial.write_text(content, encoding="utf-8")
    os.replace(partial, path)
    return profile
