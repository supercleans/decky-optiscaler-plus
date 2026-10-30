"""Install, detect and remove OptiScaler inside a game directory.

Mirrors what the official setup_linux.sh does — copy the release next to the
game executable and rename OptiScaler.dll to a proxy filename the game already
loads — but records a manifest and stashes every displaced file in a visible
backup folder, so an uninstall can put the game back exactly as it was.
"""

import json
import os
import shutil
import time
from pathlib import Path

from . import schema
from .inifile import IniFile
from .payload import sha256
from .constants import (
    BACKUP_DIR,
    CUSTOM_UPSCALER_DIR,
    DEFAULT_PROXY,
    DEFAULT_UPSCALER,
    ENGINE_HELIXSR,
    ENGINE_NIGHTLY,
    FFX_UPSCALER_AMD_FILE,
    FFX_UPSCALER_DLL,
    FSR4_MIN_SDK_VERSION,
    INI_NAME,
    LAUNCH_RECORD_NAME,
    LOG_NAME,
    MANIFEST_NAME,
    OPTIPATCHER_NAME,
    OPTI_DIR,
    PAYLOAD_DIRS,
    PLUGIN_SUBDIR,
    PROXY_FILENAMES,
    REFRAMEWORK_DLL,
    REFRAMEWORK_PD_PLUGIN,
    REFRAMEWORK_PD_ROOT_LIBS,
    RUNTIME_ARTIFACTS,
    UPSCALER_HLX_DLSS,
    UPSCALER_PRESETS,
)

DLL_MARKER = b"OptiScaler"
MIN_OPTISCALER_SIZE = 4 * 1024 * 1024


def _looks_like_optiscaler(path):
    """True if a proxy-named file is really an OptiScaler build."""
    try:
        if path.stat().st_size < MIN_OPTISCALER_SIZE:
            return False
        with open(path, "rb") as handle:
            while True:
                chunk = handle.read(1 << 20)
                if not chunk:
                    return False
                if DLL_MARKER in chunk:
                    return True
    except OSError:
        return False


def read_manifest(target_dir):
    path = Path(target_dir) / MANIFEST_NAME
    if not path.is_file():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None


def backup_dir(target_dir):
    return Path(target_dir) / BACKUP_DIR


def launch_record_path(target_dir):
    return Path(target_dir) / LAUNCH_RECORD_NAME


def read_launch_record(target_dir):
    """The Steam launch options this game had before OptiScaler went in.

    ``recorded`` is what separates "there was nothing there" from "nobody
    looked": an empty string is a real answer and the reason uninstalling can
    offer to clear the launch options outright, while a missing file means the
    install predates this record or Steam would not say, and only the override
    this plugin added can safely be taken back out.
    """
    path = launch_record_path(target_dir)
    if not path.is_file():
        return {"recorded": False, "value": ""}
    try:
        return {"recorded": True, "value": path.read_text(encoding="utf-8")}
    except OSError:
        return {"recorded": False, "value": ""}


def record_launch_options(target_dir, options, logger=None):
    """Keep the pre-install launch options, once.

    Write-once for the same reason ``_stash`` keeps the oldest backup: the value
    worth putting back is the one from before this plugin first touched the
    game, and a reinstall — or turning the launch-options step off and on again
    — must not overwrite it with the override we ourselves wrote.
    """
    path = launch_record_path(target_dir)
    if path.exists():
        return {"recorded": True, "value": read_launch_record(target_dir)["value"],
                "written": False}
    path.write_text(options or "", encoding="utf-8")
    if logger:
        logger.info("recorded previous launch options for %s", target_dir)
    return {"recorded": True, "value": options or "", "written": True}


def forget_launch_options(target_dir):
    """Drop the record. Called by uninstall: it belongs to one install."""
    path = launch_record_path(target_dir)
    existed = path.is_file()
    path.unlink(missing_ok=True)
    return existed


def detect(target_dir):
    """Report whether (and how) OptiScaler is installed in a directory."""
    target = Path(target_dir)
    result = {
        "path": str(target),
        "installed": False,
        "filename": None,
        "managed": False,
        "version": None,
        # Which nightly it came from (e.g. nightly-20261027); the version alone
        # is the same across nightlies. helixsr-<version> for HelixSR Scaler.
        "tag": None,
        # The OptiScaler build ("nightly" or "helixsr") and the upscaler it was
        # set up for, from the manifest; None for OptiScaler put in by hand.
        "engine": None,
        "upscaler": None,
        "installed_at": None,
        "ini_present": False,
        "ini_path": None,
        "log_present": False,
        "log_path": None,
        "candidates": [],
        "extra_proxies": [],
        "backup_dir": str(backup_dir(target)),
        "backed_up": [],
        "launch_record": {"recorded": False, "value": ""},
        "fsr4": {},
        # REFramework, for the RE Engine games that need it. Reported from the
        # folder rather than from the manifest so a copy the user put there
        # themselves counts — the step is "is REF present", not "did we install
        # REF", and re-installing over somebody's own working REF would be a
        # worse answer than leaving it alone.
        "reframework": {"installed": False, "revision": None, "managed": False},
    }
    if not target.is_dir():
        return result

    result["launch_record"] = read_launch_record(target)

    ini = target / INI_NAME
    result["ini_present"] = ini.is_file()
    result["ini_path"] = str(ini)
    log = target / LOG_NAME
    result["log_present"] = log.is_file()
    result["log_path"] = str(log)
    result["fsr4"] = fsr4_status(target)

    result["reframework"] = {
        "installed": (target / REFRAMEWORK_DLL).is_file(),
        # Which build went in is only knowable from what we recorded: the
        # stamp file is deliberately not installed next to the game.
        "revision": None,
        "managed": False,
    }

    stash = backup_dir(target)
    if stash.is_dir():
        result["backed_up"] = sorted(p.name for p in stash.iterdir())

    present = [name for name in PROXY_FILENAMES if (target / name).is_file()]
    result["candidates"] = present

    manifest = read_manifest(target)
    if manifest and manifest.get("filename"):
        name = manifest["filename"]
        if (target / name).is_file():
            result.update(
                installed=True,
                filename=name,
                managed=True,
                version=manifest.get("optiscaler_version"),
                tag=manifest.get("optiscaler_tag"),
                engine=manifest.get("engine"),
                upscaler=manifest.get("upscaler"),
                installed_at=manifest.get("installed_at"),
            )
            result["reframework"]["managed"] = bool(manifest.get("reframework"))
            result["reframework"]["revision"] = manifest.get("reframework_revision")
            result["extra_proxies"] = [p for p in present if p != name
                                       and _looks_like_optiscaler(target / p)]
            return result

    # Installed by hand or by another tool: identify by content.
    for name in present:
        if _looks_like_optiscaler(target / name):
            result.update(installed=True, filename=name, managed=False)
            result["extra_proxies"] = [
                p for p in present if p != name and _looks_like_optiscaler(target / p)
            ]
            break
    return result


def ffx_upscaler_info(target_dir):
    """The FidelityFX upscaler library OptiScaler loads from its own folder.

    Its file version is the FSR version the overlay's FFX box names, so it is
    shown on the game page rather than kept behind a verify step.

    In HelixSR Scaler that file is HLX FSR 4, which has no version resource;
    AMD's own sits beside it as ``*.amd.dll`` and is the one read.
    """
    dll = Path(target_dir) / FFX_UPSCALER_DLL
    amd = dll.parent / FFX_UPSCALER_AMD_FILE
    read = amd if amd.is_file() else dll
    version = pe_file_version(read) if read.is_file() else None
    return {
        "present": dll.is_file(),
        "name": read.name,
        "version": ".".join(str(n) for n in version) if version else None,
        # OptiScaler treats an SDK at or above 4.0.2 as providing FSR 4.
        "fsr4_capable": bool(version and version[:3] >= FSR4_MIN_SDK_VERSION[:3]),
        "hlx": amd.is_file(),
    }


def upscaler_of(target_dir):
    """The upscaler this folder was set up for; FSR 4 Lite for OptiScaler put in by hand."""
    return (read_manifest(target_dir) or {}).get("upscaler") or DEFAULT_UPSCALER


def preset_for(upscaler):
    return UPSCALER_PRESETS.get(upscaler) or UPSCALER_PRESETS[DEFAULT_UPSCALER]


def preset_state(target_dir):
    """Which of the upscaler preset's values the ini holds right now.

    Read back from the file, because OptiScaler's overlay can save over them:
    "applied" means the ini says so today, not that an install once wrote it.
    """
    ini = Path(target_dir) / INI_NAME
    values = IniFile(ini).to_dict() if ini.is_file() else {}
    keys = []
    for section, entries in preset_for(upscaler_of(target_dir)).items():
        for key, wanted in entries.items():
            actual = values.get(section, {}).get(key)
            keys.append({"section": section, "key": key, "wanted": wanted,
                         "actual": actual, "ok": actual == wanted})
    return {"applied": bool(values) and all(k["ok"] for k in keys), "keys": keys}


def fsr4_status(target_dir):
    """Whether this folder is set up for its upscaler: its preset in the ini.

    Named for FSR 4 Lite, which every install was before the upscaler could be
    picked; the others are judged against their own preset.
    """
    target = Path(target_dir)
    preset = preset_state(target)
    return {
        "upscaler": upscaler_of(target),
        "preset": preset,
        "ready": preset["applied"],
        "ffx": ffx_upscaler_info(target),
    }


def apply_preset(ini_path, extra=None, logger=None, upscaler=None):
    """Write the upscaler's preset (and ``extra`` changes) into an ini.

    ``upscaler`` defaults to the one the folder's manifest records, and to FSR
    4 Lite without one. Only keys the schema knows with values it accepts are
    written, so a nightly that renamed one degrades to "the rest still applies"
    rather than a failed install. Returns the (section, key) pairs written.
    """
    ini_path = Path(ini_path)
    if not ini_path.is_file():
        return []
    preset = preset_for(upscaler or upscaler_of(ini_path.parent))
    ini = IniFile(ini_path)
    written = []
    for section, values in list(preset.items()) + list((extra or {}).items()):
        for key, value in values.items():
            meta = schema.option(section, key)
            if meta is not None and not schema.valid(meta, value):
                if logger:
                    logger.warning("preset value %s.%s=%s rejected", section, key, value)
                continue
            ini.set(section, key, value)
            written.append((section, key))
    if written:
        ini.save()
    return written


def install_plugin_asi(target_dir, source, name, logger=None):
    """Drop an ASI into the folder OptiScaler loads plugins from.

    OptiScaler loads every .asi there, with ``LoadAsiPlugins`` on as every
    preset has it, which is how OptiPatcher gets in.
    """
    source = Path(source)
    if not source.is_file():
        return {"ok": False, "error": f"{name} missing at {source}"}
    destination = Path(target_dir) / PLUGIN_SUBDIR / name
    destination.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(source, destination)
    if logger:
        logger.info("installed %s at %s", name, destination)
    return {"ok": True, "path": str(destination)}



def add_files(target_dir, sources, logger=None, reframework_revision=None):
    """Copy extra files into an existing install and register them for removal.

    The same contract as everything else this plugin puts in a game folder:
    anything displaced is stashed, everything added is written into the
    manifest, and uninstall reverses both. Used to add REFramework to a game
    that is already set up, or to retry a download that failed the first time.

    A game with no manifest — OptiScaler installed by hand, or by another tool —
    still gets the files. It is the tracking that is unavailable there, not the
    install, and refusing would be refusing the only thing the user asked for.
    """
    target = Path(target_dir)
    if not target.is_dir():
        raise NotADirectoryError(f"install target does not exist: {target}")

    manifest = read_manifest(target) or {}
    backups = dict(manifest.get("backups") or {})
    files = list(manifest.get("files") or [])
    added = []

    for source in sources:
        source = Path(source)
        if not source.is_file():
            raise FileNotFoundError(f"missing {source}")
        name = source.name
        destination = target / name
        if destination.exists() and name not in backups and name not in files:
            backups[name] = _stash(target, destination, logger)
        shutil.copy2(source, destination)
        if name not in files:
            files.append(name)
        added.append(name)
        if logger:
            logger.info("installed %s", name)

    if manifest:
        manifest["files"] = files
        manifest["backups"] = backups
        if REFRAMEWORK_DLL in added:
            manifest["reframework"] = True
            manifest["reframework_revision"] = reframework_revision
        if any(name in added for name in REFRAMEWORK_PD_ROOT_LIBS):
            # A reinstall has to keep putting these at the root.
            manifest["pd_upscaler"] = True
        (target / MANIFEST_NAME).write_text(json.dumps(manifest, indent=2), encoding="utf-8")

    return {"ok": True, "path": str(target), "files": added, "tracked": bool(manifest)}


def remove_files(target_dir, names, logger=None):
    """Take specific files back out, restoring anything they displaced.

    The counterpart to `add_files`, and the reason it exists is Monster Hunter
    Wilds: REFramework is a 23 MB third-party DLL that hooks the engine, and
    when a game stops booting after an install there is no way to find out
    whether that was OptiScaler or REF unless one of them can be taken out on
    its own. Bundling them into a single all-or-nothing install left the user
    with a game that would not start and no way to bisect it.
    """
    target = Path(target_dir)
    if not target.is_dir():
        raise NotADirectoryError(f"path does not exist: {target}")

    manifest = read_manifest(target) or {}
    files = list(manifest.get("files") or [])
    backups = dict(manifest.get("backups") or {})
    removed = []
    restored = []

    for name in names:
        path = target / name
        if path.is_file():
            path.unlink()
            removed.append(name)
        if name in files:
            files.remove(name)
        # Whatever this displaced goes back, exactly as a full uninstall does.
        if backups.pop(name, None):
            stashed = backup_dir(target) / name
            if stashed.is_file():
                shutil.move(str(stashed), str(path))
                restored.append(name)
                if logger:
                    logger.info("restored original %s", name)

    if manifest:
        manifest["files"] = files
        manifest["backups"] = backups
        if REFRAMEWORK_DLL in removed:
            manifest["reframework"] = False
            manifest["reframework_revision"] = None
        (target / MANIFEST_NAME).write_text(json.dumps(manifest, indent=2), encoding="utf-8")

    return {"ok": True, "removed": removed, "restored": restored}


def _stash(target, path, logger=None):
    """Move a file or directory into the backup folder; returns its name."""
    stash = backup_dir(target)
    stash.mkdir(parents=True, exist_ok=True)
    destination = stash / path.name
    if destination.exists():
        # An earlier install already preserved the original; keep the oldest.
        if path.is_dir():
            shutil.rmtree(path, ignore_errors=True)
        else:
            path.unlink(missing_ok=True)
        return path.name
    shutil.move(str(path), str(destination))
    if logger:
        logger.info("backed up %s to %s/", path.name, BACKUP_DIR)
    return path.name


#: Names a reinstall leaves alone even when an older manifest listed them as
#: ours: they belong to things that are still installed.
STALE_KEEP = {REFRAMEWORK_DLL, REFRAMEWORK_PD_PLUGIN, MANIFEST_NAME, INI_NAME,
              LAUNCH_RECORD_NAME, BACKUP_DIR}


def _drop_stale(old_files, old_dirs, keep_files, keep_dirs, target, backups,
                logger=None):
    """Remove what the previous install put down and this one no longer uses.

    Only names the previous manifest recorded as ours are touched, so nothing
    the game shipped is at risk. A name that had displaced a game file is moved
    back instead of deleted, exactly as an uninstall would. Switching between
    the nightly and HelixSR Scaler, or dropping OptiPatcher, goes through here.
    """
    for name in sorted(old_files):
        if name in keep_files or name in STALE_KEEP:
            continue
        path = target / name
        if backups.pop(name, None):
            stashed = backup_dir(target) / Path(name).name
            if stashed.is_file():
                path.parent.mkdir(parents=True, exist_ok=True)
                shutil.move(str(stashed), str(path))
                if logger:
                    logger.info("restored original %s while upgrading", name)
            continue
        if path.is_file():
            path.unlink(missing_ok=True)
            if logger:
                logger.info("removed stale %s", name)
    for name in sorted(old_dirs):
        if name in keep_dirs:
            continue
        path = target / name
        if path.is_dir():
            shutil.rmtree(path, ignore_errors=True)
            if logger:
                logger.info("removed stale %s/", name)


def engine_for(upscaler):
    """The OptiScaler build an upscaler installs with: HelixSR Scaler for HLX DLSS."""
    return ENGINE_HELIXSR if upscaler == UPSCALER_HLX_DLSS else ENGINE_NIGHTLY


def install(target_dir, payload_root, filename=DEFAULT_PROXY, preserve_ini=True,
            logger=None, optipatcher=None, reframework_files=None,
            reframework_revision=None, release=None, pd_upscaler=False,
            upscaler=DEFAULT_UPSCALER, extra_dirs=None, ffx_upscalers=None):
    """Copy OptiScaler into target_dir under the given proxy filename.

    ``payload_root`` is the unpacked nightly, or for HLX DLSS HelixSR Scaler
    out of the user's HelixSR build, laid out the same way. ``upscaler`` picks
    the preset written into the ini. ``extra_dirs`` are further folders to put
    next to the proxy, by name: HelixSR's own folder, for HLX DLSS.
    ``ffx_upscalers`` are ``{"path", "name", "variant", "tag", "main"}`` of
    FidelityFX upscaler builds: the one with ``main`` takes the payload's own
    upscaler's place, which every FFX backend (DX12, and DX11/Vulkan through
    ffx_12) runs; the others go in as OptiScaler custom upscalers.

    ``release`` is the build it came from ({"tag", "version"}), recorded in
    the manifest so the game page can say which build a game has.

    ``optipatcher`` is the path to OptiPatcher.asi. It goes in OptiScaler's
    plugin folder and lets OptiScaler expose DLSS/DLSS-FG inputs in the games it
    has patterns for, without DXGI spoofing.

    ``pd_upscaler`` marks a game set up through REFramework's pd-upscaler branch
    and PDPerfPlugin: those look for libxess.dll at the game root, where v10 no
    longer puts it, so it is copied there too. Remembered in the manifest, so a
    reinstall that does not know about the plan (a nightly update) keeps it.

    ``reframework_files`` are the already-downloaded REFramework files for the
    RE Engine games that cannot host OptiScaler without it. They go in through
    the same ``place`` as everything else, on purpose: that is what puts them in
    the manifest, stashes anything they displace, and takes them back out on
    uninstall. A mod installed off to one side of that machinery is a mod this
    plugin cannot promise to remove.
    """
    if filename not in PROXY_FILENAMES:
        raise ValueError(f"unsupported filename: {filename}")

    target = Path(target_dir)
    payload = Path(payload_root)
    release = release or {}
    if not target.is_dir():
        raise NotADirectoryError(f"install target does not exist: {target}")
    if not os.access(target, os.W_OK):
        raise PermissionError(f"no write permission for {target}")
    source_dll = payload / "OptiScaler.dll"
    if not source_dll.is_file():
        raise FileNotFoundError(f"payload incomplete, missing {source_dll}")

    previous = detect(target)
    old_manifest = read_manifest(target) or {}
    old_files = set(old_manifest.get("files") or [])
    old_dirs = set(old_manifest.get("dirs") or [])
    backups = dict(old_manifest.get("backups") or {})
    created = []
    created_dirs = []
    # What the folder held before this install started, so a folder this
    # install creates is never mistaken for one of the game's and stashed.
    pre_existing = {entry.name for entry in target.iterdir()}

    # Remove a previous install under a different filename so the game does not
    # end up loading OptiScaler twice.
    restored_proxies = set()
    for stale in previous.get("candidates", []):
        if stale == filename:
            continue
        stale_path = target / stale
        if not _looks_like_optiscaler(stale_path):
            continue
        stale_path.unlink(missing_ok=True)
        # If we displaced the game's own dll to install there, put it back now
        # rather than leaving the game without it until uninstall.
        if backups.pop(stale, None):
            stashed = backup_dir(target) / stale
            if stashed.is_file():
                shutil.move(str(stashed), str(stale_path))
                if logger:
                    logger.info("restored original %s while moving proxy", stale)
            # The name is the game's again, but the previous manifest still
            # lists it as ours: without this the stale sweep below would delete
            # the dll just put back.
            restored_proxies.add(stale)
        elif logger:
            logger.info("removed previous OptiScaler proxy %s", stale)

    def place(src, dest_name):
        dest = target / dest_name
        dest.parent.mkdir(parents=True, exist_ok=True)
        if dest.exists() and dest_name not in backups and dest_name not in created:
            # Only stash files that belong to the game, not our own leftovers.
            if dest_name not in old_files and not _looks_like_optiscaler(dest):
                backups[dest_name] = _stash(target, dest, logger)
        shutil.copy2(src, dest)
        if dest_name not in created:
            created.append(dest_name)

    place(source_dll, filename)

    ini_path = target / INI_NAME
    ini_preserved = preserve_ini and ini_path.is_file()
    if not ini_preserved:
        shutil.copy2(payload / INI_NAME, ini_path)
    if INI_NAME not in created:
        created.append(INI_NAME)

    engine = engine_for(upscaler)
    # The nightly and HelixSR Scaler ship different files under the same
    # folder names (HLX FSR 4 and AMD's .amd.dll, the Scaler's OptiPatcher), so
    # switching between them starts our own folders over rather than merging.
    old_engine = old_manifest.get("engine") if old_manifest else engine
    fresh = old_engine != engine

    folders = [(name, payload / name) for name in PAYLOAD_DIRS]
    folders += [(name, Path(src)) for name, src in (extra_dirs or {}).items()]
    for name, src in folders:
        if not src.is_dir():
            continue
        dest = target / name
        if (dest.exists() and name in pre_existing
                and name not in backups and name not in old_dirs):
            backups[name] = _stash(target, dest, logger)
        elif fresh and name in old_dirs and dest.is_dir():
            shutil.rmtree(dest, ignore_errors=True)
        shutil.copytree(src, dest, dirs_exist_ok=True)
        if name not in created_dirs:
            created_dirs.append(name)

    # Custom upscalers go in OptiScaler/custom/<name>/ffx; the "main" one over
    # the payload's own upscaler, just copied. The previous install's custom
    # folders go first, so a build that is gone, or a switch to HLX DLSS,
    # leaves no stale entry; folders the user put there are not ours to touch,
    # and a main one was overwritten by the payload already.
    custom_root = target / OPTI_DIR / CUSTOM_UPSCALER_DIR
    for old in old_manifest.get("ffx_upscalers") or []:
        path = target / old.get("path", "")
        if old.get("path") and not old.get("main") and custom_root in path.parents and path.is_file():
            shutil.rmtree(path.parent.parent, ignore_errors=True)
    ffx_records = []
    for ffx_upscaler in ffx_upscalers or []:
        name = ffx_upscaler["name"]
        main = bool(ffx_upscaler.get("main"))
        destination = (target / FFX_UPSCALER_DLL if main
                       else custom_root / name / "ffx" / Path(FFX_UPSCALER_DLL).name)
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(ffx_upscaler["path"], destination)
        ffx_records.append({"name": name, "variant": ffx_upscaler.get("variant"),
                            "tag": ffx_upscaler.get("tag"), "main": main,
                            "path": destination.relative_to(target).as_posix(),
                            "sha256": sha256(destination)})
        if logger:
            logger.info("%s upscaler %s (%s) added", "FidelityFX" if main else "custom",
                        name, ffx_upscaler.get("tag"))
    try:
        if custom_root.is_dir() and not any(custom_root.iterdir()):
            custom_root.rmdir()
    except OSError:
        pass

    # REFramework, for the games whose wiki entry says OptiScaler does nothing
    # without it. One file (plus the revision stamp REF itself writes), placed
    # next to the executable exactly as REF's own instructions describe.
    ref_result = {"installed": False, "files": [], "error": None,
                  "revision": reframework_revision}
    for source in reframework_files or []:
        source = Path(source)
        if not source.is_file():
            ref_result["error"] = f"missing {source.name}"
            continue
        place(source, source.name)
        ref_result["files"].append(source.name)
    ref_result["installed"] = REFRAMEWORK_DLL in ref_result["files"]
    # A reinstall that brings no REFramework of its own - updating to a newer
    # nightly, say - keeps tracking the one already installed from here, so
    # an uninstall still takes it out and puts the game's own dll back. The
    # same goes for PDPerfPlugin.dll when it came with it.
    if not reframework_files and old_manifest.get("reframework"):
        kept = [name for name in (REFRAMEWORK_DLL, REFRAMEWORK_PD_PLUGIN)
                if name in old_files and (target / name).is_file()]
        if REFRAMEWORK_DLL in kept:
            created.extend(name for name in kept if name not in created)
            ref_result.update(installed=True, files=kept,
                              revision=old_manifest.get("reframework_revision"))

    pd_upscaler = bool(pd_upscaler or old_manifest.get("pd_upscaler"))
    if pd_upscaler:
        for name in REFRAMEWORK_PD_ROOT_LIBS:
            source = payload / OPTI_DIR / name
            if source.is_file():
                place(source, name)

    # OptiPatcher: an optional ASI from the OptiScaler project. Some games
    # (Red Dead Redemption 2 among them) need it to expose their DLSS inputs.
    patcher_result = {"installed": False, "error": None}
    if optipatcher:
        outcome = install_plugin_asi(target, optipatcher, OPTIPATCHER_NAME, logger)
        if outcome.get("ok"):
            patcher_result["installed"] = True
            created.append(f"{PLUGIN_SUBDIR}/{OPTIPATCHER_NAME}")
        else:
            patcher_result["error"] = outcome.get("error")
            if logger:
                logger.warning("optipatcher unavailable: %s", outcome.get("error"))

    # What the previous install put down and this one did not. Names just
    # handed back to the game are not ours to sweep.
    _drop_stale(old_files, old_dirs, set(created) | restored_proxies,
                set(created_dirs), target, backups, logger)

    # HelixSR Scaler ships its own OptiPatcher in the plugins folder. That copy
    # is used as it comes: it is part of the build the user set up.
    bundled_patcher = (engine == ENGINE_HELIXSR and not patcher_result["installed"]
                       and (target / PLUGIN_SUBDIR / OPTIPATCHER_NAME).is_file())

    # The preset goes in on every install, a preserved ini included: it is
    # what the upscaler picked means, ASI loading for OptiPatcher with it.
    preset = apply_preset(ini_path, None, logger, upscaler)

    manifest = {
        "plugin": "decky-optiscaler",
        "engine": engine,
        "upscaler": upscaler,
        "optipatcher": patcher_result["installed"],
        "optipatcher_bundled": bundled_patcher,
        # The FidelityFX upscaler builds put beside the payload's.
        "ffx_upscalers": ffx_records,
        "reframework": ref_result["installed"],
        "reframework_revision": ref_result["revision"],
        "pd_upscaler": pd_upscaler,
        "optiscaler_version": release.get("version"),
        "optiscaler_tag": release.get("tag"),
        "filename": filename,
        "installed_at": time.time(),
        "files": created,
        "dirs": created_dirs,
        "backups": backups,
        "backup_dir": BACKUP_DIR,
    }
    (target / MANIFEST_NAME).write_text(json.dumps(manifest, indent=2), encoding="utf-8")

    return {
        "path": str(target),
        "filename": filename,
        "version": release.get("version"),
        "tag": release.get("tag"),
        "engine": engine,
        "upscaler": upscaler,
        "ffx_upscalers": ffx_records,
        "ini_preserved": ini_preserved,
        "preset_written": [f"{section}.{key}" for section, key in preset],
        "optipatcher": {**patcher_result, "bundled": bundled_patcher},
        "reframework": ref_result,
        "launch_option": launch_option(filename),
        "files": created,
        "dirs": created_dirs,
        "backups": backups,
        "backup_dir": str(backup_dir(target)),
        "fsr4": fsr4_status(target),
    }


def mapped_files():
    """Every file some running process has mapped, from /proc/*/maps.

    Wine maps a game's executable and the DLLs it loaded, OptiScaler's
    included, so a game folder that appears here belongs to a running game.
    Read once and checked against many folders. Empty where there is no /proc.
    """
    found = set()
    for maps in Path("/proc").glob("[0-9]*/maps"):
        try:
            text = maps.read_text(errors="replace")
        except (OSError, ProcessLookupError):
            continue
        for line in text.splitlines():
            fields = line.split(maxsplit=5)
            if len(fields) == 6 and fields[5].startswith("/"):
                found.add(fields[5])
    return found


def in_use(target_dir, mapped=None):
    """Whether a running process has a file from this folder mapped."""
    prefix = os.path.join(str(Path(target_dir).resolve()), "")
    return any(path.startswith(prefix) for path in (mapped if mapped is not None else mapped_files()))


def launch_option(filename):
    """Steam launch options needed for Wine to load the proxy dll."""
    if filename.lower().endswith(".asi"):
        return "%command%"  # .asi is loaded by an ASI loader, no override needed
    stem = filename[:-4] if filename.lower().endswith(".dll") else filename
    return f'WINEDLLOVERRIDES="{stem}=n,b" %command%'


def uninstall(target_dir, remove_ini=True, logger=None):
    """Remove OptiScaler, restoring everything it displaced."""
    target = Path(target_dir)
    if not target.is_dir():
        raise NotADirectoryError(f"path does not exist: {target}")

    manifest = read_manifest(target)
    removed = []
    restored = []

    if manifest:
        for name in manifest.get("files", []):
            if name == INI_NAME and not remove_ini:
                continue
            path = target / name
            if path.is_file():
                path.unlink()
                removed.append(name)
        for name in manifest.get("dirs", []):
            path = target / name
            if path.is_dir():
                shutil.rmtree(path, ignore_errors=True)
                removed.append(name + "/")
    else:
        # Unmanaged install: fall back to the file set setup_linux.sh creates.
        for name in PROXY_FILENAMES:
            path = target / name
            if path.is_file() and _looks_like_optiscaler(path):
                path.unlink()
                removed.append(name)
        for name in PAYLOAD_DIRS + ["DlssOverrides"]:
            path = target / name
            if path.is_dir():
                shutil.rmtree(path, ignore_errors=True)
                removed.append(name + "/")
        if remove_ini and (target / INI_NAME).is_file():
            (target / INI_NAME).unlink()
            removed.append(INI_NAME)

    for name in RUNTIME_ARTIFACTS + ["remove_optiscaler.sh"]:
        path = target / name
        if path.is_file():
            path.unlink()
            removed.append(name)

    # The record of what Steam was passing before is ours and belongs to this
    # install; whoever asked for the uninstall has already been shown it.
    if forget_launch_options(target):
        removed.append(LAUNCH_RECORD_NAME)

    restored.extend(restore_backups(target, logger))

    manifest_path = target / MANIFEST_NAME
    if manifest_path.is_file():
        manifest_path.unlink()

    if logger:
        logger.info(
            "uninstalled OptiScaler from %s (%d removed, %d restored)",
            target, len(removed), len(restored),
        )
    return {
        "path": str(target),
        "removed": removed,
        "restored": restored,
        "backup_dir": str(backup_dir(target)),
    }


def restore_backups(target_dir, logger=None):
    """Move everything in the backup folder back, then drop the folder."""
    target = Path(target_dir)
    restored = []

    stash = backup_dir(target)
    if stash.is_dir():
        for item in sorted(stash.iterdir()):
            destination = target / item.name
            if destination.exists():
                if destination.is_dir():
                    shutil.rmtree(destination, ignore_errors=True)
                else:
                    destination.unlink()
            shutil.move(str(item), str(destination))
            restored.append(item.name)
            if logger:
                logger.info("restored %s from %s/", item.name, BACKUP_DIR)
        try:
            stash.rmdir()
        except OSError:
            if logger:
                logger.warning("%s/ not empty, leaving it in place", BACKUP_DIR)
    return restored


def pe_file_version(path):
    """Read a PE file's VS_FIXEDFILEINFO version, or None.

    Used to report which FidelityFX SDK — and therefore which FSR version — is
    actually sitting in the game folder.
    """
    try:
        data = Path(path).read_bytes()
    except OSError:
        return None
    marker = data.find(b"\xbd\x04\xef\xfe")
    if marker < 0 or marker + 16 > len(data):
        return None
    import struct

    try:
        minor, major, build, patch = struct.unpack("<HHHH", data[marker + 8 : marker + 16])
    except struct.error:
        return None
    return (major, minor, patch, build)


def verify_install(target_dir, payload_root, release=None):
    """Check that every file of the release really landed in the game folder.

    Answers the practical question "did the install actually override what the
    game shipped?" by comparing sizes against the unpacked release, and the
    driver libraries against their pinned hashes. A game installed from an
    older nightly than ``release`` is reported as outdated rather than broken:
    its files are whole, they are just not today's.
    """
    target = Path(target_dir)
    payload = Path(payload_root)
    manifest = read_manifest(target) or {}
    release = release or {}
    entries = []

    def record(name, destination, expected_size, matches):
        present = destination.is_file()
        entries.append({
            "name": name,
            "present": present,
            "matches_payload": bool(present and matches),
            "size": destination.stat().st_size if present else 0,
            "expected_size": expected_size,
        })

    if manifest.get("filename"):
        source = payload / "OptiScaler.dll"
        destination = target / manifest["filename"]
        size = source.stat().st_size if source.is_file() else 0
        record(manifest["filename"], destination, size,
               destination.is_file() and destination.stat().st_size == size)

    # A build put over the payload's own upscaler is checked as itself, below.
    replaced = {r.get("path") for r in manifest.get("ffx_upscalers") or [] if r.get("main")}
    for folder in PAYLOAD_DIRS:
        root = payload / folder
        if not root.is_dir():
            continue
        for source in sorted(p for p in root.rglob("*") if p.is_file()):
            name = source.relative_to(payload).as_posix()
            if name in replaced:
                continue
            destination = target / name
            size = source.stat().st_size
            record(name, destination, size,
                   destination.is_file() and destination.stat().st_size == size)

    for custom in manifest.get("ffx_upscalers") or []:
        if not custom.get("path"):
            continue
        # A custom upscaler, or the build over the payload's, against what went in.
        destination = target / custom["path"]
        record(custom["path"], destination, 0,
               destination.is_file() and sha256(destination) == custom.get("sha256"))

    installed_tag = manifest.get("optiscaler_tag")
    outdated = bool(installed_tag and release.get("tag") and installed_tag != release["tag"])
    problems = [e["name"] for e in entries if not e["present"] or not e["matches_payload"]]
    return {
        "path": str(target),
        "files": entries,
        # Size differences are what a newer nightly looks like, so they only
        # count as problems against the build the game was installed from.
        "problems": [] if outdated else problems,
        "complete": outdated or not problems,
        "outdated": outdated,
        "installed_tag": installed_tag,
        "current_tag": release.get("tag"),
        "ffx_upscaler": ffx_upscaler_info(target),
        "fsr4": fsr4_status(target),
    }
