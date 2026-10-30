#!/usr/bin/env python3
"""End-to-end backend test against a synthetic Steam library in a temp dir.

Exercises library discovery, executable-folder scoring, the wiki lookup (needs
network; skipped gracefully offline), install/detect/uninstall round trips with
the FSR 4 Lite preset, the nightly channel, and comment-preserving INI edits.

OptiScaler is not bundled, so installs here come from a synthetic unpacked
release shaped like a v10 nightly; the nightly channel itself is driven through
a fake transport. Nothing here downloads OptiScaler.
"""

import asyncio
import hashlib
import json
import logging
import os
import re
import shutil
import subprocess
import sys
import tempfile
import time
import urllib.error
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "py_modules"))

from optiscaler.service import OptiScalerService  # noqa: E402
from optiscaler import wiki as _wiki  # noqa: E402


def _offline(*args, **kwargs):
    raise OSError("selftest: no network")


# Installs download what they need (the nightly's custom upscalers among them);
# no check reaches the network unless it fakes what it wants back.
_wiki.download = _wiki.download_json = _offline
from optiscaler import installer  # noqa: E402
from optiscaler.inifile import IniFile  # noqa: E402
from optiscaler.constants import COMPAT_CACHE_TTL, DECK_FSR4_PRESET, INI_NAME  # noqa: E402

PASSED = []
FAILED = []


def check(name, condition, detail=""):
    (PASSED if condition else FAILED).append(name)
    mark = "ok  " if condition else "FAIL"
    print(f"  [{mark}] {name}{(' — ' + str(detail)) if detail else ''}")


def build_fixture(root):
    """A Steam install with two libraries and two differently-shaped games."""
    home = root / "home"
    steam = home / ".local" / "share" / "Steam"
    lib2 = root / "sdcard"
    (steam / "steamapps" / "common").mkdir(parents=True)
    (lib2 / "steamapps" / "common").mkdir(parents=True)
    (home / ".steam").mkdir(parents=True, exist_ok=True)
    os.symlink(steam, home / ".steam" / "steam")

    (steam / "steamapps" / "libraryfolders.vdf").write_text(
        '"libraryfolders"\n{\n\t"0"\n\t{\n\t\t"path"\t\t"%s"\n\t}\n'
        '\t"1"\n\t{\n\t\t"path"\t\t"%s"\n\t}\n}\n' % (steam, lib2)
    )
    (steam / "steamapps" / "appmanifest_1091500.acf").write_text(
        '"AppState"\n{\n\t"appid"\t\t"1091500"\n\t"name"\t\t"Cyberpunk 2077"\n'
        '\t"installdir"\t\t"Cyberpunk 2077"\n\t"SizeOnDisk"\t\t"73819938816"\n}\n'
    )
    (steam / "steamapps" / "appmanifest_228980.acf").write_text(
        '"AppState"\n{\n\t"appid"\t\t"228980"\n\t"name"\t\t"Steamworks Common Redistributables"\n'
        '\t"installdir"\t\t"Steamworks Shared"\n}\n'
    )
    (lib2 / "steamapps" / "appmanifest_2358720.acf").write_text(
        '"AppState"\n{\n\t"appid"\t\t"2358720"\n\t"name"\t\t"Black Myth Wukong"\n'
        '\t"installdir"\t\t"BlackMythWukong"\n\t"SizeOnDisk"\t\t"1"\n}\n'
    )

    # Cyberpunk: launcher at the root, real binary under bin/x64.
    cp = steam / "steamapps" / "common" / "Cyberpunk 2077"
    (cp / "bin" / "x64").mkdir(parents=True)
    (cp / "REDprelauncher.exe").write_bytes(b"MZ")
    (cp / "bin" / "x64" / "Cyberpunk2077.exe").write_bytes(b"MZ" + b"\0" * (60 << 20))
    (steam / "steamapps" / "common" / "Steamworks Shared").mkdir(parents=True)

    # Unreal: real binary under <Project>/Binaries/Win64, Engine/ must be ignored.
    bmw = lib2 / "steamapps" / "common" / "BlackMythWukong"
    (bmw / "Engine" / "Binaries" / "Win64").mkdir(parents=True)
    (bmw / "b1" / "Binaries" / "Win64").mkdir(parents=True)
    (bmw / "Engine" / "Binaries" / "Win64" / "UnrealEditor.exe").write_bytes(b"MZ")
    (bmw / "b1" / "Binaries" / "Win64" / "b1-Win64-Shipping.exe").write_bytes(b"MZ" + b"\0" * (80 << 20))
    (bmw / "b1" / "Binaries" / "Win64" / "CrashReportClient.exe").write_bytes(b"MZ")
    return home


#: What the synthetic release says it is, as the nightly channel would.
FAKE_RELEASE = {"tag": "nightly-20990101", "version": "10.0.0-test"}


def _ffx_upscaler(version=(4, 1, 1, 2740)):
    """Bytes carrying a VS_FIXEDFILEINFO with ``version``, for pe_file_version."""
    import struct
    major, minor, patch, build = version
    return (b"MZ" + b"\0" * 62 + b"\xbd\x04\xef\xfe" + b"\0" * 4
            + struct.pack("<HHHH", minor, major, build, patch))


def build_payload(root):
    """An unpacked release shaped like a v10 nightly: the proxy, the stock ini,
    the OptiScaler/ library folder and Licenses/."""
    payload = root / "payload"
    (payload / "OptiScaler" / "D3D12_OptiScaler").mkdir(parents=True)
    (payload / "Licenses").mkdir()
    (payload / "OptiScaler.dll").write_bytes(b"OptiScaler" + b"\0" * (5 << 20))
    shutil.copy2(ROOT / "defaults" / "OptiScaler.reference.ini", payload / INI_NAME)
    (payload / "OptiScaler" / "amd_fidelityfx_upscaler_dx12.dll").write_bytes(_ffx_upscaler())
    (payload / "OptiScaler" / "libxess.dll").write_bytes(b"XESS" * 64)
    (payload / "OptiScaler" / "D3D12_OptiScaler" / "D3D12Core.dll").write_bytes(b"D3D12" * 64)
    (payload / "Licenses" / "XeSS_LICENSE.txt").write_text("license")
    return payload


def use_payload(service, payload):
    """Point a service at a synthetic release instead of the nightly channel."""
    service.payload.ensure = lambda force=False, logger=None, tag=None: payload
    service.nightly.current = lambda: dict(FAKE_RELEASE)


async def run():
    root = Path(tempfile.mkdtemp(prefix="decky-optiscaler-selftest-"))
    try:
        home = build_fixture(root)
        service = OptiScalerService(
            ROOT, root / "settings", root / "runtime", home, logging.getLogger("selftest")
        )

        print("\nPayload")
        status = await service.get_status()
        check("nothing is bundled: no nightly until the first install",
              not status["archive_present"] and status["optiscaler_version"] is None, status)
        check("nor any AMD driver library: the nightly's own FSR 4.1.2 carries INT8 Lite",
              not (ROOT / "bin").exists() and "driver_dlls" not in status)
        use_payload(service, build_payload(root))
        status = await service.get_status()

        print("\nLibraries and games")
        libraries = await service.list_libraries()
        check("two steam libraries found", len(libraries) == 2, [l["name"] for l in libraries])
        added = await service.add_custom_library(str(root / "sdcard" / "steamapps" / "common"))
        check("custom library added", added["ok"])
        check("duplicate library rejected",
              not (await service.add_custom_library(str(root / "sdcard" / "steamapps" / "common")))["ok"])
        libraries = await service.list_libraries()
        check("custom library listed", any(l["source"] == "custom" for l in libraries))

        games = await service.list_games(libraries[0]["path"])
        names = [g["name"] for g in games]
        check("game listed", "Cyberpunk 2077" in names, names)
        check("redistributables filtered out",
              not any("Steamworks" in n for n in names), names)

        print("\nInstall target detection")
        cyberpunk = next(g for g in games if g["name"] == "Cyberpunk 2077")
        detail = await service.get_game(cyberpunk["path"], cyberpunk["name"])
        check("launcher folder rejected in favour of bin/x64",
              detail["target"].endswith("bin/x64"), detail["target"])
        wukong = await service.get_game(
            str(root / "sdcard" / "steamapps" / "common" / "BlackMythWukong"), "Black Myth Wukong"
        )
        check("unreal project binaries chosen over Engine/",
              wukong["target"].endswith("b1/Binaries/Win64"), wukong["target"])

        print("\nWiki name matching")
        from optiscaler.wiki import WikiClient  # noqa: E402
        # Against the bundled seed rather than whatever the wiki serves today.
        # With no seed this fell through to a synchronous download, so the
        # matcher was being graded on a page a few hundred people can edit:
        # when one row lost its leading pipe upstream, two of these probes
        # started failing and the build went red on a commit that had not
        # touched the matcher. What the live page does to the *parser* is
        # check_compat_list_shapes()'s business, from a fixture.
        wiki = WikiClient(root / "runtime" / "wiki-cache",
                          ROOT / "defaults" / "compat-list.json")
        wiki_entries, wiki_meta = wiki.load_entries()
        if not wiki_entries:
            print("  (offline — skipped)")
        else:
            expected = {
                "Expedition 33": "Clair Obscur: Expedition 33",
                "Cyberpunk 2077": "Cyberpunk 2077",
                "BlackMythWukong": "Black Myth: Wukong",
                "Talos Principle 2": "The Talos Principle 2",
                "Oblivion Remastered": "The Elder Scrolls IV: Oblivion Remastered",
            }
            for probe, want in expected.items():
                hit = wiki.match(probe, wiki_entries)
                check(f"matches {probe!r}", hit is not None and hit["name"] == want,
                      hit["name"] if hit else "no match")
            for probe in ("Balatro", "Stardew Valley", "Totally Made Up Game 9000"):
                check(f"no false positive for {probe!r}",
                      wiki.match(probe, wiki_entries) is None)

        print("\nWiki lookup")
        recommendation = await service.get_recommendation("Cyberpunk 2077")
        if recommendation["list_meta"]["error"] and not recommendation["matched"]:
            print("  (offline — skipped)")
        else:
            check("matched the compatibility list", recommendation["matched"], recommendation["game"])
            # The answer is two-phase now. The compatibility-list row answers
            # at once, and this game's own wiki page — which is what states the
            # filename outright — arrives behind it. Fetching it in front of
            # the answer is what made the setup tab hang for ever on a Deck
            # whose route to the wiki stalls.
            check("the first answer says its wiki page is still coming",
                  recommendation["detail_pending"] is True
                  or recommendation["filename_source"] == "wiki entry",
                  f"pending={recommendation['detail_pending']} "
                  f"via {recommendation['filename_source']}")
            for _ in range(200):
                await asyncio.sleep(0.05)
                if not service._wiki_jobs:
                    break
            settled = await service.get_recommendation("Cyberpunk 2077")
            check("and once it lands the filename comes from that entry",
                  settled["filename_source"] == "wiki entry"
                  and not settled["detail_pending"],
                  f"{settled['filename']} via {settled['filename_source']}")

        print("\nSchema generation")
        from optiscaler.schema_generated import OPTIONS  # noqa: E402
        by_id = {(o["section"], o["key"]): o for o in OPTIONS}
        multiplier = by_id[("XeFG", "InterpolationCount")]
        check("frame multiplier is a 2X/3X/4X choice, not a toggle",
              multiplier["type"] == "enum" and multiplier["options"] == ["1", "2", "3"],
              f"{multiplier['type']} {multiplier.get('options')}")
        check("multiplier labelled 2X/3X/4X",
              multiplier.get("optionLabels") == {"1": "2X", "2": "3X", "3": "4X"})
        dx12 = by_id[("Upscalers", "Dx12Upscaler")]
        check("v10's ffx backend is a choice, documented as serving FSR 4",
              dx12["type"] == "enum" and "4.x" in (dx12.get("optionLabels") or {}).get("ffx", ""),
              (dx12.get("optionLabels") or {}).get("ffx"))

        print("\nInstall / uninstall round trip")
        target = Path(detail["target"])
        original = b"THE GAME'S OWN DXGI" * 8
        (target / "dxgi.dll").write_bytes(original)
        # Games that ship their own FidelityFX DLLs must get them back intact.
        game_upscaler = b"GAME'S OWN FSR31 UPSCALER" * 8
        (target / "amd_fidelityfx_upscaler_dx12.dll").write_bytes(game_upscaler)
        (target / "Licenses").mkdir(exist_ok=True)
        (target / "Licenses" / "game.txt").write_text("GAME LICENSE")

        result = await service.install(str(target), "dxgi.dll")
        check("install succeeded", result["ok"], result.get("error"))
        check("launch option built",
              result.get("launch_option") == 'WINEDLLOVERRIDES="dxgi=n,b" %command%',
              result.get("launch_option"))
        check("original dll backed up", "dxgi.dll" in (result.get("backups") or {}))
        stash = target / "decky_optiscaler_backup_files"
        check("backup folder created", stash.is_dir(), stash.name)
        check("game's own Licenses folder set aside", (stash / "Licenses").is_dir())
        # v10 reads its FidelityFX libraries from OptiScaler/, so the game's own
        # copy at the root is a different file and is left exactly where it is.
        check("game's own FidelityFX dll left alone at the root",
              (target / "amd_fidelityfx_upscaler_dx12.dll").read_bytes() == game_upscaler)
        check("OptiScaler's libraries land in their own folder",
              (target / "OptiScaler" / "amd_fidelityfx_upscaler_dx12.dll").is_file()
              and (target / "OptiScaler" / "D3D12_OptiScaler" / "D3D12Core.dll").is_file())
        check("the install records which nightly it came from",
              result.get("tag") == FAKE_RELEASE["tag"]
              and installer.read_manifest(target).get("optiscaler_tag") == FAKE_RELEASE["tag"])

        # FSR 4 Lite: the preset in the ini, and nothing else needed to reach
        # FSR 4 on a Deck. The [FSR] keys stay OptiScaler's own defaults.
        ini_after = IniFile(target / INI_NAME).to_dict()
        wrong = [f"{section}.{key}" for section, values in DECK_FSR4_PRESET.items()
                 for key, value in values.items()
                 if ini_after.get(section, {}).get(key) != value]
        check("the FSR 4 Lite preset is in the ini", not wrong, wrong)
        check("and leaves the FSR 4 GPU, model and backend index to OptiScaler",
              all(ini_after.get("FSR", {}).get(key) == "auto"
                  for key in ("Fsr4GpuSupport", "Fsr4Model", "UpscalerIndex")),
              ini_after.get("FSR"))
        check("and detect reports the folder FSR 4 Lite ready",
              installer.detect(str(target))["fsr4"]["ready"])
        check("asi loading is on, ready for OptiPatcher whenever it goes in",
              ini_after.get("Plugins", {}).get("LoadAsiPlugins") == "true",
              ini_after.get("Plugins"))

        info = installer.detect(str(target))
        check("install detected", info["installed"] and info["filename"] == "dxgi.dll")

        # The launch options are Steam's, so only the frontend can read them --
        # but they are the other half of an install and have to be recoverable.
        recorded = await service.record_launch_options(str(target), "gamemoderun %command%")
        check("previous launch options recorded", recorded["ok"] and recorded["written"])
        # The client getter is absent from some builds; the frontend then hands
        # over None and Steam's own config has to answer instead. Recording
        # nothing is what made the removal dialog inert on those Decks.
        blind = await service.record_launch_options(str(root / "nowhere"), None, "1091500")
        check("a frontend that could not read is refused, not recorded as empty",
              not blind["ok"] and not blind["recorded"], blind.get("error"))
        again = await service.record_launch_options(
            str(target), 'WINEDLLOVERRIDES="dxgi=n,b" %command%')
        check("recording again keeps the original, not our own override",
              not again["written"] and again["value"] == "gamemoderun %command%",
              again["value"])
        check("the record travels with the install detail",
              installer.detect(str(target))["launch_record"]
              == {"recorded": True, "value": "gamemoderun %command%"})

        check("recognised as plugin-managed", info["managed"])
        check("OptiScaler.ini written", info["ini_present"])

        print("\nSwitching filename")
        switched = await service.install(str(target), "winmm.dll")
        check("switch succeeded", switched["ok"])
        check("now installed as winmm.dll",
              installer.detect(str(target))["filename"] == "winmm.dll")
        check("original dxgi.dll restored on switch",
              (target / "dxgi.dll").read_bytes() == original)

        print("\nInstall verification / FSR 4 Lite")
        verified = await service.verify_install(str(target))
        check("every file of the release landed in the game folder",
              verified["ok"] and verified["complete"] and not verified["outdated"],
              verified.get("problems"))
        ffx = verified["ffx_upscaler"]
        check("FidelityFX upscaler present with a readable version",
              ffx["present"] and ffx["version"] == "4.1.1.2740", ffx)
        check("and it provides FSR 4", ffx["fsr4_capable"], ffx["version"])

        # The overlay saved its own choice over the preset; applying it again
        # puts it back.
        overlay = IniFile(target / INI_NAME)
        overlay.set("Upscalers", "Dx11Upscaler", "fsr22")
        overlay.save()
        check("an overlay save over the preset is noticed",
              not installer.detect(str(target))["fsr4"]["ready"])
        again = await service.apply_fsr4_preset(str(target))
        check("applying FSR 4 Lite again restores the preset",
              again["ok"] and again["fsr4"]["ready"], again.get("error"))

        # A newer nightly does not make an older install broken, only old.
        service.nightly.current = lambda: {"tag": "nightly-20990102", "version": "10.0.0-next"}
        older = await service.verify_install(str(target))
        check("a game installed from an older nightly reads as outdated, not broken",
              older["outdated"] and older["complete"]
              and older["installed_tag"] == FAKE_RELEASE["tag"], older.get("problems"))
        service.nightly.current = lambda: dict(FAKE_RELEASE)

        print("\nConfiguration")
        config = await service.read_config(str(target))
        sections = len(IniFile(ROOT / "defaults" / "OptiScaler.reference.ini").to_dict())
        check("ini parsed", config["ok"] and len(config["values"]) == sections,
              f"{len(config['values'])} of {sections}")
        before = (target / "OptiScaler.ini").read_text(encoding="utf-8")

        write = await service.write_config(str(target), [
            {"section": "FrameGen", "key": "Enabled", "value": "true"},
            {"section": "FrameGen", "key": "FGInput", "value": "fsrfg"},
            {"section": "Upscalers", "key": "Dx12Upscaler", "value": "xess"},
            {"section": "FrameGen", "key": "FGOutput", "value": "NOT_A_VALUE"},
            {"section": "Sharpness", "key": "Sharpness", "value": "9.9"},
        ])
        check("valid changes applied", len(write["applied"]) == 3, write["applied"])
        check("invalid enum rejected",
              any(r["key"] == "FGOutput" for r in write["rejected"]))
        check("out-of-range float rejected",
              any(r["key"] == "Sharpness" for r in write["rejected"]))

        after_ini = IniFile(target / "OptiScaler.ini")
        values = after_ini.to_dict()
        check("values persisted",
              values["FrameGen"]["Enabled"] == "true"
              and values["Upscalers"]["Dx12Upscaler"] == "xess")
        after = (target / "OptiScaler.ini").read_text(encoding="utf-8")
        check("every comment preserved",
              before.count(";") == after.count(";"),
              f"{before.count(';')} -> {after.count(';')}")

        print("\nManual wiki selection")
        if wiki_entries:
            found = await service.search_wiki("forza")
            names = [r["name"] for r in found["results"]]
            check("search finds Forza entries", "Forza Horizon 5" in names, names[:3])
            found = await service.search_wiki("expedition")
            check("search finds Expedition 33",
                  any("Expedition 33" in n for n in
                      [r["name"] for r in found["results"]]))
            await service.set_wiki_entry(cyberpunk["path"], "Forza Horizon 5")
            pinned = await service.get_recommendation(
                "Cyberpunk 2077", None, False, cyberpunk["path"]
            )
            check("pinned entry overrides name matching",
                  pinned["game"] == "Forza Horizon 5" and pinned.get("manual"),
                  pinned["game"])
            await service.set_wiki_entry(cyberpunk["path"], "")
            unpinned = await service.get_recommendation(
                "Cyberpunk 2077", None, False, cyberpunk["path"]
            )
            check("unpinning restores automatic matching",
                  unpinned["game"] == "Cyberpunk 2077", unpinned["game"])

            missing = await service.get_recommendation("Totally Made Up Game 9000")
            check("a miss reports the list as available, not broken",
                  missing["list_available"] and missing["entry_count"] > 0)
            check("a miss reports what was searched", missing["searched"] == ["Totally Made Up Game 9000"])
            check("a miss offers near misses to pick from", len(missing["near_misses"]) > 0)
        else:
            print("  (offline — skipped)")

        print("\nWiki refresh behind the answer")
        from optiscaler import wiki as wiki_mod
        real_get = wiki_mod._http_get
        served = []
        try:
            # A list already on disk, and a network that is slow enough that
            # waiting for it would be obvious in the answer's timing.
            service.wiki.list_cache.write_text(json.dumps({
                "fetched_at": time.time() - COMPAT_CACHE_TTL - 60,
                "entries": [{"name": "Cached Game", "key": "cachedgame", "page": None,
                             "compatibility": "OK", "inputs": "DLSS",
                             "optipatcher": False, "notes": ""}],
            }))

            def slow(url, *a, **k):
                served.append(url)
                time.sleep(0.4)
                return ("| Game | Compatibility | Inputs |\n|---|---|---|\n"
                        "| [Cached Game](Cached-Game) | OK | DLSS |\n"
                        "| [Brand New Game](Brand-New-Game) | OK | DLSS |\n")

            wiki_mod._http_get = slow
            started = time.monotonic()
            answer = await service.get_recommendation("Cached Game")
            elapsed = time.monotonic() - started
            check("a stale list still answers immediately", elapsed < 0.3, f"{elapsed:.2f}s")
            check("and answers from the cache it had", answer["matched"], answer.get("game"))
            check("the answer says the list behind it is old",
                  answer["list_meta"].get("stale") is True)
            before = answer["list_meta"].get("revision")

            # And the refresh really did run behind it.
            for _ in range(40):
                await asyncio.sleep(0.05)
                if not service._wiki_jobs:
                    break
            check("a refresh was started behind the answer", bool(served), served)
            after = await service.wiki_status()
            check("and the newer list replaced the cached one",
                  after["entry_count"] == 2 and after["revision"] != before,
                  f"{before} -> {after['revision']}")
            check("which is how the UI knows to redraw", bool(after["revision"]))

            # Single flight: three questions in a row are not three downloads.
            service.wiki.list_cache.write_text(json.dumps({
                "fetched_at": time.time() - COMPAT_CACHE_TTL - 60,
                "entries": after["entry_count"] * [
                    {"name": "Cached Game", "key": "cachedgame", "page": None,
                     "compatibility": "OK", "inputs": "DLSS",
                     "optipatcher": False, "notes": ""}],
            }))
            served.clear()
            await asyncio.gather(*(service.get_recommendation("Cached Game") for _ in range(3)))
            for _ in range(40):
                await asyncio.sleep(0.05)
                if not service._wiki_jobs:
                    break
            check("three questions in a row are one download, not three",
                  len(served) == 1, len(served))

            # The Forza Horizon 5 case: a game whose own wiki page has never
            # been cached, on a Deck whose route to the wiki stalls rather than
            # refusing. The page used to be fetched in front of the answer, so
            # the setup tab sat on "Checking the OptiScaler wiki…" for ever —
            # while a game whose page happened to be cached answered fine.
            shutil.rmtree(service.wiki.page_cache, ignore_errors=True)
            service.wiki.page_cache.mkdir(parents=True, exist_ok=True)
            service.wiki.list_cache.write_text(json.dumps({
                "fetched_at": time.time(),
                "entries": [{"name": "Cached Game", "key": "cachedgame",
                             "page": "Cached-Game", "compatibility": "OK",
                             "inputs": "DLSS", "optipatcher": False, "notes": ""}],
            }))

            def stalls(url, *a, **k):
                served.append(url)
                # Long enough that answering at all proves nothing waited for
                # it, short enough that the attempt finishes inside this test.
                time.sleep(1)
                raise TimeoutError("stalled")

            wiki_mod._http_get = stalls
            started = time.monotonic()
            answer = await service.get_recommendation("Cached Game")
            elapsed = time.monotonic() - started
            check("a game whose wiki page was never cached still answers at once",
                  elapsed < 0.3, f"{elapsed:.2f}s")
            check("and says the fuller answer is still coming",
                  answer["matched"] and answer["detail_pending"] is True)
            for _ in range(200):
                await asyncio.sleep(0.05)
                if not service._wiki_jobs:
                    break
            # And having failed once, it stops claiming a refresh is running —
            # a page the wiki will not serve kept one permanently in flight,
            # which is how "Reading this game's entry…" became permanent.
            await service.get_recommendation("Cached Game")
            await asyncio.sleep(0.1)
            check("a page that will not download stops being re-attempted",
                  not service._wiki_jobs, service._wiki_jobs)

            # A pinned entry's answer has to be comparable with the status the
            # UI watches. It used to invent its own metadata with no revision
            # in it, so every check read as "something changed" and the plan
            # reloaded every two seconds for ever.
            await service.set_wiki_entry(str(target), "Cached Game")
            pinned = await service.get_recommendation("Cached Game", game_path=str(target))
            state = await service.wiki_status()
            check("a pinned entry carries the same revision the watch compares",
                  pinned["list_meta"].get("revision") == state["revision"],
                  f"{pinned['list_meta'].get('revision')} vs {state['revision']}")
            check("and still says it was pinned by hand",
                  pinned["list_meta"]["source"] == "manual")
            await service.set_wiki_entry(str(target), None)
        finally:
            wiki_mod._http_get = real_get

        print("\nMonitoring")
        (target / "OptiScaler.log").write_text(
            "[12:00:01.1] [I] Running on Wine 9.0-GE!\n"
            "[12:00:01.2] [I] OptiScaler working as winmm.dll, system dll loaded\n"
            "[12:00:02.0] [I] Adapter Desc: AMD Custom GPU 0405\n"
            "[12:00:05.0] [I] Creating new FSR 4.0.2 upscaler\n"
            "[12:00:06.0] [I] XeFG swapchain created\n"
            "[12:00:07.0] [E] Something broke\n"
        )
        report = await service.get_monitor(str(target))
        check("upscaler read from log", report["state"]["upscaler"] == "FSR 4.0.2",
              report["state"]["upscaler"])
        check("frame generation path detected", report["frame_generation"] == ["XeFG"],
              report["frame_generation"])
        check("errors counted", report["counts"].get("error") == 1)
        check("configured values reported", report["configured"]["fg_enabled"] == "true")

        print("\nUninstall")
        removal = await service.uninstall(str(target))
        check("uninstall succeeded", removal["ok"])
        check("no install remains", not installer.detect(str(target))["installed"])
        check("game folder restored to original contents",
              sorted(p.name for p in target.iterdir())
              == ["Cyberpunk2077.exe", "Licenses", "amd_fidelityfx_upscaler_dx12.dll", "dxgi.dll"],
              sorted(p.name for p in target.iterdir()))
        check("original dll byte-identical", (target / "dxgi.dll").read_bytes() == original)
        check("game's own FidelityFX dll restored byte-identical",
              (target / "amd_fidelityfx_upscaler_dx12.dll").read_bytes() == game_upscaler)
        check("game's own Licenses folder restored",
              (target / "Licenses" / "game.txt").read_text() == "GAME LICENSE")
        check("backup folder cleaned up", not stash.exists())
        check("the launch-options record goes with the install",
              not installer.detect(str(target))["launch_record"]["recorded"])
        check("the driver libraries go with OptiScaler's folder",
              not (target / "OptiScaler").exists())
    finally:
        shutil.rmtree(root, ignore_errors=True)


def check_remembered_choices():
    """Answers the user asked to be remembered have to survive a restart.

    The launch-options question is the one that matters: without the override
    Proton loads its own DLL and OptiScaler never runs, so the install offers to
    set it - but only until the user says "remember my choice".
    """
    import tempfile
    from optiscaler.settings import Settings

    print("\nRemembered choices")
    root = Path(tempfile.mkdtemp(prefix="optiscaler-prefs-"))
    try:
        path = root / "settings.json"
        settings = Settings(path)
        check("an unanswered question has no stored answer",
              settings.get_pref("launch_options") is None)
        settings.set_pref("launch_options", "always")
        check("the answer survives a reload",
              Settings(path).get_pref("launch_options") == "always")
        settings.set_pref("launch_options", None)
        check("forgetting it puts the question back",
              Settings(path).get_pref("launch_options") is None)
        check("prefs do not disturb the rest of the file",
              Settings(path).get("custom_libraries") == [])
        # "Remember my choices" is stored as a boolean and defaults to on, so
        # False has to survive as an answer rather than reading as "unset" —
        # otherwise turning remembering off would silently turn itself back on.
        settings.set_pref("remember_choices", False)
        check("switching remembering off is itself remembered",
              Settings(path).get_pref("remember_choices", True) is False)
        check("an untouched switch defaults to on",
              Settings(path).get_pref("never_asked", True) is True)
    finally:
        shutil.rmtree(root, ignore_errors=True)


def check_launch_record():
    """Removing OptiScaler has to be able to undo the launch options too.

    Three states have to stay distinguishable, because each means a different
    thing on the removal dialog: no record at all (an older install, or a Steam
    build that would not report them - take out only our own override), a
    recorded empty string (the game genuinely had none - the field can be
    cleared outright), and a recorded value (put exactly that back).
    """
    import tempfile

    print("\nLaunch-options record")
    root = Path(tempfile.mkdtemp(prefix="optiscaler-launch-"))
    try:
        check("nothing recorded reads as nothing recorded",
              installer.read_launch_record(root) == {"recorded": False, "value": ""})

        installer.record_launch_options(root, "")
        check("an empty record is still a record — the game had none",
              installer.read_launch_record(root) == {"recorded": True, "value": ""})

        installer.record_launch_options(root, "mangohud %command%")
        check("write-once: the first answer is the one kept",
              installer.read_launch_record(root)["value"] == "",
              installer.read_launch_record(root)["value"])

        installer.forget_launch_options(root)
        installer.record_launch_options(root, 'PROTON_LOG=1 %command% -dx12')
        check("a real value round trips verbatim",
              installer.read_launch_record(root)["value"] == 'PROTON_LOG=1 %command% -dx12')
        check("the file is plain text next to the install",
              (root / "decky_optiscaler_previous_launch_options.txt").is_file())

        check("forgetting reports whether there was anything to forget",
              installer.forget_launch_options(root) is True
              and installer.forget_launch_options(root) is False)
    finally:
        shutil.rmtree(root, ignore_errors=True)


def check_launch_options_read():
    """Steam's own config is the answer when the client will not give one.

    `SteamClient.Apps.GetAppLaunchOptions` is missing from some client builds
    outright, and the first version of the removal dialog leaned on it alone:
    on those Decks it recorded nothing at install time and offered nothing at
    removal, so OptiScaler's own override was left behind and the whole feature
    looked like it had never shipped. This is the source that does not depend
    on an undocumented method existing.
    """
    import tempfile
    from optiscaler import steam as steam_mod

    print("\nLaunch options from Steam's config")
    root = Path(tempfile.mkdtemp(prefix="optiscaler-localconfig-"))
    try:
        home = root / "home"
        config = home / ".local" / "share" / "Steam" / "userdata" / "12345" / "config"
        config.mkdir(parents=True)
        (home / ".local" / "share" / "Steam" / "steamapps").mkdir(parents=True)
        (home / ".steam").mkdir(parents=True, exist_ok=True)
        os.symlink(home / ".local" / "share" / "Steam", home / ".steam" / "steam")

        check("nothing readable is not the same as nothing set",
              steam_mod.launch_options(home, "1091500") == {"found": False, "value": "",
                                                            "source": None})

        (config / "localconfig.vdf").write_text(
            '"UserLocalConfigStore"\n{\n\t"Software"\n\t{\n\t\t"Valve"\n\t\t{\n'
            '\t\t\t"Steam"\n\t\t\t{\n\t\t\t\t"apps"\n\t\t\t\t{\n'
            '\t\t\t\t\t"1091500"\n\t\t\t\t\t{\n'
            '\t\t\t\t\t\t"LaunchOptions"\t\t"mangohud %command% -dx12"\n'
            '\t\t\t\t\t}\n\t\t\t\t}\n\t\t\t}\n\t\t}\n\t}\n}\n'
        )
        found = steam_mod.launch_options(home, "1091500")
        check("the launch options are read out of localconfig.vdf",
              found["found"] and found["value"] == "mangohud %command% -dx12", found["value"])
        absent = steam_mod.launch_options(home, "2358720")
        check("a game with no entry has none, which is an answer not a gap",
              absent["found"] and absent["value"] == "", absent)

        # Older and newer clients disagree on the capitalisation of the path,
        # and a lookup that guesses wrong reads as "this user has no games".
        (config / "localconfig.vdf").write_text(
            '"userlocalconfigstore" { "software" { "valve" { "steam" { "apps" {'
            ' "1091500" { "launchoptions" "PROTON_LOG=1 %command%" } } } } } }'
        )
        check("the path is matched whatever its capitalisation",
              steam_mod.launch_options(home, "1091500")["value"] == "PROTON_LOG=1 %command%")

        # An override with quotes in it is the exact case this has to survive.
        (config / "localconfig.vdf").write_text(
            '"UserLocalConfigStore" { "Software" { "Valve" { "Steam" { "apps" { "1091500" {'
            ' "LaunchOptions" "WINEDLLOVERRIDES=\\"dxgi=n,b\\" %command%" } } } } } }'
        )
        check("an escaped quote in the value survives the round trip",
              steam_mod.launch_options(home, "1091500")["value"]
              == 'WINEDLLOVERRIDES="dxgi=n,b" %command%',
              steam_mod.launch_options(home, "1091500")["value"])
    finally:
        shutil.rmtree(root, ignore_errors=True)


def check_non_steam_shortcut():
    """A game Steam runs but has no install folder for.

    Everything else here starts from an app manifest, and a shortcut added by
    hand has none: Steam stores a command line and nothing more. Asking it for
    the install directory got no answer, so the library context menu's
    Upscaler Manager entry ended on "Steam did not report an install folder"
    for every non-Steam game — the panel, Now Playing and the page all failed
    on it identically, because all three come through one lookup. The folder
    the shortcut's target sits in is the answer.
    """
    import struct
    import tempfile
    import zlib
    from optiscaler import steam as steam_mod

    print("\nNon-Steam shortcuts")

    def encode(entries):
        """shortcuts.vdf as Steam writes it: binary KeyValues."""
        def field(marker, key, payload):
            return bytes([marker]) + key.encode() + b"\x00" + payload

        out = b""
        for index, entry in enumerate(entries):
            body = b""
            for key, value in entry.items():
                if isinstance(value, int):
                    body += field(0x02, key, struct.pack("<i", value))
                else:
                    body += field(0x01, key, value.encode() + b"\x00")
            out += field(0x00, str(index), body + b"\x08")
        return field(0x00, "shortcuts", out + b"\x08") + b"\x08"

    # Resolved, because the folder is: a shortcut's target is canonicalised
    # before it is handed back, so the temp dir has to be compared the same way.
    root = Path(tempfile.mkdtemp(prefix="optiscaler-shortcut-")).resolve()
    try:
        home = root / "home"
        steam_root = home / ".local" / "share" / "Steam"
        config = steam_root / "userdata" / "12345" / "config"
        config.mkdir(parents=True)
        (steam_root / "steamapps").mkdir(parents=True)
        (home / ".steam").mkdir(parents=True, exist_ok=True)
        os.symlink(steam_root, home / ".steam" / "steam")

        game = root / "Games" / "Some Launcher Game" / "Binaries" / "Win64"
        game.mkdir(parents=True)
        (game / "Game-Win64-Shipping.exe").write_bytes(b"MZ")

        # Steam stores the id signed and uses it unsigned; every shortcut it
        # has ever made has the top bit set, so the two always disagree.
        signed = -1234567890
        unsigned = str(signed & 0xFFFFFFFF)
        (config / "shortcuts.vdf").write_bytes(encode([
            {"appid": signed,
             "AppName": "Some Launcher Game",
             "Exe": f'"{game / "Game-Win64-Shipping.exe"}"',
             "StartDir": f'"{game}"'},
        ]))

        found = steam_mod.find_by_appid(home, unsigned)
        check("a shortcut is found by the id the library shows, not the stored one",
              found and found["path"] == str(game), found)
        check("and keeps the name Steam displays rather than the folder's",
              found and found["name"] == "Some Launcher Game", found)
        check("and is marked as a shortcut, not a Steam install",
              found and found["source"] == "shortcut", found)
        check("the signed form is not what the library asks with",
              steam_mod.find_by_appid(home, str(signed)) is None)

        # The client answers before the file does: shortcuts.vdf is flushed on
        # Steam's schedule, so a shortcut added this session is not in it yet.
        other = root / "Games" / "Added Just Now"
        other.mkdir(parents=True)
        (other / "game.exe").write_bytes(b"MZ")
        hinted = steam_mod.find_by_appid(home, "4200000000",
                                         exe=f'"{other / "game.exe"}"', name="Added Just Now")
        check("a target the client supplied resolves with nothing on disk to read",
              hinted and hinted["path"] == str(other), hinted)

        # A quoted path is how Steam stores every one of them, and a target
        # that has moved is not a folder to go writing into.
        check("a target that no longer exists is refused rather than guessed at",
              steam_mod.shortcut_folder('"/nowhere/at/all/game.exe"') is None)
        check("but its start directory is taken when that does exist",
              steam_mod.shortcut_folder('"/nowhere/at/all/game.exe"', f'"{game}"')
              == str(game))

        # Launch options for a shortcut are in this file, not localconfig.vdf,
        # where it has no entry at all. Reading the wrong one answers "this
        # game has none" — the state that lets removal clear the field — so a
        # wrapper command would have been deleted along with our override.
        (config / "shortcuts.vdf").write_bytes(encode([
            {"appid": signed,
             "AppName": "Some Launcher Game",
             "Exe": f'"{game / "Game-Win64-Shipping.exe"}"',
             "StartDir": f'"{game}"',
             "LaunchOptions": 'WINEDLLOVERRIDES="dxgi=n,b" mangohud %command%'},
        ]))
        options = steam_mod.launch_options(home, unsigned)
        check("a shortcut's launch options come out of shortcuts.vdf",
              options["found"] and options["value"]
              == 'WINEDLLOVERRIDES="dxgi=n,b" mangohud %command%', options)
        check("and an id that is in no shortcuts file is not called empty",
              steam_mod.launch_options(home, "4200000000")
              == {"found": False, "value": "", "source": None},
              steam_mod.launch_options(home, "4200000000"))

        # Very old entries predate the appid field; Steam derives one.
        legacy_exe = f'"{game / "Game-Win64-Shipping.exe"}"'
        legacy_id = str((zlib.crc32((legacy_exe + "Legacy Game").encode()) & 0xFFFFFFFF)
                        | 0x80000000)
        (config / "shortcuts.vdf").write_bytes(encode([
            {"AppName": "Legacy Game", "Exe": legacy_exe, "StartDir": f'"{game}"'},
        ]))
        check("an entry with no stored appid is matched by the one Steam derives",
              (steam_mod.find_by_appid(home, legacy_id) or {}).get("path") == str(game))

        # Fails closed: a file that is not this format must not half-decode
        # into a folder this plugin then writes OptiScaler into.
        (config / "shortcuts.vdf").write_bytes(b"\x00shortcuts\x00\x09junk")
        check("an unreadable shortcuts file yields nothing rather than a guess",
              steam_mod.find_by_appid(home, unsigned) is None)
    finally:
        shutil.rmtree(root, ignore_errors=True)


def check_wiki_failure_reporting():
    """A list that will not download must not read as "your game is not on it".

    Both produced an empty result and the UI showed the same sentence for each,
    so a network fault presented as every game in the library being unknown to
    the wiki — with nothing anywhere saying otherwise and no way to retry.
    `status()` is the answer to which of the two it is.
    """
    import tempfile
    from optiscaler import wiki as wiki_mod

    print("\nWiki failure reporting")
    root = Path(tempfile.mkdtemp(prefix="optiscaler-wiki-"))
    real_get = wiki_mod._http_get
    try:
        client = wiki_mod.WikiClient(root / "cache")

        wiki_mod._http_get = lambda *a, **k: (_ for _ in ()).throw(
            urllib.error.URLError("Network is unreachable"))
        entries, meta = client.load_entries(True)
        check("an unreachable wiki yields no entries", entries == [])
        check("and says so in the words of what failed",
              "Network is unreachable" in (meta["error"] or ""), meta["error"])
        state = client.status()
        check("status reports the list as unavailable, not empty",
              not state["available"] and state["entry_count"] == 0)
        check("status carries the error the UI has to print",
              "Network is unreachable" in (state["error"] or ""))
        check("status names the address it could not reach",
              state["url"].endswith("Compatibility-List.md"), state["url"])

        # A list that does download is the other answer, and the difference is
        # the whole point.
        table = ("| Game | Compatibility | Inputs |\n|---|---|---|\n"
                 "| [Cyberpunk 2077](Cyberpunk-2077) | OK | DLSS |\n")
        wiki_mod._http_get = lambda *a, **k: table
        state = client.status(True)
        check("a list that downloads reports as available",
              state["available"] and state["entry_count"] == 1, state)
        check("and carries no error", state["error"] is None)

        # A fetch that succeeds but parses to nothing is a third case, and must
        # not be cached as if it were a real answer.
        wiki_mod._http_get = lambda *a, **k: "not a table at all"
        empty, meta = client.load_entries(True)
        check("a page that parses to nothing is reported, not cached",
              "zero rows" in (meta["error"] or ""), meta["error"])
        check("and the last good list is served instead of nothing",
              len(empty) == 1, len(empty))
    finally:
        wiki_mod._http_get = real_get
        shutil.rmtree(root, ignore_errors=True)


def check_wiki_cache():
    """Answers come from cache; the network is never in front of a question.

    A handheld is regularly asleep, offline, or on a network that resolves and
    does not route. Waiting for the wiki before answering meant every one of
    those cost a full timeout, and a cache older than a day was thrown away
    rather than used. Reading is stale-while-revalidate now: whatever is on
    disk is returned at once, and the refresh happens behind it.
    """
    import tempfile
    from optiscaler import wiki as wiki_mod

    print("\nWiki cache")
    root = Path(tempfile.mkdtemp(prefix="optiscaler-swr-"))
    real_get = wiki_mod._http_get
    calls = []

    def serve(table):
        def get(url, *a, **k):
            calls.append(url)
            return table
        return get

    one = ("| Game | Compatibility | Inputs |\n|---|---|---|\n"
           "| [Cyberpunk 2077](Cyberpunk-2077) | OK | DLSS |\n")
    two = one + "| [Black Myth: Wukong](Black-Myth-Wukong) | OK | DLSS |\n"

    try:
        seed = root / "seed.json"
        seed.write_text(json.dumps({
            "fetched_at": time.time(),
            "entries": [{"name": "Seeded Game", "key": "seededgame", "page": None,
                         "compatibility": "OK", "inputs": "DLSS", "optipatcher": False,
                         "notes": ""}],
        }))

        # A Deck that has never had a connection still has a list.
        wiki_mod._http_get = lambda *a, **k: (_ for _ in ()).throw(
            urllib.error.URLError("Network is unreachable"))
        offline = wiki_mod.WikiClient(root / "a", seed)
        entries, meta = offline.load_entries()
        check("an offline Deck falls back to the bundled list",
              len(entries) == 1 and meta["source"] == "bundled", meta["source"])
        check("and reports the list as available, not as a missing game",
              offline.status()["available"])

        # With no seed and no network there is genuinely nothing.
        bare = wiki_mod.WikiClient(root / "b")
        check("no cache and no network is still an empty list, reported as such",
              bare.load_entries()[0] == [] and not bare.status()["available"])

        # A cached list answers without touching the network at all.
        wiki_mod._http_get = serve(one)
        client = wiki_mod.WikiClient(root / "c", seed)
        client.revalidate()
        calls.clear()
        entries, meta = client.load_entries()
        check("a cached list is served with no request at all",
              len(entries) == 1 and calls == [], calls)
        check("and says which list it came from", meta["source"] == "cache")

        # Even when it is older than the TTL: stale is a reason to refresh
        # behind the answer, never a reason to wait for one.
        payload = json.loads(client.list_cache.read_text())
        payload["fetched_at"] = time.time() - (COMPAT_TTL := 60 * 60 * 24) - 60
        client.list_cache.write_text(json.dumps(payload))
        calls.clear()
        entries, meta = client.load_entries()
        check("a stale list is still served without waiting",
              len(entries) == 1 and calls == [], calls)
        check("and is flagged stale so a refresh gets started",
              meta["stale"] and client.is_stale())

        # The fingerprint is what the UI watches to know something arrived.
        before = client.revision()
        wiki_mod._http_get = serve(one)
        same = client.revalidate()
        check("a refresh that brings back the same list changes nothing",
              same["ok"] and not same["changed"] and client.revision() == before)
        wiki_mod._http_get = serve(two)
        changed = client.revalidate()
        check("a refresh that brings something new says so",
              changed["ok"] and changed["changed"] and changed["count"] == 2)
        check("and the fingerprint moves with it", client.revision() != before)

        # The one rule that keeps this from ever making things worse.
        good = client.revision()
        wiki_mod._http_get = lambda *a, **k: (_ for _ in ()).throw(
            urllib.error.URLError("Network is unreachable"))
        failed = client.revalidate()
        check("a failed refresh leaves the working cache alone",
              not failed["ok"] and client.revision() == good and
              len(client.load_entries()[0]) == 2)
        check("but the failure is remembered for the UI to show",
              "unreachable" in (client.last_error or ""), client.last_error)
        wiki_mod._http_get = serve(two)
        client.revalidate()
        check("and a later success clears it", client.last_error is None)

        # Detail pages follow the same rule: a stale one used to mean two HTTP
        # attempts in front of the answer, the second only after the first
        # timed out.
        wiki_mod._http_get = serve("== Cyberpunk\n|**Filename**\n|`dxgi.dll`\n")
        client.fetch_page("Cyberpunk-2077")
        os.utime(client._page_file("Cyberpunk-2077"),
                 (time.time() - COMPAT_TTL - 60,) * 2)
        calls.clear()
        page = client.load_page("Cyberpunk-2077")
        check("a stale detail page is served from disk, not waited for",
              page is not None and calls == [], calls)
        check("and is reported stale so it can be refreshed behind the answer",
              client.page_is_stale("Cyberpunk-2077"))

        # The hole the stale rule left: a page never downloaded at all was
        # still fetched in front of the answer, two URLs deep with the second
        # attempt only starting once the first had timed out. On a Deck with a
        # bad route to the wiki that is a lookup that never returns, and the
        # setup tab sat on "Checking the OptiScaler wiki…" for ever — for
        # exactly the games whose page had not happened to be cached already.
        calls.clear()
        missing = client.load_page("Never-Seen", allow_fetch=False)
        check("a page never downloaded is not fetched in front of the answer",
              missing is None and calls == [], calls)
        check("but it counts as stale, so it is fetched behind one",
              client.page_is_stale("Never-Seen"))

        # And the arrival has to be visible to the same watch that notices a
        # changed list, or the better answer never reaches the screen.
        before_page = client.revision()
        wiki_mod._http_get = serve("== Never seen\n|**Filename**\n|`winmm.dll`\n")
        client.fetch_page("Never-Seen")
        check("a page arriving moves the revision the UI watches",
              client.revision() != before_page,
              f"{before_page} -> {client.revision()}")
        after_page = client.revision()
        client.fetch_page("Never-Seen")
        check("re-fetching the same page moves nothing",
              client.revision() == after_page)

        # A page the wiki will not serve must not be asked for on every
        # question. Each attempt is two URLs deep, so re-attempting kept a
        # refresh permanently in flight — and the UI reads "a refresh is
        # running" as "the answer may still change", so it never stopped
        # waiting for one that was never going to arrive.
        wiki_mod._http_get = lambda *a, **k: (_ for _ in ()).throw(
            urllib.error.URLError("Network is unreachable"))
        check("a page that has never been seen is worth one attempt",
              client.page_needs_fetch("Refused-Page"))
        check("which is made", client.fetch_page("Refused-Page") is None)
        check("and not repeated on the next question",
              not client.page_needs_fetch("Refused-Page"))
        check("a page already cached is not asked for at all",
              not client.page_needs_fetch("Never-Seen"))
        check("nor is a game with no wiki page", not client.page_needs_fetch(None))
        # Coming back onto a network has to be noticed eventually.
        client._page_failed_at["Refused-Page"] = time.time() - wiki_mod.PAGE_RETRY_AFTER - 1
        check("but the cooldown does expire", client.page_needs_fetch("Refused-Page"))
    finally:
        wiki_mod._http_get = real_get
        shutil.rmtree(root, ignore_errors=True)


def check_wiki_transport():
    """The fetch has to survive the ways one Deck's network differs.

    A router that advertises IPv6 it cannot route is the classic case: the
    address resolves, nothing connects, and urllib has no Happy Eyeballs to
    fall back the way a browser would — so it sits on the first address until
    the timeout, every time, and the wiki never loads on that network while
    everything else works.
    """
    import socket as socket_mod
    from optiscaler import wiki as wiki_mod

    print("\nWiki transport")
    real_open = wiki_mod._open
    attempts = []

    def stalls_once(request, timeout, context, binary=False):
        attempts.append(socket_mod.getaddrinfo)
        if len(attempts) == 1:
            raise urllib.error.URLError(TimeoutError("timed out"))
        return "| Game | Compatibility |\n|---|---|\n| [X](X) | OK |\n"

    try:
        wiki_mod._open = stalls_once
        body = wiki_mod._http_get("https://example.invalid/x")
        check("a stalled connection is retried rather than given up on",
              body.startswith("| Game"), len(attempts))
        check("and the retry is the one that forces IPv4",
              attempts[1] is not attempts[0])
        check("the resolver is put back afterwards",
              socket_mod.getaddrinfo is attempts[0])

        # A server that answered is not retried: asking again says the same.
        attempts.clear()

        def refuses(request, timeout, context, binary=False):
            attempts.append(1)
            raise urllib.error.HTTPError("u", 404, "Not Found", {}, None)

        wiki_mod._open = refuses
        try:
            wiki_mod._http_get("https://example.invalid/x")
            check("an HTTP error is not retried", False, "no error raised")
        except urllib.error.HTTPError:
            check("an HTTP error is not retried", len(attempts) == 1, len(attempts))
    finally:
        wiki_mod._open = real_open

    kinds = [kind for kind, _ in wiki_mod._candidate_contexts()]
    check("an unverified context is always the last resort",
          kinds and kinds[-1] == "unverified", kinds)


def check_wiki_tls():
    """TLS failures must fall through to the next CA source, not abort.

    urlopen wraps an SSLError in a URLError, so an `except ssl.SSLError` around
    it never fires -- the fallback contexts were unreachable and every lookup
    reported the game as absent from the compatibility list. No network needed
    to catch that: it is entirely about which exception is recognised.
    """
    import ssl
    import urllib.error
    from optiscaler import wiki

    print("\nWiki TLS")
    verify_failed = ssl.SSLCertVerificationError(
        "certificate verify failed: unable to get local issuer certificate")
    check("a bare SSLError counts as a tls failure", wiki._is_tls_error(verify_failed))
    check("the URLError urlopen actually raises counts too",
          wiki._is_tls_error(urllib.error.URLError(verify_failed)))
    check("an ordinary network error does not",
          not wiki._is_tls_error(urllib.error.URLError(OSError("unreachable"))))
    check("a timeout does not", not wiki._is_tls_error(TimeoutError()))

    kinds = [kind for kind, _ in wiki._candidate_contexts()]
    check("more than one CA source is tried", len(kinds) > 1, kinds)
    check("an unverified attempt is the last resort, never the first",
          kinds[-1] == "unverified" and kinds[0] != "unverified", kinds)


def check_optipatcher():
    """OptiPatcher ships alongside and installs into the same plugin folder."""
    import tempfile
    from optiscaler import constants

    print("\nOptiPatcher")
    # Downloaded like OptiScaler, so the package carries no copy to go stale.
    check("optipatcher is not bundled", not (ROOT / "bin" / constants.OPTIPATCHER_NAME).exists())

    root = Path(tempfile.mkdtemp(prefix="optiscaler-patcher-"))
    try:
        target = root / "game"
        target.mkdir()
        source = root / "fake.asi"
        source.write_bytes(b"MZ fake")
        result = installer.install_plugin_asi(str(target), source, constants.OPTIPATCHER_NAME)
        landed = target / constants.PLUGIN_SUBDIR / constants.OPTIPATCHER_NAME
        # v10 looks for plugins under OptiScaler/plugins (Plugins.Path defaults
        # to <OptiDllPath>/plugins).
        check("optipatcher lands in OptiScaler's plugins folder",
              result["ok"] and landed.is_file()
              and landed.parent.as_posix().endswith("OptiScaler/plugins"))
        check("every upscaler's preset switches asi loading on for it",
              all(preset.get("Plugins", {}).get("LoadAsiPlugins") == "true"
                  for preset in constants.UPSCALER_PRESETS.values()))
    finally:
        shutil.rmtree(root, ignore_errors=True)


def check_optipatcher_channel():
    """The rolling OptiPatcher: downloaded when first needed, verified, kept current."""
    print("\nOptiPatcher rolling channel")
    from optiscaler import optipatcher, wiki as wiki_mod

    base = "https://github.com/optiscaler/OptiPatcher/releases/download/rolling/"

    def release(sha, url=base + "OptiPatcher.asi", name="OptiPatcher.asi"):
        return {"tag_name": "rolling", "assets": [
            {"name": name, "digest": f"sha256:{sha}", "browser_download_url": url,
             "size": 1, "updated_at": "2099-01-02T03:04:05Z"}]}

    check("the rolling asset is picked with its digest and date",
          (optipatcher.pick_asset(release("ab" * 32)) or {}).get("sha256") == "ab" * 32)
    check("one served from anywhere else is not",
          optipatcher.pick_asset(release("ab" * 32, url="https://evil/OptiPatcher.asi")) is None)
    check("nor one without a digest",
          optipatcher.pick_asset({"assets": [{"name": "OptiPatcher.asi",
                                              "browser_download_url": base + "x"}]}) is None)
    check("its label is the build's date", optipatcher.label("2099-01-02T03:04:05Z")
          == "rolling (2099-01-02)")

    root = Path(tempfile.mkdtemp(prefix="optiscaler-patcher-channel-"))
    real_json, real_download = wiki_mod.download_json, wiki_mod.download
    try:
        channel = optipatcher.OptiPatcherChannel(root / "cache")
        build = b"MZ rolling build"
        served = {"sha": hashlib.sha256(build).hexdigest(), "body": build, "fail": False}
        verified, downloads = [], []

        def fake_json(url, timeout=20, verified_only=False):
            verified.append(verified_only)
            if served["fail"]:
                raise urllib.error.URLError("offline")
            return release(served["sha"])

        def fake_download(url, dest, timeout=90):
            downloads.append(url)
            Path(dest).write_bytes(served["body"])
            return dest

        wiki_mod.download_json, wiki_mod.download = fake_json, fake_download

        served["fail"] = True
        try:
            channel.ensure()
            check("offline with nothing downloaded is an error, not a silent skip", False)
        except RuntimeError as exc:
            check("offline with nothing downloaded is an error, not a silent skip",
                  channel.current() is None and "인터넷" in str(exc), str(exc))
        served["fail"] = False
        verified.clear()
        got = channel.ensure()
        check("the first ensure downloads the newest rolling build",
              got and Path(got["path"]).read_bytes() == build
              and got["label"] == "rolling (2099-01-02)", got)
        check("and the release was read over verified TLS", verified == [True], verified)
        channel.ensure()
        check("a fresh answer is not asked again", len(verified) == 1, verified)
        channel.ensure(force=True)
        check("an unchanged build is not downloaded twice", len(downloads) == 1, downloads)

        served.update(sha=hashlib.sha256(b"MZ next").hexdigest(), body=b"tampered")
        got = channel.ensure(force=True)
        check("a download that does not match its digest is refused, the last one kept",
              Path(got["path"]).read_bytes() == build
              and channel.last_error and "checksum" in channel.last_error, channel.last_error)

        served["fail"] = True
        got = channel.ensure(force=True)
        check("offline, the last download is used",
              got and Path(got["path"]).read_bytes() == build and channel.status()["error"],
              channel.status())

        (root / "cache" / "OptiPatcher.asi").write_bytes(b"altered on disk")
        check("a download altered on disk is not used", channel.current() is None)
    finally:
        wiki_mod.download_json, wiki_mod.download = real_json, real_download
        shutil.rmtree(root, ignore_errors=True)


def check_optipatcher_offline_install():
    """No OptiPatcher download: the install goes on, says so, and keeps what was there."""
    print("\nOptiPatcher with nothing to download")
    root = Path(tempfile.mkdtemp(prefix="optiscaler-patcher-offline-"))
    try:
        payload = build_payload(root)
        service = OptiScalerService(ROOT, root / "settings", root / "runtime", root,
                                    logging.getLogger("selftest"))
        service.payload.ensure = lambda force=False, logger=None, tag=None: payload

        def offline(force=False, logger=None):
            raise RuntimeError("OptiPatcher를 다운로드할 수 없습니다. 첫 설치에는 인터넷 연결이 필요합니다.")

        service.optipatcher.ensure = offline
        fresh = root / "Fresh"
        fresh.mkdir()
        (fresh / "Game.exe").write_bytes(b"MZ")
        result = asyncio.run(service.install(str(fresh), "dxgi.dll", False, True))
        check("OptiScaler still goes in, and the missing OptiPatcher is reported",
              result["ok"] and installer.detect(str(fresh))["installed"]
              and not result["optipatcher"]["installed"]
              and "인터넷" in (result["optipatcher"]["error"] or ""), result.get("optipatcher"))

        kept = root / "Kept"
        kept.mkdir()
        (kept / "Game.exe").write_bytes(b"MZ")
        old = root / "old.asi"
        old.write_bytes(b"MZ the copy this game has")
        installer.install(str(kept), str(payload), "dxgi.dll", False, None, old, None, None,
                          {"tag": "nightly-1", "version": "10"})
        result = asyncio.run(service.install(str(kept), "dxgi.dll", True, True))
        landed = kept / "OptiScaler" / "plugins" / "OptiPatcher.asi"
        check("a reinstall keeps the OptiPatcher the game already has",
              result["ok"] and result["optipatcher"]["installed"]
              and landed.read_bytes() == b"MZ the copy this game has", result.get("optipatcher"))
    finally:
        shutil.rmtree(root, ignore_errors=True)


def check_pd_upload():
    """PDPerfPlugin.dll from a phone: a one-file page on the LAN, and the picker's file.

    Driven over real HTTP on the loopback address: the page answers only on
    its token, refuses what is not the plugin, unpacks an archive to find it,
    and closes once it has the file.
    """
    import urllib.error
    import urllib.request
    from optiscaler.upload import UploadSession

    print("\nPDPerfPlugin from a phone or a picked file")
    root = Path(tempfile.mkdtemp(prefix="optiscaler-upload-"))
    try:
        service = OptiScalerService(ROOT, root / "settings", root / "runtime", root / "home",
                                    logging.getLogger("selftest"))
        session = UploadSession(service.take_pd_plugin, "t", "h", address="127.0.0.1", ttl=60)
        base = session.url

        def post(url, body, name):
            request = urllib.request.Request(url, data=body, method="POST",
                                             headers={"X-File-Name": name})
            try:
                with urllib.request.urlopen(request, timeout=10) as answer:
                    return answer.status, json.loads(answer.read())
            except urllib.error.HTTPError as exc:
                return exc.code, json.loads(exc.read() or b"{}")

        with urllib.request.urlopen(base, timeout=10) as page:
            check("the page opens on its token", page.status == 200
                  and "Steam Deck" in page.read().decode("utf-8"))
        try:
            urllib.request.urlopen(base.rsplit("/", 1)[0] + "/guess", timeout=10)
            check("and on nothing else", False)
        except urllib.error.HTTPError as exc:
            check("and on nothing else", exc.code == 404, exc.code)

        code, answer = post(base + "/upload", b"MZ another dll", "other.dll")
        check("a DLL that is not PDPerfPlugin.dll is refused, the page stays open",
              code == 400 and not answer["ok"] and session.active, answer)
        code, answer = post(base + "/upload", b"hello", "notes.txt")
        check("so is a file that is neither the DLL nor an archive", code == 400, answer)

        archive = root / "UpscalerBasePlugin-1.1.2.zip"
        with zipfile.ZipFile(archive, "w") as zf:
            zf.writestr("UpscalerBasePlugin/PDPerfPlugin.dll", b"MZ from the archive")
        code, answer = post(base + "/upload", archive.read_bytes(), archive.name)
        check("the zip Nexus serves is unpacked to find the DLL, and kept",
              code == 200 and answer["ok"]
              and service.pd_plugin_kept().read_bytes() == b"MZ from the archive", answer)
        check("and it says whether that is the 1.1.2 build", answer["verified"] is False
              and "다른 버전" in answer["message"], answer)
        for _ in range(50):
            if not session.active:
                break
            time.sleep(0.05)
        check("the page closes once it has the file", not session.active)

        picked = root / "usb" / "PDPerfPlugin.dll"
        picked.parent.mkdir()
        picked.write_bytes(b"MZ picked on the deck")
        result = asyncio.run(service.import_pd_plugin(str(picked)))
        check("a file picked on the Deck itself is taken the same way",
              result["ok"] and result["status"]["present"]
              and service.pd_plugin_kept().read_bytes() == b"MZ picked on the deck", result)
        refused = asyncio.run(service.import_pd_plugin(str(archive.with_suffix(".txt"))))
        check("and a missing or wrong file is an error, not a crash", not refused["ok"], refused)
    finally:
        shutil.rmtree(root, ignore_errors=True)


def check_auto_plan():
    """Reading a wiki entry back out as instructions.

    The compatibility list is community prose, not a specification, so the whole
    value of automatic set-up rests on two properties: what it takes is real,
    and what it cannot take is reported rather than dropped. Both are checked
    here against the shapes real entries actually have — every fixture below is
    lifted from a live entry on the list.
    """
    from optiscaler import autoplan

    print("\nAutomatic set-up plan")

    def plan_for(**recommendation):
        base = {"matched": True, "game": "Test Game", "filename": "dxgi.dll",
                "filename_source": "wiki entry", "optipatcher": False,
                "compatibility": "✅", "notes": None, "detail": {}}
        base.update(recommendation)
        return autoplan.build(base)

    check("no match means no plan", not autoplan.build({"matched": False})["available"])
    check("no recommendation at all is survivable", not autoplan.build(None)["available"])

    # -- ini settings mined out of prose ---------------------------------
    plan = plan_for(detail={"Settings": "`Dxgi=false` since spoofing isn't required to see "
                                        "DLSS inputs _(autoapplied by Opti)_"})
    check("a setting the wiki states is taken",
          [(s["section"], s["key"], s["value"]) for s in plan["settings"]]
          == [("Spoofing", "Dxgi", "false")], plan["settings"])
    check("each setting says which part of the entry asked for it",
          plan["settings"][0]["source"] == "wiki entry, “Settings”")

    plan = plan_for(detail={"Settings": "`DontCreateD3D12DeviceForLuma=true`"})
    check("a key that is not an OptiScaler setting is refused",
          not plan["settings"] and plan["unresolved"], plan)
    check("and is reported rather than dropped",
          "DontCreateD3D12DeviceForLuma" in plan["unresolved"][0]["text"])

    # A dozen key names exist in several sections. Guessing one would write a
    # real setting the wiki never asked for, in the wrong place.
    plan = plan_for(detail={"Settings": "`Enabled = true`"})
    check("a key name several sections share is not guessed at",
          not plan["settings"] and "ambiguous" in plan["unresolved"][0]["text"],
          plan["unresolved"])
    plan = plan_for(detail={"Settings": "`[OutputScaling]` `Enabled = true` `Multiplier = 2.0`"})
    check("a stated section resolves the same key",
          ("OutputScaling", "Enabled", "true") in
          [(s["section"], s["key"], s["value"]) for s in plan["settings"]], plan["settings"])
    # A real entry, quoting the pre-0.9 layout: [OptiFG] had an Enabled key and
    # no longer does. Resolving it to some other section's Enabled would write a
    # setting nobody asked for, so it has to fail and say so.
    plan = plan_for(detail={"Settings": "[FrameGen] `FGType = optifg` [OptiFG] `Enabled = true`"})
    check("a section that no longer has that key is not quietly re-homed",
          not any(item["key"] == "Enabled" for item in plan["settings"]), plan["settings"])

    plan = plan_for(detail={"Settings": "`Dx12Upscaler = fsr31` had the highest performance"})
    check("the upscaler is left to the user even when an entry names one",
          not plan["settings"], plan["settings"])
    plan = plan_for(detail={"Settings": "`Sharpness = 9.5`"})
    check("a value outside the option's range is refused",
          not plan["settings"] and plan["unresolved"], plan)
    plan = plan_for(detail={"Settings": "`ShortcutKey=0x24`"})
    check("a hex key code is a valid keycode",
          [(s["key"], s["value"]) for s in plan["settings"]] == [("ShortcutKey", "0x24")],
          plan["settings"])

    # -- launch options --------------------------------------------------
    plan = plan_for(notes="Use -dx12 launch option.")
    check("a launch flag the wiki asks for is picked up", plan["launch_flags"] == ["-dx12"])
    check("and lands after %command%, where the game's own arguments go",
          plan["launch_options"] == 'WINEDLLOVERRIDES="dxgi=n,b" %command% -dx12',
          plan["launch_options"])
    # This one read as an instruction for every Luma Unreal Engine entry.
    plan = plan_for(detail={"Known Issues": "If seeing the non-DX11 device error, set ..."})
    check("a flag spelled inside a word is not an instruction",
          plan["launch_flags"] == [], plan["launch_flags"])
    plan = plan_for(notes="Unity game, create a shortcut with -force-d3d12 launch parameter")
    check("Unity's -force-d3d12 is picked up as itself, not as -d3d12",
          plan["launch_flags"] == ["-force-d3d12"], plan["launch_flags"])
    plan = plan_for(notes="FSR3 inputs don't work. DX12 can be forced using -force-d3d12.")
    check("a negative in the sentence before does not cancel a flag",
          plan["launch_flags"] == ["-force-d3d12"], plan["launch_flags"])
    plan = plan_for(notes="Don't use -dx12, the DX11 renderer is the working one.")
    check("a flag the entry warns against is not applied",
          plan["launch_flags"] == [], plan["launch_flags"])
    plan = plan_for(filename="OptiScaler.asi")
    check("an .asi build needs no dll override",
          plan["launch_options"] == "%command%", plan["launch_options"])

    # -- frame generation ------------------------------------------------
    plan = plan_for(detail={"FG Inputs": "DLSSG via Streamline"})
    check("the recommended FG input becomes an ini value",
          (plan["framegen"]["input"], plan["framegen"]["output"]) == ("dlssg", "fsrfg"),
          plan["framegen"])
    check("and is labelled the way OptiScaler's overlay labels it",
          plan["framegen"]["input_label"] == "DLSSG via Streamline")
    # "Nukem's DLSSG" contains "DLSSG", so order of matching decides this one.
    plan = plan_for(detail={"FG Inputs": "Nukem's DLSSG"})
    check("Nukem's is not mistaken for Streamline DLSSG",
          plan["framegen"]["input"] == "nukems", plan["framegen"])
    plan = plan_for(detail={"FG-Settings": "OptiFG (Upscaler) -> XeFG"})
    check("an arrow states the output as well as the input",
          (plan["framegen"]["input"], plan["framegen"]["output"]) == ("upscaler", "xefg"),
          plan["framegen"])
    plan = plan_for(detail={"FG Inputs": "None"})
    check("an entry reporting no working FG says so rather than picking one",
          plan["framegen"]["input"] == "nofg", plan["framegen"])
    check("and that produces no FG changes to apply",
          autoplan.framegen_changes(plan) == [], autoplan.framegen_changes(plan))
    plan = plan_for(detail={"Notes": "FSR3.1 inputs cannot be hooked."})
    check("a passing mention of FG is not a recommendation",
          plan["framegen"] is None, plan["framegen"])

    # -- the whole thing -------------------------------------------------
    plan = plan_for(
        game="007 First Light", filename="dxgi.dll", optipatcher=True,
        notes="Use -dx12 launch option.",
        detail={
            "FG Inputs": "DLSSG via Streamline",
            "Known Issues": "`Dxgi=false` to disable spoofing. "
                            "`RestoreComputeSignature=true` for DLSS inputs.",
        })
    check("a complete entry produces a complete plan",
          plan["available"] and plan["optipatcher"] and plan["source"] == "wiki entry"
          and plan["launch_flags"] == ["-dx12"] and plan["framegen"]["input"] == "dlssg"
          and len(plan["settings"]) == 2, plan)
    changes = autoplan.setting_changes(plan) + autoplan.framegen_changes(plan)
    check("every planned change is a writable ini change",
          all(set(c) == {"section", "key", "value"} for c in changes) and len(changes) == 4,
          changes)
    check("known issues are surfaced as a warning to read them",
          any("알려진 문제" in w for w in plan["warnings"]), plan["warnings"])


def check_reframework():
    """The games that cannot host OptiScaler without REFramework.

    Nine entries on the compatibility list say, in prose, that OptiScaler does
    nothing in this game unless REFramework is already in the folder — and for
    three releases the plugin read straight past it. Those games got an install
    that reported success, set the launch options, and changed nothing on
    screen, which is the worst failure available because there is no error
    anywhere to go looking for.

    Everything below is driven by the text real entries actually carry.
    """
    from optiscaler import autoplan, reframework
    from optiscaler.constants import (
        REFRAMEWORK_AUTO_INSTALL, REFRAMEWORK_DLL, REFRAMEWORK_PD_ASSETS,
    )

    print("\nREFramework")
    # Automatic installation is switched off (see constants), and everything
    # else about the feature is deliberately kept: which games need it, which
    # of the two builds, the launch-options override, the status read and the
    # removal path. So the checks below assert against the flag rather than
    # against a constant — turning it back on has to make the fetch work again,
    # and turning it off must not stop the requirement being *read*, which is
    # the half that keeps these games from silently doing nothing.

    def plan_for(**recommendation):
        base = {"matched": True, "game": "Test Game", "filename": "dxgi.dll",
                "filename_source": "wiki entry", "optipatcher": False,
                "compatibility": "✅", "notes": None, "detail": {}}
        base.update(recommendation)
        return autoplan.build(base)

    # -- reading the requirement out of the entry ------------------------
    plan = plan_for(game="Monster Hunter Wilds",
                    notes="Requires REFramework, set Dxgi=false in the OptiScaler.ini "
                          "to avoid crashes.")
    ref = plan["reframework"]
    check("a list row stating the requirement is read as one", bool(ref), plan["reframework"])
    check("praydog's unified nightly is the default build",
          ref["variant"] == "nightly" and ref["asset"] == "REFramework.zip", ref)
    check("and whether it is fetched from here follows the flag, nothing else",
          ref["automatic"] == REFRAMEWORK_AUTO_INSTALL, ref)
    check("with a reason to show the user whenever it is not",
          ref["automatic"] or bool(ref["reason"]), ref)
    check("the entry that said so is cited", "notes" in ref["source"].lower(), ref["source"])

    # The pd entries name a different mod that happens to share a filename.
    plan = plan_for(game="Resident Evil 2 (2019)",
                    notes="Requires REFramework (pd-upscaler branch) + PDUpscaler plugin "
                          "+ OptiScaler, check Wiki")
    ref = plan["reframework"]
    check("an entry naming the pd-upscaler branch gets the pd build",
          ref["variant"] == "pd-upscaler" and ref["asset"] == "RE2.zip", ref)
    check("and is told it needs UpscalerBasePlugin as well",
          ref["plugin"] == "PDPerfPlugin.dll" and ref["plugin_url"], ref)
    check("which is reported as the user's job, since Nexus needs a login",
          any("Nexus" in w for w in plan["warnings"]), plan["warnings"])

    plan = plan_for(game="Devil May Cry 5",
                    notes="Requires REFramework PDUpscaler branch + PDPerfPlugin mod and "
                          "carefully reading the compatibility entry")
    check("the branch spelled without a hyphen is the same branch",
          plan["reframework"]["asset"] == "DMC5.zip", plan["reframework"])

    # The detail page states it a different way than the list row does.
    plan = plan_for(game="Resident Evil 8 Village", detail={
        "Notes": "To get OptiScaler to work with REFramework + UpscalerBasePlugin: "
                 "Download REFramework's pd-upscaler branch."})
    check("the wiki page's phrasing is read too",
          plan["reframework"]["variant"] == "pd-upscaler", plan["reframework"])

    # -- what must not be read as a requirement --------------------------
    # These sentences are on the same pages, about the same mod, and none of
    # them is an instruction to install anything.
    for text in ("XeFG seems to disable the REF overlay",
                 "REF + XeFG currently cause heavy intermittent stuttering",
                 "Might also have to disable Vignette through REF (under Camera options)",
                 "OptiScaler depends on REF bypassing the anti-modding DRM"):
        check("a passing mention of REF is not a requirement",
              plan_for(detail={"Known Issues": text})["reframework"] is None, text)
    check("and an entry that no longer needs it is not given it anyway",
          plan_for(notes="This no longer requires REFramework as of 0.9.")["reframework"]
          is None)
    check("a game the entry says nothing about gets nothing",
          plan_for(notes="Use -dx12 launch option.")["reframework"] is None)

    # -- Proton's half, which the wiki never mentions ---------------------
    # The wiki is written for Windows, where the game folder wins. On Proton it
    # does not: REFramework's dll needs an override of its own or the mod sits
    # in the folder doing nothing, and following the entry to the letter is
    # exactly how that happens.
    plan = plan_for(game="PRAGMATA", notes="Requires REFramework to work.")
    check("REFramework gets a WINEDLLOVERRIDES entry of its own",
          plan["launch_options"] == 'WINEDLLOVERRIDES="dxgi=n,b;dinput8=n,b" %command%',
          plan["launch_options"])
    plan = plan_for(game="PRAGMATA", notes="Requires REFramework to work. Use -dx12.")
    check("and the game's own arguments still land after %command%",
          plan["launch_options"].endswith("%command% -dx12"), plan["launch_options"])
    check("a game with no REFramework requirement is unchanged",
          plan_for()["launch_options"] == 'WINEDLLOVERRIDES="dxgi=n,b" %command%')
    # -- a game with no known build --------------------------------------
    plan = plan_for(game="Some Unlisted RE Engine Game",
                    notes="Requires REFramework (pd-upscaler branch) to work.")
    ref = plan["reframework"]
    check("a pd game with no known asset refuses rather than guessing one",
          ref["required"] and not ref["automatic"] and ref["asset"] is None, ref)
    check("and says where to get it by hand", ref["page"] and ref["reason"], ref)
    check("which is raised as a warning, not buried",
          any("REFramework" in w for w in plan["warnings"]), plan["warnings"])

    # -- the archive is unpacked by name, never on trust -------------------
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        archive = root / "REFramework.zip"
        with zipfile.ZipFile(archive, "w") as zf:
            zf.writestr("dinput8.dll", b"REF" * 100)
            zf.writestr("reframework_revision.txt", "abc123")
            zf.writestr("readme.txt", "not ours")
            zf.writestr("../../evil.dll", b"nope")
            zf.writestr("nested/dinput8.dll", b"a second one")
        taken = reframework._extract(archive, root / "out")
        check("the files REFramework ships are taken",
              sorted(taken) == ["dinput8.dll", "reframework_revision.txt"], taken)
        check("and nothing else in the archive is",
              not (root / "out" / "readme.txt").exists()
              and sorted(p.name for p in (root / "out").iterdir())
              == ["dinput8.dll", "reframework_revision.txt"],
              sorted(p.name for p in (root / "out").iterdir()))
        check("a path that climbs out of the folder lands nowhere",
              not (root.parent / "evil.dll").exists() and not (root / "evil.dll").exists())
        check("the first copy of a name wins, so a nested one cannot overwrite it",
              (root / "out" / "dinput8.dll").read_bytes() == b"REF" * 100)

        empty = root / "empty.zip"
        with zipfile.ZipFile(empty, "w") as zf:
            zf.writestr("something_else.dll", b"x")
        try:
            reframework._extract(empty, root / "out2")
            check("an archive without the dll is refused", False, "no error raised")
        except ValueError as exc:
            check("an archive without the dll is refused", REFRAMEWORK_DLL in str(exc), exc)

    # -- installing it, and taking it back out ---------------------------
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        game = root / "game"
        game.mkdir()
        payload = root / "payload"
        payload.mkdir()
        (payload / "OptiScaler.dll").write_bytes(b"OptiScaler" + b"\0" * (5 << 20))
        (payload / INI_NAME).write_text("[Upscalers]\nDx12Upscaler=auto\n")
        source = root / "ref"
        source.mkdir()
        (source / REFRAMEWORK_DLL).write_bytes(b"the REFramework build")
        # The game already ships a dinput8 of its own, which is the case the
        # whole backup contract exists for.
        (game / REFRAMEWORK_DLL).write_bytes(b"the game's own dinput8")

        result = installer.install(str(game), str(payload), "dxgi.dll", False, None,
                                   None, [source / REFRAMEWORK_DLL])
        check("REFramework lands next to the executable",
              result["reframework"]["installed"]
              and (game / REFRAMEWORK_DLL).read_bytes() == b"the REFramework build", result)
        check("and the game's own file is set aside rather than lost",
              REFRAMEWORK_DLL in result["backups"], result["backups"])
        found = installer.detect(str(game))
        check("detect reports it, and that we are the ones who installed it",
              found["reframework"]["installed"] and found["reframework"]["managed"], found)

        installer.uninstall(str(game))
        check("removing OptiScaler removes REFramework with it",
              (game / REFRAMEWORK_DLL).read_bytes() == b"the game's own dinput8",
              (game / REFRAMEWORK_DLL).read_bytes())

    # -- adding it to a game already set up -------------------------------
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        game = root / "game"
        game.mkdir()
        payload = root / "payload"
        payload.mkdir()
        (payload / "OptiScaler.dll").write_bytes(b"OptiScaler" + b"\0" * (5 << 20))
        (payload / INI_NAME).write_text("[Upscalers]\nDx12Upscaler=auto\n")
        installer.install(str(game), str(payload), "dxgi.dll", False)
        source = root / "ref"
        source.mkdir()
        (source / REFRAMEWORK_DLL).write_bytes(b"added later")

        added = installer.add_files(str(game), [source / REFRAMEWORK_DLL])
        check("REFramework can be added without reinstalling OptiScaler",
              added["ok"] and (game / REFRAMEWORK_DLL).is_file(), added)
        manifest = installer.read_manifest(game)
        check("and joins the manifest, so it is removed with everything else",
              REFRAMEWORK_DLL in manifest["files"] and manifest["reframework"], manifest)
        installer.uninstall(str(game))
        check("which it is", not (game / REFRAMEWORK_DLL).exists())

    # -- the curated asset table ------------------------------------------
    seed = json.loads((ROOT / "defaults" / "compat-list.json").read_text())
    keys = {entry["key"] for entry in seed["entries"]}
    unknown = sorted(k for k in REFRAMEWORK_PD_ASSETS if k not in keys)
    check("every curated asset key is a real compatibility-list entry",
          not unknown, unknown)

    # The point of the whole feature: the games on the real list that need it
    # are found, and no others are.
    found = {}
    for entry in seed["entries"]:
        recommendation = dict(entry, matched=True, game=entry["name"], detail={},
                              filename="dxgi.dll", filename_source="x")
        ref = autoplan.build(recommendation)["reframework"]
        if ref:
            found[entry["name"]] = ref["variant"]
    check("the whole bundled list yields exactly the entries that ask for it",
          sorted(found) == [
              "Devil May Cry 5", "Monster Hunter Wilds",
              "Onimusha: Way of the Sword", "PRAGMATA",
              "Resident Evil 2 (2019)", "Resident Evil 3 (2020)",
              "Resident Evil 4 (2023)", "Resident Evil 7 Biohazard",
              "Resident Evil 8 Village", "Resident Evil 9 Requiem",
          ], sorted(found))
    check("with the right build for each",
          [found[name] for name in sorted(found)] ==
          ["pd-upscaler", "nightly", "nightly", "nightly", "pd-upscaler",
           "pd-upscaler", "pd-upscaler", "pd-upscaler", "pd-upscaler",
           "nightly"], found)
    # The asset is what the checklist names when it sends somebody to fetch
    # the file, so it has to resolve whether or not the download is on.
    check("and every one of them resolves to a named build",
          all(autoplan.build(dict(e, matched=True, game=e["name"], detail={},
                                  filename="dxgi.dll", filename_source="x"))
              ["reframework"]["asset"]
              for e in seed["entries"] if e["name"] in found))


def check_prose_is_not_a_specification():
    """Two ways a wiki page says something it is not asking you to do.

    Both of these shipped, and both broke a real game on a real Deck.

    Monster Hunter Wilds stopped booting. Its page lays out three *mutually
    exclusive* install methods, and the miner read all of them: `LoadReshade=true`
    belongs to METHOD 3, where REF's dll has been renamed to `ReShade64.dll` so
    OptiScaler loads it. Applied on top of METHOD 1 — which is what this plugin
    installs — it tells OptiScaler to load a file that is not there while REF is
    already loaded through dinput8.

    Resident Evil 2 rendered nothing useful. "If applying Output Scaling is
    crashing the game, then ... set `Enabled=true` and the desired multiplier
    (e.g. `Multiplier=2.0`)" is remediation advice with an example number, and it
    was applied unconditionally — 2x output scaling, on a Steam Deck.
    """
    from optiscaler import autoplan

    print("\nProse that is not an instruction")

    def plan_for(**recommendation):
        base = {"matched": True, "game": "Test Game", "filename": "dxgi.dll",
                "filename_source": "wiki entry", "optipatcher": False,
                "compatibility": "✅", "notes": None, "detail": {}}
        base.update(recommendation)
        return autoplan.build(base)

    # -- alternative install methods -------------------------------------
    wilds = ("*Requires REFramework to work* * *Download* - REF Nightly --- "
             "*INSTALL METHOD 1* * Keep *REFramework's* default `dinput8.dll` "
             "* Either install *OptiScaler* as `dxgi.dll` --- "
             "*METHOD 3 - loading REF through OptiScaler* "
             "* Rename *REF's* `dinput8.dll` to `ReShade64.dll` "
             "* In `OptiScaler.ini`, set `LoadReshade=true`")
    plan = plan_for(detail={"Notes": wilds})
    check("a setting from an alternative install method is not applied",
          not any(item["key"] == "LoadReshade" for item in plan["settings"]),
          plan["settings"])
    check("but the method this plugin does perform is still read",
          plan["reframework"] and plan["reframework"]["variant"] == "nightly",
          plan["reframework"])
    check("“INSTALL METHOD 1” is not itself a boundary",
          autoplan._this_method_only("a INSTALL METHOD 1 b").strip().endswith("b"))
    check("but METHOD 2 is",
          "gone" not in autoplan._this_method_only("keep this --- METHOD 2 gone"))
    check("and so is an Alternate Method",
          "gone" not in autoplan._this_method_only("keep --- Alternate Method 1 gone"))

    # -- conditional and illustrative values ------------------------------
    re2 = ("If applying Output Scaling is crashing the game, then manually enable it in "
           "*OptiScaler.ini* * Find `[OutputScaling]` in the config, set `Enabled=true` "
           "and the desired multiplier (e.g. `Multiplier=2.0`)")
    plan = plan_for(detail={"Known Issues": re2})
    check("a setting offered as a fix for a problem you may not have is refused",
          not plan["settings"], plan["settings"])
    check("both halves of it, including the one after the “e.g.”",
          len(plan["unresolved"]) == 2, plan["unresolved"])
    check("and the user is told which word made it a maybe",
          all("conditionally" in item["text"] for item in plan["unresolved"]),
          plan["unresolved"])

    # A refusal is not free either: this one is an instruction that happens to
    # name its consequence, and refusing it would leave the crash it prevents.
    # "otherwise" and "instead" are excluded from the hedge words for this.
    plan = plan_for(notes="Requires disabling spoofing, otherwise it crashes - "
                          "set Dxgi=false in OptiScaler.ini.")
    check("“do X, otherwise it crashes” is an instruction, not a condition",
          [(i["key"], i["value"]) for i in plan["settings"]] == [("Dxgi", "false")],
          plan["settings"])
    plan = plan_for(notes="If crashing on certain screen openings, try setting "
                          "`OverlayMenu=false` in OptiScaler.ini")
    check("“if crashing, try setting X” is a condition, not an instruction",
          not plan["settings"] and plan["unresolved"], plan)

    # An unhedged statement in the same field is still taken.
    plan = plan_for(detail={"Settings": "`Dxgi=false`, `OverlayMenu=false` "
                                        "(required for OptiScaler menu to function)"})
    check("a plain statement of two settings is unaffected",
          len(plan["settings"]) == 2, plan["settings"])

    # -- the overlay key it moves ----------------------------------------
    plan = plan_for(detail={"Notes": "*OptiScaler*: set `ShortcutKey=0x24` (changes to "
                                     "home key) in `OptiScaler.ini`."})
    check("the shortcut the entry asks for is still applied",
          any(i["key"] == "ShortcutKey" for i in plan["settings"]), plan["settings"])
    check("and the plan says which key that is, in words",
          plan["hotkey"] and plan["hotkey"]["name"] == "Home", plan["hotkey"])
    check("a game whose entry moves nothing has no hotkey note",
          plan_for()["hotkey"] is None)
    check("a code with no name is reported rather than invented",
          autoplan.key_name("0x9f") is None and autoplan.key_name("0x2D") == "Insert")

    # -- the two games this came from, end to end -------------------------
    plan = plan_for(game="Monster Hunter Wilds",
                    notes="Requires REFramework, set Dxgi=false in the OptiScaler.ini "
                          "to avoid crashes.",
                    detail={"Notes": wilds})
    applied = {(i["key"], i["value"]) for i in plan["settings"]}
    # Plus OptiScaler's overlay off Insert, which REFramework's uses too: the
    # entry says to move REF's, and OptiScaler's is the one this plugin owns.
    check("Monster Hunter Wilds gets the one setting its entry actually asks for",
          applied == {("Dxgi", "false"), ("ShortcutKey", "0x24")}, applied)
    check("and its overlay is moved to Home, saying why",
          plan["hotkey"] and plan["hotkey"]["name"] == "Home"
          and plan["hotkey"]["source"].startswith("REFramework"), plan["hotkey"])

    plan = plan_for(game="Resident Evil 2 (2019)",
                    notes="Requires REFramework (pd-upscaler branch) + PDUpscaler plugin",
                    detail={"Settings": "`Dxgi=false`, `OverlayMenu=false` (required for "
                                        "OptiScaler menu to function correctly)",
                            "Known Issues": re2})
    applied = {(i["key"], i["value"]) for i in plan["settings"]}
    check("Resident Evil 2 gets its two, and no output scaling",
          applied == {("Dxgi", "false"), ("OverlayMenu", "false"), ("ShortcutKey", "0x24")},
          applied)
    moved = plan_for(game="Resident Evil 2 (2019)",
                     notes="Requires REFramework (pd-upscaler branch) + PDUpscaler plugin",
                     detail={"Notes": "OptiScaler: set `ShortcutKey=0x2E` in OptiScaler.ini"})
    check("a key the entry names itself is kept, not replaced by Home",
          [(i["key"], i["value"], i["source"]) for i in moved["settings"] if i["key"] == "ShortcutKey"]
          == [("ShortcutKey", "0x2E", "wiki entry, “Notes”")], moved["settings"])
    plain = plan_for(game="Cyberpunk 2077", notes="Works out of the box")
    check("a game without REFramework keeps Insert",
          not any(i["key"] == "ShortcutKey" for i in plain["settings"]), plain["settings"])


def check_parenthesised_pages():
    """A wiki page name with brackets in it has to survive being parsed.

    `[Resident Evil 2 (2019)](Resident-Evil-2-(2019))` is an ordinary row on the
    compatibility list, and a link target of `[^)]+` stops at the inner bracket:
    the page came out as "Resident-Evil-2-(2019", the wiki does not serve that,
    and the detail page for every parenthesised title silently never downloaded.
    Those are exactly the Resident Evil entries whose settings and REFramework
    instructions live on the page rather than in the notes column.
    """
    from optiscaler import wiki as wiki_mod

    print("\nParenthesised wiki pages")
    markdown = (
        "| Game | Compatibility | FG Inputs | OptiPatcher | Notes |\n"
        "|---|---|---|---|---|\n"
        "| [Resident Evil 2 (2019)](Resident-Evil-2-(2019)) | ✅ | DLSS |  | Requires REF |\n"
        "| [AI Limit](AI-Limit) | ✅ | DLSS |  |  |\n"
    )
    entries = {e["name"]: e for e in wiki_mod.parse_compat_list(markdown)}
    check("a page name carrying brackets is kept whole",
          entries["Resident Evil 2 (2019)"]["page"] == "Resident-Evil-2-(2019)",
          entries["Resident Evil 2 (2019)"]["page"])
    check("and an ordinary one is unaffected",
          entries["AI Limit"]["page"] == "AI-Limit", entries["AI Limit"]["page"])
    check("the game's own name keeps its brackets too",
          "Resident Evil 2 (2019)" in entries)

    seed = json.loads((ROOT / "defaults" / "compat-list.json").read_text())
    truncated = [e["name"] for e in seed["entries"]
                 if e["page"] and e["page"].count("(") != e["page"].count(")")]
    check("the bundled seed has no half-a-bracket page names left",
          not truncated, truncated)


def check_compat_list_shapes():
    """The compatibility list is hand-edited prose, and its shape moves.

    Two things went wrong on the same page, and neither is visible in a browser:

    A row saved without its leading pipe ended the table for the parser, which
    dropped every row after it — 297 of 695 games, each reported to the user as
    "no wiki entry matched". GitHub renders that line as prose and closes the
    table over the gap, so the page looks right and the plugin quietly forgets
    40% of the list.

    And the page holds three tables, not one: the main table has an OptiPatcher
    column, while "Upscaler mods support" and "Luma Unreal Engine" do not. Read
    by position, their notes column was taken for OptiPatcher support — every
    such game claimed the patcher — and their images column was served to the
    user, and to the plan builder, as the entry's notes.
    """
    from optiscaler import wiki as wiki_mod

    print("\nCompatibility list shapes")
    markdown = (
        "| Game | Compatibility | Upscaler <br>Inputs | OptiPatcher <br>Support"
        " | Notes | Images |\n"
        "| ---- | :---: | :---: | :---: | ---- | :---: |\n"
        "| [Alpha](Alpha) | \u2705 | DLSS | \u2728 | Needs -dx12 | [1](u) |\n"
        "[Bravo](Bravo) | \u2705 | DLSS |  | Saved without its first pipe | [1](u) |\n"
        "| [Charlie](Charlie) | \u2705 | XeSS |  | After the broken row | [1](u) |\n"
        "\n"
        "## Upscaler mods support\n"
        "\n"
        "| Game | Compatibility | Upscaler <br>Inputs | Notes  | Images |\n"
        "| ---- | :---: | :---: | ---- | :---: |\n"
        "| [Delta](Delta) | \u2705 | DLSS | Requires a mod | [1](u) |\n"
    )
    entries = {e["name"]: e for e in wiki_mod.parse_compat_list(markdown)}

    check("a row that lost its leading pipe is still read", "Bravo" in entries)
    check("and it does not take the rest of the table with it", "Charlie" in entries)
    check("the recovered row keeps its own columns",
          entries.get("Bravo", {}).get("notes") == "Saved without its first pipe",
          entries.get("Bravo", {}).get("notes"))
    check("a table with no OptiPatcher column claims none",
          entries["Delta"]["optipatcher"] is False)
    check("and its notes are its notes, not its images",
          entries["Delta"]["notes"] == "Requires a mod", entries["Delta"]["notes"])
    check("while the main table still reads the patcher column",
          entries["Alpha"]["optipatcher"] is True and entries["Bravo"]["optipatcher"] is False)

    # Prose is allowed to contain a pipe; only something shaped like a row is
    # recovered as one.
    prose = (
        "| Game | Compatibility |\n|---|---|\n| [Echo](Echo) | \u2705 |\n"
        "See the table above | it explains the columns\n"
        "| [Foxtrot](Foxtrot) | \u2705 |\n"
    )
    names = [e["name"] for e in wiki_mod.parse_compat_list(prose)]
    check("a sentence carrying a pipe is not read as a row", names == ["Echo"], names)

    seed = json.loads((ROOT / "defaults" / "compat-list.json").read_text())
    # The seed is regenerated per release, and a truncated one is how this
    # reaches a Deck that is offline: the list it falls back to is this file.
    check("the bundled seed is the whole list, not a truncated one",
          len(seed["entries"]) > 600, len(seed["entries"]))


def check_library_labels():
    """Only the SD card is called an SD card.

    The label used to be a path test — anything under /run/media, or with
    "mmcblk" anywhere in the string — so every USB stick and external SSD came
    back as "SD Card". It is now the mount's own block device, which is the only
    thing that actually knows, and this fakes /proc/mounts to drive it.
    """
    print("\nLibrary labels")
    from optiscaler.service import OptiScalerService

    mounts = {
        "/": "/dev/nvme0n1p8",                 # internal SSD, as on most Decks
        "/run/media/mmcblk0p1": "/dev/mmcblk0p1",   # the SD card
        "/run/media/deck/USB": "/dev/sda1",         # a USB stick
        "/run/media/deck/EXT": "/dev/nvme1n1p1",    # an external NVMe drive
        "/home/deck": "/dev/nvme0n1p8",
    }

    def fake_device(path):
        path = str(path)
        best, best_len = None, -1
        for mount, device in mounts.items():
            if path == mount or path.startswith(mount.rstrip("/") + "/"):
                if len(mount) > best_len:
                    best, best_len = device, len(mount)
        return best

    service = OptiScalerService.__new__(OptiScalerService)
    service.home = Path("/home/deck")
    original = OptiScalerService._mount_device
    OptiScalerService._mount_device = staticmethod(fake_device)
    try:
        card = service._library_label("/run/media/mmcblk0p1/steamapps/common")
        usb = service._library_label("/run/media/deck/USB/games")
        ext = service._library_label("/run/media/deck/EXT/games")
        internal = service._library_label("/home/deck/.local/share/Steam")
        check("the sd card is called an sd card", card.startswith("SD Card"), card)
        check("a usb stick is not", not usb.startswith("SD Card"), usb)
        check("nor is an external ssd", not ext.startswith("SD Card"), ext)
        check("internal storage is still internal", internal == "Internal Storage", internal)

        # The 64GB Deck boots from eMMC, so its internal drive is an mmcblk
        # device too - being MMC cannot be the whole test.
        mounts["/"] = "/dev/mmcblk0p8"
        mounts["/run/media/mmcblk1p1"] = "/dev/mmcblk1p1"
        emmc_root = service._library_label("/run/media/mmcblk0p1/steamapps/common")
        real_card = service._library_label("/run/media/mmcblk1p1/steamapps/common")
        check("the drive the system booted from is never the card",
              not emmc_root.startswith("SD Card"), emmc_root)
        check("the other mmc drive still is", real_card.startswith("SD Card"), real_card)
    finally:
        OptiScalerService._mount_device = original

    check("partition suffixes are stripped from either drive naming scheme",
          (OptiScalerService._disk_name("/dev/mmcblk0p1"),
           OptiScalerService._disk_name("/dev/nvme0n1p8"),
           OptiScalerService._disk_name("/dev/sda2")) == ("mmcblk0", "nvme0n1", "sda"))


def _pe(machine):
    """The smallest file `compat.pe_machine` reads as a Windows executable."""
    return b"MZ" + b"\0" * 58 + (64).to_bytes(4, "little") + b"PE\0\0" + machine.to_bytes(2, "little")


def check_devices():
    """Which machine this is, from sysfs, and the upscaler it starts with.

    The PCI ids are the ones HelixSR's speed test printed on each: a Steam Deck
    OLED (1002:1435, which used to read as Rembrandt) and a BC-250 (1002:13fe,
    gfx1013). A BC-250 starts with HLX FSR 4; anything else with FSR 4 Lite.
    """
    print("\nDevices")
    from optiscaler import sysinfo

    def machine(model, gfx=None, board=""):
        root = Path(tempfile.mkdtemp(prefix="optiscaler-sysfs-"))
        card = root / "drm" / "card0" / "device"
        card.mkdir(parents=True)
        (card / "vendor").write_text("0x1002\n")
        (card / "device").write_text(model + "\n")
        node = root / "kfd" / "1"
        node.mkdir(parents=True)
        (node / "properties").write_text(f"gfx_target_version {gfx or 0}\n")
        saved = sysinfo.DRM_ROOT, sysinfo.KFD_NODES, sysinfo._names
        sysinfo.DRM_ROOT, sysinfo.KFD_NODES = root / "drm", root / "kfd"
        sysinfo._names = lambda: [board] if board else []
        sysinfo.gpu_info.cache_clear()
        try:
            return sysinfo.gpu_info()
        finally:
            sysinfo.DRM_ROOT, sysinfo.KFD_NODES, sysinfo._names = saved
            sysinfo.gpu_info.cache_clear()
            shutil.rmtree(root, ignore_errors=True)

    oled = machine("0x1435", 100303, "Galileo")
    check("a Steam Deck OLED is a Steam Deck, not Rembrandt",
          oled["device"] == "steamdeck" and "Steam Deck" in oled["name"]
          and oled["generation"] == "RDNA2", oled)
    lcd = machine("0x163f", 100303, "Jupiter")
    check("and so is an LCD one", lcd["device"] == "steamdeck", lcd)
    bc250 = machine("0x13fe", 100103)
    check("a BC-250 is told apart, gfx1013 and no FSR 4 from OptiScaler",
          bc250["device"] == "bc250" and bc250["gfx"] == "gfx1013"
          and bc250["fsr4"] == "unsupported", bc250)
    other = machine("0x15bf", 110300)
    check("any other machine is neither", other["device"] is None, other)

    real = sysinfo.gpu_info
    try:
        import optiscaler.service as service_mod
        service_mod.gpu_info = lambda: {"device": "bc250"}
        check("a BC-250 starts a game with HLX FSR 4",
              OptiScalerService.default_upscaler() == "hlx-fsr4")
        service_mod.gpu_info = lambda: {"device": "steamdeck"}
        check("a Steam Deck with FSR 4 Lite", OptiScalerService.default_upscaler() == "fsr4-lite")
    finally:
        service_mod.gpu_info = real


def check_compat():
    """The list's compatibility badges: folder evidence first, then the wiki.

    Each game below is built to land on exactly one verdict, including the two
    ways the folder can mislead - OptiScaler's own support DLLs looking like
    the game's, and a 32-bit launcher in front of a 64-bit game.
    """
    print("\nCompatibility badges")
    from optiscaler import compat

    root = Path(tempfile.mkdtemp(prefix="decky-optiscaler-compat-"))
    try:
        x64, x86 = _pe(0x8664), _pe(0x014C)

        def game(name, files):
            folder = root / "games" / name
            for rel, data in files.items():
                path = folder / rel
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_bytes(data)
            return folder

        dlss = game("Zzqx Dlss Game", {
            "Zzqx.exe": x64,
            "Engine/Plugins/Runtime/Nvidia/DLSS/Binaries/ThirdParty/Win64/nvngx_dlss.dll": b"",
        })
        ours = game("Zzqx Set Up Game", {
            "Zzqx.exe": x64,
            "OptiScaler.ini": b"",
            "dxgi.dll": b"",
            # What a pd-upscaler install puts at the root for PDPerfPlugin.
            "libxess.dll": b"",
            "OptiScaler/libxess.dll": b"",
            "OptiScaler/amd_fidelityfx_upscaler_dx12.dll": b"",
            "OptiScaler/D3D12_OptiScaler/D3D12Core.dll": b"",
        })
        backed_up = game("Zzqx Backed Up Game", {
            "Zzqx.exe": x64,
            "OptiScaler.ini": b"",
            "libxess.dll": b"",
            "decky_optiscaler_backup_files/libxess.dll": b"",
        })
        guarded = game("Zzqx Guarded Game", {
            "Zzqx.exe": x64, "EasyAntiCheat/EasyAntiCheat_EOS_Setup.exe": x86,
            "nvngx_dlss.dll": b"",
        })
        launcher = game("Zzqx Launcher Game", {
            "ZzqxLauncher.exe": x86, "bin/x64/Zzqx Launcher Game.exe": x64,
        })
        old = game("Zzqx Old Game", {"Zzqx Old Game.exe": x86, "libxess.dll": b""})
        native = game("Zzqx Native Game", {"zzqx.x86_64": b"\x7fELF", "nvngx_dlss.dll": b""})
        bare = game("Zzqx Bare Game", {"Zzqx Bare Game.exe": x64})
        listed = game("Cyberpunk 2077", {"bin/x64/Cyberpunk2077.exe": x64})
        broken = game("EA Sports WRC", {"WRC.exe": x64, "nvngx_dlss.dll": b""})
        partial = game("Wolfenstein Youngblood", {"Youngblood_x64vk.exe": x64})
        linux_listed = game("Cyberpunk Native", {"cyberpunk.x86_64": b"\x7fELF"})

        scan = compat.scan(dlss)
        check("a shipped DLSS library is found deep inside an Unreal install",
              scan["inputs"] == ["DLSS"] and scan["arch"] == "x64", scan)
        check("OptiScaler's own support DLLs are not read as the game's",
              compat.scan(ours)["inputs"] == [], compat.scan(ours))
        check("the game's originals in the backup folder still count",
              compat.scan(backed_up)["inputs"] == ["XeSS"], compat.scan(backed_up))
        scan = compat.scan(launcher)
        check("a 32-bit launcher does not make a 64-bit game read as 32-bit",
              scan["arch"] == "x64" and scan["exe"].endswith("Zzqx Launcher Game.exe"), scan)

        service = OptiScalerService(
            ROOT, root / "settings", root / "runtime", root, logging.getLogger("selftest")
        )
        # The bundled list is all this needs; no refresh behind the answer.
        service.refresh_wiki_if_stale = lambda: None
        service.settings.set_wiki_entry(str(launcher), "Minecraft RTX")
        service.settings.set_wiki_entry(str(linux_listed), "Cyberpunk 2077")
        everything = [dlss, guarded, launcher, old, native, bare, listed, broken, partial,
                      linux_listed]
        games = [{"path": str(p), "name": p.name, "size_on_disk": 0} for p in everything]
        result = asyncio.run(service.assess_games(games))
        status = {Path(path).name: verdict["status"] for path, verdict in result.items()}
        check("every game gets a verdict", len(result) == len(everything), status)

        expected = {
            "Zzqx Dlss Game": "likely",
            "Zzqx Guarded Game": "risky",
            "Zzqx Launcher Game": "partial",
            "Zzqx Old Game": "unsupported",
            "Zzqx Native Game": "unsupported",
            "Zzqx Bare Game": "unknown",
            "Cyberpunk 2077": "listed",
            "EA Sports WRC": "broken",
            "Wolfenstein Youngblood": "partial",
            "Cyberpunk Native": "unsupported",
        }
        for name, want in expected.items():
            check(f"{name} reads as {want}", status.get(name) == want, status.get(name))

        pinned = result[str(launcher)]["wiki"]
        check("a pinned wiki entry wins over name matching",
              pinned and pinned["name"] == "Minecraft RTX" and pinned["manual"], pinned)
        check("only the hopeful verdicts count as compatible",
              sorted(Path(p).name for p, v in result.items() if v["compatible"]) ==
              sorted(["Zzqx Dlss Game", "Zzqx Launcher Game", "Cyberpunk 2077",
                      "Wolfenstein Youngblood"]))

        # A scan is reused until the folder changes; a forced one is not. The
        # stamp is moved to the folder's new mtime, standing in for a change
        # deeper down that the top folder's mtime does not see.
        (dlss / "libxess.dll").write_bytes(b"")
        service._compat_scans[str(dlss)] = ((dlss.stat().st_mtime_ns, 0),
                                            service._compat_scans[str(dlss)][1])
        again = asyncio.run(service.assess_games(games[:1]))
        check("an unchanged folder is not walked again",
              again[str(dlss)]["inputs"] == ["DLSS"], again[str(dlss)]["inputs"])
        forced = asyncio.run(service.assess_games(games[:1], True))
        check("a forced check walks it again",
              forced[str(dlss)]["inputs"] == ["DLSS", "XeSS"], forced[str(dlss)]["inputs"])
    finally:
        shutil.rmtree(root, ignore_errors=True)


def check_nightly():
    """The nightly channel: which release it trusts, and when it downloads.

    Driven through a fake transport, so what is under test is the decisions:
    only a release that states its SHA-256 and lives in the nightly repository
    is used, the API is only read over verified TLS, a download that does not
    match is thrown away, and being offline falls back to the last download
    rather than to nothing.
    """
    print("\nNightly channel")
    from optiscaler import nightly, payload as payload_mod, wiki as wiki_mod

    data = b"not really a 7z, but the bytes the digest names"
    digest = hashlib.sha256(data).hexdigest()
    base = "https://github.com/optiscaler/OptiScaler-nightly/releases/download"

    def release(tag, asset, sha=digest, url=None):
        return {"tag_name": tag, "html_url": f"https://example/{tag}", "published_at": tag,
                "assets": [{"name": asset, "size": len(data), "digest": f"sha256:{sha}",
                            "browser_download_url": url or f"{base}/{tag}/{asset}"}]}

    newest = release("nightly-20990101", "OptiScaler_v10.0.0-pre1_20990101.7z")
    picked = nightly.pick_release([
        {"draft": True, **release("nightly-20990102", "OptiScaler_v10.0.0-pre1_20990102.7z")},
        release("nightly-x", "OptiScaler_v10.0.0-pre1_20990101.7z", url="https://evil/x.7z"),
        {**release("nightly-y", "OptiScaler_v10.0.0-pre1_20990101.7z"),
         "assets": [{"name": "OptiScaler_v10.0.0-pre1_20990101.7z", "size": 1,
                     "browser_download_url": f"{base}/y/a.7z"}]},
        newest,
    ])
    check("drafts, foreign URLs and assets without a digest are passed over",
          picked and picked["tag"] == "nightly-20990101", picked)
    check("version and date are read out of the asset name",
          picked and (picked["version"], picked["date"]) == ("10.0.0-pre1", "20990101"), picked)

    real_json, real_download = wiki_mod.download_json, wiki_mod.download
    calls = {"api": 0, "download": 0}
    state = {"releases": [newest], "offline": False, "body": data}

    def fake_json(url, timeout=20, verified_only=False):
        calls["api"] += 1
        if not verified_only:
            raise AssertionError("the release API must be read over verified TLS")
        if state["offline"]:
            raise OSError("network is unreachable")
        return state["releases"]

    def fake_download(url, dest, timeout=90):
        calls["download"] += 1
        Path(dest).write_bytes(state["body"])
        return dest

    root = Path(tempfile.mkdtemp(prefix="optiscaler-nightly-"))
    wiki_mod.download_json, wiki_mod.download = fake_json, fake_download
    try:
        channel = nightly.NightlyChannel(root / "nightly")
        channel.ensure()
        info = channel.current()
        check("the first install downloads the newest nightly",
              info and info["tag"] == "nightly-20990101" and calls["download"] == 1, calls)
        channel.ensure()
        check("a recent check is not repeated", calls["api"] == 1, calls)
        channel.ensure(force=True)
        check("checking again for the same build does not download it again",
              calls["api"] == 2 and calls["download"] == 1, calls)

        state["offline"] = True
        kept = channel.ensure(force=True)
        check("offline, the last download is used", kept["tag"] == "nightly-20990101")
        check("and why the check failed is kept for Settings",
              "unreachable" in (channel.status()["error"] or ""), channel.status()["error"])
        state["offline"] = False

        state["releases"] = [release("nightly-20990105", "OptiScaler_v10.0.0-pre1_20990105.7z",
                                     sha="0" * 64)]
        try:
            channel.ensure(force=True)
            check("a download that does not match its digest is refused", False)
        except ValueError:
            check("a download that does not match its digest is refused",
                  not (root / "nightly" / "OptiScaler_v10.0.0-pre1_20990105.7z").exists()
                  and channel.current()["tag"] == "nightly-20990101")

        state["releases"] = [release("nightly-20990106", "OptiScaler_v10.0.0-pre1_20990106.7z")]
        channel.ensure(force=True)
        archives = sorted(p.name for p in (root / "nightly").glob("*.7z"))
        check("a newer build replaces the older archive",
              archives == ["OptiScaler_v10.0.0-pre1_20990106.7z"], archives)

        empty = nightly.NightlyChannel(root / "empty")
        state["offline"] = True
        try:
            empty.ensure()
            check("with nothing downloaded, offline is an error rather than nothing", False)
        except RuntimeError as exc:
            check("with nothing downloaded, offline is an error rather than nothing",
                  "첫 설치" in str(exc), exc)
        state["offline"] = False

        # Unpacking, when this machine has an archiver that can also write one.
        archiver = shutil.which("7z") or shutil.which("7za")
        if archiver:
            release_dir = root / "release"
            (release_dir / "OptiScaler").mkdir(parents=True)
            (release_dir / "OptiScaler.dll").write_bytes(b"OptiScaler")
            (release_dir / "OptiScaler" / "libxess.dll").write_bytes(b"x")
            built = root / "built.7z"
            subprocess.run([archiver, "a", "-bd", str(built), "."], cwd=release_dir,
                           capture_output=True, check=True)
            state["body"] = built.read_bytes()
            state["releases"] = [release("nightly-20990107",
                                         "OptiScaler_v10.0.0-pre1_20990107.7z",
                                         sha=hashlib.sha256(state["body"]).hexdigest())]
            unpacked = payload_mod.Payload(channel, root / "payload").ensure(force=True)
            check("the archive unpacks into a folder named after its tag",
                  unpacked.name == "nightly-20990107"
                  and (unpacked / "OptiScaler" / "libxess.dll").is_file(), unpacked)
        else:
            print("  [skip] no 7z to build a test archive with")
    finally:
        wiki_mod.download_json, wiki_mod.download = real_json, real_download
        shutil.rmtree(root, ignore_errors=True)

    # The transport itself: verified_only must never fall to the unverified
    # context, which is fine for the wiki's public text and not for a hash.
    real_contexts, real_open = wiki_mod._candidate_contexts, wiki_mod._open
    saved = wiki_mod._ssl_context, wiki_mod._ssl_context_kind
    try:
        wiki_mod._ssl_context = wiki_mod._ssl_context_kind = None
        wiki_mod._candidate_contexts = lambda: iter([("unverified", object())])
        wiki_mod._open = lambda request, timeout, context, binary=False: "{}"
        try:
            wiki_mod._http_get("https://api.github.com/x", verified_only=True)
            check("a verified-only request never uses the unverified context", False)
        except Exception:
            check("a verified-only request never uses the unverified context", True)
        check("while the wiki's own requests still may",
              wiki_mod._http_get("https://raw.githubusercontent.com/x") == "{}")
        wiki_mod._ssl_context = wiki_mod._ssl_context_kind = None
        wiki_mod._ssl_context, wiki_mod._ssl_context_kind = object(), "unverified"
        try:
            wiki_mod._http_get("https://api.github.com/x", verified_only=True)
            check("nor a remembered unverified one", False)
        except Exception:
            check("nor a remembered unverified one", True)
    finally:
        wiki_mod._candidate_contexts, wiki_mod._open = real_contexts, real_open
        wiki_mod._ssl_context, wiki_mod._ssl_context_kind = saved


def check_versioning():
    """Which version a push to main is released as, and the notes it gets.

    The release workflow trusts these two decisions completely: a wrong one
    publishes over a tag that exists, or a release with no notes.
    """
    print("\nRelease versioning")
    sys.path.insert(0, str(ROOT / "scripts"))
    import version as v

    check("an untagged package.json version is released as it is",
          v.next_version("0.1.0", set()) == ("0.1.0", False))
    check("once it is tagged, the next push is the next patch",
          v.next_version("0.1.0", {"v0.1.0"}) == ("0.1.1", True))
    check("[minor] and [major] in the commit message bump those instead",
          v.next_version("0.1.3", {"v0.1.3"}, "Add a thing [minor]") == ("0.2.0", True)
          and v.next_version("0.1.3", {"v0.1.3"}, "[MAJOR] rework") == ("1.0.0", True))
    check("a manual run's choice wins over the message",
          v.next_version("0.1.3", {"v0.1.3"}, "[major]", "minor") == ("0.2.0", True))
    check("a bump never lands on a tag that exists",
          v.next_version("0.1.0", {"v0.1.0", "v0.1.1", "v0.1.2"}) == ("0.1.3", True))
    check("a released prerelease is followed by its final version",
          v.next_version("0.2.0-rc1", {"v0.2.0-rc1"}) == ("0.2.0", True))

    changelog = ("# Changelog\n\n## [Unreleased]\n\n- Did a thing.\n\n"
                 "## [0.0.7] - 2026-09-18\n\nOld.\n")
    released = v.release_changelog(changelog, "0.1.0", "2026-10-28", "- fallback")
    check("[Unreleased] becomes the release's section, with a fresh one above",
          "## [Unreleased]\n\n## [0.1.0] - 2026-10-28\n\n- Did a thing." in released
          and "- fallback" not in released, released)
    empty = "# Changelog\n\n## [Unreleased]\n\n## [0.0.7] - 2026-09-18\n\nOld.\n"
    filled = v.release_changelog(empty, "0.1.1", "2026-10-29", "- Fix a bug")
    check("an empty [Unreleased] gets the commit subjects instead of no notes",
          "## [0.1.1] - 2026-10-29\n\n- Fix a bug\n\n## [0.0.7]" in filled, filled)
    check("a version that already has a section is left alone",
          v.release_changelog(released, "0.1.0", "2026-10-30", "- x") == released)


def check_plugin_updates():
    """Telling the user about a newer plugin release, and what Decky is handed.

    Decky checks the zip against the SHA-256 given here and installs it under
    the name given here, so both have to come from this repository's own
    release, and a version that is not newer must never be offered.
    """
    print("\nPlugin updates")
    from optiscaler import updates, wiki as wiki_mod

    check("versions compare as numbers, not text",
          updates.version_key("0.1.10") > updates.version_key("0.1.9"))
    check("a prerelease sorts before its release",
          updates.version_key("0.2.0-rc1") < updates.version_key("0.2.0"))
    check("a version that is not one has no order", updates.version_key("nightly") is None)

    base = "https://github.com/supercleans/decky-upscaler-manager/releases/download"

    def release(version, digest="ab" * 32, url=None):
        name = f"Decky-Upscaler-Manager-v{version}.zip"
        return {"tag_name": f"v{version}", "html_url": f"https://example/v{version}",
                "published_at": "2026-10-28T00:00:00Z",
                "assets": [{"name": name, "size": 1, "digest": f"sha256:{digest}",
                            "browser_download_url": url or f"{base}/v{version}/{name}"}]}

    check("an asset from somewhere else is not offered",
          updates.pick_asset(release("0.2.0", url="https://evil/x.zip")) is None)
    check("nor one without a digest",
          updates.pick_asset({"assets": [{"name": "Decky-Upscaler-Manager-v0.2.0.zip",
                                          "browser_download_url": f"{base}/v0.2.0/x.zip"}]})
          is None)

    real_json = wiki_mod.download_json
    state = {"release": release("0.2.0"), "calls": 0}

    def fake_json(url, timeout=20, verified_only=False):
        state["calls"] += 1
        if not verified_only:
            raise AssertionError("release metadata must be read over verified TLS")
        if state["release"] is None:
            raise OSError("offline")
        return state["release"]

    wiki_mod.download_json = fake_json
    try:
        checker = updates.PluginUpdates("0.1.1", "Decky Upscaler Manager")
        answer = checker.check()
        check("a newer release is offered, with what Decky needs to install it",
              answer["update_available"] and answer["latest"] == "0.2.0"
              and answer["sha256"] == "ab" * 32 and answer["name"] == "Decky Upscaler Manager"
              and answer["url"].endswith("/Decky-Upscaler-Manager-v0.2.0.zip"), answer)
        checker.check()
        check("and is not asked again straight away", state["calls"] == 1, state["calls"])
        state["release"] = release("0.1.1")
        check("the version already running is not an update",
              not checker.check(force=True)["update_available"])
        state["release"] = release("0.1.0")
        check("nor is an older one", not checker.check(force=True)["update_available"])
        state["release"] = None
        offline = checker.check(force=True)
        check("offline, the answer says why rather than offering anything",
              offline["error"] and not offline["update_available"], offline["error"])
    finally:
        wiki_mod.download_json = real_json


def check_update_installed_games():
    """Every game on an older nightly is installed again, except a running one.

    It is the same reinstall a game's own page does, so it keeps the proxy
    filename, the ini and OptiPatcher - and REFramework stays tracked, so an
    uninstall afterwards still hands the game its own dinput8 back.
    """
    print("\nUpdating installed games")
    from optiscaler.constants import REFRAMEWORK_DLL

    root = Path(tempfile.mkdtemp(prefix="optiscaler-update-games-"))
    try:
        payload = build_payload(root)
        service = OptiScalerService(ROOT, root / "settings", root / "runtime", root,
                                    logging.getLogger("selftest"))
        service.payload.ensure = lambda force=False, logger=None, tag=None: payload
        service.nightly.current = lambda: {"tag": "nightly-20990101", "version": "10.0.0-old"}

        def game(name):
            folder = root / "games" / name
            folder.mkdir(parents=True)
            (folder / f"{name}.exe").write_bytes(b"MZ")
            return folder

        stale, running, current = game("Stale"), game("Running"), game("Current")
        # Stale: winmm.dll, OptiPatcher and REFramework (over the game's own dinput8).
        (stale / REFRAMEWORK_DLL).write_bytes(b"the game's own dinput8")
        ref = root / "ref"
        ref.mkdir()
        (ref / REFRAMEWORK_DLL).write_bytes(b"REFramework")
        patcher = root / "OptiPatcher.asi"
        patcher.write_bytes(b"MZ patcher")
        installer.install(str(stale), str(payload), "winmm.dll", False, None, patcher,
                          [ref / REFRAMEWORK_DLL], "rev1",
                          {"tag": "nightly-20990101", "version": "10.0.0-old"})
        for folder in (running, current):
            installer.install(str(folder), str(payload), "dxgi.dll", False, None,
                              patcher if folder is current else None, None,
                              None, {"tag": "nightly-20990101", "version": "10.0.0-old"})
        # A newer rolling OptiPatcher than the one these games got.
        newer = root / "newer" / "OptiPatcher.asi"
        newer.parent.mkdir()
        newer.write_bytes(b"MZ newer patcher")
        newer_info = {"path": str(newer), "sha256": hashlib.sha256(newer.read_bytes()).hexdigest(),
                      "label": "rolling (2099-01-02)", "source": "download"}
        service.optipatcher.ensure = lambda force=False, logger=None: newer_info

        # A newer nightly is downloaded; Current was already installed from it.
        service.nightly.current = lambda: {"tag": "nightly-20990102", "version": "10.0.0-new"}
        manifest = json.loads((current / ".decky-optiscaler.json").read_text())
        manifest["optiscaler_tag"] = "nightly-20990102"
        (current / ".decky-optiscaler.json").write_text(json.dumps(manifest))

        async def listing():
            return [dict(name=f.name, path=str(f), **{
                "installed": True, "managed": True, "filename": d["filename"],
                "install_path": str(f), "optiscaler_tag": d["tag"],
                "optiscaler_version": d["version"]})
                for f in (stale, running, current) for d in [installer.detect(str(f))]]

        service.list_all_games = listing
        real_mapped = installer.mapped_files
        installer.mapped_files = lambda: {str((running / "dxgi.dll").resolve())}
        try:
            result = asyncio.run(service.update_installed_games())
        finally:
            installer.mapped_files = real_mapped
        by_name = {entry["name"]: entry for entry in result["results"]}
        check("only the games on an older nightly, or an older OptiPatcher, are touched",
              set(by_name) == {"Stale", "Running", "Current"}, sorted(by_name))
        check("a game current on the nightly only gets the newer OptiPatcher",
              by_name.get("Current", {}).get("ok")
              and by_name["Current"]["from"] == "OptiPatcher"
              and (current / "OptiScaler" / "plugins" / "OptiPatcher.asi").read_bytes()
              == b"MZ newer patcher"
              and installer.detect(str(current))["tag"] == "nightly-20990102",
              by_name.get("Current"))
        check("an older one is installed again from the current nightly",
              by_name.get("Stale", {}).get("ok")
              and installer.detect(str(stale))["tag"] == "nightly-20990102",
              by_name.get("Stale"))
        check("keeping its filename and OptiPatcher, now the newest build",
              installer.detect(str(stale))["filename"] == "winmm.dll"
              and (stale / "OptiScaler" / "plugins" / "OptiPatcher.asi").read_bytes()
              == b"MZ newer patcher")
        check("a running game is skipped, not replaced under it",
              by_name.get("Running", {}).get("skipped")
              and installer.detect(str(running))["tag"] == "nightly-20990101",
              by_name.get("Running"))
        kept = installer.read_manifest(stale)
        check("REFramework stays tracked through the update",
              kept.get("reframework") and REFRAMEWORK_DLL in kept["files"], kept.get("files"))
        installer.uninstall(str(stale))
        check("so an uninstall still gives the game its own dinput8 back",
              (stale / REFRAMEWORK_DLL).read_bytes() == b"the game's own dinput8")

        # The case the lost tracking actually broke: with no dinput8 of the
        # game's to restore over it, an untracked REFramework outlived the
        # uninstall and kept loading into the game.
        bare = game("Bare")
        installer.install(str(bare), str(payload), "dxgi.dll", False, None, None,
                          [ref / REFRAMEWORK_DLL], "rev1",
                          {"tag": "nightly-20990101", "version": "10.0.0-old"})
        installer.install(str(bare), str(payload), "dxgi.dll", True, None, None, None, None,
                          {"tag": "nightly-20990102", "version": "10.0.0-new"})
        installer.uninstall(str(bare))
        check("and a REFramework of ours is not left behind after a reinstall",
              not (bare / REFRAMEWORK_DLL).exists())
    finally:
        shutil.rmtree(root, ignore_errors=True)


def check_reframework_downloads():
    """REFramework is only ever installed from a download that matched its digest.

    It is a third-party engine hook placed in somebody's game folder, which is
    why the download was once switched off. Back on, it has to come from the
    expected repository, with the SHA-256 GitHub's API names for that asset,
    read over verified TLS - and a mismatch must never reach the cache.
    """
    print("\nREFramework downloads")
    from optiscaler import reframework, wiki as wiki_mod
    from optiscaler.constants import REFRAMEWORK_AUTO_INSTALL, REFRAMEWORK_DLL

    check("automatic installation is on", REFRAMEWORK_AUTO_INSTALL is True)

    root = Path(tempfile.mkdtemp(prefix="optiscaler-ref-"))
    good = root / "good.zip"
    with zipfile.ZipFile(good, "w") as zf:
        zf.writestr(f"x/{REFRAMEWORK_DLL}", b"REF build")
        zf.writestr("x/reframework_revision.txt", "abc123")
    body = good.read_bytes()
    digest = hashlib.sha256(body).hexdigest()
    nightly = "https://github.com/praydog/REFramework-nightly/releases/download"
    pd = "https://github.com/TheRazerMD/REFramework/releases/download"

    def asset(name, url, sha=digest):
        return {"name": name, "browser_download_url": url, "digest": f"sha256:{sha}"}

    state = {"latest": {"tag_name": "n1", "assets": [asset("REFramework.zip", f"{nightly}/n1/REFramework.zip")]},
             "pd": [], "offline": False, "body": body, "downloads": 0}

    def fake_json(url, timeout=20, verified_only=False):
        if not verified_only:
            raise AssertionError("release metadata must be read over verified TLS")
        if state["offline"]:
            raise OSError("offline")
        return state["latest"] if "REFramework-nightly" in url else state["pd"]

    def fake_download(url, dest, timeout=90):
        state["downloads"] += 1
        Path(dest).parent.mkdir(parents=True, exist_ok=True)
        Path(dest).write_bytes(state["body"])
        return dest

    real_json, real_download = wiki_mod.download_json, wiki_mod.download
    wiki_mod.download_json, wiki_mod.download = fake_json, fake_download
    nightly_wanted = {"asset": "REFramework.zip", "variant": "nightly", "automatic": True}
    pd_wanted = {"asset": "MHWILDS.zip", "variant": "pd-upscaler", "automatic": True}
    try:
        files = reframework.fetch(nightly_wanted, root / "cache")
        check("a build that matches its digest is unpacked to its dll",
              [f.name for f in files] == [REFRAMEWORK_DLL] and files[0].read_bytes() == b"REF build")
        reframework.fetch(nightly_wanted, root / "cache")
        check("and the same build is not downloaded twice", state["downloads"] == 1, state["downloads"])

        state["latest"] = {"tag_name": "n2", "assets": [
            asset("REFramework.zip", f"{nightly}/n2/REFramework.zip", sha="0" * 64)]}
        try:
            reframework.fetch(nightly_wanted, root / "cache")
            check("a download that does not match its digest is refused", False)
        except ValueError:
            check("a download that does not match its digest is refused",
                  not list((root / "cache" / "nightly").glob("*0000000000000000*")))

        state["latest"] = {"tag_name": "n3", "assets": [
            asset("REFramework.zip", "https://evil.example/REFramework.zip")]}
        try:
            reframework.resolve(nightly_wanted)
            check("an asset from another place is not taken", False)
        except FileNotFoundError:
            check("an asset from another place is not taken", True)

        state["pd"] = [
            {"tag_name": "pd-new", "assets": [asset("RE2.zip", f"{pd}/pd-new/RE2.zip")]},
            {"tag_name": "pd-old", "assets": [asset("MHWILDS.zip", f"{pd}/pd-old/MHWILDS.zip")]},
        ]
        found = reframework.resolve(pd_wanted)
        check("a pd build is the newest release that carries that game's asset",
              found["tag"] == "pd-old" and found["url"].endswith("/MHWILDS.zip"), found)

        state["offline"] = True
        cached = reframework.fetch(nightly_wanted, root / "cache")
        check("offline, a build verified earlier is still used",
              cached and cached[0].read_bytes() == b"REF build")
        try:
            reframework.fetch(pd_wanted, root / "cache")
            check("but one never downloaded is not installed unverified", False)
        except OSError:
            check("but one never downloaded is not installed unverified", True)
    finally:
        wiki_mod.download_json, wiki_mod.download = real_json, real_download
        shutil.rmtree(root, ignore_errors=True)


def check_dropin():
    """FSR drop-in: FSR 4 in a game's own FSR 3.1, by swapping its DLL.

    It writes into the game's own FidelityFX files, so the contract that
    matters is the one OptiScaler's install keeps: find the right folder, keep
    every original, put the folder back exactly, and never share a folder with
    OptiScaler. The build itself comes only from the expected repository, with
    the digest GitHub names, over verified TLS.
    """
    print("\nFSR drop-in")
    from optiscaler import compat, dropin, wiki as wiki_mod
    from optiscaler.constants import BACKUP_DIR

    root = Path(tempfile.mkdtemp(prefix="optiscaler-dropin-"))
    try:
        base = "https://github.com/zgauthier2000/fsr4-shader-performance-overrides/releases/download"

        def asset(name, tag, sha="ab" * 32, url=None):
            return {"name": name, "digest": f"sha256:{sha}",
                    "browser_download_url": url or f"{base}/{tag}/{name}"}

        picked = dropin.pick_release([
            {"tag_name": "timing-kit-2026-10-25", "assets": [
                asset("fsr4-timing-kit-windows-2026-10-25.zip", "timing-kit-2026-10-25")]},
            {"tag_name": "dll-2026-10-23", "assets": [
                asset("fsr4.1.1-igpu-cyboman-rdna2-2026-10-23.7z", "x", url="https://evil/x.7z")]},
            {"tag_name": "dll-2026-10-22", "assets": [
                asset("fsr4.1.1-cyboman-rx7000-2026-10-22.7z", "dll-2026-10-22"),
                asset("fsr4.1.1-igpu-cyboman-rdna2-2026-10-22.7z", "dll-2026-10-22")]},
        ])
        check("the newest dll release's Steam Deck archive is chosen, nothing else",
              picked and picked["tag"] == "dll-2026-10-22"
              and picked["asset"] == "fsr4.1.1-igpu-cyboman-rdna2-2026-10-22.7z", picked)

        # A download that does not match its digest never reaches the cache.
        real_json, real_download = wiki_mod.download_json, wiki_mod.download
        verified = []

        def fake_json(url, timeout=20, verified_only=False):
            verified.append(verified_only)
            return [{"tag_name": "dll-2026-10-22", "assets": [
                asset("fsr4.1.1-igpu-cyboman-rdna2-2026-10-22.7z", "dll-2026-10-22", sha="0" * 64)]}]

        def fake_download(url, dest, timeout=90):
            Path(dest).parent.mkdir(parents=True, exist_ok=True)
            Path(dest).write_bytes(b"not the build the digest names")
            return dest

        wiki_mod.download_json, wiki_mod.download = fake_json, fake_download
        try:
            dropin.fetch(root / "cache")
            check("a download that does not match its digest is refused", False)
        except ValueError:
            check("a download that does not match its digest is refused",
                  not list((root / "cache").glob("*.7z")))
        finally:
            wiki_mod.download_json, wiki_mod.download = real_json, real_download
        check("and the release list was read over verified TLS", verified == [True], verified)

        # The two layouts a game's FSR 3.1 comes in.
        upscaler = root / "cyboman.dll"
        upscaler.write_bytes(b"FSR 4 drop-in")
        payload = root / "payload" / "OptiScaler"
        payload.mkdir(parents=True)
        (payload / "amd_fidelityfx_loader_dx12.dll").write_bytes(b"SDK 2 loader")
        (payload / "amd_fidelityfx_framegeneration_dx12.dll").write_bytes(b"SDK 2 FG")

        def game(name, files):
            folder = root / name
            (folder / "bin").mkdir(parents=True)
            (folder / "bin" / "Game.exe").write_bytes(_pe(0x8664))
            for rel, data in files.items():
                (folder / "bin" / rel).write_bytes(data)
            # OptiScaler's own copy and a backed-up original must not be mistaken
            # for the game's.
            (folder / "OptiScaler").mkdir()
            (folder / "OptiScaler" / "amd_fidelityfx_upscaler_dx12.dll").write_bytes(b"opti")
            (folder / BACKUP_DIR).mkdir()
            (folder / BACKUP_DIR / "amd_fidelityfx_dx12.dll").write_bytes(b"old")
            return folder

        split = game("Split", {"amd_fidelityfx_upscaler_dx12.dll": b"game upscaler 3.1",
                               "amd_fidelityfx_dx12.dll": b"game loader"})
        mono = game("Mono", {"amd_fidelityfx_dx12.dll": b"game FFX 3.1"})
        none = game("None", {})
        check("a game with its upscaler as its own file is split, in the exe's folder",
              dropin.find_target(split) == {"dir": str(split / "bin"), "layout": "split"},
              dropin.find_target(split))
        check("one with a single amd_fidelityfx_dx12.dll is monolithic",
              (dropin.find_target(mono) or {}).get("layout") == "monolithic")
        check("OptiScaler's own copy and the backups are not the game's FSR",
              dropin.find_target(none) is None, dropin.find_target(none))

        for folder in (split, mono):
            before = {p.name: p.read_bytes() for p in (folder / "bin").iterdir()}
            result = dropin.install(str(folder), upscaler, "dll-2026-10-22", root / "payload")
            state = dropin.status(str(folder))
            check(f"{folder.name}: the drop-in goes in and is recorded",
                  state["installed"] and state["intact"]
                  and (folder / "bin" / "amd_fidelityfx_upscaler_dx12.dll").read_bytes() == b"FSR 4 drop-in",
                  result)
            if folder is mono:
                check("a monolithic game gets the SDK 2 loader under its FFX name, and the frame generator",
                      (folder / "bin" / "amd_fidelityfx_dx12.dll").read_bytes() == b"SDK 2 loader"
                      and (folder / "bin" / "amd_fidelityfx_framegeneration_dx12.dll").is_file())
            dropin.uninstall(str(folder))
            after = {p.name: p.read_bytes() for p in (folder / "bin").iterdir()}
            check(f"{folder.name}: removing it puts the folder back exactly", after == before,
                  sorted(after))

        # A game update that puts the original back is noticed, not trusted.
        dropin.install(str(split), upscaler, "dll-2026-10-22")
        (split / "bin" / "amd_fidelityfx_upscaler_dx12.dll").write_bytes(b"game upscaler 3.1")
        check("a game update that restores its own DLL reads as not intact",
              not dropin.status(str(split))["intact"])
        dropin.uninstall(str(split))

        # Never two ways of putting FSR 4 into one folder.
        service = OptiScalerService(ROOT, root / "settings", root / "runtime", root,
                                    logging.getLogger("selftest"))
        dropin.install(str(split), upscaler, "dll-2026-10-22")
        refused = asyncio.run(service.install(str(split / "bin"), "dxgi.dll"))
        check("OptiScaler is refused where the drop-in is in place",
              not refused["ok"] and "드롭인" in refused["error"], refused.get("error"))
        dropin.uninstall(str(split))
        (split / "bin" / "dxgi.dll").write_bytes(b"OptiScaler" + b"\0" * (5 << 20))
        blocked = asyncio.run(service.install_dropin(str(split)))
        check("and the drop-in is refused where OptiScaler is installed",
              not blocked["ok"] and "OptiScaler" in blocked["error"], blocked.get("error"))

        # The games list: who can take the drop-in, who has to have REFramework.
        ref_entry = {"name": "X", "compatibility": "✅", "inputs": "DLSS",
                     "notes": "Requires REFramework mod (pd-upscaler branch)"}
        with_ffx = compat.verdict({"inputs": ["FSR3.1"], "ffx_dx12": ["bin/amd_fidelityfx_dx12.dll"],
                                   "exe": "Game.exe", "arch": "x64", "anti_cheat": []}, ref_entry)
        without = compat.verdict({"inputs": ["DLSS"], "ffx_dx12": [], "exe": "Game.exe",
                                  "arch": "x64", "anti_cheat": []}, ref_entry)
        check("a REFramework game with its own FSR 3.1 can take the drop-in instead",
              with_ffx["dropin"] and with_ffx["reframework"] and not with_ffx["reframework_only"],
              with_ffx)
        check("one without has to have REFramework",
              not without["dropin"] and without["reframework_only"], without)
        plain = compat.verdict({"inputs": ["DLSS"], "ffx_dx12": [], "exe": "Game.exe",
                                "arch": "x64", "anti_cheat": []},
                               {"name": "Y", "compatibility": "✅", "inputs": "DLSS", "notes": ""})
        check("and a game the wiki says nothing about needs nothing",
              not plain["reframework"] and not plain["reframework_only"]
              and not plain["optipatcher"])
        patched = compat.verdict({"inputs": ["DLSS"], "ffx_dx12": [], "exe": "Game.exe",
                                  "arch": "x64", "anti_cheat": []},
                                 {"name": "Z", "compatibility": "✅", "inputs": "DLSS",
                                  "notes": "", "optipatcher": True})
        check("a game in the wiki's OptiPatcher column is marked for it", patched["optipatcher"])
        scanned = compat.scan(split)
        check("the folder scan finds the game's FSR, not OptiScaler's or a backup",
              scanned["ffx_dx12"] and all(BACKUP_DIR not in p and not p.startswith("OptiScaler")
                                          for p in scanned["ffx_dx12"]), scanned["ffx_dx12"])
    finally:
        shutil.rmtree(root, ignore_errors=True)


def build_helixsr(home, version="3.1.0", built=True):
    """A HelixSR build where HelixSR Desktop keeps one, shaped like 3.1.0's.

    ``built`` is whether its setup ran: the network trailer on helixsr.dll and
    the HLX FSR 4 trailer on both copies of HLX FSR 4.
    """
    root = home / ".local/share/HelixSR-Desktop/releases" / version / f"HelixSR-{version}"
    helix = root / "HelixSR"
    scaler = root / "helixsr-scaler"
    (scaler / "OptiScaler" / "plugins").mkdir(parents=True)
    helix.mkdir(parents=True)
    (root / "HLX-FSR4").mkdir()
    net = b"HXSRNET1" + b"\0" * 24 if built else b""
    hlx = b"HLXFSR4D" + b"\0" * 16 if built else b""
    (helix / "helixsr.dll").write_bytes(b"MZ\0HelixSR " + version.encode() + b"\0" + b"\0" * 64 + net)
    (helix / "helixsr.ini").write_text("[Compatibility]\nWaveSize = auto\n")
    (scaler / "OptiScaler.dll").write_bytes(b"OptiScaler" + b"\0" * (5 << 20))
    shutil.copy2(ROOT / "defaults" / "OptiScaler.reference.ini", scaler / INI_NAME)
    (scaler / "README-Linux.txt").write_text("HelixSR Scaler 2.1.0 for Linux and Steam Deck\n")
    (scaler / "OptiScaler" / "amd_fidelityfx_upscaler_dx12.dll").write_bytes(b"MZ HLX FSR 4" + hlx)
    (scaler / "OptiScaler" / "amd_fidelityfx_upscaler_dx12.amd.dll").write_bytes(_ffx_upscaler())
    (scaler / "OptiScaler" / "libxess.dll").write_bytes(b"XESS" * 64)
    (scaler / "OptiScaler" / "plugins" / "OptiPatcher.asi").write_bytes(b"MZ Scaler's OptiPatcher")
    (root / "HLX-FSR4" / "amd_fidelityfx_upscaler_dx12.dll").write_bytes(b"MZ HLX FSR 4" + hlx)
    return root


def check_helixsr():
    """HLX DLSS from the HelixSR build HelixSR Desktop made, and HLX FSR 4 as a drop-in.

    HLX DLSS is not downloaded here, so the build has to be found where
    HelixSR Desktop keeps it and judged built or not by the trailer its setup
    writes; it goes in with HelixSR Scaler, which keeps its own OptiPatcher and
    turns ASI loading on for it. HLX FSR 4 (downloaded, see check_hlx) goes into
    an FSR 3.1 game as HelixSR's own drop-in does, with the game's file beside
    it. Switching a game between the nightly and the Scaler must not leave
    either's files behind.
    """
    print("\nHelixSR")
    from optiscaler import dropin, helixsr, hlx
    from optiscaler.inifile import IniFile

    root = Path(tempfile.mkdtemp(prefix="optiscaler-helixsr-"))
    try:
        home = root / "home"
        home.mkdir()
        check("no build is reported as not found", not helixsr.find(home)["found"])
        build_helixsr(home, "3.0.0", built=False)
        unbuilt = helixsr.find(home)
        check("a build whose setup never ran is found, but HLX DLSS in it is not ready",
              unbuilt["found"] and not unbuilt["dlss_ready"], unbuilt)
        release = build_helixsr(home, "3.1.0")
        found = helixsr.find(home)
        check("a built one wins, with its versions and HLX DLSS ready",
              found["version"] == "3.1.0" and found["scaler_version"] == "2.1.0"
              and found["dlss_ready"], found)
        # HLX FSR 4 is downloaded; here, the copy in that build stands in for it.
        real_fetch = hlx.fetch
        hlx.fetch = lambda cache, logger=None, tag=None: (
            release / "HLX-FSR4" / "amd_fidelityfx_upscaler_dx12.dll", "v3.2.0")

        service = OptiScalerService(ROOT, root / "settings", root / "runtime", home,
                                    logging.getLogger("selftest"))
        use_payload(service, build_payload(root))

        # -- HLX FSR 4 as a drop-in --------------------------------------------
        def game(name, files):
            folder = root / "games" / name
            (folder / "bin").mkdir(parents=True)
            (folder / "bin" / "Game.exe").write_bytes(_pe(0x8664))
            for rel, data in files.items():
                (folder / "bin" / rel).write_bytes(data)
            return folder

        split = game("Split", {"amd_fidelityfx_upscaler_dx12.dll": b"game upscaler 3.1"})
        mono = game("Mono", {"amd_fidelityfx_dx12.dll": b"game FFX 3.1"})
        for folder, name in ((split, "amd_fidelityfx_upscaler_dx12.dll"), (mono, "amd_fidelityfx_dx12.dll")):
            before = {p.name: p.read_bytes() for p in (folder / "bin").iterdir()}
            result = asyncio.run(service.install_dropin(str(folder), "hlx-fsr4"))
            beside = folder / "bin" / name.replace(".dll", ".original.dll")
            check(f"{folder.name}: HLX FSR 4 takes the game's file name, the game's file kept beside it",
                  result.get("ok") and (folder / "bin" / name).read_bytes().startswith(b"MZ HLX FSR 4")
                  and beside.read_bytes() == before[name], result)
            state = asyncio.run(service.get_dropin(str(folder)))
            check(f"{folder.name}: it reads as the HLX drop-in, intact",
                  state.get("upscaler") == "hlx-fsr4" and state.get("intact"), state)
            (folder / "bin" / "HLX_FSR.log").write_text("log")
            dropin.uninstall(str(folder))
            after = {p.name: p.read_bytes() for p in (folder / "bin").iterdir()}
            check(f"{folder.name}: removing it puts the folder back exactly", after == before, sorted(after))

        hlx.fetch = real_fetch
        swapped = asyncio.run(service.install_dropin(str(split), "hlx-dlss"))
        check("HLX DLSS is not a drop-in", not swapped["ok"], swapped)

        # -- HLX DLSS with HelixSR Scaler ---------------------------------------
        target = root / "games" / "Scaler"
        target.mkdir(parents=True)
        (target / "Game.exe").write_bytes(b"MZ")
        result = asyncio.run(service.install(str(target), "dxgi.dll", False, True, None, "hlx-dlss"))
        detected = installer.detect(str(target))
        values = IniFile(target / INI_NAME).to_dict()
        check("HLX DLSS installs HelixSR Scaler with the HelixSR folder beside it",
              result.get("ok") and (target / "HelixSR" / "helixsr.dll").is_file()
              and detected["engine"] == "helixsr" and detected["upscaler"] == "hlx-dlss"
              and detected["tag"] == "helixsr-3.1.0" and detected["version"] == "2.1.0", result)
        check("its ini is what HelixSR's own installer writes",
              values.get("Upscalers", {}).get("Dx12Upscaler") == "dlss"
              and values.get("DLSS", {}).get("HelixSR") in (None, "auto")
              and values.get("Plugins", {}).get("LoadAsiPlugins") == "true", values.get("Upscalers"))
        check("HelixSR Scaler's own OptiPatcher is used, not the rolling one",
              (target / "OptiScaler/plugins/OptiPatcher.asi").read_bytes() == b"MZ Scaler's OptiPatcher"
              and installer.read_manifest(target).get("optipatcher_bundled"), result.get("optipatcher"))
        status = asyncio.run(service.get_optipatcher_status(str(target)))
        check("and it is not reported as an outdated OptiPatcher", status["bundled"] and not status["outdated"],
              status)
        check("the FSR version is AMD's, read beside HLX FSR 4",
              detected["fsr4"]["ffx"]["version"] == "4.1.1.2740" and detected["fsr4"]["ffx"]["hlx"]
              and detected["fsr4"]["ready"], detected["fsr4"]["ffx"])

        build_helixsr(home, "3.2.0")
        later = helixsr.find(home)
        check("a newer HelixSR build is the one an update moves to", later["version"] == "3.2.0", later)

        async def listing():
            d = installer.detect(str(target))
            return [{"name": "Scaler", "path": str(target), "installed": True, "managed": True,
                     "filename": d["filename"], "install_path": str(target), "optiscaler_tag": d["tag"],
                     "optiscaler_version": d["version"], "engine": d["engine"], "upscaler": d["upscaler"]}]

        service.list_all_games = listing
        updated = asyncio.run(service.update_installed_games())
        check("updating installed games moves a HelixSR game to the newer HelixSR build, not the nightly",
              installer.detect(str(target))["tag"] == "helixsr-3.2.0"
              and installer.detect(str(target))["engine"] == "helixsr", updated)

        # Switching to FSR 4 Lite starts the OptiScaler folder over.
        result = asyncio.run(service.install(str(target), "dxgi.dll", True, False, None, "fsr4-lite"))
        values = IniFile(target / INI_NAME).to_dict()
        check("switching to FSR 4 Lite brings the nightly back, and nothing of the Scaler stays",
              result.get("ok") and installer.detect(str(target))["engine"] == "nightly"
              and not (target / "HelixSR").exists()
              and not (target / "OptiScaler/amd_fidelityfx_upscaler_dx12.amd.dll").exists()
              and not (target / "OptiScaler/plugins/OptiPatcher.asi").exists()
              and values.get("Upscalers", {}).get("Dx12Upscaler") == "ffx", result.get("files"))
        installer.uninstall(str(target))
        check("and an uninstall leaves the folder as it was",
              sorted(p.name for p in target.iterdir()) == ["Game.exe"], sorted(p.name for p in target.iterdir()))

        # Not without a build, and not over HelixSR Desktop's own install.
        shutil.rmtree(home / ".local")
        refused = asyncio.run(service.install(str(target), "dxgi.dll", False, False, None, "hlx-dlss"))
        check("an HLX DLSS install without a HelixSR build is refused, saying where to get one",
              not refused["ok"] and "HelixSR Desktop" in refused["error"], refused.get("error"))
        (target / "HelixSR-Scaler.files").write_text("dxgi.dll\n")
        foreign = asyncio.run(service.install(str(target), "dxgi.dll", False, False, None, "fsr4-lite"))
        check("a game HelixSR Desktop installed into is left to it",
              not foreign["ok"] and "HelixSR Desktop" in foreign["error"], foreign.get("error"))
    finally:
        shutil.rmtree(root, ignore_errors=True)


def check_hlx():
    """HelixSR's releases, downloaded for HLX FSR 4 like cyboman's builds.

    Only a release whose ZIP carries it built (3.2.0 on) and names its digest
    is used; the ZIP is checked against that digest before anything comes out
    of it, it is unpacked whole (HLX DLSS is built in it), nothing is taken
    from outside its folder, and one without the built trailer is refused.
    Offline, the one kept before is used. Only the releases in use stay.
    """
    print("\nHLX FSR 4 download")
    from optiscaler import hlx, wiki as wiki_mod

    base = "https://github.com/lonewolf0622/HelixSR/releases/download"
    root = Path(tempfile.mkdtemp(prefix="optiscaler-hlx-"))

    def zip_of(version, built=True, extra=None):
        path = root / f"HelixSR-{version}.zip"
        with zipfile.ZipFile(path, "w") as bundle:
            top = f"HelixSR-{version}"
            dll = b"MZ HLX FSR 4 " + version.encode() + (b"HLXFSR4D" + b"\0" * 16 if built else b"")
            bundle.writestr(f"{top}/HLX-FSR4/amd_fidelityfx_upscaler_dx12.dll", dll)
            bundle.writestr(f"{top}/helixsr-scaler/OptiScaler/amd_fidelityfx_upscaler_dx12.dll", b"scaler copy")
            bundle.writestr(f"{top}/HelixSR/helixsr.dll", b"MZ\0HelixSR " + version.encode() + b"\0")
            bundle.writestr(f"{top}/helixsr-setup.sh", "#!/usr/bin/env bash\n")
            bundle.writestr(f"{top}/README.md", "HelixSR")
            for name, data in (extra or {}).items():
                bundle.writestr(name, data)
        return path.read_bytes()

    def release(version, body, digest=None):
        tag = f"v{version}"
        return {"tag_name": tag, "published_at": f"2099-01-0{version[-1]}T00:00:00Z", "prerelease": True,
                "assets": [{"name": f"HelixSR-{version}.zip", "size": len(body),
                            "digest": "sha256:" + (digest or hashlib.sha256(body).hexdigest()),
                            "browser_download_url": f"{base}/{tag}/HelixSR-{version}.zip"},
                           {"name": "SHA256SUMS.txt", "digest": "sha256:" + "0" * 64,
                            "browser_download_url": f"{base}/{tag}/SHA256SUMS.txt"}]}

    new, old = zip_of("3.2.1"), zip_of("3.1.0", built=False)
    listed = [release("3.2.1", new), release("3.1.0", old)]
    check("only releases that carry HLX FSR 4 built are offered",
          [r["tag"] for r in hlx.usable_releases(listed)] == ["v3.2.1"])

    bodies = {"HelixSR-3.2.1.zip": new}
    state = {"offline": False, "downloads": 0}
    real_json, real_download = wiki_mod.download_json, wiki_mod.download

    def fake_json(url, timeout=20, verified_only=False):
        if not verified_only:
            raise AssertionError("the release list must be read over verified TLS")
        if state["offline"]:
            raise OSError("network is unreachable")
        return state.get("listed", listed)

    def fake_download(url, dest, timeout=90):
        state["downloads"] += 1
        Path(dest).parent.mkdir(parents=True, exist_ok=True)
        Path(dest).write_bytes(bodies[url.rsplit("/", 1)[1]])
        return dest

    wiki_mod.download_json, wiki_mod.download = fake_json, fake_download
    try:
        cache = root / "cache"
        path, tag = hlx.fetch(cache)
        check("the newest release is unpacked whole, its HLX FSR 4 used from there, and the ZIP not kept",
              tag == "v3.2.1" and path == cache / "v3.2.1" / "HLX-FSR4" / "amd_fidelityfx_upscaler_dx12.dll"
              and path.read_bytes().startswith(b"MZ HLX FSR 4 3.2.1")
              and (cache / "v3.2.1" / "helixsr-setup.sh").is_file()
              and (cache / "v3.2.1" / "helixsr-scaler" / "OptiScaler").is_dir()
              and not list(cache.glob("*.zip")), (tag, sorted(p.name for p in cache.iterdir())))
        hlx.fetch(cache)
        check("and not downloaded again", state["downloads"] == 1, state)

        state["offline"] = True
        kept, kept_tag = hlx.fetch(cache)
        check("offline, the one kept before is used", kept_tag == "v3.2.1" and kept == path)
        try:
            hlx.fetch(root / "empty")
            check("offline with nothing kept is an error", False)
        except OSError:
            check("offline with nothing kept is an error", True)
        state["offline"] = False

        bad = zip_of("3.2.2")
        bodies["HelixSR-3.2.2.zip"] = bad
        state["listed"] = [release("3.2.2", bad, digest="ab" * 32)]
        try:
            hlx.fetch(root / "bad")
            check("a ZIP that does not match its digest is refused", False)
        except ValueError:
            check("a ZIP that does not match its digest is refused",
                  not any((root / "bad").glob("v3.2.2*")) and not list((root / "bad").glob("*.zip")))

        unbuilt = zip_of("3.2.3", built=False)
        bodies["HelixSR-3.2.3.zip"] = unbuilt
        state["listed"] = [release("3.2.3", unbuilt)]
        try:
            hlx.fetch(root / "unbuilt")
            check("an HLX FSR 4 without its built shaders is refused", False)
        except ValueError:
            check("an HLX FSR 4 without its built shaders is refused",
                  not any((root / "unbuilt").glob("v3.2.3*")))

        state["listed"] = listed + [release("3.2.0", zip_of("3.2.0"))]
        bodies["HelixSR-3.2.0.zip"] = zip_of("3.2.0")
        pinned, pinned_tag = hlx.fetch(cache, tag="v3.2.0")
        check("a pin takes that release instead of the newest",
              pinned_tag == "v3.2.0" and pinned.read_bytes().startswith(b"MZ HLX FSR 4 3.2.0"))
        check("both are kept until pruned", hlx.kept(cache) == {"v3.2.0", "v3.2.1"}, hlx.kept(cache))

        newest_dll = cache / "v3.2.1" / "HelixSR" / "helixsr.dll"
        newest_dll.write_bytes(newest_dll.read_bytes() + b"HXSRNET1" + b"\0" * 24)
        hlx.prune(cache, {"v3.2.0"})
        check("a prune keeps the one in use and the one HLX DLSS is built in",
              hlx.kept(cache) == {"v3.2.0", "v3.2.1"}, hlx.kept(cache))
        newest_dll.write_bytes(b"MZ\0HelixSR 3.2.1\0")
        hlx.prune(cache, {"v3.2.0"})
        check("and removes the rest", hlx.kept(cache) == {"v3.2.0"}, hlx.kept(cache))

        evil = zip_of("3.2.4", extra={"HelixSR-3.2.4/../../escaped.txt": "x"})
        bodies["HelixSR-3.2.4.zip"] = evil
        state["listed"] = [release("3.2.4", evil)]
        try:
            hlx.fetch(root / "evil")
            check("a ZIP that names a path outside its folder is refused", False)
        except ValueError:
            check("a ZIP that names a path outside its folder is refused",
                  not (root / "escaped.txt").exists() and not any((root / "evil").glob("v3.2.4*")))
    finally:
        wiki_mod.download_json, wiki_mod.download = real_json, real_download
        shutil.rmtree(root, ignore_errors=True)


def helixsr_release(folder, version="3.2.0", nvidia=b"MZ nvngx_dlss 310.7.0"):
    """A HelixSR release unpacked as hlx.fetch_release leaves it, HLX DLSS not built."""
    (folder / "setup").mkdir(parents=True)
    (folder / "HelixSR").mkdir()
    (folder / "HLX-FSR4").mkdir()
    scaler = folder / "helixsr-scaler"
    (scaler / "OptiScaler").mkdir(parents=True)
    (folder / "helixsr-setup.sh").write_text("#!/usr/bin/env bash\n")
    (folder / "setup" / "helixsr_setup.py").write_text(
        "DLSS_URL = 'https://raw.githubusercontent.com/NVIDIA/DLSS/v310.7.0/lib/nvngx_dlss.dll'\n"
        f"DLSS_SHA256 = '{hashlib.sha256(nvidia).hexdigest()}'\n"
        "DLSS_LICENSE = 'https://github.com/NVIDIA/DLSS/blob/v310.7.0/LICENSE.txt'\n")
    (folder / "HelixSR" / "helixsr.dll").write_bytes(b"MZ\0HelixSR " + version.encode() + b"\0" * 65)
    (folder / "HLX-FSR4" / "amd_fidelityfx_upscaler_dx12.dll").write_bytes(
        b"MZ HLX FSR 4" + b"HLXFSR4D" + b"\0" * 16)
    (scaler / "OptiScaler.dll").write_bytes(b"MZ")
    (scaler / "OptiScaler.ini").write_text("[Upscalers]\n")
    (scaler / "README-Linux.txt").write_text("HelixSR Scaler 2.2.0 for Linux and Steam Deck\n")
    return folder


FAKE_SETUP = r"""
import json, os, sys, time
from pathlib import Path
release, args = Path(sys.argv[1]), sys.argv[2:]
dlss = Path(args[args.index("--dlss") + 1])
(release / "ran.json").write_text(json.dumps({
    "args": args, "stdin": sys.stdin.read(), "home": os.environ.get("HOME"),
    "xdg": os.environ.get("XDG_DATA_HOME"), "ld": os.environ.get("LD_LIBRARY_PATH"),
    "dlss": dlss.read_bytes().decode()}))
mode = os.environ.get("FAKE_SETUP_MODE", "build")
print("[helixsr-setup] using a portable Python", flush=True)
if mode == "hang":
    time.sleep(60)
if mode == "fail":
    print("[helixsr-setup] error: the setup stopped", flush=True)
    sys.exit(1)
print("[helixsr-setup] [#########-----------]   45%  3:12  shaders", flush=True)
with open(release / "HelixSR" / "helixsr.dll", "ab") as out:
    out.write(b"HXSRNET1" + b"\0" * 24)
print("[helixsr-setup] done", flush=True)
"""


def check_hlx_build():
    """HLX DLSS built here by HelixSR's own setup, when HelixSR Desktop has not.

    The setup runs as it comes, handed NVIDIA's DLL (downloaded from where the
    setup names it and checked against the SHA-256 it names), with --no-fg,
    without --yes and with its input closed, so no question waits and the
    games step at its end changes nothing. What counts afterwards is the
    network in helixsr.dll. A build HelixSR Desktop made still comes first.
    """
    print("\nHLX DLSS build")
    import threading
    from optiscaler import helixsr, hlx, hlxbuild, wiki as wiki_mod

    root = Path(tempfile.mkdtemp(prefix="optiscaler-hlxbuild-"))
    nvidia = b"MZ nvngx_dlss 310.7.0"
    script = root / "fake_setup.py"
    script.write_text(FAKE_SETUP)

    def release(folder, version="3.2.0"):
        return helixsr_release(folder, version, nvidia)

    def proton(home):
        wine = home / ".local/share/Steam/steamapps/common/Proton 9.0/files/bin/wine"
        wine.parent.mkdir(parents=True)
        wine.write_text("#!/bin/sh\n")
        wine.chmod(0o755)

    served = {"body": nvidia}

    def fake_download(url, dest, timeout=90):
        Path(dest).parent.mkdir(parents=True, exist_ok=True)
        Path(dest).write_bytes(served["body"])
        return dest

    real_command, real_download, real_which = hlxbuild.setup_command, wiki_mod.download, shutil.which
    hlxbuild.setup_command = lambda release_dir, dll: [
        sys.executable, "-I", str(script), str(release_dir), *real_command(release_dir, dll)[2:]]
    wiki_mod.download = fake_download
    hlxbuild.shutil.which = lambda name, *a, **k: None if name == "wine" else real_which(name, *a, **k)
    saved_env = {k: os.environ.get(k) for k in ("LD_LIBRARY_PATH", "LD_LIBRARY_PATH_ORIG", "FAKE_SETUP_MODE")}
    try:
        cache = root / "runtime" / "helixsr"
        folder = release(cache / "v3.2.0")
        home = root / "home"
        home.mkdir()

        source = hlxbuild.dlss_source(folder)
        check("NVIDIA's DLL is the one HelixSR's own setup names",
              source["url"].startswith("https://raw.githubusercontent.com/NVIDIA/DLSS/")
              and source["sha256"] == hashlib.sha256(nvidia).hexdigest() and source["license"], source)
        command = real_command(folder, root / "nvngx_dlss.dll")
        check("the setup is the release's own script, without frame generation and without --yes",
              command == ["bash", str(folder / "helixsr-setup.sh"), "--no-fg", "--dlss",
                          str(root / "nvngx_dlss.dll")], command)
        os.environ["LD_LIBRARY_PATH"], os.environ["LD_LIBRARY_PATH_ORIG"] = "/tmp/_MEI1234", "/usr/lib/extra"
        env = hlxbuild.environment(home)
        check("it runs in the user's home, with the system's libraries rather than Decky's",
              env["HOME"] == str(home) and env["LD_LIBRARY_PATH"] == "/usr/lib/extra"
              and "LD_LIBRARY_PATH_ORIG" not in env
              and env["XDG_DATA_HOME"] == str(home / ".local" / "share"), env.get("LD_LIBRARY_PATH"))
        os.environ.pop("LD_LIBRARY_PATH_ORIG")

        build = hlxbuild.Build()
        try:
            build.run(folder, home)
            check("without Proton the build does not start, and says to install it", False)
        except RuntimeError as exc:
            check("without Proton the build does not start, and says to install it",
                  "Proton" in str(exc) and not (folder / "ran.json").exists(), str(exc))
        proton(home)

        served["body"] = b"MZ something else"
        try:
            build.run(folder, home)
            check("a DLL that is not the one the setup names is refused before the setup runs", False)
        except ValueError:
            check("a DLL that is not the one the setup names is refused before the setup runs",
                  not (folder / "ran.json").exists() and not list(cache.glob("*.nvngx_dlss.dll")))
        served["body"] = nvidia

        os.environ["FAKE_SETUP_MODE"] = "fail"
        try:
            build.run(folder, home)
            check("a setup that builds nothing is an error that says how it ended", False)
        except RuntimeError as exc:
            check("a setup that builds nothing is an error that says how it ended",
                  "exit 1" in str(exc) and "the setup stopped" in str(exc), str(exc))

        os.environ["FAKE_SETUP_MODE"] = "hang"
        build = hlxbuild.Build()
        build.begin()
        outcome = {}

        def hang():
            try:
                build.run(folder, home)
            except Exception as exc:
                outcome["error"] = str(exc)
            build.finish(outcome.get("error"))

        worker = threading.Thread(target=hang)
        worker.start()
        for _ in range(200):
            if build.status()["log"]:
                break
            time.sleep(0.05)
        check("a build can be cancelled", build.cancel())
        worker.join(30)
        check("and a cancelled one stops, says so, and leaves no NVIDIA DLL",
              not worker.is_alive() and not build.status()["running"]
              and "취소" in (build.status()["error"] or "")
              and not list(cache.glob("*.nvngx_dlss.dll")), build.status())
        os.environ.pop("FAKE_SETUP_MODE")

        build = hlxbuild.Build()
        build.begin()
        build.run(folder, home)
        build.finish()
        ran = json.loads((folder / "ran.json").read_text())
        status = build.status()
        check("the setup is handed NVIDIA's DLL, with its input closed, and builds HLX DLSS",
              ran["dlss"] == nvidia.decode() and ran["stdin"] == "" and "--yes" not in ran["args"]
              and "--no-fg" in ran["args"] and ran["home"] == str(home)
              and helixsr.network_built(folder / "HelixSR" / "helixsr.dll"), ran)
        check("its progress is read from what it prints, and NVIDIA's DLL is gone after",
              status["ok"] and any("45%" in line for line in status["log"])
              and not list(cache.glob("*.nvngx_dlss.dll")), status)

        found = helixsr.find(home, cache)
        check("the build made here is found, marked as the plugin's",
              found["dlss_ready"] and found["plugin"] and found["version"] == "3.2.0", found)
        desktop = build_helixsr(home, "3.1.0")
        old = time.time() - 86400
        os.utime(desktop / "HelixSR" / "helixsr.dll", (old, old))
        found = helixsr.find(home, cache)
        check("but one HelixSR Desktop built comes first, even an older one",
              found["dlss_ready"] and not found["plugin"] and found["version"] == "3.1.0", found)

        # Through the service: one at a time, in the release picked, the older ones gone after.
        home2 = root / "home2"
        home2.mkdir()
        proton(home2)
        service = OptiScalerService(ROOT, root / "settings", root / "runtime2", home2,
                                    logging.getLogger("selftest"))
        fresh = release(service.helixsr_cache() / "v3.2.1", "3.2.1")
        stale = release(service.helixsr_cache() / "v3.1.9", "3.1.9")
        real_fetch_release = hlx.fetch_release
        hlx.fetch_release = lambda cache_dir, logger=None, tag=None: (fresh, "v3.2.1")
        try:
            async def go():
                started = await service.build_hlx_dlss()
                again = await service.build_hlx_dlss()
                await service._hlx_build_task
                return started, again, await service.get_hlx_dlss_build()

            started, again, after = asyncio.run(go())
        finally:
            hlx.fetch_release = real_fetch_release
        check("the service starts one build, and not a second over it",
              started["ok"] and started["build"]["running"] and not again["ok"], (started, again))
        check("the build ends ready, and HLX DLSS comes from it",
              after["ok"] and not after["running"] and after["tag"] == "v3.2.1"
              and after["helixsr"]["dlss_ready"] and after["helixsr"]["plugin"], after)
        check("and releases no longer in use are removed", not stale.exists() and fresh.exists())
    finally:
        hlxbuild.setup_command, wiki_mod.download = real_command, real_download
        hlxbuild.shutil.which = real_which
        for key, value in saved_env.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value
        shutil.rmtree(root, ignore_errors=True)


def check_setup():
    """The plugin's own set-up, its updates, HelixSR Desktop, and removing it all.

    Nothing is offered until the set-up has downloaded OptiScaler's nightly,
    cyboman's builds and a HelixSR release; HLX DLSS is built in it only when
    asked (and from then on with every HelixSR update), and failing to build
    does not hold the rest up, a download failing does. A
    HelixSR Desktop set-up is used instead of a download, its updates are only
    said, and its going away is said too. Installs then use what was set up,
    without the network; newer builds are only looked for, and updated from
    Settings. Removing the downloads leaves the games alone and goes back to
    the set-up.
    """
    print("\nPlugin set-up")
    from optiscaler import dropin, hlx

    root = Path(tempfile.mkdtemp(prefix="optiscaler-setup-"))
    calls = {"nightly": [], "dropin": [], "helixsr": [], "build": []}
    fail = {"dropin": False, "build": False}
    newest = {"dropin": "dll-2099-01-02"}

    def fake_service(name, home=None):
        home = home or root / name / "home"
        home.mkdir(parents=True, exist_ok=True)
        service = OptiScalerService(ROOT, root / name / "settings", root / name / "runtime", home,
                                    logging.getLogger("selftest"))
        state = {"current": None}

        def ensure(force=False, logger=None, tag=None):
            calls["nightly"].append((force, tag))
            state["current"] = {"tag": tag or "nightly-20990102", "version": "10.0.0-test"}
            return root / "payload"

        service.payload.ensure = ensure
        service.nightly.current = lambda: dict(state["current"]) if state["current"] else None
        service.optipatcher.ensure = lambda force=False, logger=None: None

        def build(folder, home_dir, logger=None):
            calls["build"].append(Path(folder).name)
            if fail["build"]:
                raise RuntimeError("Proton을 찾지 못했습니다.")
            dll = Path(folder) / "HelixSR" / "helixsr.dll"
            dll.write_bytes(dll.read_bytes() + b"HXSRNET1" + b"\0" * 24)

        service.hlx_build.run = build
        return service

    def fake_dropin_fetch(cache_dir, logger=None, variant=None, tag=None):
        calls["dropin"].append((variant, tag))
        if fail["dropin"]:
            raise OSError("network is unreachable")
        tag = tag or newest["dropin"]
        path = Path(cache_dir) / tag / variant / "amd_fidelityfx_upscaler_dx12.dll"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(b"cyboman " + variant.encode())
        return path, tag

    def fake_fetch_release(cache_dir, logger=None, tag=None):
        calls["helixsr"].append(tag)
        tag = tag or "v3.2.1"
        folder = Path(cache_dir) / tag
        if not folder.exists():
            helixsr_release(folder, tag.lstrip("v"))
        return folder, tag

    real = (dropin.fetch, hlx.fetch_release, dropin.releases, hlx.releases)
    dropin.fetch, hlx.fetch_release = fake_dropin_fetch, fake_fetch_release
    try:
        async def until_done(service, start):
            started = await start
            if service._job_task:
                await service._job_task
            return started, await service.get_components()

        service = fake_service("fresh")
        before = asyncio.run(service.get_components())
        check("a new plugin is not set up, and has nothing",
              not before["setup_done"] and not any(c["installed"] for c in before["channels"].values()),
              before["channels"])

        async def twice():
            first = await service.start_setup(True)
            second = await service.start_setup()
            await service._job_task
            return first, second, await service.get_components()

        first, second, after = asyncio.run(twice())
        steps = {s["key"]: s["state"] for s in after["job"]["steps"]}
        check("the set-up runs once at a time", first["ok"] and not second["ok"], second)
        check("and downloads OptiScaler, both cyboman builds and HelixSR, and builds HLX DLSS when asked",
              after["setup_done"] and after["job"]["ok"]
              and steps == {"nightly": "done", "dropin": "done", "helixsr": "done", "hlx_dlss": "done",
                            "lsfgvk": "skipped"}
              and sorted(v for v, _ in calls["dropin"]) == ["4.1.2l-exact", "4.1.2l-lossy"]
              and calls["build"] == ["v3.2.1"], (steps, calls))
        channels = after["channels"]
        check("what it set up is what is installed, HelixSR the plugin's, HLX DLSS built",
              channels["nightly"]["installed"] == "nightly-20990102"
              and channels["dropin"]["installed"] == "dll-2099-01-02"
              and channels["helixsr"]["installed"] == "v3.2.1"
              and channels["helixsr"]["source"] == "plugin" and channels["helixsr"]["dlss_ready"],
              channels)
        check("installs then take what was set up, not the newest",
              service.target_tag("dropin") == "dll-2099-01-02"
              and service.target_tag("helixsr") == "v3.2.1")

        # Newer builds are said, for the channels that are not pinned.
        dropin.releases = lambda: [{"tag": "dll-2099-01-05"}, {"tag": "dll-2099-01-02"}]
        hlx.releases = lambda: [{"tag": "v3.2.1", "version": "3.2.1"}]
        service.nightly.releases = lambda: [{"tag": "nightly-20990109"}, {"tag": "nightly-20990102"}]
        asyncio.run(service.set_channel_version("nightly", "nightly-20990102"))
        checked = asyncio.run(service.check_updates(True))
        check("a newer build is said for each channel that has one, not a pinned one",
              checked["updates"] == ["dropin"] and checked["channels"]["dropin"]["latest"] == "dll-2099-01-05"
              and not checked["channels"]["nightly"]["update"] and checked["checked_at"],
              checked["updates"])
        asked = []
        service.nightly.releases = lambda: asked.append(1) or []
        asyncio.run(service.check_updates(False))
        check("and the channels are not asked again for hours", not asked)
        asyncio.run(service.set_channel_version("nightly", None))

        newest["dropin"] = "dll-2099-01-05"
        _, updated = asyncio.run(until_done(service, service.update_component("dropin")))
        check("an update downloads the newest, and the older build goes",
              updated["channels"]["dropin"]["installed"] == "dll-2099-01-05"
              and not updated["channels"]["dropin"]["update"]
              and not (service.dropin_cache() / "dll-2099-01-02").exists(), updated["channels"]["dropin"])
        fail["dropin"] = True
        newest["dropin"] = "dll-2099-01-09"
        _, broken = asyncio.run(until_done(service, service.update_component("dropin")))
        check("a failed update says why and keeps the build there was",
              not broken["job"]["ok"] and "unreachable" in broken["job"]["error"]
              and broken["channels"]["dropin"]["installed"] == "dll-2099-01-05", broken["job"])
        fail["dropin"] = False
        newest["dropin"] = "dll-2099-01-02"

        # HLX DLSS is not built unless asked for, nor by a HelixSR update then.
        calls["build"].clear()
        optout_service = fake_service("optout")
        _, optout = asyncio.run(until_done(optout_service, optout_service.start_setup()))
        steps = {s["key"]: (s["state"], s["detail"]) for s in optout["job"]["steps"]}
        check("left off, the set-up downloads everything but builds no HLX DLSS",
              optout["setup_done"] and steps["helixsr"][0] == "done" and steps["hlx_dlss"][0] == "skipped"
              and "설정에서" in steps["hlx_dlss"][1] and not calls["build"]
              and not optout["channels"]["helixsr"]["dlss_ready"]
              and not optout["channels"]["helixsr"]["dlss_enabled"], (steps, calls["build"]))
        _, refreshed = asyncio.run(until_done(optout_service, optout_service.update_component("helixsr")))
        check("and a HelixSR update does not build it either",
              not calls["build"] and {s["key"]: s["state"] for s in refreshed["job"]["steps"]}["hlx_dlss"]
              == "skipped", refreshed["job"]["steps"])

        async def build_now():
            await optout_service.build_hlx_dlss()
            await optout_service._hlx_build_task
            return await optout_service.get_components()

        wanted = asyncio.run(build_now())
        check("built from Settings later, it is wanted from then on",
              calls["build"] == ["v3.2.1"] and wanted["channels"]["helixsr"]["dlss_ready"]
              and wanted["channels"]["helixsr"]["dlss_enabled"], wanted["channels"]["helixsr"])

        # HLX DLSS failing to build holds nothing up; a download failing does.
        fail["build"] = True
        unbuilt_service = fake_service("unbuilt")
        _, unbuilt = asyncio.run(until_done(unbuilt_service, unbuilt_service.start_setup(True)))
        steps = {s["key"]: (s["state"], s["detail"]) for s in unbuilt["job"]["steps"]}
        check("HLX DLSS failing to build is said, and the plugin is set up all the same",
              unbuilt["setup_done"] and unbuilt["job"]["ok"] and steps["hlx_dlss"][0] == "failed"
              and "Proton" in steps["hlx_dlss"][1] and not unbuilt["channels"]["helixsr"]["dlss_ready"],
              steps)
        fail["build"] = False
        fail["dropin"] = True
        down_service = fake_service("down")
        _, down = asyncio.run(until_done(down_service, down_service.start_setup()))
        check("a download failing leaves the plugin not set up, with why",
              not down["setup_done"] and not down["job"]["ok"] and "unreachable" in down["job"]["error"]
              and {s["key"]: s["state"] for s in down["job"]["steps"]}["helixsr"] == "skipped",
              down["job"])
        fail["dropin"] = False

        # HelixSR Desktop's HelixSR is used as it is, and its going away said.
        desktop_service = fake_service("desktop")
        desktop_home = desktop_service.home
        build_helixsr(desktop_home, "3.2.0")
        calls["helixsr"].clear()
        calls["build"].clear()
        _, desk = asyncio.run(until_done(desktop_service, desktop_service.start_setup()))
        steps = {s["key"]: s["state"] for s in desk["job"]["steps"]}
        check("with HelixSR Desktop's HelixSR, nothing of HelixSR is downloaded or built",
              desk["setup_done"] and steps["helixsr"] == "skipped" and steps["hlx_dlss"] == "skipped"
              and not calls["helixsr"] and not calls["build"]
              and desk["channels"]["helixsr"]["source"] == "desktop", (steps, calls))
        dll, tag = desktop_service._hlx_fsr4()
        check("and HLX FSR 4 comes from it", tag == "helixsr-3.2.0" and "HelixSR-Desktop" in str(dll), dll)
        hlx.releases = lambda: [{"tag": "v3.2.1", "version": "3.2.1"}]
        newer = asyncio.run(desktop_service.check_updates(True))
        check("a newer HelixSR is said, for HelixSR Desktop to update",
              "helixsr" in newer["updates"] and newer["channels"]["helixsr"]["latest"] == "v3.2.1")
        refused = asyncio.run(desktop_service.update_component("helixsr"))
        check("and not updated here", not refused["ok"] and "HelixSR Desktop" in refused["error"], refused)
        shutil.rmtree(desktop_home / ".local/share/HelixSR-Desktop")
        gone = asyncio.run(desktop_service.get_components())
        check("HelixSR Desktop's HelixSR going away is said",
              gone["channels"]["helixsr"]["desktop_missing"] and gone["channels"]["helixsr"]["source"] is None,
              gone["channels"]["helixsr"])
        _, mended = asyncio.run(until_done(desktop_service, desktop_service.update_component("helixsr")))
        check("and the plugin sets HelixSR up itself then",
              not mended["channels"]["helixsr"]["desktop_missing"]
              and mended["channels"]["helixsr"]["source"] == "plugin"
              and mended["channels"]["helixsr"]["dlss_ready"], mended["channels"]["helixsr"])

        # Removing the downloads: the plugin's, and HelixSR's tools when HelixSR Desktop is not here.
        game = root / "games" / "Kept"
        (game / "OptiScaler").mkdir(parents=True)
        tools = service.home / ".local/share/HelixSR/python"
        tools.mkdir(parents=True)
        for name in ("payload", "optipatcher", "reframework"):
            (service.runtime_dir / name).mkdir(parents=True, exist_ok=True)
        removed = asyncio.run(service.remove_downloads())
        check("removing the downloads takes every one, and HelixSR's setup tools",
              removed["ok"] and not removed["components"]["setup_done"]
              and not any((service.runtime_dir / n).exists()
                          for n in ("payload", "fsr4-dropin", "helixsr", "optipatcher", "reframework"))
              and not tools.exists() and (game / "OptiScaler").is_dir()
              and service.installed_tag("dropin") is None
              and not removed["components"]["channels"]["helixsr"]["dlss_enabled"],
              removed["components"]["channels"])
        kept_tools = desktop_home / ".local/share/HelixSR/python"
        kept_tools.mkdir(parents=True)
        (desktop_home / ".local/share/HelixSR-Desktop").mkdir(parents=True)
        asyncio.run(desktop_service.remove_downloads())
        check("but HelixSR's tools stay where HelixSR Desktop shares them", kept_tools.exists())
    finally:
        dropin.fetch, hlx.fetch_release, dropin.releases, hlx.releases = real
        shutil.rmtree(root, ignore_errors=True)


def check_lsfgvk():
    """lsfg-vk: its official build installed into ~/.local, and frame generation set per game.

    The build server's latest release is the one installed, unmodified, and a
    known release is checked against its pinned SHA-256. Lossless Scaling's
    lsfg-vk branch and its DLL are found in the Steam libraries. A game's
    frame generation is a profile in lsfg-vk's own configuration matched by its
    Steam app id, written the way decky-lsfg-vk writes it, so the profiles that
    plugin made stay and read the same. Removing the plugin's downloads takes
    lsfg-vk only when the plugin put it there, and never the configuration.
    """
    print("\nlsfg-vk")
    import io
    import tarfile
    import tomllib
    from optiscaler import lsfgvk, wiki as wiki_mod
    from optiscaler.constants import LSFG_PAYLOAD

    root = Path(tempfile.mkdtemp(prefix="optiscaler-lsfg-"))

    def build(version):
        buffer = io.BytesIO()
        with tarfile.open(fileobj=buffer, mode="w:xz") as bundle:
            for name in ["bin/lsfg-vk-cli", *[n for n in LSFG_PAYLOAD if n != "bin/lsfg-vk-cli"]]:
                data = f"{name} {version}".encode()
                info = tarfile.TarInfo("./" + name)
                info.size = len(data)
                bundle.addfile(info, io.BytesIO(data))
        return buffer.getvalue()

    served = {}
    index = ('<tr><td><a href="lsfg-vk-9.9.9.r3.gabc.tar.xz">&gt;&gt; Latest git version (9.9.9.r3) &lt;&lt;</a></td></tr>'
             '<tr><td><a href="lsfg-vk-9.9.9.tar.xz">&gt;&gt; Latest release candidate (9.9.9) &lt;&lt;</a></td></tr>'
             '<tr><td><a href="lsfg-vk-9.9.9.tar.xz">&gt;&gt; Latest release (9.9.9) &lt;&lt;</a></td></tr>')

    def fake_get(url, timeout=12, binary=False, verified_only=False):
        if not verified_only:
            raise AssertionError("the build server is read over verified TLS only")
        return index

    def fake_download(url, dest, timeout=90, verified_only=False):
        if not verified_only:
            raise AssertionError("lsfg-vk is downloaded over verified TLS only")
        Path(dest).parent.mkdir(parents=True, exist_ok=True)
        Path(dest).write_bytes(served[url.rsplit("/", 1)[1]])
        return dest

    real = (wiki_mod._http_get, wiki_mod.download)
    wiki_mod._http_get, wiki_mod.download = fake_get, fake_download
    try:
        home = root / "home"
        check("the latest release is the one the build server names, not a candidate or a git build",
              lsfgvk.releases() == [{"tag": "9.9.9", "version": "9.9.9",
                                      "url": "https://builds.lsfg-vk.dev/lsfg-vk-9.9.9.tar.xz"}],
              lsfgvk.releases())
        served["lsfg-vk-2.0.0.tar.xz"] = build("2.0.0")
        try:
            lsfgvk.install(home, root / "cache", None, "2.0.0")
            check("a known release that is not the official build is refused", False)
        except ValueError:
            check("a known release that is not the official build is refused",
                  not lsfgvk.installed(home) and not list((root / "cache").glob("*.tar.xz")))
        legacy = home / ".local/lib/liblsfg-vk.so"
        legacy.parent.mkdir(parents=True)
        legacy.write_bytes(b"v1")
        served["lsfg-vk-9.9.9.tar.xz"] = build("9.9.9")
        version = lsfgvk.install(home, root / "cache", None)
        layer = home / ".local/lib/liblsfg-vk-layer.so"
        check("the latest one is unpacked into ~/.local as it came, and v1's layer goes",
              version == "9.9.9" and lsfgvk.installed(home) and layer.read_bytes() == b"lib/liblsfg-vk-layer.so 9.9.9"
              and (home / ".local/share/vulkan/implicit_layer.d/VkLayer_LSFGVK_frame_generation.json").is_file()
              and not legacy.exists() and not list((root / "cache").glob("*.tar.xz")))

        # Lossless Scaling, in a Steam library.
        library = home / ".local/share/Steam/steamapps"
        (library / "common/Lossless Scaling").mkdir(parents=True)
        manifest = library / "appmanifest_993090.acf"
        manifest.write_text('"AppState"\n{\n "appid" "993090"\n}\n')
        check("Lossless Scaling on its default branch is found, and not ready",
              lsfgvk.lossless(home) == {"installed": True, "branch": "public", "dll": None, "ready": False},
              lsfgvk.lossless(home))
        manifest.write_text('"AppState"\n{\n "appid" "993090"\n "UserConfig"\n {\n  "BetaKey" "lsfg-vk"\n }\n}\n')
        (library / "common/Lossless Scaling/lsfg-vk.dll").write_bytes(b"MZ")
        ready = lsfgvk.lossless(home)
        check("on the lsfg-vk branch with its DLL, it is ready", ready["ready"] and ready["dll"], ready)

        # The configuration, as decky-lsfg-vk left it.
        config = home / ".config/lsfg-vk/conf.toml"
        config.parent.mkdir(parents=True)
        config.write_text('version = 2\n\n[global]\nallow_fp16 = true\n\n[[profile]]\nname = "Cyberpunk 2077"\n'
                          'active_in = [ "1091500" ]\npacing_mode = "vsync"\nmultiplier = 1\nflow_scale = 0.8\n'
                          'performance_mode = true\noverride_present_mode = true\n'
                          'preserve_swapchain_image_count = false\n')
        check("a profile decky-lsfg-vk made reads as that game's, whatever it allows",
              lsfgvk.game_profile(home, "1091500")["multiplier"] == 1)
        lsfgvk.set_game_profile(home, "1245620", "Cyberpunk 2077", {"multiplier": 3, "flow_scale": 0.5},
                                dll=ready["dll"])
        data = tomllib.loads(config.read_text())
        names = {p["name"]: p for p in data["profile"]}
        check("turning it on adds the game's profile by its app id, beside the other, named apart",
              data["version"] == 2 and data["global"]["dll"] == ready["dll"]
              and names["Cyberpunk 2077 (1245620)"]["active_in"] == ["1245620"]
              and names["Cyberpunk 2077 (1245620)"]["multiplier"] == 3
              and names["Cyberpunk 2077"]["active_in"] == ["1091500"], data)
        lsfgvk.set_game_profile(home, "1245620", "ignored", {"performance_mode": True})
        changed = lsfgvk.game_profile(home, "1245620")
        check("changing it keeps its name and the rest of its settings",
              changed["name"] == "Cyberpunk 2077 (1245620)" and changed["multiplier"] == 3
              and changed["performance_mode"], changed)
        before = config.read_text()
        try:
            lsfgvk.set_game_profile(home, "1245620", "x", {"multiplier": 9})
            check("settings out of range are refused, the file left as it was", False)
        except ValueError:
            check("settings out of range are refused, the file left as it was", config.read_text() == before)
        lsfgvk.set_game_profile(home, "1245620", "x", {"multiplier": 1})
        check("a multiplier of 1 is frame generation off, kept as decky-lsfg-vk keeps it",
              lsfgvk.game_profile(home, "1245620")["multiplier"] == 1)
        lsfgvk.set_game_profile(home, "1245620", "x", None)
        check("turning it off removes that profile only",
              lsfgvk.game_profile(home, "1245620") is None and lsfgvk.game_profile(home, "1091500"))
        config.write_text('version = "1"\n[game]\nexe = "x"\n')
        check("a v1 configuration counts as none, as v2 cannot read it",
              lsfgvk.read_config(home)["profiles"] == [])
        config.write_text("version = 3\n")
        try:
            lsfgvk.set_game_profile(home, "1", "x", {"multiplier": 2})
            check("a configuration of a newer version is not rewritten", False)
        except ValueError:
            check("a configuration of a newer version is not rewritten", config.read_text() == "version = 3\n")
        config.unlink()

        # decky-lsfg-vk's ~/.lsfg: a game set up here leaves it, its workarounds carried over.
        wrapper = home / ".lsfg"
        wrapper.write_text("#!/bin/sh\n# lsfg-vk-wrapper-format: 2\n\nexec \"$@\"\n")
        state_file = home / ".config/lsfg-vk/workarounds.json"
        state_file.write_text(json.dumps({"version": 2, "apps": {"1245620": {"state": {
            "dxvkFrameRate": 30, "disableGamescopeWsi": True, "disableHdr": False,
            "disableSteamdeckMode": True, "disableVkbasalt": False, "enableZink": False},
            "command_token_added": True, "non_steam": False}}}))
        localconfig = home / ".local/share/Steam/userdata/1/config/localconfig.vdf"
        localconfig.parent.mkdir(parents=True)

        def launching(apps):
            body = "".join(f'"{a}"{{"LaunchOptions" "{o}"}}' for a, o in apps.items())
            localconfig.write_text('"UserLocalConfigStore"{"Software"{"Valve"{"Steam"{"apps"{' + body + "}}}}}")

        launching({"1245620": "~/.lsfg %command%", "1091500": "/home/deck/.lsfg %command%", "7": "mangohud %command%"})
        from optiscaler import steam as steam_mod
        check("the games still launching through ~/.lsfg are found",
              steam_mod.apps_launching_with(home, r"(^|\s)(~|/home/[^/\s]+)/\.lsfg(\s|$)") == {"1245620", "1091500"})
        kept = lsfgvk.release_wrapper(home, "1245620")
        check("a game leaving it gets its workarounds, the wrapper kept while another game runs it",
              kept["workarounds"]["dxvkFrameRate"] == 30 and not kept["removed"] and wrapper.is_file(), kept)
        launching({"1245620": "~/.lsfg %command%", "7": "mangohud %command%"})
        plugins = home / "homebrew/plugins/decky-lsfg-vk"
        plugins.mkdir(parents=True)
        (plugins / "plugin.json").write_text(json.dumps({"name": "Decky LSFG-VK"}))
        kept = lsfgvk.release_wrapper(home, "1245620")
        check("and kept while decky-lsfg-vk, which keeps it, is installed", not kept["removed"] and wrapper.is_file())
        shutil.rmtree(home / "homebrew")
        gone = lsfgvk.release_wrapper(home, "1245620")
        check("the last game leaving it with decky-lsfg-vk gone takes the wrapper and its state with it",
              gone["removed"] and not wrapper.exists() and not state_file.exists()
              and gone["workarounds"]["disableSteamdeckMode"], gone)
        wrapper.write_text("#!/bin/sh\nexec my-own-script \"$@\"\n")
        check("a ~/.lsfg that is not decky-lsfg-vk's is never removed",
              not lsfgvk.release_wrapper(home, "1245620")["removed"] and wrapper.is_file())
        wrapper.unlink()

        # Through the service: set up with it, its updates, a game's frame generation, removing it.
        service = OptiScalerService(ROOT, root / "settings", root / "runtime", home, logging.getLogger("selftest"))
        lsfgvk.uninstall(home)
        check("uninstalling takes the layer's files", not lsfgvk.installed(home) and not layer.exists())

        async def until_done(start):
            started = await start
            if service._job_task:
                await service._job_task
            return started, await service.get_components()

        service.payload.ensure = lambda force=False, logger=None, tag=None: root
        service.nightly.current = lambda: {"tag": "nightly-20990101", "version": "10"}
        service.optipatcher.ensure = lambda force=False, logger=None: None
        from optiscaler import dropin, hlx
        real_dropin, real_release = dropin.fetch, hlx.fetch_release

        def fake_dropin(cache_dir, logger=None, variant=None, tag=None):
            path = Path(cache_dir) / "dll-1" / variant / "amd_fidelityfx_upscaler_dx12.dll"
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(b"MZ")
            return path, "dll-1"

        def fake_release(cache_dir, logger=None, tag=None):
            folder = Path(cache_dir) / "v3.2.0"
            if not folder.exists():
                helixsr_release(folder)
            return folder, "v3.2.0"

        dropin.fetch, hlx.fetch_release = fake_dropin, fake_release
        try:
            _, plain = asyncio.run(until_done(service.start_setup()))
            check("left off at the set-up, lsfg-vk is not installed and its step says so",
                  plain["setup_done"] and not plain["lsfgvk"]["installed"]
                  and {s["key"]: s["state"] for s in plain["job"]["steps"]}["lsfgvk"] == "skipped",
                  plain["job"]["steps"])
            served["lsfg-vk-9.9.9.tar.xz"] = build("9.9.9")
            _, withit = asyncio.run(until_done(service.start_setup(False, True)))
            check("turned on, the set-up installs it, marked as the plugin's",
                  withit["lsfgvk"]["installed"] and withit["lsfgvk"]["by_plugin"]
                  and withit["lsfgvk"]["version"] == "9.9.9" and withit["lsfgvk"]["lossless"]["ready"],
                  withit["lsfgvk"])
        finally:
            dropin.fetch, hlx.fetch_release = real_dropin, real_release

        index = index.replace("9.9.9", "9.9.10")
        served["lsfg-vk-9.9.10.tar.xz"] = build("9.9.10")
        newer = asyncio.run(service.check_updates(True))
        check("a newer release is said", "lsfgvk" in newer["updates"] and newer["lsfgvk"]["latest"] == "9.9.10",
              newer["lsfgvk"])
        _, updated = asyncio.run(until_done(service.update_component("lsfgvk")))
        check("and updated from Settings", updated["lsfgvk"]["version"] == "9.9.10"
              and not updated["lsfgvk"]["update"], updated["lsfgvk"])

        on = asyncio.run(service.set_frame_generation("1245620", "ELDEN RING",
                                                      {"multiplier": 2, "flow_scale": 0.8, "performance_mode": False}))
        check("a game's frame generation is turned on through the service, with the DLL filled in",
              on["ok"] and on["profile"]["name"] == "ELDEN RING"
              and tomllib.loads(config.read_text())["global"]["dll"] == ready["dll"], on)
        off = asyncio.run(service.set_frame_generation("1245620", "ELDEN RING", None))
        check("and off", off["ok"] and off["profile"] is None, off)
        refused = asyncio.run(service.set_frame_generation("", "Shortcut", {"multiplier": 2}))
        check("a game without an app id is refused", not refused["ok"], refused)

        removed = asyncio.run(service.remove_downloads())
        check("removing the downloads takes the lsfg-vk the plugin installed, not its configuration",
              removed["ok"] and not lsfgvk.installed(home) and config.is_file()
              and not removed["components"]["lsfgvk"]["by_plugin"], removed["components"]["lsfgvk"])
        lsfgvk.install(home, root / "cache", None, "9.9.10")
        external = asyncio.run(service.get_components())["lsfgvk"]
        asyncio.run(service.remove_downloads())
        check("one installed some other way is used as it is: not offered updates, not removed",
              external["installed"] and not external["by_plugin"] and not external["update"]
              and lsfgvk.installed(home), external)
    finally:
        wiki_mod._http_get, wiki_mod.download = real
        shutil.rmtree(root, ignore_errors=True)


def check_requirements():
    """What a game needs besides OptiScaler, read out of its wiki entry.

    These are said, never installed, so the test is what is said: the mod or
    file the entry names, whether it is firm or only offered, and nothing from
    an alternative install method or a link's label. The list's two mod
    tables say it once for every game in them, so the table each row came
    from has to survive parsing and an old cache without it must not linger.
    """
    print("\nWhat else a game needs")
    from optiscaler import compat, requirements, wiki as wiki_mod

    def names(rec):
        return {item["name"]: item["required"] for item in requirements.mine(rec)}

    luma = names({"detail": {"Upscaler Inputs": "DLSS with Luma Framework"}})
    check("a mod named in Upscaler Inputs is firm", luma == {"Luma 모드": True}, luma)
    sekiro = names({"notes": "Requires using SekiroTSR mod as basis for DLSS inputs"})
    check("Requires ... mod is firm", sekiro == {"SekiroTSR 모드": True}, sekiro)
    nukem = names({"notes": "Use [Nukem's](Nukem's-dlssg-to-fsr3) for less crashing."})
    check("a mod only offered is not", nukem == {"Nukem's dlssg-to-fsr3": False}, nukem)
    dll = requirements.mine({"notes": "DLSS inputs require pasting the DLSS DLL file (`nvngx_dlss.dll`) into the game folder."})
    check("a file to copy is found with its underscore intact",
          [(i["name"], i["required"]) for i in dll] == [("nvngx_dlss.dll 복사", True)], dll)
    ue = requirements.mine({"notes": "Requires [these UE tweaks](Unreal-Engine-Tweaks#enable-dlss) for DLSSG inputs."})
    check("Engine.ini lines link to the wiki's own section",
          ue and ue[0]["name"] == "Engine.ini 수정"
          and ue[0]["link"].endswith("/Unreal-Engine-Tweaks#enable-dlss"), ue)
    table_link = names({"notes": "**Requires extra Engine.ini commands**, check [Luma UE table](https://github.com/Filoppi/Luma-Framework/wiki#unreal-engine)"})
    check("a link called \"Luma UE table\" is not a Luma mod", "Luma 모드" not in table_link, table_link)
    alt = names({"detail": {"Notes": "Install as dxgi.dll. METHOD 2 - using Ultimate ASI Loader, requires Special K"}})
    check("what only another install method needs is left out", alt == {}, alt)
    generic = names({"notes": "Requires the Fancy Upscaler mod and carefully reading the entry"})
    check("a mod not known by name is still named", generic == {"Fancy Upscaler 모드": True}, generic)
    plain = names({"notes": "Set Dxgi=false as spoofing isn't required. Requires REFramework."})
    check("REFramework and plain settings are not listed here", plain == {}, plain)

    luma_ue = requirements.mine({"table": "luma-ue", "notes": ""})
    check("every game in the Luma UE table needs Luma UE",
          [(i["name"], i["required"]) for i in luma_ue] == [("Luma UE 모드", True)], luma_ue)
    mods = names({"table": "mods", "notes": "Requires using a DLSS mod and carefully reading the entry"})
    check("an upscaler-mods game whose mod is named gets that, not the generic one",
          mods == {"DLSS 모드": True}, mods)
    bare = names({"table": "mods", "notes": "Use ERSS-FG mod as basis for Upscaling and FG."})
    check("and one whose mod is named in prose only once still gets it", bare == {"ERSS-FG 모드": True}, bare)

    page = ("## Main\n| Game | Compatibility | Upscaler Inputs | OptiPatcher | Notes |\n|--|--|--|--|--|\n"
            "| A | ✅ | DLSS | | |\n\n## Upscaler mods support\n\n| Game | Compatibility | Upscaler <br>Inputs | Notes | Images |\n"
            "|--|--|--|--|--|\n| B | ✅ | DLSS | Requires using a DLSS mod | |\n\n## Luma Unreal Engine\n\n"
            "| Game | Compatibility | Upscaler <br>Inputs | Notes | Images |\n|--|--|--|--|--|\n| C | ✅ | DLSS | | |\n")
    parsed = {e["name"]: e.get("table") for e in wiki_mod.parse_compat_list(page)}
    check("each row keeps the table it came from", parsed == {"A": None, "B": "mods", "C": "luma-ue"},
          parsed)
    verdict = compat.verdict({"inputs": ["DLSS"], "ffx_dx12": [], "exe": "Game.exe", "arch": "x64",
                              "anti_cheat": []},
                             {"name": "C", "compatibility": "✅", "inputs": "DLSS", "notes": "",
                              "table": "luma-ue"})
    check("the games list says what a game needs", verdict["requires"] == ["Luma UE 모드"],
          verdict.get("requires"))
    seed = json.loads((ROOT / "defaults" / "compat-list.json").read_text(encoding="utf-8"))
    check("the bundled list carries the tables",
          {e.get("table") for e in seed["entries"]} >= {"mods", "luma-ue"})


def check_cyboman():
    """cyboman's FSR 4.1.2 Lite builds: a drop-in, or OptiScaler's own upscaler.

    From 4.1.2 the archive's name and its folders changed. The newest archive has to be found under its new name, the folder asked for
    taken out of it, and in a game with no FSR 3.1 of its own the same file put
    where OptiScaler keeps its FidelityFX upscaler - and taken out again when
    the game goes back to plain FSR 4 Lite.
    """
    print("\ncyboman's FSR 4.1.2 Lite builds")
    from optiscaler import dropin
    from optiscaler.constants import FFX_UPSCALER_DLL

    base = "https://github.com/zgauthier2000/fsr4-shader-performance-overrides/releases/download"
    picked = dropin.pick_release([
        {"tag_name": "timing-kit-2026-10-29.2", "assets": []},
        {"tag_name": "dll-2026-10-29", "assets": [
            {"name": "fsr4.1.2-cyboman-rx6000-2026-10-29.7z", "digest": "sha256:" + "ab" * 32,
             "browser_download_url": f"{base}/dll-2026-10-29/fsr4.1.2-cyboman-rx6000-2026-10-29.7z"},
            {"name": "fsr4.1.2-igpu-cyboman-rdna2-2026-10-29.zip", "digest": "sha256:" + "ab" * 32,
             "browser_download_url": f"{base}/dll-2026-10-29/fsr4.1.2-igpu-cyboman-rdna2-2026-10-29.zip"},
            {"name": "fsr4.1.2-igpu-cyboman-rdna2-2026-10-29.7z", "digest": "sha256:" + "ab" * 32,
             "browser_download_url": f"{base}/dll-2026-10-29/fsr4.1.2-igpu-cyboman-rdna2-2026-10-29.7z"},
        ]},
    ])
    check("the 4.1.2 archive for the Deck is found under its new name",
          picked and picked["asset"] == "fsr4.1.2-igpu-cyboman-rdna2-2026-10-29.7z", picked)

    root = Path(tempfile.mkdtemp(prefix="optiscaler-cyboman-"))
    try:
        unpacked = root / "cache" / "dll-2026-10-29"
        for folder in ("exact", "lossy", "4.1.2l-exact", "4.1.2l-lossy"):
            (unpacked / folder).mkdir(parents=True)
            (unpacked / folder / "amd_fidelityfx_upscaler_dx12.dll").write_bytes(f"cyboman {folder}".encode())
        real_json = dropin.wiki.download_json
        dropin.wiki.download_json = lambda *a, **k: [{"tag_name": "dll-2026-10-29", "assets": [
            {"name": "fsr4.1.2-igpu-cyboman-rdna2-2026-10-29.7z", "digest": "sha256:" + "ab" * 32,
             "browser_download_url": f"{base}/dll-2026-10-29/fsr4.1.2-igpu-cyboman-rdna2-2026-10-29.7z"}]}]
        try:
            path, tag = dropin.fetch(root / "cache", None, "4.1.2l-exact")
            check("the folder asked for is the one taken",
                  tag == "dll-2026-10-29" and path.read_bytes() == b"cyboman 4.1.2l-exact", path)
            try:
                dropin.fetch(root / "cache", None, "4.1.2l-nothing")
                check("a folder the release no longer has is an error, not another build", False)
            except FileNotFoundError:
                check("a folder the release no longer has is an error, not another build", True)

            service = OptiScalerService(ROOT, root / "settings", root / "runtime", root,
                                        logging.getLogger("selftest"))
            use_payload(service, build_payload(root))
            service.dropin_cache = lambda: root / "cache"

            # A game with FSR 3.1 of its own takes it as a drop-in.
            game = root / "games" / "Split" / "bin"
            game.mkdir(parents=True)
            (game / "Game.exe").write_bytes(_pe(0x8664))
            (game / "amd_fidelityfx_upscaler_dx12.dll").write_bytes(b"game upscaler 3.1")
            result = asyncio.run(service.install_dropin(str(game.parent), "fsr412l-lossy"))
            state = asyncio.run(service.get_dropin(str(game.parent)))
            check("as a drop-in, the game's FSR 3.1 file is swapped for it",
                  result.get("ok") and (game / "amd_fidelityfx_upscaler_dx12.dll").read_bytes()
                  == b"cyboman 4.1.2l-lossy" and state.get("upscaler") == "fsr412l-lossy", state)
            dropin.uninstall(str(game.parent))

            # A game without one gets it through OptiScaler, in AMD's place.
            from optiscaler.inifile import IniFile
            target = root / "games" / "NoFsr"
            target.mkdir(parents=True)
            (target / "Game.exe").write_bytes(b"MZ")
            amd = (target.parent.parent / "payload" / FFX_UPSCALER_DLL).read_bytes()
            result = asyncio.run(service.install(str(target), "dxgi.dll", False, False, None,
                                                 "fsr412l-exact"))
            main = target / FFX_UPSCALER_DLL
            custom = "OptiScaler/custom/{}/ffx/amd_fidelityfx_upscaler_dx12.dll"
            check("through OptiScaler, it takes AMD's place, so DX11 and Vulkan games run it too",
                  result.get("ok") and main.read_bytes() == b"cyboman 4.1.2l-exact"
                  and installer.detect(str(target))["upscaler"] == "fsr412l-exact", result.get("error"))
            check("AMD's own moves into the custom folder, and the other build is there too",
                  (target / custom.format("amd-fsr4")).read_bytes() == amd
                  and (target / custom.format("cyboman-4.1.2l-lossy")).read_bytes() == b"cyboman 4.1.2l-lossy"
                  and not (target / custom.format("cyboman-4.1.2l-exact")).exists())
            check("one that cannot be downloaded (HLX FSR 4 here) is left out and said so",
                  not (target / "OptiScaler/custom/hlx-fsr4").exists()
                  and [e["upscaler"] for e in result.get("custom_errors", [])] == ["hlx-fsr4"],
                  result.get("custom_errors"))
            picked = asyncio.run(service.install(str(target), "dxgi.dll", True, False, None, "hlx-fsr4"))
            check("but the picked one failing fails the install",
                  not picked.get("ok") and installer.detect(str(target))["upscaler"] == "fsr412l-exact",
                  picked)
            values = IniFile(target / INI_NAME).to_dict().get("Upscalers", {})
            check("and the ini points every API at OptiScaler's own FidelityFX upscaler",
                  values.get("Dx12Upscaler") == "ffx"
                  and values.get("Dx11Upscaler") == "ffx_12" and values.get("VulkanUpscaler") == "ffx_12"
                  and installer.fsr4_status(target)["preset"]["applied"], values)
            verified = asyncio.run(service.verify_install(str(target)))
            check("a verify checks the replaced file against what was put there, not the payload",
                  verified.get("complete") and not verified.get("problems")
                  and any(f["name"] == FFX_UPSCALER_DLL and f["matches_payload"] for f in verified["files"]),
                  verified.get("problems"))
            asyncio.run(service.install(str(target), "dxgi.dll", True, False, None, "fsr412l-lossy"))
            check("switching build swaps the two, AMD's still in the custom folder",
                  main.read_bytes() == b"cyboman 4.1.2l-lossy"
                  and (target / custom.format("cyboman-4.1.2l-exact")).read_bytes() == b"cyboman 4.1.2l-exact"
                  and not (target / custom.format("cyboman-4.1.2l-lossy")).exists()
                  and (target / custom.format("amd-fsr4")).is_file())
            asyncio.run(service.install(str(target), "dxgi.dll", True, False, None, "fsr4-lite"))
            check("going back to FSR 4 Lite puts AMD's back, the builds in the custom folder",
                  main.read_bytes() == amd and not (target / custom.format("amd-fsr4")).exists()
                  and (target / custom.format("cyboman-4.1.2l-exact")).is_file()
                  and (target / custom.format("cyboman-4.1.2l-lossy")).is_file()
                  and IniFile(target / INI_NAME).to_dict()["Upscalers"]["Dx12Upscaler"] == "ffx")
            installer.uninstall(str(target))
            check("and an uninstall takes them all out",
                  not (target / "OptiScaler").exists(), sorted(p.name for p in target.iterdir()))

            # A BC-250 takes HelixSR's two only, and downloads nothing else.
            import optiscaler.service as service_mod
            real_gpu = service_mod.gpu_info
            service_mod.gpu_info = lambda: {"device": "bc250"}
            try:
                refused = asyncio.run(service.install(str(target), "dxgi.dll", False, False, None,
                                                      "fsr412l-lossy"))
                check("on a BC-250 cyboman's build is refused", not refused.get("ok"), refused)
                refused = asyncio.run(service.install_dropin(str(game.parent), "fsr4-lite"))
                check("and so is FSR 4 Lite's drop-in", not refused.get("ok"), refused)
                found, errors = asyncio.run(service._custom_upscalers("hlx-dlss", str(root / "payload")))
                check("and an install there does not even download cyboman's builds",
                      not found and [e["upscaler"] for e in errors] == ["hlx-fsr4"], (found, errors))
            finally:
                service_mod.gpu_info = real_gpu
        finally:
            dropin.wiki.download_json = real_json
    finally:
        shutil.rmtree(root, ignore_errors=True)


def check_channel_versions():
    """Picking which OptiScaler nightly and cyboman build installs download.

    The list runs from the build this plugin was built against to the newest;
    a pin is what the next download asks for, offline it is only what is on
    the Deck, and letting go of a pin goes back to asking for the newest.
    """
    print("\nDownload versions")
    from optiscaler import dropin, nightly, wiki as wiki_mod

    data = b"a nightly archive"
    digest = hashlib.sha256(data).hexdigest()
    base = "https://github.com/optiscaler/OptiScaler-nightly/releases/download"

    def release(day):
        tag = f"nightly-2099010{day}"
        asset = f"OptiScaler_v10.0.0-pre1_2099010{day}.7z"
        return {"tag_name": tag, "published_at": f"2099-01-0{day}T10:00:00Z",
                "assets": [{"name": asset, "size": len(data), "digest": f"sha256:{digest}",
                            "browser_download_url": f"{base}/{tag}/{asset}"}]}

    listed = [release(4), release(3), release(2), release(1)]
    check("every usable release is listed, newest first",
          [r["tag"] for r in nightly.usable_releases(listed)]
          == ["nightly-20990104", "nightly-20990103", "nightly-20990102", "nightly-20990101"])
    check("a tag picks that release rather than the newest",
          nightly.pick_release(listed, "nightly-20990102")["tag"] == "nightly-20990102"
          and nightly.pick_release(listed, "nightly-gone") is None)

    real_json, real_download = wiki_mod.download_json, wiki_mod.download
    state = {"offline": False, "downloads": []}

    def fake_json(url, timeout=20, verified_only=False):
        if state["offline"]:
            raise OSError("network is unreachable")
        return listed if "OptiScaler-nightly" in url else []

    def fake_download(url, dest, timeout=90):
        state["downloads"].append(Path(dest).name)
        Path(dest).write_bytes(data)
        return dest

    root = Path(tempfile.mkdtemp(prefix="optiscaler-channels-"))
    wiki_mod.download_json, wiki_mod.download = fake_json, fake_download
    try:
        channel = nightly.NightlyChannel(root / "nightly")
        channel.ensure(tag="nightly-20990102")
        check("a pinned build is downloaded instead of the newest",
              channel.current()["tag"] == "nightly-20990102", channel.current())
        channel.ensure(force=True, tag="nightly-20990102")
        check("and, once on disk, is not looked for again even when forced",
              len(state["downloads"]) == 1, state["downloads"])
        channel.ensure()
        check("without the pin, installs keep the build on disk",
              channel.current()["tag"] == "nightly-20990102" and len(state["downloads"]) == 1)
        channel.ensure(force=True)
        check("and an update moves to the newest",
              channel.current()["tag"] == "nightly-20990104", channel.current())
        state["offline"] = True
        try:
            channel.ensure(tag="nightly-20990103")
            check("offline, a pin not on disk is an error, not the build that is", False)
        except RuntimeError as exc:
            check("offline, a pin not on disk is an error, not the build that is",
                  "nightly-20990103" in str(exc), exc)
        state["offline"] = False

        # The service: the baseline cuts the list, the pin travels into downloads.
        plugin = root / "plugin"
        (plugin / "defaults").mkdir(parents=True)
        (plugin / "defaults" / "channel-baseline.json").write_text(json.dumps({
            "nightly": {"tag": "nightly-20990102", "published_at": "2099-01-02T10:00:00Z"},
            "dropin": {"tag": "dll-2099-01-01", "published_at": "2099-01-01T10:00:00Z"},
        }))
        service = OptiScalerService(plugin, root / "settings", root / "runtime", root,
                                    logging.getLogger("selftest"))
        service.nightly = channel
        versions = asyncio.run(service.get_channel_versions("nightly"))
        tags = [v["tag"] for v in versions["versions"]]
        check("the list starts at the build the plugin was built against",
              tags == ["nightly-20990104", "nightly-20990103", "nightly-20990102"], tags)
        check("which is marked, as is the one already downloaded",
              [v["tag"] for v in versions["versions"] if v["baseline"]] == ["nightly-20990102"]
              and [v["tag"] for v in versions["versions"] if v["downloaded"]] == ["nightly-20990104"],
              versions["versions"])
        check("an unknown channel is refused",
              not asyncio.run(service.get_channel_versions("other"))["ok"])

        asyncio.run(service.set_channel_version("nightly", "nightly-20990103"))
        asked = []
        service.payload.ensure = lambda force=False, logger=None, tag=None: asked.append(tag) or root
        asyncio.run(service.ensure_payload())
        check("a pin is what the next install downloads",
              asked == ["nightly-20990103"], asked)
        check("and installs are judged against it, not the download",
              service.nightly_target() == "nightly-20990103")

        service._channel_lists.clear()
        state["offline"] = True
        offline = asyncio.run(service.get_channel_versions("nightly"))
        check("offline, the list is the baseline, the pin and what is downloaded",
              offline["ok"] and offline["error"]
              and [v["tag"] for v in offline["versions"]]
              == ["nightly-20990104", "nightly-20990103", "nightly-20990102"], offline)
        state["offline"] = False

        asyncio.run(service.set_channel_version("nightly", None))
        asked.clear()
        asyncio.run(service.ensure_payload())
        check("clearing the pin asks for the newest again", asked == [None], asked)

        asyncio.run(service.set_channel_version("dropin", "dll-2099-01-01"))
        fetched = []
        real_fetch = dropin.fetch
        dropin.fetch = lambda cache, logger=None, variant=None, tag=None: (
            fetched.append(tag) or (_ for _ in ()).throw(FileNotFoundError("stop here")))
        try:
            game = root / "games" / "Split" / "bin"
            game.mkdir(parents=True)
            (game / "Game.exe").write_bytes(_pe(0x8664))
            (game / "amd_fidelityfx_upscaler_dx12.dll").write_bytes(b"game upscaler 3.1")
            asyncio.run(service.install_dropin(str(game.parent), "fsr412l-exact"))
            check("the cyboman pin travels into the drop-in download",
                  fetched == ["dll-2099-01-01"], fetched)
        finally:
            dropin.fetch = real_fetch
    finally:
        wiki_mod.download_json, wiki_mod.download = real_json, real_download
        shutil.rmtree(root, ignore_errors=True)


def check_amd_dropin():
    """FSR 4 Lite as a drop-in: AMD's own FSR 4.1.2 from the nightly, a test.

    Where the game has FSR 3.1 to swap, the file is the nightly's, recorded
    under the nightly's tag; anywhere else FSR 4 Lite is still OptiScaler.
    """
    print("\nFSR 4 Lite drop-in")
    from optiscaler.constants import FFX_UPSCALER_DLL

    root = Path(tempfile.mkdtemp(prefix="optiscaler-amd-dropin-"))
    try:
        service = OptiScalerService(ROOT, root / "settings", root / "runtime", root,
                                    logging.getLogger("selftest"))
        payload = build_payload(root)
        use_payload(service, payload)
        game = root / "games" / "Split" / "bin"
        game.mkdir(parents=True)
        (game / "Game.exe").write_bytes(_pe(0x8664))
        (game / "amd_fidelityfx_upscaler_dx12.dll").write_bytes(b"game upscaler 3.1")
        result = asyncio.run(service.install_dropin(str(game.parent), "fsr4-lite"))
        state = asyncio.run(service.get_dropin(str(game.parent)))
        check("the nightly's own upscaler replaces the game's FSR 3.1 file",
              result.get("ok") and (game / "amd_fidelityfx_upscaler_dx12.dll").read_bytes()
              == (payload / FFX_UPSCALER_DLL).read_bytes(), result.get("error"))
        check("recorded as the FSR 4 Lite drop-in, under the nightly's tag",
              state.get("upscaler") == "fsr4-lite" and state.get("variant") == "amd"
              and state.get("tag") == FAKE_RELEASE["tag"], state)
        asyncio.run(service.remove_dropin(str(game.parent)))
        check("removing it puts the game's file back",
              (game / "amd_fidelityfx_upscaler_dx12.dll").read_bytes() == b"game upscaler 3.1")

        target = root / "games" / "NoFsr"
        target.mkdir(parents=True)
        (target / "Game.exe").write_bytes(b"MZ")
        result = asyncio.run(service.install(str(target), "dxgi.dll", False, False, None,
                                             "fsr4-lite"))
        check("without FSR 3.1, FSR 4 Lite is still OptiScaler",
              result.get("ok") and installer.detect(str(target))["upscaler"] == "fsr4-lite",
              result.get("error"))
    finally:
        shutil.rmtree(root, ignore_errors=True)


def check_pd_upscaler_games():
    """The pd-upscaler games: DMC5's pinned build, PDPerfPlugin, libxess.dll at the root.

    Three things the wiki asks of these games and a plain install got wrong:
    DMC5 is broken on the newest pd build, PDPerfPlugin has to be the 1.1.2
    build, and since v10 moved libxess.dll into OptiScaler/ PDPerfPlugin's
    upscaler cannot start without a copy at the root.
    """
    print("\npd-upscaler games")
    from optiscaler import reframework, wiki as wiki_mod
    from optiscaler.constants import REFRAMEWORK_DLL, REFRAMEWORK_PD_PLUGIN

    dmc5 = reframework.resolve({"asset": "DMC5.zip", "variant": "pd-upscaler", "automatic": True})
    check("DMC5 gets the build the wiki pins, not the newest release",
          dmc5["url"].endswith("/DMC5_working.zip") and len(dmc5["sha256"]) == 64, dmc5)

    root = Path(tempfile.mkdtemp(prefix="optiscaler-pd-"))
    real_download = wiki_mod.download
    try:
        def tampered(url, dest, timeout=90):
            Path(dest).parent.mkdir(parents=True, exist_ok=True)
            Path(dest).write_bytes(b"not the pinned build")
            return dest

        wiki_mod.download = tampered
        try:
            reframework.fetch({"asset": "DMC5.zip", "variant": "pd-upscaler", "automatic": True},
                              root / "cache")
            check("and a download that is not those bytes is refused", False)
        except ValueError:
            check("and a download that is not those bytes is refused", True)
        finally:
            wiki_mod.download = real_download

        # PDPerfPlugin.dll may not be redistributed: the user downloads it and
        # leaves it in Downloads, and nothing in the package carries it.
        check("PDPerfPlugin.dll is not bundled", not (ROOT / "bin" / REFRAMEWORK_PD_PLUGIN).exists())
        home = root / "home"
        service = OptiScalerService(ROOT, root / "settings", root / "runtime", home,
                                    logging.getLogger("selftest"))
        state = service.pd_plugin_state()
        check("with nothing downloaded it is missing, and says where to get it and put it",
              not state["present"] and service.pd_plugin_files() == []
              and state["url"] == "https://www.nexusmods.com/site/mods/502"
              and state["folder"].endswith("Downloads"), state)

        # Pretend this is the 1.1.2 build by pinning whatever the fixture is.
        import optiscaler.service as service_mod
        real_pin = service_mod.REFRAMEWORK_PD_PLUGIN_SHA256
        build = b"MZ PDPerfPlugin 1.1.2"
        service_mod.REFRAMEWORK_PD_PLUGIN_SHA256 = hashlib.sha256(build).hexdigest()
        try:
            other = home / "Downloads" / "old" / "PDPerfPlugin.dll"
            other.parent.mkdir(parents=True)
            other.write_bytes(b"MZ PDPerfPlugin 1.2.0")
            state = service.pd_plugin_state()
            check("another build in Downloads is used, marked as not the one the wiki names",
                  state["present"] and not state["verified"], state)
            right = home / "Downloads" / "UpscalerBasePlugin 1.1.2" / "PDPerfPlugin.dll"
            right.parent.mkdir(parents=True)
            right.write_bytes(build)
            state = service.pd_plugin_state()
            check("and the 1.1.2 build, in a subfolder, replaces it once it turns up",
                  state["present"] and state["verified"], state)
            shutil.rmtree(home / "Downloads")
            plugin = service.pd_plugin_files()
            check("it is kept, so clearing Downloads later loses nothing",
                  plugin and plugin[0].read_bytes() == build, plugin)
        finally:
            service_mod.REFRAMEWORK_PD_PLUGIN_SHA256 = real_pin

        # An install through the pd-upscaler plan, then a nightly update, then removal.
        payload = build_payload(root)
        game = root / "RE2"
        game.mkdir()
        (game / "re2.exe").write_bytes(b"MZ")
        ref_dir = root / "ref"
        ref_dir.mkdir()
        (ref_dir / REFRAMEWORK_DLL).write_bytes(b"REF pd build")
        installer.install(str(game), str(payload), "dxgi.dll", False, None, None,
                          [ref_dir / REFRAMEWORK_DLL] + plugin, "rev", FAKE_RELEASE, True)
        manifest = installer.read_manifest(game)
        check("REFramework, PDPerfPlugin and libxess.dll all land by the executable",
              all((game / n).is_file() for n in (REFRAMEWORK_DLL, REFRAMEWORK_PD_PLUGIN, "libxess.dll"))
              and manifest["pd_upscaler"], manifest.get("files"))
        installer.install(str(game), str(payload), "dxgi.dll", True, None, None, None, None,
                          {"tag": "nightly-20990102", "version": "10.0.0-next"})
        again = installer.read_manifest(game)
        check("a reinstall that knows nothing of the plan keeps all three, tracked",
              all(n in again["files"] for n in (REFRAMEWORK_DLL, REFRAMEWORK_PD_PLUGIN, "libxess.dll"))
              and (game / "libxess.dll").is_file(), again.get("files"))

        late = root / "RE3"
        late.mkdir()
        (late / "re3.exe").write_bytes(b"MZ")
        installer.install(str(late), str(payload), "dxgi.dll", False, None, None,
                          [ref_dir / REFRAMEWORK_DLL], "rev", FAKE_RELEASE, True)
        added = asyncio.run(service.install_pd_plugin(str(late)))
        check("a game set up before the file was supplied can be given it afterwards",
              added["ok"] and (late / REFRAMEWORK_PD_PLUGIN).is_file()
              and REFRAMEWORK_PD_PLUGIN in installer.read_manifest(late)["files"], added)

        removed = asyncio.run(service.remove_reframework(str(game)))
        check("taking REFramework out takes PDPerfPlugin and the root libxess.dll with it",
              removed["ok"] and not any((game / n).exists()
                                        for n in (REFRAMEWORK_DLL, REFRAMEWORK_PD_PLUGIN, "libxess.dll")),
              removed)
        installer.uninstall(str(game))
        check("and an uninstall leaves only the game", sorted(p.name for p in game.iterdir()) == ["re2.exe"],
              sorted(p.name for p in game.iterdir()))
    finally:
        shutil.rmtree(root, ignore_errors=True)


def check_option_validation():
    """Values the config writer accepts, for the keys whose list is not fixed.

    A write the writer refuses is dropped *and* never pushed to the running
    game, and the panel is left showing a choice that reached neither. That is
    only correct when the refusal is: FSR.FGIndex is documented in the shipped
    ini as the two generators the reference build had, but each game's
    FidelityFX runtime reports its own list, and the plugin lists what the game
    reports. Validating a pick against the ini's two entries therefore refused
    every generator past the second one that a game actually offered.

    FSR.UpscalerIndex is the same snapshot one step over -- the ini names the
    three FSR versions the reference build shipped, and the game in the
    screenshot this was written from reports 4.1.1, which is in none of them.
    """
    from optiscaler.schema import FFX_FG_MAX, FFX_UPSCALER_MAX, SCHEMA, valid

    print("\nOption validation")

    fg_index = SCHEMA[("FSR", "FGIndex")]
    check("the reference ini only documents two FFX generators",
          fg_index["options"] == ["0", "1"], fg_index["options"])
    check("but a third one the game reports is accepted", valid(fg_index, "2"))
    check("up to the ceiling an index can reach",
          valid(fg_index, str(FFX_FG_MAX - 1)) and not valid(fg_index, str(FFX_FG_MAX)))
    check("an index that is not one is still refused",
          not valid(fg_index, "-1") and not valid(fg_index, "fsr"))
    check("auto still means auto", valid(fg_index, "auto"))

    ups_index = SCHEMA[("FSR", "UpscalerIndex")]
    check("the reference ini only documents three FSR versions",
          ups_index["options"] == ["0", "1", "2"], ups_index["options"])
    check("but a fourth the game reports is accepted", valid(ups_index, "3"))
    check("up to the same ceiling",
          valid(ups_index, str(FFX_UPSCALER_MAX - 1))
          and not valid(ups_index, str(FFX_UPSCALER_MAX)))
    check("an index that is not one is still refused",
          not valid(ups_index, "-1") and not valid(ups_index, "fsr4"))

    # FSR4Preset is a closed set of six, and the reference ini writes it as one
    # comma-separated list rather than the "0 = A / 1 = B" form the generator was
    # built around. It read that as two entries with the other four buried in the
    # labels, which made "1", "3", "4" and "5" unwritable — the Quality and
    # Performance models among them. OptiScaler clamps the same range, so six is
    # the truth rather than one build's snapshot.
    fsr4_preset = SCHEMA[("FSR", "Fsr4Preset")]
    check("the FSR4 preset names all six presets",
          fsr4_preset["options"] == ["0", "1", "2", "3", "4", "5"],
          fsr4_preset["options"])
    check("so Quality and Performance can be picked",
          valid(fsr4_preset, "1") and valid(fsr4_preset, "3"))
    check("and one OptiScaler does not have is refused", not valid(fsr4_preset, "6"))

    # Everything else keeps the closed-set treatment: these lists are the
    # backends OptiScaler has, not a snapshot of one runtime's answer.
    dx11 = SCHEMA[("Upscalers", "Dx11Upscaler")]
    check("a real backend id is accepted", valid(dx11, "ffx_12"))
    check("an id OptiScaler does not have is not", not valid(dx11, "ffx"))
    # Dx12 and Vulkan also take a custom upscaler, by its folder's name: any name
    # is one, but a path is not.
    dx12 = SCHEMA[("Upscalers", "Dx12Upscaler")]
    check("Dx12Upscaler takes a backend id or a custom upscaler's folder name",
          valid(dx12, "ffx") and valid(dx12, "cyboman-4.1.2l-lossy"))
    check("but not a path", not valid(dx12, "custom/x") and not valid(dx12, "..\\x"))

    # The FSR 4 Lite preset goes into every install, so every key in it has to
    # be one this schema knows with a value it accepts - or an install would
    # half-apply it, some keys written and others silently dropped.
    from optiscaler.schema import option as schema_option
    bad = [f"{s}.{k}={v}" for s, values in DECK_FSR4_PRESET.items() for k, v in values.items()
           if not (schema_option(s, k) and valid(schema_option(s, k), v))]
    check("every key the FSR 4 Lite preset writes is accepted", not bad, bad)


def main():
    logging.basicConfig(level=logging.ERROR)
    asyncio.run(run())
    check_remembered_choices()
    check_launch_record()
    check_launch_options_read()
    check_non_steam_shortcut()
    check_wiki_failure_reporting()
    check_wiki_cache()
    check_wiki_transport()
    check_wiki_tls()
    check_optipatcher()
    check_optipatcher_channel()
    check_optipatcher_offline_install()
    check_pd_upload()
    check_auto_plan()
    check_reframework()
    check_reframework_downloads()
    check_dropin()
    check_helixsr()
    check_requirements()
    check_cyboman()
    check_hlx()
    check_hlx_build()
    check_setup()
    check_lsfgvk()
    check_channel_versions()
    check_amd_dropin()
    check_pd_upscaler_games()
    check_prose_is_not_a_specification()
    check_parenthesised_pages()
    check_compat_list_shapes()
    check_option_validation()
    check_library_labels()
    check_devices()
    check_compat()
    check_nightly()
    check_versioning()
    check_plugin_updates()
    check_update_installed_games()
    print(f"\n{len(PASSED)} passed, {len(FAILED)} failed")
    if FAILED:
        for name in FAILED:
            print(f"  FAILED: {name}")
        sys.exit(1)


if __name__ == "__main__":
    main()
