"""Whether OptiScaler is worth trying in a game, before anything is installed.

Two independent signals, because neither is enough on its own:

- **The game's own files.** OptiScaler takes over an upscaler the game already
  calls, so a shipped DLSS, XeSS or FSR library is the strongest local hint
  that there is something to take over. It also only loads into 64-bit Windows
  executables, and anti-cheat tends to refuse the injection outright.
- **The wiki's compatibility list.** Someone has tried it and said how it went.

The files are what this install actually is (a native Linux build listed on the
wiki is still not something OptiScaler can go into), and the wiki is what
people found in practice, so `verdict` puts the hard facts from the files first
and the wiki's word ahead of the softer file hints.

Scanning is a directory walk per game, so the service caches it; the wiki match
is cheap enough to redo whenever the list changes.
"""

import os
from pathlib import Path

from .constants import (
    INI_NAME,
    PAYLOAD_DIRS,
    REFRAMEWORK_PD_ROOT_LIBS,
)
from . import reframework, requirements
from .constants import BACKUP_DIR, FFX_DX12_DLL, FFX_UPSCALER_FILE
from .steam import _score_exe

# Upscaler libraries a game ships, by the input OptiScaler can take over. Not
# finding one proves little - plenty of games link FSR statically - which is
# why that case is "unknown" rather than "unsupported".
INPUT_DLLS = {
    "nvngx_dlss.dll": "DLSS",
    "sl.dlss.dll": "DLSS",
    "libxess.dll": "XeSS",
    "libxess_dx11.dll": "XeSS",
    "ffx_fsr2_api_x64.dll": "FSR2",
    "ffx_fsr2_api_dx12_x64.dll": "FSR2",
    "ffx_fsr2_api_vk_x64.dll": "FSR2",
    "amd_fidelityfx_dx12.dll": "FSR3.1",
    "amd_fidelityfx_vk.dll": "FSR3.1",
    "amd_fidelityfx_upscaler_dx12.dll": "FSR3.1",
}
INPUT_ORDER = ["DLSS", "XeSS", "FSR2", "FSR3.1"]

# Anti-cheat leaves either its own folder or one of these files behind.
ANTI_CHEAT_DIRS = {"easyanticheat": "Easy Anti-Cheat", "battleye": "BattlEye"}
ANTI_CHEAT_FILES = {
    "easyanticheat_x64.dll": "Easy Anti-Cheat",
    "easyanticheat_eos_setup.exe": "Easy Anti-Cheat",
    "start_protected_game.exe": "Easy Anti-Cheat",
    "beclient_x64.dll": "BattlEye",
    "beservice_x64.exe": "BattlEye",
}

PE_MACHINES = {0x8664: "x64", 0x014C: "x86", 0xAA64: "arm64"}

# Deep enough for Unreal's Engine/Plugins/.../ThirdParty/Win64/nvngx_dlss.dll,
# bounded so one enormous install cannot hold up the whole list.
MAX_DEPTH = 10
MAX_FILES = 60000
# Headers read while looking for a 64-bit executable, best-scored first.
MAX_EXE_PROBES = 12

# OptiScaler's own folders, whose support DLLs are not the game's.
_PAYLOAD_DIR_NAMES = {name.lower() for name in PAYLOAD_DIRS}
# What an install of this plugin puts at the game root besides the proxy:
# libxess.dll for the pd-upscaler games.
_ROOT_LIBS = {name.lower() for name in REFRAMEWORK_PD_ROOT_LIBS}
_OPTISCALER_MARKERS = {INI_NAME.lower(), "optiscaler.asi"}


def pe_machine(path):
    """The architecture a Windows executable was built for, or None."""
    try:
        with open(path, "rb") as handle:
            header = handle.read(64)
            if len(header) < 64 or header[:2] != b"MZ":
                return None
            offset = int.from_bytes(header[0x3C:0x40], "little")
            handle.seek(offset)
            signature = handle.read(6)
    except OSError:
        return None
    if len(signature) < 6 or signature[:4] != b"PE\0\0":
        return None
    return PE_MACHINES.get(int.from_bytes(signature[4:6], "little"), "other")


def _is_optiscaler_dir(names):
    """Whether OptiScaler itself is installed in a folder with these files.

    Then a libxess.dll beside it is the one put there for PDPerfPlugin, not
    the game's XeSS. Whatever the game had under that name was moved to the
    backup folder, which is scanned.
    """
    return bool({name.lower() for name in names} & _OPTISCALER_MARKERS)


def scan(game_path):
    """What a game's folder says about OptiScaler, without changing anything."""
    root = Path(game_path)
    result = {
        "inputs": [],
        "input_files": [],
        "exe": None,
        "arch": None,
        "anti_cheat": [],
        # The game's own DX12 FidelityFX, which the FSR drop-in replaces.
        "ffx_dx12": [],
        "complete": True,
    }
    if not root.is_dir():
        result["complete"] = False
        return result

    inputs = set()
    anti_cheat = set()
    exes = []
    seen = 0
    root_depth = len(root.parts)
    for dirpath, dirnames, filenames in os.walk(root):
        current = Path(dirpath)
        depth = len(current.parts) - root_depth
        for name in dirnames:
            label = ANTI_CHEAT_DIRS.get(name.lower())
            if label:
                anti_cheat.add(label)
        if depth >= MAX_DEPTH:
            dirnames[:] = []
        else:
            dirnames[:] = [d for d in dirnames
                           if not d.startswith(".") and d.lower() not in _PAYLOAD_DIR_NAMES]

        ours = _is_optiscaler_dir(filenames)
        for filename in filenames:
            lowered = filename.lower()
            source = INPUT_DLLS.get(lowered)
            if source and not (ours and lowered in _ROOT_LIBS):
                inputs.add(source)
                # The backup folder holds originals an install displaced; the
                # drop-in goes where the game loads its FidelityFX from.
                if (lowered in (FFX_DX12_DLL, FFX_UPSCALER_FILE)
                        and BACKUP_DIR.lower() not in (p.lower() for p in current.relative_to(root).parts)
                        and len(result["ffx_dx12"]) < 4):
                    result["ffx_dx12"].append(str((current / filename).relative_to(root)))
                if len(result["input_files"]) < 8:
                    result["input_files"].append(str((current / filename).relative_to(root)))
            label = ANTI_CHEAT_FILES.get(lowered)
            if label:
                anti_cheat.add(label)
            if lowered.endswith(".exe"):
                exe = current / filename
                score = _score_exe(exe, root)
                if score > -100:
                    exes.append((score, exe))

        seen += len(filenames)
        if seen >= MAX_FILES:
            result["complete"] = False
            break

    result["inputs"] = [name for name in INPUT_ORDER if name in inputs]
    result["anti_cheat"] = sorted(anti_cheat)

    # The best-scored executable is reported, but a 32-bit launcher in front
    # of a 64-bit game must not make the game read as 32-bit: any 64-bit
    # candidate is the one that counts.
    exes.sort(key=lambda pair: -pair[0])
    for _, exe in exes[:MAX_EXE_PROBES]:
        arch = pe_machine(exe)
        if arch is None:
            continue
        if result["exe"] is None or arch == "x64":
            result["exe"] = str(exe.relative_to(root))
            result["arch"] = arch
        if arch == "x64":
            break
    return result


def _wiki_status(compatibility):
    text = compatibility or ""
    if "❌" in text:
        return "broken"
    if "✅" in text:
        return "works"
    if "➖" in text:
        return "partial"
    return None


def verdict(found, entry):
    """Combine a folder scan with the matched wiki entry, if any.

    Returns ``status`` for the badge, ``compatible`` for the list filter and a
    one-line ``summary`` that says which signal decided it.
    """
    inputs = found.get("inputs") or []
    anti_cheat = found.get("anti_cheat") or []
    wiki = None
    if entry:
        wiki = {
            "name": entry.get("name"),
            "compatibility": entry.get("compatibility"),
            "inputs": entry.get("inputs"),
            "status": _wiki_status(entry.get("compatibility")),
            "manual": bool(entry.get("manual")),
        }
    wiki_status = wiki["status"] if wiki else None
    detected = ", ".join(inputs)
    caveat = f" · {', '.join(anti_cheat)}" if anti_cheat else ""

    if found.get("complete", True) and not found.get("exe"):
        status, summary = "unsupported", "Windows 실행 파일 없음 (Linux 네이티브 빌드?)"
    elif found.get("arch") and found["arch"] != "x64":
        status, summary = "unsupported", f"{found['arch']} 실행 파일 — OptiScaler는 64비트가 필요합니다"
    elif wiki_status == "broken":
        status, summary = "broken", "위키: 작동 안 함"
    elif wiki_status == "works":
        status, summary = "listed", f"위키 ✅ · {wiki['inputs'] or detected or '입력 정보 없음'}{caveat}"
    elif wiki_status == "partial":
        status, summary = "partial", f"위키: 일부 작동{caveat}"
    elif anti_cheat:
        status, summary = "risky", f"안티치트: {', '.join(anti_cheat)}"
    elif inputs:
        status, summary = "likely", f"{detected} 발견"
    else:
        status, summary = "unknown", "DLSS/XeSS/FSR 라이브러리 없음"

    # REFramework, as the wiki's list row states it. A game whose own FSR 3.1
    # can take the drop-in has a way to FSR 4 without it.
    needs_ref = bool(entry and reframework.requirement([("notes", entry.get("notes") or "")]))
    can_dropin = bool(found.get("ffx_dx12")) and found.get("arch") in (None, "x64")
    return {
        "status": status,
        "compatible": status in ("listed", "likely", "partial"),
        "dropin": can_dropin,
        "reframework": needs_ref,
        "reframework_only": needs_ref and not can_dropin,
        # The wiki's OptiPatcher column: its patterns cover this game.
        "optipatcher": bool(entry and entry.get("optipatcher")),
        # What the list row says the game cannot go without besides OptiScaler:
        # a mod, Engine.ini lines, a file. Said, not installed.
        "requires": requirements.required_names(entry) if entry else [],
        "summary": summary,
        "wiki": wiki,
        **found,
    }
