"""Facade tying the backend modules into the API the frontend calls."""

import asyncio
import json
import os
import shutil
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from . import (autoplan, compat, dropin, helixsr, hlx, hlxbuild, installer, jobs, monitor,
               reframework, steam)
from .constants import (
    CHANNEL_BASELINE,
    CHANNEL_LIST_TTL,
    CHANNELS,
    CUSTOM_AMD_NAME,
    CUSTOM_UPSCALER_NAMES,
    CYBOMAN_VARIANTS,
    DEFAULT_PROXY,
    DEFAULT_UPSCALER,
    DEVICE_ALLOWED_UPSCALERS,
    DEVICE_UPSCALERS,
    DROPIN_VARIANTS,
    ENGINE_HELIXSR,
    FFX_UPSCALER_DLL,
    HELIXSR_DESKTOP_DATA,
    HELIXSR_DIR,
    HELIXSR_DLL,
    HELIXSR_TOOLS_DIR,
    INI_NAME,
    OPTIPATCHER_NAME,
    PLUGIN_SUBDIR,
    PROXY_FILENAMES,
    REFRAMEWORK_DLL,
    REFRAMEWORK_PD_PLUGIN,
    REFRAMEWORK_PD_PLUGIN_DROP_DEPTH,
    REFRAMEWORK_PD_PLUGIN_DROP_DIR,
    REFRAMEWORK_PD_PLUGIN_NAME,
    REFRAMEWORK_PD_PLUGIN_SHA256,
    REFRAMEWORK_PD_PLUGIN_URL,
    REFRAMEWORK_PD_ROOT_LIBS,
    RUNTIME_DOWNLOADS,
    UPSCALER_FSR4_LITE,
    UPSCALER_HLX_DLSS,
    UPSCALER_HLX_FSR4,
    UPSCALER_LITE_LOSSY,
    UPDATE_CHECK_TTL,
    UPSCALERS,
)
from .inifile import IniFile
from .nightly import NightlyChannel
from .optipatcher import OptiPatcherChannel
from .updates import PluginUpdates
from .payload import Payload
from .schema import SCHEMA, valid as _valid
from .settings import Settings
from .sysinfo import gpu_info
from .wiki import WikiClient


class OptiScalerService:
    def __init__(self, plugin_dir, settings_dir, runtime_dir, home, logger):
        self.plugin_dir = Path(plugin_dir)
        self.runtime_dir = Path(runtime_dir)
        self.home = Path(home)
        self.log = logger

        self.settings = Settings(Path(settings_dir) / "settings.json")
        # OptiScaler itself comes from the nightly channel, downloaded on the
        # first install and shared by every game after it.
        self.nightly = NightlyChannel(self.runtime_dir / "nightly")
        # This plugin's own releases, against the version that is running.
        self.updates = PluginUpdates(*self._plugin_identity())
        self.payload = Payload(self.nightly, self.runtime_dir / "payload")
        # OptiPatcher's rolling build, the same way: downloaded by the first
        # install that wants it.
        self.optipatcher = OptiPatcherChannel(self.runtime_dir / "optipatcher")
        # The bundled copy is the floor: a Deck that has never reached the wiki
        # still gets a compatibility list rather than "no entry matched" for
        # every game it owns.
        self.wiki = WikiClient(
            self.runtime_dir / "wiki-cache",
            self.plugin_dir / "defaults" / "compat-list.json",
        )
        self._payload_lock = asyncio.Lock()
        self._mutation_lock = asyncio.Lock()
        # Background wiki refreshes in flight, by key. Answers come from cache
        # and the network never sits in front of one; this is what keeps the
        # cache current behind them, single-flight so a page opened three times
        # does not download three times.
        self._wiki_jobs = set()
        # Folder scans behind the compatibility badges, by game path, with the
        # (folder mtime, size on disk) they were taken at.
        self._compat_scans = {}
        # The phone-to-Deck upload page for PDPerfPlugin.dll, while one is open.
        self._pd_upload = None
        # Each channel's release list, by channel: (when, builds). Settings
        # asks every time it opens; the API allows 60 requests an hour.
        self._channel_lists = {}
        # HLX DLSS being built by HelixSR's setup, when HelixSR Desktop has
        # not built it: one at a time, its state read by the UI.
        self.hlx_build = hlxbuild.Build()
        self._hlx_build_task = None
        # Setting the plugin up, or updating one of its downloads: one at a
        # time, its steps read by the UI. When the channels were last asked
        # whether a newer build is out, and what went wrong if it failed.
        self.job = jobs.Job()
        self._job_task = None
        self._updates_checked_at = None
        self._update_error = None

    # -- helpers ---------------------------------------------------------
    @staticmethod
    async def _run(func, *args, **kwargs):
        return await asyncio.to_thread(func, *args, **kwargs)

    async def ensure_payload(self, force=False):
        """The unpacked nightly to install from; ``force`` checks for a newer one.

        The build picked in Settings, when there is one, instead of the newest.
        """
        async with self._payload_lock:
            root = await self._run(self.payload.ensure, force, self.log, self.pinned("nightly"))
            if force:
                # "Check now" asks about OptiPatcher too. A failure there is
                # its own, kept in its status, and not the nightly's.
                try:
                    await self._run(self.optipatcher.ensure, True, self.log)
                except Exception:
                    pass
            return str(root)

    def release(self):
        """Which nightly the unpacked payload is, for manifests and reports."""
        info = self.nightly.current() or {}
        return {"tag": info.get("tag"), "version": info.get("version")}

    # -- download versions -----------------------------------------------
    def pinned(self, channel):
        """The build picked in Settings for ``channel``, or None for the newest."""
        return self.settings.get_pref(f"channel_version:{channel}") or None

    def channel_baseline(self, channel):
        """The channel's newest build when this plugin was built, or {}."""
        try:
            data = json.loads((self.plugin_dir / "defaults" / CHANNEL_BASELINE)
                              .read_text(encoding="utf-8"))
            entry = data.get(channel)
            return entry if isinstance(entry, dict) and entry.get("tag") else {}
        except (OSError, ValueError, AttributeError):
            return {}

    def _downloaded_tags(self, channel):
        if channel == "nightly":
            current = self.nightly.current()
            return {current["tag"]} if current else set()
        if channel == "helixsr":
            return hlx.kept(self.helixsr_cache())
        cache = self.dropin_cache()
        return ({d.name for d in cache.iterdir() if d.is_dir() and not d.name.endswith(".part")}
                if cache.is_dir() else set())

    async def get_channel_versions(self, channel):
        """The builds ``channel`` can be pinned to, newest first.

        The one this plugin was built against and every one published since.
        Offline, only what is known without the network: that build, the one
        pinned and the ones already downloaded.
        """
        if channel not in CHANNELS:
            return {"ok": False, "error": f"unknown channel {channel}"}
        baseline = self.channel_baseline(channel)
        pinned = self.pinned(channel)
        downloaded = await self._run(self._downloaded_tags, channel)
        error = None
        try:
            when, found = self._channel_lists.get(channel, (0, None))
            if found is None or time.time() - when >= CHANNEL_LIST_TTL:
                found = await self._run({"nightly": self.nightly.releases,
                                         "dropin": dropin.releases,
                                         "helixsr": hlx.releases}[channel])
                self._channel_lists[channel] = (time.time(), found)
            since = baseline.get("published_at")
            # ISO 8601 in UTC sorts as text.
            versions = [{"tag": r["tag"], "published_at": r.get("published_at")} for r in found
                        if not since or (r.get("published_at") or "") >= since]
        except Exception as exc:
            error = f"{type(exc).__name__}: {exc}"
            versions = [{"tag": tag, "published_at": None}
                        for tag in sorted({baseline.get("tag"), pinned, *downloaded} - {None},
                                          reverse=True)]
        for version in versions:
            version["baseline"] = version["tag"] == baseline.get("tag")
            version["downloaded"] = version["tag"] in downloaded
        return {"ok": True, "channel": channel, "pinned": pinned,
                "baseline": baseline.get("tag"), "versions": versions, "error": error}

    async def set_channel_version(self, channel, tag=None):
        """Pin ``channel`` to ``tag``; None goes back to the build set up, and its updates."""
        if channel not in CHANNELS:
            return {"ok": False, "error": f"unknown channel {channel}"}
        await self._run(self.settings.set_pref, f"channel_version:{channel}", tag or None)
        return {"ok": True, "channel": channel, "pinned": tag or None}

    def nightly_target(self):
        """The nightly tag games are set up from: the pinned one, else the download."""
        return self.pinned("nightly") or self.release()["tag"]

    @staticmethod
    def default_upscaler():
        """The upscaler to start a game with on this machine."""
        return DEVICE_UPSCALERS.get(gpu_info().get("device"), DEFAULT_UPSCALER)

    @staticmethod
    def allowed_upscalers():
        """The upscalers this machine may pick, every one but on a BC-250."""
        return DEVICE_ALLOWED_UPSCALERS.get(gpu_info().get("device"), UPSCALERS)

    def _refuse_on_device(self, upscaler):
        """Why ``upscaler`` cannot go in on this machine, or None."""
        if upscaler in self.allowed_upscalers():
            return None
        return f"이 기기에서는 {upscaler}을(를) 쓸 수 없습니다. HLX FSR 4나 HLX DLSS를 고르세요."

    def helixsr_build(self):
        """The HelixSR build HLX DLSS comes from: HelixSR Desktop's, else the plugin's."""
        return helixsr.find(self.home, self.helixsr_cache())

    async def get_helixsr_status(self):
        return await self._run(self.helixsr_build)

    def _helixsr_source(self):
        """(scaler folder, release, HelixSR folder) for an HLX DLSS install, or raise."""
        build = self.helixsr_build()
        if not build.get("found") or not build["dlss_ready"]:
            raise FileNotFoundError(
                "HLX DLSS가 아직 빌드되지 않았습니다. 설정의 HelixSR 항목에서 HLX DLSS를 빌드하거나, "
                "HelixSR Desktop으로 HelixSR를 한 번 설정한 뒤 다시 시도하세요.")
        # The Scaler's own version, where a nightly records OptiScaler's; the
        # tag names the HelixSR build, which is what an update moves to.
        release = {"tag": helixsr.tag(build), "version": build["scaler_version"]}
        return build["scaler_dir"], release, build["helixsr_dir"]

    # -- keeping the wiki cache current ----------------------------------
    def _start_wiki_job(self, key, work):
        """Run one refresh behind whatever answer was just given.

        Failure is deliberately quiet here: the caller has already been served
        from cache, and a refresh that could not happen is reported by
        `wiki_status` rather than by interrupting something the user is doing.
        """
        if key in self._wiki_jobs:
            return
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            return
        self._wiki_jobs.add(key)

        async def run():
            try:
                result = await self._run(work)
                if isinstance(result, dict) and result.get("changed"):
                    self.log.info("compatibility list updated: %s entries",
                                  result.get("count"))
            except Exception:
                self.log.exception("background wiki refresh failed (%s)", key)
            finally:
                self._wiki_jobs.discard(key)

        loop.create_task(run())

    def refresh_wiki_if_stale(self):
        """Start a list refresh when the cached one is old enough to matter."""
        if self.wiki.is_stale():
            self._start_wiki_job("list", self.wiki.revalidate)

    def refresh_page_if_stale(self, page):
        """Fetch one game's wiki page behind the answer, if it is worth trying.

        `page_needs_fetch` rather than `page_is_stale`: a page the wiki will not
        serve must not be re-attempted on every question, or a refresh is
        permanently in flight and the UI never stops waiting for one that is
        never going to arrive.
        """
        if self.wiki.page_needs_fetch(page):
            self._start_wiki_job(f"page:{page}", lambda: self.wiki.fetch_page(page))

    def prime_wiki(self):
        """Called at plugin start, so the list is current before it is asked for."""
        self.refresh_wiki_if_stale()

    # -- status ----------------------------------------------------------
    async def get_status(self):
        status = await self._run(self.payload.status)
        status["optiscaler_version"] = (
            f"{status['version']} ({status['tag']})" if status.get("tag") else None
        )
        status["optipatcher"] = await self._run(self.optipatcher.status)
        status["proxy_filenames"] = PROXY_FILENAMES
        status["default_proxy"] = DEFAULT_PROXY
        return status

    # -- libraries -------------------------------------------------------
    def _libraries(self):
        """Steam library folders plus any the user added by hand."""
        libraries = []
        for path in steam.library_folders(self.home):
            libraries.append(
                {
                    "path": str(path),
                    "name": self._library_label(path),
                    "source": "steam",
                    "game_count": len(steam.steam_games(path)),
                    "available": True,
                }
            )
        for entry in self.settings.get("custom_libraries", []):
            path = Path(entry["path"])
            available = path.is_dir()
            libraries.append(
                {
                    "path": str(path),
                    "name": entry.get("name") or path.name,
                    "source": "custom",
                    "game_count": len(steam.folder_games(path)) if available else 0,
                    "available": available,
                }
            )
        return libraries

    async def list_libraries(self):
        return await self._run(self._libraries)

    def _library_label(self, path):
        path = Path(path)
        text = str(path)
        if str(self.home) in text:
            return "Internal Storage"
        if self._is_sd_card(path):
            return f"SD Card ({path.name})"
        # Anything else mounted under /run/media is removable, but it is a USB
        # stick or an external SSD - calling those an SD card was the bug this
        # replaced, and there is nothing here that can tell which kind it is.
        if text.startswith("/run/media"):
            return f"External Drive ({path.name})"
        return path.name or text

    @staticmethod
    def _mount_device(path):
        """The block device backing `path`, from /proc/mounts.

        The longest mount point that is a prefix of the path wins, which is what
        makes a library on a card mounted inside another filesystem resolve to
        the card rather than to whatever it sits in.
        """
        try:
            target = os.path.realpath(str(path))
            entries = Path("/proc/mounts").read_text(errors="replace").splitlines()
        except OSError:
            return None
        best = None
        best_len = -1
        for line in entries:
            fields = line.split()
            if len(fields) < 2:
                continue
            device = fields[0]
            # /proc/mounts escapes spaces and friends as octal.
            mount = (
                fields[1]
                .replace("\\040", " ")
                .replace("\\011", "\t")
                .replace("\\012", "\n")
                .replace("\\134", "\\")
            )
            if target == mount or target.startswith(mount.rstrip("/") + "/"):
                if len(mount) > best_len:
                    best, best_len = device, len(mount)
        return best

    @staticmethod
    def _disk_name(device):
        """`/dev/mmcblk0p1` -> `mmcblk0`: the drive, not the partition."""
        if not device or not device.startswith("/dev/"):
            return None
        name = os.path.basename(device)
        if name.startswith("mmcblk") or name.startswith("nvme"):
            # mmcblk0p1, nvme0n1p2 - the partition suffix is "p<n>".
            return name.rsplit("p", 1)[0] if "p" in name[6:] else name
        return name.rstrip("0123456789") or name

    def _is_sd_card(self, path):
        """Whether this really is the SD card, rather than any removable drive.

        The old test was the path — anything under /run/media, or with mmcblk
        anywhere in it — which labelled every USB stick and external SSD an SD
        card. The card is a property of the device, so the device is what is
        asked: an MMC drive that is not the one the system booted from. The
        exclusion matters on the 64 GB Deck, whose internal storage is eMMC and
        therefore an mmcblk device too.
        """
        device = self._mount_device(path)
        disk = self._disk_name(device)
        if not disk or not disk.startswith("mmcblk"):
            return False
        return disk != self._disk_name(self._mount_device("/"))

    async def add_custom_library(self, path, name=None):
        target = Path(path).expanduser()
        if not target.is_dir():
            return {"ok": False, "error": f"Not a directory: {target}"}
        added = await self._run(self.settings.add_library, str(target), name)
        if not added:
            return {"ok": False, "error": "That folder is already a library."}
        return {"ok": True, "path": str(target)}

    async def remove_custom_library(self, path):
        removed = await self._run(self.settings.remove_library, path)
        return {"ok": removed}

    async def browse(self, path=None):
        """Directory listing used by the custom-library folder picker."""
        def work():
            if not path:
                roots = [
                    {"path": str(self.home), "name": "Home"},
                    {"path": "/run/media", "name": "Removable media"},
                    {"path": "/", "name": "Filesystem root"},
                ]
                return {
                    "path": None,
                    "parent": None,
                    "entries": [r for r in roots if Path(r["path"]).is_dir()],
                }
            current = Path(path).expanduser()
            if not current.is_dir():
                return {"path": str(current), "parent": str(current.parent), "entries": []}
            entries = []
            try:
                for child in sorted(current.iterdir(), key=lambda p: p.name.lower()):
                    if child.is_dir() and not child.name.startswith("."):
                        entries.append({"path": str(child), "name": child.name})
            except PermissionError:
                pass
            return {
                "path": str(current),
                "parent": str(current.parent) if current.parent != current else None,
                "entries": entries,
            }

        return await self._run(work)

    # -- games -----------------------------------------------------------
    async def list_games(self, library_path, source="steam"):
        def work():
            games = (steam.steam_games(library_path) if source == "steam"
                     else steam.folder_games(library_path))
            for game in games:
                target = self.settings.get_target(game["path"])
                probe = target or game["path"]
                detection = installer.detect(probe)
                if not detection["installed"] and not target:
                    # Cheap top-level probe missed it; look one level deeper.
                    for candidate in steam.find_exe_dirs(game["path"])[:4]:
                        found = installer.detect(candidate["path"])
                        if found["installed"]:
                            detection = found
                            break
                game["installed"] = detection["installed"]
                game["filename"] = detection["filename"]
                game["install_path"] = detection["path"] if detection["installed"] else None
                game["managed"] = detection["managed"]
                game["optiscaler_version"] = detection.get("version")
                game["optiscaler_tag"] = detection.get("tag")
            return games

        return await self._run(work)

    async def list_all_games(self):
        """Every detected game across every library, as one flat list.

        The main page leads with games rather than libraries, because picking a
        game is what people came to do; libraries stay available for the cases
        where a folder has to be added by hand.
        """
        def work():
            seen = set()
            games = []
            patcher = self.optipatcher.current()
            # What an update would move each kind of install to.
            nightly_tag = self.nightly_target()
            build = self.helixsr_build()
            helixsr_tag = helixsr.tag(build) if build.get("found") else None
            for library in self._libraries():
                source = library["source"]
                found = (steam.steam_games(library["path"]) if source == "steam"
                         else steam.folder_games(library["path"]))
                for game in found:
                    if game["path"] in seen:
                        continue
                    seen.add(game["path"])
                    game["library"] = library["name"]
                    game["source"] = source
                    target = self.settings.get_target(game["path"])
                    probe = target or game["path"]
                    detection = installer.detect(probe)
                    if not detection["installed"] and not target:
                        for candidate in steam.find_exe_dirs(game["path"])[:4]:
                            deeper = installer.detect(candidate["path"])
                            if deeper["installed"]:
                                detection = deeper
                                break
                    game["installed"] = detection["installed"]
                    game["filename"] = detection["filename"]
                    game["install_path"] = detection["path"] if detection["installed"] else None
                    game["managed"] = detection["managed"]
                    game["optiscaler_version"] = detection.get("version")
                    game["optiscaler_tag"] = detection.get("tag")
                    game["engine"] = detection.get("engine")
                    game["upscaler"] = detection.get("upscaler")
                    managed = detection["installed"] and detection["managed"]
                    # An older build than an install would use now: the nightly
                    # for FSR 4 Lite, the HelixSR build for HLX.
                    newest = helixsr_tag if game["engine"] == ENGINE_HELIXSR else nightly_tag
                    game["outdated"] = bool(managed and newest and game["optiscaler_tag"] != newest)
                    # An older OptiPatcher build than installs use now, which
                    # the batch update replaces. HelixSR Scaler's own is kept.
                    game["optipatcher_outdated"] = bool(
                        managed and game["engine"] != ENGINE_HELIXSR
                        and _optipatcher_outdated(detection["path"], patcher))
                    games.append(game)
            # Set-up games first, then alphabetical - the ones already managed
            # are the ones being come back to.
            games.sort(key=lambda g: (not g["installed"], g["name"].lower()))
            return games

        return await self._run(work)

    def _compat_scan(self, path, size_on_disk, force=False):
        """A folder scan, reused until the folder or Steam's size for it changes."""
        try:
            stamp = (Path(path).stat().st_mtime_ns, size_on_disk)
        except OSError:
            stamp = (None, size_on_disk)
        cached = self._compat_scans.get(path)
        if cached and cached[0] == stamp and not force:
            return cached[1]
        found = compat.scan(path)
        self._compat_scans[path] = (stamp, found)
        return found

    async def assess_games(self, games, force=False):
        """How likely OptiScaler is to work in each game, keyed by path.

        Separate from `list_all_games` so the list is on screen before every
        install folder has been walked; the frontend asks a page at a time. A
        pinned wiki entry wins over name matching, as it does on the detail
        page, and the names matched are the same pair that page uses.
        """
        self.refresh_wiki_if_stale()

        def work():
            entries, _ = self.wiki.load_entries()
            by_name = {entry["name"]: entry for entry in entries}

            def one(game):
                path = str(game.get("path") or "")
                try:
                    found = self._compat_scan(path, game.get("size_on_disk"), force)
                    pinned = by_name.get(self.settings.get_wiki_entry(path) or "")
                    folder = Path(path).name
                    entry = (dict(pinned, manual=True) if pinned else
                             self.wiki.match(game.get("name") or folder, entries, [folder]))
                    return path, compat.verdict(found, entry)
                except Exception as exc:
                    # One unreadable folder must not cost every other badge.
                    self.log.exception("compatibility check failed for %s", path)
                    return path, {"status": "error", "compatible": False, "summary": str(exc)}

            # Walking folders is I/O-bound, and on an SD card mostly waiting.
            with ThreadPoolExecutor(max_workers=4) as pool:
                return dict(pool.map(one, games or []))

        return await self._run(work)

    async def get_game(self, game_path, name=None):
        """Everything the game detail page needs."""
        def work():
            path = Path(game_path)
            candidates = steam.find_exe_dirs(path)
            saved_target = self.settings.get_target(str(path))

            detection = None
            for candidate in candidates:
                found = installer.detect(candidate["path"])
                if found["installed"]:
                    detection = found
                    break
            if detection is None:
                root = installer.detect(str(path))
                detection = root if root["installed"] else None

            if detection:
                target = detection["path"]
            elif saved_target:
                target = saved_target
            elif candidates:
                target = candidates[0]["path"]
            else:
                target = str(path)

            info = installer.detect(target)
            ini_info = {"present": False, "keys": 0}
            ini_path = Path(target) / INI_NAME
            if ini_path.is_file():
                values = IniFile(ini_path).to_dict()
                ini_info = {
                    "present": True,
                    "keys": sum(len(v) for v in values.values()),
                }
            return {
                "ini_info": ini_info,
                "wiki_entry": self.settings.get_wiki_entry(str(path)),
                "gpu": gpu_info(),
                "path": str(path),
                "name": name or path.name,
                "target": target,
                "target_is_saved": bool(saved_target),
                "candidates": candidates,
                "install": info,
                # The nightly a reinstall would use now, next to the one this
                # game has, so the page can say when there is a newer build.
                "current_tag": self.release()["tag"],
                "launch_option": installer.launch_option(info["filename"] or DEFAULT_PROXY),
                "reframework": reframework.status(target),
                "writable": os.access(target, os.W_OK) if Path(target).is_dir() else False,
            }

        return await self._run(work)

    async def find_running_game(self, appid, shortcut=None):
        """Resolve an app id to its game folder and install state.

        ``shortcut`` is what the Steam client said about a non-Steam entry —
        its target, its start directory and its name — or None for a game
        Steam has a manifest for. A shortcut has no install directory anywhere
        in Steam's records, so without this a game added by hand answered "no
        install folder" and could not be opened at all: the Quick Access panel,
        Now Playing and the library context menu all come through here.
        """
        shortcut = shortcut or {}

        def work():
            game = steam.find_by_appid(self.home, appid, shortcut.get("exe"),
                                       shortcut.get("start_dir"), shortcut.get("name"))
            if not game:
                return {"found": False, "appid": str(appid)}
            return {"found": True, **game}

        game = await self._run(work)
        if not game.get("found"):
            return game
        detail = await self.get_game(game["path"], game["name"])
        return {**game, "detail": detail}

    async def verify_install(self, target_dir):
        """Confirm the bundled files really landed in the game folder."""
        try:
            payload_root, release = await self._payload_for(target_dir)
            return {"ok": True, **await self._run(
                installer.verify_install, target_dir, payload_root, release
            )}
        except Exception as exc:
            return {"ok": False, "error": str(exc)}

    # -- wiki search / manual selection ----------------------------------
    async def search_wiki(self, query, limit=30):
        self.refresh_wiki_if_stale()
        return await self._run(self.wiki.search, query, limit)

    async def set_wiki_entry(self, game_path, entry_name):
        """Pin a compatibility-list entry to a game, overriding name matching."""
        await self._run(self.settings.set_wiki_entry, game_path, entry_name)
        return {"ok": True}

    # -- FSR 4 Lite -------------------------------------------------------
    async def apply_fsr4_preset(self, target_dir):
        """Write the upscaler's preset again.

        For when OptiScaler's overlay has saved different values over it: the
        same thing an install does, without replacing anything else.
        """
        try:
            def work():
                if not (Path(target_dir) / INI_NAME).is_file():
                    raise FileNotFoundError("OptiScaler.ini가 없습니다. 먼저 OptiScaler를 설치하세요")
                installer.apply_preset(Path(target_dir) / INI_NAME, None, self.log)
                return {"fsr4": installer.fsr4_status(target_dir)}

            async with self._mutation_lock:
                return {"ok": True, **await self._run(work)}
        except Exception as exc:
            self.log.exception("FSR 4 preset failed for %s", target_dir)
            return {"ok": False, "error": str(exc)}

    async def get_launch_options(self, appid):
        """What Steam passes a game, read out of its own config on disk.

        The frontend asks the client first, because that is live and this file
        is only flushed periodically. But `GetAppLaunchOptions` is missing from
        some client builds entirely, and on those the plugin could previously
        neither report the launch options nor undo them — so this is the answer
        of last resort rather than a nicety.
        """
        return await self._run(steam.launch_options, self.home, appid)

    async def record_launch_options(self, target_dir, options=None, appid=None):
        """Keep this game's launch options as they were before the install.

        ``options`` is what the frontend read from the Steam client, which is
        the freshest source; ``None`` means it could not read them, and Steam's
        own config file is then asked instead. Recording nothing is the last
        resort, because a missing record is what makes removing OptiScaler
        unable to put anything back.

        Written once, next to the install it belongs to, beside the manifest
        and the backup folder.
        """
        try:
            if options is None and appid is not None:
                found = await self._run(steam.launch_options, self.home, appid)
                if not found["found"]:
                    return {"ok": False, "error": "Steam would not report the launch options",
                            "recorded": False, "value": "", "written": False}
                options = found["value"]
            if options is None:
                return {"ok": False, "error": "no launch options to record",
                        "recorded": False, "value": "", "written": False}
            return {"ok": True, **await self._run(
                installer.record_launch_options, target_dir, options, self.log
            )}
        except Exception as exc:
            self.log.exception("could not record launch options for %s", target_dir)
            return {"ok": False, "error": str(exc)}

    async def get_pref(self, key, default=None):
        """One remembered UI choice, e.g. whether to set launch options."""
        return {"key": key, "value": self.settings.get_pref(key, default)}

    async def set_pref(self, key, value):
        await self._run(self.settings.set_pref, key, value)
        return {"ok": True, "key": key, "value": value}

    async def set_game_target(self, game_path, target_dir):
        await self._run(self.settings.set_target, game_path, target_dir)
        return {"ok": True}

    # -- wiki ------------------------------------------------------------
    async def get_recommendation(self, name, extra_names=None, force=False, game_path=None):
        """Wiki recommendation, honouring a manually pinned entry if there is one.

        Answered from the cache; anything out of date is refreshed behind the
        answer, both the list and this game's own detail page.
        """
        if not force:
            self.refresh_wiki_if_stale()
        pinned = self.settings.get_wiki_entry(game_path) if game_path else None
        if pinned:
            entry = await self._run(self.wiki.entry_by_name, pinned)
            if entry:
                result = await self._run(self.wiki.recommend_entry, entry, force)
                if not force:
                    self.refresh_page_if_stale(entry.get("page"))
                return result
        result = await self._run(self.wiki.recommend, name, extra_names, force)
        if not force:
            self.refresh_page_if_stale(result.get("page"))
        return result

    async def refresh_wiki(self):
        entries, meta = await self._run(self.wiki.load_entries, True)
        return {"count": len(entries), "meta": meta}

    async def wiki_status(self, force=False):
        """Is the compatibility list usable, how old is it, and what last failed?"""
        if not force:
            self.refresh_wiki_if_stale()
        status = await self._run(self.wiki.status, force)
        # What the UI watches to know a background refresh is worth waiting a
        # moment for: while this is true, the revision it holds may change.
        status["revalidating"] = bool(self._wiki_jobs)
        return status

    # -- automatic set-up ------------------------------------------------
    async def get_auto_plan(self, name, extra_names=None, force=False, game_path=None):
        """The wiki recommendation plus the plan built from it.

        Both together, because the plan is only meaningful next to the entry it
        was read out of: the UI shows what will be changed and cites the wiki
        row or field each item came from, so "automatic" is never a black box.
        """
        recommendation = await self.get_recommendation(name, extra_names, force, game_path)
        plan = await self._run(autoplan.build, recommendation)
        ref = plan.get("reframework")
        if ref and ref.get("plugin"):
            state = await self._run(self.pd_plugin_state)
            ref.update(plugin_ready=state["present"], plugin_verified=state["verified"],
                       plugin_folder=state["folder"], plugin_url=state["url"])
            if state["present"]:
                plan["warnings"] = [w for w in plan.get("warnings", [])
                                    if "Nexus Mods" not in w]
        if game_path:
            plan["enabled"] = bool(self.settings.get_pref(_auto_key(game_path), False))
        return {"recommendation": recommendation, "plan": plan}

    async def set_auto_mode(self, game_path, enabled):
        """Remember whether one game's settings are driven by the wiki."""
        await self._run(self.settings.set_pref, _auto_key(game_path), bool(enabled) or None)
        return {"ok": True, "enabled": bool(enabled)}

    async def auto_install(self, target_dir, game_path=None, name=None, extra_names=None,
                           optipatcher=None, upscaler=None):
        """Install and configure a game the way its wiki entry describes.

        One call rather than a filename, an OptiPatcher toggle and a run of
        config writes done separately, because the ini has to exist before the
        wiki's settings can go into it, and a half-applied plan is worse than
        none. The Steam launch options are returned rather than set: only the
        frontend can talk to Steam. ``optipatcher`` overrides the entry's
        OptiPatcher column when the user switched that step off (or on).
        ``upscaler`` is the one picked for the game; the one it already has
        when reinstalling without saying.
        """
        planned = await self.get_auto_plan(name or Path(target_dir).name, extra_names,
                                           False, game_path)
        plan = planned["plan"]
        if not plan["available"]:
            return {"ok": False, "error": "no compatibility entry matched this game",
                    **planned}

        patcher = plan["optipatcher"] if optipatcher is None else bool(optipatcher)
        result = await self.install(target_dir, plan["filename"], False, patcher,
                                    plan.get("reframework"), upscaler)
        if not result.get("ok"):
            return {"ok": False, "error": result.get("error"), **planned}

        changes = autoplan.setting_changes(plan) + autoplan.framegen_changes(plan)
        written = await self.write_config(target_dir, changes) if changes else {"applied": []}
        if game_path:
            await self._run(self.settings.set_target, game_path, target_dir)
            await self.set_auto_mode(game_path, True)
        return {
            "ok": True,
            "install": result,
            "applied": written.get("applied", []),
            "rejected": written.get("rejected", []),
            **planned,
        }

    async def apply_auto_settings(self, target_dir, game_path=None, name=None,
                                  extra_names=None):
        """Re-apply the wiki's settings to a game that is already installed.

        Used when automatic mode is switched on for a game set up by hand, and
        after a wiki refresh, so the ini says what the entry currently says.
        """
        planned = await self.get_auto_plan(name or Path(target_dir).name, extra_names,
                                           False, game_path)
        plan = planned["plan"]
        if not plan["available"]:
            return {"ok": False, "error": "no compatibility entry matched this game",
                    **planned}
        changes = autoplan.setting_changes(plan) + autoplan.framegen_changes(plan)
        written = await self.write_config(target_dir, changes) if changes else {"ok": True}
        if game_path:
            await self.set_auto_mode(game_path, True)
        return {"ok": True, "applied": written.get("applied", []), **planned}

    # -- install ---------------------------------------------------------
    async def install(self, target_dir, filename=DEFAULT_PROXY, preserve_ini=True,
                      optipatcher=False, reframework_plan=None, upscaler=None):
        """Install OptiScaler, and REFramework first when the plan calls for it.

        ``upscaler`` decides which OptiScaler: HelixSR Scaler from the user's
        HelixSR build for HLX DLSS, and the nightly for the rest. A nightly
        install carries cyboman's FSR 4.1.2 Lite builds and HLX FSR 4 as custom
        upscalers beside AMD's, all of them, with the picked one the DX12
        upscaler; only the picked one failing to download fails the install.
        Left out, a reinstall keeps the one the game has. HelixSR Scaler brings
        its own OptiPatcher, so ``optipatcher`` only means anything for the
        nightly.

        A failed REFramework download does not fail the install. The two are
        separate mods and the OptiScaler half is still worth having on disk;
        what matters is that the failure is *reported*, because for these games
        an install without REF is one that will do nothing and say nothing.

        Which is also why the requirement is still carried through here with
        automatic installation switched off: the plan says the game needs REF,
        the checklist says where to get it, and only the download is gone.
        """
        ref_result = {"required": False, "installed": False, "error": None}
        ref_files = None
        ref_revision = None
        if reframework_plan and reframework_plan.get("required"):
            ref_result["required"] = True
        # `automatic` is the whole gate: a game with no known build has never
        # had one, and since 0.0.5.3-testing no game does, because downloading
        # a third-party engine hook into somebody's game folder is not a
        # promise this plugin makes any more. The requirement still travelled
        # here and is still reported — the checklist says what the game needs
        # and where to get it — so this is a step left to the user, not an
        # error to put in front of them.
        if reframework_plan and reframework_plan.get("automatic"):
            try:
                ref_files = await self._run(
                    reframework.fetch, reframework_plan, self.reframework_cache(), self.log
                )
                ref_revision = await self._run(reframework.revision_of, ref_files)
            except Exception as exc:
                self.log.warning("REFramework download failed for %s: %s", target_dir, exc)
                ref_result["error"] = str(exc)
        if await self._run(dropin.read_manifest, target_dir):
            # Two ways of putting FSR 4 into one folder would fight over the
            # same FidelityFX files.
            return {"ok": False, "error": "이 게임에는 FSR 드롭인이 적용되어 있습니다. 드롭인을 먼저 제거하세요."}
        if upscaler is None:
            # A reinstall keeps the game's; a first install starts from this
            # machine's recommendation.
            manifest = await self._run(installer.read_manifest, target_dir)
            upscaler = (manifest or {}).get("upscaler") or self.default_upscaler()
        if upscaler not in UPSCALERS:
            return {"ok": False, "error": f"{upscaler}은(는) OptiScaler로 설치하는 업스케일러가 아닙니다."}
        refused = self._refuse_on_device(upscaler)
        if refused:
            return {"ok": False, "error": refused}
        foreign = await self._run(helixsr.foreign_install, target_dir)
        if foreign and not await self._run(installer.read_manifest, target_dir):
            return {"ok": False, "error": "이 게임에는 HelixSR Desktop이 설치한 HelixSR가 있습니다. "
                                          "HelixSR Desktop에서 먼저 제거하세요."}
        hlx = installer.engine_for(upscaler) == ENGINE_HELIXSR
        try:
            ffx, ffx_errors = [], []
            if hlx:
                payload_root, release, helixsr_dir = await self._run(self._helixsr_source)
                extra_dirs = {HELIXSR_DIR: helixsr_dir}
            else:
                payload_root, release, extra_dirs = await self.ensure_payload(), self.release(), None
                ffx, ffx_errors = await self._custom_upscalers(upscaler, payload_root)
            async with self._mutation_lock:
                pd = _is_pd(reframework_plan)
                if pd and ref_files:
                    ref_files = list(ref_files) + self.pd_plugin_files()
                patcher, patcher_error = None, None
                if optipatcher and not hlx:
                    # Like a failed REFramework download, this does not fail the
                    # install: OptiScaler goes in, and the miss is reported.
                    try:
                        patcher = await self.optipatcher_path()
                    except Exception as exc:
                        # A reinstall keeps the copy the game already has
                        # rather than dropping it for want of a download.
                        patcher = await self._run(self._keep_installed_optipatcher, target_dir)
                        patcher_error = None if patcher else str(exc)
                result = await self._run(
                    installer.install, target_dir, payload_root, filename, preserve_ini,
                    self.log, patcher,
                    ref_files, ref_revision, release, pd,
                    upscaler, extra_dirs, ffx,
                )
                if patcher_error:
                    result["optipatcher"] = {"installed": False, "error": patcher_error}
                if ffx_errors:
                    result["custom_errors"] = ffx_errors
            if ref_result["required"]:
                installed = result.get("reframework", {})
                ref_result["installed"] = bool(installed.get("installed"))
                ref_result["error"] = ref_result["error"] or installed.get("error")
                result["reframework"] = {**installed, **ref_result}
            return {"ok": True, **result}
        except Exception as exc:  # surfaced verbatim in the UI
            self.log.exception("install failed for %s", target_dir)
            return {"ok": False, "error": str(exc)}

    async def _custom_upscalers(self, picked, payload_root):
        """Every custom upscaler a nightly install carries, downloaded: (list, errors).

        The picked one takes AMD's place as OptiScaler's own FidelityFX
        upscaler, and AMD's moves to the custom folder in its stead. The picked
        one has to be there, so its failure is the install's; any other is left
        out and said so, the install going on without it. What this machine
        cannot pick is not downloaded at all.
        """
        found, errors = [], []
        allowed = self.allowed_upscalers()
        for upscaler, name in CUSTOM_UPSCALER_NAMES.items():
            if upscaler not in allowed:
                continue
            try:
                if upscaler in CYBOMAN_VARIANTS:
                    variant = CYBOMAN_VARIANTS[upscaler]
                    source, tag = await self._run(dropin.fetch, self.dropin_cache(), self.log,
                                                  variant, self.target_tag("dropin"))
                else:
                    variant = DROPIN_VARIANTS[upscaler]
                    source, tag = await self._run(self._hlx_fsr4)
            except Exception as exc:
                if upscaler == picked:
                    raise
                self.log.warning("custom upscaler %s left out: %s", name, exc)
                errors.append({"upscaler": upscaler, "error": str(exc)})
                continue
            found.append({"path": str(source), "name": name, "variant": variant, "tag": tag,
                          "main": upscaler == picked})
        if any(entry["main"] for entry in found):
            found.append({"path": str(Path(payload_root) / FFX_UPSCALER_DLL), "name": CUSTOM_AMD_NAME,
                          "variant": DROPIN_VARIANTS[UPSCALER_FSR4_LITE],
                          "tag": self.release()["tag"], "main": False})
        return found, errors

    async def uninstall(self, target_dir, remove_ini=True):
        try:
            async with self._mutation_lock:
                result = await self._run(installer.uninstall, target_dir, remove_ini, self.log)
            return {"ok": True, **result}
        except Exception as exc:
            self.log.exception("uninstall failed for %s", target_dir)
            return {"ok": False, "error": str(exc)}

    # -- configuration ---------------------------------------------------
    async def read_config(self, target_dir):
        def work():
            path = Path(target_dir) / INI_NAME
            if not path.is_file():
                return {"ok": False, "error": "OptiScaler.ini not found", "values": {}}
            return {
                "ok": True,
                "path": str(path),
                "values": IniFile(path).to_dict(),
                "modified": path.stat().st_mtime,
            }

        return await self._run(work)

    async def write_config(self, target_dir, changes):
        """changes: [{section, key, value}] — value None/'' means 'auto'.

        OptiScaler reads its ini once, at launch, so whatever is written here
        applies the next time the game starts.
        """
        def work():
            path = Path(target_dir) / INI_NAME
            if not path.is_file():
                return {"ok": False, "error": "OptiScaler.ini not found"}
            ini = IniFile(path)
            applied = []
            rejected = []
            for change in changes or []:
                section = change.get("section")
                key = change.get("key")
                if not section or not key:
                    continue
                value = change.get("value")
                value = "auto" if value in (None, "") else str(value)
                meta = SCHEMA.get((section, key))
                if meta and not _valid(meta, value):
                    rejected.append({"section": section, "key": key, "value": value})
                    continue
                ini.set(section, key, value)
                applied.append({"section": section, "key": key, "value": value})
            if applied:
                ini.save()
            return {"ok": True, "applied": applied, "rejected": rejected,
                    "written_at": time.time()}

        async with self._mutation_lock:
            return await self._run(work)

    async def _payload_for(self, target_dir):
        """(payload root, release) of the build a game is on: nightly or HelixSR."""
        upscaler = await self._run(installer.upscaler_of, target_dir)
        if installer.engine_for(upscaler) == ENGINE_HELIXSR:
            root, release, _ = await self._run(self._helixsr_source)
            return root, release
        return await self.ensure_payload(), self.release()

    async def reset_config(self, target_dir):
        """Restore the release's stock OptiScaler.ini, plus the upscaler's preset."""
        try:
            payload_root = Path((await self._payload_for(target_dir))[0])

            def work():
                import shutil
                destination = Path(target_dir) / INI_NAME
                shutil.copy2(payload_root / INI_NAME, destination)
                # A stock ini is not what this plugin installs: the upscaler's
                # preset goes back in with it.
                installer.apply_preset(destination, None, self.log)
                return {"ok": True, "path": str(destination)}

            async with self._mutation_lock:
                return await self._run(work)
        except Exception as exc:
            return {"ok": False, "error": str(exc)}

    # -- REFramework ------------------------------------------------------
    # -- PDPerfPlugin.dll, which the user supplies -------------------------
    def pd_plugin_kept(self):
        """Where the user's PDPerfPlugin.dll is kept once it has been found."""
        return self.runtime_dir / "user-files" / REFRAMEWORK_PD_PLUGIN

    def pd_plugin_state(self):
        """Whether the user has supplied PDPerfPlugin.dll, and whether it is 1.1.2.

        It may not be redistributed, so the user downloads it and leaves it in
        their Downloads folder. The first time it is seen there it is copied
        into the plugin's data folder, so clearing Downloads later loses
        nothing. A verified copy there is preferred over an unverified one.
        """
        import shutil
        from .payload import sha256

        def verified(path):
            return sha256(path) == REFRAMEWORK_PD_PLUGIN_SHA256

        kept = self.pd_plugin_kept()
        drop = self.home / REFRAMEWORK_PD_PLUGIN_DROP_DIR
        if not (kept.is_file() and verified(kept)):
            found = _find_named(drop, REFRAMEWORK_PD_PLUGIN, REFRAMEWORK_PD_PLUGIN_DROP_DEPTH)
            best = next((p for p in found if verified(p)), None) or (
                None if kept.is_file() else (found[0] if found else None))
            if best:
                kept.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(best, kept)
                self.log.info("PDPerfPlugin.dll taken from %s", best)
        present = kept.is_file()
        media = Path("/run/media")
        return {
            "present": present,
            "verified": bool(present and verified(kept)),
            "name": REFRAMEWORK_PD_PLUGIN,
            "build": REFRAMEWORK_PD_PLUGIN_NAME,
            "url": REFRAMEWORK_PD_PLUGIN_URL,
            "folder": str(drop),
            # Where the file picker opens: the SD card and USB drives live
            # under /run/media on SteamOS, which is where a file brought over
            # from a PC is.
            "picker_start": str(media if media.is_dir() else self.home),
        }

    def take_pd_plugin(self, source, name=None):
        """Keep PDPerfPlugin.dll from a file the user picked or sent.

        The DLL itself, or the archive Nexus Mods serves it in (zip or 7z),
        which is unpacked to find it. Anything else is refused with a reason.
        """
        import shutil
        import tempfile
        from .payload import extract_archive

        source = Path(source)
        name = name or source.name
        head = source.read_bytes()[:6] if source.is_file() else b""
        with tempfile.TemporaryDirectory(prefix="pdperf-") as tmp:
            if head[:2] == b"MZ":
                if name.lower() != REFRAMEWORK_PD_PLUGIN.lower():
                    raise ValueError(f"{name}은(는) {REFRAMEWORK_PD_PLUGIN}이 아닙니다.")
                found = source
            elif head[:2] == b"PK" or head[:6] == b"7z\xbc\xaf\x27\x1c":
                unpacked = Path(tmp) / "unpacked"
                if head[:2] == b"PK":
                    # The standard library reads zip; only 7z needs an archiver.
                    import zipfile
                    with zipfile.ZipFile(source) as archive:
                        for member in archive.infolist():
                            if Path(member.filename).name.lower() == REFRAMEWORK_PD_PLUGIN.lower():
                                target = unpacked / REFRAMEWORK_PD_PLUGIN
                                target.parent.mkdir(parents=True, exist_ok=True)
                                target.write_bytes(archive.read(member))
                                break
                else:
                    extract_archive(source, unpacked, self.log)
                matches = _find_named(unpacked, REFRAMEWORK_PD_PLUGIN, 8)
                if not matches:
                    raise ValueError(f"압축 파일 안에 {REFRAMEWORK_PD_PLUGIN}이 없습니다.")
                found = matches[0]
            else:
                raise ValueError(f"{REFRAMEWORK_PD_PLUGIN} 또는 그것이 든 zip·7z 파일을 골라 주세요.")
            kept = self.pd_plugin_kept()
            kept.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(found, kept)
        state = self.pd_plugin_state()
        self.log.info("PDPerfPlugin.dll taken from %s (verified: %s)", name, state["verified"])
        return {
            "ok": True,
            "verified": state["verified"],
            "message": (f"받았습니다. {REFRAMEWORK_PD_PLUGIN_NAME} 파일이 맞습니다. 스팀덱 화면으로 돌아가세요."
                        if state["verified"] else
                        f"받았습니다. 다만 {REFRAMEWORK_PD_PLUGIN_NAME}와 다른 버전입니다. 1.2.0은 동작하지 않습니다."),
        }

    async def import_pd_plugin(self, path):
        """The file picker's answer: a PDPerfPlugin.dll, or the archive it came in."""
        try:
            result = await self._run(self.take_pd_plugin, path)
            return {**result, "status": await self._run(self.pd_plugin_state)}
        except Exception as exc:
            return {"ok": False, "error": str(exc)}

    async def start_pd_upload(self):
        """Open the upload page a phone on the same Wi-Fi sends the file to."""
        from .upload import UploadSession
        if self._pd_upload is not None:
            self._pd_upload.close()
        try:
            self._pd_upload = await self._run(
                UploadSession, self.take_pd_plugin,
                "PDPerfPlugin.dll 보내기",
                f"Nexus Mods에서 받은 {REFRAMEWORK_PD_PLUGIN_NAME} 파일(zip·7z 그대로, 또는 압축을 푼 "
                f"{REFRAMEWORK_PD_PLUGIN})을 골라 Steam Deck으로 보내세요.",
                self.log)
        except Exception as exc:
            return {"ok": False, "error": str(exc)}
        return {"ok": True, **self._pd_upload.status()}

    async def get_pd_upload_status(self):
        session = self._pd_upload
        if session is None:
            return {"ok": True, "active": False, "url": None, "expires_at": None, "result": None}
        return {"ok": True, **session.status()}

    async def stop_pd_upload(self):
        if self._pd_upload is not None:
            self._pd_upload.close()
        return {"ok": True}

    def pd_plugin_files(self):
        """The user's PDPerfPlugin.dll, to install with REFramework; [] without one."""
        state = self.pd_plugin_state()
        if state["present"] and not state["verified"]:
            self.log.warning("PDPerfPlugin.dll is not the %s build the wiki names",
                             REFRAMEWORK_PD_PLUGIN_NAME)
        return [self.pd_plugin_kept()] if state["present"] else []

    async def get_pd_plugin_status(self):
        return await self._run(self.pd_plugin_state)

    async def install_pd_plugin(self, target_dir):
        """Put the user's PDPerfPlugin.dll into a game that is already set up.

        With libxess.dll at the root, where PDPerfPlugin looks for it now that
        v10 keeps it in OptiScaler/ - the same pair an install puts in.
        """
        try:
            files = await self._run(self.pd_plugin_files)
            if not files:
                return {"ok": False, "error": f"{REFRAMEWORK_PD_PLUGIN} 파일을 찾지 못했습니다. "
                                              f"{REFRAMEWORK_PD_PLUGIN_URL}에서 받아 다운로드 "
                                              "폴더에 넣어 주세요."}
            files += [lib for lib in (Path(target_dir) / "OptiScaler" / name
                                      for name in REFRAMEWORK_PD_ROOT_LIBS) if lib.is_file()]
            manifest = await self._run(installer.read_manifest, target_dir) or {}
            async with self._mutation_lock:
                result = await self._run(installer.add_files, target_dir, files, self.log,
                                         manifest.get("reframework_revision"))
            return {"ok": bool(result.get("ok")), "files": result.get("files", [])}
        except Exception as exc:
            self.log.exception("PDPerfPlugin install failed for %s", target_dir)
            return {"ok": False, "error": str(exc)}

    def reframework_cache(self):
        """Where downloaded REFramework builds are kept between installs.

        Under the runtime directory, so setting up a second Resident Evil game
        is a copy rather than a second 13 MB download on a handheld connection —
        and so it goes when the plugin does.
        """
        return self.runtime_dir / "reframework"

    async def get_reframework_status(self, target_dir, game_path=None, name=None,
                                     extra_names=None):
        """Whether this game needs REFramework, and whether it has it.

        Both halves in one answer, because either alone is unreadable: "present"
        means nothing for a game that does not want it, and "required" means
        nothing without knowing whether it is already there.
        """
        wanted = None
        if name or game_path:
            planned = await self.get_auto_plan(name or Path(target_dir).name, extra_names,
                                               False, game_path)
            wanted = planned["plan"].get("reframework")
        manifest = await self._run(installer.read_manifest, target_dir) or {}
        return await self._run(reframework.status, target_dir, wanted or {},
                               manifest.get("reframework_revision"))

    async def install_reframework(self, target_dir, game_path=None, name=None,
                                  extra_names=None):
        """Add REFramework to a game that is already set up, or retry a failure.

        Separate from the install for the same reason OptiPatcher is: a download
        over a handheld's connection is the part that fails, and having to
        reinstall OptiScaler to retry it would be a poor answer to a flaky
        network.
        """
        try:
            planned = await self.get_auto_plan(name or Path(target_dir).name, extra_names,
                                               False, game_path)
            wanted = planned["plan"].get("reframework")
            if not wanted or not wanted.get("required"):
                return {"ok": False, "error": "this game's wiki entry does not ask for "
                                              "REFramework"}
            if not wanted.get("automatic"):
                return {"ok": False, "error": wanted.get("reason") or
                        "REFramework cannot be downloaded for this game",
                        "page": wanted.get("page")}
            files = await self._run(reframework.fetch, wanted, self.reframework_cache(),
                                    self.log)
            revision = await self._run(reframework.revision_of, files)
            if _is_pd(wanted):
                # PDPerfPlugin.dll goes in with it, and libxess.dll at the root,
                # where PDPerfPlugin looks for it now that v10 keeps it in OptiScaler/.
                files = list(files) + self.pd_plugin_files() + [
                    lib for lib in (Path(target_dir) / "OptiScaler" / name
                                    for name in REFRAMEWORK_PD_ROOT_LIBS) if lib.is_file()]
            result = await self._run(installer.add_files, target_dir, files, self.log,
                                     revision)
            if not result.get("ok"):
                return {"ok": False, "error": result.get("error")}
            return {"ok": True, "installed": True, "files": result["files"],
                    "status": await self._run(reframework.status, target_dir, wanted,
                                              revision)}
        except Exception as exc:
            self.log.exception("REFramework install failed for %s", target_dir)
            return {"ok": False, "error": str(exc)}

    async def remove_reframework(self, target_dir):
        """Take REFramework back out without touching OptiScaler.

        The isolation test a game that will not boot needs. Two mods went into
        that folder and either could be the one at fault; being able to remove
        one of them is the difference between a bug report and an answer.
        """
        try:
            # Everything that came with it goes too: PDPerfPlugin.dll is no use
            # without it, and libxess.dll at the root was only for PDPerfPlugin.
            manifest = await self._run(installer.read_manifest, target_dir) or {}
            names = [REFRAMEWORK_DLL] + [n for n in [REFRAMEWORK_PD_PLUGIN] + REFRAMEWORK_PD_ROOT_LIBS
                                         if n in (manifest.get("files") or [])]
            result = await self._run(installer.remove_files, target_dir, names, self.log)
            return {"ok": True, **result}
        except Exception as exc:
            self.log.exception("REFramework removal failed for %s", target_dir)
            return {"ok": False, "error": str(exc)}

    async def optipatcher_path(self):
        """The newest rolling OptiPatcher, downloading it the first time.

        Raises when there is no download and none can be made.
        """
        info = await self._run(self.optipatcher.ensure, False, self.log)
        return info["path"]

    def _keep_installed_optipatcher(self, target_dir):
        """A copy of the OptiPatcher this game has now, out of the install's way."""
        import shutil
        from .payload import sha256
        existing = Path(target_dir) / PLUGIN_SUBDIR / OPTIPATCHER_NAME
        if not existing.is_file():
            return None
        keep = self.runtime_dir / "optipatcher-kept" / sha256(existing)[:16]
        keep.mkdir(parents=True, exist_ok=True)
        shutil.copy2(existing, keep / OPTIPATCHER_NAME)
        return str(keep / OPTIPATCHER_NAME)

    async def get_optipatcher_status(self, target_dir):
        """Whether OptiPatcher is available here and installed for this game.

        Answered from disk. A check for a newer rolling build, when the last
        one is old, runs behind the answer, so the next look can offer it.
        """
        if self.optipatcher.is_stale():
            self._start_wiki_job("optipatcher",
                                 lambda: self.optipatcher.ensure(False, self.log))

        def work():
            installed_path = Path(target_dir) / PLUGIN_SUBDIR / OPTIPATCHER_NAME
            current = self.optipatcher.current()
            # HelixSR Scaler's own copy, which comes and goes with the Scaler.
            bundled = bool((installer.read_manifest(target_dir) or {}).get("optipatcher_bundled"))
            return {
                # Always: switching it on downloads it, as an install does.
                "available": True,
                "installed": installed_path.is_file(),
                "bundled": bundled,
                "version": current["label"] if current else None,
                "outdated": not bundled and _optipatcher_outdated(target_dir, current),
            }

        return await self._run(work)

    async def install_optipatcher(self, target_dir, enabled=True):
        """Add or remove OptiPatcher for one game without reinstalling."""
        try:
            path = Path(target_dir) / PLUGIN_SUBDIR / OPTIPATCHER_NAME
            if not enabled:
                if path.is_file():
                    path.unlink()
                return {"ok": True, "installed": False}
            source = await self.optipatcher_path()
            result = await self._run(
                installer.install_plugin_asi, target_dir, source, OPTIPATCHER_NAME, self.log
            )
            if not result.get("ok"):
                return {"ok": False, "error": result.get("error")}
            # ASI loading is already on: every preset has it.
            return {"ok": True, "installed": True}
        except Exception as exc:
            self.log.exception("optipatcher change failed for %s", target_dir)
            return {"ok": False, "error": str(exc)}

    # -- updates ---------------------------------------------------------
    def _plugin_identity(self):
        """(version, name) of the running plugin, from its own package files.

        The name is plugin.json's, which is the folder Decky installed it under
        and so the name an update has to be installed as to replace it.
        """
        def read(name, key, default):
            try:
                return json.loads((self.plugin_dir / name).read_text(encoding="utf-8"))[key]
            except (OSError, ValueError, KeyError):
                return default

        return read("package.json", "version", "0.0.0"), read("plugin.json", "name", "")

    async def check_plugin_update(self, force=False):
        """Whether a newer release of this plugin is out, and how Decky gets it."""
        return await self._run(self.updates.check, force)

    async def update_installed_games(self):
        """Install the newest build again in every game set up from an older one.

        Only games this plugin manages, each with the filename, ini, upscaler
        and OptiPatcher choice it already has - the same as reinstalling it from
        its own page. FSR 4 Lite games move to the downloaded nightly; HLX games
        to the HelixSR build HLX DLSS comes from now, and only when there is
        a newer one. A game already on the current nightly whose OptiPatcher is
        an older build gets the newer one, and nothing else. A game that is
        running is skipped rather than having its DLLs replaced under it, and
        one game failing does not stop the rest.
        """
        try:
            await self.ensure_payload()
        except Exception as exc:
            return {"ok": False, "error": str(exc), "tag": None, "results": []}
        current = self.release()["tag"]
        build = await self._run(self.helixsr_build)
        helixsr_current = helixsr.tag(build) if build.get("found") else None
        try:
            patcher = await self._run(self.optipatcher.ensure, False, self.log)
        except Exception:
            # Games on an older nightly still update; their OptiPatcher is
            # reported by the install. The others have nothing newer to get.
            patcher = None
        games = await self.list_all_games()
        mapped = await self._run(installer.mapped_files)
        results = []
        for game in games:
            if not (game.get("installed") and game.get("managed")):
                continue
            target = game["install_path"]
            hlx = game.get("engine") == ENGINE_HELIXSR
            newest = helixsr_current if hlx else current
            if hlx and not newest:
                continue  # the HelixSR build is gone; nothing to move to
            if game.get("optiscaler_tag") == newest:
                if not hlx and await self._run(_optipatcher_outdated, target, patcher):
                    results.append(await self._refresh_optipatcher(game, patcher, mapped))
                continue
            entry = {
                "name": game["name"],
                "path": game["path"],
                "from": game.get("optiscaler_tag") or game.get("optiscaler_version"),
                "to": newest,
                "skipped": False,
            }
            if installer.in_use(target, mapped):
                entry.update(ok=False, skipped=True, error="게임이 실행 중입니다")
                results.append(entry)
                continue
            manifest = await self._run(installer.read_manifest, target) or {}
            result = await self.install(target, game.get("filename") or DEFAULT_PROXY, True,
                                        bool(manifest.get("optipatcher")), None,
                                        game.get("upscaler"))
            entry.update(ok=bool(result.get("ok")), error=result.get("error"))
            results.append(entry)
        return {"ok": True, "tag": current, "results": results}

    async def _refresh_optipatcher(self, game, patcher, mapped):
        """Put the newer OptiPatcher into a game that is otherwise current."""
        target = game["install_path"]
        entry = {"name": game["name"], "path": game["path"], "from": "OptiPatcher",
                 "to": patcher["label"], "skipped": False}
        if installer.in_use(target, mapped):
            entry.update(ok=False, skipped=True, error="게임이 실행 중입니다")
            return entry
        async with self._mutation_lock:
            result = await self._run(installer.install_plugin_asi, target, patcher["path"],
                                     OPTIPATCHER_NAME, self.log)
        entry.update(ok=bool(result.get("ok")), error=result.get("error"))
        return entry

    # -- FSR drop-in -----------------------------------------------------
    def dropin_cache(self):
        """Where the downloaded drop-in builds are kept, shared by every game."""
        return self.runtime_dir / "fsr4-dropin"

    def helixsr_cache(self):
        """Where HelixSR's releases are unpacked, shared by every game."""
        return self.runtime_dir / "helixsr"

    def _hlx_fsr4(self):
        """HLX FSR 4: (dll, tag).

        HelixSR Desktop's, when that app has set HelixSR up here; otherwise
        that of the HelixSR release the plugin downloaded (or the one pinned).
        Releases no longer in use go once it is there; see hlx.prune.
        """
        desktop = self.helixsr_desktop()
        if desktop:
            return hlx.hlx_file(desktop["root"]), helixsr.tag(desktop)
        dll, tag = hlx.fetch(self.helixsr_cache(), self.log, self.target_tag("helixsr"))
        building = self.hlx_build.status()["tag"] if self.hlx_build.running else None
        hlx.prune(self.helixsr_cache(), {tag, building} - {None})
        return dll, tag

    def _build_hlx_in(self, folder, tag):
        """Build HLX DLSS in an unpacked release (``hlx_build`` begun); raise when it is not.

        One that has it built already is left as it is.
        """
        self.hlx_build.say("HelixSR 받음", tag)
        if not helixsr.network_built(Path(folder) / HELIXSR_DIR / HELIXSR_DLL):
            self.hlx_build.run(folder, self.home, self.log)
        # The build HLX DLSS installs copy now; older ones go.
        hlx.prune(self.helixsr_cache(), {tag})

    # -- HLX DLSS built here ---------------------------------------------
    async def build_hlx_dlss(self):
        """Start HelixSR's setup building HLX DLSS in the pinned (or newest) release.

        The UI asks the user to agree to NVIDIA's licence first: the setup is
        handed NVIDIA's DLL, downloaded here, instead of asking itself.
        """
        if not self.hlx_build.begin():
            return {"ok": False, "error": "HLX DLSS를 이미 빌드하고 있습니다.",
                    "build": self.hlx_build.status()}
        self._hlx_build_task = asyncio.get_running_loop().create_task(self._build_hlx_dlss())
        return {"ok": True, "build": self.hlx_build.status()}

    async def _build_hlx_dlss(self):
        error = None
        try:
            self.hlx_build.say("HelixSR 받는 중")
            folder, tag = await self._run(hlx.fetch_release, self.helixsr_cache(), self.log,
                                          self.target_tag("helixsr"))
            await self._run(self._set_installed, "helixsr", tag)
            await self._run(self._build_hlx_in, folder, tag)
        except Exception as exc:
            self.log.exception("HLX DLSS build failed")
            error = str(exc) or type(exc).__name__
        self.hlx_build.finish(error)

    async def get_hlx_dlss_build(self):
        """The build's progress, and the HelixSR build HLX DLSS comes from now."""
        return {**self.hlx_build.status(), "helixsr": await self._run(self.helixsr_build)}

    async def cancel_hlx_dlss_build(self):
        return {"ok": await self._run(self.hlx_build.cancel)}

    # -- the plugin's own downloads: set up once, updated from Settings ---
    def installed_tag(self, channel):
        """The build of ``channel`` the plugin set up (or last updated to), if still on disk."""
        if channel == "nightly":
            return (self.nightly.current() or {}).get("tag")
        tag = (self.settings.get("installed") or {}).get(channel)
        if channel == "dropin":
            variants = dict.fromkeys(CYBOMAN_VARIANTS.values())
            return tag if all(dropin.has(self.dropin_cache(), tag, v) for v in variants) else None
        return tag if tag and tag in hlx.kept(self.helixsr_cache()) else None

    def target_tag(self, channel):
        """The build installs take from ``channel``: the pinned one, else the one set up."""
        return self.pinned(channel) or self.installed_tag(channel)

    def _set_installed(self, channel, tag):
        installed = dict(self.settings.get("installed") or {})
        installed[channel] = tag
        self.settings.set("installed", installed)

    def helixsr_desktop(self):
        """HelixSR Desktop's build (or one set up by hand), when it is whole, or None.

        Whole is HLX DLSS and HLX FSR 4 both built: then HelixSR comes from it,
        and its updates are that app's to make.
        """
        build = helixsr.find(self.home)
        if build.get("found") and build.get("dlss_ready") and helixsr.hlx_built(hlx.hlx_file(build["root"])):
            return build
        return None

    def _cyboman_used(self):
        return any(upscaler in self.allowed_upscalers() for upscaler in CYBOMAN_VARIANTS)

    def _update_for(self, channel, installed, desktop):
        """What the last check found newer than ``installed``: {latest, update}."""
        _, found = self._channel_lists.get(channel, (0, None))
        if not found:
            return {"latest": None, "update": False}
        latest = found[0]
        if channel == "helixsr" and desktop:
            have, new = _version_tuple(desktop.get("version")), _version_tuple(latest.get("version"))
            return {"latest": latest["tag"], "update": bool(have and new and new > have)}
        update = bool(installed) and not self.pinned(channel) and installed != latest["tag"]
        return {"latest": latest["tag"], "update": update}

    def components(self):
        """What the plugin has downloaded and whether newer builds are out, without the network.

        HelixSR comes from HelixSR Desktop when that app has set it up here;
        one that did and is gone is said (``desktop_missing``) until the plugin
        sets HelixSR up itself.
        """
        desktop = self.helixsr_desktop()
        seen = bool(self.settings.get("helixsr_desktop_seen"))
        if desktop and not seen:
            self.settings.set("helixsr_desktop_seen", True)
            seen = True
        build = self.helixsr_build()
        helixsr_tag = self.installed_tag("helixsr")
        plugin_ready = bool(helixsr_tag and build.get("plugin") and build.get("dlss_ready"))
        nightly = self.release()
        channels = {
            "nightly": {"installed": self.installed_tag("nightly"), "version": nightly.get("version"),
                        "used": True},
            "dropin": {"installed": self.installed_tag("dropin"), "used": self._cyboman_used()},
            "helixsr": {
                "installed": helixsr_tag, "used": True,
                "source": "desktop" if desktop else ("plugin" if helixsr_tag else None),
                "desktop_version": desktop.get("version") if desktop else None,
                "desktop_root": desktop.get("root") if desktop else None,
                "dlss_ready": bool(build.get("dlss_ready")),
                "desktop_missing": seen and not desktop and not plugin_ready,
            },
        }
        for channel, entry in channels.items():
            entry["pinned"] = self.pinned(channel)
            entry.update(self._update_for(channel, entry["installed"], desktop)
                         if entry["used"] else {"latest": None, "update": False})
        return {
            "setup_done": bool(self.settings.get("setup_done")),
            "job": self.job.status(),
            "build": self.hlx_build.status(),
            "channels": channels,
            "updates": [channel for channel, entry in channels.items() if entry["update"]],
            "checked_at": self._updates_checked_at,
            "update_error": self._update_error,
        }

    async def get_components(self):
        return await self._run(self.components)

    async def check_updates(self, force=False):
        """Ask each channel for its newest build, every few hours or with ``force``.

        Only asked, nothing downloaded: Settings updates what the user picks.
        """
        listers = {"nightly": self.nightly.releases, "dropin": dropin.releases, "helixsr": hlx.releases}
        errors, asked = [], False
        for channel, lister in listers.items():
            if channel == "dropin" and not self._cyboman_used():
                continue
            when, found = self._channel_lists.get(channel, (0, None))
            if found is not None and not force and time.time() - when < UPDATE_CHECK_TTL:
                continue
            asked = True
            try:
                self._channel_lists[channel] = (time.time(), await self._run(lister))
            except Exception as exc:
                errors.append(f"{channel}: {type(exc).__name__}: {exc}")
        if asked:
            self._updates_checked_at = time.time()
            self._update_error = "; ".join(errors) or None
        return await self.get_components()

    async def start_setup(self):
        """Download everything installs use, and build HLX DLSS, in the background.

        OptiScaler's nightly, cyboman's builds (where this machine can pick
        them) and a HelixSR release with HLX DLSS built in it, unless HelixSR
        Desktop has set HelixSR up here. The plugin is set up once the
        downloads are there; HLX DLSS failing to build is said, and can be
        built again from Settings, without holding up the rest. The UI asks the
        user to agree to NVIDIA's licence first.
        """
        steps = [("nightly", "OptiScaler nightly"), ("dropin", "cyboman FSR 4.1.2 Lite"),
                 ("helixsr", "HelixSR (HLX FSR 4)"), ("hlx_dlss", "HLX DLSS 빌드")]
        return await self._start_job("setup", steps, CHANNELS)

    async def update_component(self, channel):
        """Download ``channel``'s newest build (or the pinned one), in the background.

        HelixSR is built again in the new release. HelixSR Desktop's HelixSR is
        that app's to update.
        """
        if channel not in CHANNELS:
            return {"ok": False, "error": f"unknown channel {channel}"}
        if channel == "helixsr" and await self._run(self.helixsr_desktop):
            return {"ok": False, "error": "HelixSR Desktop의 HelixSR를 쓰고 있습니다. "
                                          "HelixSR Desktop에서 업데이트하세요."}
        steps = {"nightly": [("nightly", "OptiScaler nightly")],
                 "dropin": [("dropin", "cyboman FSR 4.1.2 Lite")],
                 "helixsr": [("helixsr", "HelixSR (HLX FSR 4)"), ("hlx_dlss", "HLX DLSS 빌드")]}[channel]
        return await self._start_job("update", steps, [channel], channel)

    async def _start_job(self, kind, steps, channels, channel=None):
        if "helixsr" in channels and self.hlx_build.running:
            return {"ok": False, "error": "HLX DLSS를 빌드하고 있습니다. 끝난 뒤 다시 시도하세요."}
        if not self.job.begin(kind, steps, channel):
            return {"ok": False, "error": "다른 설치나 업데이트가 진행 중입니다."}
        self._job_task = asyncio.get_running_loop().create_task(
            self._fetch_components(channels, setup=kind == "setup"))
        return {"ok": True, "components": await self.get_components()}

    async def _job_step(self, key, work):
        self.job.step(key, jobs.RUNNING)
        try:
            result = await work()
        except Exception as exc:
            self.job.step(key, jobs.FAILED, str(exc) or type(exc).__name__)
            raise
        self.job.step(key, jobs.DONE, result[1] if isinstance(result, tuple) else result)
        return result

    async def _fetch_components(self, channels, setup=False):
        error = None
        try:
            if "nightly" in channels:
                await self._job_step("nightly", self._fetch_nightly)
            if "dropin" in channels:
                if self._cyboman_used():
                    await self._job_step("dropin", lambda: self._run(self._fetch_cyboman))
                else:
                    self.job.step("dropin", jobs.SKIPPED, "이 기기에서는 쓰지 않습니다.")
            if "helixsr" in channels:
                desktop = await self._run(self.helixsr_desktop)
                if desktop:
                    detail = f"HelixSR Desktop의 HelixSR {desktop.get('version') or ''}를 씁니다."
                    self.job.step("helixsr", jobs.SKIPPED, detail)
                    self.job.step("hlx_dlss", jobs.SKIPPED, detail)
                else:
                    folder, tag = await self._job_step("helixsr", lambda: self._run(self._fetch_helixsr))
                    try:
                        await self._job_step("hlx_dlss", lambda: self._build_hlx_job(folder, tag))
                    except Exception:
                        pass  # said in its step: everything but HLX DLSS works without it
            if setup:
                await self._run(self.settings.set, "setup_done", True)
        except Exception as exc:
            self.log.exception("setting up the plugin's downloads failed")
            error = str(exc) or type(exc).__name__
        self.job.finish(error)

    async def _fetch_nightly(self):
        await self.ensure_payload(force=True)
        return self.release()["tag"]

    def _fetch_cyboman(self):
        tag = None
        for variant in dict.fromkeys(CYBOMAN_VARIANTS.values()):
            _, tag = dropin.fetch(self.dropin_cache(), self.log, variant, self.pinned("dropin"))
        self._set_installed("dropin", tag)
        dropin.prune(self.dropin_cache(), {tag})
        return tag

    def _fetch_helixsr(self):
        folder, tag = hlx.fetch_release(self.helixsr_cache(), self.log, self.pinned("helixsr"))
        self._set_installed("helixsr", tag)
        # The plugin's HelixSR now: a HelixSR Desktop gone since is no longer news.
        self.settings.set("helixsr_desktop_seen", False)
        hlx.prune(self.helixsr_cache(), {tag})
        return folder, tag

    async def _build_hlx_job(self, folder, tag):
        if not self.hlx_build.begin():
            raise RuntimeError("HLX DLSS를 이미 빌드하고 있습니다.")
        error = None
        try:
            await self._run(self._build_hlx_in, folder, tag)
        except Exception as exc:
            self.log.exception("HLX DLSS build failed")
            error = str(exc) or type(exc).__name__
        self.hlx_build.finish(error)
        if error:
            raise RuntimeError(error)
        return tag

    async def remove_downloads(self):
        """Remove everything the plugin downloaded; games keep what was installed in them.

        The plugin goes back to its set-up. HelixSR's setup tools go too, unless
        HelixSR Desktop, which shares them, is here.
        """
        if self.job.running or self.hlx_build.running:
            return {"ok": False, "error": "설치나 업데이트가 진행 중입니다. 끝난 뒤 다시 시도하세요."}
        async with self._payload_lock:
            def work():
                for name in RUNTIME_DOWNLOADS:
                    shutil.rmtree(self.runtime_dir / name, ignore_errors=True)
                self.nightly.dir.mkdir(parents=True, exist_ok=True)
                if not (self.home / HELIXSR_DESKTOP_DATA).exists():
                    shutil.rmtree(self.home / HELIXSR_TOOLS_DIR, ignore_errors=True)
                self.settings.set("installed", {})
                self.settings.set("setup_done", False)
                self.settings.set("helixsr_desktop_seen", False)
            await self._run(work)
        return {"ok": True, "components": await self.get_components()}

    async def get_dropin(self, game_path):
        """Whether this game can take the FSR drop-in, and whether it has it."""
        def work():
            state = dropin.status(game_path)
            if state.get("possible"):
                state["optiscaler_installed"] = installer.detect(state["dir"])["installed"]
            if state.get("installed"):
                # Which of the picked upscalers this drop-in is.
                state["upscaler"] = next(
                    (name for name, variant in DROPIN_VARIANTS.items()
                     if variant == state.get("variant")), None)
            return state

        return await self._run(work)

    async def install_dropin(self, game_path, upscaler=UPSCALER_LITE_LOSSY):
        """Swap the game's FSR 3.1 DLL for an FSR 4 drop-in, keeping the original.

        ``upscaler`` is one of cyboman's FSR 4.1.2 Lite builds or HLX FSR 4,
        downloaded; or FSR 4 Lite, AMD's FSR 4.1.2 file from the OptiScaler
        nightly, as a test.
        """
        try:
            variant = DROPIN_VARIANTS.get(upscaler)
            if not variant:
                return {"ok": False, "error": f"{upscaler}은(는) 드롭인으로 넣는 업스케일러가 아닙니다."}
            refused = self._refuse_on_device(upscaler)
            if refused:
                return {"ok": False, "error": refused}
            state = await self._run(dropin.status, game_path)
            if not state.get("possible"):
                return {"ok": False, "error": "이 게임에는 교체할 FSR 3.1 DLL이 없습니다"}
            if (await self._run(installer.detect, state["dir"]))["installed"]:
                return {"ok": False, "error": "이 게임에는 OptiScaler가 설치되어 있습니다. 드롭인을 쓰려면 먼저 OptiScaler를 제거하세요."}
            if await self._run(helixsr.foreign_install, state["dir"]):
                return {"ok": False, "error": "이 게임에는 HelixSR Desktop이 설치한 HelixSR가 있습니다. "
                                              "HelixSR Desktop에서 먼저 제거하세요."}
            if await self._run(installer.in_use, state["dir"]):
                return {"ok": False, "error": "게임이 실행 중입니다. 게임을 종료한 뒤 다시 시도하세요."}
            payload_root = None
            if upscaler == UPSCALER_HLX_FSR4:
                source, tag = await self._run(self._hlx_fsr4)
            elif upscaler == UPSCALER_FSR4_LITE:
                payload_root = await self.ensure_payload()
                source, tag = Path(payload_root) / FFX_UPSCALER_DLL, self.release()["tag"]
            else:
                source, tag = await self._run(dropin.fetch, self.dropin_cache(), self.log, variant,
                                              self.target_tag("dropin"))
                if state["layout"] == "monolithic":
                    payload_root = await self.ensure_payload()
            async with self._mutation_lock:
                result = await self._run(dropin.install, game_path, source, tag, payload_root,
                                         self.log, variant)
            return {"ok": True, **result}
        except Exception as exc:
            self.log.exception("FSR drop-in failed for %s", game_path)
            return {"ok": False, "error": str(exc)}

    async def remove_dropin(self, game_path):
        """Put the game's own FidelityFX files back."""
        try:
            state = await self._run(dropin.status, game_path)
            if state.get("possible") and await self._run(installer.in_use, state["dir"]):
                return {"ok": False, "error": "게임이 실행 중입니다. 게임을 종료한 뒤 다시 시도하세요."}
            async with self._mutation_lock:
                result = await self._run(dropin.uninstall, game_path, self.log)
            return {"ok": True, **result}
        except Exception as exc:
            self.log.exception("FSR drop-in removal failed for %s", game_path)
            return {"ok": False, "error": str(exc)}

    # -- monitoring ------------------------------------------------------
    async def get_monitor(self, target_dir):
        return await self._run(monitor.status, target_dir)

    async def clear_log(self, target_dir):
        cleared = await self._run(monitor.clear_log, target_dir)
        return {"ok": cleared}

    async def set_logging(self, target_dir, enabled):
        """Toggle LogToFile, which monitoring depends on."""
        return await self.write_config(
            target_dir,
            [
                {"section": "Log", "key": "LogToFile", "value": "true" if enabled else "false"},
                {"section": "Log", "key": "LogLevel", "value": "2" if enabled else "auto"},
                {"section": "Log", "key": "SingleFile", "value": "true"},
            ],
        )


def _optipatcher_outdated(target_dir, current):
    """Whether this game has OptiPatcher, and it is not the build installs use now."""
    from .payload import sha256
    path = Path(target_dir) / PLUGIN_SUBDIR / OPTIPATCHER_NAME
    return bool(current and path.is_file() and sha256(path) != current["sha256"])


def _find_named(root, name, depth):
    """Files called ``name`` (any case) under ``root``, newest first."""
    import os
    root = Path(root)
    if not root.is_dir():
        return []
    found = []
    base = len(root.parts)
    for dirpath, dirnames, filenames in os.walk(root):
        if len(Path(dirpath).parts) - base >= depth:
            dirnames[:] = []
        dirnames[:] = [d for d in dirnames if not d.startswith(".")]
        found += [Path(dirpath) / f for f in filenames if f.lower() == name.lower()]
    return sorted(found, key=lambda p: p.stat().st_mtime, reverse=True)


def _is_pd(plan):
    """Whether a REFramework plan is the pd-upscaler branch with PDPerfPlugin."""
    return bool(plan and plan.get("required") and plan.get("variant") == "pd-upscaler")


def _auto_key(game_path):
    """Preference key holding whether one game is in automatic mode."""
    return f"auto_mode:{game_path}"


def _version_tuple(version):
    """"3.2.0" as (3, 2, 0); None for anything else."""
    try:
        return tuple(int(part) for part in str(version).split("."))
    except (TypeError, ValueError):
        return None
